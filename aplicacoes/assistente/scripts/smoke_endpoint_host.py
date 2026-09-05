#!/usr/bin/env python3
"""Smoke do endpoint clássico no host, sem containers, usando FastAPI TestClient.

Este script mantém o foco no router ``/llm_lang/stream``. Ele não recebe
documentos de processo; para uma sessão com ``id_procedimentos`` use
``smoke_session_host.py`` ou ``smoke_session_stack.sh``.

Uso esperado, a partir de ``aplicacoes/assistente`` neste worktree:

    uv run python scripts/smoke_endpoint_host.py
    uv run python scripts/smoke_endpoint_host.py --no-thinking
    uv run python scripts/smoke_endpoint_host.py --local-upload-smoke --mock-llm
    uv run python scripts/smoke_endpoint_host.py --text "Escreva um poema simples apenas para teste."

O script:
- carrega `.env` e `security.env` do root do worktree, sem imprimir segredos;
- sobe a app FastAPI em memória com TestClient;
- faz POST em `/llm_lang/stream`;
- consome eventos SSE;
- quando `--local-upload-smoke` é usado, simula interação local com arquivo avulso
  passando pelo router HTTP, extração real do arquivo local, persistência em cache fake
  e tool de consulta de anexo no agente;
- imprime um resumo seguro: tipos de evento, amostra de conteúdo, reasoning, metadata,
  cache de anexos e erros.

Não usa servidor externo da API do Assistente; apenas o LiteLLM/proxy e demais serviços
configurados nos envs quando o fluxo real precisar deles. Para teste hermético de
arquivos avulsos, use `--mock-llm --local-upload-smoke`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
import types
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi.testclient import TestClient

ENDPOINT = "/llm_lang/stream"
DEFAULT_TEXT = (
    "Escreva um poema simples apenas para teste. Responda em no máximo 4 versos."
)
DEFAULT_UPLOAD_TEXT = (
    "Consulte o arquivo avulso deste tópico e responda citando o nome do arquivo e "
    "o identificador interno que está no conteúdo."
)
DEFAULT_SYSTEM_PROMPT = (
    "Você é um assistente útil. Para este teste, responda de forma breve e direta."
)
DEFAULT_UPLOAD_FILENAME = "relatorio-avulso-local.txt"
DEFAULT_UPLOAD_CONTENT = """Relatório local para smoke de arquivos avulsos.
Identificador interno: ARQUIVO-AVULSO-LOCAL-42.
A recomendação final é preservar a compatibilidade do fluxo de reasoning.
"""
_LAST_FAKE_CACHE: FakeRedisJsonCache | None = None
_LAST_UPLOAD_TEMP_FILES: list[Path] = []


def find_repo_root(start: Path) -> Path:
    """Sobe a árvore até encontrar o root do worktree Git."""
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError(f"Não foi possível encontrar root Git a partir de {start}")


def load_worktree_envs(app_dir: Path) -> list[Path]:
    """Carrega envs do root do worktree e do diretório da app."""
    repo_root = find_repo_root(app_dir)
    # Ordem intencional: defaults primeiro, depois segredos/sobrescritas.
    # Usamos override=True entre arquivos para reproduzir o merge típico do compose/env_file;
    # variáveis exportadas pelo shell antes do script ainda podem ser usadas ajustando os envs
    # explicitamente fora daqui se necessário.
    candidates = [
        repo_root / "default.env",
        repo_root / "security.env",
        repo_root / ".env",
        app_dir / ".env",
        app_dir / "security.env",
    ]
    loaded: list[Path] = []
    for env_file in candidates:
        if env_file.exists():
            load_dotenv(env_file, override=True)
            loaded.append(env_file)

    # Compatibilidade local: alguns envs do compose usam SEI_ADDRESS, enquanto
    # Settings exige SEI_API_DB_ADDRESS. Não imprime o valor.
    if not os.getenv("SEI_API_DB_ADDRESS") and os.getenv("SEI_ADDRESS"):
        os.environ["SEI_API_DB_ADDRESS"] = os.environ["SEI_ADDRESS"]

    local_required_defaults = {
        "SOLR_USER": "local-smoke-solr-user",
        "SOLR_PASSWORD": "local-smoke-solr-password",
        "DB_SEIIA_USER": "local-smoke-db-user",
        "DB_SEIIA_PWD": "local-smoke-db-password",
        "SEI_API_DB_ADDRESS": "http://local-smoke-sei-api",
        "SEI_API_DB_IDENTIFIER_SERVICE": "local-smoke-service",
    }
    for key, value in local_required_defaults.items():
        os.environ.setdefault(key, value)

    # Alguns valores do default.env usam interpolação estilo compose. Como o
    # security.env é carregado depois, reexpande os principais campos ao final.
    for key in (
        "LITELLM_PROXY_URL",
        "DB_SEIIA_HOST",
        "DB_SEIIA_PORT",
        "DB_SEIIA_ASSISTENTE",
        "SEI_API_DB_IDENTIFIER_SERVICE",
    ):
        value = os.getenv(key)
        if value and "${" in value:
            os.environ[key] = os.path.expandvars(value)

    return loaded


def redact_path(path: Path) -> str:
    """Mostra só o caminho, nunca o conteúdo."""
    try:
        return str(path.relative_to(find_repo_root(Path.cwd())))
    except Exception:
        return str(path)


def parse_sse_events(raw_text: str) -> list[dict[str, Any]]:
    """Parse simples de eventos SSE no formato `data: {...}\n\n`."""
    events: list[dict[str, Any]] = []
    for block in raw_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        data_lines = []
        for line in block.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if not data_lines:
            continue
        data = "\n".join(data_lines)
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            parsed = {"type": "_unparsed", "data": data}
        events.append(parsed)
    return events


def consume_stream_response(response) -> tuple[str, list[dict[str, Any]]]:
    """Consome a resposta do TestClient e retorna texto bruto + eventos parseados."""
    # TestClient normalmente já materializa o streaming em response.text.
    raw_text = response.text
    return raw_text, parse_sse_events(raw_text)


def summarize_events(
    events: list[dict[str, Any]], max_chars: int = 1200
) -> dict[str, Any]:
    counter = Counter(str(event.get("type", "<missing>")) for event in events)
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    statuses: list[str] = []
    errors: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []

    for event in events:
        event_type = event.get("type")
        data = event.get("data")
        if event_type == "content" and isinstance(data, str):
            content_parts.append(data)
        elif event_type == "reasoning" and isinstance(data, str):
            reasoning_parts.append(data)
        elif event_type == "status" and isinstance(data, str):
            statuses.append(data)
        elif event_type == "error":
            errors.append(event)
        elif event_type == "metadata" and isinstance(data, dict):
            metadata.append(data)

    content = "".join(content_parts)
    reasoning = "".join(reasoning_parts)
    final_metadata = metadata[-1] if metadata else None

    return {
        "event_count": len(events),
        "event_types": dict(counter),
        "status_samples": statuses[:10],
        "content_chars": len(content),
        "content_preview": content[:max_chars],
        "reasoning_chars": len(reasoning),
        "reasoning_preview": reasoning[:max_chars],
        "metadata_present": bool(final_metadata),
        "metadata_keys": sorted(final_metadata.keys()) if final_metadata else [],
        "metadata_model": final_metadata.get("model") if final_metadata else None,
        "metadata_use_thinking": final_metadata.get("use_thinking")
        if final_metadata
        else None,
        "metadata_finish_reason": final_metadata.get("finish_reason")
        if final_metadata
        else None,
        "metadata_reasoning_chars": len(str(final_metadata.get("reasoning") or ""))
        if final_metadata
        else 0,
        "errors": errors,
        "has_end_event": any(event.get("type") == "end" for event in events),
    }


class FakeRedisJsonCache:
    """Cache JSON em memória para simular Redis no smoke local."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.ttl: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get_json(self, key: str) -> Any:
        return self.store.get(key)

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> bool:
        self.store[key] = value
        if ttl is not None:
            self.ttl[key] = ttl
        return True

    async def expire(self, key: str, ttl: int) -> bool:
        if key not in self.store:
            return False
        self.ttl[key] = ttl
        return True

    async def delete_key(self, key: str) -> bool:
        self.deleted.append(key)
        return self.store.pop(key, None) is not None

    def snapshot(self) -> dict[str, Any]:
        return {
            "keys": sorted(self.store),
            "values": self.store,
            "ttl": self.ttl,
            "deleted": self.deleted,
        }


def prepare_local_upload_file(args: argparse.Namespace) -> Path:
    """Cria um arquivo local que será retornado pelo mock de download do SEI."""
    global _LAST_UPLOAD_TEMP_FILES  # noqa: PLW0603

    if args.upload_file:
        source = Path(args.upload_file).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(
                f"Arquivo informado em --upload-file não existe: {source}"
            )
        return source

    tmp_dir = Path(tempfile.mkdtemp(prefix="assistente-upload-smoke-"))
    upload_path = tmp_dir / args.upload_name
    upload_path.write_text(args.upload_content, encoding="utf-8")
    _LAST_UPLOAD_TEMP_FILES.append(upload_path)
    return upload_path


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "id_usuario": args.id_usuario,
        "id_topico": args.id_topico,
        "id_request": args.id_request,
        "ip": "127.0.0.1",
        "text": args.text,
        "system_prompt": args.system_prompt,
        "use_thinking": args.thinking,
        "use_websearch": args.websearch,
        "summarize_history": False,
        "skip_memory": True,
        # Sem documentos SEI para manter o teste focado em arquivos avulsos/agente/LLM.
        "id_procedimentos": None,
        "arquivos_avulsos": None,
    }
    if args.local_upload_smoke:
        payload["id_topico"] = args.id_topico or 424242
        payload["text"] = args.text or DEFAULT_UPLOAD_TEXT
        payload["arquivos_avulsos"] = [
            {
                "id_arquivo_avulso": args.upload_id,
                "nome_arquivo_avulso": args.upload_name,
                "extensao_arquivo_avulso": args.upload_ext,
            }
        ]
    return payload


def install_local_smoke_stubs() -> None:  # noqa: C901  # NOSONAR
    """Neutraliza side-effects de Postgres/Redis no smoke local.

    O objetivo do smoke_endpoint_host.py é validar o endpoint FastAPI + stream + agente/LLM.
    No shell fora do Docker, hosts como `infra-postgres` e `infra-redis` não
    resolvem. Para payload sem documentos e sem memória, essas integrações não
    são necessárias para a resposta do agente, mas alguns módulos conectam no
    import/startup. Estes stubs evitam apenas esses side-effects.
    """

    class DummyMetaData:
        def create_all(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
            return None

    class DummyBasePgvector:
        metadata = DummyMetaData()

    class DummyEngine:
        def connect(self):
            return self

        def execute(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
            return None

        def commit(self) -> None:
            return None

        def dispose(self) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, ARG002
            return False

    class DummyAsyncDbInstance:
        engine = DummyEngine()
        async_engine = None
        conn_str = "postgresql://local-smoke/stub"

        async def connect(self):
            return self

        @staticmethod
        def hide_password(connection_string: str) -> str:
            return connection_string

        async def close(self) -> None:
            return None

    db_instances = types.ModuleType("sei_ia.data.database.db_instances")
    db_instances.BasePgvector = DummyBasePgvector
    db_instances.app_db_instance = DummyAsyncDbInstance()
    sys.modules["sei_ia.data.database.db_instances"] = db_instances

    table_manager = types.ModuleType("sei_ia.data.database.table_manager")

    class DummyTableManager:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
            pass

        def initialize_all_tables(self) -> bool:
            return True

    table_manager.TableManager = DummyTableManager
    sys.modules["sei_ia.data.database.table_manager"] = table_manager

    runtime_bootstrap = types.ModuleType("sei_ia.data.database.runtime_bootstrap")

    async def initialize_runtime_database(
        _db: Any,
        _metadata: Any,
    ) -> None:
        return None

    runtime_bootstrap.initialize_runtime_database = initialize_runtime_database
    sys.modules["sei_ia.data.database.runtime_bootstrap"] = runtime_bootstrap

    session_checkpointer = types.ModuleType("sei_ia.services.session_fs.checkpointer")
    dummy_checkpointer = object()

    async def get_session_checkpointer() -> object:
        return dummy_checkpointer

    async def close_session_checkpointer() -> None:
        return None

    session_checkpointer.get_session_checkpointer = get_session_checkpointer
    session_checkpointer.close_session_checkpointer = close_session_checkpointer
    sys.modules["sei_ia.services.session_fs.checkpointer"] = session_checkpointer

    session_runtime = types.ModuleType("sei_ia.services.session_fs.runtime")

    async def get_session_manager() -> object:
        return object()

    async def run_sweeper() -> None:
        await asyncio.Event().wait()

    session_runtime.get_session_manager = get_session_manager
    session_runtime.run_sweeper = run_sweeper
    sys.modules["sei_ia.services.session_fs.runtime"] = session_runtime

    cache_cleanup = types.ModuleType("sei_ia.services.cache.cache_cleanup_service")

    async def cleanup_non_cacheable_documents(
        *_args: Any, **_kwargs: Any
    ) -> dict[str, list[Any]]:
        return {"deleted_from_redis": [], "deleted_from_postgres": []}

    cache_cleanup.cleanup_non_cacheable_documents = cleanup_non_cacheable_documents
    sys.modules["sei_ia.services.cache.cache_cleanup_service"] = cache_cleanup


def install_upload_smoke_stubs(args: argparse.Namespace) -> dict[str, Any]:
    """Instala mocks locais para simular upload avulso via fluxo real do router."""
    global _LAST_FAKE_CACHE  # noqa: PLW0603

    upload_path = prepare_local_upload_file(args)
    fake_cache = FakeRedisJsonCache()
    _LAST_FAKE_CACHE = fake_cache

    from sei_ia.data.database.sei_client import sei_client
    from sei_ia.services import cache as cache_module
    from sei_ia.services.cache import topic_attachments

    def fake_download_arquivo_avulso(id_arquivo_avulso: int, doc_extension: str) -> str:
        print(
            "upload_download_stub: "
            + json.dumps(
                {
                    "id_upload": id_arquivo_avulso,
                    "extensao": doc_extension,
                    "path": str(upload_path),
                },
                ensure_ascii=False,
            )
        )
        return str(upload_path)

    def fake_remove_arquivos_avulsos(id_arquivos_avulsos: list[int] | set[int]) -> dict:
        print(
            "upload_remove_stub: "
            + json.dumps(
                {"ids": sorted({int(id_) for id_ in id_arquivos_avulsos})},
                ensure_ascii=False,
            )
        )
        return {"status": "success", "data": []}

    sei_client.md_ia_download_arquivo_avulso = fake_download_arquivo_avulso
    sei_client.md_ia_remove_arquivos_avulsos = fake_remove_arquivos_avulsos
    cache_module.get_cache = lambda: fake_cache
    topic_attachments.get_cache = lambda: fake_cache

    return {
        "upload_path": str(upload_path),
        "upload_exists_before_request": upload_path.exists(),
        "cache_backend": "FakeRedisJsonCache",
    }


def install_mock_llm(args: argparse.Namespace) -> None:  # noqa: C901
    """Mocka o LLM mantendo create_react_agent/tool-calling real.

    Em vez de emular o endpoint inteiro, substitui apenas `get_llm_model` por um
    BaseChatModel que passa pelo LangGraph agent, usa bind_tools, emite reasoning
    no formato Responses API quando `use_thinking=True`, chama a tool de anexos
    e depois responde com base no ToolMessage.
    """
    from collections.abc import AsyncIterator, Iterator

    from langchain_core.callbacks import (
        AsyncCallbackManagerForLLMRun,
        CallbackManagerForLLMRun,
    )
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import (
        AIMessage,
        AIMessageChunk,
        BaseMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )
    from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
    from langchain_core.tools import BaseTool
    from pydantic import Field

    from sei_ia.agents import chat_completion_graph
    from sei_ia.agents.disclaimer import disclaimer_classifier
    from sei_ia.services.llm_models import chat_workflow, get_model as get_model_module

    async def fake_classify_disclaimer_need(state: dict[str, Any]) -> dict[str, str]:
        _ = state
        return {"disclaimer_case": "outro"}

    class LocalUploadSmokeChatModel(BaseChatModel):
        model_name: str = "local-upload-smoke-model"
        bound_tools: list[BaseTool] = Field(default_factory=list)
        use_responses_api: bool = False
        reasoning: dict[str, Any] | None = None

        @property
        def _llm_type(self) -> str:
            return "local-upload-smoke-chat-model"

        def bind_tools(self, tools: list[BaseTool], **kwargs: Any):  # noqa: ANN201, ARG002
            return self.model_copy(update={"bound_tools": list(tools)})

        def _find_tool(self) -> BaseTool | None:
            for tool in self.bound_tools:
                if tool.name == "consultar_anexos_do_topico":
                    return tool
            return None

        def _needs_tool_call(self, messages: list[BaseMessage]) -> bool:
            has_tool_result = any(isinstance(msg, ToolMessage) for msg in messages)
            if has_tool_result:
                return False
            last = messages[-1] if messages else None
            if not isinstance(last, HumanMessage):
                return False
            return self._find_tool() is not None

        def _tool_call_message(self) -> AIMessage:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "consultar_anexos_do_topico",
                        "args": {"nome_arquivo": args.upload_name},
                        "id": "call_local_upload_smoke",
                    }
                ],
            )

        @staticmethod
        def _stringify_content(content: Any) -> str:
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return json.dumps(content, ensure_ascii=False)
            return str(content)

        def _build_answer(self, messages: list[BaseMessage]) -> str:
            system_prompt = "\n".join(
                self._stringify_content(msg.content)
                for msg in messages
                if isinstance(msg, SystemMessage)
            )
            human_prompt = "\n".join(
                self._stringify_content(msg.content)
                for msg in messages
                if isinstance(msg, HumanMessage)
            )
            tool_payloads = [
                self._stringify_content(msg.content)
                for msg in messages
                if isinstance(msg, ToolMessage)
            ]
            tool_text = "\n".join(tool_payloads)
            has_upload_context = "<arquivos_avulsos>" in human_prompt
            has_instruction = "anexos" in system_prompt.lower()
            has_identifier = "ARQUIVO-AVULSO-LOCAL-42" in tool_text or (
                "ARQUIVO-AVULSO-LOCAL-42" in human_prompt
            )
            return (
                "SMOKE_OK arquivos_avulsos="
                f"{has_upload_context} tool_instruction={has_instruction} "
                f"tool_payload_identifier={has_identifier} arquivo={args.upload_name}"
            )

        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: CallbackManagerForLLMRun | None = None,
            **kwargs: Any,
        ) -> ChatResult:
            _ = (stop, run_manager, kwargs)
            message = (
                self._tool_call_message()
                if self._needs_tool_call(messages)
                else AIMessage(content=self._build_answer(messages))
            )
            return ChatResult(generations=[ChatGeneration(message=message)])

        async def _agenerate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: AsyncCallbackManagerForLLMRun | None = None,
            **kwargs: Any,
        ) -> ChatResult:
            _ = (stop, run_manager, kwargs)
            return self._generate(messages)

        def _stream(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: CallbackManagerForLLMRun | None = None,
            **kwargs: Any,
        ) -> Iterator[ChatGenerationChunk]:
            _ = (stop, run_manager, kwargs)
            if self._needs_tool_call(messages):
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        tool_call_chunks=[
                            {
                                "name": "consultar_anexos_do_topico",
                                "args": json.dumps(
                                    {"nome_arquivo": args.upload_name},
                                    ensure_ascii=False,
                                ),
                                "id": "call_local_upload_smoke",
                                "index": 0,
                            }
                        ],
                    )
                )
                return
            if self.use_responses_api:
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content=[
                            {
                                "type": "reasoning",
                                "summary": [
                                    {
                                        "type": "summary_text",
                                        "text": "reasoning-smoke: arquivo avulso persistido e consultado. ",
                                    }
                                ],
                            }
                        ]
                    )
                )
            answer = self._build_answer(messages)
            for idx in range(0, len(answer), 24):
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content=[
                            {"type": "output_text", "text": answer[idx : idx + 24]}
                        ]
                        if self.use_responses_api
                        else answer[idx : idx + 24]
                    )
                )

        async def _astream(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: AsyncCallbackManagerForLLMRun | None = None,
            **kwargs: Any,
        ) -> AsyncIterator[ChatGenerationChunk]:
            _ = (stop, run_manager, kwargs)
            for chunk in self._stream(messages):
                yield chunk
                await asyncio.sleep(0)

    def fake_get_llm_model(
        model_type: str,
        temperature: float,
        **kwargs: Any,
    ) -> LocalUploadSmokeChatModel:
        _ = (model_type, temperature)
        return LocalUploadSmokeChatModel(
            use_responses_api=bool(kwargs.get("use_responses_api")),
            reasoning=kwargs.get("reasoning"),
        )

    chat_workflow.get_llm_model = fake_get_llm_model
    get_model_module.get_llm_model = fake_get_llm_model
    disclaimer_classifier.get_llm_model = fake_get_llm_model
    disclaimer_classifier.classify_disclaimer_need = fake_classify_disclaimer_need
    chat_completion_graph.classify_disclaimer_need = fake_classify_disclaimer_need


def make_app(use_local_stubs: bool = True):
    """Import tardio para garantir env carregado antes de settings_config."""
    if use_local_stubs:
        install_local_smoke_stubs()

    from sei_ia import main as main_module

    main_module.embedding_generator.provider.test_connection = lambda: True

    # Desliga timeout middleware no smoke para simplificar diagnóstico local.
    # Mantém RequestMiddleware para preencher request.state.body/id/ip como no fluxo real.
    return main_module.get_app(
        enable_timeout_middleware=False,
        enable_request_middleware=True,
    )


def inspect_fake_cache(id_topico: int | None, id_upload: int) -> dict[str, Any]:
    """Retorna resumo seguro do cache fake após a requisição."""
    if _LAST_FAKE_CACHE is None or id_topico is None:
        return {"enabled": False}

    snapshot = _LAST_FAKE_CACHE.snapshot()
    attachment_payloads = [
        value
        for key, value in snapshot["values"].items()
        if key.endswith(f":attachment:{id_upload}") and isinstance(value, dict)
    ]
    index_payloads = [
        value
        for key, value in snapshot["values"].items()
        if key.endswith(":index") and isinstance(value, dict)
    ]
    content_joined = "\n".join(
        str(p.get("conteudo") or "") for p in attachment_payloads
    )
    return {
        "enabled": True,
        "key_count": len(snapshot["keys"]),
        "keys": snapshot["keys"],
        "has_topic_index": bool(index_payloads),
        "has_attachment_payload": bool(attachment_payloads),
        "attachment_names": [p.get("nome_arquivo") for p in attachment_payloads],
        "attachment_content_chars": [
            p.get("content_chars") for p in attachment_payloads
        ],
        "contains_identifier": "ARQUIVO-AVULSO-LOCAL-42" in content_joined,
    }


def run(args: argparse.Namespace) -> int:
    app_dir = Path(__file__).resolve().parent
    os.chdir(app_dir)
    loaded_envs = load_worktree_envs(app_dir)

    print("== Assistente TestClient smoke ==")
    print(f"app_dir: {app_dir}")
    print(f"repo_root: {find_repo_root(app_dir)}")
    print(f"endpoint: {ENDPOINT}")
    print(f"env_files_loaded: {[redact_path(p) for p in loaded_envs]}")
    print(
        "env_presence: "
        + json.dumps(
            {
                "LITELLM_PROXY_URL": bool(os.getenv("LITELLM_PROXY_URL")),
                "LITELLM_PROXY_API_KEY": bool(os.getenv("LITELLM_PROXY_API_KEY")),
                "LANGFUSE_PUBLIC_KEY": bool(os.getenv("LANGFUSE_PUBLIC_KEY")),
                "LANGFUSE_SECRET_KEY": bool(os.getenv("LANGFUSE_SECRET_KEY")),
            },
            ensure_ascii=False,
        )
    )
    payload = build_payload(args)
    safe_payload = {**payload, "system_prompt": "[present]", "text": payload["text"]}
    print("payload: " + json.dumps(safe_payload, ensure_ascii=False, indent=2))

    started = time.monotonic()
    upload_context: dict[str, Any] = {}
    try:
        app = make_app()
        if args.local_upload_smoke:
            upload_context = install_upload_smoke_stubs(args)
        if args.mock_llm:
            install_mock_llm(args)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(ENDPOINT, json=payload, timeout=args.timeout)
    except Exception as exc:  # noqa: BLE001 - smoke script precisa reportar qualquer falha
        elapsed = time.monotonic() - started
        print(
            json.dumps(
                {
                    "ok": False,
                    "phase": "client_request_exception",
                    "elapsed_seconds": round(elapsed, 3),
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    elapsed = time.monotonic() - started
    raw_text, events = consume_stream_response(response)
    summary = summarize_events(events, max_chars=args.preview_chars)
    cache_summary = inspect_fake_cache(payload.get("id_topico"), args.upload_id)
    ok = (
        response.status_code == 200
        and not summary["errors"]
        and summary["content_chars"] > 0
        and summary["has_end_event"]
    )
    if args.local_upload_smoke:
        ok = (
            ok
            and cache_summary.get("has_topic_index")
            and cache_summary.get("has_attachment_payload")
            and cache_summary.get("contains_identifier")
            and (
                "SMOKE_OK" in summary["content_preview"]
                or "ARQUIVO-AVULSO-LOCAL-42" in summary["content_preview"]
            )
        )
        if args.thinking:
            ok = ok and summary["reasoning_chars"] > 0

    result = {
        "ok": ok,
        "status_code": response.status_code,
        "elapsed_seconds": round(elapsed, 3),
        "raw_sse_chars": len(raw_text),
        "local_upload_context": upload_context,
        "topic_attachment_cache": cache_summary,
        **summary,
    }
    if summary["errors"]:
        detail = json.dumps(summary["errors"], ensure_ascii=False)
        if "No api key passed in" in detail or "Tried to access" in detail:
            result["diagnostic_hint"] = (
                "A aplicação envia os aliases públicos 'standard'/'mini'/'nano'. "
                "O litellm_config.yaml deve publicá-los com os modelos físicos "
                "configurados em LITELLM_STANDARD_MODEL/LITELLM_MINI_MODEL/"
                "LITELLM_NANO_MODEL como model/base_model. Se este smoke estiver "
                "apontando para um proxy central, valide a combinação "
                "LITELLM_PROXY_URL + aliases publicados antes de concluir bug no app."
            )
    print("result: " + json.dumps(result, ensure_ascii=False, indent=2, default=str))

    if args.dump_raw:
        print("raw_sse:")
        print(raw_text[:10000])

    return 0 if ok else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default=None)
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT)
    parser.add_argument("--id-usuario", type=int, default=999999)
    parser.add_argument("--id-topico", type=int, default=None)
    parser.add_argument("--id-request", type=int, default=999999001)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--preview-chars", type=int, default=1200)
    parser.add_argument("--dump-raw", action="store_true")
    parser.add_argument(
        "--local-upload-smoke",
        action="store_true",
        help="Simula interação local com arquivos avulsos + cache/tool de tópico.",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Mocka somente o LLM; mantém router, extração, cache e agente/tool reais.",
    )
    parser.add_argument("--upload-id", type=int, default=42001)
    parser.add_argument("--upload-name", default=DEFAULT_UPLOAD_FILENAME)
    parser.add_argument("--upload-ext", default="txt")
    parser.add_argument("--upload-file", default=None)
    parser.add_argument("--upload-content", default=DEFAULT_UPLOAD_CONTENT)
    thinking = parser.add_mutually_exclusive_group()
    thinking.add_argument(
        "--thinking", dest="thinking", action="store_true", default=True
    )
    thinking.add_argument("--no-thinking", dest="thinking", action="store_false")

    websearch = parser.add_mutually_exclusive_group()
    websearch.add_argument(
        "--websearch", dest="websearch", action="store_true", default=False
    )
    websearch.add_argument("--no-websearch", dest="websearch", action="store_false")
    args = parser.parse_args(argv)
    if args.text is None:
        args.text = DEFAULT_UPLOAD_TEXT if args.local_upload_smoke else DEFAULT_TEXT
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))

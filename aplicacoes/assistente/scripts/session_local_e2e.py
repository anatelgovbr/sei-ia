#!/usr/bin/env python3
"""E2E local do ``/llm_lang/session_stream`` com duas iterações.

O teste sobe a aplicação FastAPI em memória, usa o LLM/Langfuse configurados no
ambiente e substitui somente a consulta de conteúdo ao SEI por um fixture local.
Assim ele valida o fluxo de sessão, SSE, materialização e observabilidade sem
depender de o SEISU/SEI conseguir alcançar esta máquina.

Executar a partir de ``aplicacoes/assistente``::

    uv run python scripts/session_local_e2e.py

O primeiro payload contém ``LOCAL-DOC-001``. O segundo usa o mesmo usuário/tópico
e acrescenta ``LOCAL-DOC-002``. Por padrão o modelo é um fake determinístico para
que o teste funcione mesmo sem rota para o proxy; ``--real-llm`` usa a base e a
chave externas ``LITELLM_STANDARD_API_BASE``/``LITELLM_STANDARD_API_KEY`` e
converte os modelos reais do ambiente para os aliases aceitos pelo proxy. O
resultado não imprime credenciais nem o corpo integral dos documentos; mostra
apenas chamadas, manifesto, frames e previews.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from scripts.smoke_endpoint_host import (  # noqa: E402
    install_local_smoke_stubs,
    load_worktree_envs,
    make_app,
)

DOC_CONTENT = {
    "LOCAL-DOC-001": (
        "Documento local 001. Identificador: LOCAL-FIXTURE-001. "
        "Conteúdo usado apenas para validar a primeira iteração da sessão."
    ),
    "LOCAL-DOC-002": (
        "Documento local 002. Identificador: LOCAL-FIXTURE-002. "
        "Este arquivo foi acrescentado ao segundo payload da mesma sessão."
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id-usuario", type=int, default=990001)
    parser.add_argument("--id-topico", type=int, default=990002)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument(
        "--real-llm",
        action="store_true",
        help="Usa o LiteLLM configurado; por padrão usa um modelo local determinístico.",
    )
    return parser.parse_args()


def configure_real_llm_environment() -> dict[str, Any]:
    """Adapta as variáveis do proxy publicado no host às settings da app.

    O container recebe ``ASSISTENTE_LITELLM_PROXY_URL=http://infra-litellm:4000``
    porque esse nome só existe na rede Docker. O runner deste script fica fora
    dela e deve usar a base publicada no mesmo host, junto da chave da virtual
    key. A aplicação envia ao proxy os aliases públicos fixos ``standard``,
    ``mini`` e ``nano``. As variáveis ``LITELLM_*_MODEL`` continuam necessárias
    para registrar os ``model``/``base_model`` físicos na configuração do proxy.
    """
    proxy_sources = (
        (
            "ASSISTENTE_LITELLM_PROXY_URL",
            "ASSISTENTE_LITELLM_PROXY_API_KEY",
        ),
        ("LITELLM_PROXY_URL", "LITELLM_PROXY_API_KEY"),
    )
    proxy_source = ""
    proxy_url = ""
    api_key = ""
    for url_variable, key_variable in proxy_sources:
        candidate_url = os.getenv(url_variable, "").strip()
        candidate_key = os.getenv(key_variable, "").strip()
        if candidate_url and candidate_key:
            proxy_source = url_variable
            proxy_url = candidate_url
            api_key = candidate_key
            break

    if not proxy_url:
        raise RuntimeError(
            "Proxy LiteLLM ausente: defina um par correspondente de "
            "ASSISTENTE_LITELLM_PROXY_URL/ASSISTENTE_LITELLM_PROXY_API_KEY ou "
            "LITELLM_PROXY_URL/LITELLM_PROXY_API_KEY."
        )

    parsed = urlparse(proxy_url)
    if not parsed.scheme or not parsed.hostname:
        raise RuntimeError(
            "URL do proxy LiteLLM inválida: use "
            "ASSISTENTE_LITELLM_PROXY_URL ou LITELLM_PROXY_URL."
        )

    # LITELLM_{STANDARD,MINI,NANO}_MODEL continuam sendo a configuração física
    # do proxy. A app envia os aliases públicos estáveis; aqui só conferimos a
    # presença dos valores físicos para reportar erro cedo, sem reescrever o
    # ambiente.
    model_sources = (
        "LITELLM_STANDARD_MODEL",
        "LITELLM_MINI_MODEL",
        "LITELLM_NANO_MODEL",
    )
    model_aliases: dict[str, str] = {}
    missing_models: list[str] = []
    for model_source in model_sources:
        model = os.getenv(model_source, "").strip()
        if not model:
            missing_models.append(model_source)
            continue
        model_aliases[model_source.removeprefix("LITELLM_")] = model
    if missing_models:
        raise RuntimeError(
            "Modelos físicos do proxy ausentes: " + ", ".join(missing_models)
        )

    os.environ["ASSISTENTE_LITELLM_PROXY_URL"] = proxy_url.rstrip("/")
    os.environ["ASSISTENTE_LITELLM_PROXY_API_KEY"] = api_key

    health_url = f"{proxy_url.rstrip('/')}/health/readiness"
    try:
        health_response = httpx.get(
            health_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        health_response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Readiness autenticada do proxy LiteLLM falhou "
            f"({type(exc).__name__}: {str(exc).splitlines()[0][:160]})"
        ) from exc

    return {
        "source": proxy_source,
        "host": parsed.hostname,
        "port": parsed.port,
        "api_key_present": True,
        "model_aliases": model_aliases,
    }


class LocalSessionChatModel(BaseChatModel):
    """Modelo local mínimo que passa pelo grafo/callbacks do session agent."""

    model_name: str = "local-session-e2e-model"

    @property
    def _llm_type(self) -> str:
        return "local-session-e2e"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ARG002
        return self

    @staticmethod
    def _text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                str(item.get("text", "")) for item in content if isinstance(item, dict)
            )
        return str(content)

    def _answer(self, messages: list[BaseMessage]) -> str:
        system = "\n".join(
            self._text(message.content)
            for message in messages
            if getattr(message, "type", "") == "system"
        )
        found = [doc_id for doc_id in DOC_CONTENT if doc_id in system]
        identifiers = [f"LOCAL-FIXTURE-{doc_id.rsplit('-', 1)[-1]}" for doc_id in found]
        return (
            "LOCAL_E2E_OK documentos="
            + ",".join(found)
            + " identificadores="
            + ",".join(identifiers)
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,  # noqa: ANN001, ARG002
        **kwargs,
    ) -> ChatResult:
        _ = (stop, run_manager, kwargs)
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content=self._answer(messages)))
            ]
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,  # noqa: ANN001, ARG002
        **kwargs,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,  # noqa: ANN001, ARG002
        **kwargs,
    ):
        _ = (stop, run_manager, kwargs)
        answer = self._answer(messages)
        for index in range(0, len(answer), 24):
            yield ChatGenerationChunk(
                message=AIMessageChunk(content=answer[index : index + 24])
            )

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,  # noqa: ANN001, ARG002
        **kwargs,
    ):
        for chunk in self._stream(
            messages, stop=stop, run_manager=run_manager, **kwargs
        ):
            yield chunk
            await asyncio.sleep(0)


def payload(
    *,
    id_usuario: int,
    id_topico: int,
    id_request: int,
    document_ids: list[str],
    text: str,
    no_cache: bool,
) -> dict[str, Any]:
    return {
        "id_usuario": id_usuario,
        "id_topico": id_topico,
        "id_request": id_request,
        "ip": "127.0.0.1",
        "text": text,
        "system_prompt": (
            "Responda brevemente usando somente os documentos locais da sessão. "
            "Cite os identificadores encontrados."
        ),
        "use_thinking": False,
        "use_websearch": False,
        "summarize_history": False,
        "skip_memory": False,
        "no_cache": no_cache,
        "trace": True,
        "id_procedimentos": [
            {
                "id_procedimento": "LOCAL-PROC-001",
                "metadata": {
                    "id_protocolo_formatado": "LOCAL-PROC-FORMATTED-001",
                    "source": "local-session-e2e",
                },
                "id_documentos": [
                    {"id_documento": doc_id, "download_ext": False}
                    for doc_id in document_ids
                ],
            }
        ],
        "arquivos_avulsos": None,
    }


def parse_sse(response) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in response.iter_lines():
        if not line or not line.startswith("data:"):
            continue
        raw = line.split(":", 1)[1].strip()
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def safe_manifest(meta_file: Path) -> dict[str, Any]:
    data = json.loads(meta_file.read_text(encoding="utf-8"))
    processes = data.get("processos")
    if not isinstance(processes, list):
        raise ValueError(  # noqa: TRY004
            "E2E exige manifesto de sessão v1 com processos em lista"
        )

    process_ids: list[str] = []
    document_ids: list[str] = []
    files: list[str] = []
    for process in processes:
        if not isinstance(process, dict):
            raise ValueError(  # noqa: TRY004
                "E2E encontrou processo inválido no manifesto v1"
            )
        process_ids.append(str(process.get("id_procedimento", "")))
        documents = process.get("documentos")
        if not isinstance(documents, list):
            raise ValueError(  # noqa: TRY004
                "E2E exige documentos aninhados em cada processo do manifesto v1"
            )
        for document in documents:
            if not isinstance(document, dict):
                raise ValueError(  # noqa: TRY004
                    "E2E encontrou documento inválido no manifesto v1"
                )
            document_ids.append(str(document.get("id_documento", "")))
            if document.get("arquivo"):
                files.append(str(document["arquivo"]))

    return {
        "schema_version": data.get("schema_version"),
        "doc_ids": data.get("doc_ids", []),
        "processes": process_ids,
        "document_entries": document_ids,
        "files": files,
    }


def summarize_turn(
    *,
    turn: int,
    trace_id: str,
    response,
    events: list[dict[str, Any]],
    fetch_calls: list[dict[str, Any]],
    fetch_start: int,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    content = "".join(
        str(event.get("data", "")) for event in events if event.get("type") == "content"
    )
    errors = [
        {
            "status_code": event.get("status_code"),
            "detail": str(event.get("detail", ""))[:500],
        }
        for event in events
        if event.get("type") == "error"
    ]
    metadata = next(
        (event.get("data") for event in events if event.get("type") == "metadata"),
        {},
    )
    return {
        "turn": turn,
        "trace_id": trace_id,
        "http_status": response.status_code,
        "event_counts": dict(Counter(event.get("type", "unknown") for event in events)),
        "content_chars": len(content),
        "content_preview": content[:1200],
        "errors": errors,
        "metadata": {
            "session_key": metadata.get("session_key"),
            "documents": metadata.get("documentos"),
            "unavailable_documents": metadata.get("documentos_indisponiveis"),
        },
        "fetch_calls_this_turn": fetch_calls[fetch_start:],
        "manifest": manifest,
    }


def validate_results(
    results: list[dict[str, Any]], *, id_usuario: int, id_topico: int
) -> list[dict[str, str]]:
    """Valida SSE, continuidade da sessão e materialização esperada."""
    failed = [
        {"reason": "turn_response_invalid"}
        for result in results
        if result["http_status"] != 200
        or result["errors"]
        or result["content_chars"] == 0
        or result["metadata"]["session_key"] != f"{id_usuario}_{id_topico}"
    ]
    expected_processes = ["LOCAL-PROC-001"]
    expected_first = ["LOCAL-DOC-001"]
    expected_second = ["LOCAL-DOC-001", "LOCAL-DOC-002"]
    if len(results) != 2:
        failed.append({"reason": "expected_two_turns"})
    elif results[0]["manifest"]["processes"] != expected_processes:
        failed.append({"reason": "first_process_order_mismatch"})
    elif results[1]["manifest"]["processes"] != expected_processes:
        failed.append({"reason": "second_process_order_mismatch"})
    elif results[0]["manifest"]["document_entries"] != expected_first:
        failed.append({"reason": "first_manifest_mismatch"})
    elif results[1]["manifest"]["document_entries"] != expected_second:
        failed.append({"reason": "second_manifest_mismatch"})
    elif results[0]["manifest"]["doc_ids"] != expected_first:
        failed.append({"reason": "first_materialized_documents_mismatch"})
    elif results[1]["manifest"]["doc_ids"] != expected_second:
        failed.append({"reason": "second_materialized_documents_mismatch"})
    elif results[0]["metadata"]["documents"] != 1:
        failed.append({"reason": "first_metadata_documents_mismatch"})
    elif results[1]["metadata"]["documents"] != 2:
        failed.append({"reason": "second_metadata_documents_mismatch"})
    elif any(result["metadata"]["unavailable_documents"] for result in results):
        failed.append({"reason": "unexpected_unavailable_documents"})
    elif [call["document_id"] for call in results[0]["fetch_calls_this_turn"]] != [
        "LOCAL-DOC-001"
    ]:
        failed.append({"reason": "first_materialization_mismatch"})
    elif [call["document_id"] for call in results[1]["fetch_calls_this_turn"]] != [
        "LOCAL-DOC-002"
    ]:
        failed.append({"reason": "second_materialization_mismatch"})
    return failed


def run(args: argparse.Namespace) -> int:
    os.chdir(APP_DIR)
    loaded = load_worktree_envs(APP_DIR)
    llm_config: dict[str, Any] = {}
    if args.real_llm:
        llm_config = configure_real_llm_environment()

    # O histórico real do tópico consultaria o SEI. Para este teste a continuidade
    # é a mesma thread/checkpointer + o mesmo filesystem; nenhum fetch de histórico
    # externo é necessário.
    os.environ["ASSISTENTE_SESSION_SEED_HISTORY"] = "false"

    print(
        json.dumps(
            {
                "mode": "local_session_e2e",
                "env_files_loaded": [str(path.name) for path in loaded],
                "langfuse_enabled": os.getenv("ASSISTENTE_USE_LANGFUSE", "").lower()
                == "true",
                "llm_mode": "real" if args.real_llm else "local_fake",
                "langfuse_host": urlparse(os.getenv("LANGFUSE_URL", "")).hostname,
                "llm_proxy_host": llm_config.get(
                    "host",
                    urlparse(os.getenv("ASSISTENTE_LITELLM_PROXY_URL", "")).hostname,
                ),
                "llm_proxy_port": llm_config.get(
                    "port", urlparse(os.getenv("ASSISTENTE_LITELLM_PROXY_URL", "")).port
                ),
                "llm_api_key_present": llm_config.get("api_key_present", False),
                "llm_model_aliases": llm_config.get("model_aliases", {}),
                "sei_fetch": "local_fixture (nenhuma chamada ao SEI)",
            },
            ensure_ascii=False,
        )
    )

    # Reutiliza os stubs locais existentes para Postgres/Redis/lifespan. O
    # checkpointer e o SessionManager abaixo são reais, apenas em memória/temporários.
    install_local_smoke_stubs()

    with tempfile.TemporaryDirectory(prefix="assistente-session-e2e-") as tmp:
        from sei_ia.agents.session_agent import agent as agent_module
        from sei_ia.configs.settings_config import settings
        from sei_ia.data.content_status import ContentStatus
        from sei_ia.routers.session import stream as stream_module
        from sei_ia.services.session_fs.manager import (
            SessionDocumentOutcome,
            SessionManager,
        )

        # A primeira importação da app configura o singleton Langfuse antes do
        # CallbackHandler do session agent ser criado.
        app = make_app(use_local_stubs=True)

        checkpointer = InMemorySaver()
        manager = SessionManager(
            sessions_root=tmp,
            ttl_seconds=3600,
            checkpointer=checkpointer,
            max_fetch_concurrency=4,
            preview_chars=800,
        )

        async def get_manager():
            return manager

        async def get_checkpointer():
            return checkpointer

        stream_module.get_session_manager = get_manager
        stream_module.get_session_checkpointer = get_checkpointer
        stream_module.settings.SESSION_SEED_HISTORY = False
        settings.SESSION_SEED_HISTORY = False

        if not args.real_llm:
            # O modo injected não cria o subagente explorador; basta trocar o
            # construtor do modelo principal no módulo de sessão. O CallbackHandler
            # continua real e registra a execução do grafo no Langfuse.
            agent_module.get_model = lambda *_args, **_kwargs: LocalSessionChatModel()

        fetch_calls: list[dict[str, Any]] = []

        async def fake_fetch(
            document_id: str, download_ext: bool | None, no_cache: bool
        ) -> SessionDocumentOutcome:
            if document_id not in DOC_CONTENT:
                raise RuntimeError(f"fixture ausente para {document_id}")
            fetch_calls.append(
                {
                    "document_id": document_id,
                    "download_ext": download_ext,
                    "no_cache": no_cache,
                    "source": "local_fixture",
                }
            )
            return SessionDocumentOutcome(
                content=DOC_CONTENT[document_id],
                formatted_document_number=f"{document_id}-formatted",
                formatted_process_number=None,
                status=ContentStatus.available(),
                source="unknown",
                provenance={"source": "local_fixture", "fixture_version": 1},
            )

        stream_module._fetch_document = fake_fetch

        # O agent_module usa o mesmo get_model real configurado no ambiente. A
        # atribuição só torna explícito que não há mock de LLM neste caminho.
        _ = agent_module
        turns = [
            payload(
                id_usuario=args.id_usuario,
                id_topico=args.id_topico,
                id_request=1,
                document_ids=["LOCAL-DOC-001"],
                text="Leia o primeiro documento e informe o identificador local.",
                no_cache=True,
            ),
            payload(
                id_usuario=args.id_usuario,
                id_topico=args.id_topico,
                id_request=2,
                document_ids=["LOCAL-DOC-001", "LOCAL-DOC-002"],
                text="Continue a análise e considere também o novo documento acrescentado agora.",
                no_cache=False,
            ),
        ]
        results: list[dict[str, Any]] = []
        with TestClient(app, raise_server_exceptions=False) as client:
            for turn_number, request_payload in enumerate(turns, start=1):
                trace_id = uuid.uuid4().hex
                fetch_start = len(fetch_calls)
                started = time.monotonic()
                response = client.post(
                    "/llm_lang/session_stream",
                    json=request_payload,
                    headers={"X-Langfuse-Trace-Id": trace_id},
                    timeout=args.timeout,
                )
                events = parse_sse(response)
                session_key = f"{args.id_usuario}_{args.id_topico}"
                manifest = safe_manifest(
                    manager._paths(session_key).meta_file  # noqa: SLF001
                )
                result = summarize_turn(
                    turn=turn_number,
                    trace_id=trace_id,
                    response=response,
                    events=events,
                    fetch_calls=fetch_calls,
                    fetch_start=fetch_start,
                    manifest=manifest,
                )
                result["elapsed_seconds"] = round(time.monotonic() - started, 3)
                results.append(result)

        # A rota faz flush no finally; este flush adicional reduz a janela até a
        # consulta de confirmação no Langfuse.
        from sei_ia.routers.chat import _flush_langfuse

        _flush_langfuse()
        print(
            json.dumps(
                {"turns": results, "all_fetch_calls": fetch_calls},
                ensure_ascii=False,
                indent=2,
            )
        )

        failed = validate_results(
            results,
            id_usuario=args.id_usuario,
            id_topico=args.id_topico,
        )
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

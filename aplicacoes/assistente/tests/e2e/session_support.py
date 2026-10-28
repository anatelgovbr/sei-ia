"""Suporte hermético para E2E do endpoint de sessão."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from sei_ia.data.content_status import ContentStatus
from sei_ia.services.session_fs.manager import SessionDocumentOutcome, SessionManager

_CANARY_PATTERN = re.compile(r"CANARY_[A-Z0-9_]+")
_ENDPOINT = "/llm_lang/session_stream"


@dataclass(frozen=True)
class DocumentFixture:
    """Documento devolvido pelo extrator local do E2E."""

    content: str
    formatted_document_number: str
    formatted_process_number: str | None = None
    metadata: Mapping[str, object] | None = None


@dataclass(frozen=True)
class FetchCall:
    """Consulta documental observada na borda isolada do endpoint."""

    document_id: str
    download_ext: bool | None
    no_cache: bool


@dataclass(frozen=True)
class StreamResult:
    """Resposta HTTP e eventos SSE decodificados."""

    status_code: int
    content_type: str
    events: tuple[dict[str, Any], ...]

    @property
    def event_types(self) -> list[str]:
        return [str(event.get("type", "")) for event in self.events]

    @property
    def content(self) -> str:
        return "".join(
            str(event.get("data", ""))
            for event in self.events
            if event.get("type") == "content"
        )

    @property
    def errors(self) -> list[dict[str, Any]]:
        return [event for event in self.events if event.get("type") == "error"]

    @property
    def metadata(self) -> dict[str, Any]:
        metadata_events = [
            event for event in self.events if event.get("type") == "metadata"
        ]
        if len(metadata_events) != 1:
            raise AssertionError(
                f"esperado um evento metadata, encontrados {len(metadata_events)}"
            )
        data = metadata_events[0].get("data")
        assert isinstance(data, dict), "metadata SSE deve conter um objeto em data"
        return data

    def assert_completed(self) -> None:
        """Valida o contrato terminal comum a todos os cenários de sucesso."""
        assert self.status_code == 200
        assert self.content_type.startswith("text/event-stream")
        assert not self.errors
        assert self.content
        assert self.event_types.count("metadata") == 1
        assert self.event_types.count("end") == 1
        assert self.event_types[-2:] == ["metadata", "end"]


class DeterministicSessionModel(BaseChatModel):
    """Modelo local que informa os canários visíveis em sua janela."""

    model_name: str = "deterministic-session-e2e"

    @property
    def _llm_type(self) -> str:
        return "deterministic-session-e2e"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ARG002
        return self

    @staticmethod
    def _message_text(message: BaseMessage) -> str:
        content = message.content
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False, default=str)

    def _answer(self, messages: list[BaseMessage]) -> str:
        visible = {
            canary
            for message in messages
            for canary in _CANARY_PATTERN.findall(self._message_text(message))
        }
        return "VISIBLE_CANARIES=" + ",".join(sorted(visible))

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


def process_spec(
    process_id: str,
    document_ids: Sequence[str],
    *,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Monta um processo no formato público aceito pelo endpoint."""
    return {
        "id_procedimento": process_id,
        "metadata": dict(metadata or {}),
        "id_documentos": [
            {
                "id_documento": document_id,
                "download_ext": False,
                "sin_armazena_cache": "S",
            }
            for document_id in document_ids
        ],
    }


def parse_sse(response) -> tuple[dict[str, Any], ...]:  # noqa: ANN001
    """Decodifica todos os frames ``data:`` e falha diante de JSON inválido."""
    events: list[dict[str, Any]] = []
    for line in response.iter_lines():
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            raise AssertionError(f"linha SSE inesperada: {line!r}")
        event = json.loads(line.split(":", 1)[1].strip())
        assert isinstance(event, dict), "payload SSE deve ser um objeto JSON"
        events.append(event)
    return tuple(events)


class SessionStreamHarness:
    """Aplicação real de sessão com todas as bordas externas substituídas."""

    def __init__(
        self,
        monkeypatch,
        tmp_path: Path,
        *,
        documents: Mapping[str, DocumentFixture],
        history: Sequence[Mapping[str, object]] = (),
        model_factory: Callable[[], BaseChatModel] = DeterministicSessionModel,
        id_usuario: int = 91001,
        id_topico: int = 92001,
    ) -> None:
        from sei_ia.agents.session_agent import agent as agent_module
        from sei_ia.configs.settings_config import settings
        from sei_ia.data.database import sei_client as sei_client_module
        from sei_ia.main import get_app
        from sei_ia.routers.session import stream as stream_module

        self.id_usuario = id_usuario
        self.id_topico = id_topico
        self.documents = dict(documents)
        self.fetch_calls: list[FetchCall] = []
        self.history_fetch_calls = 0
        self.sessions_root = tmp_path / "sessions"
        self.checkpointer = InMemorySaver()
        self.manager = SessionManager(
            sessions_root=self.sessions_root,
            ttl_seconds=3600,
            checkpointer=self.checkpointer,
            max_fetch_concurrency=4,
            preview_chars=800,
        )

        async def get_manager() -> SessionManager:
            return self.manager

        async def get_checkpointer() -> InMemorySaver:
            return self.checkpointer

        async def fetch_document(
            document_id: str, download_ext: bool | None, no_cache: bool
        ) -> SessionDocumentOutcome:
            fixture = self.documents[document_id]
            self.fetch_calls.append(
                FetchCall(
                    document_id=document_id,
                    download_ext=download_ext,
                    no_cache=no_cache,
                )
            )
            return SessionDocumentOutcome(
                content=fixture.content,
                formatted_document_number=fixture.formatted_document_number,
                formatted_process_number=fixture.formatted_process_number,
                status=ContentStatus.available(),
                source="unknown",
                provenance={"source": "session_e2e_fixture"},
                metadata=fixture.metadata,
            )

        history_rows = [dict(row) for row in history]

        def fetch_history(_topic_id: str) -> pd.DataFrame:
            self.history_fetch_calls += 1
            return pd.DataFrame(history_rows)

        def model_config(
            agent_tag: str, model_override: str | None = None
        ) -> dict[str, Any]:
            _ = model_override
            return {
                "model": f"test/{agent_tag}",
                "model_name": f"test-{agent_tag}",
                "max_ctx_len": 100_000,
            }

        async def validate_model_override(_model: str) -> None:
            return None

        async def validate_reasoning_effort(
            _model: str, _reasoning_effort: str
        ) -> None:
            return None

        monkeypatch.setattr(stream_module, "get_session_manager", get_manager)
        monkeypatch.setattr(stream_module, "get_session_checkpointer", get_checkpointer)
        monkeypatch.setattr(stream_module, "_fetch_document", fetch_document)
        monkeypatch.setattr(stream_module, "get_model_config", model_config)
        monkeypatch.setattr(
            stream_module,
            "_langfuse_span",
            lambda *_args, **_kwargs: nullcontext(None),
        )
        monkeypatch.setattr(
            stream_module,
            "_update_langfuse_observation",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            stream_module, "_update_langfuse_trace", lambda *_args, **_kwargs: None
        )
        monkeypatch.setattr(
            stream_module, "validate_model_override", validate_model_override
        )
        monkeypatch.setattr(
            stream_module, "validate_reasoning_effort", validate_reasoning_effort
        )
        monkeypatch.setattr(stream_module, "_new_trace_id", lambda: None)
        monkeypatch.setattr(stream_module, "_flush_langfuse", lambda: None)
        monkeypatch.setattr(agent_module, "get_model_config", model_config)
        monkeypatch.setattr(
            agent_module,
            "get_model",
            lambda *_args, **_kwargs: model_factory(),
        )
        monkeypatch.setattr(
            sei_client_module, "consulta_historico_topico_com_tokens", fetch_history
        )
        monkeypatch.setattr(settings, "USE_LANGFUSE", False)
        monkeypatch.setattr(settings, "SESSION_TRACE", False)
        monkeypatch.setattr(settings, "SESSION_SEED_HISTORY", bool(history_rows))

        app = get_app(
            enable_timeout_middleware=False,
            enable_request_middleware=False,
        )
        self.client = TestClient(app, raise_server_exceptions=False)
        self._request_id = 0

    @property
    def session_root(self) -> Path:
        return self.sessions_root / f"{self.id_usuario}_{self.id_topico}"

    def manifest(self) -> dict[str, Any]:
        """Lê o manifesto produzido pelo ``SessionManager`` real."""
        return json.loads(
            (self.session_root / "session.json").read_text(encoding="utf-8")
        )

    def post(
        self,
        text: str,
        processes: Sequence[Mapping[str, Any]] = (),
        *,
        skip_memory: bool = False,
        no_cache: bool = False,
        mode: str = "injected",
        request_overrides: Mapping[str, Any] | None = None,
    ) -> StreamResult:
        """Envia um turno ao endpoint público e consome a resposta SSE."""
        self._request_id += 1
        payload = {
            "id_usuario": self.id_usuario,
            "id_topico": self.id_topico,
            "id_request": self._request_id,
            "ip": "127.0.0.1",
            "text": text,
            "use_thinking": False,
            "use_websearch": False,
            "summarize_history": False,
            "skip_memory": skip_memory,
            "no_cache": no_cache,
            "trace": False,
            "mode": mode,
            "id_procedimentos": list(processes),
            "arquivos_avulsos": None,
        }
        payload.update(request_overrides or {})
        response = self.client.post(_ENDPOINT, json=payload)
        return StreamResult(
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            events=parse_sse(response),
        )

    def close(self) -> None:
        self.client.close()


__all__ = [
    "DocumentFixture",
    "FetchCall",
    "SessionStreamHarness",
    "StreamResult",
    "parse_sse",
    "process_spec",
]

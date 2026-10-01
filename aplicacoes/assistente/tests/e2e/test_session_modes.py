"""E2E herméticos dos modos documental e explorador da sessão."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from sei_ia.agents.session_agent.trace import logger as session_trace_logger
from tests.e2e.session_support import (
    DocumentFixture,
    SessionStreamHarness,
    process_spec,
)

_CANARY_PATTERN = re.compile(r"CANARY_[A-Z0-9_]+")
_FILE_PATTERN = re.compile(r"/?proc_[^\s\"']+/[^\s\"']+\.txt")

_INJECTED = "injected"
_FILESYSTEM_DIRECT = "filesystem_direct"
_FILESYSTEM_DELEGATED = "filesystem_delegated"


class _ToolCallingSessionModel(BaseChatModel):
    """Modelo local que escolhe tools pela evidência presente nas mensagens."""

    scenario: str
    bound_tool_names: frozenset[str] = frozenset()
    model_name: str = "tool-calling-session-e2e"

    @property
    def _llm_type(self) -> str:
        return "tool-calling-session-e2e"

    @staticmethod
    def _text(message: BaseMessage) -> str:
        if isinstance(message.content, str):
            return message.content
        return json.dumps(message.content, ensure_ascii=False, default=str)

    @staticmethod
    def _tool_name(tool: Any) -> str:
        if isinstance(tool, dict):
            function = tool.get("function")
            if isinstance(function, dict):
                return str(function.get("name") or "")
            return str(tool.get("name") or "")
        return str(getattr(tool, "name", ""))

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):  # noqa: ARG002
        names = frozenset(filter(None, (self._tool_name(tool) for tool in tools)))
        return self.model_copy(update={"bound_tool_names": names})

    @staticmethod
    def _tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[
                {"name": name, "args": args, "id": call_id, "type": "tool_call"}
            ],
        )

    @classmethod
    def _canaries(cls, messages: Sequence[BaseMessage]) -> list[str]:
        return sorted(
            {
                canary
                for message in messages
                for canary in _CANARY_PATTERN.findall(cls._text(message))
            }
        )

    @classmethod
    def _tool_messages(cls, messages: Sequence[BaseMessage]) -> list[ToolMessage]:
        return [message for message in messages if isinstance(message, ToolMessage)]

    @classmethod
    def _used_tools(cls, messages: Sequence[BaseMessage]) -> set[str]:
        names = {
            str(message.name)
            for message in messages
            if isinstance(message, ToolMessage) and message.name
        }
        names.update(
            str(tool_call.get("name"))
            for message in messages
            if isinstance(message, AIMessage)
            for tool_call in message.tool_calls
            if tool_call.get("name")
        )
        return names

    @classmethod
    def _path_from_messages(cls, messages: Sequence[BaseMessage]) -> str | None:
        for message in reversed(messages):
            match = _FILE_PATTERN.search(cls._text(message))
            if match:
                return "/" + match.group(0).lstrip("/")
        return None

    def _next_message(self, messages: list[BaseMessage]) -> AIMessage:
        if self.scenario == _INJECTED:
            visible = self._canaries(messages)
            return AIMessage(content="EVIDENCIA=" + ",".join(visible))

        tool_messages = self._tool_messages(messages)
        tool_canaries = self._canaries(tool_messages)
        if tool_canaries:
            return AIMessage(content="EVIDENCIA=" + ",".join(tool_canaries))

        used_tools = self._used_tools(messages)
        if "read_session" in self.bound_tool_names and "read_session" not in used_tools:
            return self._tool_call("read_session", {}, "call-read-session")

        path = self._path_from_messages(tool_messages or messages)
        if path is not None:
            is_main_agent = "task" in self.bound_tool_names
            if (
                self.scenario == _FILESYSTEM_DELEGATED
                and is_main_agent
                and "task" not in used_tools
            ):
                return self._tool_call(
                    "task",
                    {
                        "subagent_type": "explorador",
                        "description": (
                            f"Leia somente {path}. Localize a evidência pedida pelo "
                            "usuário e devolva seu texto literal. Eixo obrigatório: "
                            "valor da evidência documental."
                        ),
                    },
                    "call-delegate-document",
                )

            explorer_or_direct = (
                self.scenario == _FILESYSTEM_DIRECT or not is_main_agent
            )
            if explorer_or_direct and "read_file" not in used_tools:
                return self._tool_call(
                    "read_file",
                    {"file_path": path},
                    "call-read-document",
                )

        return AIMessage(content="EVIDENCIA_NAO_ENCONTRADA")

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,  # noqa: ANN001, ARG002
        **kwargs: Any,
    ) -> ChatResult:
        _ = (stop, run_manager, kwargs)
        return ChatResult(
            generations=[ChatGeneration(message=self._next_message(messages))]
        )


class _TraceCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def trace_messages():
    handler = _TraceCapture()
    session_trace_logger.addHandler(handler)
    yield handler.messages
    session_trace_logger.removeHandler(handler)


@pytest.fixture
def harness_factory(monkeypatch, tmp_path):
    harnesses: list[SessionStreamHarness] = []

    def create(scenario: str, documents: dict[str, DocumentFixture]):
        from sei_ia.routers.session import stream as stream_module

        async def classify_complexity(*_args: Any, **_kwargs: Any) -> str:
            return "medium"

        monkeypatch.setattr(stream_module, "classify_complexity", classify_complexity)
        harness = SessionStreamHarness(
            monkeypatch,
            tmp_path,
            documents=documents,
            model_factory=lambda: _ToolCallingSessionModel(scenario=scenario),
        )
        harnesses.append(harness)
        return harness

    yield create

    for harness in harnesses:
        harness.close()


def _assert_success(result, mode: str) -> None:  # noqa: ANN001
    result.assert_completed()
    assert result.metadata["mode"] == mode


def _assert_trace_contains(trace_messages: list[str], caller: str, tool: str) -> None:
    assert any(caller in message and tool in message for message in trace_messages)


def test_injected_responde_com_contexto_injetado_sem_explorar(
    harness_factory, trace_messages
):
    harness = harness_factory(
        _INJECTED,
        {
            "DOC-INJECTED": DocumentFixture(
                content="A evidência integral é CANARY_INJECTED_CONTEXT.",
                formatted_document_number="DOC INJECTED",
            )
        },
    )

    result = harness.post(
        "Qual é a evidência integral do documento?",
        [process_spec("PROC-INJECTED", ["DOC-INJECTED"])],
        mode="injected",
        request_overrides={"trace": True},
    )

    _assert_success(result, "injected")
    assert "CANARY_INJECTED_CONTEXT" in result.content
    assert not any(
        "read_file" in message or "task" in message for message in trace_messages
    )


def test_filesystem_le_documento_antes_de_responder(harness_factory, trace_messages):
    hidden_prefix = "Trecho de índice sem a evidência. " * 40
    harness = harness_factory(
        _FILESYSTEM_DIRECT,
        {
            "DOC-FILESYSTEM": DocumentFixture(
                content=hidden_prefix + "Valor integral CANARY_FILESYSTEM_READ.",
                formatted_document_number="DOC FILESYSTEM",
            )
        },
    )

    result = harness.post(
        "Leia o documento e informe o valor integral da evidência.",
        [process_spec("PROC-FILESYSTEM", ["DOC-FILESYSTEM"])],
        mode="filesystem",
        request_overrides={"trace": True},
    )

    _assert_success(result, "filesystem")
    assert "CANARY_FILESYSTEM_READ" in result.content
    _assert_trace_contains(trace_messages, "principal", "read_file")


def test_filesystem_explorador_le_e_devolve_evidencia(harness_factory, trace_messages):
    hidden_prefix = "Trecho de índice sem a evidência. " * 40
    harness = harness_factory(
        _FILESYSTEM_DELEGATED,
        {
            "DOC-DELEGATED": DocumentFixture(
                content=hidden_prefix + "Valor integral CANARY_EXPLORER_HANDOFF.",
                formatted_document_number="DOC DELEGATED",
            )
        },
    )

    result = harness.post(
        "Delegue a leitura e informe o valor integral da evidência.",
        [process_spec("PROC-DELEGATED", ["DOC-DELEGATED"])],
        mode="filesystem",
        request_overrides={"trace": True},
    )

    _assert_success(result, "filesystem")
    assert "CANARY_EXPLORER_HANDOFF" in result.content
    _assert_trace_contains(trace_messages, "principal", "task")
    _assert_trace_contains(trace_messages, "sub:", "read_file")

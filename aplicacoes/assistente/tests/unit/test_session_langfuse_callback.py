"""Redação dos observations automáticos do agente Session."""

import hashlib
import json
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from sei_ia.agents.session_agent.langfuse_callback import SessionLangfuseCallback
from sei_ia.routers.session.observability import build_finalization_trace_output


@dataclass
class _FakeObservation:
    started: dict
    updates: list[dict] = field(default_factory=list)
    ended: bool = False
    trace_id: str = "trace-id"

    def update(self, **kwargs):
        self.updates.append(kwargs)
        return self

    def end(self):
        self.ended = True
        return self


class _FakeClient:
    def __init__(self) -> None:
        self.observations: list[_FakeObservation] = []

    def start_observation(self, **kwargs):
        observation = _FakeObservation(started=kwargs)
        self.observations.append(observation)
        return observation


@pytest.fixture
def callback(monkeypatch):
    handler = SessionLangfuseCallback()
    client = _FakeClient()
    handler.client = client
    monkeypatch.setattr(
        handler,
        "_attach_observation",
        lambda run_id, observation: handler.runs.__setitem__(run_id, observation),
    )
    monkeypatch.setattr(
        handler,
        "_detach_observation",
        lambda run_id: handler.runs.pop(run_id, None),
    )
    return handler, client


@pytest.mark.parametrize("tool_name", ["read_file", "grep"])
def test_tool_observation_remove_conteudo_e_preserva_telemetria(callback, tool_name):
    handler, client = callback
    run_id = uuid4()
    document_content = "CONTEUDO SEI ULTRASSECRETO"

    handler.on_tool_start(
        {"name": tool_name},
        '{"file_path":"proc_1/123.txt"}',
        run_id=run_id,
        inputs={"file_path": "proc_1/123.txt"},
    )
    handler.on_tool_end(
        ToolMessage(
            content=document_content,
            tool_call_id="tool-call-success",
            status="success",
        ),
        run_id=run_id,
    )

    observation = client.observations[0]
    serialized = json.dumps(
        {"started": observation.started, "updates": observation.updates},
        ensure_ascii=False,
        default=str,
    )
    output = observation.updates[-1]["output"]
    assert document_content not in serialized
    assert observation.started["name"] == tool_name
    assert observation.started["as_type"] == "tool"
    assert output["redacted"] is True
    assert output["status"] == "success"
    assert (
        output["sha256"] == hashlib.sha256(document_content.encode("utf-8")).hexdigest()
    )
    assert observation.ended is True


def test_tool_message_error_preserva_status_sem_persistir_conteudo(callback):
    handler, client = callback
    run_id = uuid4()
    document_content = "ERRO COM CONTEUDO SEI ULTRASSECRETO"

    handler.on_tool_start({"name": "grep"}, "consulta", run_id=run_id)
    handler.on_tool_end(
        ToolMessage(
            content=document_content,
            tool_call_id="tool-call-error",
            status="error",
        ),
        run_id=run_id,
    )

    observation = client.observations[0]
    update = observation.updates[-1]
    output = update["output"]
    serialized = json.dumps(update, ensure_ascii=False, default=str)
    assert document_content not in serialized
    assert observation.started["name"] == "grep"
    assert observation.started["as_type"] == "tool"
    assert output["redacted"] is True
    assert output["status"] == "error"
    assert (
        output["sha256"] == hashlib.sha256(document_content.encode("utf-8")).hexdigest()
    )
    assert update["level"] == "ERROR"
    assert "ToolMessage status=error" in update["status_message"]
    assert observation.ended is True


def test_tool_exception_preserva_status_sem_persistir_mensagem(callback):
    handler, client = callback
    run_id = uuid4()
    document_content = "ERRO COM CONTEUDO SEI ULTRASSECRETO"

    handler.on_tool_start({"name": "grep"}, "consulta", run_id=run_id)
    handler.on_tool_error(RuntimeError(document_content), run_id=run_id)

    observation = client.observations[0]
    update = observation.updates[-1]
    assert document_content not in update["status_message"]
    assert update["level"] == "ERROR"
    assert "RuntimeError" in update["status_message"]
    assert observation.ended is True


def test_chain_e_generation_removem_documento_mas_output_raiz_permanece(callback):
    handler, client = callback
    chain_run_id = uuid4()
    generation_run_id = uuid4()
    document_content = "TRECHO DOCUMENTAL QUE NAO PODE IR AO OBSERVATION"

    handler.on_chain_start(
        {"name": "agent"},
        {"messages": [ToolMessage(content=document_content, tool_call_id="call-1")]},
        run_id=chain_run_id,
    )
    handler.on_chain_end(
        {"messages": [AIMessage(content=document_content)]},
        run_id=chain_run_id,
    )
    handler.on_chat_model_start(
        {"name": "model"},
        [
            [
                HumanMessage(content="pergunta"),
                ToolMessage(content=document_content, tool_call_id="call-1"),
            ]
        ],
        run_id=generation_run_id,
        invocation_params={"_type": "openai", "model": "fake"},
    )
    handler.on_llm_end(
        LLMResult(
            generations=[[ChatGeneration(message=AIMessage(content=document_content))]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 3,
                    "total_tokens": 10,
                }
            },
        ),
        run_id=generation_run_id,
    )

    automatic_observations = json.dumps(
        [
            {"started": observation.started, "updates": observation.updates}
            for observation in client.observations
        ],
        ensure_ascii=False,
        default=str,
    )
    generation = client.observations[-1]
    final_output = build_finalization_trace_output(
        content=document_content,
        event_counts={},
        metadata_sent=True,
        end_sent=True,
    )

    assert document_content not in automatic_observations
    assert generation.started["as_type"] == "generation"
    assert generation.updates[-1]["usage"]["total_tokens"] == 10
    assert final_output["response"]["output"] == document_content

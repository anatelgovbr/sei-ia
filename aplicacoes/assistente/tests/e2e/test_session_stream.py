"""E2E herméticos do ``/llm_lang/session_stream``."""

from __future__ import annotations

import json

import pytest

from tests.e2e.session_support import (
    DeterministicSessionModel,
    DocumentFixture,
    FetchCall,
    SessionStreamHarness,
    process_spec,
)

_PRIOR_USER_SECRET = "segredo-exclusivo-do-usuario-7429"


class _UserMessageMemoryModel(DeterministicSessionModel):
    """Prova memória da mensagem humana sem ecoá-la na primeira resposta."""

    def _answer(self, messages):
        human_texts = [
            self._message_text(message)
            for message in messages
            if getattr(message, "type", "") == "human"
        ]
        current = human_texts[-1] if human_texts else ""
        if "CANARY_TURN_TWO" not in current:
            return f"FIRST_TURN_ACK;{super()._answer(messages)}"
        prior_user_visible = any(
            _PRIOR_USER_SECRET in text for text in human_texts[:-1]
        )
        memory_marker = (
            "PRIOR_USER_MEMORY_VISIBLE"
            if prior_user_visible
            else "PRIOR_USER_MEMORY_MISSING"
        )
        return f"{memory_marker};{super()._answer(messages)}"


@pytest.fixture
def harness_factory(monkeypatch, tmp_path):
    harnesses: list[SessionStreamHarness] = []

    def create(**kwargs) -> SessionStreamHarness:
        harness = SessionStreamHarness(monkeypatch, tmp_path, **kwargs)
        harnesses.append(harness)
        return harness

    yield create

    for harness in harnesses:
        harness.close()


def _process_index(manifest: dict) -> dict[str, dict]:
    assert manifest["schema_version"] == 2
    assert "documentos" not in manifest
    processes = manifest["processos"]
    assert isinstance(processes, list)
    return {process["id_procedimento"]: process for process in processes}


def _document_index(process: dict) -> dict[str, dict]:
    documents = process["documentos"]
    assert isinstance(documents, list)
    return {document["id_documento"]: document for document in documents}


def _assert_session_metadata(result, harness, *, is_new: bool, documents: int) -> None:
    result.assert_completed()
    assert result.metadata["session_key"] == (
        f"{harness.id_usuario}_{harness.id_topico}"
    )
    assert result.metadata["is_new_session"] is is_new
    assert result.metadata["documentos"] == documents
    assert result.metadata["documentos_indisponiveis"] == []


def test_cria_e_retoma_sessao_em_dois_turnos(harness_factory):
    harness = harness_factory(
        documents={
            "DOC-ONE": DocumentFixture(
                content="Primeiro documento CANARY_DOC_ONE.",
                formatted_document_number="DOC 0001",
                formatted_process_number="PROC 2026/0001",
                metadata={"type": "decision", "origin": "CANARY_DOC_META_ONE"},
            ),
            "DOC-TWO": DocumentFixture(
                content="Segundo documento CANARY_DOC_TWO.",
                formatted_document_number="DOC 0002",
                metadata={"type": "report", "origin": "CANARY_DOC_META_TWO"},
            ),
        },
        model_factory=_UserMessageMemoryModel,
    )

    first = harness.post(
        f"Primeiro turno com {_PRIOR_USER_SECRET}.",
        [
            process_spec(
                "PROC-ONE",
                ["DOC-ONE"],
                metadata={
                    "id_protocolo_formatado": "PROC 2026/0001",
                    "subject": "CANARY_PROCESS_META",
                },
            )
        ],
    )
    first_manifest = harness.manifest()
    first_fetches = list(harness.fetch_calls)

    second = harness.post(
        "Segundo turno CANARY_TURN_TWO.",
        [process_spec("PROC-ONE", ["DOC-ONE", "DOC-TWO"])],
    )
    second_manifest = harness.manifest()
    second_fetches = harness.fetch_calls[len(first_fetches) :]

    _assert_session_metadata(first, harness, is_new=True, documents=1)
    assert "CANARY_DOC_ONE" in first.content
    assert "FIRST_TURN_ACK" in first.content
    assert _PRIOR_USER_SECRET not in first.content
    assert first_fetches == [FetchCall("DOC-ONE", False, False)]

    _assert_session_metadata(second, harness, is_new=False, documents=2)
    assert "CANARY_DOC_ONE" in second.content
    assert "CANARY_DOC_TWO" in second.content
    assert "PRIOR_USER_MEMORY_VISIBLE" in second.content
    assert "CANARY_TURN_TWO" in second.content
    assert second_fetches == [FetchCall("DOC-TWO", False, False)]

    first_process = _process_index(first_manifest)["PROC-ONE"]
    assert first_process["metadata"] == {
        "id_protocolo_formatado": "PROC 2026/0001",
        "subject": "CANARY_PROCESS_META",
    }
    assert _document_index(first_process)["DOC-ONE"]["metadata"] == {
        "type": "decision",
        "origin": "CANARY_DOC_META_ONE",
    }

    second_process = _process_index(second_manifest)["PROC-ONE"]
    assert second_process["metadata"] == first_process["metadata"]
    second_documents = _document_index(second_process)
    assert list(second_documents) == ["DOC-ONE", "DOC-TWO"]
    assert second_documents["DOC-ONE"]["metadata"] == {
        "type": "decision",
        "origin": "CANARY_DOC_META_ONE",
    }
    assert second_documents["DOC-TWO"]["metadata"] == {
        "type": "report",
        "origin": "CANARY_DOC_META_TWO",
    }
    assert second_manifest["doc_ids"] == ["DOC-ONE", "DOC-TWO"]


def test_semeia_historico_real_da_sessao(harness_factory):
    harness = harness_factory(
        documents={
            "DOC-HISTORY": DocumentFixture(
                content="Documento atual CANARY_HISTORY_DOC.",
                formatted_document_number="DOC HISTORY",
            )
        },
        history=[
            {
                "pergunta": "Pergunta anterior CANARY_SEEDED_QUESTION",
                "resposta": "Resposta anterior CANARY_SEEDED_ANSWER",
                "dth_cadastro": "2026-01-02T03:04:05",
                "total_tokens": 17,
            }
        ],
    )

    result = harness.post(
        "Pergunta atual CANARY_HISTORY_CURRENT.",
        [process_spec("PROC-HISTORY", ["DOC-HISTORY"])],
    )

    _assert_session_metadata(result, harness, is_new=True, documents=1)
    assert "CANARY_SEEDED_QUESTION" in result.content
    assert "CANARY_SEEDED_ANSWER" in result.content
    assert "CANARY_HISTORY_CURRENT" in result.content
    assert "CANARY_HISTORY_DOC" in result.content
    assert harness.history_fetch_calls == 1

    history_path = harness.session_root / "historico_conversa.jsonl"
    rows = [json.loads(line) for line in history_path.read_text().splitlines()]
    assert rows == [
        {
            "pergunta": "Pergunta anterior CANARY_SEEDED_QUESTION",
            "resposta": "Resposta anterior CANARY_SEEDED_ANSWER",
            "dth_cadastro": "2026-01-02T03:04:05",
            "total_tokens": 17,
        }
    ]


def test_skip_memory_ignora_turno_anterior_sem_perder_documentos(harness_factory):
    harness = harness_factory(
        documents={
            "DOC-MEMORY": DocumentFixture(
                content="Documento persistente CANARY_MEMORY_DOC.",
                formatted_document_number="DOC MEMORY",
            )
        }
    )
    process = process_spec("PROC-MEMORY", ["DOC-MEMORY"])

    first = harness.post("Guardar CANARY_MEMORY_OLD.", [process])
    second = harness.post(
        "Responder apenas com CANARY_MEMORY_CURRENT.",
        [process],
        skip_memory=True,
    )

    _assert_session_metadata(first, harness, is_new=True, documents=1)
    assert "CANARY_MEMORY_OLD" in first.content
    _assert_session_metadata(second, harness, is_new=False, documents=1)
    assert "CANARY_MEMORY_CURRENT" in second.content
    assert "CANARY_MEMORY_DOC" in second.content
    assert "CANARY_MEMORY_OLD" not in second.content
    assert harness.fetch_calls == [FetchCall("DOC-MEMORY", False, False)]
    assert not (harness.session_root / "historico_conversa.jsonl").exists()


def test_preserva_agrupamento_de_multiplos_processos_e_documentos(harness_factory):
    harness = harness_factory(
        documents={
            "DOC-A": DocumentFixture(
                content="Conteúdo CANARY_DOC_A.",
                formatted_document_number="DOC A",
                metadata={"category": "alpha"},
            ),
            "DOC-B": DocumentFixture(
                content="Conteúdo CANARY_DOC_B.",
                formatted_document_number="DOC B",
                metadata={"category": "beta"},
            ),
            "DOC-C": DocumentFixture(
                content="Conteúdo CANARY_DOC_C.",
                formatted_document_number="DOC C",
                metadata={"category": "gamma"},
            ),
        }
    )

    result = harness.post(
        "Compare CANARY_MULTI_PROCESS.",
        [
            process_spec(
                "PROC-A",
                ["DOC-A", "DOC-B"],
                metadata={"subject": "assunto A"},
            ),
            process_spec(
                "PROC-B",
                ["DOC-C"],
                metadata={"subject": "assunto B"},
            ),
        ],
    )
    manifest = harness.manifest()

    _assert_session_metadata(result, harness, is_new=True, documents=3)
    for canary in (
        "CANARY_DOC_A",
        "CANARY_DOC_B",
        "CANARY_DOC_C",
        "CANARY_MULTI_PROCESS",
    ):
        assert canary in result.content

    processes = _process_index(manifest)
    assert list(processes) == ["PROC-A", "PROC-B"]
    assert processes["PROC-A"]["metadata"] == {"subject": "assunto A"}
    assert processes["PROC-B"]["metadata"] == {"subject": "assunto B"}
    assert list(_document_index(processes["PROC-A"])) == ["DOC-A", "DOC-B"]
    assert list(_document_index(processes["PROC-B"])) == ["DOC-C"]
    assert {
        document_id: document["metadata"]
        for process in processes.values()
        for document_id, document in _document_index(process).items()
    } == {
        "DOC-A": {"category": "alpha"},
        "DOC-B": {"category": "beta"},
        "DOC-C": {"category": "gamma"},
    }
    assert {call.document_id for call in harness.fetch_calls} == {
        "DOC-A",
        "DOC-B",
        "DOC-C",
    }

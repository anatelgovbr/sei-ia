"""Testes unitários para schemas persistidos da sessão e da memória."""

import json
from datetime import datetime

import pytest
from pydantic import BaseModel, ValidationError

from sei_ia.agents.memory.session.schemas import (
    MdIaInteracaoChatSchema,
    MdIaTopicoChatSchema,
    MemoryModel,
    SessionModel,
)
from sei_ia.services.session_fs.types import SessionMeta


def test_session_meta_v1_persiste_processos_e_documentos_aninhados():
    meta = SessionMeta(
        created_at=1.0,
        last_access=2.0,
        ttl_seconds=60,
        doc_ids=("D1",),
        requested_doc_ids=("D1",),
        processos={
            "P1": {
                "id_procedimento": "P1",
                "metadata": {"numero": "53500.1"},
                "documentos": ["D1"],
            }
        },
        documentos={
            "D1": {
                "id_documento": "D1",
                "content_state": "available",
                "arquivo": "proc_P1/D1.txt",
                "metadata": {"tipo": "oficio"},
                "preview": "inicio",
                "tokens": 12,
                "download_ext": True,
                "sin_armazena_cache": "S",
            }
        },
    )

    payload = json.loads(meta.to_json())

    assert payload["schema_version"] == 1
    assert isinstance(payload["processos"], list)
    assert payload["processos"][0]["documentos"][0]["id_documento"] == "D1"
    assert "documentos" not in payload
    assert meta.doc_ids == ("D1",)


def test_session_meta_v1_recompoe_indices_sem_perder_ordem_ou_metadata():
    meta = SessionMeta.from_json(
        json.dumps(
            {
                "created_at": 1.0,
                "last_access": 2.0,
                "ttl_seconds": 60,
                "doc_ids": ["D2", "D1"],
                "processos": [
                    {
                        "id_procedimento": "P1",
                        "metadata": {"numero": "53500.1"},
                        "documentos": [
                            {
                                "id_documento": "D2",
                                "id_documento_formatado": "DOC-D2",
                                "arquivo": "proc_P1/D2.txt",
                            },
                            {
                                "id_documento": "D1",
                                "id_documento_formatado": "DOC-D1",
                                "arquivo": "proc_P1/D1.txt",
                            },
                        ],
                    }
                ],
                "schema_version": 1,
            }
        )
    )
    payload = json.loads(meta.to_json())

    assert meta.schema_version == 1
    assert payload["processos"][0]["metadata"] == {"numero": "53500.1"}
    assert [
        document["id_documento"] for document in payload["processos"][0]["documentos"]
    ] == ["D2", "D1"]
    assert list(meta.documentos) == ["D2", "D1"]
    assert meta.doc_ids == ("D2", "D1")
    assert "documentos" not in payload


def test_session_meta_rejeita_manifesto_plano_sem_migracao():
    with pytest.raises(ValueError, match=r"índice plano|processos aninhados"):
        SessionMeta.from_json(
            json.dumps(
                {
                    "created_at": 1.0,
                    "last_access": 2.0,
                    "ttl_seconds": 60,
                    "doc_ids": ["D1"],
                    "processos": {"P1": {"documentos": ["D1"]}},
                    "documentos": {"D1": {"id_documento": "D1"}},
                    "schema_version": 1,
                }
            )
        )


class TestMdIaInteracaoChatSchema:
    def test_criacao_minima(self):
        obj = MdIaInteracaoChatSchema(id_md_ia_interacao_chat=1)
        assert obj.id_md_ia_interacao_chat == 1

    def test_eh_pydantic_model(self):
        assert issubclass(MdIaInteracaoChatSchema, BaseModel)

    def test_campos_opcionais_default_none(self):
        obj = MdIaInteracaoChatSchema(id_md_ia_interacao_chat=1)
        assert obj.id_md_ia_topico_chat is None
        assert obj.id_message is None
        assert obj.pergunta is None
        assert obj.resposta is None
        assert obj.dth_cadastro is None

    def test_com_todos_os_campos(self):
        now = datetime(2024, 1, 1, 12, 0, 0)
        obj = MdIaInteracaoChatSchema(
            id_md_ia_interacao_chat=42,
            id_md_ia_topico_chat=10,
            id_message=5,
            pergunta="O que é SEI?",
            resposta="SEI é o sistema eletrônico.",
            dth_cadastro=now,
        )
        assert obj.id_md_ia_interacao_chat == 42
        assert obj.pergunta == "O que é SEI?"
        assert obj.dth_cadastro == now

    def test_serializacao_para_dict(self):
        obj = MdIaInteracaoChatSchema(id_md_ia_interacao_chat=1)
        d = obj.model_dump()
        assert isinstance(d, dict)
        assert "id_md_ia_interacao_chat" in d

    def test_id_obrigatorio_levanta_erro_sem_ele(self):
        with pytest.raises(ValidationError):
            MdIaInteracaoChatSchema()


class TestMemoryModel:
    def test_criacao_basica(self):
        obj = MemoryModel(id=1, prompt="pergunta", resposta="resposta")
        assert obj.id == 1
        assert obj.prompt == "pergunta"
        assert obj.resposta == "resposta"

    def test_eh_pydantic_model(self):
        assert issubclass(MemoryModel, BaseModel)

    def test_created_at_default_none(self):
        obj = MemoryModel(id=1, prompt="p", resposta="r")
        assert obj.created_at is None

    def test_com_created_at(self):
        now = datetime(2024, 6, 15, 10, 30)
        obj = MemoryModel(id=1, prompt="p", resposta="r", created_at=now)
        assert obj.created_at == now

    def test_serializacao(self):
        obj = MemoryModel(id=1, prompt="pergunta", resposta="resposta")
        d = obj.model_dump()
        assert d["id"] == 1
        assert d["prompt"] == "pergunta"

    def test_campos_obrigatorios_levanta_erro(self):
        with pytest.raises(ValidationError):
            MemoryModel(id=1)


class TestSessionModel:
    def _make_memory(self):
        return MemoryModel(id=1, prompt="p", resposta="r")

    def test_criacao_basica(self):
        obj = SessionModel(id=1, session_id="abc", user_id=10, memory=[])
        assert obj.session_id == "abc"
        assert obj.user_id == 10

    def test_eh_pydantic_model(self):
        assert issubclass(SessionModel, BaseModel)

    def test_memory_lista_vazia(self):
        obj = SessionModel(id=1, session_id="s", user_id=1, memory=[])
        assert obj.memory == []

    def test_memory_com_items(self):
        m = self._make_memory()
        obj = SessionModel(id=1, session_id="s", user_id=1, memory=[m])
        assert len(obj.memory) == 1
        assert obj.memory[0].prompt == "p"

    def test_created_at_default_none(self):
        obj = SessionModel(id=1, session_id="s", user_id=1, memory=[])
        assert obj.created_at is None

    def test_serializacao(self):
        obj = SessionModel(id=1, session_id="test_session", user_id=42, memory=[])
        d = obj.model_dump()
        assert d["session_id"] == "test_session"
        assert d["user_id"] == 42


class TestMdIaTopicoChatSchema:
    def test_criacao_minima(self):
        obj = MdIaTopicoChatSchema(id_md_ia_topico_chat=1, id_usuario=100)
        assert obj.id_md_ia_topico_chat == 1
        assert obj.id_usuario == 100

    def test_eh_pydantic_model(self):
        assert issubclass(MdIaTopicoChatSchema, BaseModel)

    def test_campos_opcionais_default_none(self):
        obj = MdIaTopicoChatSchema(id_md_ia_topico_chat=1, id_usuario=100)
        assert obj.id_unidade is None
        assert obj.nome is None
        assert obj.sin_ativo is None
        assert obj.dth_cadastro is None

    def test_com_todos_os_campos(self):
        now = datetime(2024, 3, 15)
        obj = MdIaTopicoChatSchema(
            id_md_ia_topico_chat=5,
            id_usuario=200,
            id_unidade=10,
            nome="Tópico de Teste",
            sin_ativo="S",
            dth_cadastro=now,
        )
        assert obj.nome == "Tópico de Teste"
        assert obj.sin_ativo == "S"

    def test_serializacao(self):
        obj = MdIaTopicoChatSchema(id_md_ia_topico_chat=1, id_usuario=100)
        d = obj.model_dump()
        assert "id_md_ia_topico_chat" in d

    def test_campos_obrigatorios_levanta_erro(self):
        with pytest.raises(ValidationError):
            MdIaTopicoChatSchema(id_md_ia_topico_chat=1)

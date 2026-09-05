"""Contrato da ferramenta read_session, sem rede nem acesso ao filesystem."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from sei_ia.agents.session_agent.read_session import make_read_session_tool
from sei_ia.services.session_fs.types import SessionMeta


def _resolved_v1() -> SimpleNamespace:
    return SimpleNamespace(
        meta=SimpleNamespace(
            processos=[
                {
                    "id_procedimento": "p1",
                    "metadata": {"numero_processo": "53500.1"},
                    "documentos": [
                        {
                            "id_documento": "d1",
                            "estado": "disponivel",
                            "arquivo": "proc_p1/d1.txt",
                            "metadata": {"tipo": "oficio"},
                            "preview": "preview 1",
                            "tokens": 10,
                        },
                        {
                            "id_documento": "d2",
                            "estado": "indisponivel",
                            "arquivo": None,
                            "metadata": {"tipo": "anexo"},
                            "preview": "",
                            "tokens": 0,
                        },
                    ],
                },
                {
                    "id_procedimento": "p2",
                    "metadata": {"numero_processo": "53500.2"},
                    "documentos": [
                        {
                            "id_documento": "d3",
                            "estado": "disponivel",
                            "arquivo": "proc_p2/d3.txt",
                            "metadata": {},
                            "preview": "preview 3",
                            "tokens": 20,
                        }
                    ],
                },
            ]
        )
    )


def _json(tool, **kwargs):
    return json.loads(tool.invoke(kwargs))


def test_catalogo_sem_args_entrega_arvore_completa_em_uma_chamada():
    tool = make_read_session_tool(_resolved_v1())

    result = _json(tool)

    assert result["status"] == "ok"
    assert result["summary"] == {
        "processes": 2,
        "documents": 3,
        "available": 2,
        "unavailable": 1,
        "total_tokens": 30,
    }
    assert [p["id_procedimento"] for p in result["processos"]] == ["p1", "p2"]
    assert [d["id_documento"] for d in result["processos"][0]["documentos"]] == [
        "d1",
        "d2",
    ]
    assert result["processos"][0]["documentos"][0]["metadata"] == {"tipo": "oficio"}
    assert result["processos"][0]["documentos"][0]["arquivo"] == "proc_p1/d1.txt"
    assert "conteudo" not in json.dumps(result)


def test_filtros_process_document_e_vinculo():
    tool = make_read_session_tool(_resolved_v1())

    by_process = _json(tool, id_procedimento="p1")
    assert by_process["status"] == "ok"
    assert len(by_process["processos"]) == 1

    by_document = _json(tool, id_documento="d3")
    assert by_document["status"] == "ok"
    assert by_document["processo"]["id_procedimento"] == "p2"
    assert by_document["documento"]["id_documento"] == "d3"

    exact = _json(tool, id_procedimento="p2", id_documento="d3")
    assert exact["status"] == "ok"
    assert exact["processo"]["id_procedimento"] == "p2"

    mismatch = _json(tool, id_procedimento="p1", id_documento="d3")
    assert mismatch["status"] == "not_found"


def test_not_found_e_documento_ambiguo():
    resolved = _resolved_v1()
    resolved.meta.processos.append(
        {
            "id_procedimento": "p3",
            "metadata": {},
            "documentos": [
                {
                    "id_documento": "d3",
                    "estado": "disponivel",
                    "arquivo": "proc_p3/d3.txt",
                    "metadata": {},
                    "preview": "",
                    "tokens": 1,
                }
            ],
        }
    )
    tool = make_read_session_tool(resolved)

    assert _json(tool, id_procedimento="missing")["status"] == "not_found"
    ambiguous = _json(tool, id_documento="d3")
    assert ambiguous["status"] == "ambiguous"
    assert {item["id_procedimento"] for item in ambiguous["matches"]} == {"p2", "p3"}


def test_tool_captura_snapshot_e_expoe_apenas_filtros_no_schema():
    resolved = _resolved_v1()
    tool = make_read_session_tool(resolved)
    resolved.meta.processos[0]["metadata"]["alterado_depois"] = True

    result = _json(tool, id_procedimento="p1")

    assert "alterado_depois" not in json.dumps(result)
    assert set(tool.args_schema.model_json_schema()["properties"]) == {
        "id_procedimento",
        "id_documento",
    }


def test_snapshot_do_session_meta_v1_usa_arvore_publica():
    processos = {
        process["id_procedimento"]: {
            "id_procedimento": process["id_procedimento"],
            "metadata": process["metadata"],
            "documentos": [doc["id_documento"] for doc in process["documentos"]],
        }
        for process in _resolved_v1().meta.processos
    }
    documentos = {
        doc["id_documento"]: doc
        for process in _resolved_v1().meta.processos
        for doc in process["documentos"]
    }
    meta = SessionMeta(
        created_at=1,
        last_access=1,
        ttl_seconds=60,
        processos=processos,
        documentos=documentos,
    )

    result = _json(make_read_session_tool(SimpleNamespace(meta=meta)))

    assert result["summary"]["documents"] == 3
    assert [p["id_procedimento"] for p in result["processos"]] == ["p1", "p2"]


@pytest.mark.parametrize("kwargs", [{"id_procedimento": ""}, {"id_documento": ""}])
def test_string_vazia_equivale_a_filtro_ausente(kwargs):
    result = _json(make_read_session_tool(_resolved_v1()), **kwargs)
    assert result["status"] == "ok"
    assert len(result["processos"]) == 2

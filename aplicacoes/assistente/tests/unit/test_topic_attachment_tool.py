"""Testes da tool `consultar_anexos_do_topico`.

Verifica:
- Catálogo quando nenhum seletor é informado.
- Consulta por nome e id retornam conteúdo completo persistido.
- Schema da tool NÃO expõe `id_topico` ao LLM.
- `id_topico=None` faz a factory devolver None.
- Anexo expirado/inexistente retorna `status=not_found`.
"""

from __future__ import annotations

import json

import pytest

from sei_ia.configs.settings_config import settings
from sei_ia.data.etl.extract.uploads import ProcessedAttachment
from tests.unit.test_topic_attachment_cache import FakeRedisCache


@pytest.fixture(autouse=True)
def fake_cache(monkeypatch):
    cache = FakeRedisCache()
    monkeypatch.setattr(
        "sei_ia.services.cache.topic_attachments.get_cache", lambda: cache
    )
    return cache


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setattr(settings, "ARQUIVOS_AVULSOS_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "ARQUIVOS_AVULSOS_CACHE_TTL_SECONDS", 60)


def _attach(id_arq: int, nome: str, conteudo: str) -> ProcessedAttachment:
    return ProcessedAttachment(
        id_arquivo_avulso=id_arq,
        nome_arquivo=nome,
        extensao="pdf",
        tipo="text",
        conteudo=conteudo,
        size_bytes=len(conteudo),
        mime="application/pdf",
    )


@pytest.mark.asyncio
async def test_tool_distingue_anexo_vazio_e_indisponivel():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )
    from sei_ia.services.cache.topic_attachments import persist_topic_attachments

    await persist_topic_attachments(
        id_topico=42,
        attachments=[
            ProcessedAttachment(
                id_arquivo_avulso=1,
                nome_arquivo="vazio.pdf",
                extensao="pdf",
                tipo="text",
                conteudo="",
                content_state="empty",
                content_reason="no_text_extracted",
            ),
            ProcessedAttachment(
                id_arquivo_avulso=2,
                nome_arquivo="falho.pdf",
                extensao="pdf",
                tipo="text",
                conteudo=None,
                content_state="unavailable",
                content_reason="download_failed",
            ),
        ],
    )
    tool = make_consultar_anexos_topico_tool(42)

    empty = json.loads(await tool.ainvoke({"id_arquivo_avulso": 1}))
    unavailable = json.loads(await tool.ainvoke({"id_arquivo_avulso": 2}))

    assert empty["status"] == "empty"
    assert "conteudo" not in empty
    assert unavailable["status"] == "unavailable"
    assert unavailable["selected"]["content_reason"] == "download_failed"
    assert "conteudo" not in unavailable


@pytest.mark.asyncio
async def test_factory_retorna_none_sem_id_topico():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )

    assert make_consultar_anexos_topico_tool(None) is None


@pytest.mark.asyncio
async def test_factory_retorna_none_quando_cache_desabilitado(monkeypatch):
    monkeypatch.setattr(settings, "ARQUIVOS_AVULSOS_CACHE_ENABLED", False)
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )

    assert make_consultar_anexos_topico_tool(99) is None


@pytest.mark.asyncio
async def test_schema_nao_expoe_id_topico():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )

    tool = make_consultar_anexos_topico_tool(42)
    schema = tool.args_schema.model_json_schema()
    assert "id_topico" not in schema["properties"]
    # Os argumentos esperados estão presentes.
    assert {"nome_arquivo", "id_arquivo_avulso"} <= set(schema["properties"].keys())
    assert "remaining_context_tokens" not in schema["properties"]


@pytest.mark.asyncio
async def test_listagem_sem_seletor():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )
    from sei_ia.services.cache.topic_attachments import persist_topic_attachments

    await persist_topic_attachments(
        id_topico=42,
        attachments=[_attach(1, "A.pdf", "AAA"), _attach(2, "B.pdf", "BBB")],
    )

    tool = make_consultar_anexos_topico_tool(42)
    result = json.loads(await tool.ainvoke({}))
    assert result["status"] == "ok"
    assert len(result["attachments"]) == 2
    assert {a["nome_arquivo"] for a in result["attachments"]} == {"A.pdf", "B.pdf"}


@pytest.mark.asyncio
async def test_consulta_por_id():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )
    from sei_ia.services.cache.topic_attachments import persist_topic_attachments

    await persist_topic_attachments(
        id_topico=42, attachments=[_attach(1, "doc.pdf", "Conteúdo completo")]
    )
    tool = make_consultar_anexos_topico_tool(42)
    result = json.loads(await tool.ainvoke({"id_arquivo_avulso": 1}))
    assert result["status"] == "ok"
    assert result["selected"]["id_arquivo_avulso"] == 1
    assert result["conteudo"] == "Conteúdo completo"


@pytest.mark.asyncio
async def test_consulta_inclui_contexto_restante_quando_informado():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )
    from sei_ia.services.cache.topic_attachments import persist_topic_attachments

    await persist_topic_attachments(
        id_topico=42, attachments=[_attach(1, "doc.pdf", "Conteúdo")]
    )
    tool = make_consultar_anexos_topico_tool(42, remaining_context_tokens=123)
    result = json.loads(await tool.ainvoke({"id_arquivo_avulso": 1}))
    assert result["status"] == "ok"
    assert result["remaining_context_tokens"] == 123


@pytest.mark.asyncio
async def test_consulta_recusa_conteudo_maior_que_contexto_restante():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )
    from sei_ia.services.cache.topic_attachments import persist_topic_attachments

    await persist_topic_attachments(
        id_topico=42, attachments=[_attach(1, "grande.pdf", "palavra " * 100)]
    )
    tool = make_consultar_anexos_topico_tool(42, remaining_context_tokens=1)
    result = json.loads(await tool.ainvoke({"id_arquivo_avulso": 1}))
    assert result["status"] == "content_too_large"
    assert "conteudo" not in result
    assert result["file_tokens"] > result["remaining_context_tokens"]


@pytest.mark.asyncio
async def test_consulta_por_nome():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )
    from sei_ia.services.cache.topic_attachments import persist_topic_attachments

    await persist_topic_attachments(
        id_topico=42, attachments=[_attach(1, "Relatório.pdf", "Texto")]
    )
    tool = make_consultar_anexos_topico_tool(42)
    result = json.loads(await tool.ainvoke({"nome_arquivo": "relatório.pdf"}))
    assert result["status"] == "ok"
    assert result["selected"]["nome_arquivo"] == "Relatório.pdf"


@pytest.mark.asyncio
async def test_conteudo_completo_sem_truncamento():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )
    from sei_ia.services.cache.topic_attachments import persist_topic_attachments

    conteudo = "0123456789ABCDEF"
    await persist_topic_attachments(
        id_topico=42, attachments=[_attach(1, "big.pdf", conteudo)]
    )
    tool = make_consultar_anexos_topico_tool(42)

    result = json.loads(await tool.ainvoke({"id_arquivo_avulso": 1}))
    assert result["status"] == "ok"
    # O conteúdo completo é retornado, sem truncamento/slicing.
    assert result["conteudo"] == conteudo
    assert len(result["conteudo"]) == 16


@pytest.mark.asyncio
async def test_not_found_quando_id_inexistente():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )

    tool = make_consultar_anexos_topico_tool(42)
    result = json.loads(await tool.ainvoke({"id_arquivo_avulso": 999}))
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_not_found_quando_nome_inexistente():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )
    from sei_ia.services.cache.topic_attachments import persist_topic_attachments

    await persist_topic_attachments(
        id_topico=42, attachments=[_attach(1, "A.pdf", "x")]
    )
    tool = make_consultar_anexos_topico_tool(42)
    result = json.loads(await tool.ainvoke({"nome_arquivo": "outro.pdf"}))
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_ambiguous_quando_nome_bate_em_varios():
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )
    from sei_ia.services.cache.topic_attachments import persist_topic_attachments

    await persist_topic_attachments(
        id_topico=42,
        attachments=[
            _attach(1, "Relatorio-Janeiro.pdf", "jan"),
            _attach(2, "Relatorio-Fevereiro.pdf", "fev"),
        ],
    )
    tool = make_consultar_anexos_topico_tool(42)
    result = json.loads(await tool.ainvoke({"nome_arquivo": "relatorio"}))
    assert result["status"] == "ambiguous"
    assert len(result["matches"]) == 2


@pytest.mark.asyncio
async def test_isolamento_entre_topicos():
    """Tool criada para tópico B não enxerga anexo do tópico A."""
    from sei_ia.agents.attachments.topic_attachment_tool import (
        make_consultar_anexos_topico_tool,
    )
    from sei_ia.services.cache.topic_attachments import persist_topic_attachments

    await persist_topic_attachments(
        id_topico=100, attachments=[_attach(1, "secreto.pdf", "TOP-SECRET")]
    )
    tool_b = make_consultar_anexos_topico_tool(200)
    result = json.loads(await tool_b.ainvoke({"id_arquivo_avulso": 1}))
    assert result["status"] == "not_found"

    # E sem seletor, devolve catálogo vazio.
    result_empty = json.loads(await tool_b.ainvoke({}))
    assert result_empty["status"] == "empty"

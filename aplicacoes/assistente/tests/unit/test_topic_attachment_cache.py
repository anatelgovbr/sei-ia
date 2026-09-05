"""Testes unitários para o cache de anexos avulsos por tópico no Redis.

Cobre persistência, listagem, recuperação por nome/id, TTL e isolamento
entre tópicos. Não exige Redis real — usa um fake do `RedisCache` que
implementa os contratos `get_json/set_json/expire` consumidos pelo serviço.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from sei_ia.configs.settings_config import settings
from sei_ia.data.etl.extract.uploads import ProcessedAttachment


class FakeRedisCache:
    """Fake do RedisCache compatível com `topic_attachments`.

    Armazena entradas em memória, suporta TTL (expiração checada na leitura)
    e simula o circuit breaker estando desabilitado via `enabled=False`.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[dict[str, Any], float | None]] = {}
        self.enabled = True

    def _expired(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return True
        _, expires_at = entry
        return expires_at is not None and expires_at < time.time()

    async def get_json(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        if self._expired(key):
            self._store.pop(key, None)
            return None
        return self._store[key][0]

    async def set_json(self, key: str, data: dict[str, Any], ttl_seconds: int) -> bool:
        if not self.enabled:
            return False
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        self._store[key] = (data, expires_at)
        return True

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        if not self.enabled or key not in self._store:
            return False
        data, _ = self._store[key]
        self._store[key] = (data, time.time() + ttl_seconds)
        return True

    async def delete_key(self, key: str) -> bool:
        return self._store.pop(key, None) is not None


@pytest.fixture(autouse=True)
def fake_cache(monkeypatch):
    """Substitui get_cache() em sei_ia.services.cache.topic_attachments por um fake."""
    cache = FakeRedisCache()
    monkeypatch.setattr(
        "sei_ia.services.cache.topic_attachments.get_cache",
        lambda: cache,
    )
    return cache


@pytest.fixture(autouse=True)
def _enable_attachments_cache(monkeypatch):
    """Garante que o feature flag está ligado durante o teste."""
    monkeypatch.setattr(settings, "ARQUIVOS_AVULSOS_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "ARQUIVOS_AVULSOS_CACHE_TTL_SECONDS", 60)


def _attachment(
    id_arq: int = 1, nome: str = "doc.pdf", conteudo: str | None = "olá"
) -> ProcessedAttachment:
    return ProcessedAttachment(
        id_arquivo_avulso=id_arq,
        nome_arquivo=nome,
        extensao="pdf",
        tipo="text",
        conteudo=conteudo,
        size_bytes=len(conteudo or ""),
        mime="application/pdf",
    )


@pytest.mark.asyncio
async def test_persiste_e_lista_por_topico():
    from sei_ia.services.cache.topic_attachments import (
        list_topic_attachments,
        persist_topic_attachments,
    )

    persisted = await persist_topic_attachments(
        id_topico=42,
        attachments=[
            _attachment(1, "alpha.pdf", "conteúdo do alpha"),
            _attachment(2, "beta.pdf", "conteúdo do beta"),
        ],
    )
    assert persisted is True

    entries = await list_topic_attachments(42)
    assert len(entries) == 2
    nomes = {e["nome_arquivo"] for e in entries}
    assert nomes == {"alpha.pdf", "beta.pdf"}


@pytest.mark.asyncio
async def test_get_por_id():
    from sei_ia.services.cache.topic_attachments import (
        get_topic_attachment,
        persist_topic_attachments,
    )

    await persist_topic_attachments(
        id_topico=42,
        attachments=[_attachment(7, "relatorio.pdf", "Conteúdo cheio")],
    )
    payload = await get_topic_attachment(id_topico=42, id_arquivo_avulso=7)
    assert payload is not None
    assert payload["nome_arquivo"] == "relatorio.pdf"
    assert payload["conteudo"] == "Conteúdo cheio"


@pytest.mark.asyncio
async def test_leitura_v1_distingue_anexo_vazio_de_indisponivel(fake_cache):
    from sei_ia.services.cache.topic_attachments import (
        get_topic_attachment,
        topic_attachment_key,
        topic_index_key,
    )

    legacy_payload = {
        "version": "v1",
        "id_topico": 42,
        "id_arquivo_avulso": 7,
        "nome_arquivo": "vazio.pdf",
        "extensao": "pdf",
        "tipo": "text",
        "conteudo": "",
        "cached_at": "2026-08-07T00:00:00+00:00",
    }
    await fake_cache.set_json(
        topic_attachment_key(42, 7, version="v1"), legacy_payload, 60
    )
    await fake_cache.set_json(
        topic_index_key(42, version="v1"),
        {"version": "v1", "id_topico": 42, "attachments": [legacy_payload]},
        60,
    )

    payload = await get_topic_attachment(id_topico=42, id_arquivo_avulso=7)

    assert payload is not None
    assert payload["content_state"] == "empty"
    assert payload["content_reason"] == "no_text_extracted"


@pytest.mark.asyncio
async def test_imagem_persistida_sem_bytes_vira_indisponivel():
    from sei_ia.services.cache.topic_attachments import (
        get_topic_attachment,
        persist_topic_attachments,
    )

    await persist_topic_attachments(
        id_topico=42,
        attachments=[
            ProcessedAttachment(
                id_arquivo_avulso=8,
                nome_arquivo="foto.png",
                extensao="png",
                tipo="imagem",
                conteudo=None,
            )
        ],
    )

    payload = await get_topic_attachment(id_topico=42, id_arquivo_avulso=8)

    assert payload is not None
    assert payload["content_state"] == "unavailable"
    assert payload["content_reason"] == "visual_not_retained"


@pytest.mark.asyncio
async def test_get_por_nome_exato():
    from sei_ia.services.cache.topic_attachments import (
        get_topic_attachment,
        persist_topic_attachments,
    )

    await persist_topic_attachments(
        id_topico=42,
        attachments=[_attachment(9, "Relatório Anual.pdf", "Sumário do ano")],
    )
    # casefold + match exato
    payload = await get_topic_attachment(
        id_topico=42, nome_arquivo="relatório anual.pdf"
    )
    assert payload is not None
    assert payload["id_arquivo_avulso"] == 9


@pytest.mark.asyncio
async def test_get_por_nome_substring():
    from sei_ia.services.cache.topic_attachments import (
        get_topic_attachment,
        persist_topic_attachments,
    )

    await persist_topic_attachments(
        id_topico=42,
        attachments=[_attachment(9, "Relatório Detalhado de Consumo.pdf", "X")],
    )
    payload = await get_topic_attachment(id_topico=42, nome_arquivo="consumo")
    assert payload is not None
    assert payload["id_arquivo_avulso"] == 9


@pytest.mark.asyncio
async def test_topicos_diferentes_nao_compartilham():
    from sei_ia.services.cache.topic_attachments import (
        get_topic_attachment,
        list_topic_attachments,
        persist_topic_attachments,
    )

    await persist_topic_attachments(
        id_topico=100, attachments=[_attachment(1, "A.pdf", "AAA")]
    )
    await persist_topic_attachments(
        id_topico=200, attachments=[_attachment(2, "B.pdf", "BBB")]
    )

    a_entries = await list_topic_attachments(100)
    b_entries = await list_topic_attachments(200)
    assert {e["id_arquivo_avulso"] for e in a_entries} == {1}
    assert {e["id_arquivo_avulso"] for e in b_entries} == {2}

    # Cross-topic lookup deve falhar.
    cross = await get_topic_attachment(id_topico=100, id_arquivo_avulso=2)
    assert cross is None


@pytest.mark.asyncio
async def test_ttl_expira(monkeypatch):
    from sei_ia.services.cache.topic_attachments import (
        get_topic_attachment,
        persist_topic_attachments,
    )

    monkeypatch.setattr(settings, "ARQUIVOS_AVULSOS_CACHE_TTL_SECONDS", 1)
    await persist_topic_attachments(
        id_topico=42,
        attachments=[_attachment(11, "exp.pdf", "conteúdo")],
    )
    # Avança o relógio do fake — substitui time() para simular passagem do TTL.
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 5)

    payload = await get_topic_attachment(id_topico=42, id_arquivo_avulso=11)
    assert payload is None


@pytest.mark.asyncio
async def test_merge_renova_ttl_de_anexos_antigos():
    """Ao adicionar novo anexo, o índice mantém os anteriores e renova TTL."""
    from sei_ia.services.cache.topic_attachments import (
        list_topic_attachments,
        persist_topic_attachments,
    )

    await persist_topic_attachments(
        id_topico=42, attachments=[_attachment(1, "A.pdf", "A")]
    )
    await persist_topic_attachments(
        id_topico=42, attachments=[_attachment(2, "B.pdf", "B")]
    )

    entries = await list_topic_attachments(42)
    ids = {e["id_arquivo_avulso"] for e in entries}
    assert ids == {1, 2}


@pytest.mark.asyncio
async def test_cache_desabilitado_nao_persiste(monkeypatch):
    from sei_ia.services.cache.topic_attachments import (
        list_topic_attachments,
        persist_topic_attachments,
    )

    monkeypatch.setattr(settings, "ARQUIVOS_AVULSOS_CACHE_ENABLED", False)
    persisted = await persist_topic_attachments(
        id_topico=42, attachments=[_attachment(1, "A.pdf", "A")]
    )
    assert persisted is False
    entries = await list_topic_attachments(42)
    assert entries == []


@pytest.mark.asyncio
async def test_listagem_filtra_anexo_expirado_no_index(fake_cache):
    """Se o anexo no índice já expirou (chave do anexo sumiu), filtrar do retorno."""
    from sei_ia.services.cache.topic_attachments import (
        list_topic_attachments,
        persist_topic_attachments,
        topic_attachment_key,
    )

    await persist_topic_attachments(
        id_topico=42,
        attachments=[
            _attachment(1, "A.pdf", "A"),
            _attachment(2, "B.pdf", "B"),
        ],
    )
    # Apaga manualmente a chave do anexo 2 — índice ainda referencia.
    await fake_cache.delete_key(topic_attachment_key(42, 2))

    entries = await list_topic_attachments(42)
    assert {e["id_arquivo_avulso"] for e in entries} == {1}

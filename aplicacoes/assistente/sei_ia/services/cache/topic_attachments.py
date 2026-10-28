"""Persistência de anexos avulsos por tópico no Redis.

Permite que o agente final consulte, em mensagens subsequentes do mesmo
tópico, nome e conteúdo textual dos anexos enviados anteriormente — mesmo
que o anexo já tenha sido sinalizado para remoção no SEI.

Modelo de chaves (por `id_topico`):

    {prefix}{version}:topic:{id_topico}:index
    {prefix}{version}:topic:{id_topico}:attachment:{id_arquivo_avulso}

Cada anexo persistido no Redis tem TTL próprio (1h por padrão); ao adicionar um
novo anexo o TTL do índice é renovado. Persistência é fail-open: se Redis estiver
fora, registra warning e retorna False, sem propagar exceção.

Há dois TTLs independentes: o upload-fonte no SEI fica disponível por 1h
(contrato externo), enquanto ``ARQUIVOS_AVULSOS_CACHE_TTL_SECONDS`` controla
somente esta cópia textual pós-processamento no Redis. Aumentar o TTL do cache
não prolonga a vida do upload no SEI. Portanto, testes E2E devem criar e consumir
um upload fresco; testes unitários do cache podem sobrescrever o setting/relógio.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.content_status import ContentReason, ContentState
from sei_ia.data.etl.extract.uploads import ProcessedAttachment
from sei_ia.services.cache import get_cache
from sei_ia.services.counter import token_counter

setup_logging()
logger = logging.getLogger(__name__)


# Versão do schema dos anexos por tópico — independente do CACHE_VERSION global,
# para permitir evolução isolada deste cache sem invalidar cache de documentos.
TOPIC_ATTACHMENT_SCHEMA_VERSION = "v2"
_LEGACY_TOPIC_ATTACHMENT_SCHEMA_VERSION = "v1"


def _base_prefix(version: str = TOPIC_ATTACHMENT_SCHEMA_VERSION) -> str:
    """Prefixo das chaves resolvido em tempo de chamada (settings podem mudar em testes)."""
    return f"{settings.ARQUIVOS_AVULSOS_CACHE_KEY_PREFIX}{version}:topic:"


def topic_index_key(
    id_topico: int, *, version: str = TOPIC_ATTACHMENT_SCHEMA_VERSION
) -> str:
    """Chave do índice de anexos do tópico."""
    return f"{_base_prefix(version)}{id_topico}:index"


def topic_attachment_key(
    id_topico: int,
    id_arquivo_avulso: int,
    *,
    version: str = TOPIC_ATTACHMENT_SCHEMA_VERSION,
) -> str:
    """Chave de um anexo específico do tópico."""
    return f"{_base_prefix(version)}{id_topico}:attachment:{id_arquivo_avulso}"


def _attachment_to_payload(
    id_topico: int, attachment: ProcessedAttachment, cached_at: str
) -> dict[str, Any]:
    """Monta o payload completo de um anexo para persistência."""
    conteudo = attachment.conteudo
    content_state: ContentState = attachment.content_state
    content_reason: ContentReason | None = attachment.content_reason
    if attachment.tipo == "imagem" and conteudo is None:
        content_state = "unavailable"
        content_reason = "visual_not_retained"
    content_chars = len(conteudo) if conteudo else 0
    try:
        content_tokens = token_counter(conteudo) if conteudo else 0
    except Exception:
        # token_counter pode falhar para conteúdo muito grande ou inválido;
        # neste cache, esse valor é só informacional.
        content_tokens = 0
    return {
        "version": TOPIC_ATTACHMENT_SCHEMA_VERSION,
        "id_topico": id_topico,
        "id_arquivo_avulso": attachment.id_arquivo_avulso,
        "nome_arquivo": attachment.nome_arquivo,
        "extensao": attachment.extensao,
        "tipo": attachment.tipo,
        "conteudo": conteudo,
        "content_state": content_state,
        "content_reason": content_reason,
        "content_chars": content_chars,
        "content_tokens": content_tokens,
        "size_bytes": attachment.size_bytes,
        "mime": attachment.mime,
        "cached_at": cached_at,
    }


def _index_entry_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extrai os metadados do anexo para a entrada de índice (sem conteúdo)."""
    return {
        "id_arquivo_avulso": payload["id_arquivo_avulso"],
        "nome_arquivo": payload["nome_arquivo"],
        "extensao": payload["extensao"],
        "tipo": payload["tipo"],
        "content_chars": payload.get("content_chars", 0),
        "content_tokens": payload.get("content_tokens", 0),
        "size_bytes": payload.get("size_bytes"),
        "mime": payload.get("mime"),
        "content_state": payload.get("content_state"),
        "content_reason": payload.get("content_reason"),
        "cached_at": payload["cached_at"],
    }


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Projeta um payload v1 no contrato v2 sem reescrever dados legados."""
    normalized = dict(payload)
    if normalized.get("version") == TOPIC_ATTACHMENT_SCHEMA_VERSION:
        return normalized
    conteudo = normalized.get("conteudo")
    if normalized.get("tipo") == "imagem" and conteudo is None:
        state, reason = "unavailable", "visual_not_retained"
    elif conteudo == "":
        state, reason = "empty", "no_text_extracted"
    elif conteudo is None:
        state, reason = "unavailable", "legacy_state_unknown"
    else:
        state, reason = "available", None
    normalized.update(
        {
            "version": TOPIC_ATTACHMENT_SCHEMA_VERSION,
            "content_state": state,
            "content_reason": reason,
        }
    )
    return normalized


async def _get_attachment_payload(
    cache, id_topico: int, id_arquivo_avulso: int
) -> dict[str, Any] | None:
    for version in (
        TOPIC_ATTACHMENT_SCHEMA_VERSION,
        _LEGACY_TOPIC_ATTACHMENT_SCHEMA_VERSION,
    ):
        payload = await cache.get_json(
            topic_attachment_key(id_topico, id_arquivo_avulso, version=version)
        )
        if isinstance(payload, dict):
            return _normalize_payload(payload)
    return None


async def _get_topic_indexes(cache, id_topico: int) -> list[dict[str, Any]]:
    indexes: list[dict[str, Any]] = []
    for version in (
        TOPIC_ATTACHMENT_SCHEMA_VERSION,
        _LEGACY_TOPIC_ATTACHMENT_SCHEMA_VERSION,
    ):
        index = await cache.get_json(topic_index_key(id_topico, version=version))
        if isinstance(index, dict):
            indexes.append(index)
    return indexes


async def persist_topic_attachments(
    id_topico: int,
    attachments: list[ProcessedAttachment],
) -> bool:
    """Persiste anexos do tópico no Redis com TTL configurável.

    Mantém anexos já existentes no índice (merge por `id_arquivo_avulso`):
    novos anexos sobrescrevem; anexos antigos têm o TTL renovado se ainda
    existirem no Redis.

    Retorna True se ao menos um anexo foi gravado. Fail-open em erro do
    Redis: registra warning e retorna False sem propagar exceção.
    """
    if not settings.ARQUIVOS_AVULSOS_CACHE_ENABLED:
        return False
    if not attachments:
        return False
    if id_topico is None:
        return False

    cache = get_cache()
    ttl = settings.ARQUIVOS_AVULSOS_CACHE_TTL_SECONDS
    now = datetime.now(UTC).isoformat()

    try:
        existing_index = await cache.get_json(topic_index_key(id_topico)) or {
            "version": TOPIC_ATTACHMENT_SCHEMA_VERSION,
            "id_topico": id_topico,
            "attachments": [],
        }

        # Mapeia id -> entrada de índice para merge determinístico.
        index_by_id: dict[int, dict[str, Any]] = {
            entry["id_arquivo_avulso"]: entry
            for entry in existing_index.get("attachments", [])
            if isinstance(entry, dict) and "id_arquivo_avulso" in entry
        }

        any_written = False
        for attachment in attachments:
            payload = _attachment_to_payload(id_topico, attachment, now)
            written = await cache.set_json(
                topic_attachment_key(id_topico, attachment.id_arquivo_avulso),
                payload,
                ttl,
            )
            if written:
                index_by_id[attachment.id_arquivo_avulso] = _index_entry_from_payload(
                    payload
                )
                any_written = True
                logger.debug(
                    "Anexo persistido no Redis: id_topico=%s id_arquivo_avulso=%s "
                    "nome=%s chars=%s",
                    id_topico,
                    attachment.id_arquivo_avulso,
                    attachment.nome_arquivo,
                    payload["content_chars"],
                )
            else:
                logger.warning(
                    "Falha ao persistir anexo no Redis (fail-open): "
                    "id_topico=%s id_arquivo_avulso=%s",
                    id_topico,
                    attachment.id_arquivo_avulso,
                )

        # Renova TTL de anexos pré-existentes referenciados no índice.
        # Se a chave do anexo já expirou, expire() devolve False — ela é
        # filtrada do índice na próxima leitura.
        for existing_id in index_by_id:
            if existing_id in {a.id_arquivo_avulso for a in attachments}:
                continue
            await cache.expire(topic_attachment_key(id_topico, existing_id), ttl)

        new_index = {
            "version": TOPIC_ATTACHMENT_SCHEMA_VERSION,
            "id_topico": id_topico,
            "cached_at": now,
            "attachments": list(index_by_id.values()),
        }
        await cache.set_json(topic_index_key(id_topico), new_index, ttl)
    except Exception as exc:
        # Fail-open: nunca deixar persistência derrubar o request atual.
        logger.warning(
            "Falha inesperada ao persistir anexos do tópico %s no Redis: %s",
            id_topico,
            exc,
        )
        return False
    else:
        return any_written


async def list_topic_attachments(id_topico: int) -> list[dict[str, Any]]:
    """Lista metadados de anexos persistidos para o tópico.

    Retorna lista vazia se índice não existir, estiver expirado ou Redis
    indisponível. Filtra entradas cujo payload do anexo já expirou.
    """
    if not settings.ARQUIVOS_AVULSOS_CACHE_ENABLED:
        return []
    if id_topico is None:
        return []

    cache = get_cache()
    try:
        indexes = await _get_topic_indexes(cache, id_topico)
    except Exception as exc:
        logger.warning(
            "Falha ao consultar índice de anexos do tópico %s: %s", id_topico, exc
        )
        return []

    if not indexes:
        return []

    entries = [entry for index in indexes for entry in index.get("attachments", [])]
    valid_entries: list[dict[str, Any]] = []
    seen: set[int] = set()
    for entry in entries:
        if not isinstance(entry, dict) or "id_arquivo_avulso" not in entry:
            continue
        attachment_id = entry["id_arquivo_avulso"]
        if attachment_id in seen:
            continue
        # Verifica se o payload do anexo ainda existe; caso contrário,
        # o índice está dessincronizado e o anexo expirou.
        payload = await _get_attachment_payload(cache, id_topico, attachment_id)
        if payload is None:
            continue
        seen.add(attachment_id)
        normalized_entry = dict(entry)
        normalized_entry["content_state"] = payload["content_state"]
        normalized_entry["content_reason"] = payload["content_reason"]
        valid_entries.append(normalized_entry)
    return valid_entries


def _normalize_name(value: str) -> str:
    """Comparação case-insensitive estável para nomes de arquivo."""
    return value.strip().casefold()


async def get_topic_attachment(  # noqa: PLR0911
    id_topico: int,
    id_arquivo_avulso: int | None = None,
    nome_arquivo: str | None = None,
) -> dict[str, Any] | None:
    """Recupera o payload completo de um anexo do tópico.

    Seleciona por `id_arquivo_avulso` (match exato) ou `nome_arquivo`
    (match case-insensitive contra `nome_arquivo` do índice).

    Quando o nome bate em múltiplos anexos, retorna None — caller deve
    listar e refinar. Quando nada bate ou Redis está indisponível,
    também retorna None.
    """
    if not settings.ARQUIVOS_AVULSOS_CACHE_ENABLED:
        return None
    if id_topico is None:
        return None
    if id_arquivo_avulso is None and not nome_arquivo:
        return None

    cache = get_cache()

    if id_arquivo_avulso is not None:
        return await _get_attachment_payload(cache, id_topico, id_arquivo_avulso)

    # Busca por nome — usa índice para resolver id.
    entries = await list_topic_attachments(id_topico)
    if not entries:
        return None
    needle = _normalize_name(nome_arquivo or "")
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and _normalize_name(entry.get("nome_arquivo", "")) == needle
    ]
    if not matches:
        # Fallback: match parcial (substring) para tolerância a usuários
        # que digitam só parte do nome.
        matches = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and needle in _normalize_name(entry.get("nome_arquivo", ""))
        ]
    if len(matches) != 1:
        return None

    return await _get_attachment_payload(
        cache, id_topico, matches[0]["id_arquivo_avulso"]
    )


async def find_topic_attachments_by_name(
    id_topico: int, nome_arquivo: str
) -> list[dict[str, Any]]:
    """Retorna entradas de índice que casam com o nome (exato ou substring)."""
    if not settings.ARQUIVOS_AVULSOS_CACHE_ENABLED or id_topico is None:
        return []
    entries = await list_topic_attachments(id_topico)
    if not entries:
        return []
    needle = _normalize_name(nome_arquivo)
    exact = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and _normalize_name(entry.get("nome_arquivo", "")) == needle
    ]
    if exact:
        return exact
    return [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and needle in _normalize_name(entry.get("nome_arquivo", ""))
    ]

"""Catálogo de modelos disponíveis no LiteLLM Proxy, com o tipo de agente de cada um.

Consulta ``GET /model/info`` no proxy (mesmo padrão de
``speech_to_text._fetch_stt_backend_model``) e devolve, para cada entrada do
``model_list`` do ``litellm_config.yaml``, o ``model_name``, as ``tags``
(``agents:<papel>``) declaradas em ``litellm_params.tags`` e os
``reasoning_effort_levels`` declarados em ``model_info`` (ver
``litellm_config.template.yaml`` / ``LITELLM_MODEL_CATALOG`` — documentação
de quais valores de ``reasoning_effort`` aquele modelo físico aceita de
verdade). Cacheado com TTL curto — não é rastreio de custo, é a mesma fonte
de verdade do proxy, só evita martelar `/model/info` a cada chamada.

Diferente de ``speech_to_text``, aqui não há fallback silencioso: se a
consulta falhar, a exceção propaga — o endpoint inteiro existe pra informar
o catálogo real, então devolver algo vazio/errado seria pior que um erro
claro. Pelo mesmo motivo, ``validate_reasoning_effort`` rejeita (nunca
ignora) um ``reasoning_effort`` pedido pro payload quando o modelo alvo não
declara nenhum nível no ``model_info`` — sem essa informação não há como
saber se o proxy/modelo aceita o valor.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TypedDict

import httpx

from sei_ia.configs.settings_config import settings

logger = logging.getLogger(__name__)

_MODEL_INFO_TIMEOUT_S = 5.0
_CATALOG_TTL_S = 300.0  # 5 min — mesmo TTL usado em speech_to_text.py
_catalog_cache: tuple[list[ModelCatalogEntry], float] | None = None


class ModelCatalogEntry(TypedDict):
    model_name: str
    tags: list[str]
    reasoning_effort_levels: list[str]


def _fetch_model_catalog() -> list[ModelCatalogEntry]:
    """Busca o catálogo real no proxy via ``GET /model/info``."""
    resp = httpx.get(
        f"{settings.LITELLM_PROXY_URL.rstrip('/')}/model/info",
        headers={
            "Authorization": f"Bearer {settings.LITELLM_PROXY_API_KEY or 'dummy-key'}"
        },
        timeout=_MODEL_INFO_TIMEOUT_S,
    )
    resp.raise_for_status()
    entries: list[ModelCatalogEntry] = []
    for entry in resp.json().get("data", []):
        model_name = entry.get("model_name")
        if not model_name:
            continue
        tags = entry.get("litellm_params", {}).get("tags") or []
        reasoning_effort_levels = (
            entry.get("model_info", {}).get("reasoning_effort_levels") or []
        )
        entries.append(
            {
                "model_name": model_name,
                "tags": list(tags),
                "reasoning_effort_levels": list(reasoning_effort_levels),
            }
        )
    return entries


def get_model_catalog() -> list[ModelCatalogEntry]:
    """Retorna o catálogo de modelos (nome + tags de agente) do proxy.

    Cacheado por ``_CATALOG_TTL_S``. Nunca mascara falha: se a consulta ao
    proxy falhar, a exceção propaga pro chamador (o router converte pra
    ``HTTPException(502)``).
    """
    global _catalog_cache
    if (
        _catalog_cache is not None
        and (time.monotonic() - _catalog_cache[1]) < _CATALOG_TTL_S
    ):
        return _catalog_cache[0]

    entries = _fetch_model_catalog()
    _catalog_cache = (entries, time.monotonic())
    return entries


def _reasoning_effort_catalog_order(catalog: list[ModelCatalogEntry]) -> list[str]:
    """Ordem "canônica" de ``reasoning_effort``, derivada do próprio catálogo
    ao vivo — não fixada em código. Pega a ordem de primeira aparição de
    cada nível em qualquer entrada do ``GET /model/info``: normalmente
    alguma entrada declara a lista completa (ex.: ``["none", "low",
    "medium", "high"]``) e essa ordem vira a referência; nomes de nível
    fora desse conjunto (proxy configurado com algo novo amanhã) continuam
    aparecendo, só entram depois dos já vistos. Assim o código nunca supõe
    de antemão quais valores de reasoning_effort existem.
    """
    order: list[str] = []
    seen: set[str] = set()
    for entry in catalog:
        for level in entry["reasoning_effort_levels"]:
            if level not in seen:
                seen.add(level)
                order.append(level)
    return order


def get_reasoning_effort_levels(model_name: str) -> list[str]:
    """Níveis de ``reasoning_effort`` declarados no proxy para ``model_name``.

    Lê ``model_info.reasoning_effort_levels`` de TODAS as entradas do
    catálogo (`GET /model/info`) com esse ``model_name`` e mescla os níveis
    — o mesmo modelo físico pode aparecer mais de uma vez na resposta do
    proxy: a entrada fixa do tier (`litellm_config.template.yaml`, sem
    `model_info.reasoning_effort_levels` — o template não tem esse campo)
    e uma entrada de ``LITELLM_MODEL_CATALOG`` redeclarando o mesmo
    `model_name` só pra anexar os níveis. Parar na primeira entrada (como
    antes) deixava a entrada vazia esconder os níveis reais declarados numa
    entrada seguinte. Lista vazia = modelo não encontrado no catálogo OU
    encontrado mas nenhuma entrada declara níveis — os dois casos tratados
    igual por quem chama: nenhum ``reasoning_effort`` deve ser aceito.
    """
    catalog = get_model_catalog()
    model_levels = {
        level
        for entry in catalog
        if entry["model_name"] == model_name
        for level in entry["reasoning_effort_levels"]
    }
    return [
        level
        for level in _reasoning_effort_catalog_order(catalog)
        if level in model_levels
    ]


async def validate_model_override(model_override: str) -> None:
    """Valida um `model` (override) contra o catálogo ao vivo do proxy LiteLLM.

    O override só é suportado para o papel `principal` (mesma decisão de
    design de sempre — explorador/classificador/etc. continuam nos tiers
    fixos). Levanta ``ValueError`` (o router converte pra
    ``HTTPException(422)``/frame de erro SSE) quando o alias pedido não
    existe no proxy ou existe mas não carrega a tag ``agents:principal`` —
    nunca aceita silenciosamente. Roda a consulta ao catálogo (bloqueante,
    cacheada) numa thread pra não travar o event loop.
    """
    entries = await asyncio.to_thread(get_model_catalog)
    tag = "agents:principal"
    if any(
        entry["model_name"] == model_override and tag in entry["tags"]
        for entry in entries
    ):
        return
    # set() por causa do mesmo model_name podendo aparecer mais de uma vez no
    # catalogo (ver get_reasoning_effort_levels) — sem isso a mensagem lista
    # o alias duplicado.
    allowed = sorted({entry["model_name"] for entry in entries if tag in entry["tags"]})
    msg = (
        f"model={model_override!r} não está liberado para override (aliases "
        f"declarados com a tag {tag!r} no litellm_config: {allowed or 'nenhum'})."
    )
    raise ValueError(msg)


async def validate_reasoning_effort(model_name: str, reasoning_effort: str) -> None:
    """Valida ``reasoning_effort`` contra o que o proxy declara pra ``model_name``.

    Levanta ``ValueError`` (o router converte pra ``HTTPException(422)``)
    quando o nível pedido não está entre os declarados em
    ``model_info.reasoning_effort_levels`` — inclusive quando o modelo não
    declara nenhum nível. Roda a consulta ao catálogo (bloqueante, cacheada)
    numa thread pra não travar o event loop dos endpoints async que chamam
    esta função.
    """
    allowed = await asyncio.to_thread(get_reasoning_effort_levels, model_name)
    if reasoning_effort not in allowed:
        msg = (
            f"reasoning_effort={reasoning_effort!r} não é suportado pelo modelo "
            f"{model_name!r} (níveis declarados no litellm_config: "
            f"{allowed or 'nenhum'})."
        )
        raise ValueError(msg)

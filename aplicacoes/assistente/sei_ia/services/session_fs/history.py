"""Sementação de histórico na thread nova a partir do JSONL local do tópico.

Lê o arquivo ``historico_conversa.jsonl`` (gravado pelo manager) e devolve
pares HumanMessage/AIMessage com ids estáveis e determinísticos. Nenhum acesso
ao banco: a semente vem do JSONL, evitando segunda chamada ao SEI.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

logger = logging.getLogger(__name__)


def _stable_id(session_key: str, kind: str, ordinal: int) -> str:
    """Gera id determinístico para evitar duplicatas ao re-semear. sha256(seed:{key}:{kind}:{ord})."""
    raw = f"seed:{session_key}:{kind}:{ordinal}"
    return hashlib.sha256(raw.encode()).hexdigest()


def seed_messages_from_jsonl(
    jsonl_path: Path,
    session_key: str,
    max_turns: int,
) -> list[BaseMessage]:
    """Lê o JSONL de histórico e devolve os últimos ``max_turns`` pares como mensagens.

    Os ids são estáveis (determinísticos por session_key + ordinal) para que
    chamadas repetidas não gerem duplicatas no checkpointer. Linhas com resposta
    vazia são ignoradas. Arquivo ausente ou vazio devolve lista vazia.
    """
    if not jsonl_path.exists():
        return []

    try:
        linhas = [
            json.loads(linha)
            for linha in jsonl_path.read_text(encoding="utf-8").splitlines()
            if linha.strip()
        ]
    except Exception:
        logger.warning(
            "Falha ao ler %s para semente de histórico", jsonl_path, exc_info=True
        )
        return []

    if not linhas:
        return []

    # Pega os últimos N turnos (linhas já estão em ordem cronológica ascendente)
    recentes = linhas[-max_turns:]

    mensagens: list[BaseMessage] = []
    for ordinal, linha in enumerate(recentes):
        pergunta = linha.get("pergunta") or ""
        resposta = linha.get("resposta") or ""
        dth = linha.get("dth_cadastro") or ""

        if not resposta:
            continue

        prefixo = f"{dth}: " if dth else ""
        mensagens.append(
            HumanMessage(
                content=f"{prefixo}{pergunta}",
                id=_stable_id(session_key, "h", ordinal),
            )
        )
        mensagens.append(
            AIMessage(
                content=resposta,
                id=_stable_id(session_key, "a", ordinal),
            )
        )

    return mensagens

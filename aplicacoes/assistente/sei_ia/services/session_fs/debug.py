"""Verificação de comportamento via blob do checkpoint (padrão de stack real).

Em vez de confiar na resposta do LLM (que pode alucinar), confirmamos que algo
realmente aconteceu procurando a string nos blobs serializados do checkpointer
Postgres da thread. Ex.: `deep_research_search` aparecer nos blobs prova que a
tool foi de fato chamada.
"""

from __future__ import annotations

import psycopg

from sei_ia.configs.settings_config import settings

_TABLES = ("checkpoint_writes", "checkpoint_blobs")


def checkpoint_blob_counts(
    thread_id: str, needles: list[str], *, schema: str | None = None
) -> dict[str, int]:
    """Para cada `needle`, conta blobs da thread que a contêm (writes + blobs).

    `count > 0` prova que aquele conteúdo entrou no estado serializado da thread.
    Lê a conexão e o schema das settings do app, então funciona em qualquer stack
    configurada.
    """
    schema = schema or settings.SESSION_CHECKPOINTER_SCHEMA
    counts = dict.fromkeys(needles, 0)
    conn_str = settings.DB_SEIIA_CONNECTION_STRING
    with psycopg.connect(conn_str, autocommit=True) as conn, conn.cursor() as cur:
        for needle in needles:
            total = 0
            for table in _TABLES:
                cur.execute(
                    f'SELECT count(*) FROM "{schema}".{table} '  # noqa: S608  # NOSONAR — schema de settings, table de constante _TABLES
                    "WHERE thread_id = %s "
                    "AND position(%s in encode(blob, 'escape')) > 0",
                    (thread_id, needle),
                )
                total += cur.fetchone()[0]
            counts[needle] = total
    return counts


def assert_tool_called(thread_id: str, tool_name: str, *, schema: str | None = None):
    """Helper de teste: falha se a tool não aparecer no estado da thread."""
    count = checkpoint_blob_counts(thread_id, [tool_name], schema=schema)[tool_name]
    assert count > 0, f"tool {tool_name!r} não foi chamada na thread {thread_id}"
    return count

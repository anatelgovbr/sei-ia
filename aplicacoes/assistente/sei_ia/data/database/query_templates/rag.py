"""Queries para RAG."""

from sei_ia.configs.settings_config import settings

EMBEDDINGS_TABLE_NAME = settings.EMBEDDINGS_TABLE_NAME
_SCHEMA_TABLE = settings.DB_SEIIA_ASSISTENTE_SCHEMA + "." + EMBEDDINGS_TABLE_NAME

SIMILARITY_PGVECTOR_QUERY = (
    "        SELECT\n"
    "            id_documento,\n"
    "            1 - (embedding <=> '{prompt_embedding}') AS cosine_similarity,\n"
    "            start_position,\n"
    "            finished_position\n"
    "        FROM " + _SCHEMA_TABLE + "\n"
    "        WHERE\n"
    "            1=1\n"
    "            AND {filter_conditions}\n"
    "            AND 1 - (embedding <=> '{prompt_embedding}') >= {min_similarity}\n"
    "        ORDER BY cosine_similarity DESC\n"
    "        LIMIT {top_k};\n"
    "        "
)

SQL_HAS_DOCUMENT_EMBEDDING = (
    "    SELECT\n"
    "        id_documento\n"
    "    FROM " + _SCHEMA_TABLE + "\n"
    "    WHERE\n"
    "        1=1\n"
    "        {where_id_documento};\n"
    "    "
)

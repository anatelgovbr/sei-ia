"""Queries para RAG."""

from sei_ia.configs.settings_config import settings

EMBEDDINGS_TABLE_NAME = settings.EMBEDDINGS_TABLE_NAME

SIMILARITY_PGVECTOR_QUERY = f"""
        SELECT
            id_documento,
            1 - (embedding <=> '{{prompt_embedding}}') AS cosine_similarity,
            start_position,
            finished_position
        FROM {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{EMBEDDINGS_TABLE_NAME}
        WHERE
            1=1
            AND {{filter_conditions}}
            AND 1 - (embedding <=> '{{prompt_embedding}}') >= {{min_similarity}}
        ORDER BY cosine_similarity DESC
        LIMIT {{top_k}};
        """  # noqa:S608

SQL_HAS_DOCUMENT_EMBEDDING = f"""
    SELECT
        id_documento
    FROM {settings.DB_SEIIA_ASSISTENTE_SCHEMA}.{EMBEDDINGS_TABLE_NAME}
    WHERE
        1=1
        {{where_id_documento}};
    """  # noqa:S608

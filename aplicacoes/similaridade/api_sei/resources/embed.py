"""Utilitários e filtros para processamento de texto."""

from fastapi import HTTPException

from api_sei.db_models.db_instances import app_db

QUERY_SIMILAR_EMBEDDING = """SELECT id_processo AS id,
 1 -((SELECT embd FROM embd_doc_minilm_128_chunk_merged WHERE id_processo = {id_processo}) <=> embd)
   as score FROM embd_doc_minilm_128_chunk_merged {where_clause} ORDER BY score DESC LIMIT {rows};"""


def get_similarity_embedding(
    id_processo: int, list_id_processos: list[int], rows: int
) -> dict:
    """Recupera embeddings de similaridade para um ID de processo dado, baseado em lista de IDS e número de linhas.

    Parameters:
        id_processo (int): O ID do processo para o qual recuperar embeddings.
        list_id_processos (List[int]): A lista de IDs de processos para comparar similaridades.
        rows (int): O número de recomendações a retornar.

    Returns:
        dict: Um dicionário contendo uma lista de recomendações com IDs e pontuações.
    """
    if not isinstance(list_id_processos, list):
        raise TypeError("list_id_processos deve ser uma lista")

    if not list_id_processos:
        raise ValueError("list_id_processos não pode ser vazio")

    if not isinstance(id_processo, int):
        raise TypeError("id_processo deve ser um inteiro")

    if not isinstance(rows, int) or rows <= 0:
        raise ValueError("rows deve ser um inteiro positivo maior que zero")

    try:
        where_clause = (
            "WHERE id_processo IN ({})".format(",".join(map(str, list_id_processos)))
            if list_id_processos
            else ""
        )
        query = QUERY_SIMILAR_EMBEDDING.format(
            id_processo=id_processo, where_clause=where_clause, rows=rows
        )
        result = app_db.execute_query(query)
        recommendation = [dict(row) for row in result]

        return {"recommendation": recommendation}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erro de consulta no banco: {e!s}"
        ) from e

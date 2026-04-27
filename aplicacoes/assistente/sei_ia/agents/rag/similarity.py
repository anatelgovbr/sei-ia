"""Módulo de busca por trechos similares."""

import logging

from sei_ia.agents.prompts.rag import DOC_METADATA_CHUNKS
from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.database.db_instances import app_db_instance
from sei_ia.data.database.query_templates.rag import SIMILARITY_PGVECTOR_QUERY
from sei_ia.services.embedder.chunk_retriever import ChunkContentRetriever
from sei_ia.services.exceptions.http_exceptions import HTTPException500

setup_logging()

logger = logging.getLogger(__name__)


async def similarity_query(
    prompt_embedding: list,
    filter_metadata: dict,
    min_similarity: float,
    top_k: int,
    user_state: dict = None,
) -> tuple[str, dict]:
    """Funcao de busca de trechos similares em documento.

    Args:
        prompt_embedding (ndarray): Embedding do prompt
        filter_metadata (Tuple[str,Optional[str|int]]): Qual a chave e valor no json da coluna metadata_ quer filtrar
        min_similarity (float): Similaridade mínima, deve ser um valor entre 0 e 1
        top_k (int): Melhores casos

    Raises:
        HTTPException204: Caso não haja nenhuma informação parecida

    Returns:
        Tupla[str: Retorna uma string com os top-k textos, dict: Contendo os chunks retornados no rag]
    """
    logger.debug("entrou no similarity_query")
    logger.debug(f"Parâmetros: min_similarity={min_similarity}, top_k={top_k}")
    logger.debug(
        f"Tamanho do embedding: {len(prompt_embedding) if prompt_embedding else 0}"
    )
    format_filter_metadata = []
    for metadata in filter_metadata:
        for key, value in metadata.items():
            if value != "" and value is not None:
                format_filter_metadata.append(f"{key} = '{value}'")
                logger.debug(f"Adicionado filtro: {key} = '{value}'")

    filter_conditions = " OR ".join(format_filter_metadata)
    logger.debug(
        f"Condições de filtro SQL: {filter_conditions if filter_conditions else '1=1'}"
    )

    sql = SIMILARITY_PGVECTOR_QUERY.format(
        prompt_embedding=prompt_embedding,
        filter_conditions=filter_conditions if filter_conditions != "" else "1=1",
        min_similarity=str(min_similarity),
        top_k=top_k,
    )
    logger.debug(f"Query SQL construída (primeiros 500 chars): {sql[:500]}...")

    if not app_db_instance.async_engine:
        error_msg = "AsyncEngine não está inicializado. Verifique a configuração do banco de dados."
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    try:
        similarity_df = await app_db_instance.select_native_async(sql)
        logger.debug(f"Query retornou {len(similarity_df)} resultados")
    except Exception as e:
        logger.error(f"Erro ao executar query de similaridade: {e}", exc_info=True)
        # Retornar resultado vazio em vez de lançar erro
        return "", {}

    if len(similarity_df) == 0:
        logger.warning("Nao localizou documentos similares.")
        logger.debug(f"Filtros utilizados: {filter_metadata}")
        logger.debug(f"Min similarity: {min_similarity}, Top K: {top_k}")
        return "", {}

    logger.debug(
        f"similaridades dos chunks {similarity_df['cosine_similarity'].tolist()}"
    )

    retriever = ChunkContentRetriever()

    document_chunks = {}
    for _, row in similarity_df.iterrows():
        id_documento = str(row["id_documento"]).replace(".0", "")
        chunk = {
            "start_position": int(row["start_position"]),
            "finished_position": int(row["finished_position"]),
            "similarity_score": row["cosine_similarity"],
        }
        if id_documento not in document_chunks:
            document_chunks[id_documento] = []
        document_chunks[id_documento].append(chunk)

    # Construir a string CHUNKS_RAG para cada documento
    result_strings = []
    for id_documento, chunks in document_chunks.items():
        doc_metadata = None
        proc_metadata = None
        id_doc_formatado = None

        id_doc_normalized = (
            id_documento.replace(".0", "") if ".0" in id_documento else id_documento
        )

        for item_proc in user_state.get("id_procedimentos", []):
            for item_doc in item_proc.id_documentos:
                item_doc_id = str(item_doc.id_documento).replace(".0", "")

                if item_doc_id == id_doc_normalized:
                    doc_metadata = item_doc.metadata
                    proc_metadata = item_proc.metadata
                    id_doc_formatado = item_doc.id_documento_formatado
                    logger.debug(f"Metadados encontrados para documento {id_documento}")
                    break
            if doc_metadata:
                break

        # Se encontrou os metadados, construir a string
        if doc_metadata and proc_metadata:
            # Recuperar o texto de cada chunk usando o retriever
            chunk_texts = []
            for chunk in chunks:
                text = await retriever.get_chunk_content(
                    id_documento=id_doc_normalized,
                    start_position=chunk["start_position"],
                    end_position=chunk["finished_position"],
                    user_state=user_state,
                )
                if text:
                    chunk_texts.append(text)
                    # Adicionar o texto ao chunk para retorno em document_chunks
                    chunk["text"] = text
                else:
                    logger.warning(
                        f"Não foi possível recuperar chunk: doc={id_documento}, "
                        f"pos=[{chunk['start_position']}:{chunk['finished_position']}]"
                    )

            if chunk_texts:
                result_strings.append(
                    DOC_METADATA_CHUNKS.format(
                        id_doc_formatado=id_doc_formatado,
                        chunk="\n\n".join(chunk_texts),
                        metadados_proc=proc_metadata,
                        metadados_doc=doc_metadata,
                    )
                )
        else:
            available_docs = []
            for item_proc in user_state.get("id_procedimentos", []):
                for item_doc in item_proc.id_documentos:
                    available_docs.append(str(item_doc.id_documento))

            logger.error(
                f"Documento {id_documento} (normalizado: {id_doc_normalized}) não encontrado no user_state. "
                f"Documentos disponíveis: {available_docs}"
            )
            raise HTTPException500(
                detail=f"Não foi possível encontrar os metadados do documento {id_documento} durante similarity_query. "
                f"Documentos disponíveis no user_state: {', '.join(available_docs)}"
            )

    logger.debug("saiu do similarity_query")
    return "\n\n".join(result_strings), document_chunks

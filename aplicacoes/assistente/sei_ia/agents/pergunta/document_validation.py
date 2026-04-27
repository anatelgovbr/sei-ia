"""Módulo para validação de documentos indexados no banco vetorial."""

import inspect
import logging

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.database.db_instances import app_db_instance
from sei_ia.data.database.query_templates.rag import SQL_HAS_DOCUMENT_EMBEDDING
from sei_ia.data.pydantic_models import UserState

setup_logging()
logger = logging.getLogger(__name__)


async def check_all_documents_indexed(user_state: UserState) -> dict[str, bool]:
    """
    Verifica se todos os documentos do processo estão indexados no banco vetorial.

    Args:
        user_state: Estado do usuário contendo os procedimentos e documentos

    Returns:
        Dict com:
        - 'all_indexed': bool indicando se todos estão indexados
        - 'missing_documents': lista de IDs de documentos não indexados
        - 'indexed_documents': lista de IDs de documentos indexados
        - 'total_documents': total de documentos verificados
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    # Extrair todos os IDs de documentos
    document_ids = []
    for proc in user_state.get("id_procedimentos", []):
        if hasattr(proc, "id_documentos"):
            for doc in proc.id_documentos:
                if hasattr(doc, "id_documento"):
                    document_ids.append(doc.id_documento)

    logger.info(f"Verificando indexação de {len(document_ids)} documentos")
    logger.debug(f"IDs dos documentos: {document_ids}")

    if not document_ids:
        logger.warning("Nenhum documento encontrado para verificar")
        return {
            "all_indexed": True,
            "missing_documents": [],
            "indexed_documents": [],
            "total_documents": 0,
        }

    try:
        # Verificar quais documentos estão indexados
        # Usar CAST para garantir compatibilidade de tipos entre string e integer
        where_id_documento = "AND id_documento::text IN ({})".format(
            ",".join([f"'{doc_id}'" for doc_id in document_ids])
        )
        sql = SQL_HAS_DOCUMENT_EMBEDDING.format(where_id_documento=where_id_documento)

        logger.debug(f"Query de verificação: \n{sql}")

        result = await app_db_instance.select_native_async(sql)

        # Extrair IDs dos documentos indexados
        indexed_ids = []
        if len(result) > 0:
            indexed_ids = [str(row["id_documento"]) for _, row in result.iterrows()]

        logger.debug(f"Documentos indexados encontrados: {indexed_ids}")

        # Identificar documentos faltantes
        missing_ids = [doc_id for doc_id in document_ids if doc_id not in indexed_ids]

        all_indexed = len(missing_ids) == 0

        logger.info("Resultado da verificação:")
        logger.info(f"  - Total de documentos: {len(document_ids)}")
        logger.info(f"  - Chunks indexados: {len(indexed_ids)}")
        logger.info(f"  - Documentos faltantes: {len(missing_ids)}")

        if missing_ids:
            logger.warning(f"Documentos não indexados: {missing_ids}")
        else:
            logger.info("Todos os documentos estão indexados!")

        result_dict = {
            "all_indexed": all_indexed,
            "missing_documents": missing_ids,
            "indexed_documents": indexed_ids,
            "total_documents": len(document_ids),
        }

        logger.debug(f">> saindo de {inspect.currentframe().f_code.co_name}")
        return result_dict

    except Exception as e:
        logger.error(f"Erro ao verificar documentos indexados: {e}", exc_info=True)
        # Em caso de erro, assumir que documentos não estão indexados
        return {
            "all_indexed": False,
            "missing_documents": document_ids,
            "indexed_documents": [],
            "total_documents": len(document_ids),
            "error": str(e),
        }


def get_missing_documents_error_message(
    missing_docs: list[str], total_docs: int
) -> str:
    """
    Gera mensagem de erro detalhada para documentos não indexados.

    Args:
        missing_docs: Lista de IDs de documentos faltantes
        total_docs: Total de documentos verificados

    Returns:
        Mensagem de erro formatada
    """
    if not missing_docs:
        return "Todos os documentos estão indexados"

    missing_count = len(missing_docs)
    msg = " ⚠️ Aviso: Nem todos os documentos estão indexados no banco vetorial. "
    if missing_count:
        msg += f"Documentos faltantes: {', '.join(missing_docs)}. "
    else:
        msg += f"Primeiros documentos faltantes: {', '.join(missing_docs[:5])}... "

    msg += "É necessário indexar os documentos antes de usar o sistema RAG."

    return msg

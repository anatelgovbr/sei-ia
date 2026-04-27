"""chunks repository."""

import logging

from sei_ia.configs.logging_config import setup_logging

setup_logging()

logger = logging.getLogger(__name__)


def get_chunks_positions(document_chunks: dict) -> dict[int, list[tuple[int, int]]]:
    """Recupera as posições dos pedaços para a lista fornecida de ids de documento.

    Parâmetros:
        document_chunks (dict): Um dicionário mapeando cada id de documento a uma lista de posições dos pedaços,
        onde cada posição é representada por um dicionário com as chaves 'start_position' e 'finished_position'.
    Retorna:
        dict: Um dicionário mapeando cada id de documento a uma lista de tuplas (start_position, finished_position).
    """
    logger.debug("Entrou em get_chunks_positions")
    dict_document_chunks = {}
    for id_documento, chunks in document_chunks.items():
        dict_document_chunks[id_documento] = [
            {"inicio": v["start_position"], "fim": v["finished_position"]}
            for v in chunks
        ]

    logger.debug("Finalizou o get_chunks_positions")
    return dict_document_chunks

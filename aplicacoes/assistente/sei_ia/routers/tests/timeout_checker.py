""" "Rota de testes para timeout."""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from sei_ia.configs.logging_config import setup_logging

setup_logging()

ENDPOINT_NAME = "/tests/timeout/{timeout}"
logger = logging.getLogger(__name__)
router = APIRouter()


async def simulated_timeout(timeout: int) -> dict:
    """Funcao assincrona para simular timeout."""
    for i in range(timeout):
        if (i % 10) == 0:
            logger.debug(f"{i}/{timeout}")
        await asyncio.sleep(1)
    return {"message": "Operação concluída com sucesso sem erro de timeout."}


@router.post(
    ENDPOINT_NAME,
    tags=["tests"],
    summary="Modelo de testes de timeout",
)
async def tests(timeout: int = 600) -> JSONResponse:
    """Endpoint para testar o timeout.

    Args:
        timeout (int): Tempo de espera em segundos antes de retornar a resposta.

    Raises:
        HTTPException: Em caso de timeout ou erro durante a execução.

    Returns:
        dict: Mensagem de sucesso.
    """
    logger.info(f"Iniciando espera de {timeout} segundos para simulação de timeout.")
    response = await simulated_timeout(timeout)
    logger.info("Operação concluída com sucesso após o timeout.")
    return JSONResponse(content=response, status_code=200)

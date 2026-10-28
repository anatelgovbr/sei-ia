"""Validadores."""

import inspect
import logging

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import ChatRequest
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException400,
    HTTPException403,
    HTTPException422,
)

setup_logging()

logger = logging.getLogger(__name__)


def has_id_process(request: ChatRequest, intent_selector_code: str) -> bool:
    """Verifica se o id_procedimentos está corretamente preenchido.

    Cada id_procedimento deve ter um valor não vazio e cada lista id_documentos
    deve conter documentos não vazios.
    """
    logger.debug("Verificando se possui id_procedimento")
    if not request.id_procedimentos:
        raise HTTPException422(
            detail="Bad Request - id_procedimentos não pode ser vazio"
            f" para a intenção {intent_selector_code}."
        )
    for procedimento in request.id_procedimentos:
        if not procedimento.id_procedimento:
            raise HTTPException422(
                detail="Bad Request - id_procedimento não pode ser vazio"
                f" para a intenção {intent_selector_code}."
            )
        if not procedimento.id_documentos or any(
            not doc for doc in procedimento.id_documentos
        ):
            raise HTTPException422(
                detail="Bad Request - id_documentos não pode ser vazio"
                f" para a intenção {intent_selector_code}."
            )
    return True


def validate_proc_reference(
    request: ChatRequest,
) -> None:
    """Seleciona a intenção do prompt do usuário para documentos.

    Args:
        request (CompletationRequest2):
            Objeto contendo os dados da solicitação.
    """
    logger.debug(inspect.currentframe().f_code.co_name)

    if len(request.all_procs_allowed()) > 1:
        raise HTTPException403(
            detail=f"{inspect.currentframe().f_code.co_name}: Bad Request - Menção a mais de um processo não "
            f"permitido."
        )
    if len(request.all_documents_allowed()) == 0:
        raise HTTPException400(
            detail=f"{inspect.currentframe().f_code.co_name}: Bad Request - Menção a processo sem documentos "
            f"permitidos."
        )

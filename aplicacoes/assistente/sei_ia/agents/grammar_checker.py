"""Modulo usado para gerar prompt de correcao textual."""

import logging
import re

from sei_ia.agents.prompts.completation import (
    COMPLETATION_WITH_DOC_INSTRUCTION,
    INTERMEDIATE_COMPLETATION_WITH_DOC,
)
from sei_ia.agents.prompts.system import SYSTEM_MESSAGE_TEXT_CORRECTOR
from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.etl.extract.doc_content import get_doc_from_id
from sei_ia.data.pydantic_models import ChatRequest, UserState
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException404,
    HTTPException409,
    HTTPException411DocumentTimeout,
    HTTPException412SeiApiTimeout,
    HTTPException415,
    HTTPException500,
)

setup_logging()

logger = logging.getLogger(__name__)


async def get_documents(
    request: ChatRequest,
    *,
    docs_paged: list,
) -> dict:
    """Concatena todos os documentos em um dicionario de forma assíncrona.

    Args:
        request: Request com documentos
        docs_paged: lista de documentos e respectivas paginações

    Returns:
        Dicionário contendo a chave do documento e o conteúdo
    """
    documents = {}
    id_documentos = request.all_documents_allowed()
    for id_documento in id_documentos:
        try:
            doc, id_documento_formatado = await get_doc_from_id(
                id_documento, docs_paged
            )
            documents[id_documento_formatado] = doc
        except (HTTPException411DocumentTimeout, HTTPException412SeiApiTimeout) as exc:
            logger.exception(f"Timeout no documento {id_documento}: {exc.detail}")
            raise exc
        except (
            HTTPException404,
            HTTPException204,
            HTTPException500,
            HTTPException415,
            HTTPException409,
        ) as exc:
            logger.exception(f"Error: {exc.detail}, id_documento: {id_documento}")
            raise exc from exc
    return documents


async def make_prompt_with_doc_grammar_correction(user_state: UserState) -> UserState:
    """Gera um prompt para correção ortográfica de documentos, sem alterar estilo ou síntese.

    Args:
        user_state (UserState): Dados do usuário.

    Returns:
        UserState: Estado do usuário atualizado com o prompt.
    """
    content_documents = ""
    for item_proc in user_state["id_procedimentos"]:
        match = re.search(r"Número do Processo: (.+)", item_proc.metadata or "")
        protocolo_processo = match.group(1).strip() if match else ""
        for item_doc in item_proc.id_documentos:
            # Agora item_doc é um objeto (ItemDocumentRequest)
            doc_prompt = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
                id_documento_formatado=item_doc.id_documento_formatado,
                protocolo_processo=protocolo_processo,
                doc=item_doc.content,
            )
            content_documents += doc_prompt

    # Instrução extra para reforçar o objetivo da correção e tradução multilíngue
    extra_instruction = (
        "\nATENÇÃO: Corrija erros ortográficos e de pontuação do texto do usuário e dos documentos. "
        "Quando solicitado, realize tradução entre quaisquer idiomas conforme especificado pelo usuário. "
        "Não altere desnecessariamente o estilo, a originalidade ou a síntese do texto, exceto quando necessário para tradução."
    )

    last_prompt = COMPLETATION_WITH_DOC_INSTRUCTION.format(
        instruction=SYSTEM_MESSAGE_TEXT_CORRECTOR + extra_instruction,
        text=user_state["user_request"],
        conteudo_documentos=content_documents,
    )
    user_state["last_prompt"] = last_prompt
    return user_state

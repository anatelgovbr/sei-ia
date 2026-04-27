"""Modulo de prompt com documentos."""

import inspect
import logging

from openai import APITimeoutError, RateLimitError

from sei_ia.agents.prompts.completation import COMPLETATION_WITH_DOC
from sei_ia.agents.summarize.summarize import (
    SummaryOverallState,
    select_summarize_model,
    split_text_summarize,
)
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException408,
    HTTPException413,
)

setup_logging()

logger = logging.getLogger(__name__)


async def make_prompt_with_doc_summarization(user_state: UserState) -> UserState:
    """Funcao de busca paginada de documentos e sumarizacao.

    caso documento for muito grande.

    Args:
        user_state (UserState): Estado do usuário contendo informações de contexto e requisição.

    Raises:
        HTTPException: 413, detail="Tamanho do contexto excede o limite para realizar resumos."

    Returns:
        UserState: Objeto contendo os após a execução da função.

    A paginação dos documentos é definida pelo payload da requisição,
    usando os campos pag_doc_init e pag_doc_end em cada item de id_documentos.
            - outros carácteres aceitos como separadores para as páginas são
                "-", "/" ou "|"

    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")
    all_docs_content = ""
    for item_id_procedimento in user_state["id_procedimentos"]:
        for item_id_documento in item_id_procedimento.id_documentos:
            if item_id_documento.content:
                meta = getattr(item_id_documento, "metadata", "") or ""
                if meta:
                    all_docs_content += meta + "\n"
                all_docs_content += item_id_documento.content
    limit_summarize = (
        settings.SUMMARIZE_TOKENS_LIMIT_MULTIPLIER * user_state["general_max_ctx_len"]
    )
    if user_state["all_tokens_counter"] < user_state["general_max_ctx_len"]:
        logger.debug("Documento nao é necessario sumarizar")
        last_prompt = COMPLETATION_WITH_DOC.format(
            text=user_state["user_request"], conteudo_documentos=all_docs_content
        )
    elif user_state["all_tokens_counter"] < limit_summarize:
        logger.debug("Documento é necessario sumarizar")
        user_state["doc_summarized"] = True
        chunks, _ = split_text_summarize(all_docs_content)
        content_chunks = {"contents": [d.page_content for d in chunks]}
        summarize_chain = select_summarize_model(user_state)
        try:
            output: SummaryOverallState = summarize_chain.invoke(content_chunks)
        except (RateLimitError, APITimeoutError) as exc:
            logger.exception(f"Erro na sumarizacao: {exc.message}")
            raise HTTPException408 from exc

        last_prompt = COMPLETATION_WITH_DOC.format(
            text=user_state["user_request"],
            conteudo_documentos=output["collapsed_summaries"],
        )

    else:
        raise HTTPException413(
            detail=f"Tamanho do contexto excedido ({user_state['all_tokens_counter']} tokens) - não é possível realizar resumos."
        )
    user_state["last_prompt"] = last_prompt
    user_state["doc_summarized"] = True
    logger.debug(f">> saiu de {inspect.currentframe().f_code.co_name}")
    return user_state

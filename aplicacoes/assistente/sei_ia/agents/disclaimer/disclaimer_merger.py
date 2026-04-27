"""Node otimizado para preparação do disclaimer ANTES de generate_response."""

import inspect
import logging

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState

setup_logging()
logger = logging.getLogger(__name__)


async def prepare_disclaimer_for_response(state: UserState) -> dict:
    """Node de convergência que prepara o disclaimer para ser adicionado na resposta.

    Este node executa após a convergência (fan-in) do classify_disclaimer_need
    e ANTES de generate_response. Ele prepara o texto do disclaimer que será
    adicionado no começo da resposta pelo generate_response.

    Args:
        state: Estado do usuário contendo disclaimer_case

    Returns:
        Dict com o campo 'disclaimer_text' contendo o disclaimer preparado (ou None)
    """
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    disclaimer_case = state.get("disclaimer_case")
    disclaimer_text = None

    # Verifica se deve preparar disclaimer
    disclaimer_case_condition = disclaimer_case in (
        "orientacao_sobre_uso_do_sei",
        "totalidade_do_sei",
        "fora_do_escopo_tecnologico",
    )

    if disclaimer_case_condition:
        disclaimer_introduction = "⚠️ **Atenção:** "

        if disclaimer_case == "fora_do_escopo_tecnologico":
            disclaimer_content = (
                "O assistente do SEI IA não processa "
                "arquivos de áudio, de vídeo ou de imagem, e tampouco "
                "extrai caracteres por meio de OCR. Portanto, a "
                "resposta a seguir pode conter imprecisão."
            )
            disclaimer_text = disclaimer_introduction + disclaimer_content + "\n\n"

        else:
            # Verificar se há documentos no contexto
            has_no_documents = (
                state["id_procedimentos"] is None or len(state["id_procedimentos"]) == 0
            )

            if has_no_documents or state["id_procedimentos"] is None:
                if disclaimer_case == "orientacao_sobre_uso_do_sei":
                    disclaimer_content = (
                        "O assistente do SEI IA não ensina o uso do "
                        "SEI. Portanto, a resposta a seguir pode conter "
                        "imprecisão."
                    )

                elif disclaimer_case == "totalidade_do_sei":
                    disclaimer_content = (
                        "A funcionalidade de responder a "
                        "solicitações relacionadas ao SEI como um todo ainda "
                        "não foi implementada. Portanto, a resposta a seguir "
                        "pode conter imprecisão."
                    )
                else:
                    disclaimer_content = None

                if disclaimer_content:
                    disclaimer_text = (
                        disclaimer_introduction + disclaimer_content + "\n\n"
                    )

    logger.debug(
        f">> saindo de {inspect.currentframe().f_code.co_name} com disclaimer_text={'definido' if disclaimer_text else 'None'}"
    )

    # Retorna apenas o campo modificado
    return {"disclaimer_text": disclaimer_text}

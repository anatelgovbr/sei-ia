"""modulo de memoria em conversacoes."""

import contextlib
import inspect
import logging

import pandas as pd
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_stream_writer

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.database.sei_client import consulta_historico_topico_com_tokens

setup_logging()
logger = logging.getLogger(__name__)


def summarize_history_batches(
    dataframe: pd.DataFrame, model, max_limit_tokens: int
) -> tuple[str, str]:
    """
    Resume o histórico de mensagens de forma iterativa, garantindo que
    o texto final nunca ultrapasse max_limit_tokens, mantendo a ordem cronológica.
    """
    system_prompt = (
        "Você recebe múltiplos pares de Pergunta e Resposta.\n"
        "Cada Pergunta deve aparecer exatamente como está, incluindo a data no início (campo pergunta_data).\n"
        "Imediatamente abaixo de cada pergunta, apresente um resumo da resposta correspondente.\n"
        "Preserve estritamente a ordem original.\n"
    )

    # Ordena do mais antigo para o mais recente
    df = dataframe.sort_values(by="dth_cadastro", ascending=True)
    df["pergunta_data"] = df["dth_cadastro"].astype(str) + ": " + df["pergunta"]

    accumulated = []
    tokens_accum = 0
    type_choiced_summary = "full history"
    for _, row in df.iterrows():
        fragment = f"{row['pergunta_data']}\n{row['resposta']}"
        tokens = int(row["total_tokens"])

        accumulated.append(fragment)
        tokens_accum += tokens

        if tokens_accum > max_limit_tokens:
            batch_text = "\n\n".join(accumulated)
            resp = model.invoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=batch_text)]
            )
            summarized_text = resp.content.strip()

            accumulated = [summarized_text]
            tokens_accum = len(summarized_text.split())
            type_choiced_summary = "summarized"
    while tokens_accum > max_limit_tokens:
        type_choiced_summary = "summarized"
        batch_text = "\n\n".join(accumulated)
        logger.debug(
            f">> {inspect.currentframe().f_code.co_name}: "
            f"tokens_accum={tokens_accum} > max_limit_tokens={max_limit_tokens}, "
            "fazendo nova iteração de resumo."
        )
        resp = model.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=batch_text)]
        )
        summarized_text = resp.content.strip()
        accumulated = [summarized_text]
        tokens_accum = len(summarized_text.split())

    return "\n\n".join(accumulated), type_choiced_summary


def get_interacao_chat_by_topico_id_using_api(
    topico_id: str,
    model: BaseChatModel | None = None,
    max_tokens: int | None = settings.MEMORY_ITERATION_TOKENS_LIMIT,
    iter_limit: int | None = settings.MEMORY_ITERATION_LIMIT,
    summarize_history: bool = False,
) -> tuple[pd.DataFrame | str, str]:
    """Retrieves a session with associated memories based on the session ID.

    Parameters:
        topico_id (str): The ID of the session to retrieve.

    Returns:
        pd.DataFrame: DataFrame com interações filtradas por tokens e limite de iterações.
    """

    type_choiced_summary = "full history"
    logger.debug(f">> entrou em {inspect.currentframe().f_code.co_name}")

    _stream_writer = None
    with contextlib.suppress(Exception):
        _stream_writer = get_stream_writer()
        _stream_writer({"_status": "Recuperando mensagens anteriores do tópico"})

    def _emit_end():
        if _stream_writer is not None:
            with contextlib.suppress(Exception):
                _stream_writer({"_status": "Mensagens anteriores recuperadas"})

    dataframe = consulta_historico_topico_com_tokens(id_topico=topico_id)
    # O adapter mapeia tópico sem histórico (404 da API) para DataFrame vazio em
    # vez de levantar, então o sinal "empty history" vem de dataframe.empty —
    # não de uma exceção. Colunas espelham o que o adapter devolve.
    if dataframe.empty:
        _emit_end()
        return pd.DataFrame(
            columns=["pergunta", "resposta", "dth_cadastro", "total_tokens"]
        ), "empty history"

    # Ordena de forma decrescente para iniciar pelas mais recentes
    if summarize_history and dataframe["total_tokens"].sum() >= max_tokens:
        # Se for para usar o histórico resumido, retorna o DataFrame já filtrado
        text, type_choiced_summary = summarize_history_batches(
            dataframe, model=model, max_limit_tokens=max_tokens
        )
        _emit_end()
        return text, type_choiced_summary

    # Ordena de forma decrescente para iniciar pelas mais recentes
    df_rescentes = dataframe.sort_values(by="dth_cadastro", ascending=False)
    if iter_limit is not None:
        # Mantém as iterações mais recentes
        df_rescentes = df_rescentes.head(iter_limit)
    df_rescentes["tokens_acumulados"] = df_rescentes["total_tokens"].cumsum()
    df_filtrado = df_rescentes[df_rescentes["tokens_acumulados"] <= max_tokens].drop(
        columns="tokens_acumulados"
    )
    # Reordena para ordem cronológica dos diálogos
    df_filtrado = df_filtrado.sort_values(by="dth_cadastro", ascending=True)
    df_filtrado["pergunta_data"] = (
        df_filtrado["dth_cadastro"].astype(str) + ": " + df_filtrado["pergunta"]
    )
    if df_filtrado.shape[0] < df_rescentes.shape[0]:
        type_choiced_summary = "truncate"
    _emit_end()
    return df_filtrado, type_choiced_summary

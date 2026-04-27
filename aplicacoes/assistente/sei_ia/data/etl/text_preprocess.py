"""Processamento de textos."""

import logging
import re

import pandas as pd
import tiktoken

from sei_ia.data.etl.html_to_md.html_to_txtmd import HtmlTxtmd

logger = logging.getLogger(__name__)

encoder = tiktoken.get_encoding("o200k_base")


def html_to_markdown(html: str) -> str:
    """Converte HTML de documentos SEI para Markdown usando HtmlTxtmd.

    Args:
        html: Conteúdo HTML do documento SEI.

    Returns:
        Texto convertido para Markdown.
    """
    try:
        html_txtmd = HtmlTxtmd()
        html_txtmd.processa(html)
        return html_txtmd.output
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Erro na conversão de HTML para Markdown. [{exc!s}]")
        return f"Erro na conversão de HTML para Markdown. [{exc!s}]"


def process_html_to_markdown(df: pd.DataFrame) -> pd.DataFrame:
    """Processa e converte HTML em Markdown no DataFrame.

    Args:
        df: DataFrame com coluna 'HTML'.

    Returns:
        DataFrame com coluna 'TEXTO_LIMPO' e sem a coluna 'HTML'.
    """
    df["TEXTO_LIMPO"] = df["HTML"].apply(
        lambda x: html_to_markdown(x) if isinstance(x, str) and x.strip() else ""
    )
    return df.drop(columns=["HTML"])


def remove_multiple_spaces(row: str) -> str:
    """Remove espaços múltiplos, quebras de linha redundantes e espaços nas bordas.

    Args:
        row: Dicionário/linha com chave 'TEXTO_LIMPO'.

    Returns:
        Linha com texto limpo.
    """
    text = row["TEXTO_LIMPO"]
    text = re.sub(r"[^\S\r\n]{2,}", " ", text)
    text = re.sub(r"(\r?\n\s*)+\r?\n", "\n\n", text)
    text = text.strip()
    row["TEXTO_LIMPO"] = text
    return row


def split_by_sections(text: str) -> dict:
    """Divide texto em seções baseado em cabeçalhos Markdown com negrito.

    Args:
        text: Texto em formato Markdown.

    Returns:
        Dicionário com nome da seção como chave e lista de linhas como valor.
    """
    padrao_quebra = r"# \*\*(.*?)\*\*"
    if text[:2] != "**":
        text = "# **INICIO**" + text
    secoes = re.split(padrao_quebra, text)
    secoes = [secao.strip() for secao in secoes if secao.strip()]
    dicionario_secoes = {}
    for i in range(0, len(secoes), 2):
        chave = secoes[i]
        valor = secoes[i + 1] if i + 1 < len(secoes) else ""
        dicionario_secoes[chave] = [x for x in valor.splitlines() if x != ""]
    return dicionario_secoes


def pre_processamento_pdf(text: str) -> str:
    """Pré-processa texto extraído de PDF: remove espaços duplos e quebras desnecessárias.

    Args:
        text: Texto de entrada.

    Returns:
        Texto pré-processado.
    """
    text = re.sub(r"[ ]{2,}", " ", text.strip())
    return re.sub(r"[ \n]{2,}", "\n", text)


def get_file_extension(filename: str) -> str:
    """Extrai a extensão do arquivo a partir do nome.

    Args:
        filename: Nome do arquivo.

    Returns:
        Extensão em minúsculas, ou 'html' se não houver extensão.
    """
    parts = filename.split(".")
    return parts[-1].lower() if len(parts) > 1 else "html"

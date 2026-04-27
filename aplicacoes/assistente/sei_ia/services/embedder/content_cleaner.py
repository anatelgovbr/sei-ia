"""Módulo para limpeza de conteúdo de documentos antes da indexação."""

import logging
import re

from sei_ia.configs.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def clean_document_content(content: str) -> str:
    """
    Limpa o conteúdo do documento removendo caracteres problemáticos.

    Args:
        content: Conteúdo original do documento

    Returns:
        Conteúdo limpo e seguro para processamento
    """
    if not content:
        return ""

    # 1. Remover caracteres NUL (0x00) que causam erro no JSON
    content = content.replace("\x00", "")

    # 2. Remover outros caracteres de controle problemáticos (exceto quebras de linha)
    content = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]", "", content)

    # 3. Normalizar quebras de linha
    content = re.sub(r"\r\n", "\n", content)  # Windows -> Unix
    content = re.sub(r"\r", "\n", content)  # Mac -> Unix

    # 4. Remover múltiplas quebras de linha consecutivas
    content = re.sub(r"\n{3,}", "\n\n", content)

    # 5. Remover espaços em excesso
    content = re.sub(r"[ \t]+", " ", content)  # Múltiplos espaços -> um espaço
    content = re.sub(r"[ \t]*\n[ \t]*", "\n", content)  # Espaços ao redor de quebras

    # 6. Trim geral
    content = content.strip()

    return content

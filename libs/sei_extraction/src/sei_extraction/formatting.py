"""Formatação de conteúdo de documento com anexos em blocos delimitados.

Move o formatador que vivia no fork ``sei_db_handlers`` do assistente para a lib
compartilhada, para o ``sei_api`` chamar sem duplicar.
"""

from __future__ import annotations

import re


def _sanitize_prompt_label(label: str) -> str:
    """Normaliza o rótulo do delimitador [] para não quebrar abertura/fechamento."""
    return re.sub(r"\s+", " ", str(label).replace("[", "(").replace("]", ")")).strip()


def _format_prompt_block(label: str, content: str | None) -> str:
    """Formata um bloco técnico com delimitadores ``[label] ... [/label]``."""
    safe_label = _sanitize_prompt_label(label)
    return f"[{safe_label}]\n{content or ''}\n[/{safe_label}]\n"


def format_email_with_attachments(
    content_doc: str | None,
    attachments: list[tuple[int, str, str | None]],
) -> str:
    """Monta conteúdo de e-mail com os anexos extraídos, cada um num bloco delimitado.

    Args:
        content_doc: corpo principal do e-mail.
        attachments: lista de ``(indice, nome_arquivo, texto_extraido)``.

    Returns:
        Texto com o corpo e cada anexo em blocos ``[label] ... [/label]``.
    """
    augmented = _format_prompt_block("conteudo_principal_do_email", content_doc)
    for idx, filename, anexo_text in attachments:
        augmented += _format_prompt_block(f"anexo_{idx} - {filename}", anexo_text)
    return augmented

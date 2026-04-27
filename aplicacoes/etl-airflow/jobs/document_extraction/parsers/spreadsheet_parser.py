"""Spreadsheet parser using python-calamine (API direta, sem engine pandas)."""

import logging

import pandas as pd
from python_calamine import CalamineWorkbook

logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    """Extrai todas as planilhas de um arquivo de planilha.

    Suporta: XLSX, XLS, XLSB, XLSM, ODS via CalamineWorkbook (API direta).

    Usa CalamineWorkbook.from_path + sheet.to_python() em vez de
    pd.ExcelFile(engine="calamine"), que requer registro de entry point
    no pandas e nao funciona com python-calamine >= 0.4.x.

    Fluxo:
    1. Abre o arquivo com CalamineWorkbook.from_path
    2. Itera por todas as abas/planilhas do arquivo
    3. Para cada aba, converte para lista de linhas via to_python()
    4. Monta DataFrame (primeira linha como header)
    5. Limita a 100 colunas para evitar planilhas malformadas
    6. Converte cada aba para formato Markdown
    7. Concatena todas as abas com identificacao
    8. Retorna o texto completo em Markdown

    Args:
        file_path: Caminho para o arquivo de planilha.

    Returns:
        Todas as planilhas concatenadas em formato Markdown.

    Raises:
        Exception: Para erros de processamento de planilha.
    """
    logger.debug(f"Extracting text from spreadsheet: {file_path}")

    try:
        markdown_sheets = []

        with CalamineWorkbook.from_path(file_path) as wb:
            for sheet_num, sheet_name in enumerate(wb.sheet_names):
                sheet = wb.get_sheet_by_index(sheet_num)
                rows = sheet.to_python()

                logger.debug(f"Sheet {sheet_name} loaded. Rows: {len(rows)}")

                if not rows:
                    continue

                headers = [str(c) for c in rows[0]]
                data = rows[1:]

                df_sheet = pd.DataFrame(data, columns=headers)

                max_columns = 100
                if df_sheet.shape[1] > max_columns:
                    logger.warning(
                        f"Sheet {sheet_name} has {df_sheet.shape[1]} columns. Limiting to {max_columns}."
                    )
                    df_sheet = df_sheet.iloc[:, :max_columns]

                markdown_text = df_sheet.to_markdown(index=False)
                formatted_sheet = (
                    f"\n\nSheet {sheet_num + 1}: {sheet_name}\n{markdown_text}"
                )
                markdown_sheets.append(formatted_sheet)

        return "\n\n".join(markdown_sheets)

    except Exception as e:
        logger.exception(f"Error extracting text from spreadsheet {file_path}")
        msg = f"Failed to extract spreadsheet content: {e}"
        raise Exception(msg) from e

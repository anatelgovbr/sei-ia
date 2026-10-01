"""Spreadsheet parser using CalamineWorkbook.from_path (not pandas ExcelFile)."""

from __future__ import annotations

import logging
from typing import Optional

from sei_extraction.config import ExtractionConfig
from sei_extraction.exceptions import SpreadsheetExtractionError

logger = logging.getLogger(__name__)

_MAX_COLUMNS = 100


def extract_spreadsheet(
    file_path: str,
    config: ExtractionConfig,
    start_sheet: Optional[int] = None,
    end_sheet: Optional[int] = None,
) -> str:
    try:
        import pandas as pd
        from python_calamine import CalamineWorkbook

        output_sheets = []

        with CalamineWorkbook.from_path(file_path) as wb:
            sheet_names = wb.sheet_names
            total = len(sheet_names)

            start_idx = (start_sheet - 1) if start_sheet else 0
            end_idx = end_sheet if end_sheet and end_sheet <= total else total

            max_sheets = config.max_sheets_to_process
            if max_sheets is not None and (end_idx - start_idx) > max_sheets:
                logger.warning(
                    "Sheet count (%d) exceeds max_sheets_to_process (%d). Truncating.",
                    end_idx - start_idx,
                    max_sheets,
                )
                end_idx = start_idx + max_sheets

            for sheet_num in range(start_idx, end_idx):
                sheet_name = sheet_names[sheet_num]
                sheet = wb.get_sheet_by_index(sheet_num)
                rows = sheet.to_python()

                logger.debug("Sheet %s loaded. Rows: %d", sheet_name, len(rows))

                if not rows:
                    continue

                headers = [str(c) for c in rows[0]]
                data = rows[1:]

                df = pd.DataFrame(data, columns=headers)
                original_rows = df.shape[0]

                if df.shape[1] > _MAX_COLUMNS:
                    logger.warning(
                        "Sheet %s has %d columns. Limiting to %d.",
                        sheet_name,
                        df.shape[1],
                        _MAX_COLUMNS,
                    )
                    df = df.iloc[:, :_MAX_COLUMNS]

                max_rows = config.max_rows_per_sheet
                truncated = False
                if max_rows is not None and df.shape[0] > max_rows:
                    logger.warning(
                        "Sheet %s has %d rows. Limiting to %d.",
                        sheet_name,
                        original_rows,
                        max_rows,
                    )
                    df = df.head(max_rows)
                    truncated = True

                truncation_note = (
                    f" [Truncado: mostrando {max_rows} de {original_rows} linhas]"
                    if truncated
                    else ""
                )

                if config.spreadsheet_format == "csv":
                    body = df.to_csv(index=False)
                else:
                    body = df.to_markdown(index=False)

                formatted = (
                    f"\n\nSheet {sheet_num + 1}: {sheet_name}{truncation_note}\n{body}"
                )
                output_sheets.append(formatted)

        return "\n\n".join(output_sheets)

    except SpreadsheetExtractionError:
        raise
    except Exception as exc:
        logger.exception("Erro ao extrair planilha %s", file_path)
        raise SpreadsheetExtractionError(
            f"Erro ao extrair conteúdo da planilha {file_path}: {exc}"
        ) from exc

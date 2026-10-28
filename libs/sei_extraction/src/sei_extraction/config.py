"""ExtractionConfig: frozen dataclass holding all extraction tunables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class ExtractionConfig:
    ocr_enabled: bool = True
    ocr_min_text_threshold: int = 50
    ocr_dpi: int = 150
    ocr_max_concurrent_pages: int = 10
    ocr_model: str = "nano"
    spreadsheet_format: Literal["csv", "markdown"] = "csv"
    max_rows_per_sheet: Optional[int] = 1000
    max_sheets_to_process: Optional[int] = 10

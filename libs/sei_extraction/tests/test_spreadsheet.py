"""Tests for parsers/spreadsheet.py."""

from __future__ import annotations


from sei_extraction.config import ExtractionConfig
from sei_extraction.parsers.spreadsheet import extract_spreadsheet


def test_csv_format(xlsx_path):
    config = ExtractionConfig(
        spreadsheet_format="csv", max_rows_per_sheet=None, max_sheets_to_process=None
    )
    result = extract_spreadsheet(xlsx_path, config)
    assert "Sheet1" in result or "Sheet 1" in result or "1:" in result
    assert "A" in result
    assert "1" in result


def test_markdown_format(xlsx_path):
    config = ExtractionConfig(
        spreadsheet_format="markdown",
        max_rows_per_sheet=None,
        max_sheets_to_process=None,
    )
    result = extract_spreadsheet(xlsx_path, config)
    assert "|" in result, "Markdown format should produce pipe-separated tables"


def test_row_limit_respected(xlsx_path):
    config = ExtractionConfig(
        spreadsheet_format="csv", max_rows_per_sheet=2, max_sheets_to_process=None
    )
    result = extract_spreadsheet(xlsx_path, config)
    assert "Truncado" in result or result.count("\n") < 10


def test_sheet_limit_respected(xlsx_path):
    config = ExtractionConfig(
        spreadsheet_format="csv", max_rows_per_sheet=None, max_sheets_to_process=1
    )
    result = extract_spreadsheet(xlsx_path, config)
    assert "Sheet2" not in result


def test_none_limits_means_unlimited(xlsx_path):
    config = ExtractionConfig(
        spreadsheet_format="csv", max_rows_per_sheet=None, max_sheets_to_process=None
    )
    result = extract_spreadsheet(xlsx_path, config)
    assert "Sheet1" in result or "1:" in result
    assert "Sheet2" in result or "2:" in result

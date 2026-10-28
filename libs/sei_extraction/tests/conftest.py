"""Fixtures that build tiny binary test artifacts in-memory."""

from __future__ import annotations


import pytest


@pytest.fixture(scope="session")
def native_pdf_path(tmp_path_factory):
    import fitz

    tmp = tmp_path_factory.mktemp("pdfs")
    path = str(tmp / "native.pdf")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Hello from native PDF text.")
    doc.save(path)
    doc.close()
    return path


@pytest.fixture(scope="session")
def xlsx_path(tmp_path_factory):
    import pandas as pd

    tmp = tmp_path_factory.mktemp("xlsx")
    path = str(tmp / "sample.xlsx")
    df1 = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})
    df2 = pd.DataFrame({"C": [10, 20], "D": ["foo", "bar"]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df1.to_excel(writer, sheet_name="Sheet1", index=False)
        df2.to_excel(writer, sheet_name="Sheet2", index=False)
    return path

"""API HTTP para conversão de PDF em markdown usando pymupdf4llm."""

import pymupdf
import pymupdf4llm
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

app = FastAPI(title="Marker — PDF to Markdown")


@app.get("/health")
def health() -> dict:
    """Retorna status do serviço."""
    return {"status": "ok"}


@app.post("/convert")
async def convert_pdf_upload(file: UploadFile = File(...)) -> JSONResponse:  # noqa: B008 # NOSONAR
    """Recebe um arquivo PDF via multipart e retorna o markdown."""
    content = await file.read()
    try:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            markdown = pymupdf4llm.to_markdown(doc)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Falha ao converter PDF: {exc}"
        ) from exc
    return JSONResponse({"markdown": markdown})

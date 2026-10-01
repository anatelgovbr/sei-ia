"""API HTTP para conversão de PDF em markdown usando pymupdf4llm."""

import io

import httpx
import pymupdf4llm
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
        with io.BytesIO(content) as buf:
            markdown = pymupdf4llm.to_markdown(buf)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Falha ao converter PDF: {exc}") from exc
    return JSONResponse({"markdown": markdown})


class ConvertUrlRequest(BaseModel):
    """Payload para conversão de PDF via URL."""

    url: str


@app.post("/convert-url")
async def convert_pdf_url(body: ConvertUrlRequest) -> JSONResponse:
    """Baixa um PDF a partir de uma URL e retorna o markdown."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:  # NOSONAR
            resp = await client.get(body.url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao baixar PDF: {exc}") from exc
    try:
        with io.BytesIO(resp.content) as buf:
            markdown = pymupdf4llm.to_markdown(buf)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Falha ao converter PDF: {exc}") from exc
    return JSONResponse({"markdown": markdown})

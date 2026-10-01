# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

WORKDIR /app

RUN --mount=type=cache,id=seiia-pip-python312,target=/root/.cache/pip,sharing=locked \
    pip install \
    pymupdf4llm==0.0.17 \
    fastapi==0.115.0 \
    "uvicorn[standard]==0.30.6" \
    httpx==0.27.0 \
    python-multipart==0.0.9

COPY ops/marker/server.py /app/server.py

EXPOSE 8082

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8082"]

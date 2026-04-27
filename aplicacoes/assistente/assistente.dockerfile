# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

FROM base AS builder

LABEL MAINTAINER="Time SEI IA"

WORKDIR /app


# Configurações do uv para build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv


RUN mkdir -p /app/logs
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        g++ build-essential libpoppler-cpp-dev pkg-config git curl \
        libmagic-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


# Copiar apenas arquivos de dependências primeiro (para cache)
COPY ./aplicacoes/assistente/pyproject.toml ./aplicacoes/assistente/uv.lock ./aplicacoes/assistente/README.md /app/


RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen


# Stage final
FROM base
WORKDIR /app

# Instalar dependências de runtime para unstructured e healthchecks
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libmagic1 \
        pandoc \
        libreoffice-writer-nogui \
        libreoffice-impress-nogui \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY ./aplicacoes/assistente /app

COPY --link --from=builder /app/.venv /app/.venv

# Configurações para runtime - impede que uv tente recriar o ambiente
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    UV_NO_SYNC=1

EXPOSE 8088

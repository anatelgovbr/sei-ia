# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# O container e descartavel: as dependencias entram no Python da imagem final.
# Isso elimina a copia entre stages de dezenas de milhares de arquivos do
# ambiente virtual local, que continua restrito ao desenvolvimento.
WORKDIR /app/aplicacoes/assistente

# Dependencias de runtime apenas. Os sdists atuais sao Python puro; se surgir
# uma extensao nativa que exija compilador, o build falha para tratarmos o
# pacote explicitamente, em vez de levar toolchain para a imagem.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libmagic1 \
        pandoc \
        libreoffice-writer-nogui \
        libreoffice-impress-nogui \
        ffmpeg

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

# Copiar apenas metadados preserva a camada pesada quando muda somente o codigo.
# Os pyprojects das libs mantem a topologia necessaria aos paths do lock.
COPY ./libs/sei_extraction/pyproject.toml /app/libs/sei_extraction/pyproject.toml
COPY ./libs/sei_api/pyproject.toml /app/libs/sei_api/pyproject.toml
COPY ./aplicacoes/assistente/pyproject.toml ./aplicacoes/assistente/uv.lock ./aplicacoes/assistente/README.md /app/aplicacoes/assistente/

# O export e derivado do lock, sem emitir o projeto/app nem as libs locais. O
# uv pip sync instala no Python da imagem, com hashes obrigatorios. O indice CPU
# e necessario para torch/torchvision; unsafe-best-match tambem considera o PyPI.
RUN --mount=type=cache,id=seiia-uv-python312,target=/root/.cache/uv,sharing=locked \
    uv export --quiet --directory /app/aplicacoes/assistente --frozen --no-dev \
      --no-emit-project --no-emit-package sei-api --no-emit-package sei-extraction \
      --output-file /tmp/requirements-assistente.txt \
    && uv pip sync --system --python /usr/local/bin/python \
      --strict --require-hashes \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      --index-strategy unsafe-best-match \
      /tmp/requirements-assistente.txt \
    && uv pip check --system --python /usr/local/bin/python \
    && rm -f /tmp/requirements-assistente.txt

# O codigo local nao e instalado como pacote editavel. O PYTHONPATH deixa as
# libs compartilhadas e a aplicacao disponiveis sem criar metadados por rebuild.
COPY ./libs /app/libs
COPY ./aplicacoes/assistente/sei_ia /app/aplicacoes/assistente/sei_ia
COPY LICENSE /app/aplicacoes/assistente/LICENSE

ENV PYTHONPATH="/app/aplicacoes/assistente:/app/libs/sei_extraction/src:/app/libs/sei_api/src"

# Smoke sem rede: prova imports da imagem final, inclusive das libs locais.
RUN --network=none python -c "import sei_ia, sei_api, sei_extraction; from sei_extraction.html_to_md import HtmlTxtmd"

EXPOSE 8088

LABEL MAINTAINER="Time SEI IA" \
    org.opencontainers.image.title="SEI IA Assistente"

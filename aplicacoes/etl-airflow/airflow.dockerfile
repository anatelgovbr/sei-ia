# syntax=docker/dockerfile:1.7

# ==============================================================================
# Stage 1: Builder - Instala todas as dependências Python
# ==============================================================================
FROM apache/airflow:2.9.3-python3.10 AS builder

USER root
ARG AIRFLOW_UID

# Instalar dependências do sistema necessárias para compilação
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential git vim openssh-client jq \
    libpoppler-cpp-dev pkg-config wget unzip libaio1 \
    g++ curl \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow
WORKDIR /home/airflow/app

# Copiar APENAS pyproject.toml primeiro (otimiza cache)
COPY --chown=airflow:root ./aplicacoes/etl-airflow/pyproject.toml /home/airflow/app/pyproject.toml
COPY --chown=airflow:root ./aplicacoes/etl-airflow/uv.lock /home/airflow/app/uv.lock

# Instalar PyTorch CPU-only ANTES das outras dependências
# Isso garante que docling e outras deps não puxem a versão com CUDA
RUN --mount=type=cache,target=/home/airflow/.cache/pip,uid=50000 \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Instalar dependências Python (torch já está instalado, não será baixado novamente)
RUN --mount=type=cache,target=/home/airflow/.cache/pip,uid=50000 \
    pip install --no-warn-script-location -e .

# ==============================================================================
# Stage 2: Runtime - Imagem final otimizada
# ==============================================================================
FROM apache/airflow:2.9.3-python3.10 AS runtime

USER root
ARG AIRFLOW_UID

# Instalar apenas dependências runtime (sem build-essential, gcc, etc)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
    git vim openssh-client jq \
    libpoppler-cpp-dev wget unzip libaio1 curl \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ARG GIT_TOKEN
ARG DB_SEIIA_HOST
ARG DB_SEIIA_USER
ARG DB_SEIIA_PWD
ARG DB_SEIIA_ASSISTENTE
ARG EMBEDDINGS_TABLE_NAME

# Criação do script askpass.sh no diretório raiz para que todas as autorizacoes do git sejam feitas com o token
RUN echo "#!/bin/sh" > /askpass.sh && \
    echo "echo \$GIT_TOKEN" >> /askpass.sh && \
    chmod +x /askpass.sh
ENV GIT_ASKPASS="/askpass.sh"

USER airflow
WORKDIR /home/airflow/app

# Copiar pacotes Python instalados do stage builder
COPY --from=builder --chown=airflow:root /home/airflow/.local /home/airflow/.local
COPY --from=builder --chown=airflow:root /home/airflow/app/pyproject.toml /home/airflow/app/pyproject.toml

# Copiar código da aplicação (esta layer muda frequentemente, mas não invalida cache das deps)
COPY --chown=airflow:root ./aplicacoes/etl-airflow/jobs /home/airflow/app/jobs
COPY --chown=airflow:root ./aplicacoes/etl-airflow/healthcheck /home/airflow/app/healthcheck

# Reinstalar em modo editável para criar os links (rápido, deps já instaladas)
USER airflow
RUN pip install --no-cache-dir --no-deps -e .

USER root
# Copiar DAGs para o diretório do Airflow
RUN cp -R /home/airflow/app/jobs/dags/dag_objects/* /opt/airflow/dags
RUN chown airflow -R /home/airflow

USER airflow

CMD ["tail", "-f", "/dev/null"]

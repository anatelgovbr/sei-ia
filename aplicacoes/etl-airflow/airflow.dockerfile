# syntax=docker/dockerfile:1.7

# A imagem oficial ja contem o Airflow e seu ambiente Python em
# /home/airflow/.local. Instalar as dependencias do projeto diretamente sobre
# essa base evita copiar e exportar a arvore inteira entre dois stages.
ARG AIRFLOW_VERSION=2.9.3
FROM apache/airflow:${AIRFLOW_VERSION}-python3.10 AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.8.11 /uv /bin/uv

USER airflow
WORKDIR /home/airflow/app

# Este e o ambiente da imagem oficial do Airflow. UV so instala nele os
# requisitos travados do projeto; nao cria nem altera um Python de sistema.
ENV VIRTUAL_ENV=/home/airflow/.local \
    UV_CACHE_DIR=/home/airflow/.cache/uv \
    UV_LINK_MODE=copy

# Metadados e lock mudam com menos frequencia que o codigo. Um hit nesta layer
# pula toda a instalacao; se ela invalidar, o mount reaproveita os wheels locais.
COPY --chown=airflow:root ./aplicacoes/etl-airflow/pyproject.toml /home/airflow/app/pyproject.toml
COPY --chown=airflow:root ./aplicacoes/etl-airflow/uv.lock /home/airflow/app/uv.lock
RUN /bin/uv export --quiet --directory /home/airflow/app --frozen --no-dev \
      --no-emit-project --no-emit-package sei-extraction --no-emit-package sei-api \
      --output-file /tmp/requirements-airflow.txt

RUN --mount=type=cache,id=seiia-uv-airflow-python310-v1,target=/home/airflow/.cache/uv,sharing=locked,uid=50000,gid=0,mode=0770 \
    /bin/uv pip install --python "${VIRTUAL_ENV}/bin/python" \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      --index-strategy unsafe-best-match \
      -r /tmp/requirements-airflow.txt

# As libs e o projeto sao codigo Python puro. O PYTHONPATH os torna importaveis
# sem reinstalar pacotes locais a cada alteracao de fonte.
ENV PYTHONPATH="/home/airflow/app:/home/airflow/libs/sei_extraction/src:/home/airflow/libs/sei_api/src"
COPY --chown=airflow:root ./libs/sei_extraction /home/airflow/libs/sei_extraction
COPY --chown=airflow:root ./libs/sei_api /home/airflow/libs/sei_api
COPY --chown=airflow:root ./aplicacoes/etl-airflow/jobs /home/airflow/app/jobs
COPY --chown=airflow:root ./aplicacoes/etl-airflow/healthcheck /home/airflow/app/healthcheck
COPY --chown=airflow:root LICENSE /home/airflow/app/LICENSE
COPY --chown=airflow:root ./aplicacoes/etl-airflow/jobs/dags/dag_objects/ /opt/airflow/dags/

RUN PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=test \
    EMBEDDING_BASE_MODEL=smoke-test \
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=sqlite:////tmp/airflow-build-smoke.db \
    _AIRFLOW_WWW_USER_PASSWORD=build-smoke-only \
    python -c "import airflow, jobs, sei_api, sei_extraction; from sei_extraction.html_to_md import HtmlTxtmd" \
    && /bin/uv pip check --python "${VIRTUAL_ENV}/bin/python"

CMD ["tail", "-f", "/dev/null"]

LABEL org.opencontainers.image.title="SEI IA ETL Airflow"

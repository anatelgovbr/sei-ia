# syntax=docker/dockerfile:1.7

# A imagem oficial ja contem o Airflow e seu ambiente Python em
# /home/airflow/.local. Instalar as dependencias do projeto diretamente sobre
# essa base evita copiar e exportar a arvore inteira entre dois stages.
ARG AIRFLOW_VERSION=2.9.3
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12 AS runtime

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
# A base traz o provider common-sql 1.14.2 (SQL injection, corrigido na 1.24.1). Sobe so ele,
# na versao travada no extra airflow do lock, sem trazer o core do Airflow junto.
RUN /bin/uv export --quiet --directory /home/airflow/app --frozen --no-dev \
      --no-emit-project --no-emit-package sei-extraction --no-emit-package sei-api \
      --output-file /tmp/requirements-airflow.txt \
    && /bin/uv export --quiet --directory /home/airflow/app --frozen --no-dev --extra airflow \
      --no-emit-project --no-emit-package sei-extraction --no-emit-package sei-api \
    | awk '/^apache-airflow-providers-common-sql==/{p=1} p{print} p&&!/\\$/{p=0}' \
      >> /tmp/requirements-airflow.txt \
    && grep -q '^apache-airflow-providers-common-sql==' /tmp/requirements-airflow.txt

# O ETL nao usa os providers Google Cloud e Snowflake da imagem base. Eles e suas
# dependencias exclusivas travam protobuf, filelock e setuptools abaixo das
# versoes sem vulnerabilidade do lock, entao saem da imagem antes da instalacao.
RUN /bin/uv pip freeze --python "${VIRTUAL_ENV}/bin/python" | cut -d= -f1 \
    | grep -E '^(apache-airflow-providers-(google|snowflake)|gcsfs|gcloud-aio-.+|google-(ads|analytics-admin|api-core|api-python-client|auth-oauthlib|cloud-.+|crc32c|resumable-media)|grpc-google-iam-v1|grpc-interceptor|grpcio-gcp|grpcio-status|json-merge-patch|looker-sdk|pandas-gbq|db-dtypes|proto-plus|pydata-google-auth|snowflake-.+|sqlalchemy-(bigquery|spanner)|uritemplate)$' \
    | xargs /bin/uv pip uninstall --python "${VIRTUAL_ENV}/bin/python"

# O ETL tambem nao usa os providers Amazon, Microsoft Azure, Kubernetes, MySQL, SFTP/SSH
# e gRPC, nem o pyarrow, o pyopenssl e o uv da base (o uv do projeto vem de /bin/uv). Seus
# clientes (redshift-connector, azure-*, kiota, asyncssh, mysql-connector-python, httplib2...)
# e as dependencias que so eles puxam trazem versoes vulneraveis sem correcao compativel
# com o Airflow 2.9.3, entao saem da imagem. Os providers que o proprio apache-airflow
# exige (common-io, common-sql, fab, ftp, http, imap, smtp, sqlite) ficam.
RUN /bin/uv pip freeze --python "${VIRTUAL_ENV}/bin/python" | cut -d= -f1 \
    | grep -E '^(apache-airflow-providers-(amazon|cncf-kubernetes|grpc|microsoft-azure|mysql|sftp|ssh)|adal|adlfs|aiofiles|asn1crypto|asyncssh|azure-.+|bcrypt|boto3|cachetools|google-auth|google-auth-httplib2|httplib2|ijson|isodate|jsonpath-ng|kubernetes|kubernetes-asyncio|microsoft-kiota-.+|msal|msal-extensions|msgraph-core|msrest|msrestazure|mysql-connector-python|mysqlclient|oauthlib|paramiko|ply|portalocker|pyarrow|pyathena|pynacl|pyopenssl|pyparsing|redshift-connector|requests-oauthlib|rsa|s3transfer|scramp|sqlalchemy-redshift|sshtunnel|std-uritemplate|uv|watchtower|websocket-client)$' \
    | xargs /bin/uv pip uninstall --python "${VIRTUAL_ENV}/bin/python"

RUN --mount=type=cache,id=seiia-uv-airflow-python312-v1,target=/home/airflow/.cache/uv,sharing=locked,uid=50000,gid=0,mode=0770 \
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

# O pip check cobre tambem os pacotes da imagem base e e estrito: qualquer
# conflito derruba o build.
RUN PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=test \
    EMBEDDING_BASE_MODEL=smoke-test \
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=sqlite:////tmp/airflow-build-smoke.db \
    _AIRFLOW_WWW_USER_PASSWORD=build-smoke-only \
    python -c "import airflow, jobs, sei_api, sei_extraction; from sei_extraction.html_to_md import HtmlTxtmd" \
    && /bin/uv pip check --python "${VIRTUAL_ENV}/bin/python"

CMD ["tail", "-f", "/dev/null"]

LABEL org.opencontainers.image.title="SEI IA ETL Airflow"

# syntax=docker/dockerfile:1.7

FROM registry.access.redhat.com/ubi8/ubi:latest

COPY --from=ghcr.io/astral-sh/uv:0.8.11 /uv /bin/uv

LABEL maintainer="Time SEI IA <seiia@anatel.gov.br>"

ARG NB_USER="seisimi"
ARG NB_UID="4000"
ARG NB_GID="4000"

ENV UV_CACHE_DIR=/tmp/uv-cache \
    UV_LINK_MODE=copy

USER root

RUN --mount=type=cache,target=/var/cache/dnf,sharing=locked \
    dnf -y update \
    && rm -rf /etc/localtime \
    && ln -s /usr/share/zoneinfo/America/Sao_Paulo /etc/localtime \
    && dnf -y install bzip2 git openssl curl ca-certificates fontconfig gzip tar \
    ca-certificates \
    sudo \
    wget

ENV SHELL=/bin/bash \
    NB_USER="${NB_USER}" \
    NB_UID=${NB_UID} \
    NB_GID=${NB_GID} \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8

ENV HOME="/home/${NB_USER}"

RUN sed -i 's/^#force_color_prompt=yes/force_color_prompt=yes/' /etc/skel/.bashrc

COPY aplicacoes/etl-airflow/fix-permissions /usr/local/bin/fix-permissions
RUN chmod a+rx /usr/local/bin/fix-permissions

RUN echo "auth requisite pam_deny.so" >> /etc/pam.d/su && \
    sed -i.bak -e 's/^%admin/#%admin/' /etc/sudoers && \
    sed -i.bak -e 's/^%sudo/#%sudo/' /etc/sudoers && \
    useradd -l -m -s /bin/bash -N -u "${NB_UID}" "${NB_USER}" && \
    groupadd -g ${NB_GID} ${NB_USER} && \
    groupmod --gid $NB_GID $NB_USER \
    && usermod --uid $NB_UID --gid $NB_GID $NB_USER \
    && usermod -aG $NB_UID $NB_USER \
    && chown -R $NB_UID:$NB_GID /home/$NB_USER && \
    chmod g+w /etc/passwd && \
    fix-permissions "${HOME}"

RUN mkdir "/home/${NB_USER}/work" && \
    fix-permissions "/home/${NB_USER}"

ARG PYTHON_VERSION=3.10.18

USER ${NB_USER}

ENV VIRTUAL_ENV="/home/${NB_USER}/.venv" \
    UV_PYTHON_INSTALL_DIR="/home/${NB_USER}/.local/share/uv/python" \
    PATH="/home/${NB_USER}/.venv/bin:$PATH"

WORKDIR /home/${NB_USER}/app

# O UV instala um CPython exato no home do usuario e cria um virtualenv
# isolado. Nenhum comando escreve no Python do UBI.
RUN --mount=type=cache,id=seiia-uv-uid4000-python310-v1,target=/tmp/uv-cache,sharing=locked,uid=4000,gid=4000,mode=0770 \
    /bin/uv python install "${PYTHON_VERSION}" \
    && /bin/uv venv --python "${PYTHON_VERSION}" "${VIRTUAL_ENV}"

COPY --chown=${NB_UID}:${NB_GID} ./aplicacoes/etl-airflow/pyproject.toml /home/${NB_USER}/app/pyproject.toml
COPY --chown=${NB_UID}:${NB_GID} ./aplicacoes/etl-airflow/uv.lock /home/${NB_USER}/app/uv.lock

# Exporta o lock com os extras usados pela API, sem emitir os pacotes locais.
RUN /bin/uv export --quiet --directory /home/${NB_USER}/app --frozen --no-dev \
      --extra etls --extra airflow \
      --no-emit-project --no-emit-package sei-extraction --no-emit-package sei-api \
      --output-file /tmp/requirements-api.txt

# O export fixa versoes e hashes; a estrategia permite buscar no PyPI
# dependencias que o indice do PyTorch tambem anuncia, mas nao hospeda.
RUN --mount=type=cache,id=seiia-uv-uid4000-python310-v1,target=/tmp/uv-cache,sharing=locked,uid=4000,gid=4000,mode=0770 \
    /bin/uv pip install --python "${VIRTUAL_ENV}/bin/python" \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      --index-strategy unsafe-best-match \
      -r /tmp/requirements-api.txt

COPY --chown=${NB_UID}:${NB_GID} ./libs/sei_extraction /home/${NB_USER}/libs/sei_extraction
COPY --chown=${NB_UID}:${NB_GID} ./libs/sei_api /home/${NB_USER}/libs/sei_api

RUN --mount=type=cache,id=seiia-uv-uid4000-python310-v1,target=/tmp/uv-cache,sharing=locked,uid=4000,gid=4000,mode=0770 \
    /bin/uv pip install --python "${VIRTUAL_ENV}/bin/python" \
      --no-deps -e "/home/${NB_USER}/libs/sei_extraction[extract]" \
    && /bin/uv pip install --python "${VIRTUAL_ENV}/bin/python" \
      --no-deps -e "/home/${NB_USER}/libs/sei_api"

COPY --chown=${NB_UID}:${NB_GID} ./aplicacoes/etl-airflow/jobs /home/${NB_USER}/app/jobs
COPY --chown=${NB_UID}:${NB_GID} ./aplicacoes/etl-airflow/document_extraction /home/${NB_USER}/app/document_extraction
COPY --chown=${NB_UID}:${NB_GID} LICENSE /home/${NB_USER}/app/LICENSE

RUN --mount=type=cache,id=seiia-uv-uid4000-python310-v1,target=/tmp/uv-cache,sharing=locked,uid=4000,gid=4000,mode=0770 \
    /bin/uv pip install --python "${VIRTUAL_ENV}/bin/python" \
      --no-deps -e .

RUN /bin/uv pip check --python "${VIRTUAL_ENV}/bin/python" \
    && ENVIRONMENT=test \
      EMBEDDING_BASE_MODEL=smoke-test \
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=sqlite:////tmp/airflow-build-smoke.db \
      _AIRFLOW_WWW_USER_PASSWORD=build-smoke-only \
      python -c "import jobs, sei_api, sei_extraction; from sei_extraction.html_to_md import HtmlTxtmd"

USER root

# Área sem CACHE - layers colocadas deste ponto em diante nunca serão cacheados
ARG CACHEBUST=1

USER ${NB_USER}

CMD ["sleep", "infinity"]

LABEL org.opencontainers.image.title="SEI IA ETL Jobs API"

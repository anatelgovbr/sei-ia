# syntax=docker/dockerfile:1.7

FROM registry.access.redhat.com/ubi8/ubi:latest
LABEL maintainer="Time SEI IA <seiia@anatel.gov.br>"

COPY --from=ghcr.io/astral-sh/uv:0.8.11 /uv /bin/uv

ARG NB_USER="seisimi"
ARG NB_UID="4000"
ARG NB_GID="4000"

USER root

RUN --mount=type=cache,target=/var/cache/dnf,sharing=locked \
    dnf -y update \
    && rm -rf /etc/localtime \
    && ln -s /usr/share/zoneinfo/America/Sao_Paulo /etc/localtime \
    && dnf -y install bzip2 git curl ca-certificates fontconfig gzip tar unzip \
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

COPY aplicacoes/similaridade/fix-permissions /usr/local/bin/fix-permissions
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

WORKDIR /home/${NB_USER}/app

# O Python baixado pelo UV e o virtualenv pertencem ao usuario da aplicacao.
# Eles nunca alteram o Python do UBI. O cache e compartilhado com Jobs API,
# que usa o mesmo UID e a mesma versao exata de Python.
ENV VIRTUAL_ENV="/home/${NB_USER}/.venv" \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR="/home/${NB_USER}/.local/share/uv/python" \
    PATH="/home/${NB_USER}/.venv/bin:${PATH}"

RUN --mount=type=cache,id=seiia-uv-uid4000-python310-v1,target=/tmp/uv-cache,sharing=locked,uid=4000,gid=4000,mode=0770 \
    /bin/uv python install "${PYTHON_VERSION}" \
    && /bin/uv venv --python "${PYTHON_VERSION}" "${VIRTUAL_ENV}"

ENV OTEL_RESOURCE_ATTRIBUTES="service.name=api-sei"

COPY ./aplicacoes/similaridade/pyproject.toml /home/${NB_USER}/app/pyproject.toml
COPY ./aplicacoes/similaridade/uv.lock /home/${NB_USER}/app/uv.lock

RUN /bin/uv export --quiet --directory /home/${NB_USER}/app --frozen --no-dev --extra otel \
      --no-emit-project --no-emit-package sei-extraction --no-emit-package sei-api \
      --output-file /tmp/requirements-similaridade.txt

RUN --mount=type=cache,id=seiia-uv-uid4000-python310-v1,target=/tmp/uv-cache,sharing=locked,uid=4000,gid=4000,mode=0770 \
    /bin/uv pip install --python "${VIRTUAL_ENV}/bin/python" \
      -r /tmp/requirements-similaridade.txt

# sei-api e sei-extraction sao libs locais declaradas via [tool.uv.sources] (path editavel).
# O instalador recebe os paths antes do projeto, sem nova resolucao de dependencias.
# A ordem importa: sei-api depende de
# sei-extraction, entao sei_extraction tem de ser instalado primeiro.
COPY --chown=${NB_USER}:${NB_GID} ./libs/sei_extraction /home/${NB_USER}/libs/sei_extraction
COPY --chown=${NB_USER}:${NB_GID} ./libs/sei_api /home/${NB_USER}/libs/sei_api
RUN --mount=type=cache,id=seiia-uv-uid4000-python310-v1,target=/tmp/uv-cache,sharing=locked,uid=4000,gid=4000,mode=0770 \
    /bin/uv pip install --python "${VIRTUAL_ENV}/bin/python" \
      --no-deps -e "/home/${NB_USER}/libs/sei_extraction"
RUN --mount=type=cache,id=seiia-uv-uid4000-python310-v1,target=/tmp/uv-cache,sharing=locked,uid=4000,gid=4000,mode=0770 \
    /bin/uv pip install --python "${VIRTUAL_ENV}/bin/python" \
      --no-deps -e "/home/${NB_USER}/libs/sei_api"

USER root

COPY ./aplicacoes/similaridade /home/${NB_USER}/app
COPY LICENSE /home/${NB_USER}/app/LICENSE
RUN chown -R ${NB_USER}:${NB_GID} /home/${NB_USER}/app

USER ${NB_USER}
RUN --mount=type=cache,id=seiia-uv-uid4000-python310-v1,target=/tmp/uv-cache,sharing=locked,uid=4000,gid=4000,mode=0770 \
    /bin/uv pip install --python "${VIRTUAL_ENV}/bin/python" \
      --no-deps -e ".[otel]"
RUN /bin/uv pip check --python "${VIRTUAL_ENV}/bin/python" \
    && python -c "import api_sei.resources.lda, api_sei.utils, app_api, sei_api, sei_extraction"

ARG CACHEBUST=1

USER ${NB_USER}

CMD ["sleep", "infinity"]

LABEL org.opencontainers.image.title="SEI IA Similaridade"

# syntax=docker/dockerfile:1.7

FROM registry.access.redhat.com/ubi8/ubi:latest

LABEL Thiago Vieira <tpbvieira@anatel.gov.br>

ARG NB_USER="seisimi"
ARG NB_UID="4000"
ARG NB_GID="4000"
ARG GIT_TOKEN

ENV MICROMAMBA_ENV_PATH="/home/${NB_USER}/micromamba_env"
ENV MAMBA_ROOT_PREFIX=/opt/micromamba
ENV PIP_CACHE_DIR=/tmp/pip-cache

USER root

# Criação do script askpass.sh no diretório raiz para que todas as autorizacoes do git sejam feitas com o token
RUN echo "#!/bin/sh" > /askpass.sh && \
    echo "echo \$GIT_TOKEN" >> /askpass.sh && \
    chmod +x /askpass.sh
ENV GIT_ASKPASS="/askpass.sh"

RUN --mount=type=cache,target=/var/cache/dnf,sharing=locked \
    dnf -y update \
    && dnf clean all \
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

RUN curl -fsSL https://micromamba.snakepit.net/api/micromamba/linux-64/latest | tar -xvj -C /tmp
RUN mv /tmp/bin/micromamba /usr/local/bin/micromamba && chmod +x /usr/local/bin/micromamba
RUN . ~/.bashrc

ARG PYTHON_VERSION=3.10

RUN micromamba clean --locks
RUN micromamba create -y -p ${MICROMAMBA_ENV_PATH} -c conda-forge python=$PYTHON_VERSION
RUN chown -R ${NB_USER}:${NB_GID} ${MICROMAMBA_ENV_PATH}

### Instalar o mysql 
RUN --mount=type=cache,target=/var/cache/dnf,sharing=locked \
    curl -sSLO https://dev.mysql.com/get/mysql80-community-release-el7-11.noarch.rpm \
    && sudo rpm -ivh mysql80-community-release-el7-11.noarch.rpm \
    && yum -y install gcc python3-devel mysql-devel pkgconfig

USER ${NB_USER}

ENV PATH "/home/${NB_USER}/micromamba_env/bin:$PATH"

WORKDIR /home/${NB_USER}/app

RUN --mount=type=cache,target=/tmp/pip-cache,sharing=locked \
    eval "$(micromamba shell hook --shell=bash)" \
    && micromamba activate ${MICROMAMBA_ENV_PATH}  \
    && pip3 install --no-cache-dir mysqlclient

USER root

COPY --chown=${NB_UID}:${NB_GID} ./aplicacoes/etl-airflow/pyproject.toml /home/${NB_USER}/app/pyproject.toml
COPY --chown=${NB_UID}:${NB_GID} ./aplicacoes/etl-airflow/uv.lock /home/${NB_USER}/app/uv.lock

# Install dependencies from pyproject first so docs/README changes do not invalidate the heavy layer.
RUN --mount=type=cache,target=/tmp/pip-cache,sharing=locked \
    eval "$(micromamba shell hook --shell=bash)" \
    && micromamba activate ${MICROMAMBA_ENV_PATH}  \
    && pip3 install tomli \
    && python3 - <<'PY' > /tmp/requirements-api.txt
import pathlib
import tomli

project = tomli.loads(pathlib.Path("/home/seisimi/app/pyproject.toml").read_text())["project"]
requirements = []
seen = set()

for group in ("dependencies",):
    for requirement in project.get(group, []):
        if requirement not in seen:
            seen.add(requirement)
            requirements.append(requirement)

for extra in ("etls", "airflow"):
    for requirement in project["optional-dependencies"].get(extra, []):
        if requirement not in seen:
            seen.add(requirement)
            requirements.append(requirement)

print("\n".join(requirements))
PY

RUN --mount=type=cache,target=/tmp/pip-cache,sharing=locked \
    eval "$(micromamba shell hook --shell=bash)" \
    && micromamba activate ${MICROMAMBA_ENV_PATH}  \
    && pip3 install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip3 install --no-cache-dir -r /tmp/requirements-api.txt

COPY --chown=${NB_UID}:${NB_GID} ./aplicacoes/etl-airflow/jobs /home/${NB_USER}/app/jobs
COPY --chown=${NB_UID}:${NB_GID} ./aplicacoes/etl-airflow/document_extraction /home/${NB_USER}/app/document_extraction

RUN --mount=type=cache,target=/tmp/pip-cache,sharing=locked \
    eval "$(micromamba shell hook --shell=bash)" \
    && micromamba activate ${MICROMAMBA_ENV_PATH}  \
    && pip3 install --no-cache-dir --no-deps -e .
RUN chown -R ${NB_USER}:${NB_GID} /home/${NB_USER}/app

USER root

# Área sem CACHE - layers colocadas deste ponto em diante nunca serão cacheados
ARG CACHEBUST=1

RUN rm /askpass.sh

USER ${NB_USER}

ENV GIT_TOKEN=""

CMD ["sleep", "infinity"]

# syntax=docker/dockerfile:1.7

FROM registry.access.redhat.com/ubi8/ubi:latest
LABEL Thiago Vieira <tpbvieira@anatel.gov.br>

ARG NB_USER="seisimi"
ARG NB_UID="4000"
ARG NB_GID="4000"
ARG GIT_TOKEN
ARG LIB_CONNECTION
ENV LIB_CONNECTION=$LIB_CONNECTION

ENV MICROMAMBA_ENV_PATH="/home/${NB_USER}/micromamba_env"

RUN echo "#!/bin/sh" > /askpass.sh && \
    echo "echo \$GIT_TOKEN" >> /askpass.sh && \
    chmod +x /askpass.sh
ENV GIT_ASKPASS="/askpass.sh"

USER root

RUN --mount=type=cache,target=/var/cache/dnf,sharing=locked \
    dnf -y update \
    && dnf clean all \
    && rm -rf /etc/localtime \
    && ln -s /usr/share/zoneinfo/America/Sao_Paulo /etc/localtime \
    && dnf -y install bzip2 git openssl curl ca-certificates fontconfig gzip tar unzip libaio \
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

RUN curl -fsSL https://micromamba.snakepit.net/api/micromamba/linux-64/latest | tar -xvj -C /tmp
RUN mv /tmp/bin/micromamba /usr/local/bin/micromamba && chmod +x /usr/local/bin/micromamba

ARG PYTHON_VERSION=3.10

RUN micromamba create -y -p ${MICROMAMBA_ENV_PATH} -c conda-forge python=$PYTHON_VERSION
RUN chown -R ${NB_USER}:${NB_GID} /home/${NB_USER} 
USER ${NB_USER}

WORKDIR /home/${NB_USER}/app

RUN micromamba run -p ${MICROMAMBA_ENV_PATH} pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    micromamba run -p ${MICROMAMBA_ENV_PATH} pip3 install transformers==4.28.1 tqdm==4.65.0 numpy==1.26.4 scikit-learn==1.0.2 scipy==1.13.1 nltk==3.8.1 sentencepiece==0.1.98 && \
    micromamba run -p ${MICROMAMBA_ENV_PATH} pip3 install --no-deps sentence-transformers==2.2.2

ENV PATH "/home/${NB_USER}/.local/bin:$PATH"

ENV OTEL_RESOURCE_ATTRIBUTES="service.name=api-sei"

COPY ./aplicacoes/similaridade/pyproject.toml /home/${NB_USER}/app

RUN micromamba run -p ${MICROMAMBA_ENV_PATH} pip3 install -e ".[otel]" --user
RUN micromamba run -p ${MICROMAMBA_ENV_PATH} opentelemetry-bootstrap -a install

USER root

COPY ./aplicacoes/similaridade /home/${NB_USER}/app
RUN chown -R ${NB_USER}:${NB_GID} /home/${NB_USER}/app

USER ${NB_USER}
RUN echo 'eval "$(micromamba shell hook --shell=bash)" && \
    micromamba activate ${MICROMAMBA_ENV_PATH}' >> ~/.bashrc

### Instalação ORACLE
ENV ORACLE_HOME=/opt/oracle
ENV PATH=/opt/oracle:$PATH
ENV ORACLE_VERSION=19.24
ENV LD_LIBRARY_PATH=/opt/oracle:$LD_LIBRARY_PATH

USER root
RUN wget https://download.oracle.com/otn_software/linux/instantclient/instantclient-basic-linuxx64.zip -O /tmp/instantclient && \
    unzip /tmp/instantclient -d /tmp/oracle && \
    mkdir /opt/oracle && \
    cp -r /tmp/oracle/instantclient*/* /opt/oracle && \
    rm -rf /tmp/* && \
    echo 'export ORACLE_HOME=/opt/oracle' >> /home/${NB_USER}/.bashrc && \
    echo 'export PATH=$PATH:/opt/oracle' >> /home/${NB_USER}/.bashrc && \
    echo 'export ORACLE_VERSION=19.24' >> /home/${NB_USER}/.bashrc && \
    echo 'export LD_LIBRARY_PATH=/opt/oracle:$LD_LIBRARY_PATH' >> /home/${NB_USER}/.bashrc && \
    chown ${NB_USER} -R /opt/oracle

### Instalação SQL SERVER
RUN --mount=type=cache,target=/var/cache/dnf,sharing=locked \
    dnf -y update && \
    dnf -y install curl gnupg2

RUN curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /etc/pki/rpm-gpg/RPM-GPG-KEY-microsoft && \
    curl -o /etc/yum.repos.d/mssql-release.repo https://packages.microsoft.com/config/rhel/8/prod.repo

RUN --mount=type=cache,target=/var/cache/dnf,sharing=locked \
    dnf -y update && \
    ACCEPT_EULA=Y dnf install -y msodbcsql18 unixODBC-devel gcc-c++ && \
    dnf clean all

RUN eval "$(micromamba shell hook --shell=bash)" \
    && micromamba activate ${MICROMAMBA_ENV_PATH}  \
    && pip3 install pyodbc \
    && if [ -n "${LIB_CONNECTION}" ]; then pip3 install "${LIB_CONNECTION}"; fi

# Criar pasta de destino para certificados apenas no home
RUN mkdir -p /home/${NB_USER}/certificado

# Gerar certificados autoassinados se não existirem, apenas no diretório home
RUN if [ ! -f /home/${NB_USER}/certificado/seiia.cert.pem ] || [ ! -f /home/${NB_USER}/certificado/seiia.cert.key ]; then \
        openssl req -x509 -newkey rsa:4096 -keyout /home/${NB_USER}/certificado/seiia.cert.key -out /home/${NB_USER}/certificado/seiia.cert.pem -days 3650 -nodes -subj "/C=BR/ST=Estado/L=Cidade/O=Organizacao/OU=Unidade/CN=localhost"; \
    fi

# Garantir permissões corretas no diretório home
RUN chown -R ${NB_USER}:${NB_GID} /home/${NB_USER}/certificado

ARG CACHEBUST=1

USER ${NB_USER}

CMD "sleep infinity"

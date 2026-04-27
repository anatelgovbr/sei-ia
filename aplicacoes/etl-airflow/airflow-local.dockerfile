FROM apache/airflow:2.9.3-python3.10
USER root
ARG AIRFLOW_UID

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         build-essential git vim openssh-client jq \
         libpoppler-cpp-dev pkg-config wget unzip libaio1 \
         g++ git curl \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


ARG GIT_TOKEN
ARG DB_SEIIA_HOST
ARG DB_SEIIA_USER
ARG DB_SEIIA_PWD
ARG DB_SEIIA_ASSISTENTE
ARG DB_SEIIA_PORT_DESENV
ARG EMBEDDINGS_TABLE_NAME

# Criação do script askpass.sh no diretório raiz para que todas as autorizacoes do git sejam feitas com o token
RUN echo "#!/bin/sh" > /askpass.sh && \
    echo "echo \$GIT_TOKEN" >> /askpass.sh && \
    chmod +x /askpass.sh
ENV GIT_ASKPASS="/askpass.sh"

USER root
WORKDIR /home/airflow/app
COPY --chown=airflow:root ./jobs /home/airflow/app/jobs
COPY --chown=airflow:root ./pyproject.toml /home/airflow/app/pyproject.toml

USER airflow
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -e .[etls,airflow]

USER root
RUN cp -R /home/airflow/app/jobs/dags/dag_objects/* /opt/airflow/dags
RUN chown airflow -R /home/airflow
# Área sem CACHE - layers colocadas deste ponto em diante nunca serão cacheados
COPY ./healthcheck /home/airflow/app/jobs/healthcheck
ARG CACHEBUST=1

CMD ["tail", "-f", "/dev/null"]
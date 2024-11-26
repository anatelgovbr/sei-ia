ARG DOCKER_REGISTRY
ARG API_ASSISTENTE_VERSION

FROM ${DOCKER_REGISTRY:-}api_assistente:${API_ASSISTENTE_VERSION}

WORKDIR /opt/healthchecker

RUN pip install docker

CMD  ["python", "teste.py"]
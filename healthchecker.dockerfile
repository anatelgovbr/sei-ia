FROM anatelgovbr/api_assistente:0.3.1-RC

WORKDIR /opt/healthchecker

RUN pip install docker

CMD  ["python", "teste.py"]
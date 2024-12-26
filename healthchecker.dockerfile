FROM anatelgovbr/api_assistente:1.0.2

WORKDIR /opt/healthchecker

RUN pip install docker

CMD  ["python", "teste.py"]

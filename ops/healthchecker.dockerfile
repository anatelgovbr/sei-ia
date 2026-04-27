FROM anatelgovbr/api_assistente:0.3.1-RC

WORKDIR /opt/healthchecker

RUN pip install \
    docker \
    pandas \
    requests \
    SQLAlchemy \
    psycopg2-binary \
    python-dotenv \
    rich \
    urllib3 \
    tabulate

CMD ["python3", "teste.py"]

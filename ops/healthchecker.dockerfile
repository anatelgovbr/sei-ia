# syntax=docker/dockerfile:1.7
FROM python:3.10-slim-bookworm

WORKDIR /opt/healthchecker

COPY LICENSE /licenses/monorepo-GPL-3.0-or-later.txt
COPY ops/healthchecker-requirements.txt /tmp/healthchecker-requirements.txt

RUN --mount=type=cache,id=seiia-pip-python310,target=/root/.cache/pip,sharing=locked \
    pip install --requirement /tmp/healthchecker-requirements.txt

CMD ["python3", "teste.py"]

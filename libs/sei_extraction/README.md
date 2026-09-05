# sei_extraction

Biblioteca compartilhada de extração e tratamento de documentos do SEI, consumida pelos apps do monorepo (`assistente`, `etl-airflow`, `similaridade`). Existe para eliminar o fork por copy-paste do stack de extração entre os três apps.

Stage 1 (atual): motor `html_to_md` (HTML→Markdown), neutro, depende só de `beautifulsoup4`/`lxml`/`html5lib`.

## Piso de versão

Python 3.10 (os apps vão de 3.10 a 3.12). Toda a lib é escrita em sintaxe 3.10. Não pode depender de `langchain` (lint proíbe via ruff `banned-api`).

## Testes

    uv venv --python 3.10 .venv
    uv pip install -e ".[dev]"
    uv run pytest tests -v

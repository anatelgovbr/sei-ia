# sei_extraction

Biblioteca compartilhada de extração e tratamento de documentos do SEI, consumida pelos apps do monorepo (`assistente`, `etl-airflow`, `similaridade`). Existe para eliminar o fork por copy-paste do stack de extração entre os três apps.

Stage 1 (atual): motor `html_to_md` (HTML→Markdown), neutro, depende só de `beautifulsoup4`/`lxml`/`html5lib`.

## Extração HTML e Fallback

A função `html_to_markdown` (em `sei_extraction.text`) e o extrator `extract_html` (em `sei_extraction.parsers.office`) implementam extração resiliente com fallback:

1. **Parser primário**: `HtmlTxtmd`, que converte HTML de documentos SEI para Markdown estruturado.
2. **Fallback automático**: se o parser primário falhar (por exemplo, listas com estilos não suportados), o extrator recorre ao `BeautifulSoup` com o parser nativo `html.parser`, preservando o texto visível legível, quebras de parágrafos, listas e tabelas, e descartando tags de não-conteúdo (`head`, `script`, `style`, `noscript`, `template` e tags ignoradas).
3. **Tratamento de erros**: caso o fallback também falhe ou não extraia texto para uma entrada não vazia, uma exceção `OfficeExtractionError` (subclasse de `ExtractionError`) é propagada com chaining (`from`), garantindo que falhas de extração não sejam mascaradas como documentos válidos.

## Piso de versão

Python 3.10 (os apps vão de 3.10 a 3.12). Toda a lib é escrita em sintaxe 3.10. Não pode depender de `langchain` (lint proíbe via ruff `banned-api`).

## Testes

    uv venv --python 3.10 .venv
    uv pip install -e ".[dev]"
    uv run pytest tests -v

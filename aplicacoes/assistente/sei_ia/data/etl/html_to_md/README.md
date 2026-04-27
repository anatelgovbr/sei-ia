# html_to_md

Conversor de HTML (especialmente do editor SEI) para texto em formato Markdown customizado.


## Instalação

1. **Instale as dependências**

Você pode instalar todas as dependências de uma vez usando o arquivo `requirements.txt`:

```
pip install -r requirements.txt
```

Ou, se preferir, instale manualmente:

```
pip install beautifulsoup4 lxml html5lib pandas tiktoken
```

2. **Estrutura esperada**

O projeto espera os módulos internos em uma estrutura semelhante a:

```
html_to_txtmd.py
text_preprocess.py
html/
    bs4.py
    dom_preprocessor.py
    editor_sei.py
    table.py
    tag_types.py
    unicode.py
```

## Exemplo de Uso

```python
from html_to_txtmd import HtmlTxtmd

def html_to_markdown(html: str) -> str:
    try:
        html_txtmd = HtmlTxtmd()
        html_txtmd.processa(html)
        return html_txtmd.output
    except Exception as exc:
        print(f"Erro na conversão de HTML para Markdown. [{exc!s}]")
        return f"Erro na conversão de HTML para Markdown. [{exc!s}]"

# Exemplo
html = "<h1>Exemplo</h1><p>Texto <b>negrito</b></p>"
markdown = html_to_markdown(html)
print(markdown)
```

## Sobre a conversão

- O conversor trata HTML gerado pelo editor SEI, removendo tags desnecessárias, normalizando caracteres e convertendo para um Markdown adaptado.
- Utiliza BeautifulSoup com parser `lxml` (fallback para `html5lib`).
- Suporta listas, tabelas, cabeçalhos, blocos de código, sobrescritos/subscritos, imagens, links, entre outros.
- O Markdown gerado pode conter variações para melhor legibilidade, não sendo estritamente compatível com renderizadores Markdown padrão.

## Observações

- Para converter arquivos, basta ler o HTML como string e passar para `html_to_markdown`.
- Adapte o caminho dos imports conforme a estrutura do seu projeto.
- As dependências estão listadas em `requirements.txt` para facilitar a instalação.

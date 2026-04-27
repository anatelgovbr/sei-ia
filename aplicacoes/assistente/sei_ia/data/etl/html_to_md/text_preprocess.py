"""Processamento de textos."""

import logging
import re
import string
import warnings
from io import StringIO
from itertools import product

import pandas as pd
import tiktoken
from bs4 import BeautifulSoup

from sei_ia.data.etl.html_to_txtmd import HtmlTxtmd

logger = logging.getLogger(__name__)

encoder = tiktoken.get_encoding("o200k_base")


# Função alterada para utilizar HtmlTxtmd - 2026-03-05
def html_to_markdown(html: str) -> str:  # noqa: C901
    try:
        html_txtmd = HtmlTxtmd()
        html_txtmd.processa(html)
        return html_txtmd.output
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Erro na conversão de HTML para Markdown. [{exc!s}]")
        return f"Erro na conversão de HTML para Markdown. [{exc!s}]"


def int_to_roman(num: int) -> str:
    """Converte número inteiro para algarismo romano.

    Args:
        num: Número inteiro de 1 a 3999

    Returns:
        String com número romano
    """
    values = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    symbols = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]

    roman = ""
    for value, symbol in zip(values, symbols):  # noqa: B905
        while num >= value:
            roman += symbol
            num -= value
    return roman


ROMAN_NUMERALS = [int_to_roman(i) for i in range(1, 501)]  # I até CC
LETTERS = [
    "".join(c) for n in range(1, 3) for c in product(string.ascii_lowercase, repeat=n)
]


# Função para processar os filhos de um elemento HTML e converter para Markdown
def process_children(tag: str) -> str:
    """Função para proc os filhos de um elemento HTML e converter Markdown.

    Args:
        tag (_type_): _description_

    Returns:
        _type_: _description_
    """
    content = ""
    for child in tag.children:
        # Verificando se o filho é uma tag <br /> e substituindo por uma
        # quebra de linha no Markdown
        if child.name == "br":
            content += "\n"
        # Se o filho for uma string, simplesmente adicione ao conteúdo
        elif child.name is None:
            content += child.string
        # Para outras tags, obtenha seu texto
        else:
            content += child.get_text()
    return content


def process_item_nivel(markdown: str, element: str, counters: tuple | list) -> tuple:
    """Funcao de processamento de item nivel.

    Args:
        markdown (str): conteudo markdown ja formatado
        element (str): Elemento css
        counters (tuple|list): contadores

    Returns:
        tuple: markdown, counters
    """
    (
        level1_counter,
        level2_counter,
        level3_counter,
        level4_counter,
        paragrafo_num1_counter,
        paragrafo_num2_counter,
        paragrafo_num3_counter,
        paragrafo_num4_counter,
        roman_counter,
        letter_counter,
    ) = counters
    if "Item_Nivel1" in element.get("class"):
        level1_counter += 1
        (level2_counter, level3_counter, level4_counter, roman_counter) = (
            0,
            0,
            0,
            0,
        )
        markdown += f"# **{level1_counter}. {process_children(element).upper()}**\n\n"
    elif "Item_Nivel2" in element.get("class"):
        level2_counter += 1
        (level3_counter, level4_counter, roman_counter) = (0, 0, 0)
        markdown += (
            f"{level1_counter}.{level2_counter}. {process_children(element)}\n\n"
        )
    elif "Item_Nivel3" in element.get("class"):
        level3_counter += 1
        (level4_counter, roman_counter) = (0, 0)
        markdown += (
            f"{level1_counter}.{level2_counter}.{level3_counter}."
            f" {process_children(element)}\n\n"
        )
    elif "Item_Nivel4" in element.get("class"):
        level4_counter += 1
        (roman_counter) = 0
        markdown += (
            f"{level1_counter}.{level2_counter}."
            f"{level3_counter}.{level4_counter}. "
            f"{process_children(element)}\n\n"
        )
    counters = (
        level1_counter,
        level2_counter,
        level3_counter,
        level4_counter,
        paragrafo_num1_counter,
        paragrafo_num2_counter,
        paragrafo_num3_counter,
        paragrafo_num4_counter,
        roman_counter,
        letter_counter,
    )
    return markdown, counters


def process_pagragrafo_numerado(
    markdown: str, element: str, counters: tuple | list
) -> tuple:
    """Funcao de processamento de paragrafo numerado.

    Args:
        markdown (str): conteudo markdown ja formatado
        element (str): Elemento css
        counters (tuple): contadores

    Returns:
        tuple: markdown, counters
    """
    (
        level1_counter,
        level2_counter,
        level3_counter,
        level4_counter,
        paragrafo_num1_counter,
        paragrafo_num2_counter,
        paragrafo_num3_counter,
        paragrafo_num4_counter,
        roman_counter,
        letter_counter,
    ) = counters
    if "Paragrafo_Numerado_Nivel1" in element.get("class"):
        paragrafo_num1_counter += 1
        (
            paragrafo_num2_counter,
            paragrafo_num3_counter,
            paragrafo_num4_counter,
            roman_counter,
        ) = (0, 0, 0, 0)
        markdown += f"{paragrafo_num1_counter}. {process_children(element)}\n\n"
    elif "Paragrafo_Numerado_Nivel2" in element.get("class"):
        paragrafo_num2_counter += 1
        (paragrafo_num3_counter, paragrafo_num4_counter, roman_counter) = (0, 0, 0)
        markdown += (
            f"{paragrafo_num1_counter}.{paragrafo_num2_counter}."
            f" {process_children(element)}\n\n"
        )
    elif "Paragrafo_Numerado_Nivel3" in element.get("class"):
        paragrafo_num3_counter += 1
        (paragrafo_num4_counter, roman_counter) = (0, 0)
        markdown += (
            f"{paragrafo_num1_counter}.{paragrafo_num2_counter}."
            f"{paragrafo_num3_counter}."
            f" {process_children(element)}\n\n"
        )
    elif "Paragrafo_Numerado_Nivel4" in element.get("class"):
        paragrafo_num4_counter += 1
        (roman_counter) = 0
        markdown += (
            f"{paragrafo_num1_counter}.{paragrafo_num2_counter}."
            f"{paragrafo_num3_counter}.{paragrafo_num4_counter}."
            f" {process_children(element)}\n\n"
        )
    counters = (
        level1_counter,
        level2_counter,
        level3_counter,
        level4_counter,
        paragrafo_num1_counter,
        paragrafo_num2_counter,
        paragrafo_num3_counter,
        paragrafo_num4_counter,
        roman_counter,
        letter_counter,
    )
    return markdown, counters


def process_romanos(
    markdown: str,
    element: str,
    counters: tuple | list,
    roman_numerals: list,
) -> tuple:
    """Funcao de processamento de paragrafo numerado.

    Args:
        markdown (str): conteudo markdown ja formatado
        element (str): Elemento css
        counters (tuple): contadores
        roman_numerals (list): lista de algarismos romanos

    Returns:
        tuple: markdown, counters
    """
    (
        level1_counter,
        level2_counter,
        level3_counter,
        level4_counter,
        paragrafo_num1_counter,
        paragrafo_num2_counter,
        paragrafo_num3_counter,
        paragrafo_num4_counter,
        roman_counter,
        letter_counter,
    ) = counters
    if "Item_Inciso_Romano" in element.get("class"):
        roman_counter += 1
        roman_numeral = (
            roman_numerals[roman_counter - 1]
            if roman_counter <= len(roman_numerals)
            else str(roman_counter)
        )
        markdown += f"{roman_numeral} - {process_children(element)}\n\n"
    counters = (
        level1_counter,
        level2_counter,
        level3_counter,
        level4_counter,
        paragrafo_num1_counter,
        paragrafo_num2_counter,
        paragrafo_num3_counter,
        paragrafo_num4_counter,
        roman_counter,
        letter_counter,
    )
    return markdown, counters


def process_others(
    markdown: str, element: str, counters: tuple | list, letters: list
) -> tuple:
    """Funcao de processamento de paragrafo numerado.

    Args:
        markdown (str): conteudo markdown ja formatado
        element (str): Elemento css
        counters (tuple): contadores
        letters (list): lista de letras

    Returns:
        tuple: markdown, counters
    """
    (
        level1_counter,
        level2_counter,
        level3_counter,
        level4_counter,
        paragrafo_num1_counter,
        paragrafo_num2_counter,
        paragrafo_num3_counter,
        paragrafo_num4_counter,
        roman_counter,
        letter_counter,
    ) = counters
    if "Item_Alinea_Letra" in element.get("class"):
        letter_counter += 1
        letter = (
            letters[letter_counter - 1]
            if letter_counter <= len(letters)
            else chr(96 + letter_counter)
        )
        markdown += f"{letter}) {process_children(element)}\n\n"
    # Tratando parágrafos com classe de Citação
    elif "Citacao" in element.get("class"):
        markdown += f"```markdown\n{process_children(element)}\n```\n\n"
    # Tratando parágrafos com classes que força o texto em maiúsculo com
    # negrito
    elif any(
        cls in element.get("class")
        for cls in [
            "Texto_Centralizado_Maiusculas_Negrito",
            "Texto_Fundo_Cinza_Maiusculas_Negrito",
        ]
    ):
        markdown += f"**{process_children(element).upper()}**\n\n"
    # Tratando parágrafos com classes que força o texto em maiúsculo
    elif any(
        cls in element.get("class")
        for cls in [
            "Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc",
            "Texto_Centralizado_Maiusculas",
            "Texto_Justificado_Maiusculas",
        ]
    ):
        markdown += f"{process_children(element).upper()}\n\n"
    # Tratando parágrafos com classes que força o texto em negrito
    elif "Texto_Fundo_Cinza_Negrito" in element.get("class"):
        markdown += f"**{process_children(element)}**\n\n"
    else:
        markdown += process_children(element) + "\n\n"
    counters = (
        level1_counter,
        level2_counter,
        level3_counter,
        level4_counter,
        paragrafo_num1_counter,
        paragrafo_num2_counter,
        paragrafo_num3_counter,
        paragrafo_num4_counter,
        roman_counter,
        letter_counter,
    )
    return markdown, counters


def process_paragraph(  # noqa: C901, PLR0912, PLR0915
    element: any, counters: tuple, roman_numerals: list, letters: list
) -> str:
    """Função para processar parágrafos HTML e convertê-los em Markdown.

    aplicando formatações específicas com base nas classes CSS.

    Args:
        element (_type_): elementos
        counters (_type_): contadores
        roman_numerals (list): lista com numeros romanos
        letters (list): lista com letras

    Returns:
        str: String markdown
    """
    # Inicializando a string Markdown e contadores para formatação estruturada
    markdown = ""
    (
        level1_counter,
        level2_counter,
        level3_counter,
        level4_counter,
        paragrafo_num1_counter,
        paragrafo_num2_counter,
        paragrafo_num3_counter,
        paragrafo_num4_counter,
        roman_counter,
        letter_counter,
    ) = counters

    # Processamento para diferentes tipos de parágrafos com base nas
    # classes CSS
    paragraph_class = element.get("class")
    if paragraph_class:
        # Resetando o contador de 'Item_Alinea_Letra' conforme necessário
        if any(
            cls in paragraph_class
            for cls in [
                "Item_Nivel1",
                "Item_Nivel2",
                "Item_Nivel3",
                "Item_Nivel4",
                "Paragrafo_Numerado_Nivel1",
                "Paragrafo_Numerado_Nivel2",
                "Paragrafo_Numerado_Nivel3",
                "Paragrafo_Numerado_Nivel4",
                "Item_Inciso_Romano",
            ]
        ):
            letter_counter = 0

        # Tratando parágrafos com classes Item_Nivel1 a Item_Nivel4
        if "Item_Nivel1" in paragraph_class:
            level1_counter += 1
            (level2_counter, level3_counter, level4_counter, roman_counter) = (
                0,
                0,
                0,
                0,
            )
            markdown += (
                f"# **{level1_counter}. {process_children(element).upper()}**\n\n"
            )
        elif "Item_Nivel2" in paragraph_class:
            level2_counter += 1
            (level3_counter, level4_counter, roman_counter) = (0, 0, 0)
            markdown += (
                f"{level1_counter}.{level2_counter}. {process_children(element)}\n\n"
            )
        elif "Item_Nivel3" in paragraph_class:
            level3_counter += 1
            (level4_counter, roman_counter) = (0, 0)
            markdown += f"{level1_counter}.{level2_counter}.{level3_counter}. {process_children(element)}\n\n"
        elif "Item_Nivel4" in paragraph_class:
            level4_counter += 1
            (roman_counter) = 0
            markdown += (
                f"{level1_counter}.{level2_counter}.{level3_counter}"
                f".{level4_counter}. {process_children(element)}\n\n"
            )
        # Tratando parágrafos com classes Paragrafo_Numerado_Nivel1 a
        # Paragrafo_Numerado_Nivel4
        elif "Paragrafo_Numerado_Nivel1" in paragraph_class:
            paragrafo_num1_counter += 1
            (
                paragrafo_num2_counter,
                paragrafo_num3_counter,
                paragrafo_num4_counter,
                roman_counter,
            ) = (0, 0, 0, 0)
            markdown += f"{paragrafo_num1_counter}. {process_children(element)}\n\n"
        elif "Paragrafo_Numerado_Nivel2" in paragraph_class:
            paragrafo_num2_counter += 1
            (paragrafo_num3_counter, paragrafo_num4_counter, roman_counter) = (0, 0, 0)
            markdown += f"{paragrafo_num1_counter}.{paragrafo_num2_counter}. {process_children(element)}\n\n"
        elif "Paragrafo_Numerado_Nivel3" in paragraph_class:
            paragrafo_num3_counter += 1
            (paragrafo_num4_counter, roman_counter) = (0, 0)
            markdown += (
                f"{paragrafo_num1_counter}.{paragrafo_num2_counter}."
                f"{paragrafo_num3_counter}. {process_children(element)}\n\n"
            )
        elif "Paragrafo_Numerado_Nivel4" in paragraph_class:
            paragrafo_num4_counter += 1
            (roman_counter) = 0
            markdown += (
                f"{paragrafo_num1_counter}.{paragrafo_num2_counter}."
                f"{paragrafo_num3_counter}.{paragrafo_num4_counter}. {process_children(element)}\n\n"
            )
        # Tratamento de listas romano
        elif "Item_Inciso_Romano" in paragraph_class:
            roman_counter += 1
            roman_numeral = (
                roman_numerals[roman_counter - 1]
                if roman_counter <= len(roman_numerals)
                else str(roman_counter)
            )
            markdown += f"{roman_numeral} - {process_children(element)}\n\n"
        # Tratamento de listas alfabéticas
        elif "Item_Alinea_Letra" in paragraph_class:
            letter_counter += 1
            letter = (
                letters[letter_counter - 1]
                if letter_counter <= len(letters)
                else chr(96 + letter_counter)
            )
            markdown += f"{letter}) {process_children(element)}\n\n"
        # Tratando parágrafos com classe de Citação
        elif "Citacao" in paragraph_class:
            markdown += f"```markdown\n{process_children(element)}\n```\n\n"
        # Tratando parágrafos com classes que força o texto em maiúsculo com
        # negrito
        elif any(
            cls in paragraph_class
            for cls in [
                "Texto_Centralizado_Maiusculas_Negrito",
                "Texto_Fundo_Cinza_Maiusculas_Negrito",
            ]
        ):
            markdown += f"**{process_children(element).upper()}**\n\n"
        # Tratando parágrafos com classes que força o texto em maiúsculo
        elif any(
            cls in paragraph_class
            for cls in [
                "Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc",
                "Texto_Centralizado_Maiusculas",
                "Texto_Justificado_Maiusculas",
            ]
        ):
            markdown += f"{process_children(element).upper()}\n\n"
        # Tratando parágrafos com classes que força o texto em negrito
        elif "Texto_Fundo_Cinza_Negrito" in paragraph_class:
            markdown += f"**{process_children(element)}**\n\n"
        else:
            markdown += process_children(element) + "\n\n"
    else:
        markdown += process_children(element) + "\n\n"

    # Atualizando os contadores
    counters = [
        level1_counter,
        level2_counter,
        level3_counter,
        level4_counter,
        paragrafo_num1_counter,
        paragrafo_num2_counter,
        paragrafo_num3_counter,
        paragrafo_num4_counter,
        roman_counter,
        letter_counter,
    ]
    return markdown, counters


def process_table(element: str) -> str:
    """Definindo uma função para processar tabelas HTML para  Markdown."""
    # Verificando a existência de células mescladas
    if any(
        cell.has_attr("rowspan") or cell.has_attr("colspan")
        for cell in element.find_all(["th", "td"])
    ):
        return str(element)  # Retorna o HTML original da tabela
    markdown = ""
    rows = element.find_all("tr")
    for i, row in enumerate(rows):
        row_markdown = "|"
        for cell in row.find_all(["th", "td"]):
            cell_content = process_children(cell).strip()  # Processa
            # o conteúdo da célula
            if not cell_content:  # Substitui conteúdo vazio por espaço simples
                cell_content = " "
            row_markdown += f" {cell_content} |"
        markdown += row_markdown + "\n"
        # Adicionando a linha de separação após a primeira linha (cabeçalho)
        if i == 0:  # A primeira linha é tratada como cabeçalho
            markdown += "|---" * len(row.find_all(["th", "td"])) + "|\n"

    return markdown + "\n"


def replace_html_special_characters(html: str) -> str:
    """Substituições de caracteres especiais HTML por caracteres.

    apropriados ou strings vazias.

    Args:
        html (_type_): _description_

    Returns:
        _type_: _description_
    """
    return (
        html.replace("&nbsp;", " ")  # Espaço não quebrável
        .replace("&#8239;", " ")  # Espaço estreito não quebrável
        .replace("&#8203;", "")  # Zero width space
        .replace("&#64257;", "fi")  # Ligadura fi
        .replace("&shy;", "")
    )  # Soft hyphen


def remove_html_comments(html: str) -> str:
    """Função para remover comentários HTML.

    Args:
        html (_type_): _description_

    Returns:
        _type_: _description_
    """
    return re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)


def remove_specific_elements(html: str) -> str:
    """Função para remover diversos elementos HTML sem perder o conteúd.

    Args:
        html (_type_): _description_

    Returns:
        _type_: _description_
    """
    soup = BeautifulSoup(html, "html.parser")
    # Lista de tags para remover, mantendo o conteúdo interno
    tags_to_remove = ["span", "div", "main", "section", "blockquote", "center", "nav"]
    # Lógica para remover elementos com 'display: none', incluindo seu
    # conteúdo interno
    for element in soup.find_all(
        style=lambda value: value and "display: none" in value
    ):
        element.decompose()

    for tag in tags_to_remove:
        [match.unwrap() for match in soup.find_all(tag)]

    return soup


def html_to_markdown_antiga(html: str) -> str:  # noqa: C901
    """Função para converter conteúdo HTML em Markdown.

    Args:
        html (_type_): _description_

    Returns:
        _type_: _description_
    """
    try:
        html = replace_html_special_characters(html)
        html = remove_html_comments(html)
        soup = remove_specific_elements(html)
        markdown = ""
        counters = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

        for element in soup.body:
            # Convertendo cabeçalhos HTML (h1-h9) para Markdown
            if element.name in ["h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8", "h9"]:
                header_level = int(element.name[1])
                markdown += "#" * header_level + f" {element.get_text().strip()}\n\n"
            # Mantendo o HTML original para os elementos listados
            elif element.name in ["code", "pre"]:
                markdown += str(element)
            elif element.name == "p":
                paragraph_markdown, counters = process_paragraph(
                    element, counters, ROMAN_NUMERALS, LETTERS
                )
                markdown += paragraph_markdown
            elif element.name == "table":
                table_markdown = process_table(element)
                markdown += table_markdown
            elif element.name == "hr":
                markdown += "---\n"
            elif element.name == "ul":
                markdown += (
                    "\n".join(
                        [f"- {li.get_text().strip()}" for li in element.find_all("li")]
                    )
                    + "\n\n"
                )
            elif element.name == "ol":
                markdown += (
                    "\n".join(
                        [f"1. {li.get_text().strip()}" for li in element.find_all("li")]
                    )
                    + "\n\n"
                )
    except Exception:  # noqa: BLE001
        try:
            return remove_html_and_format_table(html)
        except Exception as exc:  # noqa: BLE001
            logger.debug(exc)
            return f"Erro na conversão de HTML para Markdown.{exc!s}"
    else:
        try:
            return remove_html_and_format_table(markdown)
        except Exception as exc:  # noqa: BLE001
            logger.debug(exc)
            return remove_html_tags(markdown)


def remove_multiple_spaces(row: str) -> str:
    """Remover espacos multiplos.

    Função para remover espaços múltiplos dentro de cada parágrafo, limpar
    quebras de linha com espaços,
    e remover espaços e quebras de linha no início e no final do conteúdo.

    Args:
        row (_type_): _description_

    Returns:
        _type_: _description_
    """
    text = row["TEXTO_LIMPO"]
    text = re.sub(r"[^\S\r\n]{2,}", " ", text)
    text = re.sub(r"(\r?\n\s*)+\r?\n", "\n\n", text)
    text = text.strip()
    row["TEXTO_LIMPO"] = text
    return row


def process_html_to_markdown(df: pd.DataFrame) -> pd.DataFrame:
    """Função para processar e converter HTML em Markdown no DataFrame.

    Args:
        df (_type_): _description_

    Returns:
        _type_: _description_
    """
    df["TEXTO_LIMPO"] = df["HTML"].apply(
        lambda x: html_to_markdown(x) if isinstance(x, str) and x.strip() else ""
    )
    return df.drop(columns=["HTML"])


def split_by_sections(text: str) -> dict:
    """Slit text por secoes.

    Args:
        text (str): _description_

    Returns:
        dict: _description_
    """
    padrao_quebra = r"# \*\*(.*?)\*\*"
    if text[:2] != "**":
        text = "# **INICIO**" + text
    secoes = re.split(padrao_quebra, text)
    secoes = [secao.strip() for secao in secoes if secao.strip()]
    dicionario_secoes = {}
    for i in range(0, len(secoes), 2):
        chave = secoes[i]
        valor = secoes[i + 1] if i + 1 < len(secoes) else ""
        dicionario_secoes[chave] = [x for x in valor.splitlines() if x != ""]
    return dicionario_secoes


def pre_processamento_pdf(text: str) -> str:
    """Funcao para preprocessamento de dados.

    remove espacos duplos e qubras de linha desnecessarios.

    Args:
        text (str): texto de entrada

    Returns:
        str: texto pre processado
    """
    text = re.sub(r"[ ]{2,}", " ", text.strip())
    return re.sub(r"[ \n]{2,}", "\n", text)


def remove_html_tags(text: str) -> str:
    """Remove HTML tags from a given text string.

    Args:
        text (str): The input text with HTML tags.

    Returns:
        str: The text without HTML tags.
    """
    return re.sub(r"<.*?>", "", text)


def remove_html_and_format_table(html_content: str) -> str:
    """Remove tags HTML e formata qualquer tabela em Markdown, sem perder informação.

    Extrai cada <table>, tenta ler diretamente com pandas e, se der warning/erro
    de “filename too long” ou FutureWarning, relê a tabela via StringIO.
    Então substitui o <table> pelo seu Markdown e retorna todo o texto limpo.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    for table in soup.find_all("table"):
        table_html = str(table)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                # Always use StringIO to avoid filename interpretation
                buffer = StringIO(table_html)
                df_table = pd.read_html(buffer)[0]

        except (ValueError, OSError) as e:
            logger.warning(f"Failed to parse table with pandas: {e}")
            # Fallback: return the original table HTML
            table.replace_with(f"\n{table_html}\n")
            continue

        table.replace_with(df_table.to_markdown(index=False))

    return soup.get_text()


def get_file_extension(filename: str) -> str:
    """Função auxiliar para extrair a extensão do arquivo.

    Args:
        filename (str): nome do arquivo
    """
    parts = filename.split(".")
    return parts[-1].lower() if len(parts) > 1 else "html"

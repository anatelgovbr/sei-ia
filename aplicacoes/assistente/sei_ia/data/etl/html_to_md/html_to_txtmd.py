import logging

from bs4.element import NavigableString

from .html.bs4 import BS
from .html.dom_preprocessor import DomPreprocessor
from .html.editor_sei import EditorSei
from .html.table import Table
from .html.tag_types import HtmlTagTypes
from .html.unicode import Normalize


class HtmlTxtmd:
    # Debug output identation
    IDENT = "  "

    def __init__(
        self,
        logger_name: str | None = None,
    ) -> None:
        self._logger_name = logger_name or self.__class__.__name__

        self._logger = logging.getLogger(self._logger_name)

        self._bs = BS()
        self._dom_preprocessor = DomPreprocessor()
        self._editor_sei = EditorSei()
        self._normalize = Normalize()
        self._table = Table()

        self._processa_tag = {
            "ol": self.process_ol,
            "ul": self.process_ul,
            "table": self.process_table,
            "hr!": self.process_hr,
            "pre": self.process_pre,
        }
        self._br_no_break_tags = {"h1", "h2", "h3", "h4", "h5", "h6", "table"}

    @property
    def output(self):
        output = "".join(self._outputs)
        self.new_outputs()
        output = self.pos_process_markdown(output)
        return output

    def new_outputs(self):
        self._outputs = []

    def processa(self, html: str):
        self.inicialize_dom(html)

        self.init_vars_navigate()
        # Inicia a navegação recursiva pelos elementos do DOM
        self.navigate_el(self._soup, self._counters, self._levels, self._outputs)

    def log_ident(self, levels):
        return f"{self.IDENT * levels['log_level']}"

    def debug(self, levels, mess: str):
        self._logger.debug(f"{self.log_ident(levels)}{mess}")

    def inicialize_dom(self, html):
        # Pré-processa texto de entrada
        html = self.tab_to_space(html)

        # Inicializa DOM
        self._soup = self._bs.inicialize(html)
        # self._logger.debug('html original parseado')
        # self._logger.debug(self._soup.prettify())

        self.pre_process_dom()

    def init_vars_navigate(self):
        self.new_outputs()

        self._counters = self._editor_sei.P_GLOBALS.copy()
        # valores de controle de níveis de recursão
        self._levels = {
            "ol_level": 1,
            "log_level": 0,
        }

    def tab_to_space(self, html: str):
        return html.replace("\t", " ")

    def pre_process_dom(self):
        self.remove_ignored_tags()
        self.remove_display_none()

        self._dom_preprocessor.normalize(self._soup)
        # self._logger.debug('DOM pré-processado')
        # self._logger.debug(self._soup.prettify())
        # self._logger.debug(f"[{self._soup.encode().decode()=}]")

    def remove_display_none(self):
        for element in list(self._soup.select("[style]")):
            if not element.attrs:
                continue
            style = element.attrs.get("style", "")
            if isinstance(style, (list, tuple)):
                style = " ".join(style)
            if "display:none" in "".join(style.split()).lower():
                element.decompose()

    def remove_ignored_tags(self):
        ignore = HtmlTagTypes.IGNORE

        for tag in list(self._soup.find_all(True)):
            name = tag.name
            if name and (name in ignore or ":" in name):
                tag.extract()

    def lista_titulo_interior(self, outputs):
        try:
            li_titulo, *li_interior = outputs
        except Exception:
            li_titulo, li_interior = "\n\n", []
        return li_titulo, li_interior

    def new_levels(self, levels, incrementing=None):
        result = levels.copy()
        if incrementing is None:
            incrementing = []
        incrementing.append("log_level")
        for level in incrementing:
            result[level] += 1
        return result

    def navigate_el(self, node, counters, levels, outputs):
        self.debug(levels, f"percorrer [{type(node)=}] [{node.name=}] [{levels=}]")
        for child_idx, child in enumerate(list(node.children)):
            self.debug(levels, f"child {child_idx} [{child.name=}]")

            if isinstance(child, NavigableString):  # texto puro
                self.debug(levels, f"NavigableString [{type(child)=}]")
                if child.strip():
                    self.outputs_append(outputs, child)
                continue

            if child.name in HtmlTagTypes.FLOW_CONTAINERS:
                self.debug(levels, "FLOW")

                tag = child.name
                # hr dentro de select é separador de opções, não linha horizontal
                if child.name == "hr" and node.name != "select":
                    tag = "hr!"

                if tag in self._processa_tag:
                    self._processa_tag[tag](child, counters, levels, outputs)
                else:
                    child_outputs = []
                    self.navigate_el(
                        child, counters, self.new_levels(levels), child_outputs
                    )
                    outputs.append("".join(child_outputs))
                continue

            if child.name == "p":
                self._editor_sei.set_log_ident(self.log_ident(levels))
                p_class = self._editor_sei.p_class_lambda(child, counters)
                markdown = self.navigate_phrasing(child, self.new_levels(levels))
                self.debug(levels, f"P [{p_class=}]")
                self.outputs_append(outputs, f"{p_class(markdown)}\n\n")
                continue

            elif child.name == "code":
                if BS.has_single_child(child, "pre"):
                    for pre in child.find_all("pre", recursive=False):
                        texto = pre.decode_contents()
                        texto = self.suffix_if_not(texto, "\n")
                        self.outputs_append(outputs, f"```\n{texto}```\n\n")
                    continue

            elif child.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                header_mark = "#" * int(child.name[-1])
                child_outputs = []
                self.navigate_el(
                    child, counters, self.new_levels(levels), child_outputs
                )
                child_strip = [
                    child_output.strip()
                    for child_output in child_outputs
                    if child_output.strip()
                ]
                markdown = " ¶ ".join(child_strip) if child_strip else " "
                self.outputs_append(outputs, f"{header_mark} {markdown}\n\n")
                continue

            markdown = self.navigate_phrasing(child, self.new_levels(levels))
            self.debug(levels, f"NOT FLOW NOT P... [{type(child)=}]")
            self.outputs_append(outputs, f"{markdown}")
            continue

        # self.logger.debug(f"{identtion}[{outputs=}]")

    def process_ol(self, child, counters, levels, outputs):
        ol_number = self._editor_sei.ol_number_lambda(child, levels["ol_level"])
        start = child.attrs.get("start", "1")
        for idx, li in enumerate(
            list(child.find_all("li", recursive=False)), start=int(start)
        ):
            self.debug(levels, f"li {idx} [{ol_number(1)=}]")

            child_outputs = ["\n\n"] if BS.is_first_child_not_p(li) else []
            child_levels = self.new_levels(levels, incrementing=["ol_level"])
            self.navigate_el(li, counters, child_levels, child_outputs)
            li_titulo, li_interior = self.lista_titulo_interior(child_outputs)

            self.outputs_append(outputs, f"{ol_number(idx)} {li_titulo}")
            for linha in li_interior:
                self.outputs_append(outputs, f"    {linha}")

    def process_ul(self, child, counters, levels, outputs):
        for idx, li in enumerate(list(child.find_all("li", recursive=False)), start=1):
            self.debug(levels, f"li {idx}")

            child_outputs = []
            self.navigate_el(li, counters, self.new_levels(levels), child_outputs)
            li_titulo, li_interior = self.lista_titulo_interior(child_outputs)

            self.outputs_append(outputs, f"- {li_titulo}")
            for linha in li_interior:
                self.outputs_append(outputs, f"    {linha}")

    def process_table(self, child, counters, levels, outputs):
        # Se tem:
        # - tabela aninhada
        # - tag "ol" aninhado
        # - tag "ul" aninhado
        # é considerado layout e converte células para "div".
        if (
            self.has_nested_table(child)
            # or self.has_p_sei(child)
            or self.has_nested_ol(child)
            or self.has_nested_ul(child)
        ):
            self.process_table_caption(child, counters, levels, outputs)
            divs = self._table.cells_to_divs(child)
            for div in divs:
                div_outputs = []
                self.navigate_el(div, counters, self.new_levels(levels), div_outputs)
                outputs.append("".join(div_outputs))
        else:
            self.process_table_caption(child, counters, levels, outputs)
            child = self._table.no_span(child)
            markdown = self.navigate_cells(child, counters, levels)
            self.outputs_append(outputs, f"{markdown}\n\n")

    def process_table_caption(self, table, counters, levels, outputs) -> str:
        caption = table.find("caption")
        if caption:
            output = self.navigate_phrasing(caption, self.new_levels(levels))
            self.outputs_append(outputs, f"{output}\n\n")

    def navigate_cells(self, table, counters, levels) -> str:
        row_list = []
        rows = list(table.find_all("tr"))
        col_count = 0
        for row_idx, row in enumerate(rows):
            cell_list = []
            for cell in list(row.find_all(["th", "td"])):
                if row_idx == 0:
                    col_count += 1
                cell_outputs = []
                self.navigate_el(cell, counters, self.new_levels(levels), cell_outputs)
                cell_strip = [
                    cell_output.strip()
                    for cell_output in cell_outputs
                    if cell_output.strip()
                ]
                cell_list.append(" ¶ ".join(cell_strip) if cell_strip else " ")
            row_list.append(f"|{'|'.join(cell_list)}|")
            if row_idx == 0:
                row_list.append(f"|{'---|' * col_count}")
        return "\n".join(row_list)

    def process_hr(self, child, counters, levels, outputs):
        self.outputs_append(outputs, "---\n\n")

    def process_pre(self, child, counters, levels, outputs):
        texto = child.decode_contents()
        texto = self.suffix_if_not(texto, "\n")
        self.outputs_append(outputs, f"```\n{texto}```\n\n")

    def has_nested_table(self, child) -> bool:
        nested_table = child.find("table")
        return nested_table and nested_table is not child

    def has_nested_ol(self, child) -> bool:
        return any(ol.find("ol") for ol in child.find_all("ol"))

    def has_nested_ul(self, child) -> bool:
        return any(ol.find("ul") for ol in child.find_all("ul"))

    def has_p_sei(self, child) -> bool:
        return bool(child.find("p", class_=self._editor_sei.P_SEI_CLASSES))

    def outputs_append(self, outputs, content):
        text = str(content)
        if text:
            outputs.append(text)

    def navigate_phrasing(self, node, levels):
        chunks = []
        for child in node:
            output = None
            if child.name in ["b", "strong"]:
                if self._bs.has_tag_children(child):
                    output = self.navigate_phrasing(child, self.new_levels(levels))
                else:
                    output = child.get_text()
                chunks.append(f"**{output}**")
            elif child.name in ["i", "em"]:
                if self._bs.has_tag_children(child):
                    output = self.navigate_phrasing(child, self.new_levels(levels))
                else:
                    output = child.get_text()
                chunks.append(f"_{output}_")
            elif child.name in ["s", "del", "strike"]:
                if self._bs.has_tag_children(child):
                    output = self.navigate_phrasing(child, self.new_levels(levels))
                else:
                    output = child.get_text()
                chunks.append(f"~~{output}~~")
            elif child.name == "code":
                output = child.get_text()
                chunks.append(f"`{output}`")
            elif child.name == "a":
                if self._bs.has_tag_children(child):
                    output = self.navigate_phrasing(child, self.new_levels(levels))
                else:
                    output = child.get_text()
                href = child.get("href")
                if href:
                    title = child.get("title")
                    if title:
                        title = f' "{title}"'
                    chunks.append(f"[{output}]({href}{title})")
                else:
                    chunks.append(output)
            elif child.name == "img":
                src = child.get("src")
                if not src or src.startswith("data:"):
                    src = "_"
                alt = child.get("alt")
                if not alt:
                    alt = ""
                title = child.get("title")
                title = f' "{title}"' if title else ""
                chunks.append(f"![{alt}]({src}{title})")
            elif child.name == "embed":
                src = child.get("src")
                if src:
                    chunks.append(f"[embed src: {src}]")
            elif child.name in ["picture", "audio", "video"]:
                if self._bs.has_tag_children(child):
                    output = self.navigate_phrasing(child, self.new_levels(levels))
                    chunks.append(output)
            elif child.name == "source":
                parent = BS.name_first_parent_in_list(
                    child, ["picture", "audio", "video"]
                )
                if parent == "picture" and self._bs.has_tag_children(child):
                    output = self.navigate_phrasing(child, self.new_levels(levels))
                    chunks.append(output)
                if parent in ["audio", "video"]:
                    src = child.get("src")
                    chunks.append(f"[{parent} source: {src}]")
                    if self._bs.has_tag_children(child):
                        output = self.navigate_phrasing(child, self.new_levels(levels))
                        chunks.append(output)
            elif child.name == "track":
                parent = BS.name_first_parent_in_list(child, ["audio", "video"])
                if parent:
                    src = child.get("src")
                    label = child.get("label")
                    if label:
                        label = f' "{label}"'
                    chunks.append(f"[{parent} track: {src}{label}]")
            elif child.name == "svg":
                chunks.append("[svg]")
            elif child.name == "br":
                if any(p.name in self._br_no_break_tags for p in child.parents):
                    chunks.append(" — ")
                else:
                    chunks.append("  \n")
            elif child.name in ["sup", "sub"]:
                if self._bs.has_tag_children(child):
                    output = self.navigate_phrasing(child, self.new_levels(levels))
                else:
                    output = child.get_text()
                left = self.left_attached(child)
                marker = "^" if child.name == "sup" else "_"
                chunks.append(
                    f"{marker}{{{output}}}" if left else f"{{}}{marker}{{{output}}}"
                )
            elif child.name == "math":
                output = str(child)
                chunks.append(output)
            else:
                output = child.get_text()
                chunks.append(output)
            self.debug(levels, f"[{child.name=}] [{child=}] [{output}]")
        return "".join(chunks)

    def left_attached(self, node) -> bool:
        sib = node.previous_sibling
        return isinstance(sib, str) and sib and not sib[-1].isspace()

    def pos_process_markdown(self, markdown):
        markdown = self._normalize.nfkc_seletivo(markdown)
        return markdown

    # métodos utilitários

    def suffix_if_not(self, text: str, suffix, suffix_test=None):
        if suffix_test is None:
            suffix_test = suffix
        if not text.endswith(suffix_test):
            text = f"{text}{suffix}"
        return text

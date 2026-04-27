import logging
import re

from bs4 import BeautifulSoup
from bs4.element import Comment, NavigableString, Tag

from .tag_types import HtmlTagTypes


class DomPreprocessor:
    def __init__(
        self,
        logger_name: str | None = None,
        log_level: str = "INFO",
    ) -> None:
        self._logger_name = logger_name or self.__class__.__name__

        self.logger = logging.getLogger(self._logger_name)

        # Só configura o nível se não recebeu um logger externo
        if logger_name is None:
            level = getattr(logging, log_level.upper(), logging.INFO)
            self.logger.setLevel(level)

        # Block tags cujo interior deve ser percorrido para englobar "textos" com tag "p".
        # Por exemplo a tag "pre" é block, mas não deve ser processada. Por isso não consta.
        self.BLOCK_TAGS = {
            "address",
            "article",
            "aside",
            "blockquote",
            "div",
            "dl",
            "fieldset",
            "figcaption",
            "figure",
            "footer",
            "form",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "hr",
            "main",
            "nav",
            "ol",
            "ul",
            "section",
            "table",
        }
        self.BLOCK_TAGS_NO_RECURSION = {
            "pre",
        }
        self.RE_ASCII_WS = re.compile(r"[\t\n\f\r ]+")
        self.RE_INLINE_SPACE = re.compile(r"[ \t]")

    def normalize(self, soup: BeautifulSoup):
        """
        Agrupa texto solto e elementos inline (phrasing content) em <p>
        ao longo de todo o documento, preservando blocos e <p> existentes.
        """

        def is_meaningful_text(node):
            return isinstance(node, NavigableString) and node.strip()

        def prepare_structure(node: Tag):
            if not isinstance(node, Tag):
                return

            if node.name == "p":
                return

            children = list(node.children)
            buffer = []

            def flush(ref=None):
                if not buffer:
                    return

                # Evita <p> vazio
                if not any(isinstance(x, Tag) or is_meaningful_text(x) for x in buffer):
                    buffer.clear()
                    return

                p = soup.new_tag("p")
                for el in buffer:
                    p.append(el)
                buffer.clear()

                if ref:
                    ref.insert_before(p)
                else:
                    node.append(p)

            for child in list(children):
                self.logger.debug(f"{child.name=}")

                if isinstance(child, NavigableString):
                    if isinstance(child, Comment):
                        child.decompose()
                        continue
                    self.logger.debug("é NavigableString")
                    is_meaningful = bool(child.strip())
                    is_inline_space = not child.strip() and bool(
                        self.RE_INLINE_SPACE.search(child)
                    )
                    if is_meaningful or (buffer and is_inline_space):
                        buffer.append(child.extract())
                    continue

                if isinstance(child, Tag):
                    self.logger.debug("é Tag")

                    if child.name in self.BLOCK_TAGS:
                        self.logger.debug("é Block Tag")
                        flush(child)
                        prepare_structure(child)
                        continue

                    if child.name in self.BLOCK_TAGS_NO_RECURSION:
                        self.logger.debug("é Block Tag no recursion")
                        flush(child)
                        continue

                    if child.name == "p":
                        self.logger.debug("é P")
                        flush(child)
                        continue

                    if child.name in HtmlTagTypes.PHRASING_TAGS:
                        self.logger.debug("é Phrasing Tag")

                        # se for code apenas com um pre dentro, funciona como Block Tag no recursion
                        if child.name == "code":
                            grandchilds_names = [
                                grandchild.name
                                for grandchild in list(child.children)
                                if grandchild.name is not None
                            ]
                            self.logger.debug(grandchilds_names)
                            if grandchilds_names == ["pre"]:
                                self.logger.debug(
                                    "é Phrasing Tag funcionando como Block Tag no recursion"
                                )
                                flush(child)
                                continue

                        buffer.append(child.extract())
                        continue

                    flush(child)
                    prepare_structure(child)

            flush()

        def normalize_whitespace(node: Tag):
            has_prev = node.name != "p"
            for child in list(node.children):
                if isinstance(child, NavigableString):
                    text = str(child)

                    if self.RE_ASCII_WS.fullmatch(text):
                        normalized = " "
                    else:
                        normalized = self.RE_ASCII_WS.sub(" ", text)
                        if not has_prev:
                            normalized = normalized.lstrip(" ")

                    if normalized != text:
                        child.replace_with(NavigableString(normalized))

                    has_prev = True

                elif isinstance(child, Tag):
                    if child.name not in self.BLOCK_TAGS_NO_RECURSION:
                        normalize_whitespace(child)
                    has_prev = child.name != "br"

        # Começa recursivamente do soup
        prepare_structure(soup)
        normalize_whitespace(soup)

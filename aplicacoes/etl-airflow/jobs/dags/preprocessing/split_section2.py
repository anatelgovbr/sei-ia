"""split_section2 module."""

import re

from bs4 import BeautifulSoup

from jobs.dags.preprocessing.text_clean import remove_encoding

_HTML_PARSER = "html.parser"


class SplitSection:
    def __init__(self, html, idx=None, html_sections=None) -> None:
        if html_sections is None:
            html_sections = {}
        body = BeautifulSoup(html, _HTML_PARSER).find("body")
        self.html = str(body) if body else html
        self.index = idx
        self.html_sections = html_sections
        self.doc = BeautifulSoup(html, _HTML_PARSER)
        self.sections = self.get_sections()

    @staticmethod
    def doc_find(doc, search):
        p = SplitSection.doc_find_tag(doc, search, "p")
        if p is None:
            p = SplitSection.doc_find_tag(doc, search, "strong")
        return p

    @staticmethod
    def doc_find_tag(doc, search, tag_name):
        pattern = "|".join([re.escape(s) for s in search])
        regexp = rf"^(\s*[\divxIVX]*\s*[\.\)º\-]*\s*)({pattern}).*$"
        identifiers = re.compile(regexp, re.DOTALL)  # re.IGNORECASE | re.DOTALL)

        def filt(tag):
            return (tag.name == tag_name) and (
                identifiers.match(str(tag)) or identifiers.match(tag.text)
            )

        return doc.find(filt)

    @staticmethod
    def doc_find_all(doc):
        return doc.find_all(["p"])

    @staticmethod
    def doc_find_all_next(detect):
        return detect.find_all_next("p")

    def get_sections(self) -> list:
        """Captura o nome das secoes."""
        sects = [
            BeautifulSoup(
                "<p>UNLIKELY_START_OF_DOCUMENT_MARKER</p>", _HTML_PARSER
            ).find("p")
        ]
        for _, search in self.html_sections.items():
            p = self.doc_find(self.doc, search)
            if p is not None:
                sects.append(p)
        return sects

    def get_p(self, min_len=300) -> list:
        list_p = self.doc_find_all(self.doc)
        store = []
        for p in list_p:
            txt = self.pre_processing(p)
            if len(txt) > min_len:
                store.append(txt)
        return store

    def pre_processing(self, text) -> str:
        return remove_encoding(text)

    def _split_non_last_section(self, search: list, nivel, next_section: list) -> str:
        idx_search = (
            0 if nivel.text.strip() == "UNLIKELY_START_OF_DOCUMENT_MARKER" else None
        )
        html_split = self.doc_find_all(self.doc)
        idx_next = None
        for idx, soup in enumerate(html_split):
            soup = BeautifulSoup(str(soup), _HTML_PARSER)
            is_search = self.doc_find(soup, search)
            is_next = self.doc_find(soup, next_section)
            if is_search and idx_search is None:
                idx_search = idx
            if is_next is not None and idx_search is not None:
                idx_next = idx
                selected = [e.get_text() for e in html_split[idx_search : idx_next + 1]]
                if nivel.text.strip() != "UNLIKELY_START_OF_DOCUMENT_MARKER":
                    i = selected[0].find(nivel.text)
                    selected[0] = selected[0][i + len(nivel.text) :]
                i_next = selected[-1].find(next_section[0])
                selected[-1] = selected[-1][:i_next]
                return "<SEP> ".join([self.pre_processing(x) for x in selected])
        return ""

    def _split_last_section(self, search: list, nivel) -> str:
        if nivel.text.strip() == "UNLIKELY_START_OF_DOCUMENT_MARKER":
            return "<SEP>".join(
                [self.pre_processing(x.get_text()) for x in self.doc_find_all(self.doc)]
            )
        detect = self.doc_find(self.doc, search)
        if not detect:
            return ""
        selected = [detect.get_text()] + [
            e.get_text() for e in self.doc_find_all_next(detect)
        ]
        i = selected[0].find(nivel.text)
        selected[0] = selected[0][i + len(nivel.text) :]
        return "<SEP>".join([self.pre_processing(x) for x in selected])

    def split_section(self, search) -> str:
        """Separa o documento SEI em suas secoes
        @params
        search : secao a ser pesquisada.
        """
        for idx, nivel in enumerate(self.sections):
            nivel_in_search = self.doc_find(
                BeautifulSoup(str(nivel), _HTML_PARSER), search
            )
            if not nivel_in_search:
                continue
            if self.sections[-1].text != nivel.text:
                next_section = [self.sections[idx + 1].text.strip()]
                result = self._split_non_last_section(search, nivel, next_section)
                if result:
                    return result
            else:
                return self._split_last_section(search, nivel)
        return ""

    def create_sections(self) -> dict:
        d = {}
        if self.index:
            d["nr_documento"] = self.index
        d["preambulo"] = self.split_section(["UNLIKELY_START_OF_DOCUMENT_MARKER"])
        for k, v in self.html_sections.items():
            d[k] = self.split_section(v)
        return d

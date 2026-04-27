import logging
import string
from collections import namedtuple
from itertools import product

LiNumberType = namedtuple("LiNumberType", ["separator", "number"])


class EditorSei:
    def __init__(
        self,
        logger_name: str | None = None,
    ) -> None:
        self._logger_name = logger_name or self.__class__.__name__

        self.logger = logging.getLogger(self._logger_name)

        self.ROMAN_NUMERALS = [self.int_to_roman(i) for i in range(1, 501)]
        self.LETTERS_LOWER = [
            "".join(c)
            for n in range(1, 3)
            for c in product(string.ascii_lowercase, repeat=n)
        ]

        self.LI_DECIMAL_DEFAULT = LiNumberType(")", lambda x: x)
        self.LI_DECIMAL_DASH = LiNumberType(" -", lambda x: x)
        self.LI_DECIMAL = LiNumberType(".", lambda x: x)
        self.LI_UPPER_LATIN = LiNumberType(")", self.int_to_upper_latin)
        self.LI_UPPER_LATIN_POINT = LiNumberType(".", self.int_to_upper_latin)
        self.LI_LOWER_LATIN = LiNumberType(")", self.int_to_lower_latin)
        self.LI_LOWER_LATIN_POINT = LiNumberType(".", self.int_to_lower_latin)
        self.LI_UPPER_ROMAN: LiNumberType = LiNumberType(".", self.int_to_upper_roman)
        self.LI_LOWER_ROMAN: LiNumberType = LiNumberType(".", self.int_to_lower_roman)
        self.LI_TYPE_LEVEL = {
            ("default", 1): self.LI_DECIMAL_DEFAULT,
            ("default", 2): self.LI_LOWER_LATIN,
            ("default", 3): self.LI_UPPER_ROMAN,
            ("default", 4): self.LI_UPPER_LATIN,
            ("default", 0): self.LI_DECIMAL_DASH,
            ("decimal-dash", 0): self.LI_DECIMAL_DASH,
            ("decimal", 0): self.LI_DECIMAL,
            ("upper-latin", 0): self.LI_UPPER_LATIN,
            ("lower-latin", 0): self.LI_LOWER_LATIN,
            ("upper-roman", 0): self.LI_UPPER_ROMAN,
            ("a", 0): self.LI_LOWER_LATIN_POINT,
            ("A", 0): self.LI_UPPER_LATIN_POINT,
            ("i", 0): self.LI_LOWER_ROMAN,
            ("I", 0): self.LI_UPPER_ROMAN,
            ("1", 0): self.LI_DECIMAL,
        }

        self.P_ROMAN = "Item_Inciso_Romano"
        self.P_LATIN = "Item_Alinea_Letra"
        self.P_LEVELS_SERIES = [
            [
                "Item_Nivel1",
                "Item_Nivel2",
                "Item_Nivel3",
                "Item_Nivel4",
                self.P_ROMAN,
                self.P_LATIN,
            ],
            [
                "Paragrafo_Numerado_Nivel1",
                "Paragrafo_Numerado_Nivel2",
                "Paragrafo_Numerado_Nivel3",
                "Paragrafo_Numerado_Nivel4",
                self.P_ROMAN,
                self.P_LATIN,
            ],
        ]
        self.P_GLOBALS = self.get_p_globals()
        self.P_SEI_CLASSES = self.P_GLOBALS.keys()

        self.P_QUOTE = [
            "Citacao",
        ]
        self.P_BOLD = [
            "Texto_Fundo_Cinza_Negrito",
        ]
        self.P_UPPER = [
            "Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc",
            "Texto_Centralizado_Maiusculas",
            "Texto_Justificado_Maiusculas",
        ]
        self.P_UPPER_BOLD = [
            "Texto_Centralizado_Maiusculas_Negrito",
            "Texto_Fundo_Cinza_Maiusculas_Negrito",
        ]
        self._log_ident = ""

    def set_log_ident(self, log_ident: str) -> None:
        """Seta o valor de log_ident para uso posterior."""
        self._log_ident = log_ident

    def ol_number_lambda(self, node, level=1):
        ol_sei = self.has_class(node, "infra-editor__lista")
        if ol_sei:
            ol_type = self.get_1st_class_by_prefix(node, "list-style-type-", "default")
        else:
            html_ol_type = node.get("type")
            ol_type = html_ol_type if html_ol_type else "1"
        try:
            li = self.LI_TYPE_LEVEL[(ol_type, level)]
        except KeyError:
            li = self.LI_TYPE_LEVEL[(ol_type, 0)]
        return lambda number: f"{li.number(number)}{li.separator}"

    def p_class_lambda(self, node, counters):
        ol_type = self.get_1st_class_by_prefix(node)
        self.logger.debug(f"{self._log_ident}p_number_lambda [{ol_type=}]")
        if ol_type in self.P_GLOBALS:
            numbers = self.p_numbers(ol_type, counters)
            if ol_type == "Item_Nivel1":
                return lambda line: f"# **{numbers} {line.upper()}**"
            else:
                return lambda line: f"{numbers} {line}"
        elif ol_type in self.P_UPPER:
            return lambda line: line.upper()
        elif ol_type in self.P_BOLD:
            return lambda line: f"**{line}**"
        elif ol_type in self.P_UPPER_BOLD:
            return lambda line: f"**{line.upper()}**"
        elif ol_type in self.P_QUOTE:
            return lambda line: f"```\n{line}\n```"
        else:
            return lambda line: line

    def get_p_globals(self):
        classes = set()
        for p_level_serie in self.P_LEVELS_SERIES:
            classes = classes.union(p_level_serie)
        return dict.fromkeys(classes, 0)

    def p_numbers(self, level, counters):
        levels = self.p_series_inc(level, counters)
        if level == self.P_ROMAN:
            numbers = [self.ROMAN_NUMERALS[counters[level] - 1]]
            closing = " -"
        elif level == self.P_LATIN:
            numbers = [self.LETTERS_LOWER[counters[level] - 1]]
            closing = ")"
        else:
            numbers = [str(counters[level]) for level in levels]
            closing = "."
        return ".".join(numbers) + closing

    def p_series_inc(self, level, counters):
        levels = []
        for p_level_serie in self.P_LEVELS_SERIES:
            if level in p_level_serie:
                achou = False
                for p_level in p_level_serie:
                    if achou:
                        counters[p_level] = 0
                    else:
                        if p_level == level:
                            try:
                                counters[p_level] += 1
                            except TypeError:
                                self.logger.error(
                                    f"{self._log_ident}[{p_level=}] [{counters=}]"
                                )
                            achou = True
                        levels.append(p_level)
                break
        self.logger.debug(
            f"{self._log_ident}p_series_inc [{level=}] [{counters[level]=}]"
        )
        return levels

    def get_1st_class_by_prefix(self, element, prefix="", default=""):
        return self.get_classes_by_prefix(element, prefix, default)[0]

    def get_classes_by_prefix(self, element, prefix="", default=""):
        el_classes = element.get("class")
        classes = (
            [cl[len(prefix) :] for cl in el_classes if cl.startswith(prefix)]
            if el_classes
            else []
        )
        if not classes:
            classes.append(default)
        return classes

    def has_class(self, element, el_class):
        el_classes = element.get("class")
        return el_classes and el_class in el_classes

    def int_to_lower_latin(self, idx: int) -> str:
        return self.LETTERS_LOWER[idx - 1]

    def int_to_upper_latin(self, idx: int) -> str:
        return self.LETTERS_LOWER[idx - 1].upper()

    def int_to_lower_roman(self, idx: int) -> str:
        return self.ROMAN_NUMERALS[idx - 1].lower()

    def int_to_upper_roman(self, idx: int) -> str:
        return self.ROMAN_NUMERALS[idx - 1]

    def int_to_roman(self, num: int) -> str:
        """Converte número inteiro para algarismo romano.

        Args:
            num: Número inteiro de 1 a 3999

        Returns:
            String com número romano
        """
        values = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
        symbols = [
            "M",
            "CM",
            "D",
            "CD",
            "C",
            "XC",
            "L",
            "XL",
            "X",
            "IX",
            "V",
            "IV",
            "I",
        ]

        roman = ""
        for value, symbol in zip(values, symbols):  # noqa: B905
            while num >= value:
                roman += symbol
                num -= value
        return roman

import logging
import unicodedata

ENCLOSED_CODES = set(range(0x2460, 0x24FF + 1)) | set(range(0x1F100, 0x1F1FF + 1))

# Categorias Unicode que nunca são frações — evita chamar numeric() desnecessariamente
_FRAC_CATEGORIES = {"No", "Nl"}  # Number, other / letter

SUPERSCRIPTS = (
    set(range(0x2070, 0x2071 + 1))
    | {0x00B2, 0x00B3, 0x00B9}
    | set(range(0x2074, 0x207F + 1))
)
SUBSCRIPTS = set(range(0x2080, 0x209C + 1))
SUPER_SUB_SCRIPTS = SUPERSCRIPTS | SUBSCRIPTS


class Normalize:
    def __init__(self, logger_name: str | None = None):
        self._logger_name = logger_name or self.__class__.__name__
        self.logger = logging.getLogger(self._logger_name)

        self._cache = {}

    def nfkc_seletivo(self, texto: str) -> str:
        # referência local evita lookup de atributo por iteração
        cache = self._cache
        out = []
        append = out.append

        for ch in texto:
            if ch in cache:
                append(cache[ch])
                continue

            code = ord(ch)

            # 1. é sup ou sub
            if ch in SUPER_SUB_SCRIPTS:
                cache[ch] = ch
                append(ch)
                continue

            # 2. é enclosed não parênteses
            if code in ENCLOSED_CODES:
                decoded = unicodedata.normalize("NFKC", ch)
                if decoded[0] != "(":
                    cache[ch] = ch
                    append(ch)
                    continue

            # 3. é fração (categoria antes de numeric())
            if unicodedata.category(ch) in _FRAC_CATEGORIES:
                try:
                    v = unicodedata.numeric(ch)
                    if not v.is_integer():
                        cache[ch] = ch
                        append(ch)
                        continue
                except (TypeError, ValueError):
                    pass

            normalized = unicodedata.normalize("NFKC", ch)
            cache[ch] = normalized
            append(normalized)

        return "".join(out)

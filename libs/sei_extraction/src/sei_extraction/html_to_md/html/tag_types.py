"""
Este módulo disponibiliza alguns grupos de tags HTML por tipo.
Utilizado para categorização de `nodes` do BeautifulSoup (bs4) por `name`.

--

# HTML Living Standard (WHATWG) - Fonte oficial

https://html.spec.whatwg.org

Seção: 3.2.5 Content models

# MDN Web Docs - Alternativa mais organizada

https://developer.mozilla.org/en-US/docs/Web/HTML/Content_categories

Flow content, Phrasing content. Sectioning content, Heading content, Embedded content, Interactive content, Palpable content
"""

from typing import ClassVar


class HtmlTagTypes:
    # tag types
    DOCUMENT: ClassVar[set[str]] = {
        "[document]",
        "html",
        "body",
    }
    DOCUMENT_IGNORE: ClassVar[set[str]] = {
        "title",
        "head",
        "meta",
        "style",
        "script",
    }
    SECTIONING: ClassVar[set[str]] = {
        "section",
        "article",
        "main",
        "aside",
        "nav",
    }
    GROUPERS: ClassVar[set[str]] = {
        "header",
        "footer",
        "figure",
        "details",
    }
    DIV_LIKE: ClassVar[set[str]] = {
        "div",
    }.union(SECTIONING).union(GROUPERS)
    SEPARATORS: ClassVar[set[str]] = {
        "hr",
    }
    TABLE: ClassVar[set[str]] = {
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
    }
    TABLE_IGNORE: ClassVar[set[str]] = {
        "colgroup",
        "col",
    }
    FORM: ClassVar[set[str]] = {
        "form",
        "fieldset",
    }
    LISTS: ClassVar[set[str]] = {
        "li",
        "ul",
        "ol",
    }
    QUOTES: ClassVar[set[str]] = {
        "blockquote",
        "pre",
    }
    OBSOLETE: ClassVar[set[str]] = {
        "center",
    }
    FLOW_CONTAINERS: ClassVar[set[str]] = (  # container estrutural
        set()
        .union(DOCUMENT)
        .union(DIV_LIKE)
        .union(SEPARATORS)
        .union(TABLE)
        .union(FORM)
        .union(LISTS)
        .union(QUOTES)
        .union(OBSOLETE)
    )

    PHRASING_TAGS_HTML: ClassVar[set[str]] = {
        "a",
        "abbr",
        "area",
        "audio",
        "b",
        "bdi",
        "bdo",
        "br",
        "button",
        "canvas",
        "cite",
        "code",
        "data",
        "datalist",
        "del",
        "dfn",
        "em",
        "embed",
        "i",
        "iframe",
        "img",
        "input",
        "ins",
        "kbd",
        "label",
        "link",
        "map",
        "mark",
        "math",
        "meta",
        "meter",
        "noscript",
        "object",
        "output",
        "picture",
        "progress",
        "q",
        "ruby",
        "rp",
        "rt",
        "s",
        "samp",
        "select",
        "slot",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "svg",
        "textarea",
        "time",
        "u",
        "var",
        "wbr",
    }
    PHRASING_TAGS_OTHERS: ClassVar[set[str]] = {
        "msreadoutspan",  # MS - Destaca o que está sendo lido
    }
    PHRASING_TAGS_IGNORE: ClassVar[set[str]] = {
        "area",
        "canvas",
        "font",
        "iframe",
        "map",
        "noscript",
        "object",
    }
    PHRASING_TAGS: ClassVar[set[str]] = (
        set().union(PHRASING_TAGS_HTML).union(PHRASING_TAGS_OTHERS)
    )

    OTHERS_IGNORE: ClassVar[set[str]] = {
        "template",
    }
    IGNORE: ClassVar[set[str]] = (
        set()
        .union(DOCUMENT_IGNORE)
        .union(PHRASING_TAGS_IGNORE)
        .union(OTHERS_IGNORE)
        .union(TABLE_IGNORE)
    )

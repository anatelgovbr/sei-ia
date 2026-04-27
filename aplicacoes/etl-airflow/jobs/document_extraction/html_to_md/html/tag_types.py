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


class HtmlTagTypes:
    # tag types
    DOCUMENT = {
        "[document]",
        "html",
        "body",
    }
    DOCUMENT_IGNORE = {
        "title",
        "head",
        "meta",
        "style",
        "script",
    }
    SECTIONING = {
        "section",
        "article",
        "main",
        "aside",
        "nav",
    }
    GROUPERS = {
        "header",
        "footer",
        "figure",
        "details",
    }
    DIV_LIKE = {
        "div",
    }.union(SECTIONING).union(GROUPERS)
    SEPARATORS = {
        "hr",
    }
    TABLE = {
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
    }
    TABLE_IGNORE = {
        "colgroup",
        "col",
    }
    FORM = {
        "form",
        "fieldset",
    }
    LISTS = {
        "li",
        "ul",
        "ol",
    }
    QUOTES = {
        "blockquote",
        "pre",
    }
    OBSOLETE = {
        "center",
    }
    FLOW_CONTAINERS = (  # container estrutural
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

    PHRASING_TAGS_HTML = {
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
    PHRASING_TAGS_OTHERS = {
        "msreadoutspan",  # MS - Destaca o que está sendo lido
    }
    PHRASING_TAGS_IGNORE = {
        "area",
        "canvas",
        "font",
        "iframe",
        "map",
        "noscript",
        "object",
    }
    PHRASING_TAGS = set().union(PHRASING_TAGS_HTML).union(PHRASING_TAGS_OTHERS)

    OTHERS_IGNORE = {
        "template",
    }
    IGNORE = (
        set()
        .union(DOCUMENT_IGNORE)
        .union(PHRASING_TAGS_IGNORE)
        .union(OTHERS_IGNORE)
        .union(TABLE_IGNORE)
    )

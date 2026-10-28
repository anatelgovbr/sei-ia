"""regex module."""

import re

expressions = {
    "re_resolucoes": r"resolução nº [\d\.]+",
    "re_leis": r"lei nº [\d\.]+",
    "re_decretos": r"decreto nº [\d\.]+",
    "re_artigos": r"art\. [\d\.]+",
    "re_processos": r"[\d]{5}\.[\d]{6}\/[\d]{4}\-[\d]{2}",
    "re_documentos": r"(?<=[^\d])[\d]{7}(?=[^\d])",
}


def transform_expressions(text):
    text = re.sub(r"[-/nºçã., ]", "", text)
    text = text.replace("ç", "c")
    return text.replace("ã", "a")


def summarize_text(text):
    summarized_text = []

    for r_expr in expressions.values():
        instances = re.findall(r_expr, text.lower())

        for instance in instances:
            summarized_text.append(transform_expressions(instance))

    summarized_text = " ".join(summarized_text)

    return re.sub(r"[\s]+", " ", summarized_text)


def apply_regex_model(txts_series):
    return txts_series.apply(summarize_text)

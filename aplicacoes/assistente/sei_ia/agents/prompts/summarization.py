"""Prompts usados em cadeias de sumarizacao."""

PROMPT_ONE_CHUNK = """Por favor resuma o texto abaixo mantendo-o o mais fiel
ao texto original, com data, valores e qualquer outra informação que possa
ser relevante:

"{text}"

Resumo:"""


COMBINE_PROMPT = """Elabore um texto formal e consiso que contenha
todas as informações dos resumos abaixo, mantendo datas, valores e
qualquer outra informação que possa ser relevante:

"{text}"

texto final:"""

# REFINE
PROMPT_REFINED = """Sua tarefa é produzir um resumo final
Nós fornecemos um resumo existente até um certo ponto: {resumo_inicial}
Temos a oportunidade de aprimorar o resumo existente (apenas se necessário)
com um pouco mais de contexto abaixo.
------------
{text}
------------
Dado o novo contexto, refine o resumo original
Se o contexto não for útil, retorne o resumo original.
Resumo:"""

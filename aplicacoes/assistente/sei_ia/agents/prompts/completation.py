"""Prompt com documentos."""

COMPLETATION_WITH_DOC_INSTRUCTION = r"""
INSTRUCOES: {instruction}

# Baseado na SOLICITACAO abaixo, lembrando que
cada documento é identificado por #número_do_documento seguido opcionalmente por delimitação
de páginas ("#número_do_documento[página]" ou "#número_do_documento[página_inicial:página_final]"):
---
SOLICITACAO: {text}
---
[conteúdo dos documentos]
{conteudo_documentos}
[\conteúdo dos documentos]
# Por favor, responda à SOLICITACAO da melhor forma possível.
"""


COMPLETATION_WITH_DOC = r"""# Baseado na SOLICITACAO abaixo, lembrando que
cada documento é identificado por #número_do_documento seguido opcionalmente por delimitação de
páginas ("#número_do_documento[página]" ou "#número_do_documento[página_inicial:página_final]"):
---
SOLICITACAO: {text}
---
[conteúdo dos documentos]
{conteudo_documentos}
[\conteúdo dos documentos]
# Por favor, responda à SOLICITACAO da melhor forma possível.
"""

INTERMEDIATE_COMPLETATION_WITH_DOC = """-------
# o conteúdo do documento #{id_documento_formatado} do processo {protocolo_processo}
está transcrito abaixo:
(delimitado por [doc_{id_documento_formatado}---] conteúdo [\\doc_{id_documento_formatado}---])
[doc_{id_documento_formatado}---]
{doc}
[\\doc_{id_documento_formatado}---]
"""

INTERMEDIATE_COMPLETATION_WITH_DOC_FOR_FALSE_RAG = """
# o conteúdo do documento #{id_documento_formatado}
está transcrito abaixo:
(delimitado por [doc_{id_documento_formatado}---] conteúdo [\\doc_{id_documento_formatado}---])
[doc_{id_documento_formatado}---]
[metadados---]
{metadata_proc}
{metadata_doc}
[\\metadados---]
[doc_{id_documento_formatado}---]
{doc}
[\\doc_{id_documento_formatado}---]
"""

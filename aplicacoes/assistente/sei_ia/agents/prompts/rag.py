"""Prompts usados por RAG."""

INSTRUCTIONS_SOURCES = r"""
### Instructions for output object RagAnswer:
1. Include source numbers like </Source(1)>, </Source(2)>, etc., in the response text where context was used.
2. The </Source(n)> index must correspond to the `sources` list in the JSON.
3. Transcribe exact excerpts from the source; no summarization.

### Output Format:
Enclose your answer within <rag_answer> tags using valid JSON:
{
  "answer": "Your answer with </Source(n)> references ...",
  "sources": [
    {
      "index": 1,
      "id_documento_formatado": "doc_id_123",
      "conteudo_documento": "Exact text used from the source ..."
    }
  ]
}

### Example:
<rag_answer>
{
  "answer": "Em dezembro de 2020, o processo foi pautado ... pelo Conselho diretor </Source(1)> .",
  "sources": [
    {
      "index": 1,
      "id_documento_formatado": "10066368",
      "conteudo_documento": "Na Reunião nº 893 do Conselho Diretor..."
    }
  ]
}
</rag_answer>
"""


PROMPT_RAG = """## Considere a seguinte pergunta:
{prompt}

# Analisando os textos fornecidos como referência,
 utilize as informações disponíveis nos chunks abaixo para gerar a resposta:
{emb_text}
\n

# Instruções adicionais
{instrucoes}

# Instruções importantes para a resposta:
 * Responda com base no formato acima, garantindo clareza e correção.
 * Se a informação necessária não estiver contida nos textos, indique que não foi possível responder.
Resposta:"""

DOC_METADATA_CHUNKS = """
[Texto de referencia #{id_doc_formatado}---]
[metadados---]
{metadados_proc}
{metadados_doc}
[\\metadados---]
[Conteúdo---]
{chunk}
[\\Conteúdo---]
[\\Texto de Referência ##{id_doc_formatado}---]
"""
# Explicar que os textos provêm de um RAG.
# Caso não tenha a informação, informe que nos trechos não havia a
# informação necessária para responder.

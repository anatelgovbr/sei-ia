# Prompts de Geração

> Prompts para geração de respostas

## RAG Prompt

**Arquivo**: `sei_ia/agents/prompts/rag.py`

```python
RAG_PROMPT = """
Responda a pergunta do usuário baseando-se nos trechos de documentos abaixo.

IMPORTANTE:
- Use marcadores <doc_N> para citar fontes
- Cite apenas trechos relevantes
- Se não encontrar informação, informe claramente

Trechos disponíveis:
{chunks}

Pergunta: {user_request}
"""
```

## Sumarização Prompt

**Arquivo**: `sei_ia/agents/prompts/summarization.py`

```python
SUMMARIZATION_PROMPT = """
Faça um resumo executivo do documento.

Diretrizes:
- Mantenha informações críticas
- Organize em tópicos quando apropriado
- Use linguagem clara e objetiva
- Limite: {max_tokens} tokens

Documento:
{content}
"""
```

## Question Generation Prompt

**Arquivo**: `sei_ia/agents/prompts/question_generation.py`

```python
QUESTION_GENERATION_PROMPT = """
Gere {n} variações da pergunta original mantendo o mesmo significado.

Use:
- Sinônimos
- Estruturas diferentes
- Perspectivas variadas

Pergunta original: {original_question}

Retorne uma pergunta por linha.
"""
```

## Disclaimer Prompt

**Arquivo**: `sei_ia/agents/prompts/disclaimer_need_identifier.py`

```python
DISCLAIMER_PROMPT = """
Analise se a resposta pode conter:
- Elementos fictícios
- Previsões
- Suposições

Se sim, classifique o caso e retorne o disclaimer apropriado.
"""
```

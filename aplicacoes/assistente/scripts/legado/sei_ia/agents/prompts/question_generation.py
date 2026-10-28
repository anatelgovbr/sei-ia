"""Prompts para geração de múltiplas perguntas no RAG Enhanced."""

GENERATE_QUESTIONS_PROMPT = """
Você é um especialista em análise de documentos administrativos e jurídicos.

Pergunta original do usuário: {user_question}

Gere exatamente {n_questions} perguntas relacionadas que ajudarão a buscar informações relevantes nos documentos.
As perguntas devem:
1. Uma reformulação mais específica da pergunta original
2. Uma pergunta sobre o contexto temporal (datas, prazos, vigências)
3. Uma pergunta sobre partes envolvidas ou responsáveis
4. Uma pergunta sobre implicações ou consequências
5. Uma pergunta mais geral sobre o tema

Formato de resposta (uma pergunta por linha, sem numeração):
pergunta 1
pergunta 2
pergunta 3
pergunta 4
pergunta 5
"""

# Prompts de Intenção

> Prompts para classificação de intenção

**Arquivo**: `sei_ia/agents/prompts/intent_selector.py`

## Prompt de Classificação

```python
INTENT_CLASSIFICATION_PROMPT = """
Analise a seguinte requisição e classifique a intenção do usuário.

Categorias disponíveis:
A) conversar - Conversa geral sem referência a documentos
B) pergunta - Pergunta específica sobre um documento
C) resumo - Pedido de resumo ou síntese
D) reescrever - Correção gramatical ou tradução
E) multi_pergunta - Múltiplas perguntas sobre documentos
F) analise - Análise detalhada de documento
G) escrever - Pedido de redação de texto
H) outras - Outras intenções não listadas

Requisição: {user_request}

Responda em JSON:
{
    "justificativa": "explicação breve",
    "intencao": "letra_da_categoria"
}
"""
```

## Exemplos de Classificação

| Requisição | Intenção |
|------------|----------|
| "Qual o objeto deste processo?" | `pergunta` |
| "Resuma este documento" | `resumo` |
| "Corrija este texto: ..." | `reescrever` |
| "Olá, como você está?" | `conversar` |
| "Analise os riscos deste contrato" | `analise` |

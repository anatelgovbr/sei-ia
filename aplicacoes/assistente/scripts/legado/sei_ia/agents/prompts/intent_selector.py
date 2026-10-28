"""Prompts para o seletor de intenções."""

DICT_DOCUMENTS_INTENTIONS = {
    "conversar": (
        "Conversação: Refere-se a perguntas que não têm necessidade do conteúdo "
        "do documento citado."
    ),
    "pergunta": (
        "Uma única pergunta sobre um ou mais documentos e/ou processos: Refere-se a casos em "
        "que pode ser usado RAG (uso de embeddings e recuperação por similaridade) "
        "para extrair trechos específicos do documento que respondam à pergunta do "
        "usuário. Inclui perguntas como 'Do que se trata', 'O que é', 'Qual o conteúdo', "
        "'Sobre o que fala' quando se referem a documentos específicos. Não aplicável "
        "quando o usuário faz mais de uma pergunta."
    ),
    "resumo": (
        "Resumir um documento específico: Aplica-se quando o usuário explicitamente "
        "pede um resumo, lista, bullets, tópicos frásicos, principais pontos ou usa "
        "palavras como 'resumir', 'sumarizar', 'sintetizar'."
    ),
    "escrever": (
        "Escrever texto sobre um documento específico: Refere-se a solicitações "
        "de criar tabelas, elaborar textos, notícias, matérias jornalísticas, etc."
    ),
    "reescrever": (
        "Reescrever, transcrever, traduzir ou corrigir texto sobre um documento específico: Inclui "
        "transcrição, reescrita, revisão, correção, melhoria, tradução entre quaisquer idiomas, preencher um template, transcrever partes "
        "(como capas, introdução, conclusão, ementa, etc.) de documentos e combinação "
        "entre documentos."
    ),  # exceção caso maior que 4k, pois a saída máxima do GPT é 4k
    "multi_pergunta": (
        "Mais de uma pergunta sobre um ou mais documentos: Refere-se a casos "
        "em que pode ser usado RAG FALSA (uso de trechos reais do texto para responder "
        "individualmente à solicitação do usuário)."
    ),
    "outras": (
        "Nenhuma das opções: Use esta opção apenas nos casos em que nenhuma das "
        "outras possibilidades seja aplicável."
    ),
    "analise": (
        "Pergunta cuja a resposta demanda análise de todo ou grande parte do documento: "
        "Refere-se a casos em que a pergunta feita vai demandar uma análise de todo ou grande "
        "parte do conteúdo do documento para a formulação da resposta, tais como perguntas sobre "
        "quantidades (exemplos: 'quantas vezes', 'qual a frequência'), perguntas compostas por "
        " uma sentença afirmativa seguida de uma frase interrogativa "
        "(exemplos: 'analisando o texto, você identifica erros?', 'comparando os documentos, temos "
        "contradições?')."
    ),
}


INTENT_DOCUMENTS_SELECTION_PROMPT = """Responda apenas com um JSON válido (sem markdown e sem comentários).
Campos obrigatórios: "justificativa" e "intencao".
A chave "intencao" deve ser UMA destas opções: conversar, pergunta, resumo, escrever, reescrever, multi_pergunta, outras, analise.

Exemplo de formato esperado:
{{"justificativa": "texto da justificativa do motivo da seleção", "intencao": "pergunta"}}

O número do documento está sempre indicado por #numero_do_documento.
Identifique a intenção do usuário considerando as descrições abaixo:
{intentions}

Pergunta do usuário:
{prompt}
"""


PROMPT_SPLIT_TASK = """# Considerando a solicitacao abaixo:
---
{prompt}
---
# Quais seriam os passos logicos para a resolucao da tarefa?
# Em caso de documento, pode solicitar para a pessoa inserir o conteudo de forma manual.
"""

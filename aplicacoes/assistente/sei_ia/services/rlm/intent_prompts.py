"""Mapeamento de intent para fragmento de prompt do agente RLM."""

INTENT_PROMPT_FRAGMENTS = {
    "pergunta": "Responda a pergunta do usuario com base nos documentos, citando as fontes usando marcadores <doc_ID></doc_ID>.",
    "resumo": "Faca um resumo estruturado dos documentos fornecidos.",
    "escrever": "Gere um novo documento baseado nas referencias fornecidas, seguindo os padroes indicados.",
    "reescrever": "Corrija e reescreva o documento, corrigindo erros ortograficos e gramaticais, mantendo o conteudo original.",
    "conversar": "Responda ao usuario de forma conversacional.",
    "analise": "Analise os documentos e responda a pergunta do usuario com citacoes.",
    "multi_pergunta": "Responda todas as perguntas do usuario com base nos documentos, citando as fontes.",
    "outras": "Responda ao usuario da melhor forma possivel com base nos documentos.",
}

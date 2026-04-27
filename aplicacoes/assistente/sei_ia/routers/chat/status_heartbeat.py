import random

_WEB_SEARCH_MESSAGES = [
    "Ainda pesquisando na Internet...",
    "Aguardando resultados da busca na web",
    "Coletando informações da web",
    "Consultando fontes online na web",
    "Processando resultados da pesquisa na Internet",
    "Busca na Internet em andamento",
    "Reunindo dados da Internet",
    "Aguarde, ainda pesquisando informações na web",
]

_DOC_PROCESSING_MESSAGES = [
    "Ainda processando os documentos",
    "Análise dos documentos em andamento",
    "Lendo os documentos, aguarde",
    "Extração de conteúdo em andamento",
    "Interpretando o conteúdo dos documentos",
    "Processamento dos documentos ainda em curso",
    "Documentos sendo lidos e interpretados",
    "Aguarde, análise dos documentos em andamento",
]

_HISTORY_MESSAGES = [
    "Ainda recuperando o histórico do tópico",
    "Carregando mensagens anteriores do tópico",
    "Buscando histórico da conversa",
    "Recuperação das mensagens do tópico em andamento",
    "Carregando contexto da conversa",
    "Histórico do tópico ainda sendo recuperado",
    "Buscando mensagens do tópico",
    "Aguarde, histórico do tópico sendo carregado",
]

_VECTORIZATION_MESSAGES = [
    "Ainda vetorizando os documentos",
    "Vetorização dos documentos em andamento",
    "Gerando representações vetoriais dos documentos",
    "Processando vetorização dos documentos",
    "Aguarde, vetorização dos documentos ainda em curso",
    "Convertendo documentos em vetores",
    "Indexação vetorial dos documentos em andamento",
    "Aguarde, vetorização dos documentos sendo geradas",
]

INTERMEDIATE_MESSAGES: dict[str, list[str]] = {
    "Pesquisando na Internet": _WEB_SEARCH_MESSAGES,
    "Pesquisando informações na Internet": _WEB_SEARCH_MESSAGES,
    "Processando documentos": _DOC_PROCESSING_MESSAGES,
    "Recuperando mensagens anteriores do tópico": _HISTORY_MESSAGES,
    "Vetorizando documentos": _VECTORIZATION_MESSAGES,
}


def get_next_intermediate_message(
    current_status: str, last_msg: str | None
) -> str | None:
    messages = INTERMEDIATE_MESSAGES.get(current_status)
    if not messages:
        return None
    available = [m for m in messages if m != last_msg]
    if not available:
        available = messages
    return random.choice(available)

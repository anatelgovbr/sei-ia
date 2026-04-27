"""Modelos Pydantic e TypedDict para a API do SEI-IA Assistente.

Este módulo define todos os schemas de dados utilizados pela aplicação:

    Request Models:
        - ChatRequest: Requisição principal de chat
        - FeedbackRequest: Envio de feedback

    Document Models:
        - ItemDocumentRequest: Documento individual na requisição
        - ItemRequestIdProcedimento: Processo com seus documentos

    Response Models:
        - ResponseDataModel: Resposta completa da API
        - RagAnswer: Resposta com fontes do RAG
        - Source: Fonte individual do RAG

    Internal Models (TypedDict):
        - UserState: Estado durante processamento no LangGraph
        - ItemDocument: Documento processado internamente
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from typing_extensions import TypedDict

from sei_ia.agents.prompts.system import SYSTEM_PROMPT_v2 as SYSTEM_PROMPT

# ==============================================================================
# CONSTANTES
# ==============================================================================
VALIDATION_ERROR = "stars must be between 1 and 5"
VALORES_STARS = (1, 5)
DEFAULT_MAX_TOKENS = 4000


# ==============================================================================
# MODELOS AUXILIARES (Response)
# ==============================================================================


class Message(BaseModel):
    """Mensagem individual com role e conteúdo."""

    role: str = "user"
    content: str


class ChatCompletionRequest(BaseModel):
    """Requisição de chat completion."""

    text: str
    id_documento: str | None = None


class InitialConfigModel(BaseModel):
    """Configuração inicial do modelo na resposta."""

    messages: list[str]
    temperature: float
    max_tokens: int


class MessageModel(BaseModel):
    """Mensagem na resposta (role + content)."""

    role: str
    content: str


class ChoiceModel(BaseModel):
    """Escolha/resposta individual do modelo."""

    message: MessageModel
    finish_reason: str
    index: int


class UsageModel(BaseModel):
    """Informações de consumo de tokens."""

    prompt_tokens: int  # Tokens do prompt de entrada
    completion_tokens: int  # Tokens da resposta gerada
    total_tokens: int  # Total = prompt + completion


class ResponseDataModel(BaseModel):
    """Modelo completo de resposta da API (modo não-streaming)."""

    id: str  # UUID da resposta
    id_message: int  # ID sequencial da mensagem
    object: str  # Tipo: "chat.completion"
    created: datetime  # Timestamp de criação
    model: str  # Nome do modelo usado
    usage: UsageModel  # Contagem de tokens
    initial_config: InitialConfigModel  # Configuração inicial
    choices: list[ChoiceModel]  # Lista de respostas
    doc_paged: bool  # Documento foi paginado?
    doc_summarized: bool  # Documento foi sumarizado?


# ==============================================================================
# DOCUMENT MODELS - Estrutura de documentos na requisição
# ==============================================================================


class ItemDocumentRequest(BaseModel):
    """Documento individual na requisição.

    Representa um documento do SEI com opções de extração (paginação, anexos, cache).

    Hierarquia:
        ChatRequest → ItemRequestIdProcedimento → ItemDocumentRequest
    """

    # --- Identificação (obrigatório) ---
    id_documento: str

    # --- Opções de Extração ---
    download_ext: bool | None = Field(
        default=None, description="Download de arquivo externo (PDF, etc.)"
    )
    id_anexos: list[str] | None = Field(
        default=None, description="IDs de anexos para correspondência eletrônica"
    )
    pag_doc_init: int | None = Field(
        default=None, description="Página inicial para extração parcial"
    )
    pag_doc_end: int | None = Field(
        default=None, description="Página final para extração parcial"
    )

    # --- Cache ---
    sin_armazena_cache: str | None = Field(
        default="S", description="'S' = cachear (padrão), 'N' = não cachear (volátil)"
    )

    # --- Campos preenchidos durante processamento (após concatenate_documents) ---
    id_documento_formatado: str | None = Field(
        default=None, description="ID formatado (ex: '10066368')"
    )
    content: str | None = Field(
        default=None, description="Conteúdo extraído do documento"
    )
    metadata: dict | str | None = Field(default=None, description="Metadados do SEI")
    doc_tokens: int | None = Field(
        default=None, description="Contagem de tokens do conteúdo"
    )
    doc_paged: bool | None = Field(default=None, description="Indica se foi paginado")


# ==============================================================================
# INTERNAL MODELS (TypedDict) - Modelos internos do workflow
# ==============================================================================


class ItemDocument(TypedDict):
    """Documento processado internamente (TypedDict).

    Usado após a extração do documento do SEI, contém o conteúdo e metadados.
    """

    id_documento: str  # ID original
    id_documento_formatado: str  # ID formatado (ex: "10066368")
    content: str  # Conteúdo extraído
    doc_tokens: int  # Contagem de tokens
    doc_paged: bool  # Foi paginado?
    pag_doc_init: int | None  # Página inicial
    pag_doc_end: int | None  # Página final
    download_ext: bool | None  # Download externo?
    id_anexos: list[str] | None  # Anexos
    metadata: dict  # Metadados do SEI
    sin_armazena_cache: str | None  # "S" = cachear, "N" = não cachear


class ItemProcedimento(TypedDict):
    """Processo administrativo processado internamente (TypedDict)."""

    id_procedimento: str  # Número do processo
    id_documentos: list[ItemDocument] | list[str]  # Documentos processados
    metadata: dict  # Metadados


class ItemRequestIdProcedimento(BaseModel):
    """Processo administrativo na requisição.

    Agrupa documentos de um mesmo processo.

    Hierarquia:
        ChatRequest → ItemRequestIdProcedimento → ItemDocumentRequest
    """

    model_config = {"extra": "allow", "validate_assignment": True}

    id_procedimento: str
    id_documentos: (
        list[ItemDocumentRequest] | list[str]
    )  # TODO: Remover list[str] é necessário apenas para compatibilidade com payloads antigos
    metadata: dict | str = {}

    @field_validator("id_procedimento")
    @classmethod
    def replace_na_with_empty(cls, value: str) -> str:
        """Substitui 'N/A' por string vazia."""
        if value == "N/A":
            return ""
        return value

    @field_validator("id_documentos")
    @classmethod
    def transform_legacy_documents(cls, value: list) -> list:
        """Transforma documentos do formato antigo (strings) para o novo (objetos)."""
        if not value:
            return []

        # Se já são objetos ItemDocumentRequest, retorna como está
        if value and not isinstance(value[0], str):
            return value

        # Transformar strings para objetos ItemDocumentRequest
        transformed = []
        for doc_id in value:
            if isinstance(doc_id, str):
                doc_request = ItemDocumentRequest(
                    id_documento=doc_id,
                    download_ext=None,
                    pag_doc_init=0,
                    pag_doc_end=0,
                )
                transformed.append(doc_request)
            else:
                # Já é um objeto ItemDocumentRequest
                transformed.append(doc_id)

        return transformed


class UserState(TypedDict):
    """Estado principal durante processamento no LangGraph.

    Este TypedDict acompanha toda a requisição através do workflow,
    armazenando identificação, documentos, configurações e resposta.

    Seções:
        - Identificação: IDs de usuário, requisição, sessão
        - Documentos: Processos e documentos da requisição
        - Requisição: Texto, prompt, intenção detectada
        - Modelo: Tipo, temperatura, limites de tokens
        - Flags: Comportamento (websearch, thinking, memory)
        - Processamento: Estados de paginação, RAG, sumarização
        - RAG: Método, chunks, mapeamentos
        - Web Search: Resultados da busca web
        - Disclaimer: Avisos legais
        - Resposta: Resultado final
    """

    # --- IDENTIFICAÇÃO ---
    id_request: int  # ID único da requisição
    id_usuario: int  # ID do usuário
    ip: str  # IP do cliente
    endpoint_name: str  # Nome do endpoint chamado
    id_topico: int | None  # ID da sessão/tópico

    # --- DOCUMENTOS ---
    id_procedimentos: list[ItemRequestIdProcedimento] | None
    all_procs: list[str]  # Lista de IDs de processos
    all_documents: list[str]  # Lista de IDs de documentos

    # --- REQUISIÇÃO ---
    user_request: str  # Texto original do usuário
    system_prompt: str  # Prompt de sistema
    original_request_body: str  # JSON original da requisição
    intent: Literal[
        "conversar",
        "pergunta",
        "resumo",
        "escrever",
        "reescrever",
        "multi_pergunta",
        "outras",
        "analise",
    ]

    # --- CONFIGURAÇÃO DO MODELO ---
    model_type: Literal["mini", "standard", "nano", "think"]
    model_name: str  # Nome do deployment Azure
    temperature: float  # Temperatura do modelo
    general_max_output_tokens: int  # Limite de tokens de saída
    general_max_ctx_len: int  # Limite de contexto
    limit_rag: int  # Limite de chunks RAG

    # --- FLAGS DE COMPORTAMENTO ---
    use_websearch: bool  # Busca web habilitada?
    use_thinking: bool | None  # Modelo de raciocínio?
    summarize_history: bool  # Sumarizar histórico?
    skip_memory: bool  # Ignorar memória da sessão?

    # --- FLAGS DE PROCESSAMENTO ---
    doc_paged: bool | list  # Documento paginado?
    doc_summarized: bool  # Documento sumarizado?
    doc_rag: bool  # Usou RAG?
    doc_false_rag: bool  # RAG não aplicável?
    has_content: bool  # Tem conteúdo para processar?
    all_tokens_counter: int  # Contador total de tokens

    # --- RAG ---
    rag_method: str | None  # Método: "chunks" ou "full_doc"
    rag_documents_count: int | None  # Qtd de documentos no RAG
    rag_chunks_count: int | None  # Qtd de chunks recuperados
    rag_chunks_data: dict | None  # Dados dos chunks
    id_to_formatted_map: dict[str, str] | None  # Mapa ID -> ID formatado

    # --- WEB SEARCH ---
    tool_web_search: list[dict] | None  # Resultados da busca web

    # --- DISCLAIMER ---
    disclaimer_case: str | None  # Caso do disclaimer
    disclaimer_text: str | None  # Texto do disclaimer

    # --- PROMPT ---
    last_prompt: str  # Último prompt construído

    # --- RESPOSTA ---
    response: dict[str, Any]  # Resposta final


class UploadItem(BaseModel):
    """Item de upload na requisição.

    Representa um arquivo enviado pelo usuário para ser processado junto à mensagem.
    """

    id_upload: int
    nome_original: str
    extensao: str


class ChatRequest(BaseModel):
    """ChatRequest.

    Represents a completion request with user ID, text, system prompt,
    document ID, and temperature.
    """

    id_usuario: int
    id_topico: int | None = None
    text: str
    system_prompt: str | None = SYSTEM_PROMPT
    fator_limiar_rag: float = 1.0
    id_procedimentos: list[ItemRequestIdProcedimento] | None = None
    id_request: int | None = None
    ip: str | None = None
    use_thinking: bool | None = None
    use_websearch: bool = False
    summarize_history: bool = False
    skip_memory: bool = False
    uploads: list[UploadItem] | None = None

    def id_procedimentos_to_json(self) -> str:
        """Converte a lista `id_procedimentos` para uma representação em string JSON.

        Retorna:
            str: A representação em string JSON da lista `id_procedimentos`.
                Retorna `None` se `id_procedimentos` for `None`.
        """
        if self.id_procedimentos is None:
            return None
        return [
            id_procendimento.to_json() for id_procendimento in self.id_procedimentos
        ]

    def all_documents_allowed(self) -> list[str]:
        """Returns a list of all allowed documents."""
        if self.id_procedimentos is None:
            return []
        allowed = []
        for id_procedimento in self.id_procedimentos:
            # Tratar tanto objetos Pydantic quanto strings
            if isinstance(id_procedimento.id_documentos, list):
                for doc in id_procedimento.id_documentos:
                    if isinstance(doc, str):
                        allowed.append(doc)
                    else:
                        # É um ItemDocumentRequest
                        allowed.append(doc.id_documento)
        return allowed

    def all_procs_allowed(self) -> list[str]:
        """Returns a list of all allowed procedimentos."""
        if self.id_procedimentos is None:
            return []
        allowed = []
        for id_procedimento in self.id_procedimentos:
            allowed.append(id_procedimento.id_procedimento)
        return allowed


class ChatRequestWithModel(ChatRequest):
    agent_type: Literal["standard", "think", "mini", "nano"] | None


class FeedbackRequest(BaseModel):
    """Feedback.

    Represents a feedback request with message ID, stars,
    and optional comment.
    """

    id_mensagem: int
    stars: int
    comment: str | None = None

    @field_validator("stars")
    @classmethod
    def stars_must_be_in_range(cls: any, value: int) -> int:
        """Validates that stars are within the range of 1 to 5."""
        if value < VALORES_STARS[0] or value > VALORES_STARS[1]:
            raise ValueError(VALIDATION_ERROR)
        return value


class Source(BaseModel):
    """Modelo de dados para as fontes do RAG."""

    index: int
    id_documento_formatado: str = Field(
        ..., title="ID do Documento", description="ID do documento formatado."
    )
    conteudo_documento: str = Field(
        ..., title="Conteúdo do Documento", description="Conteúdo utilizado pela IA."
    )

    def __str__(self) -> str:
        """Retorna uma representação em string do objeto."""
        return (
            f"Documento SEI nº {self.id_documento_formatado} | "
            f"Trecho utilizado pela IA: {self.conteudo_documento}"
        )


class RagAnswer(BaseModel):
    """Modelo de dados para a resposta do RAG."""

    answer: str = Field(
        ...,
        examples=[
            (
                "O processo nº 53500.016759/2019-58 propõe uma nova metodologia de cálculo "
                "para as multas relacionadas a infrações de direitos e garantias dos usuários "
                "conforme estabelecido pela Portaria nº 791, de 26 de agosto de 2014 </Source(1)>.\n"
                "Os principais pontos abordados nos documentos analisados incluem: \n"
                "  1. Proposta de Alteração: A proposta visa revisar a metodologia de cálculo do "
                "valor base das sanções de multa, considerando um número significativo de usuários "
                "e adequações necessárias para o cumprimento de determinações do Conselho Diretor  </Source(1)>. \n"
                "  2. Legalidade e Regularidade: A regularidade formal do procedimento e a legalidade "
                "dos dispositivos da minuta foram atestadas pela Procuradoria Federal Especializada "
                "junto à Anatel </Source(2)>."
            )
        ],
    )
    sources: list[Source] = Field(
        default_factory=list,
        examples=[
            Source(
                index=1,
                id_documento_formatado="10066368",
                conteudo_documento=(
                    "Proposta de alteração da metodologia de Cálculo "
                    "aprovada pela Portaria nº 791, de 26 de agosto de 2014."
                ),
            ),
            Source(
                index=2,
                id_documento_formatado="10066368",
                conteudo_documento=(
                    "Regularidade formal do procedimento e legalidade dos dispositivos da minuta "
                    "atestadas pela Procuradoria Federal Especializada junto à Anatel."
                ),
            ),
        ],
    )

# Modelos de Dados / Data Models

> Schemas de request, response e modelos internos da API

**Arquivo fonte**: `sei_ia/data/pydantic_models.py`

---

## Visão Geral

Os modelos de dados do SEI-IA Assistente são organizados em 4 categorias:

| Categoria | Descrição | Exemplos |
|-----------|-----------|----------|
| **Request Models** | Entrada da API | `ChatRequest`, `FeedbackRequest` |
| **Document Models** | Estrutura de documentos | `ItemDocumentRequest`, `ItemRequestIdProcedimento` |
| **Response Models** | Saída da API | `ResponseDataModel`, `RagAnswer` |
| **Internal Models** | Estado interno (TypedDict) | `UserState`, `ItemDocument` |

---

## 1. Request Models

### ChatRequest

Modelo principal para requisições de chat. Todos os endpoints de chat recebem este modelo.

```python
class ChatRequest(BaseModel):
    # === Campos Obrigatórios ===
    id_usuario: int                    # ID do usuário
    text: str                          # Texto/pergunta do usuário

    # === Identificação da Sessão ===
    id_topico: int | None = None       # ID do tópico/sessão (para histórico)
    id_request: int | None = None      # ID único da requisição
    ip: str | None = None              # IP do cliente

    # === Documentos ===
    id_procedimentos: list[ItemRequestIdProcedimento] | None = None

    # === Configurações do Modelo ===
    system_prompt: str | None = SYSTEM_PROMPT  # Prompt de sistema customizado
    fator_limiar_rag: float = 1.0              # Multiplicador do limiar RAG

    # === Flags de Comportamento ===
    use_thinking: bool | None = None   # Usar modelo de raciocínio (think)
    use_websearch: bool = False        # Habilitar busca na web
    summarize_history: bool = False    # Sumarizar histórico longo
    skip_memory: bool = False          # Ignorar memória da sessão
```

**Exemplo de uso mínimo:**
```json
{
    "id_usuario": 1,
    "text": "Qual é o objeto deste processo?"
}
```

**Exemplo completo:**
```json
{
    "id_usuario": 1,
    "id_topico": 123,
    "text": "Qual é o objeto deste processo?",
    "id_procedimentos": [
        {
            "id_procedimento": "53500.000001/2024-00",
            "id_documentos": [
                {"id_documento": "12345678"}
            ]
        }
    ],
    "use_websearch": false,
    "skip_memory": false
}
```

**Métodos auxiliares:**

| Método | Retorno | Descrição |
|--------|---------|-----------|
| `all_documents_allowed()` | `list[str]` | Lista todos os IDs de documentos |
| `all_procs_allowed()` | `list[str]` | Lista todos os IDs de processos |

---

### FeedbackRequest

Modelo para envio de feedback sobre respostas.

```python
class FeedbackRequest(BaseModel):
    id_mensagem: int           # ID da mensagem avaliada (obrigatório)
    stars: int                 # Avaliação de 1 a 5 (obrigatório)
    comment: str | None = None # Comentário opcional
```

**Validação:** `stars` deve estar entre 1 e 5.

**Exemplo:**
```json
{
    "id_mensagem": 12345,
    "stars": 5,
    "comment": "Resposta muito útil!"
}
```

!!! note "Contrato de Paginação"
    A paginação de documentos é definida exclusivamente pelos campos
    `pag_doc_init` e `pag_doc_end` enviados no payload. O backend não
    infere paginação a partir do texto livre em `text`.

---

## 2. Document Models

Hierarquia de documentos na requisição:

```
ChatRequest
└── id_procedimentos: list[ItemRequestIdProcedimento]
    └── id_documentos: list[ItemDocumentRequest]
```

### ItemRequestIdProcedimento

Representa um processo administrativo com seus documentos.

```python
class ItemRequestIdProcedimento(BaseModel):
    id_procedimento: str       # Número do processo (ex: "53500.000001/2024-00")
    id_documentos: list[ItemDocumentRequest] | list[str]  # Documentos do processo
    metadata: dict | str = {}  # Metadados opcionais
```

**Exemplo:**
```json
{
    "id_procedimento": "53500.000001/2024-00",
    "id_documentos": [
        {"id_documento": "12345678"},
        {"id_documento": "87654321", "pag_doc_init": 1, "pag_doc_end": 10}
    ],
    "metadata": {}
}
```

---

### ItemDocumentRequest

Representa um documento individual com opções de extração.

```python
class ItemDocumentRequest(BaseModel):
    # === Identificação (obrigatório) ===
    id_documento: str                    # ID do documento no SEI

    # === Opções de Extração ===
    download_ext: bool | None = None     # Download de arquivo externo
    id_anexos: list[str] | None = None   # IDs de anexos (correspondência)
    pag_doc_init: int | None = None      # Página inicial (paginação)
    pag_doc_end: int | None = None       # Página final (paginação)

    # === Cache ===
    sin_armazena_cache: str | None = "S" # "S" = cachear, "N" = não cachear
```

**Casos de uso:**

| Cenário | Configuração |
|---------|--------------|
| Documento completo | `{"id_documento": "123"}` |
| Páginas específicas | `{"id_documento": "123", "pag_doc_init": 5, "pag_doc_end": 10}` |
| Sem cache | `{"id_documento": "123", "sin_armazena_cache": "N"}` |
| Com anexos | `{"id_documento": "123", "id_anexos": ["456", "789"]}` |

**Regra importante:**
- O campo `text` pode mencionar processos e documentos livremente.
- Apenas `pag_doc_init` e `pag_doc_end` controlam a extração parcial de páginas.
- Para página única, envie `pag_doc_init` e `pag_doc_end` com o mesmo valor.

---

## 3. Response Models

### ResponseDataModel

Modelo completo de resposta (modo não-streaming).

```python
class ResponseDataModel(BaseModel):
    # === Identificação ===
    id: str                    # UUID da resposta
    id_message: int            # ID sequencial da mensagem
    object: str                # Tipo: "chat.completion"
    created: datetime          # Timestamp de criação

    # === Modelo ===
    model: str                 # Nome do modelo usado

    # === Tokens ===
    usage: UsageModel          # Contagem de tokens

    # === Configuração ===
    initial_config: InitialConfigModel

    # === Resposta ===
    choices: list[ChoiceModel] # Lista de respostas

    # === Flags de Processamento ===
    doc_paged: bool            # Documento foi paginado?
    doc_summarized: bool       # Documento foi sumarizado?
```

---

### UsageModel

Informações de consumo de tokens.

```python
class UsageModel(BaseModel):
    prompt_tokens: int       # Tokens do prompt de entrada
    completion_tokens: int   # Tokens da resposta gerada
    total_tokens: int        # Total = prompt + completion
```

---

### RagAnswer

Resposta com fontes do RAG (Retrieval-Augmented Generation).

```python
class RagAnswer(BaseModel):
    answer: str              # Texto da resposta com marcadores </Source(N)>
    sources: list[Source]    # Lista de fontes utilizadas
```

**Exemplo:**
```json
{
    "answer": "O processo propõe uma nova metodologia... </Source(1)>",
    "sources": [
        {
            "index": 1,
            "id_documento_formatado": "10066368",
            "conteudo_documento": "Proposta de alteração da metodologia..."
        }
    ]
}
```

---

### Source

Fonte individual do RAG.

```python
class Source(BaseModel):
    index: int                      # Índice da fonte (1, 2, 3...)
    id_documento_formatado: str     # ID formatado do documento
    conteudo_documento: str         # Trecho utilizado na resposta
```

---

## 4. Internal Models (TypedDict)

Modelos internos usados durante o processamento. Não são expostos na API.

### UserState

Estado principal que acompanha toda a requisição através do workflow LangGraph.

```python
class UserState(TypedDict):
    # ╔══════════════════════════════════════════════════════════════╗
    # ║                      IDENTIFICAÇÃO                           ║
    # ╚══════════════════════════════════════════════════════════════╝
    id_request: int                    # ID único da requisição
    id_usuario: int                    # ID do usuário
    ip: str                            # IP do cliente
    endpoint_name: str                 # Nome do endpoint chamado
    id_topico: int | None              # ID da sessão/tópico

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                       DOCUMENTOS                             ║
    # ╚══════════════════════════════════════════════════════════════╝
    id_procedimentos: list[ItemRequestIdProcedimento] | None
    all_procs: list[str]               # Lista de IDs de processos
    all_documents: list[str]           # Lista de IDs de documentos

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                       REQUISIÇÃO                             ║
    # ╚══════════════════════════════════════════════════════════════╝
    user_request: str                  # Texto original do usuário
    system_prompt: str                 # Prompt de sistema
    original_request_body: str         # JSON original da requisição
    intent: Literal[...]               # Intenção detectada
    # Valores: "conversar", "pergunta", "resumo", "escrever",
    #          "reescrever", "multi_pergunta", "outras", "analise"

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                    CONFIGURAÇÃO DO MODELO                    ║
    # ╚══════════════════════════════════════════════════════════════╝
    model_type: Literal["mini", "standard", "nano", "think"]
    model_name: str                    # Nome do deployment Azure
    temperature: float                 # Temperatura do modelo
    general_max_output_tokens: int     # Limite de tokens de saída
    general_max_ctx_len: int           # Limite de contexto
    limit_rag: int                     # Limite de chunks RAG

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                     FLAGS DE COMPORTAMENTO                   ║
    # ╚══════════════════════════════════════════════════════════════╝
    use_websearch: bool                # Busca web habilitada?
    use_thinking: bool | None          # Modelo de raciocínio?
    summarize_history: bool            # Sumarizar histórico?
    skip_memory: bool                  # Ignorar memória?

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                  FLAGS DE PROCESSAMENTO                      ║
    # ╚══════════════════════════════════════════════════════════════╝
    doc_paged: bool | list             # Documento paginado?
    doc_summarized: bool               # Documento sumarizado?
    doc_rag: bool                      # Usou RAG?
    doc_false_rag: bool                # RAG não aplicável?
    has_content: bool                  # Tem conteúdo para processar?
    all_tokens_counter: int            # Contador total de tokens

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                          RAG                                 ║
    # ╚══════════════════════════════════════════════════════════════╝
    rag_method: str | None             # Método: "chunks" ou "full_doc"
    rag_documents_count: int | None    # Qtd de documentos no RAG
    rag_chunks_count: int | None       # Qtd de chunks recuperados
    rag_chunks_data: dict | None       # Dados dos chunks
    id_to_formatted_map: dict[str, str] | None  # Mapa ID -> ID formatado

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                       WEB SEARCH                             ║
    # ╚══════════════════════════════════════════════════════════════╝
    tool_web_search: list[dict] | None # Resultados da busca web

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                       DISCLAIMER                             ║
    # ╚══════════════════════════════════════════════════════════════╝
    disclaimer_case: str | None        # Caso do disclaimer
    disclaimer_text: str | None        # Texto do disclaimer

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                        PROMPT                                ║
    # ╚══════════════════════════════════════════════════════════════╝
    last_prompt: str                   # Último prompt construído

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                        RESPOSTA                              ║
    # ╚══════════════════════════════════════════════════════════════╝
    response: dict[str, Any]           # Resposta final
```

---

### ItemDocument

Documento processado durante o workflow.

```python
class ItemDocument(TypedDict):
    id_documento: str              # ID original
    id_documento_formatado: str    # ID formatado (ex: "10066368")
    content: str                   # Conteúdo extraído
    doc_tokens: int                # Contagem de tokens
    doc_paged: bool                # Foi paginado?
    pag_doc_init: int | None       # Página inicial
    pag_doc_end: int | None        # Página final
    download_ext: bool | None      # Download externo?
    id_anexos: list[str] | None    # Anexos
    metadata: dict                 # Metadados do SEI
    sin_armazena_cache: str | None # Flag de cache
```

---

## 5. Streaming Events (SSE)

Formato dos eventos Server-Sent Events para streaming.

### Tipos de Eventos

| Tipo | Descrição | Quando ocorre |
|------|-----------|---------------|
| `content` | Chunk de texto | Durante geração |
| `metadata` | Informações finais | Ao concluir |
| `end` | Fim do stream | Final |

### Content Event
```json
{"type": "content", "data": "texto parcial...", "timestamp": 1704067200.123}
```

### Metadata Event
```json
{
    "type": "metadata",
    "data": {
        "id": "uuid-da-resposta",
        "id_message": 12345,
        "usage": {"prompt_tokens": 1500, "completion_tokens": 200, "total_tokens": 1700},
        "model": "standard",
        "doc_rag": true,
        "doc_paged": false,
        "doc_summarized": false,
        "rag_method": "chunks",
        "sources_count": 3
    },
    "timestamp": 1704067230.456
}
```

### End Event
```json
{"type": "end", "data": "Stream completed", "timestamp": 1704067230.789}
```

---

## Próximos Passos

- [Endpoints](endpoints.md) - Como usar os modelos na API
- [Exemplos](examples.md) - Exemplos práticos

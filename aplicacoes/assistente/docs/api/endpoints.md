# Endpoints da API

> Documentação completa dos endpoints REST

## Visão Geral

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Health check |
| POST | `/llm_lang/chat_gpt_4o_mini_128k` | Chat com modelo **mini** |
| POST | `/llm_lang/session_stream` | Chat com sessão e resposta streaming SSE (único streaming publicado) |
| POST | `/feedback/feedback` | Enviar feedback |
| GET | `/tests` | Executar testes internos |

!!! warning "Nome de Endpoint Legado"
    O nome do endpoint contém "gpt_4o_mini" por razão histórica.
    A família GPT-4o **não é mais utilizada diretamente**.

    - `chat_gpt_4o_mini_128k` → usa `model_type="mini"`

    O model type é mapeado para o modelo atual configurado no Azure OpenAI.

!!! info "Streaming publicado"
    O endpoint de streaming da API é `/llm_lang/session_stream`.

---

## Health Check

### GET /health

Verifica o status da aplicação.

**Response**

```json
{
    "status": "OK"
}
```

**Status Codes**

| Code | Descrição |
|------|-----------|
| 200 | Aplicação saudável |
| 500 | Erro interno |

---

## Chat Endpoints

### POST /llm_lang/chat_gpt_4o_mini_128k

Chat usando o modelo **mini** (mais rápido e econômico).

!!! note "Nome Legado"
    O nome "gpt_4o_mini_128k" é histórico. Este endpoint usa `model_type="mini"`.

**Request Body**

```json
{
    "id_usuario": 1,
    "id_topico": 123,
    "text": "Qual é o objeto deste processo?",
    "system_prompt": null,
    "fator_limiar_rag": 1.0,
    "id_procedimentos": [
        {
            "id_procedimento": "00000.000000/0000-00",
            "id_documentos": [
                {
                    "id_documento": "12345678",
                    "download_ext": false,
                    "pag_doc_init": null,
                    "pag_doc_end": null
                }
            ],
            "metadata": {}
        }
    ],
    "use_thinking": false,
    "use_websearch": false,
    "summarize_history": false,
    "skip_memory": false
}
```

**Parâmetros**

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| id_usuario | int | Sim | ID do usuário |
| id_topico | int | Não | ID do tópico/sessão |
| text | string | Sim | Pergunta ou comando |
| system_prompt | string | Não | Prompt de sistema customizado |
| fator_limiar_rag | float | Não | Fator de limiar para RAG (default: 1.0) |
| id_procedimentos | array | Não | Lista de processos e documentos |
| use_thinking | bool | Não | Usar modelo de raciocínio |
| use_websearch | bool | Não | Habilitar busca web |
| summarize_history | bool | Não | Sumarizar histórico |
| skip_memory | bool | Não | Ignorar memória de sessão |

!!! note "Paginação de documentos"
    Quando o frontend quiser processar apenas parte de um documento, deve
    enviar `pag_doc_init` e `pag_doc_end` dentro de `id_documentos[]`.
    O backend não usa o conteúdo de `text` para inferir paginação.

**Response (JSON)**

```json
{
    "response": "O objeto do processo é...",
    "usage": {
        "prompt_tokens": 1500,
        "completion_tokens": 200,
        "total_tokens": 1700
    },
    "model": "mini",
    "doc_paged": false,
    "doc_summarized": false,
    "doc_rag": false
}
```

---

## Chat em streaming por sessão

### POST /llm_lang/session_stream

Executa o agente com filesystem escopado à sessão e responde como Server-Sent
Events (SSE). `id_topico` é obrigatório neste endpoint, pois identifica a
sessão que será criada ou retomada.

**Request Body (mínimo)**

```json
{
    "id_usuario": 1,
    "id_topico": 123,
    "text": "Oi",
    "id_procedimentos": [],
    "use_thinking": false,
    "use_websearch": false
}
```

**Parâmetros principais**

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| id_usuario | int | Sim | ID do usuário |
| id_topico | int | Sim | ID da sessão/tópico |
| text | string | Sim | Pergunta ou comando |
| id_procedimentos | array | Não | Processos e documentos a materializar na sessão |
| use_thinking | bool | Não | Solicitar reasoning de nível mais alto |
| use_websearch | bool | Não | Habilitar busca web |
| skip_memory | bool | Não | Ignorar o histórico da sessão no turno |
| arquivos_avulsos | array | Não | Metadados de arquivos anexados |

**Response (SSE)**

Cada evento chega como `data: {json}\n\n`, com `type` entre `status`,
`reasoning`, `content`, `metadata`, `end` e `error`. Uma resposta concluída
contém os frames `metadata` e `end`; falhas depois do início do stream chegam
como `error`, com `status_code` e `detail` no payload. O cliente deve tratar o
stream como `text/event-stream`, e não como um JSON único.

```text
data: {"type":"status", ...}

data: {"type":"content", ...}

data: {"type":"metadata", ...}

data: {"type":"end", ...}
```

---

## Feedback

### POST /feedback/feedback

Envia feedback sobre uma resposta.

**Request Body**

```json
{
    "id_mensagem": 12345,
    "stars": 5,
    "comment": "Resposta muito útil e precisa!"
}
```

**Parâmetros**

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| id_mensagem | int | Sim | ID da mensagem avaliada |
| stars | int | Sim | Avaliação (1-5 estrelas) |
| comment | string | Não | Comentário opcional |

**Validações**:
- `stars` deve estar entre 1 e 5

**Response**

```json
{
    "success": true,
    "message": "Feedback registrado com sucesso"
}
```

---

## Testes

### GET /tests

Executa bateria de testes internos.

**Query Parameters**

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| cached | bool | Usar cache nos testes |

**Response**

```json
{
    "tests_passed": 10,
    "tests_failed": 0,
    "details": [...]
}
```

---

## Códigos de Erro

| Código | Descrição |
|--------|-----------|
| 200 | Sucesso |
| 204 | Sem conteúdo |
| 400 | Request inválido |
| 401 | Não autorizado |
| 404 | Não encontrado |
| 408 | Timeout |
| 413 | Contexto muito grande |
| 429 | Rate limit excedido |
| 500 | Erro interno |
| 503 | Serviço indisponível |

---

## Headers

### Request Headers

| Header | Descrição |
|--------|-----------|
| Content-Type | application/json |
| Accept | application/json ou text/event-stream |

### Response Headers

| Header | Descrição |
|--------|-----------|
| X-Trace-ID | ID de rastreamento da requisição |
| Content-Type | application/json ou text/event-stream |

---

## Rate Limiting

- Limite: 30 requisições por segundo (configurável)
- Header `Retry-After` indica tempo de espera

---

## Documentação Interativa

- **Swagger UI**: http://localhost:8088/docs
- **ReDoc**: http://localhost:8088/

---

## Próximos Passos

- [Modelos de Dados](models.md)
- [Exemplos de Uso](examples.md)

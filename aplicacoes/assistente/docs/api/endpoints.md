# Endpoints da API

> Documentação completa dos endpoints REST

## Visão Geral

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Health check |
| POST | `/llm_lang/chat_gpt_4o_128k` | Chat com modelo **standard** |
| POST | `/llm_lang/chat_gpt_4o_mini_128k` | Chat com modelo **mini** |
| POST | `/feedback/feedback` | Enviar feedback |
| GET | `/tests` | Executar testes internos |

!!! warning "Nomes de Endpoints Legados"
    Os nomes dos endpoints contêm "gpt_4o" por razões históricas.
    A família GPT-4o **não é mais utilizada diretamente**.

    - `chat_gpt_4o_128k` → usa `model_type="standard"`
    - `chat_gpt_4o_mini_128k` → usa `model_type="mini"`

    Os model types são mapeados para os modelos atuais configurados no Azure OpenAI.

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

### GET /health/websearch

Verifica se a configuração de web search está ativa.

**Response**

```json
{
    "websearch_enabled": true,
    "agent_id": "xxx-xxx-xxx"
}
```

---

## Chat Endpoints

### POST /llm_lang/chat_gpt_4o_128k

Chat usando o modelo **standard**.

!!! note "Nome Legado"
    O nome "gpt_4o_128k" é histórico. Este endpoint usa `model_type="standard"`.

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
            "id_procedimento": "53500.000001/2024-00",
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

**Response (Streaming SSE)**

```
data: {"type": "content", "data": "O objeto do processo"}
data: {"type": "content", "data": " é a análise..."}
data: {"type": "metadata", "data": {"tokens_used": 150, "model": "standard"}}
data: {"type": "end", "timestamp": 1704067200}
```

**Response (JSON)**

```json
{
    "response": "O objeto do processo é...",
    "usage": {
        "prompt_tokens": 1500,
        "completion_tokens": 200,
        "total_tokens": 1700
    },
    "model": "standard",
    "doc_paged": false,
    "doc_summarized": false,
    "doc_rag": false
}
```

---

### POST /llm_lang/chat_gpt_4o_mini_128k

Chat usando o modelo **mini** (mais rápido e econômico).

!!! note "Nome Legado"
    O nome "gpt_4o_mini_128k" é histórico. Este endpoint usa `model_type="mini"`.

**Request Body**: Mesmo schema de `/llm_lang/chat_gpt_4o_128k`

**Diferenças**:
- `model_type`: mini
- Mais rápido e econômico
- Ideal para tarefas simples

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

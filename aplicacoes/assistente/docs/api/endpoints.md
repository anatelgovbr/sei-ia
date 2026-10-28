# Endpoints da API

> Documentação completa dos endpoints REST

## Visão Geral

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Health check |
| POST | `/llm_lang/session_stream` | Chat com sessão e resposta streaming SSE (único streaming publicado) |
| POST | `/feedback/feedback` | Enviar feedback |
| GET | `/tests` | Executar testes internos |

!!! info "Chat publicado"
    O único endpoint de chat é `/llm_lang/session_stream`, com resposta SSE.
    Os tiers internos de modelos, incluindo `mini`, continuam disponíveis aos agentes.

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

## Chat em streaming por sessão

### POST /llm_lang/session_stream

Executa o agente em uma sessão persistente e responde como Server-Sent Events
(SSE). `id_topico` é obrigatório neste endpoint, pois identifica a sessão que
será criada ou retomada.

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
| no_cache | bool | Não | Reseta a sessão e invalida caches documentais; mantenha `false` para continuidade |

Os IDs dos exemplos são ilustrativos. Use usuário, tópico e documentos autorizados.
Para retomar uma conversa, mantenha `id_usuario` e `id_topico` e envie `no_cache: false`.
Campos de paginação `pag_doc_init` e `pag_doc_end` pertencem a cada item de
`id_procedimentos[].id_documentos[]`; mencionar páginas no texto não controla a extração.
A paginação de documentos externos exige `download_ext: true` e formato suportado
(PDF ou planilha); o OCR respeita o mesmo intervalo solicitado.
Limites de página persistem no manifesto da sessão (`session.json`); alterar o intervalo
invalida o arquivo materializado e força extração fresca. Omissão de intervalo no payload
explícito solicita o documento inteiro; documentos voláteis implícitos herdam o intervalo persistido.
Uploads de texto e áudio entram no conteúdo do turno; áudio disponível também
adiciona ao prompt a instrução de tratar a transcrição como fala do usuário.
Imagens disponíveis seguem como mídia multimodal e adicionam a instrução
correspondente. Essas instruções não são adicionadas para uploads de texto puro.

Falhas isoladas de upload não encerram a sessão. O agente recebe um marcador de
conteúdo indisponível e os metadados finais registram o estado sanitizado de cada
upload. Uma falha do serviço de transcrição usa `reason="transcription_failed"`;
timeouts usam `reason="timeout"`. O arquivo com falha permanece no SEI para retry.

Quando `use_websearch=true`, cada fonte coletada recebe um marcador estável
`<web_N>` visível ao modelo. O stream converte os marcadores usados na resposta
em links de fonte; o marcador interno não é enviado ao cliente.

**Manifesto da sessão**

O manifesto materializado usa uma árvore de processos. Não há um índice plano de
documentos no nível raiz. Os metadados de processo ficam em
`processos[].metadata`, e os metadados de cada documento ficam em
`processos[].documentos[].metadata`. Ambos os campos são opcionais. Quando a
origem não fornece metadados, o endpoint não infere nem cria valores para
preenchê-los.

**Response (SSE)**

Cada evento chega como `data: {json}\n\n`, com `type` entre `status`,
`reasoning`, `content`, `metadata`, `end` e `error`. Em uma resposta concluída
com sucesso, os dois últimos frames são sempre, nesta ordem, `metadata` e `end`.
Falhas depois do início do stream chegam como `error`, com `status_code` e
`detail` no payload. O cliente deve tratar o stream como `text/event-stream`, e
não como um JSON único.

O campo `data.mode` do frame `metadata` de finalização informa o modo usado no turno:

| Valor | Comportamento observado |
|-------|-------------------------|
| `injected` | O conteúdo dos documentos foi incluído diretamente no contexto do modelo |
| `filesystem` | Os documentos foram materializados no filesystem da sessão para consulta pelo agente |

O campo `data.uploads` lista o resultado de cada upload deste turno sem expor
conteúdo nem mensagens internas dos serviços:

```json
[
    {
        "id": 1202,
        "name": "reuniao.wav",
        "type": "audio",
        "state": "unavailable",
        "reason": "transcription_failed"
    }
]
```

Exemplo reduzido dos dois frames finais de uma resposta concluída:

```text
data: {"type":"metadata","data":{"mode":"injected"},"timestamp":1704067230.456}

data: {"type":"end","data":"Stream completed","timestamp":1704067230.789}
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

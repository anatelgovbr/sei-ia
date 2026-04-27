# Quickstart

> Guia rápido para começar a usar o SEI-IA Assistente

## Pré-requisitos

Certifique-se de ter completado a [Instalação](installation.md) e configurado as [Variáveis de Ambiente](environment.md).

---

## Iniciando a Aplicação

### Desenvolvimento

```bash
# Com uvicorn (hot reload)
uv run uvicorn sei_ia.main:app --reload --port 8088
```

### Produção

```bash
# Com gunicorn
uv run gunicorn sei_ia.main:app -c sei_ia/configs/gunicorn_conf.py
```

### Docker

```bash
docker-compose -f docker-compose-local.yml up -d
```

---

## Verificando o Status

### Health Check

```bash
curl http://localhost:8088/health
```

Resposta esperada:
```json
{"status": "OK"}
```

---

## Primeira Requisição

### Endpoint de Chat Básico

```bash
curl -X POST http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k \
  -H "Content-Type: application/json" \
  -d '{
    "id_usuario": 1,
    "text": "Qual é a capital do Brasil?",
    "system_prompt": null,
    "id_procedimentos": null
  }'
```

### Resposta Esperada

```json
{
  "response": "A capital do Brasil é Brasília...",
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 25,
    "total_tokens": 75
  }
}
```

---

## Chat com Documentos

Para fazer perguntas sobre documentos do SEI:

```bash
curl -X POST http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k \
  -H "Content-Type: application/json" \
  -d '{
    "id_usuario": 1,
    "text": "Qual é o objeto deste processo?",
    "id_procedimentos": [
      {
        "id_procedimento": "53500.000001/2024-00",
        "id_documentos": [
          {
            "id_documento": "12345678"
          }
        ]
      }
    ]
  }'
```

---

## Chat com Busca Web

Para habilitar busca web via Bing, use o parâmetro `use_websearch: true`:

```bash
curl -X POST http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k \
  -H "Content-Type: application/json" \
  -d '{
    "id_usuario": 1,
    "text": "Quais são as últimas notícias sobre telecomunicações no Brasil?",
    "use_websearch": true
  }'
```

---

## Streaming de Respostas

O sistema suporta Server-Sent Events (SSE) para streaming:

```python
import httpx

with httpx.stream(
    "POST",
    "http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k",
    json={
        "id_usuario": 1,
        "text": "Explique o que é inteligência artificial"
    },
    headers={"Accept": "text/event-stream"}
) as response:
    for line in response.iter_lines():
        if line.startswith("data:"):
            print(line[5:])
```

Formato do streaming:
```
data: {"type": "content", "data": "A inteligência"}
data: {"type": "content", "data": " artificial é..."}
data: {"type": "metadata", "data": {"tokens": 150}}
data: {"type": "end", "timestamp": 1234567890}
```

---

## Enviando Feedback

Após receber uma resposta, você pode enviar feedback:

```bash
curl -X POST http://localhost:8088/feedback/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "id_mensagem": 12345,
    "stars": 5,
    "comment": "Resposta muito útil!"
  }'
```

---

## Endpoints Disponíveis

| Método | Endpoint | Model Type |
|--------|----------|------------|
| GET | `/health` | - |
| POST | `/llm_lang/chat_gpt_4o_128k` | standard |
| POST | `/llm_lang/chat_gpt_4o_mini_128k` | mini |
| POST | `/feedback/feedback` | - |

> **Nota**: Os nomes dos endpoints contêm "gpt_4o" por razões históricas (legado).

---

## Documentação Interativa

Acesse a documentação Swagger para testar os endpoints:

- **Swagger UI**: http://localhost:8088/docs
- **ReDoc**: http://localhost:8088/

---

## Próximos Passos

- [Arquitetura](../architecture/overview.md) - Entenda como o sistema funciona
- [API Completa](../api/endpoints.md) - Veja todos os parâmetros disponíveis
- [Sistema RAG](../rag-system/overview.md) - Entenda a busca semântica

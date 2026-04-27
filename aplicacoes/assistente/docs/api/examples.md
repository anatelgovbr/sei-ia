# Exemplos de Uso / Usage Examples

> Exemplos práticos de como usar a API do SEI-IA Assistente

## Ferramentas

Os exemplos usam `curl` e `Python (httpx)`. Adapte conforme necessário.

---

## 1. Health Check

### curl

```bash
curl http://localhost:8088/health
```

### Python

```python
import httpx

response = httpx.get("http://localhost:8088/health")
print(response.json())
# {"status": "OK"}
```

---

## 2. Chat Simples (sem documentos)

### curl

```bash
curl -X POST http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k \
  -H "Content-Type: application/json" \
  -d '{
    "id_usuario": 1,
    "text": "O que é o SEI?"
  }'
```

### Python

```python
import httpx

response = httpx.post(
    "http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k",
    json={
        "id_usuario": 1,
        "text": "O que é o SEI?"
    }
)
print(response.json()["response"])
```

---

## 3. Chat com Documento

### curl

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
          {"id_documento": "12345678"}
        ]
      }
    ]
  }'
```

### Python

```python
import httpx

response = httpx.post(
    "http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k",
    json={
        "id_usuario": 1,
        "text": "Qual é o objeto deste processo?",
        "id_procedimentos": [
            {
                "id_procedimento": "53500.000001/2024-00",
                "id_documentos": [
                    {"id_documento": "12345678"}
                ]
            }
        ]
    },
    timeout=120.0
)
print(response.json()["response"])
```

---

## 4. Chat com Múltiplos Documentos

```python
import httpx

response = httpx.post(
    "http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k",
    json={
        "id_usuario": 1,
        "text": "Compare os dois documentos e liste as principais diferenças",
        "id_procedimentos": [
            {
                "id_procedimento": "53500.000001/2024-00",
                "id_documentos": [
                    {"id_documento": "12345678"},
                    {"id_documento": "87654321"}
                ]
            }
        ]
    },
    timeout=300.0
)
```

!!! note "Fonte de verdade"
    Neste fluxo, a paginação vem exclusivamente do payload (`pag_doc_init`
    e `pag_doc_end`). O campo `text` pode mencionar processos ou documentos,
    mas não controla a extração parcial de páginas.

---

## 5. Chat com Paginação de Documento

Extrair apenas páginas específicas de um documento:

```python
import httpx

response = httpx.post(
    "http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k",
    json={
        "id_usuario": 1,
        "text": "Resuma o conteúdo das páginas 5 a 10",
        "id_procedimentos": [
            {
                "id_procedimento": "53500.000001/2024-00",
                "id_documentos": [
                    {
                        "id_documento": "12345678",
                        "pag_doc_init": 5,
                        "pag_doc_end": 10
                    }
                ]
            }
        ]
    }
)
```

---

## 6. Chat com Busca Web

Use o parâmetro `use_websearch: true` em qualquer endpoint de chat para habilitar busca web via Bing:

```bash
curl -X POST http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k \
  -H "Content-Type: application/json" \
  -d '{
    "id_usuario": 1,
    "text": "Quais são as últimas notícias sobre leilão de 5G no Brasil?",
    "use_websearch": true
  }'
```

---

## 7. Chat com Streaming

### Python (SSE)

```python
import httpx

with httpx.stream(
    "POST",
    "http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k",
    json={
        "id_usuario": 1,
        "text": "Explique o que é inteligência artificial em 3 parágrafos"
    },
    headers={"Accept": "text/event-stream"},
    timeout=120.0
) as response:
    for line in response.iter_lines():
        if line.startswith("data:"):
            data = line[5:].strip()
            print(data)
```

### Parsing do SSE

```python
import json

def parse_sse_event(line: str) -> dict | None:
    if line.startswith("data:"):
        try:
            return json.loads(line[5:].strip())
        except json.JSONDecodeError:
            return None
    return None

# Uso
event = parse_sse_event('data: {"type": "content", "data": "Olá"}')
if event and event["type"] == "content":
    print(event["data"])
```

---

## 8. Sumarização de Documento

```python
import httpx

response = httpx.post(
    "http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k",
    json={
        "id_usuario": 1,
        "text": "Faça um resumo executivo deste documento",
        "id_procedimentos": [
            {
                "id_procedimento": "53500.000001/2024-00",
                "id_documentos": [
                    {"id_documento": "12345678"}
                ]
            }
        ]
    },
    timeout=300.0
)

result = response.json()
print(f"Documento sumarizado: {result.get('doc_summarized')}")
print(result["response"])
```

---

## 9. Correção Gramatical

```python
import httpx

response = httpx.post(
    "http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k",
    json={
        "id_usuario": 1,
        "text": "Corrija o seguinte texto: 'A empresa nao cumpriu com as obrigaçoes contratuais estabelecida no edital de licitaçao.'"
    }
)

print(response.json()["response"])
```

---

## 10. Envio de Feedback

```bash
curl -X POST http://localhost:8088/feedback/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "id_mensagem": 12345,
    "stars": 5,
    "comment": "Resposta muito precisa e útil!"
  }'
```

---

## 11. Usando System Prompt Customizado

```python
import httpx

custom_prompt = """
Você é um especialista em telecomunicações.
Responda sempre de forma técnica e cite normas quando aplicável.
"""

response = httpx.post(
    "http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k",
    json={
        "id_usuario": 1,
        "text": "Explique o processo de outorga de radiofrequência",
        "system_prompt": custom_prompt
    }
)
```

---

## 12. Tratamento de Erros

### Códigos de Erro HTTP

| Código | Nome | Descrição | Solução |
|--------|------|-----------|---------|
| 400 | Bad Request | Payload inválido ou campos obrigatórios ausentes | Verificar formato do JSON e campos `id_usuario`, `text` |
| 401 | Unauthorized | Autenticação falhou | Verificar credenciais/token |
| 403 | Forbidden | Sem permissão para acessar o recurso | Verificar permissões do usuário |
| 404 | Not Found | Endpoint ou documento não encontrado | Verificar URL e ID do documento |
| 408 | Request Timeout | Requisição demorou demais no servidor | Aumentar timeout ou simplificar a requisição |
| 413 | Payload Too Large | Documento muito grande para processar | Usar paginação (`pag_doc_init`, `pag_doc_end`) |
| 422 | Unprocessable Entity | Dados válidos mas semanticamente incorretos | Verificar valores dos campos (ex: `stars` entre 1-5) |
| 429 | Too Many Requests | Rate limit excedido | Aguardar e tentar novamente com backoff |
| 500 | Internal Server Error | Erro interno do servidor | Verificar logs, reportar se persistir |
| 502 | Bad Gateway | Erro de comunicação com serviços externos | Verificar conectividade com Azure OpenAI/SEI |
| 503 | Service Unavailable | Serviço temporariamente indisponível | Aguardar e tentar novamente |
| 504 | Gateway Timeout | Timeout na comunicação com serviços externos | Aumentar timeout ou simplificar a requisição |

### Erros de Cliente (httpx)

| Exceção | Descrição | Solução |
|---------|-----------|---------|
| `httpx.TimeoutException` | Timeout na requisição | Aumentar `timeout` (padrão: 120s para chat) |
| `httpx.ConnectError` | Falha ao conectar no servidor | Verificar URL e conectividade de rede |
| `httpx.ReadError` | Erro ao ler resposta | Verificar estabilidade da conexão |
| `httpx.HTTPStatusError` | Resposta com código de erro HTTP | Tratar conforme tabela acima |

### Exemplo de Tratamento Completo

```python
import httpx
import time

def chat_with_retry(payload: dict, max_retries: int = 3) -> dict:
    """Realiza chat com retry automático para erros recuperáveis."""

    for attempt in range(max_retries):
        try:
            response = httpx.post(
                "http://localhost:8088/llm_lang/chat_gpt_4o_mini_128k",
                json=payload,
                timeout=120.0
            )
            response.raise_for_status()
            return response.json()

        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Backoff exponencial
                continue
            raise Exception("Timeout após múltiplas tentativas")

        except httpx.HTTPStatusError as e:
            status = e.response.status_code

            if status == 400:
                raise ValueError(f"Payload inválido: {e.response.text}")
            elif status == 413:
                raise ValueError("Documento muito grande - use paginação")
            elif status == 422:
                raise ValueError(f"Dados inválidos: {e.response.text}")
            elif status == 429:
                # Rate limit - aguardar e tentar novamente
                retry_after = int(e.response.headers.get("Retry-After", 5))
                time.sleep(retry_after)
                continue
            elif status in (500, 502, 503, 504):
                # Erros de servidor - retry com backoff
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise Exception(f"Erro de servidor persistente: {status}")
            else:
                raise

        except httpx.RequestError as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise Exception(f"Erro de conexão: {e}")

    raise Exception("Máximo de tentativas excedido")


# Uso
try:
    result = chat_with_retry({
        "id_usuario": 1,
        "text": "Qual é o objeto deste processo?"
    })
    print(result["response"])
except ValueError as e:
    print(f"Erro de validação: {e}")
except Exception as e:
    print(f"Erro: {e}")
```

### Validação de Payload

Erros comuns de validação (422):

| Campo | Erro | Solução |
|-------|------|---------|
| `id_usuario` | Campo obrigatório | Sempre incluir ID do usuário |
| `text` | Campo obrigatório | Sempre incluir texto da pergunta |
| `stars` | Valor fora do range 1-5 | Usar valores entre 1 e 5 |
| `id_documento` | Formato inválido | Usar apenas números como string |
| `pag_doc_init` / `pag_doc_end` | Valores inconsistentes | `pag_doc_end` >= `pag_doc_init` |

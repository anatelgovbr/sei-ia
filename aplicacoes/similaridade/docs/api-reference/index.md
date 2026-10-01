# API Reference

Referência completa dos endpoints da API sei-similaridade.

---

## Base URL

```
http://localhost:8000
```

---

## Documentação Interativa

Após iniciar a aplicação, acesse a documentação interativa:

| Interface | URL | Descrição |
|-----------|-----|-----------|
| **Swagger UI** | `/docs` | Interface interativa para testar endpoints |
| **ReDoc** | `/redoc` | Documentação estática formatada |
| **OpenAPI JSON** | `/openapi.json` | Schema OpenAPI 3.0 |

---

## Endpoints

### Recomendação de Processos (WMLT)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/process-recommenders/weighted-mlt-recommender/recommendations/{id_protocolo}` | Buscar processos similares |
| GET | `/process-recommenders/weighted-mlt-recommender/indexed-ids/{id_protocolo}` | Verificar se protocolo está indexado |

### Busca de Jurisprudência (Doc2Doc)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/document-recommenders/mlt-recommender/recommendations` | Buscar documentos similares |

### Health Check

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Verificar saúde da API |
| GET | `/teste` | Executar testes automatizados |

---

## Detalhamento dos Endpoints

### GET /process-recommenders/weighted-mlt-recommender/recommendations/{id_protocolo}

Busca processos similares usando WMLT.

**Parâmetros:**

| Nome | Tipo | Local | Obrigatório | Descrição |
|------|------|-------|-------------|-----------|
| `id_protocolo` | string | path | Sim | ID do processo (17-20 dígitos) |
| `rows` | int | query | Não | Quantidade de resultados (default: 10) |
| `debug` | bool | query | Não | Retornar info de debug (default: false) |
| `extraction_method` | string | query | Não | Método: `solr` ou `bm25` (default: solr) |
| `id_user` | int | query | Não | ID do usuário para auditoria |

**Exemplo:**

```bash
curl "http://localhost:8000/process-recommenders/weighted-mlt-recommender/recommendations/53500123456202400?rows=5"
```

**Resposta (200 OK):**

```json
{
  "id": 42,
  "recommendations": [
    {"id_protocolo": "53500987654202400", "score": 1.00},
    {"id_protocolo": "53500111222202300", "score": 0.87},
    {"id_protocolo": "53500333444202300", "score": 0.72}
  ]
}
```

---

### GET /process-recommenders/weighted-mlt-recommender/indexed-ids/{id_protocolo}

Verifica se um protocolo está indexado no Solr.

**Parâmetros:**

| Nome | Tipo | Local | Obrigatório | Descrição |
|------|------|-------|-------------|-----------|
| `id_protocolo` | string | path | Sim | ID do processo |

**Exemplo:**

```bash
curl "http://localhost:8000/process-recommenders/weighted-mlt-recommender/indexed-ids/53500123456202400"
```

**Resposta (200 OK):**

```json
{
  "indexed": true,
  "id_protocolo": "53500123456202400"
}
```

---

### GET /document-recommenders/mlt-recommender/recommendations

Busca documentos de jurisprudência similares.

**Parâmetros:**

| Nome | Tipo | Local | Obrigatório | Descrição |
|------|------|-------|-------------|-----------|
| `text` | string | query | Não* | Texto livre para busca |
| `list_id_doc` | list[int] | query | Não* | IDs de documentos de referência |
| `list_type_id_doc` | list[int] | query | Não | Filtrar por tipos de documento |
| `text_weight` | float | query | Não | Peso do texto vs docs (default: 0.5) |
| `rows` | int | query | Não | Quantidade de resultados (default: 10) |
| `normalized` | bool | query | Não | Normalizar scores [0,1] (default: false) |
| `include_citations` | bool | query | Não | Incluir citações (default: false) |
| `id_user` | int | query | Não | ID do usuário para auditoria |

!!! warning "Entrada Obrigatória"
    Pelo menos `text` ou `list_id_doc` deve ser fornecido.

**Exemplo - Busca por Texto:**

```bash
curl "http://localhost:8000/document-recommenders/mlt-recommender/recommendations?text=recurso+administrativo&rows=5"
```

**Exemplo - Busca por Documentos:**

```bash
curl "http://localhost:8000/document-recommenders/mlt-recommender/recommendations?list_id_doc=135629&list_id_doc=135630"
```

**Exemplo - Busca Combinada:**

```bash
curl "http://localhost:8000/document-recommenders/mlt-recommender/recommendations?text=multa&list_id_doc=135629&text_weight=0.7&normalized=true"
```

**Resposta (200 OK):**

```json
{
  "id_recommendation": 123,
  "recommendation": [
    {
      "id_document": 135700,
      "id_type_document": 8,
      "score": 1.00
    },
    {
      "id_document": 135701,
      "id_type_document": 7,
      "score": 0.85
    }
  ]
}
```

---

### GET /health

Verifica a saúde da API.

**Exemplo:**

```bash
curl "http://localhost:8000/health"
```

**Resposta (200 OK):**

```json
{
  "status": "ok"
}
```

---

### GET /teste

Executa bateria de testes automatizados.

**Exemplo:**

```bash
curl "http://localhost:8000/teste"
```

**Resposta (200 OK):**

```json
{
  "status": "success",
  "tests_passed": 15,
  "tests_failed": 0,
  "duration_ms": 1234
}
```

---

## Códigos de Resposta

| Código | Descrição |
|--------|-----------|
| **200** | Sucesso |
| **400** | Parâmetros inválidos |
| **404** | Documento não encontrado |
| **500** | Erro interno do servidor |
| **503** | Serviço indisponível (Solr offline) |

---

## Erros Comuns

### 400 - Parâmetros Inválidos

```json
{
  "detail": "id_protocolo must be 17-20 digits"
}
```

### 404 - Documento Não Encontrado

```json
{
  "detail": "Protocol 53500123456202400 not found in Solr"
}
```

### 503 - Solr Indisponível

```json
{
  "detail": "Solr service unavailable"
}
```

---

## Autenticação

Se `USE_AUTHENTICATION=true`, a API requer token JWT:

```bash
curl -H "Authorization: Bearer {token}" "http://localhost:8000/..."
```

### Obter Token

```bash
curl -X POST "http://localhost:8000/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user&password=pass"
```

---

## Rate Limiting

A API não possui rate limiting nativo. Recomenda-se usar um proxy reverso (nginx, traefik) para controle de taxa.

---

## Próximos Passos

- [WMLT](../wmlt/index.md) - Detalhes sobre recomendação de processos
- [Doc2Doc](../doc2doc/index.md) - Detalhes sobre busca de jurisprudência
- [Variáveis de Ambiente](../getting-started/environment-variables.md) - Configuração

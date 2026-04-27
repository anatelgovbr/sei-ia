# PostgreSQL

O PostgreSQL armazena logs, recomendações e configurações do sistema.

---

## Visão Geral

| Aspecto | Valor |
|---------|-------|
| **Versão** | 15+ |
| **ORM** | SQLAlchemy 2.0+ |
| **Driver** | psycopg2 |

---

## Tabelas

O sistema usa as seguintes tabelas:

| Tabela | Propósito |
|--------|-----------|
| `log_consume` | Auditoria de requisições |
| `process_weighted_mlt_recommendation` | Recomendações WMLT |
| `document_mlt_recommendation` | Recomendações Doc2Doc |
| `config_mlt_fields_weights` | Configuração de pesos |

---

## log_consume

Registra todas as requisições feitas à API para auditoria.

### Schema

```sql
CREATE TABLE log_consume (
    id SERIAL PRIMARY KEY,
    time_created TIMESTAMP DEFAULT NOW(),
    api_recomend_url TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    id_protocol BIGINT[] NOT NULL,
    id_user BIGINT
);
```

### Colunas

| Coluna | Tipo | Nullable | Descrição |
|--------|------|----------|-----------|
| `id` | SERIAL | NO | ID único |
| `time_created` | TIMESTAMP | NO | Data/hora da requisição |
| `api_recomend_url` | TEXT | NO | Endpoint acessado |
| `status_code` | INTEGER | NO | Código HTTP de resposta |
| `id_protocol` | BIGINT[] | NO | IDs de protocolo consultados |
| `id_user` | BIGINT | YES | ID do usuário (se autenticado) |

### Exemplo

```sql
SELECT * FROM log_consume ORDER BY time_created DESC LIMIT 5;
```

| id | time_created | api_recomend_url | status_code | id_protocol |
|----|--------------|------------------|-------------|-------------|
| 42 | 2024-01-15 10:30:00 | /wmlt/123... | 200 | {123...} |
| 41 | 2024-01-15 10:29:55 | /doc2doc | 200 | {135629} |

---

## process_weighted_mlt_recommendation

Armazena recomendações do WMLT para histórico e auditoria.

### Schema

```sql
CREATE TABLE process_weighted_mlt_recommendation (
    id_recommendation SERIAL PRIMARY KEY,
    id_protocolo VARCHAR NOT NULL,
    id_user BIGINT,
    rows INTEGER DEFAULT 10,
    parsedquery_field VARCHAR,
    id_field VARCHAR NOT NULL,
    fq VARCHAR[],
    debug BOOLEAN DEFAULT FALSE,
    extraction_method VARCHAR,
    recommendation JSON,
    created_at TIMESTAMP DEFAULT NOW(),
    requested_at TIMESTAMP
);
```

### Colunas

| Coluna | Tipo | Nullable | Descrição |
|--------|------|----------|-----------|
| `id_recommendation` | SERIAL | NO | ID único da recomendação |
| `id_protocolo` | VARCHAR | NO | Protocolo consultado |
| `id_user` | BIGINT | YES | Usuário que fez a requisição |
| `rows` | INTEGER | NO | Quantidade de resultados |
| `parsedquery_field` | VARCHAR | YES | Campo de parsed query usado |
| `id_field` | VARCHAR | NO | Campo de ID usado |
| `fq` | VARCHAR[] | YES | Filter queries aplicados |
| `debug` | BOOLEAN | NO | Se debug estava ativo |
| `extraction_method` | VARCHAR | YES | Método: solr ou bm25 |
| `recommendation` | JSON | YES | Resultado da recomendação |
| `created_at` | TIMESTAMP | NO | Data de criação |
| `requested_at` | TIMESTAMP | YES | Data da requisição original |

### Exemplo de Recommendation (JSON)

```json
{
  "recommendations": [
    {"id_protocolo": "53500987654202400", "score": 1.00},
    {"id_protocolo": "53500111222202300", "score": 0.87}
  ]
}
```

---

## document_mlt_recommendation

Armazena recomendações do Doc2Doc.

### Schema

```sql
CREATE TABLE document_mlt_recommendation (
    id_recommendation BIGSERIAL PRIMARY KEY,
    text VARCHAR,
    list_id_doc INTEGER[],
    list_type_id_doc INTEGER[],
    rows INTEGER,
    include_citations BOOLEAN,
    text_weight FLOAT,
    normalized BOOLEAN,
    fq VARCHAR[],
    recommendation JSON,
    created_at TIMESTAMP DEFAULT NOW(),
    requested_at TIMESTAMP,
    id_user BIGINT
);
```

### Colunas

| Coluna | Tipo | Nullable | Descrição |
|--------|------|----------|-----------|
| `id_recommendation` | BIGSERIAL | NO | ID único |
| `text` | VARCHAR | YES | Texto de busca |
| `list_id_doc` | INTEGER[] | YES | IDs de documentos de referência |
| `list_type_id_doc` | INTEGER[] | YES | Filtro de tipos |
| `rows` | INTEGER | YES | Quantidade de resultados |
| `include_citations` | BOOLEAN | YES | Se incluiu citações |
| `text_weight` | FLOAT | YES | Peso do texto (0-1) |
| `normalized` | BOOLEAN | YES | Se normalizou scores |
| `fq` | VARCHAR[] | YES | Filter queries |
| `recommendation` | JSON | YES | Resultado |
| `created_at` | TIMESTAMP | NO | Data de criação |
| `requested_at` | TIMESTAMP | YES | Data da requisição |
| `id_user` | BIGINT | YES | Usuário |

---

## config_mlt_fields_weights

Armazena a configuração de pesos para o WMLT.

### Schema

```sql
CREATE TABLE config_mlt_fields_weights (
    id BIGSERIAL PRIMARY KEY,
    weights JSON NOT NULL,
    created_on TIMESTAMP DEFAULT NOW()
);
```

### Colunas

| Coluna | Tipo | Nullable | Descrição |
|--------|------|----------|-----------|
| `id` | BIGSERIAL | NO | ID único |
| `weights` | JSON | NO | Configuração de pesos |
| `created_on` | TIMESTAMP | NO | Data de criação |

### Exemplo de Weights (JSON)

```json
{
  "metadata": {
    "weight": 0.3,
    "fields": {
      "metadata_name_id_type_process": {"weight": 0.5},
      "metadata_id_unit_process_generator": {"weight": 0.1}
    }
  },
  "content": {
    "weight": 0.7,
    "fields": {
      "content_id_type_doc_": {
        "weight": 0.98,
        "fields": {
          "content_id_type_doc_8": {
            "weight": 1.0,
            "fields": {
              "content_id_type_doc_8_ementa": {"weight": 0.85}
            }
          }
        }
      }
    }
  }
}
```

### Consulta de Pesos Atuais

```sql
SELECT weights FROM config_mlt_fields_weights
ORDER BY created_on DESC
LIMIT 1;
```

---

## Conexão

### Variáveis de Ambiente

| Variável | Descrição |
|----------|-----------|
| `DB_SEIIA_HOST` | Host do PostgreSQL |
| `DB_SEIIA_USER` | Usuário |
| `DB_SEIIA_PWD` | Senha |
| `DB_SEIIA_SIMILARIDADE` | Nome do banco |
| `CONN_STRING_APP_DB` | Connection string completa |

### Connection String

```
postgresql+psycopg2://user:password@host:5432/database
```

---

## Queries Úteis

### Recomendações por Período

```sql
SELECT
    DATE(created_at) as data,
    COUNT(*) as total
FROM process_weighted_mlt_recommendation
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY data DESC;
```

### Top Protocolos Consultados

```sql
SELECT
    id_protocolo,
    COUNT(*) as consultas
FROM process_weighted_mlt_recommendation
GROUP BY id_protocolo
ORDER BY consultas DESC
LIMIT 10;
```

### Requisições por Status

```sql
SELECT
    status_code,
    COUNT(*) as total
FROM log_consume
WHERE time_created >= NOW() - INTERVAL '24 hours'
GROUP BY status_code
ORDER BY total DESC;
```

---

## Próximos Passos

- [Apache Solr](solr.md) - Configuração dos cores
- [Jobs API](jobs-api.md) - ETL de dados
- [Visão Geral](index.md) - Voltar à visão geral

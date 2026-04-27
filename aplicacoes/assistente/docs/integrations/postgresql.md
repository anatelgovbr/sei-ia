# PostgreSQL + pgvector

> Banco de dados relacional e vetorial

## Visão Geral

O PostgreSQL é usado para:
- Armazenamento de embeddings (com pgvector)
- Persistência de feedback
- Status de gateways

## Configuração

```bash
DB_SEIIA_HOST=localhost
DB_SEIIA_PORT=5432
DB_SEIIA_USER=seiia
DB_SEIIA_PWD=sua_senha
DB_SEIIA_ASSISTENTE=SEI_LLM
DB_SEIIA_ASSISTENTE_SCHEMA=sei_llm
DB_SEIIA_POOL_MIN_SIZE=1
DB_SEIIA_POOL_MAX_SIZE=10
```

## Extensão pgvector

```sql
-- Habilitar extensão
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabela de embeddings
CREATE TABLE embeddings (
    chunk_id UUID PRIMARY KEY,
    id_documento VARCHAR(50),
    embedding VECTOR(1536),
    chunk_content TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Índice vetorial
CREATE INDEX ON embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

## Conexão Assíncrona

**Arquivo**: `sei_ia/data/database/async_db_connection.py`

```python
# Pool de conexões assíncronas
async_engine = create_async_engine(
    connection_string,
    pool_size=10,
    max_overflow=5
)
```

## Modelos SQLAlchemy

- `sei_ia/data/database/db_models/embedding.py`
- `sei_ia/data/database/db_models/feedback.py`

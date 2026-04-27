# Redis

> Cache distribuído

## Visão Geral

Redis é usado para cache de documentos extraídos do SEI.

**Arquivo**: `sei_ia/services/cache/redis_client.py`

## Configuração

```bash
ASSISTENTE_REDIS_URI=redis://localhost:6379/0
ASSISTENTE_CACHE_ENABLED=true
ASSISTENTE_CACHE_TTL_SECONDS=120
ASSISTENTE_CACHE_MAX_CONNECTIONS=100
ASSISTENTE_CACHE_COMPRESS=true
ASSISTENTE_CACHE_KEY_PREFIX=seiia:doc:
ASSISTENTE_CACHE_VERSION=v1
```

## Funcionalidades

| Feature | Descrição |
|---------|-----------|
| TTL | Expiração automática (120s default) |
| Compressão | gzip para reduzir uso de memória |
| Pool | Pool de conexões (100 max) |
| Retry | Retry automático em timeouts |

## Estrutura de Chaves

```
seiia:doc:v1:{document_id}
```

## Uso

```python
from sei_ia.services.cache.redis_client import RedisCache

cache = RedisCache()

# Salvar
await cache.set(doc_id, content, ttl=120)

# Buscar
content = await cache.get(doc_id)
if content is None:
    # Cache miss - buscar do SEI
    ...
```

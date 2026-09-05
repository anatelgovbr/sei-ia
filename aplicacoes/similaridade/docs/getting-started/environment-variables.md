# Variáveis de Ambiente

A API sei-similaridade é configurada através de variáveis de ambiente. Este documento lista todas as variáveis disponíveis.

---

## Conexões Solr

| Variável | Default | Descrição |
|----------|---------|-----------|
| `SOLR_ADDRESS` | - | URL base do Solr (ex: `http://solr:8983/solr`) |
| `SOLR_MLT_PROCESS_CORE` | - | Nome do core para processos WMLT |
| `SOLR_MLT_JURISPRUDENCE_CORE` | `documentos_bm25` | Nome do core para jurisprudência |
| `SOLR_USER` | - | Usuário de autenticação Solr (opcional) |
| `SOLR_PASSWORD` | - | Senha de autenticação Solr (opcional) |
| `SOLR_READ_TIMEOUT_SECONDS` | `30` | Timeout de leitura das consultas assíncronas ao Solr (segundos) |

---

## Conexões PostgreSQL

| Variável | Default | Descrição |
|----------|---------|-----------|
| `DB_SEIIA_HOST` | `localhost` | Host do PostgreSQL |
| `DB_SEIIA_USER` | - | Usuário do banco |
| `DB_SEIIA_PWD` | - | Senha do banco |
| `DB_SEIIA_SIMILARIDADE` | `sei_similaridade` | Nome do banco de dados |
| `CONN_STRING_APP_DB` | - | Connection string completa (alternativo) |

!!! note "Connection String"
    Se `CONN_STRING_APP_DB` for definida, ela terá prioridade sobre as variáveis individuais.
    Informe o endpoint sem credenciais embutidas e configure usuário e senha pelas variáveis dedicadas.

---

## API de acesso ao banco do SEI

| Variável | Default | Descrição |
|----------|---------|-----------|
| `SEI_API_DB_ADDRESS` | - | Endpoint da API de banco do SEI |
| `SEI_API_DB_USER` | `Usuario_IA` | Usuário de leitura |
| `SEI_API_DB_PASSWORD` | - | Senha do usuário |
| `SEI_API_DB_TIMEOUT` | `120` | Timeout de conexão (segundos) |
| `SEI_API_DB_IDENTIFIER_SERVICE` | - | Identificador do serviço chamador |

---

## Jobs API

| Variável | Default | Descrição |
|----------|---------|-----------|
| `JOBS_API_ADDRESS` | `http://etl-airflow-api:8642` | URL interna da Jobs API para indexação sob demanda |

A Jobs API não é um endpoint do SEI e não é publicada no host. Na stack, a Similaridade a chama por HTTP na rede Docker; não a aponte para o gateway TLS.

---

## Comportamento

| Variável | Default | Descrição |
|----------|---------|-----------|
| `LOG_LEVEL` | `DEBUG` | Nível de log: `critical`, `error`, `warning`, `info`, `debug`, `trace` |
| `VERIFY_SSL` | `false` | Validar certificados SSL |
| `TZ` | `America/Sao_Paulo` | Timezone |

---

## Autenticação (Opcional)

| Variável | Default | Descrição |
|----------|---------|-----------|
| `USE_AUTHENTICATION` | `false` | Habilitar autenticação JWT |
| `SECRET_KEY` | - | Chave secreta para JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Tempo de expiração do token |

---

## Observabilidade (Opcional)

| Variável | Default | Descrição |
|----------|---------|-----------|
| `ENABLE_OTEL_METRICS` | `true` | Habilitar métricas OpenTelemetry |

---

## Armazenamento

| Variável | Default | Descrição |
|----------|---------|-----------|
| `STORAGE_PROJ_DIR` | `/opt/sei_similaridade/` | Diretório de armazenamento |

---

## Exemplo Completo

Crie um arquivo `.env` na raiz do projeto:

```bash
# === TIMEZONE ===
TZ=America/Sao_Paulo

# === LOGGING ===
LOG_LEVEL=INFO

# === SOLR ===
SOLR_ADDRESS=http://solr:8983/solr
SOLR_MLT_PROCESS_CORE=processos_mlt
SOLR_MLT_JURISPRUDENCE_CORE=documentos_bm25
SOLR_USER=
# Defina SOLR_PASSWORD no security.env da raiz.
SOLR_READ_TIMEOUT_SECONDS=30

# === PostgreSQL ===
DB_SEIIA_HOST=postgres
DB_SEIIA_USER=seiia
# Defina DB_SEIIA_PWD no security.env da raiz.
DB_SEIIA_SIMILARIDADE=sei_similaridade

# === Banco SEI (Oracle) ===
SEI_API_DB_ADDRESS=oracle-sei:1521
SEI_API_DB_USER=Usuario_IA
# Defina SEI_API_DB_PASSWORD no security.env da raiz.
SEI_API_DB_TIMEOUT=120

# === Jobs API ===
JOBS_API_ADDRESS=http://etl-airflow-api:8642

# === Comportamento ===
VERIFY_SSL=false
ENABLE_OTEL_METRICS=true

# === Autenticação (opcional) ===
USE_AUTHENTICATION=false
SECRET_KEY=sua-chave-secreta-muito-longa-e-segura
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

---

## Próximos Passos

- [Instalação](index.md) - Voltar ao guia de instalação
- [WMLT](../wmlt/index.md) - Entender recomendação de processos
- [Camada de Dados](../dados/index.md) - Configuração do Solr e PostgreSQL

# Variáveis de Ambiente

Esta página documenta variáveis consumidas pela aplicação em desenvolvimento.
Para instalação externa, o contrato exato e autoritativo é formado por
`default.env` e `security_example.env` da raiz; siga `docs/INSTALL.md` no
monorepo e não acrescente nomes deste guia aos arquivos do deploy.

## Ambiente

| Variável | Default | Descrição |
|----------|---------|-----------|
| `ENVIRONMENT` | `test` | Ambiente de execução (`dev`, `homol`, `prod`, `test`) |
| `LOG_LEVEL` | `INFO` | Nível de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `VERIFY_SSL` | `False` | Verificação de certificados SSL |

---

## Apache Solr

| Variável | Default | Descrição |
|----------|---------|-----------|
| `SOLR_ADDRESS` | - | URL base do servidor Solr (ex: `http://solr:8983`) |
| `SOLR_USER` | - | Usuário para autenticação no Solr |
| `SOLR_PASSWORD` | - | Senha para autenticação no Solr |
| `SOLR_MLT_PROCESS_CORE` | - | Nome do core Solr para indexação de processos |
| `SOLR_MLT_JURISPRUDENCE_CORE` | `documentos_bm25` | Nome do core Solr para documentos |
| `SOLR_N_ROWS` | `700` | Número de linhas retornadas por consulta Solr |
| `MLT_PROCESS_CONFIGSET` | `configs/solr_core_configs/process` | Caminho do configset para processos |
| `MLT_JURISPRUDENCE_CONFIGSET` | `configs/solr_core_configs/jurisprudence` | Caminho do configset para documentos |

---

## API do SEI

| Variável | Default | Descrição |
|----------|---------|-----------|
| `SEI_API_DB_ADDRESS` | - | URL base da API do SEI |
| `SEI_API_DB_USER` | `Usuario_IA` | Usuário da API do SEI |
| `SEI_API_DB_IDENTIFIER_SERVICE` | - | Identificador do serviço no SEI |
| `SEI_API_DB_TIMEOUT` | `120` | Timeout em segundos para requisições |
| `SEI_API_MAX_CONCURRENCY` | `15` | Máximo de requisições concorrentes |
| `SEI_API_MAX_RETRIES` | `5` | Número máximo de tentativas em falhas |
| `SEI_API_BACKOFF_BASE` | `1.0` | Base do backoff exponencial (segundos) |
| `SEI_API_BACKOFF_MAX` | `32.0` | Backoff máximo (segundos) |

---

## Apache Airflow

| Variável | Default | Descrição |
|----------|---------|-----------|
| `AIRFLOW__CORE__DEFAULT_TIMEZONE` | `America/Sao_Paulo` | Timezone do Airflow |
| `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` | `postgresql+psycopg2://...` | Connection string do banco Airflow |
| `AIRFLOW_API_BASE_URL` | `http://etl-airflow-webserver:8080/api/v1` | URL interna da API REST do Airflow |
| `_AIRFLOW_WWW_USER_USERNAME` | `seiia` | Usuário web do Airflow |
| `_AIRFLOW_WWW_USER_PASSWORD` | obrigatória, sem default | Senha web do Airflow |

---

## Indexação (ETL)

| Variável | Default | Descrição |
|----------|---------|-----------|
| `INDEX_PROCESS_BATCH_SIZE` | `5` | Tamanho do lote para indexação de processos |
| `LIMIT_QUEUE` | `100` | Número máximo de DAGs Worker simultâneos |

---

## LiteLLM e Embeddings

### Configuração do LiteLLM Proxy

| Variável | Default | Descrição |
|----------|---------|-----------|
| `LITELLM_PROXY_URL` | `http://localhost:4000` | URL do LiteLLM Proxy |
| `LITELLM_PROXY_API_KEY` | obrigatória no deploy | Chave usada por todos os clientes do proxy |
| `LITELLM_EMBEDDING_MODEL_NAME` | `embedding` | Alias público usado para rotear a requisição de embedding |
| `EMBEDDING_MODEL` | `embedding` | Alias legado de execução avulsa; não define a identidade física da tabela |
| `EMBEDDING_API_VERSION` | `2024-10-21` | Versão da API (auto-detectada do proxy). Conceito específico do Azure OpenAI — não se aplica ao usar Google Vertex AI como provider |
| `EMBEDDING_BASE_MODEL` | definido pelo Compose a partir do contrato | Pin usado para resolver o tokenizador (`tiktoken`) e gerar o nome da tabela de embeddings; evita rede durante a importação das DAGs |

!!! note "Alias público e modelo base"
    No deploy integrado, `LITELLM_EMBEDDING_MODEL_NAME` permanece como o alias
    público `embedding`, enquanto `EMBEDDING_BASE_MODEL` recebe o modelo físico
    configurado em `LITELLM_EMBEDDING_MODEL`. O primeiro controla o roteamento;
    o segundo preserva a identidade da tabela e a tokenização.
    O provider tenta reconhecer o nome sem o prefixo do
    provedor; quando isso não é possível, usa uma codificação aproximada apenas
    para estimar o tamanho dos chunks e registra um aviso. O valor de
    `EMBEDDING_DIM` deve sempre corresponder à dimensão efetiva retornada pelo
    modelo configurado no proxy.

### Configuração de Chunking

| Variável | Default | Descrição |
|----------|---------|-----------|
| `MAX_LENGTH_CHUNK_SIZE` | `1512` | Tamanho máximo de cada chunk em tokens |
| `CHUNK_OVERLAP` | `50` | Sobreposição entre chunks em tokens |
| `EMBEDDINGS_MAX_CONCURRENCY` | `20` | Concorrência máxima para geração de embeddings |

### Configuração de Processamento

| Variável | Default | Descrição |
|----------|---------|-----------|
| `EMBEDDING_BATCH_SIZE` | `10` | Documentos por lote de embedding |
| `EMBEDDING_MAX_ACTIVE_RUNS` | `2` | DAGs de embedding simultâneos |

!!! info "Nome da Tabela de Embeddings"
    O nome da tabela é gerado automaticamente seguindo o padrão:
    ```
    {EMBEDDING_BASE_MODEL}-{MAX_LENGTH_CHUNK_SIZE}-{CHUNK_OVERLAP}
    ```
    Exemplo: `text_embedding_3_small_1512_50`

---

## PostgreSQL (Embeddings)

| Variável | Default | Descrição |
|----------|---------|-----------|
| `DB_SEIIA_HOST` | - | Host do PostgreSQL |
| `DB_SEIIA_PORT` | `5432` | Porta do PostgreSQL |
| `DB_SEIIA_USER` | - | Usuário do PostgreSQL |
| `DB_SEIIA_PWD` | - | Senha do PostgreSQL |
| `DB_SEIIA_ASSISTENTE` | `SEI_LLM` | Nome do banco de dados |
| `DB_SEIIA_ASSISTENTE_SCHEMA` | `sei_llm` | Schema para tabelas de embeddings |

---

## Redis (Cache)

| Variável | Default | Descrição |
|----------|---------|-----------|
| `REDIS_URI` | `redis://infra-redis:6379/0` | URI de conexão Redis (compartilhada com o Assistente) |
| `JOBS_CACHE_ENABLED` | `true` | Habilita/desabilita cache |
| `JOBS_CACHE_KEY_PREFIX` | `seiia:doc:` | Prefixo das chaves de cache |

!!! note "Compartilhamento com Assistente"
    O Redis e o PostgreSQL são compartilhados com o sistema Assistente.
    O prefixo `seiia:doc:` segue o mesmo padrão do Assistente para permitir invalidação de cache cruzada.

---

## Outros

| Variável | Default | Descrição |
|----------|---------|-----------|
| `CONN_STRING_APP_DB` | - | Connection string do banco da aplicação |
| `FORMATS` | `configs/formats.csv` | Arquivo com formatos de documento permitidos |

---

## Exemplo de Configuração

```bash
# Ambiente
export ENVIRONMENT=prod
export LOG_LEVEL=INFO

# Solr
export SOLR_ADDRESS=http://solr:8983
export SOLR_USER=admin
# Defina SOLR_PASSWORD no ambiente local.
export SOLR_MLT_PROCESS_CORE=processos_mlt

# SEI API
export SEI_API_DB_ADDRESS=http://sei-api:8080
export SEI_API_DB_USER=Usuario_IA

# LiteLLM
export LITELLM_PROXY_URL=http://litellm:4000
# Use o mesmo nome publicado como model_name no proxy.
export LITELLM_EMBEDDING_MODEL_NAME=embedding
export EMBEDDING_BASE_MODEL=openai/text-embedding-3-small

# PostgreSQL (Embeddings)
export DB_SEIIA_HOST=postgres
export DB_SEIIA_PORT=5432
export DB_SEIIA_USER=seiia
# Defina DB_SEIIA_PWD no ambiente local.
export DB_SEIIA_ASSISTENTE=SEI_LLM
export DB_SEIIA_ASSISTENTE_SCHEMA=sei_llm

# Redis
export REDIS_URI=redis://infra-redis:6379/0
export JOBS_CACHE_ENABLED=true

# Airflow: preencha localmente sem registrar credenciais no documento.
# Defina AIRFLOW__DATABASE__SQL_ALCHEMY_CONN no ambiente local.
```

---

## Próximos Passos

- [Indexação de Processos](../etl/indexacao-processos.md)
- [Indexação de Documentos](../etl/indexacao-documentos.md)
- [ETL de Embeddings](../etl/embeddings.md)

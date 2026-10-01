# SEI IA ETL/Airflow

Pipelines que extraem dados do SEI, indexam processos e documentos no Solr e geram
embeddings no PostgreSQL/pgvector.

| Pipeline | Destino | Consumidor |
|---|---|---|
| indexação de processos | Solr | Similaridade |
| indexação de documentos | Solr | Similaridade |
| geração de embeddings | PostgreSQL/pgvector | Assistente |

> A instalação externa não é feita isoladamente desta pasta. Use o
> [manual integrado](../../docs/INSTALL.md), que constrói a stack por código-fonte
> com `make up` e valida Airflow, Solr, bancos, LiteLLM e APIs com `make check`.

## Desenvolvimento local

O projeto usa `uv`. Para trabalhar somente nesta aplicação:

```bash
cd aplicacoes/etl-airflow
uv sync --locked --extra airflow
```

Execute testes unitários de forma seletiva durante o desenvolvimento e a suíte
definida pelo projeto antes de entregar mudanças:

```bash
uv run pytest --no-cov tests/unit/<arquivo_de_teste>.py
uv run pytest
```

O Airflow de deploy é criado pelo `docker-compose.yml` da raiz. Não use comandos de
inicialização de um Airflow avulso como substituto da instalação integrada.

## LiteLLM e embeddings

No deploy integrado, o ETL envia ao proxy o alias público `embedding`. O proxy
usa `LITELLM_EMBEDDING_MODEL` somente para apontar esse alias ao modelo físico:

- `LITELLM_PROXY_URL` aponta para `infra-litellm:4000` na rede Docker;
- `LITELLM_PROXY_API_KEY` é obrigatória em todas as chamadas;
- `LITELLM_EMBEDDING_MODEL_NAME` é `embedding`, o nome usado nas requisições;
- `EMBEDDING_BASE_MODEL` recebe o pin físico para tokenização e nome da tabela,
  evitando que a importação das DAGs dependa de uma consulta de rede;
- o proxy não é publicado no host pela composição padrão.

As credenciais de provedores ficam em `security.env`. O arquivo
`litellm_config.yaml` é uma cópia do template da raiz e conserva referências
`os.environ/VAR`; ele não contém segredos literais.

## DAGs principais

| DAG | Função |
|---|---|
| `process_update_index` | enfileira processos para indexação |
| `documents_update_index` | enfileira documentos para o Solr |
| `documents_update_embedding` | enfileira documentos para embeddings |
| `cache_invalidation` | invalida itens cancelados |
| `system_clean_airflow_logs` | limpa logs antigos |
| `system_create_mlt_weights_config` | atualiza pesos de similaridade |

## Documentação da aplicação

```bash
uv run mkdocs build --strict
uv run mkdocs serve
```

As variáveis da aplicação são explicadas em `docs/`. Para o contrato exato do
deploy, prevalecem `default.env`, `security_example.env` e o
[manual da raiz](../../docs/INSTALL.md).

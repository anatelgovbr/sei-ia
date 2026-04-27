# Documentação dos Módulos

## Visão Geral

O projeto está organizado em módulos especializados para diferentes funcionalidades:

```
jobs/
├── api.py                   # Aplicação FastAPI principal
├── envs.py                  # Variáveis de ambiente
├── api_rest/                # API REST
│   ├── routers/             # Endpoints da API
│   └── services/            # Lógica de negócio
├── dags/                    # Apache Airflow
│   ├── dag_objects/         # DAGs
│   ├── database/            # Operações Solr
│   ├── preprocessing/       # Processamento de dados
│   └── inference/           # Inferência com regex
├── db_models/               # Modelos de banco de dados
├── document_extraction/     # Extração de documentos
│   └── parsers/             # Parsers (PDF, Office, etc)
├── services/                # Serviços
│   ├── cache/               # Cliente Redis
│   └── embedder/            # Geração de embeddings
├── configs/                 # Configurações
├── scripts_airflow/         # Scripts utilitários
├── exception_handling/      # Exceções customizadas
└── utils/                   # Funções utilitárias
```

## Módulos Principais

### API REST

**Arquivo:** `jobs/api.py`

```python
from jobs.api import app
```

Aplicação FastAPI principal que expõe endpoints para geração de embeddings e consulta de processos. A documentação ReDoc está disponível na raiz (`/`).

### API REST - Routers

**Arquivo:** `jobs/api_rest/routers/embeddings.py`

```python
from jobs.api_rest.routers.embeddings import router
```

Routers FastAPI que definem os endpoints da API:

- `embeddings.py`: Endpoint `POST /embeddings/generate` para geração de embeddings vetoriais

### API REST - Services

**Arquivos:** `jobs/api_rest/services/`

```python
from jobs.api_rest.services.embedding_service import generate_embeddings_for_documents
from jobs.api_rest.services.process import get_process_by_nr_process
```

Camada de serviços com a lógica de negócio:

| Serviço | Descrição |
|---------|-----------|
| `embedding_service.py` | Orquestra a geração de embeddings (verificação de existência, chunking, geração, salvamento) |
| `process.py` | Lógica para consulta de processos não indexados |

---

## DAGs do Airflow

### DAGs - Objetos

**Diretório:** `jobs/dags/dag_objects/`

```python
from jobs.dags.dag_objects.mlt_etl_process.dag_mlt_etl_process import dag
```

DAGs do Apache Airflow para orquestração de jobs:

| Arquivo | Descrição |
|---------|-----------|
| `dag_mlt_etl_process.py` | Indexação de processos no Solr (MLT) |
| `dag_mlt_etl_documents.py` | Indexação de documentos no Solr |
| `dag_mlt_generate_embedding.py` | Geração de embeddings em lote |
| `dag_mlt_cache_invalidation.py` | Invalidação de cache Redis |
| `dag_mlt_start_etl.py` | Orquestrador principal do ETL |
| `dag_mlt_start_embedding.py` | Orquestrador de geração de embeddings |
| `clean_logs.py` | Limpeza de logs antigos do Airflow |
| `sync_config.py` | Sincronização de configurações |

### DAGs - Database

**Diretório:** `jobs/dags/database/`

```python
from jobs.dags.database.generic_sender import GenericSender
from jobs.dags.database.create_solr_core import create_solr_core
from jobs.dags.database.delete_solr_core import delete_solr_core
```

Operações de banco de dados e Solr:

| Módulo | Descrição |
|--------|-----------|
| `generic_sender.py` | Envio em bulk para Solr |
| `create_solr_core.py` | Criação de cores Solr |
| `delete_solr_core.py` | Deleção de cores Solr |

### DAGs - Preprocessing

**Diretório:** `jobs/dags/preprocessing/`

```python
from jobs.dags.preprocessing.process_from_sei import ProcessFromSEI
from jobs.dags.preprocessing.process_transformed import ProcessTransformed
```

Processamento e transformação de dados:

| Módulo | Descrição |
|--------|-----------|
| `process_from_sei.py` | Busca dados do SEI (metadados, documentos, processos relacionados) |
| `process_transformed.py` | Transforma dados para o schema do Solr |
| `sections_dictionary.py` | Mapeamento de seções de documentos jurídicos |
| `split_section2.py` | Divisão de seções de documentos |
| `text_clean.py` | Limpeza e normalização de texto |

### DAGs - Inference

**Diretório:** `jobs/dags/inference/`

```python
from jobs.dags.inference.regex import apply_regex_model
```

Inferência e extração de informações:

- `regex.py`: Aplicação de modelos de regex para extração de padrões

---

## Modelos de Banco de Dados

**Diretório:** `jobs/db_models/`

```python
from jobs.db_models.app_tables import Queue, Log, Config
from jobs.db_models.embedding import Embedding
from jobs.db_models.solr_handlers import SolrHandler
from jobs.db_models.sei_db_handlers import SEIDBHandler
```

Modelos de banco de dados e handlers:

| Módulo | Descrição |
|--------|-----------|
| `app_tables.py` | Modelos SQLAlchemy (Queue, Log, Config) |
| `embedding.py` | Modelo de embeddings com pgvector |
| `async_db_connection.py` | Conector assíncrono PostgreSQL |
| `sei_db_handlers.py` | Cliente API SEI |
| `solr_handlers.py` | Cliente Solr |
| `solr_select.py` | Query builder Solr |
| `repository.py` | Padrão Repository |
| `sqlserver.py` | Cliente SQL Server |

---

## Extração de Documentos

**Diretório:** `jobs/document_extraction/`

```python
from jobs.document_extraction.document_reader import DocumentReader
from jobs.document_extraction.text_processor import TextProcessor
```

Extração e processamento de documentos:

| Módulo | Descrição |
|--------|-----------|
| `document_reader.py` | Coordenador de leitura de documentos (interno/externo) |
| `text_processor.py` | Processamento de texto extraído |

### Parsers

**Diretório:** `jobs/document_extraction/parsers/`

```python
from jobs.document_extraction.parsers.pdf_parser import PDFParser
from jobs.document_extraction.parsers.office_parser import OfficeParser
from jobs.document_extraction.parsers.spreadsheet_parser import SpreadsheetParser
```

Parsers específicos por tipo de documento:

| Parser | Formatos | Biblioteca |
|--------|----------|------------|
| `pdf_parser.py` | PDF | PyMuPDF |
| `office_parser.py` | DOCX, ODT, PPTX | Docling |
| `spreadsheet_parser.py` | XLSX, XLS, ODS, CSV | python-calamine |

---

## Serviços

### Embedder

**Diretório:** `jobs/services/embedder/`

```python
from jobs.services.embedder.embedding_generator import EmbeddingGenerator
from jobs.services.embedder.providers.litellm import LiteLLMEmbeddingProvider
from jobs.services.embedder.providers.azure import AzureOpenAIProvider
```

Geração de embeddings vetoriais:

| Módulo | Descrição |
|--------|-----------|
| `embedding_generator.py` | Orquestrador de geração de embeddings com pooling |
| `providers/provider_interface.py` | Interface abstrata para providers |
| `providers/litellm.py` | **Implementação LiteLLM Proxy (recomendado)** |
| `providers/azure.py` | Implementação Azure OpenAI direta (legado) |

!!! note "Provider Recomendado"
    O `LiteLLMEmbeddingProvider` é o provider padrão e recomendado.
    Utiliza o LiteLLM Proxy como gateway para Azure OpenAI.
    Ver [Integração LiteLLM](services/litellm-integration.md) para detalhes.

### Cache

**Diretório:** `jobs/services/cache/`

```python
from jobs.services.cache.redis_client import RedisClient
```

Cliente Redis para cache distribuído de documentos.

---

## Configurações

### Parameters

**Diretório:** `jobs/configs/parameters/`

```python
from jobs.configs.parameters.conf_mlt_fields_weights import get_mlt_weights
from jobs.configs.parameters.models import available_models
```

Configurações do sistema:

| Módulo | Descrição |
|--------|-----------|
| `conf_mlt_fields_weights.py` | Pesos de campos para MLT no Solr |
| `default_conf_mlt_fields_weights.py` | Pesos padrão |
| `data_access.py` | Configuração de acesso a dados |
| `models.py` | Modelos disponíveis |
| `normalizer_weights.py` | Pesos de normalização |

### Solr Core Configs

**Diretório:** `jobs/configs/solr_core_configs/configsets/`

Configurações dos cores Solr:

| Configset | Uso |
|-----------|-----|
| `_default/` | Configuração padrão |
| `jurisprudence/` | Core de documentos (BM25) |
| `process/` | Core de processos (MLT) |
| `sei_protocolos/` | Core de protocolos SEI |

---

## Scripts Airflow

**Diretório:** `jobs/scripts_airflow/`

```python
from jobs.scripts_airflow.trigger_dag import trigger_dag
```

Scripts utilitários para Airflow:

| Script | Descrição |
|--------|-----------|
| `trigger_dag.py` | Trigger de DAGs programaticamente |
| `operator.py` | Operadores customizados |
| `rerun_failed.py` | Re-executa DAGs falhadas |
| `change_dagruns_state.py` | Muda estado de runs |
| `clean_dag_runs.py` | Limpa runs antigos |
| `get_all_dagruns.py` | Lista todas as runs |

---

## Outros Módulos

### Exception Handling

**Diretório:** `jobs/exception_handling/`

```python
from jobs.exception_handling.exceptions import JobsException
```

Exceções customizadas do projeto.

### Utils

**Diretório:** `jobs/utils/`

```python
from jobs.utils.funcs import utility_function
```

Funções utilitárias gerais.

### Environment

**Arquivo:** `jobs/envs.py`

```python
from jobs.envs import ENVIRONMENT, SOLR_ADDRESS, auth
```

Variáveis de ambiente e configurações globais do sistema. Principais variáveis:

| Variável | Descrição |
|----------|-----------|
| `ENVIRONMENT` | Ambiente de execução (dev, homol, prod, test) |
| `SOLR_ADDRESS` | URL do servidor Solr |
| `SOLR_MLT_PROCESS_CORE` | Nome do core de processos |
| `EMBEDDING_PROVIDER` | Provider de embeddings (azure) |
| `EMBEDDING_MODEL` | Modelo de embeddings |
| `JOBS_REDIS_URI` | URI do Redis |

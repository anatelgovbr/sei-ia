# SEI-Similaridade Jobs

[![Release](https://img.shields.io/badge/release-1.1.7-blue)](https://git.anatel.gov.br/processo_eletronico/sei-ia/sei-similaridade/jobs)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](https://git.anatel.gov.br/processo_eletronico/sei-ia/sei-similaridade/jobs/-/pipelines)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![Airflow](https://img.shields.io/badge/airflow-2.9.3-orange)](https://airflow.apache.org/)

Sistema de processamento ETL para preparar dados do SEI (Sistema Eletrônico de Informações) da Anatel.

## O que o Jobs faz

O SEI-Similaridade Jobs é responsável por:

1. **Indexação de Processos**: Extrai processos do SEI, transforma e envia para Apache Solr para que o projeto `api_sei` realize busca por similaridade de processos.

2. **Indexação de Documentos**: Extrai documentos do SEI, transforma e envia para Apache Solr para que o projeto `api_sei` realize busca por similaridade de documentos (Doc2Doc).

3. **Geração de Embeddings**: Gera embeddings vetoriais dos documentos via LiteLLM e armazena no PostgreSQL para serem usados em RAG pelo projeto Assistente.

4. **Manutenção**: Limpeza de cache, logs e atualização de configurações de pesos MLT.

## Visão Geral

```mermaid
graph TB
    subgraph Jobs["SEI-Similaridade Jobs"]
        ETL_PROC["Indexação Processos"]
        ETL_DOC["Indexação Documentos"]
        ETL_EMB["Geração Embeddings"]
        MANUT["Manutenção"]
    end

    SEI_API["SEI API"] --> ETL_PROC
    SEI_API --> ETL_DOC
    SEI_API --> ETL_EMB

    ETL_PROC --> SOLR[("Solr")]
    ETL_DOC --> SOLR
    SOLR --> API_SEI["api_sei<br/>(Similaridade)"]

    ETL_EMB --> LITELLM["LiteLLM Proxy"]
    LITELLM --> PG[("PostgreSQL<br/>pgvector")]
    PG --> ASSISTENTE["Assistente<br/>(RAG)"]

    MANUT --> SOLR
    MANUT --> PG
    MANUT --> REDIS[("Redis")]
```

## Tecnologias

| Categoria | Tecnologia |
|-----------|------------|
| **Orquestração** | Apache Airflow 2.9.3 |
| **API** | FastAPI |
| **Busca** | Apache Solr (destino do ETL) |
| **Vector DB** | PostgreSQL + pgvector |
| **Cache** | Redis |
| **Embeddings** | LiteLLM Proxy → Azure OpenAI |
| **Processamento** | PyMuPDF, Docling, BeautifulSoup |

## Navegação

### Getting Started
- [Variáveis de Ambiente](getting-started/environment-variables.md)

### ETL Pipelines
- [Visão Geral](etl/index.md)
- [Indexação de Processos](etl/indexacao-processos.md)
- [Indexação de Documentos](etl/indexacao-documentos.md)
- [Embeddings](etl/embeddings.md)
- [DAGs de Manutenção](etl/dags-manutencao.md)

### Referência
- [Módulos](modules.md)

## Links Externos

- [GitLab - sei-similaridade/jobs](https://git.anatel.gov.br/processo_eletronico/sei-ia/sei-similaridade/jobs)
- [Wiki Anatel](https://anatel365.sharepoint.com/:u:/r/sites/WikiAnatel/SitePages/TIC-Dados-Sei-Similaridade-jobs.aspx)

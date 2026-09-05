# Camada de Dados

A API sei-similaridade integra com múltiplas fontes de dados para fornecer recomendações precisas.

---

## Visão Geral

```mermaid
flowchart TB
    subgraph API["sei-similaridade API"]
        S[Services]
    end

    subgraph Solr["Apache Solr"]
        PROC[(processos_mlt)]
        JURIS[(documentos_bm25)]
    end

    subgraph PG["PostgreSQL"]
        LOGS[(Logs)]
        RECS[(Recomendações)]
        CONFIG[(Configurações)]
    end

    subgraph SEI["Banco SEI"]
        ORACLE[(Oracle/MSSQL)]
    end

    subgraph Jobs["Jobs API"]
        ETL[ETL Pipelines]
    end

    S <-->|HTTP| PROC
    S <-->|HTTP| JURIS
    S <-->|SQL| LOGS
    S <-->|SQL| RECS
    S <-->|SQL| CONFIG
    S -->|SQL| ORACLE
    S -->|HTTP| ETL
```

---

## Componentes

| Componente | Tecnologia | Propósito |
|------------|------------|-----------|
| **Apache Solr** | Solr 9.0+ | Motor de busca textual (MLT) |
| **PostgreSQL** | PostgreSQL 15+ | Persistência e configurações |
| **Banco SEI** | Oracle/MSSQL | Fonte de dados de documentos |
| **Jobs API** | Python/Airflow | ETL e indexação |

---

## Fluxo de Dados

```mermaid
sequenceDiagram
    participant SEI as Banco SEI
    participant JOBS as Jobs API
    participant SOLR as Solr
    participant API as sei-similaridade
    participant PG as PostgreSQL

    Note over SEI,JOBS: ETL (Jobs API)
    SEI->>JOBS: Extrair processos/documentos
    JOBS->>SOLR: Indexar no Solr

    Note over API,PG: Requisição
    API->>SOLR: Buscar similares
    SOLR-->>API: Resultados
    API->>PG: Salvar recomendação
```

---

## Detalhamento

### Apache Solr

O Solr é o motor de busca principal, responsável por:

- **Indexação**: Armazenar documentos com seus campos de texto
- **MLT (More Like This)**: Encontrar documentos similares
- **Extração de termos**: Identificar termos relevantes

[Ver documentação completa do Solr →](solr.md)

### PostgreSQL

O PostgreSQL armazena:

- **Logs de auditoria**: Todas as requisições
- **Recomendações**: Resultados para histórico
- **Configurações**: Pesos e parâmetros

[Ver documentação completa do PostgreSQL →](postgresql.md)

### Jobs API

A Jobs API executa ETL para manter os dados atualizados:

- **Extração**: Busca dados no banco SEI
- **Transformação**: Processa e tokeniza
- **Carga**: Indexa no Solr

[Ver documentação completa da Jobs API →](jobs-api.md)

---

## Conexões

| Fonte | Protocolo | Variável de Ambiente |
|-------|-----------|----------------------|
| Solr | HTTP | `SOLR_ADDRESS` |
| PostgreSQL | SQL | `CONN_STRING_APP_DB` |
| Banco SEI | SQL | `SEI_API_DB_ADDRESS` |
| Jobs API | HTTP | `JOBS_API_ADDRESS` |

---

## Próximos Passos

- [Apache Solr](solr.md) - Configuração dos cores
- [PostgreSQL](postgresql.md) - Schema das tabelas
- [Jobs API](jobs-api.md) - Integração ETL
- [Variáveis de Ambiente](../getting-started/environment-variables.md) - Configuração

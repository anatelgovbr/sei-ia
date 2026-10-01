# Apache Solr

O Apache Solr é o motor de busca textual usado para indexação e busca de documentos similares.

---

## Visão Geral

| Aspecto | Valor |
|---------|-------|
| **Versão** | 9.0+ |
| **Protocolo** | HTTP/REST |
| **Funcionalidade Principal** | More Like This (MLT) |

---

## Cores Utilizados

O sei-similaridade usa dois cores (índices) no Solr:

| Core | Conteúdo | Consumidor | Variável |
|------|----------|------------|----------|
| `processos_mlt` | Processos SEI | WMLT | `SOLR_MLT_PROCESS_CORE` |
| `documentos_bm25` | Jurisprudências | Doc2Doc | `SOLR_MLT_JURISPRUDENCE_CORE` |

---

## Core: processos_mlt

Este core armazena **processos** do SEI para recomendação via WMLT.

### Campos Principais

| Campo | Tipo | Indexed | Stored | Descrição |
|-------|------|---------|--------|-----------|
| `id_protocolo` | string | ✓ | ✓ | ID único do processo |
| `protocolo_formatado` | string | ✓ | ✓ | Formato: 00000.000001/2024-01 |
| `id_process` | string | ✓ | ✓ | ID do processo no SEI |
| `id_type_process` | int | ✓ | ✓ | Tipo do processo |

### Campos de Metadata

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `metadata_name_id_type_process` | text | Nome do tipo de processo |
| `metadata_id_unit_process_generator` | int | ID da unidade geradora |
| `metadata_process_specification` | text | Especificação |
| `metadata_id_contact_interested` | int | ID do interessado |
| `metadata_info_related_processes` | text | Processos relacionados |
| `metadata_name_id_type_doc_*` | text | Tipos de documento |

### Campos de Conteúdo

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `content_id_type_doc_*` | text | Conteúdo por tipo de documento |
| `content_id_type_doc_8_ementa` | text | Ementa de acórdãos |
| `content_id_type_doc_8_acordao` | text | Texto de acórdãos |
| `content_id_type_doc_7_relatorio` | text | Relatório de análises |
| `content_citations` | text | Citações |

### Campos de ParsedQuery

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `fulltext_parsedquery_t` | text | Query completa pré-calculada |
| `sections_parsedquery_t` | text | Query por seções |

---

## Core: documentos_bm25

Este core armazena **documentos de jurisprudência** para busca Doc2Doc.

### Campos Principais

| Campo | Tipo | Indexed | Stored | Descrição |
|-------|------|---------|--------|-----------|
| `id_document` | int | ✓ | ✓ | ID único do documento |
| `id_type_document` | int | ✓ | ✓ | Tipo do documento |

### Campos de Conteúdo

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `content` | text | Conteúdo textual completo |
| `ementa` | text | Ementa (se aplicável) |
| `acordao` | text | Texto do acórdão |
| `relatorio` | text | Relatório |
| `voto` | text | Voto |

### Tipos de Documento

| ID | Tipo | Descrição |
|----|------|-----------|
| 4 | Despacho | Decisão administrativa |
| 7 | Análise | Análise técnica |
| 8 | Acórdão | Decisão colegiada |
| 16 | Informe | Documento informativo |
| 94 | Voto | Voto de conselheiro |

---

## Configuração MLT

O handler MLT é configurado em `solrconfig.xml`:

```xml
<requestHandler name="/mlt" class="solr.MoreLikeThisHandler">
  <lst name="defaults">
    <str name="mlt.fl">content,metadata_name</str>
    <int name="mlt.mintf">2</int>
    <int name="mlt.mindf">5</int>
    <int name="mlt.maxqt">25</int>
    <str name="mlt.interestingTerms">details</str>
  </lst>
</requestHandler>
```

### Parâmetros MLT

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| `mlt.fl` | `content,metadata_name` | Campos a analisar |
| `mlt.mintf` | `2` | Min Term Frequency |
| `mlt.mindf` | `5` | Min Document Frequency |
| `mlt.maxqt` | `25` | Max Query Terms |
| `mlt.interestingTerms` | `details` | Retorna termos + scores |

---

## Endpoints Utilizados

### Busca MLT

```
GET /solr/{core}/mlt?
    q=id_protocolo:{id}&
    mlt.fl=content&
    mlt.interestingTerms=details
```

### Busca Select

```
GET /solr/{core}/select?
    q=term1^weight1 term2^weight2&
    fl=id_protocolo,score&
    rows=10
```

### Verificação de Documento

```
GET /solr/{core}/select?
    q=id_protocolo:{id}&
    fl=id_protocolo
```

---

## Autenticação

Se o Solr estiver configurado com autenticação:

```python
from requests.auth import HTTPBasicAuth

auth = HTTPBasicAuth(SOLR_USER, SOLR_PASSWORD)
response = requests.get(url, auth=auth)
```

### Variáveis de Ambiente

| Variável | Descrição |
|----------|-----------|
| `SOLR_USER` | Usuário de autenticação |
| `SOLR_PASSWORD` | Senha de autenticação |

---

## Configsets

Os configsets estão em `configs/solr_core_configs/configsets/`:

```
configsets/
├── jurisprudence/           # Core documentos_bm25
│   ├── managed-schema.xml   # Schema
│   └── solrconfig.xml       # Configuração
├── process/                 # Core processos_mlt
│   ├── managed-schema.xml
│   └── solrconfig.xml
└── sei_protocolos/          # Core auxiliar
    ├── schema.xml
    └── solrconfig.xml
```

---

## Monitoramento

### Health Check

```bash
curl "http://localhost:8983/solr/admin/cores?action=STATUS"
```

### Estatísticas do Core

```bash
curl "http://localhost:8983/solr/processos_mlt/admin/luke"
```

### Quantidade de Documentos

```bash
curl "http://localhost:8983/solr/processos_mlt/select?q=*:*&rows=0"
```

---

## Próximos Passos

- [PostgreSQL](postgresql.md) - Tabelas de persistência
- [Jobs API](jobs-api.md) - ETL de indexação
- [Visão Geral](index.md) - Voltar à visão geral

# Jobs API

A Similaridade usa a API do ETL para indexar sob demanda processos que ainda
não estão visíveis no Solr.

O contrato HTTP, incluindo endpoint, autenticação, formato da resposta,
validação do processo solicitado e espera pela visibilidade no Solr, pertence a
`docs/agent_docs/service_communication_patterns.md`.

O papel da API do ETL na arquitetura pertence a
`docs/agent_docs/service_architecture.md`.

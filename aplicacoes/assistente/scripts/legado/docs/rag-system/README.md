# Sistema RAG (histórico arquivado)

!!! info "Documentação histórica arquivada"
    Esta seção documenta a arquitetura e os componentes originais do sistema clássico de Retrieval-Augmented Generation (RAG) do SEI-IA Assistente, arquivado sob `scripts/legado/sei_ia/`. O chat ativo opera com o agente Session (`agents/session_agent/`), utilizando os modos injected e filesystem. A infraestrutura de embeddings e o bootstrap de banco permanecem ativos em `sei_ia/` para sustentar a inicialização protegida e o lifespan da aplicação.

## Conteúdo

1. [Visão Geral](overview.md) - Como o RAG clássico funcionava
2. [Embeddings](embeddings.md) - Geração e validação de embeddings
3. [Retrieval](retrieval.md) - Busca vetorial e multi-query retrieval
4. [Indexação Automática](auto-indexing.md) - Auto-indexação de documentos ausentes

## O que é RAG?

**R**etrieval-**A**ugmented **G**eneration é uma técnica que combina:
- **Retrieval**: Busca de informações relevantes em uma base de conhecimento vetorial
- **Augmented**: Enriquecimento do contexto com essas informações
- **Generation**: Geração de resposta usando LLM com o contexto enriquecido

## Por que era usado no fluxo clássico?

- Documentos muito grandes que não cabiam no contexto do LLM
- Precisão: Respostas baseadas em trechos específicos do documento
- Eficiência: Processa apenas as partes relevantes
- Rastreabilidade: Fontes citáveis na resposta

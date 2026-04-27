# Sistema RAG / RAG System

Esta seção documenta o sistema de Retrieval-Augmented Generation (RAG) do SEI-IA Assistente.

## Conteúdo / Contents

1. [Visão Geral](overview.md) - Como o RAG funciona
2. [Embeddings](embeddings.md) - Geração de embeddings
3. [Retrieval](retrieval.md) - Busca de chunks similares
4. [Indexação Automática](auto-indexing.md) - Auto-indexação de documentos

## O que é RAG?

**R**etrieval-**A**ugmented **G**eneration é uma técnica que combina:
- **Retrieval**: Busca de informações relevantes em uma base de conhecimento
- **Augmented**: Enriquecimento do contexto com essas informações
- **Generation**: Geração de resposta usando LLM com o contexto enriquecido

## Por que usar RAG?

- Documentos muito grandes que não cabem no contexto do LLM
- Precisão: Respostas baseadas em trechos específicos do documento
- Eficiência: Processa apenas as partes relevantes
- Rastreabilidade: Fontes citáveis na resposta

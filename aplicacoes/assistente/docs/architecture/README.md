# Arquitetura / Architecture

Esta seção descreve a arquitetura do SEI-IA Assistente.

## Conteúdo / Contents

1. [Visão Geral](overview.md) - Arquitetura geral do sistema e fluxo Session
2. [Componentes](components.md) - Detalhes de cada componente da aplicação ativa

Somente RAG, pergunta e seus auxiliares diretos permanecem em `scripts/legado/`. O grafo LangGraph clássico foi excluído (consulte `scripts/legado/README.md`).

## Princípios Arquiteturais

- **Modularidade**: Componentes independentes e reutilizáveis
- **Assíncrono**: Operações I/O-bound são async
- **Observabilidade**: Logs, métricas e traces integrados
- **Escalabilidade**: Design para múltiplos workers

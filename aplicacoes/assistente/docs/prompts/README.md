# Prompts

Esta seção documenta os prompts utilizados pelo SEI-IA Assistente.

## Conteúdo

1. [Prompts de Sistema](system-prompts.md)
2. [Prompts de Intenção](intent-prompts.md)
3. [Prompts de Geração](generation-prompts.md)

## Localização

- **Session Agent (ativo)**: `sei_ia/agents/session_agent/prompts.py` (instruções de sistema, modos injected/filesystem e tratamento de mídias/anexos)
- **Busca Web (ativa)**: prompts internos em `sei_ia/agents/websearch/`
- **Prompts do sistema base**: `sei_ia/agents/prompts/system.py` e `context_formatters.py`
- **Prompts clássicos preservados**: arquivados sob `scripts/legado/sei_ia/agents/prompts/`

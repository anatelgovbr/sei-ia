# Web Search Agent

> Busca, coleta e persistência de fontes pela stack SearXNG

## Função

A busca web é ativada quando a requisição envia `use_websearch=true`. O Assistente
consulta o SearXNG, coleta as páginas com fastCRW e usa Byparr como fallback para
sites com proteção antibot. O fluxo não usa Azure AI Foundry nem Bing Grounding.

## Componentes

| Componente | Responsabilidade |
|---|---|
| `SearxCrawlAgent` | Busca no SearXNG, seleciona URLs e coleta páginas com fastCRW/Byparr |
| `WebResearchAgent` | Busca rasa, salva páginas em `web/` na sessão e devolve janelas ao agente principal |
| `DeepResearchAgent` | Busca profunda com planejamento, extração e síntese internas |

O `session_stream` escolhe entre `WebResearchAgent` e `DeepResearchAgent` por
`ASSISTENTE_SESSION_WEB_TOOL`. Os dois usam as mesmas URLs internas da stack.

## Configuração

As URLs e limites não secretos ficam no `default.env`. O único segredo específico é
`SEARXNG_SECRET_KEY`, presente no `security.env`; gere-o com `openssl rand -hex 32`
antes da primeira subida da stack.

A infraestrutura permanece agrupada no profile Compose `web-search`, ativado pelos
comandos oficiais do Makefile. Assim, `make up` sobe `infra-searxng`,
`infra-fastcrw`, `infra-byparr`, `infra-lightpanda`, `infra-chrome` e `infra-marker`
junto com a stack. Ao executar o Compose diretamente, informe
`--profile web-search`.

## Uso na API

```json
{
  "id_usuario": 1,
  "text": "Últimas notícias sobre 5G",
  "use_websearch": true
}
```

As fontes coletadas são associadas à resposta e, no `session_stream`, também ao
manifesto da sessão. `use_thinking` pode alterar o `reasoning_effort` do modelo, mas
não seleciona um alias de modelo separado.

---

## Próximos passos

- [Intent Selector](intent-selector.md) - Classificação de intenções
- [Visão Geral dos Agentes](overview.md) - Arquitetura completa

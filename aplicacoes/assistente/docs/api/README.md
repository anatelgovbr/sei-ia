# API

Esta seção documenta a API REST do SEI-IA Assistente.

## Conteúdo / Contents

1. [Endpoints](endpoints.md) - Todos os endpoints disponíveis
2. [Modelos de Dados](models.md) - Request/Response schemas
3. [Exemplos de Uso](examples.md) - Exemplos práticos

## URL Base

```
http://localhost:8088
```

## Autenticação

Atualmente a API não requer autenticação. A autenticação é gerenciada pela aplicação SEI.

## Formato

- Content-Type: `application/json`
- Respostas em streaming: `text/event-stream`

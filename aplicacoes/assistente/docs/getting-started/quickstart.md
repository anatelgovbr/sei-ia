# Quickstart

## Preparação

Complete a [instalação](installation.md) e configure as
[variáveis de ambiente](environment.md). No desenvolvimento, use Python 3.12 e a
`.venv` do Assistente. PostgreSQL/pgvector, Redis, LiteLLM e SEI precisam estar
acessíveis; iniciar a API executa o bootstrap de banco e do checkpointer.

Execute do diretório `aplicacoes/assistente`:

```bash
uv run uvicorn sei_ia.main:app --reload --port 8088
```

Esse comando inicia somente a aplicação local. Não use uma stack de deploy como
checkout de desenvolvimento.

## Verificar a API

```bash
curl --fail http://localhost:8088/health
```

Resposta esperada: `{"status":"OK"}`. O health check não substitui uma chamada real
ao modelo.

## Enviar uma mensagem

O único endpoint de chat é `/llm_lang/session_stream`. Troque os IDs ilustrativos
por usuário e tópico autorizados:

```bash
curl --no-buffer --fail-with-body \
  http://localhost:8088/llm_lang/session_stream \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{
    "id_usuario": 1,
    "id_topico": 123,
    "text": "Explique o que é o SEI.",
    "id_procedimentos": [],
    "use_websearch": false,
    "use_thinking": false,
    "no_cache": false
  }'
```

A resposta chega em frames SSE com `type` e conteúdo em `data`. Exiba os frames
`content`, trate `error` e espere `metadata` seguida de `end`. HTTP 200 sozinho
não significa sucesso, pois um erro pode chegar depois da abertura do stream.

Para uma segunda mensagem, mantenha `id_usuario` e `id_topico` e envie
`no_cache: false`. O histórico sincronizado do SEI também participa da continuidade.

## Documentos, anexos e busca web

- Documentos entram em `id_procedimentos[].id_documentos[]`.
- Paginação usa `pag_doc_init` e `pag_doc_end` no item documental.
- Anexos referenciam uploads recentes do SEI em `arquivos_avulsos`.
- `use_websearch: true` habilita a ferramenta de busca configurada.
- `use_thinking: true` solicita reasoning no modelo selecionado.

Veja os [exemplos completos de SSE](../api/examples.md). Não use `response.json()`
para interpretar uma resposta de chat.

## Próximos passos

- [Endpoints e feedback](../api/endpoints.md)
- [Arquitetura](../architecture/overview.md)
- [Modelos de dados](../api/models.md)

Somente RAG, pergunta e seus auxiliares diretos permanecem em `scripts/legado/`
(consulte `scripts/legado/README.md`). A infraestrutura de embeddings permanece
ativa em `sei_ia/` para o lifespan de inicialização e integridade de banco.
Não há republicação de endpoints antigos nem suporte operacional para o código arquivado.

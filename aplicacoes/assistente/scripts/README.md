# Smoke tests do Assistente

Os scripts desta pasta têm dois modos de execução: host e stack. A diferença é
onde a API do Assistente está rodando e, portanto, qual endereço LiteLLM pode ser
resolvido.

| Entrada | API do Assistente | Quando usar |
| --- | --- | --- |
| `smoke_session_host.py` | Processo local, via uvicorn | Ponto de entrada canônico: sessão `/llm_lang/session_stream` com payload JSON e documentos reais do SEI |
| `smoke_session_stack.sh` | Containers já iniciados pelo Compose | Sessão real contra `https://localhost:8088`, com LiteLLM interno da stack |
| `smoke_helpers.py` | Módulo de helpers | Helpers de diagnóstico e ambiente compartilhados (usados por `session_local_e2e.py` e medições) |
## Modo host

```bash
cd aplicacoes/assistente
uv run python scripts/smoke_session_host.py \
  --payload scripts/req_8116731.json \
  --langfuse-trace-id 0123456789abcdef0123456789abcdef \
  --no-blob-check
```

A CLI clássica `smoke_endpoint_host.py` foi excluída.
Suas rotinas auxiliares reutilizáveis permanecem em `scripts/smoke_helpers.py`.
Para validar o Session, use exclusivamente `smoke_session_host.py` ou `smoke_session_stack.sh`.
Na revisão de código, prefira iniciar um processo supervisionado da worktree e usar
`--no-serve` com `--url` explícita, sem reutilizar um servidor de origem desconhecida.
No host, `infra-litellm:4000` não é resolvível: esse nome só existe na rede do
Compose. Configure `ASSISTENTE_LITELLM_PROXY_URL` para um endpoint acessível pelo
host e, se necessário, `ASSISTENTE_LITELLM_PROXY_API_KEY`. Para o fluxo que baixa
documentos, configure também os envs do ambiente SEI com conteúdo completo; os valores nunca
devem ser impressos ou commitados. Se a configuração `ASSISTENTE_*` ainda apontar
para `infra-litellm`, o launcher host substitui URL e chave pelos equivalentes
`LITELLM_*` já disponíveis no ambiente. Ele não remapeia aliases de modelos.
Um proxy configurado explicitamente em `ASSISTENTE_LITELLM_PROXY_URL` é preservado.

Se `aplicacoes/assistente/.env` não existir, `smoke_session_host.py` o cria com
permissão `0600` a partir dos env files do worktree; um arquivo existente não é
sobrescrito. O smoke retorna código diferente de zero para HTTP diferente de 200,
qualquer frame `error` ou SSE sem os frames terminais `metadata` e `end`.

## Aceitação manual da release

A aceitação funcional externa é manual pela interface do SEI: entre com um usuário
autorizado, abra o Assistente, envie `Oi` e confirme que uma resposta aparece.
Esse teste exercita em conjunto o módulo, o certificado, o gateway, o backend e o
modelo. Os scripts desta pasta são auxiliares de diagnóstico e não substituem essa
aceitação.

## Traces Langfuse do comparativo

Para enviar traces ao projeto `comparativo-deepagents-classico`, siga a seção
[Preparação do benchmark](../experimentos/latencia-session-vs-classico/README.md#preparação),
que é a fonte única para o arquivo protegido `langfuse-comparativo.env`. Antes do
smoke, mantenha `ASSISTENTE_USE_LANGFUSE=true`; `--langfuse-trace-id` é opcional e
facilita localizar exatamente o request no Langfuse. Para validar reutilização,
mantenha o servidor, `id_usuario` e `id_topico`; envie duas mensagens com
`no_cache: false` no JSON. Omitir `--no-cache` não sobrescreve `true` no payload.
Verifique conteúdo, continuidade, metadata e end, não apenas o exit code.

```bash
cd /caminho/para/monorepo
set -a
. ./langfuse-comparativo.env
set +a

cd aplicacoes/assistente
uv run python scripts/smoke_session_host.py --payload scripts/req_8116731.json
```

## Modo stack

Use uma stack já provisionada pelo fluxo de deploy autorizado e execute a partir
da pasta da aplicação. O smoke não comprova que a imagem corresponde à worktree
alterada; confirme a procedência antes de usá-lo como evidência de revisão.

```bash
cd aplicacoes/assistente
scripts/smoke_session_stack.sh \
  --payload scripts/req_8116731.json \
  --no-blob-check
```

O launcher não executa `make up`, não reinicia e não derruba containers. Ele
verifica o health em `https://localhost:${ASSISTENTE_PORT:-8088}/health`, usa por
defeito `.runtime/certs/seiia.cert.pem` e encaminha os demais argumentos para
`smoke_session_host.py` com `--no-serve`. Assim, o request passa pela API
publicada pelo nginx e a aplicação dentro do container resolve
`infra-litellm:4000`.

Variáveis úteis:

- `ASSISTENTE_PORT`: porta publicada pelo nginx; padrão `8088`.
- `ASSISTENTE_CONTAINER_URL`: URL completa publicada, se não for localhost.
- `ASSISTENTE_CONTAINER_CERT`: certificado CA para essa URL HTTPS.

## Payload

O ponto de entrada host é `scripts/smoke_session_host.py`. Launchers antigos de
compatibilidade não fazem parte do contrato atual.

Para a sessão, o payload deve usar `id_documentos` e, em cada item, o campo
`id_documento`. O script encaminha o JSON sem converter esses identificadores;
`download_ext` e `precisa_ocr` também são preservados.

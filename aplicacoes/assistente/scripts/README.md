# Smoke tests do Assistente

Os scripts desta pasta têm dois modos de execução: host e stack. A diferença é
onde a API do Assistente está rodando e, portanto, qual endereço LiteLLM pode ser
resolvido.

| Entrada | API do Assistente | Quando usar |
| --- | --- | --- |
| `smoke_endpoint_host.py` | Em memória, via FastAPI `TestClient` | Diagnóstico isolado de uma implementação interna; não é gate de release |
| `smoke_session_host.py` | Processo local, via uvicorn | Sessão `/llm_lang/session_stream` com payload JSON e documentos reais do SEI |
| `smoke_session_stack.sh` | Containers já iniciados pelo Compose | Sessão real contra `https://localhost:8088`, com LiteLLM interno da stack |

## Modo host

```bash
cd aplicacoes/assistente
uv run python scripts/smoke_session_host.py \
  --payload scripts/request_example.json \
  --langfuse-trace-id 0123456789abcdef0123456789abcdef \
  --no-blob-check
```

`smoke_endpoint_host.py` usa `TestClient`, não valida a integração publicada nem
sobe um servidor externo do Assistente. `smoke_session_host.py` sobe uvicorn local
se necessário, a menos que receba `--no-serve`.

No host, `infra-litellm:4000` não é resolvível: esse nome só existe na rede do
Compose. Configure `ASSISTENTE_LITELLM_PROXY_URL` para um endpoint acessível pelo
host e, se necessário, `ASSISTENTE_LITELLM_PROXY_API_KEY`. Para o fluxo que baixa
documentos, configure também os envs do ambiente SEI com conteúdo completo; os valores nunca
devem ser impressos ou commitados. Se a configuração `ASSISTENTE_*` ainda apontar
para `infra-litellm`, o launcher host substitui URL, chave e aliases standard/mini/nano
pelos equivalentes `LITELLM_*` já disponíveis no ambiente. Um proxy host configurado
explicitamente em `ASSISTENTE_LITELLM_PROXY_URL` é preservado.

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

## Modo stack

Suba a stack em um terminal e, em outro, execute o launcher a partir da pasta da
aplicação:

```bash
# raiz do worktree
make up

# pasta da aplicação
cd aplicacoes/assistente
scripts/smoke_session_stack.sh \
  --payload scripts/request_example.json \
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

## Compatibilidade e payload

O antigo `scripts/session_real_test.py` continua como launcher de compatibilidade;
novos usos devem chamar `smoke_session_host.py`. O antigo `run_test.py` da raiz da
aplicação foi removido para manter todos os pontos de entrada nesta pasta.

Para a sessão, o payload deve usar `id_documentos` e, em cada item, o campo
`id_documento`. O script encaminha o JSON sem converter esses identificadores;
`download_ext` e `precisa_ocr` também são preservados.

# Exemplos de uso

O chat usa `POST /llm_lang/session_stream`. A resposta é SSE, não um JSON único.
Os IDs abaixo são ilustrativos; substitua-os por usuário, tópico e documentos
que você tem autorização para acessar.

## Health check

```bash
curl --fail http://localhost:8088/health
```

`{"status":"OK"}` confirma que a API atende. Isso não comprova acesso ao LLM ou ao SEI.

## Texto sem documentos

```bash
curl --no-buffer --fail-with-body \
  http://localhost:8088/llm_lang/session_stream \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{
    "id_usuario": 1,
    "id_topico": 123,
    "text": "O que é o SEI?",
    "id_procedimentos": [],
    "no_cache": false
  }'
```

Para continuar, envie outra mensagem com o mesmo `id_usuario` e `id_topico`.
Mantenha `no_cache: false`; `true` reseta a sessão e invalida caches documentais.

## Cliente Python

O endpoint emite um JSON por frame `data:`. Além do status HTTP, verifique frames
`error` e o encerramento com `metadata` seguido de `end`. Não repita automaticamente
uma requisição interrompida, pois ela pode ter produzido efeitos na sessão.

```python
import json

import httpx

payload = {
    "id_usuario": 1,
    "id_topico": 123,
    "text": "Explique o que é o SEI.",
    "id_procedimentos": [],
    "no_cache": False,
}

metadata = None
ended = False
with httpx.stream(
    "POST",
    "http://localhost:8088/llm_lang/session_stream",
    json=payload,
    headers={"Accept": "text/event-stream"},
    timeout=300,
) as response:
    response.raise_for_status()
    for line in response.iter_lines():
        if not line.startswith("data:"):
            continue
        event = json.loads(line[5:].strip())
        kind = event.get("type")
        if kind == "error":
            raise RuntimeError(f"Falha SSE: {event.get('status_code')}")
        if kind == "content":
            print(event["data"], end="", flush=True)
        elif kind == "metadata":
            metadata = event["data"]
        elif kind == "end":
            if metadata is None:
                raise RuntimeError("Stream terminou sem metadata")
            ended = True

if not ended:
    raise RuntimeError("Stream interrompido antes de end")
```

## Documentos e paginação

Use o mesmo cliente com um payload documental:

```json
{
  "id_usuario": 1,
  "id_topico": 124,
  "text": "Qual é o objeto deste processo?",
  "id_procedimentos": [
    {
      "id_procedimento": "53500.000001/2024-00",
      "metadata": {},
      "id_documentos": [
        {
          "id_documento": "12345678",
          "download_ext": true,
          "pag_doc_init": 5,
          "pag_doc_end": 10
        }
      ]
    }
  ],
  "no_cache": false
}
```

A paginação é controlada pelos campos do documento, não por números no texto.
Para comparar documentos, adicione os itens à lista `id_documentos` e peça a
comparação em `text`. Para resumir, altere a instrução, mantendo o transporte SSE.
Confira `documentos_indisponiveis` na metadata; uma resposta parcial não comprova
que todos os documentos foram obtidos.

## Busca web e reasoning

- `use_websearch: true` habilita a ferramenta configurada no Session. A stack usa
  SearXNG e serviços de coleta, não Bing como contrato da API.
- `use_thinking: true` solicita reasoning no modelo selecionado. Não existe um
  endpoint público separado para o tier `mini`.
- Frames `status` e `reasoning` são distintos de `content`.

## Anexos

O payload referencia um upload recém-criado no SEI, não um arquivo local ou multipart:

```json
{
  "id_usuario": 1,
  "id_topico": 125,
  "text": "Resuma o arquivo anexado.",
  "id_procedimentos": [],
  "arquivos_avulsos": [
    {
      "id_arquivo_avulso": 456,
      "nome_arquivo_avulso": "nota.txt",
      "extensao_arquivo_avulso": "txt"
    }
  ],
  "no_cache": false
}
```

Uploads elegíveis são sinalizados para remoção no SEI após o sucesso. Não reutilize
um ID já consumido para um novo teste.

## Referências

- [Contrato dos endpoints](endpoints.md)
- [Modelos de dados](models.md)
- [Quickstart](../getting-started/quickstart.md)

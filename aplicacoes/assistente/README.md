# SEI IA Assistente

API de assistência generativa do Módulo SEI IA. Ela usa documentos do SEI,
PostgreSQL/pgvector, Redis e os aliases publicados pelo proxy LiteLLM.

> A instalação externa não é feita a partir desta pasta. Use o
> [manual integrado](../../docs/INSTALL.md), que instala a stack completa por
> código-fonte com `make up`, TLS no gateway Nginx e configuração exata dos
> arquivos de ambiente.

## Desenvolvimento local

Requisitos:

- Python 3.12;
- [uv](https://docs.astral.sh/uv/);
- dependências da stack acessíveis no ambiente de desenvolvimento.

Prepare o ambiente da aplicação sem usar o Python do sistema:

```bash
cd aplicacoes/assistente
uv sync --locked
```

O `.env.example` desta pasta é exclusivo do loop de desenvolvimento da aplicação.
No deploy integrado, as fontes de configuração são `default.env`, `security.env` e
`litellm_config.yaml` na raiz do monorepo.

Com as dependências externas configuradas:

```bash
uv run uvicorn sei_ia.main:app --reload --port 8088
```

Qualidade e testes:

```bash
make check
make test
```

## Integração com modelos

O Assistente fala com modelos somente pelo LiteLLM. No deploy integrado, a chave do
proxy é obrigatória e vem de `LITELLM_PROXY_API_KEY`; credenciais de provedores ficam
em `security.env`, nunca no YAML ou no código.

O template da raiz mantém os aliases exigidos pela stack: `standard`, `mini`, `nano`,
`embedding` e `speech-to-text`. O comando
`make check` valida autenticação, saúde e presença desses aliases.
Esses são os únicos nomes enviados pela aplicação nos caminhos padrão; os valores
físicos de `LITELLM_*_MODEL` ficam no proxy como `model`/`base_model` e preservam a
identidade dos embeddings.

`use_thinking` reutiliza o modelo selecionado e altera o `reasoning_effort` da
requisição; não existe um alias de modelo `think`.

## Documentação da aplicação

```bash
uv run mkdocs build --strict
uv run mkdocs serve
```

Consulte `docs/` para arquitetura e integrações internas. Para topologia da stack,
TLS, instalação do módulo e aceitação funcional no SEI, prevalece o
[manual da raiz](../../docs/INSTALL.md).

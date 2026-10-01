# Azure OpenAI

> Como configurar o SEI-IA Assistente para usar, via Azure OpenAI, os
> modelos já homologados no projeto.

> Fonte de verdade do formato do `litellm_config.yaml`:
> `litellm_config.template.yaml` na raiz do monorepo e
> `docs/INSTALL.md` (seção "Configuração dos modelos LLM e LiteLLM").

## Arquitetura

O SEI-IA Assistente utiliza **LiteLLM Proxy** para comunicação com Azure OpenAI. Isso permite:

- Centralizar credenciais e configurações no proxy
- Facilitar troca de modelos sem alterar código
- Suportar múltiplos providers (Azure, OpenAI, Anthropic, etc.)

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Assistente    │ ──── │  LiteLLM Proxy  │ ──── │  Azure OpenAI   │
│   (ChatOpenAI)  │      │  localhost:4000 │      │  (modelos LLM)  │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

Diferente do Bedrock/Vertex, o Azure OpenAI não tem um gate de aprovação
por modelo: a unidade de configuração é o **deployment** — dá-se um nome
a um deployment apontando para um modelo + versão específicos, e as
chamadas de API referenciam esse nome, não o nome cru do modelo (ver
"Pré-requisitos no Azure" abaixo).

## Papéis (`agents:*`) e os 5 aliases fixos

Cada requisição ao LiteLLM Proxy carrega uma tag `agents:<papel>`, que
identifica a função que o agente está exercendo naquele momento
(classificar, buscar, extrair, responder ao usuário etc.). Com
`router_settings.enable_tag_filtering: true`, essa tag funciona como
**controle de acesso**: uma requisição marcada com um papel que o
deployment escolhido não declara em `litellm_params.tags` é rejeitada com
`401 Not allowed to access model due to tags configuration`.

| Papel (`agents:<papel>`) | Função no sistema |
|---|---|
| `principal` | Modelo da sessão de chat — gera a resposta final apresentada ao usuário. |
| `classificador` | Classificações curtas e baratas: decide se uma resposta precisa de aviso/disclaimer, faz a extração de conteúdo dentro dos subagentes exploradores do Deep Agents. |
| `busca_web` | Conduz e gera as buscas do fluxo de pesquisa web (geração de query, busca especulativa). |
| `explorador` | Subagentes de exploração paralela lançados pelo agente principal (tool `task` do Deep Agents, com teto de concorrência) — investigam documentos/tópicos em paralelo, priorizando custo baixo sobre profundidade. |
| `ocr` | Extração de texto de imagens e documentos escaneados. |
| `triagem_busca` | Classifica o pedido de busca web em um modo de execução (página única, site restrito, pesquisa multi-entidade, busca simples) antes de a pesquisa começar. |
| `embedding` | Geração de vetores de embedding para indexação/RAG. |
| `audio_transcription` | Transcrição de áudio (Whisper). |

No `litellm_config.yaml`, cada papel é atendido por um dos **5 aliases
fixos** — `standard`, `mini`, `nano`, `embedding`, `speech-to-text`. São
nomes **reservados**: o gerador de config em CI/CD rejeita qualquer
entrada de `LITELLM_MODEL_CATALOG` que tente redefinir um deles.
`model_name` continua sendo o alias, não o nome do deployment — o
deployment entra em `litellm_params.model`/`model_info.base_model`:

| Alias (`model_name`) | Papéis que atende | Deployment (variável) | Credencial |
|---|---|---|---|
| `standard` | `principal` | `LITELLM_STANDARD_MODEL` | `LITELLM_STANDARD_API_*` |
| `mini` | `classificador`, `busca_web` | `LITELLM_MINI_MODEL` | `LITELLM_MINI_API_*` |
| `nano` | `explorador`, `ocr`, `triagem_busca` | `LITELLM_NANO_MODEL` | `LITELLM_NANO_API_*` |
| `embedding` | `embedding` | `LITELLM_EMBEDDING_MODEL` | `LITELLM_EMBEDDING_API_*` |
| `speech-to-text` | `audio_transcription` | `LITELLM_STT_MODEL` | `LITELLM_STT_API_*` |

Cada alias tem sua própria credencial (`API_BASE`/`API_KEY`/
`API_VERSION`) — `standard`, `mini` e `nano` podem apontar para
deployments em recursos Azure diferentes, sem depender uns dos outros.

> **`nano` e `embedding` são um contrato entre apps, não só do
> Assistente**: `libs/sei_extraction` (compartilhada por Assistente,
> Similaridade e ETL) usa `"nano"` como default de `ocr_model`, e o
> `etl-airflow` replica `"embedding"` como alias padrão de roteamento
> (`jobs/envs.py`). Trocar o deployment por trás desses dois aliases muda
> o modelo de OCR/embedding usado pelas outras aplicações também.

> **Importante**: um deployment adicional pode ser liberado para mais de
> um papel ao mesmo tempo, listando todas as tags relevantes na mesma
> entrada (ex.: `tags: ["agents:explorador", "agents:ocr"]`) sem mexer
> nos 5 aliases fixos — ver "Configuração do LiteLLM Proxy" abaixo.

## Modelos Homologados

Deployments GPT validados por cenário (classificador, explorador, OCR) e
comportamento real de `reasoning_effort`:

| Modelo | Classificador / Explorador | OCR (visão) | `reasoning_effort` |
|---|---|---|---|
| gpt-5.4 | OK | OK | `none`/`low`/`medium`/`high` — todos com efeito real e crescente |
| gpt-5.4-mini | OK | OK | `none`/`low`/`medium`/`high` — todos com efeito real |
| gpt-5.4-nano | OK | OK | `none`/`low`/`medium`/`high` — todos com efeito real |
| gpt-5.5 | OK | OK | `none`/`low`/`medium`/`high` — todos com efeito real |
| gpt-5.6-luna | OK | OK | `none`/`low`/`medium`/`high` — todos com efeito real |
| gpt-5.6-terra | OK | OK | `none`/`low`/`medium`/`high` — todos com efeito real |
| gpt-5.3-chat (`gpt-chat-latest`) | OK | OK | Só aceita `medium` — `low`/`high` são rejeitados com erro explícito (*"Supported values are: 'medium'"*). `none`/`medium` são aceitos, mas nenhum dos dois gera raciocínio de fato — este modelo não expõe reasoning explícito por esse parâmetro |

`text-embedding-3-small`: 1536 dimensões, alias `embedding`.
`text-embedding-3-large`: 3072 dimensões, alias `embedding` (alternativa de maior qualidade/custo).
`whisper` / `gpt-transcribe`: alias `speech-to-text` — transcrição de áudio via `/v1/audio/transcriptions`.

> **Atenção — Whisper está em descontinuação na Azure**: se não for
> possível provisionar um deployment `whisper` no seu recurso, use
> `gpt-transcribe` no lugar — mesmo endpoint `/v1/audio/transcriptions`,
> funcionando em todos os formatos e cenários testados (mp3/wav/m4a/webm,
> áudio com ruído, chunking de áudio longo) e ~25% mais barato por
> minuto. Único ponto ainda em aberto: validar com áudio real longo
> (15-20 min), já que o teste de chunking usou áudio sintético
> repetitivo.
>
> **Exige `response_format` explícito**: o `gpt-transcribe` rejeita
> `verbose_json` com HTTP 400, e o LiteLLM injeta exatamente esse formato
> quando o cliente não manda nenhum (para obter a duração e calcular
> custo). O Assistente envia `response_format="json"` explícito em
> `_transcribe_via_whisper`; um cliente próprio que fale com o proxy
> precisa fazer o mesmo.

> **Nota**: a disponibilidade de modelos depende do que está provisionado
> no seu recurso Azure OpenAI — reavalie esta lista para o conjunto de
> deployments realmente criado antes de assumi-la como definitiva.

## Limitações

- **`gpt-5.3-chat` não expõe reasoning explícito de verdade** — aceita o
  parâmetro `reasoning_effort`, mas só `medium` é aceito sem erro entre os
  4 níveis, e mesmo assim não gera tokens de raciocínio mensuráveis. Não é
  um bom candidato para o alias `standard` (ou qualquer outro que precise
  de controle fino de `reasoning_effort`).
- **Nem todo deployment aceita todos os níveis de `reasoning_effort`** —
  ver coluna da tabela acima. Antes de liberar um deployment novo para um
  papel que varia o nível de raciocínio, valide os 4 valores
  individualmente; não assumir que membros da mesma família de modelo
  (`gpt-5.x`) se comportam de forma idêntica.
- Diferente do AWS Bedrock e do GCP Vertex AI, o Azure OpenAI não tem
  gate de aprovação documentado por modelo — a barreira real de
  configuração é a criação do **deployment** com quota (`capacity`)
  suficiente, não uma aprovação de acesso (ver "Pré-requisitos no Azure").

## Configuração

### Pré-requisitos no Azure

- Um recurso **Azure OpenAI** (Azure AI Foundry) provisionado, em uma
  região onde os modelos desejados estejam disponíveis para deployment.
- Um **deployment** criado para cada alias que será usado — o Azure não
  libera "modelo" diretamente, é preciso criar um deployment nomeado
  apontando para `modelo + versão`; as chamadas de API referenciam esse
  nome de deployment.
- Capacidade (quota) alocada ao deployment em unidades de TPM (parâmetro
  `capacity`, 1 unidade = 1.000 tokens/min) — sem quota suficiente, as
  chamadas retornam erro de rate limit mesmo com o deployment criado.
- Uma política de atualização de versão por deployment
  (`versionUpgradeOption`), configurável via portal/REST/CLI:
  - `OnceNewDefaultVersionAvailable` — atualiza automaticamente até 2
    semanas após uma nova versão virar default.
  - `OnceCurrentVersionExpired` — atualiza só quando a versão atual é
    descontinuada (comportamento padrão quando o valor é `null`).
  - `NoAutoUpgrade` — nunca atualiza automaticamente; ao expirar, o
    deployment para de funcionar até ser recriado/apontado manualmente.

### Credencial (API Key do recurso)

**Passo a passo:**

**1. Fazer login no Azure Portal**

- Acesse [portal.azure.com](https://portal.azure.com) com uma conta que
  tenha permissão para gerenciar recursos Azure OpenAI.

**2. Criar (ou localizar) o recurso Azure OpenAI**

- Na busca superior, digite `Azure OpenAI` e crie um recurso (ou abra um
  já existente) na região desejada.

**3. Criar os deployments necessários**

- Dentro do recurso, acesse **Model deployments** (ou pelo **Azure AI
  Foundry**, dependendo da interface).
- Para cada alias desejado (`standard`, `mini`, `nano`, `embedding`,
  `speech-to-text`), crie um deployment: escolha o modelo base, a versão,
  defina um nome de deployment e a capacidade (`capacity`, em TPM).
- Anote o **nome do deployment** — é esse nome, não o nome cru do modelo,
  que vai na variável `LITELLM_*_MODEL` correspondente.

**4. Obter a chave e o endpoint**

- Na página de visão geral do recurso, acesse **Keys and Endpoint**.
- Copie uma das duas chaves (`KEY 1` ou `KEY 2`) e o **Endpoint**
  (formato `https://<seu-recurso>.openai.azure.com/`).

**Como usar:**

- Trate a chave como uma credencial sensível, equivalente a uma senha —
  nunca commite esse valor em controle de versão.
- Repita esse processo para cada alias que apontar para um recurso Azure
  diferente — cada alias tem sua própria credencial no `security.env`.

### Variáveis de Ambiente

```bash
# URL do proxy LiteLLM
LITELLM_PROXY_URL=http://localhost:4000

# API key do proxy (opcional, depende da configuração do proxy)
# LITELLM_PROXY_API_KEY=sua_api_key

# Limites de contexto e output
ASSISTENTE_OUTPUT_TOKENS_STANDARD_MODEL=32768
ASSISTENTE_CTX_LEN_STANDARD_MODEL=250000
```

### Configuração do LiteLLM Proxy

O template usa `os.environ/<VAR>` — o LiteLLM resolve essas referências
sozinho a partir das variáveis de ambiente do container, sem precisar de
nenhum passo de substituição manual. Os 5 `model_name` (`standard`/
`mini`/`nano`/`embedding`/`speech-to-text`) **não mudam**; o que muda por
provider é o valor de `LITELLM_*_MODEL` (o nome do deployment) e das
credenciais.

**Trecho relevante do `litellm_config.template.yaml`:**

```yaml
model_list:
  - model_name: standard
    litellm_params:
      model: os.environ/LITELLM_STANDARD_MODEL       # azure/<deployment>
      api_base: os.environ/LITELLM_STANDARD_API_BASE
      api_key: os.environ/LITELLM_STANDARD_API_KEY
      api_version: os.environ/LITELLM_STANDARD_API_VERSION
      tags: ["agents:principal"]
    model_info:
      base_model: os.environ/LITELLM_STANDARD_MODEL

  - model_name: mini
    litellm_params:
      model: os.environ/LITELLM_MINI_MODEL
      api_base: os.environ/LITELLM_MINI_API_BASE
      api_key: os.environ/LITELLM_MINI_API_KEY
      api_version: os.environ/LITELLM_MINI_API_VERSION
      tags: ["agents:classificador", "agents:busca_web"]
    model_info:
      base_model: os.environ/LITELLM_MINI_MODEL

  - model_name: nano
    litellm_params:
      model: os.environ/LITELLM_NANO_MODEL
      api_base: os.environ/LITELLM_NANO_API_BASE
      api_key: os.environ/LITELLM_NANO_API_KEY
      api_version: os.environ/LITELLM_NANO_API_VERSION
      tags: ["agents:explorador", "agents:ocr", "agents:triagem_busca"]
    model_info:
      base_model: os.environ/LITELLM_NANO_MODEL

  - model_name: embedding
    litellm_params:
      model: os.environ/LITELLM_EMBEDDING_MODEL
      api_base: os.environ/LITELLM_EMBEDDING_API_BASE
      api_key: os.environ/LITELLM_EMBEDDING_API_KEY
      api_version: os.environ/LITELLM_EMBEDDING_API_VERSION
      tags: ["agents:embedding"]
    model_info:
      base_model: os.environ/LITELLM_EMBEDDING_MODEL

  - model_name: speech-to-text
    litellm_params:
      model: os.environ/LITELLM_STT_MODEL
      api_base: os.environ/LITELLM_STT_API_BASE
      api_key: os.environ/LITELLM_STT_API_KEY
      api_version: os.environ/LITELLM_STT_API_VERSION
      tags: ["agents:audio_transcription"]
    model_info:
      base_model: os.environ/LITELLM_STT_MODEL

router_settings:
  enable_tag_filtering: true
```

Preencha em `security.env`, usando o **nome do deployment** (não o nome
cru do modelo):

```dotenv
LITELLM_STANDARD_MODEL=azure/<nome-do-deployment-standard>
LITELLM_STANDARD_API_BASE=https://<seu-recurso>.openai.azure.com/
LITELLM_STANDARD_API_KEY=<sua-api-key>
LITELLM_STANDARD_API_VERSION=<versao-da-api>

LITELLM_MINI_MODEL=azure/<nome-do-deployment-mini>
LITELLM_MINI_API_BASE=...
LITELLM_MINI_API_KEY=...
LITELLM_MINI_API_VERSION=...
```

`<versao-da-api>` é a versão da API REST do Azure OpenAI (ex.:
`2024-10-21`) — consulte a documentação oficial da Azure para a versão
vigente; fixar uma data como referência de longo prazo aqui envelheceria
rápido, já que a Azure publica novas versões com frequência.

Para liberar um modelo extra sem mexer nos 5 aliases fixos, use o
catálogo opcional `LITELLM_MODEL_CATALOG` (variável de CI/CD tipo File,
JSON `[{"model": "...", "roles": [...]}]`) — ver `docs/INSTALL.md`. O
gerador rejeita qualquer item que tente redefinir um dos 5 nomes
reservados.

## Factory de Modelos

O arquivo `sei_ia/services/llm_models/get_model.py` é o ponto central para
obtenção de modelos. A função recebe o **papel do agente**; internamente
resolve o tier (`standard`/`mini`/`nano`) e monta a tag
`agents:<agent_tag>` mandada ao proxy:

```python
def get_model(
    agent_tag: str,                      # 'principal', 'classificador', 'explorador',
                                          # 'ocr', 'busca_web' ou 'triagem_busca'
    temperature: float | None = None,
    model_override: str | None = None,   # modelo do catálogo, validado contra o proxy
    **kwargs,
) -> ChatOpenAI:
    """Cria instância do modelo LLM via LiteLLM Proxy."""
    config = get_model_config(agent_tag, model_override=model_override)
    # config["model"] é o alias (standard/mini/nano); a tag
    # "agents:<agent_tag>" vai junto na requisição via extra_body.
    ...
```

### Uso

```python
from sei_ia.services.llm_models.get_model import get_model

# Classificação curta
model = get_model("classificador", temperature=0.7)
response = model.invoke("Olá!")

# Com LangChain chains
chain = prompt | get_model("principal")
```

## Embeddings

Embeddings também são gerados via LiteLLM Proxy:

- Modelo: `text-embedding-3-small`
- Dimensões: 1536
- Máximo de tokens: 8191

**Arquivo**: `sei_ia/services/embedder/embedding_generator.py`

> **Atenção**: se a aplicação já tiver sido usada com outro provider de
> embedding, a dimensão do vetor pode ser diferente da configurada
> anteriormente. Trocar de provider de embedding exige garantir que a
> coluna do banco (`vector(N)`) e o valor de dimensão configurado na
> aplicação estejam alinhados com o modelo em uso — e, se houver
> embeddings já persistidos com a dimensão antiga, eles precisam ser
> reprocessados, não apenas reconfigurados.

## Tratamento de Erros

O sistema trata erros de conexão com o proxy/Azure:

```python
from litellm.exceptions import APIConnectionError

try:
    response = model.invoke(prompt)
except (httpx.RemoteProtocolError, APIConnectionError) as exc:
    # Erro de conexão - streaming interrompido
    logger.exception(f"Erro de conexão: {exc}")
    raise HTTPException(status_code=500)
```

## Retry e Backoff

O retry é gerenciado em duas camadas:

1. **ChatOpenAI**: `max_retries=5` (configurável via `ASSISTENTE_MAX_RETRIES`)
2. **LiteLLM Proxy**: Configurações de retry do próprio proxy

Variáveis relacionadas:

```bash
ASSISTENTE_MAX_RETRIES=5
ASSISTENTE_BACKOFF_MAX_TRIES=99
ASSISTENTE_BACKOFF_MAX_TIME=240
ASSISTENTE_BACKOFF_INITIAL_WAIT=1.0
```

# Google Vertex AI

> Integração com modelos Gemini e Embeddings via LiteLLM Proxy

> Fonte de verdade do formato do `litellm_config.yaml`:
> `litellm_config.template.yaml` na raiz do monorepo e
> `docs/INSTALL.md` (seção "Configuração dos modelos LLM e LiteLLM").

## Arquitetura

O SEI-IA Assistente utiliza **LiteLLM Proxy** para comunicação com o Google Vertex AI. Isso permite:

- Centralizar credenciais e configurações no proxy
- Facilitar troca de modelos sem alterar código
- Suportar múltiplos providers (Azure, Vertex AI, OpenAI, Anthropic, etc.)

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Assistente    │ ──── │  LiteLLM Proxy  │ ──── │  Google Vertex  │
│   (ChatOpenAI)  │      │  localhost:4000 │      │  AI (Gemini)    │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

Diferente do Azure OpenAI, o Vertex AI não autentica por API key: o LiteLLM
Proxy autentica junto ao Google usando uma **credencial de service
account** (arquivo JSON), configurada em cada entrada do modelo.

## Papéis (`agents:*`) e os 5 aliases fixos

Cada requisição ao LiteLLM Proxy carrega uma tag `agents:<papel>`, que
identifica a função que o agente está exercendo naquele momento
(classificar, buscar, extrair, responder ao usuário etc.). Com
`router_settings.enable_tag_filtering: true`, essa tag funciona como
**controle de acesso**: uma requisição marcada com um papel que o modelo
escolhido não declara em `litellm_params.tags` é rejeitada com
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
| `audio_transcription` | Transcrição de áudio. |

No `litellm_config.yaml`, cada papel é atendido por um dos **5 aliases
fixos** — `standard`, `mini`, `nano`, `embedding`, `speech-to-text`. São
nomes **reservados**: o gerador de config em CI/CD rejeita qualquer
entrada de `LITELLM_MODEL_CATALOG` que tente redefinir um deles:

| Alias (`model_name`) | Papéis que atende |
|---|---|
| `standard` | `principal` |
| `mini` | `classificador`, `busca_web` |
| `nano` | `explorador`, `ocr`, `triagem_busca` |
| `embedding` | `embedding` |
| `speech-to-text` | `audio_transcription` |

No Vertex, "credencial" é a service account (arquivo JSON) mais
`vertex_project`/`vertex_location` — não o par `api_base`/`api_key` que o
gerador de CI/CD normalmente preenche via `LITELLM_*_API_*` (ver
"Configuração do LiteLLM Proxy" abaixo para o porquê isso importa). Cada
alias pode usar sua própria service account/projeto/região, apontando
para modelos físicos diferentes sem depender uns dos outros.

> **`nano` e `embedding` são um contrato entre apps, não só do
> Assistente**: `libs/sei_extraction` (compartilhada por Assistente,
> Similaridade e ETL) usa `"nano"` como default de `ocr_model`, e o
> `etl-airflow` replica `"embedding"` como alias padrão de roteamento
> (`jobs/envs.py`). Trocar o modelo por trás desses dois aliases muda o
> que é usado para OCR/embedding nas outras aplicações também.

> **Importante**: um modelo físico adicional pode ser liberado para mais
> de um papel ao mesmo tempo, listando todas as tags relevantes na mesma
> entrada (ex.: `tags: ["agents:explorador", "agents:ocr"]`), sem mexer
> nos 5 aliases fixos — ver "Configuração do LiteLLM Proxy" abaixo.

## Modelos Homologados

Modelos Gemini e Claude (via Model Garden) validados por cenário
(classificador, explorador, OCR/visão) e comportamento real de
`reasoning_effort`:

| Modelo | Classificador / Explorador | OCR (visão) | `reasoning_effort` |
|---|---|---|---|
| `gemini-2.5-pro` | OK | OK | Não aceita `none` (erro 400) — é "thinking sempre ligado" nesta geração; `low`(671)/`medium`(1781)/`high`(2290) com efeito real e crescente |
| `gemini-2.5-flash` | OK | OK | `none` desliga de fato; `low`/`medium`/`high` com efeito real |
| `gemini-2.5-flash-lite` | OK | OK | `none` desliga de fato; `low`/`medium`/`high` com efeito real |
| `gemini-3-flash-preview` | OK | OK | `none` desliga de fato; `low`/`medium`/`high` com efeito real |
| `gemini-3.1-pro-preview` | OK | OK | Aceita `none` sem erro, mas **não desliga de fato** (ainda gasta tokens de raciocínio); `low`/`medium`/`high` com efeito real |
| `gemini-3.1-flash-lite` | OK | OK | `none` desliga de fato; `low`/`medium`/`high` com efeito real |
| `gemini-3.5-flash` | OK | OK | `none` desliga de fato; `low`/`medium`/`high` com efeito real |
| `gemini-3.5-flash-lite` | OK | OK | `none` desliga de fato; `low`/`medium`/`high` com efeito real |
| `gemini-3.6-flash` | OK | OK | `none` desliga de fato; `low`/`medium`/`high` com efeito real |
| `gemini-3.7-flash` | OK | OK | Rejeita `none` (nível não suportado); `low` aceito mas sem efeito; `medium`/`high` com efeito real |
| `claude-opus-5` (Model Garden) | OK | OK | Aceita todos os níveis sem erro, mas nunca gasta tokens de raciocínio (sempre 0) |
| `claude-sonnet-5` (Model Garden) | OK | OK | Aceita todos os níveis sem erro, mas nunca gasta tokens de raciocínio (sempre 0) |
| `claude-sonnet-4-6` (Model Garden) | OK | OK | `none`(0)/`low`(99)/`medium`(148)/`high`(259) — único Claude do Model Garden com efeito real de reasoning |
| `claude-opus-4-8` (Model Garden) | OK | OK | Aceita todos os níveis sem erro, mas nunca gasta tokens de raciocínio (sempre 0) |
| `claude-opus-4-7` (Model Garden) | OK | OK | Aceita todos os níveis sem erro, mas nunca gasta tokens de raciocínio (sempre 0) |

`gemini-embedding-2`: 3072 dimensões, alias `embedding`.
`text-embedding-004`: 768 dimensões, alias `embedding` (alternativa mais
antiga; requer região própria, `us-central1`, diferente da usada pelos
modelos de chat).

Para transcrição de áudio, o alias `speech-to-text` pode reaproveitar o
mesmo modelo usado no alias `nano` (ex.: `gemini-2.5-flash-lite`) — o
Vertex não expõe Chirp via `/v1/audio/transcriptions` nessa integração; o
áudio é enviado como bloco multimodal (`input_audio`) para um Gemini de
chat. Ver observação em "Configuração do LiteLLM Proxy" abaixo.

> **Nota**: modelos Claude via Model Garden dependem de aprovação de
> acesso por modelo (ver "Pré-requisitos no Google Cloud") — a
> disponibilidade e o catálogo completo de versões liberadas variam por
> projeto GCP; reavalie esta lista antes de assumi-la como definitiva.

## Limitações

- **Nenhum modelo pode ser assumido como "suporta `reasoning_effort: none`"
  só por pertencer a uma família** — precisa validação individual. Na
  família Gemini: `gemini-2.5-pro` rejeita `none` de vez (thinking sempre
  ligado nesta geração); `gemini-3.7-flash` rejeita com um erro diferente
  (indício de mapeamento desatualizado para lançamentos recentes da
  3.x); `gemini-3.1-pro-preview` aceita `none` sem erro mas não desliga de
  fato o raciocínio.
- **A maioria dos modelos Claude via Model Garden não expõe
  `reasoning_effort` de verdade** — aceitam os 4 níveis sem erro, mas só
  `claude-sonnet-4-6` gasta tokens de raciocínio reais; os demais
  (`opus-5`, `sonnet-5`, `opus-4-8`, `opus-4-7`) sempre retornam 0,
  independentemente do nível pedido.
- **Transcrição de áudio não é nativa** — ver "Configuração do LiteLLM
  Proxy" abaixo; o caminho suportado é multimodal via chat, não um
  endpoint de transcrição dedicado.
- **As tags `agents:*` funcionam como controle de acesso, não só
  atribuição de custo** — com `enable_tag_filtering: true`, uma
  requisição com uma tag que o modelo não declara é rejeitada (`401`),
  não passa e loga com a tag "errada": simplesmente não roteia.
- **Modelos de parceiro (Claude) exigem aprovação manual de acesso**, que
  não é instantânea — ver "Pré-requisitos no Google Cloud" abaixo. Não
  presuma um modelo Claude disponível no Model Garden só porque aparece
  listado no catálogo do Vertex.

## Configuração

### Pré-requisitos no Google Cloud

- Um projeto GCP com a API do Vertex AI habilitada.
- Uma service account com permissão de uso do Vertex AI (`roles/aiplatform.user`
  ou equivalente), com uma chave JSON gerada para ela.
- **Dois caminhos distintos de acesso a modelo**, conforme a origem:
  - **Modelos Google (Gemini, embeddings)**: uso direto, sem gate de
    aprovação — basta a API habilitada e a service account com o papel
    correto.
  - **Modelos de parceiro como MaaS (Model as a Service)** — Claude,
    Mistral, Llama, Grok: é preciso **pedir acesso pelo Model Garden**,
    modelo por modelo, com aprovação manual (não instantânea). Sem essa
    aprovação, a chamada retorna `404` mesmo com credenciais corretas.
  - Quota (RPM/TPM) é pedida à parte de cada modelo, na página de Quotas
    do console, filtrando por `base_model` (ex.:
    `base_model:anthropic-claude-sonnet-4-5`) — um pedido padrão de
    aumento de quota GCP, independente do gate de acesso ao modelo.
- **Controle organizacional declarativo opcional**: a org policy
  `vertexai.allowedModels` permite allow/deny por modelo, separando as
  actions `predict` (chamada via API gerenciada) e `deploy` (hospedar
  você mesmo); é hierárquica (organização → pasta → projeto), com limite
  de até 500 valores combinados de allow+deny e sem wildcard por
  grupo/provider — cada modelo precisa ser especificado individualmente.
- A região (`location`) onde os modelos desejados estão disponíveis (ex.:
  `global`, `us-central1`). Modelos de embedding costumam exigir uma região
  específica, diferente da usada pelos modelos de chat.

### Credencial da service account

**Passo a passo para gerar a chave:**

**1. Fazer login no Google Cloud Console**

- Acesse [console.cloud.google.com](https://console.cloud.google.com) e
  selecione o projeto GCP correto no seletor de projetos, no topo da
  página.

**2. Habilitar o Vertex AI no projeto**

- Na barra de busca superior, digite `Vertex AI` e entre na página do
  produto (aparece como "Vertex AI — Plataforma de agentes").
- Clique no botão **Ativar**.
- Esse botão só fica disponível para quem tem permissão de habilitar APIs
  no projeto. Se estiver desabilitado ou ausente, peça para alguém com
  essa permissão fazer a ativação antes de continuar — os passos
  seguintes dependem disso.
- Se algum modelo desejado for de parceiro (MaaS — ex.: Claude), acesse o
  **Model Garden**, localize o modelo e solicite acesso ali mesmo. A
  aprovação é manual, não instantânea — planeje esse passo com
  antecedência antes de liberar o alias correspondente no
  `litellm_config.yaml`.

**3. Criar a service account**

- No menu lateral, acesse **IAM e administrador → Contas de serviço**.
- Clique em **Criar conta de serviço**.
- Informe um nome e um ID — podem ser escolhidos livremente, não há um
  padrão obrigatório.
- Clique em **Criar e continuar**.

**4. Atribuir a permissão à service account**

- Na etapa "Conceder a esta conta de serviço acesso ao projeto", selecione
  o papel **Agentes de Serviço da Vertex AI** (`roles/aiplatform.user` ou
  equivalente, conforme o uso pretendido).
- Clique em **Continuar** e depois em **Concluir**.

  > **Importante — motivo de segurança**: use uma service account em vez
  > de conceder a permissão diretamente via IAM a um usuário. A credencial
  > fica isolada, pode ser revogada/rotacionada independentemente de
  > contas de usuário, e não expõe acesso pessoal de quem está
  > configurando.

**5. Gerar a chave no formato JSON**

- De volta à lista de contas de serviço, clique na conta recém-criada
  para abri-la.
- Vá até a aba **Chaves**.
- Clique em **Adicionar chave → Criar nova chave**.
- Selecione o formato **JSON** e confirme.
- O arquivo é baixado automaticamente para a máquina — essa é a
  credencial usada em `vertex_credentials` (ver "Como usar" mais abaixo).

O download gera um arquivo com esta estrutura:

```json
{
  "type": "service_account",
  "project_id": "<seu-projeto-gcp>",
  "private_key_id": "<id-da-chave>",
  "private_key": "-----BEGIN PRIVATE KEY-----\n<conteudo-da-chave>\n-----END PRIVATE KEY-----\n",
  "client_email": "<nome-da-service-account>@<seu-projeto-gcp>.iam.gserviceaccount.com",
  "client_id": "<client-id-numerico>",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "<url-do-certificado-da-service-account>",
  "universe_domain": "googleapis.com"
}
```

Todos os campos são gerados pelo Google — não é algo que se escreve à mão.
O único campo obrigatório para identificar de qual conta se trata, se
precisar conferir manualmente, é `client_email`; `project_id` deve bater
com o `vertex_project` configurado em cada entrada do modelo.

**Como usar:**

- Salve o arquivo fora do controle de versão (adicione o caminho ao
  `.gitignore`) — é uma credencial sensível, equivalente a uma senha.
- Restrinja as permissões do arquivo (leitura apenas pelo usuário/processo
  que roda o proxy — ex. `chmod 600`).
- Monte o arquivo dentro do container do LiteLLM Proxy (ex. via volume do
  Docker Compose) e referencie o caminho **montado dentro do container**
  (não o caminho no host) em `vertex_credentials`.

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

**O contrato gerado por CI/CD (`os.environ/LITELLM_*_API_BASE`/`API_KEY`/
`API_VERSION`) não serve para o Vertex** — ele foi pensado para conexões
estilo OpenAI/Azure (uma API key simples). O Vertex autentica com
service account (arquivo JSON) + `vertex_project` + `vertex_location`,
campos que não existem em `security_example.env` nem no gerador de CI/CD
desta branch. Usar o Vertex em algum dos 5 aliases exige editar
manualmente a entrada correspondente no `litellm_config.yaml` **já
gerado** (ou a cópia local do template, se não passar pelo pipeline
interno), trocando `api_base`/`api_key`/`api_version` por
`vertex_project`/`vertex_location`/`vertex_credentials`. O `model_name`
do alias não muda — só o conteúdo de `litellm_params`.

**Exemplo — alias `mini` adaptado para o Vertex** (mesmo padrão para
`standard`/`nano`/`embedding`/`speech-to-text`):

```yaml
model_list:
  # ... standard, tal como gerado ...

  - model_name: mini
    litellm_params:
      model: vertex_ai/<seu-modelo>        # ver "Modelos Homologados" acima
      vertex_project: "<seu-projeto-gcp>"
      vertex_location: "global"            # ex.: global, us-central1
      vertex_credentials: "<caminho-para-credencial.json>"
      tags: ["agents:classificador", "agents:busca_web"]
    model_info:
      base_model: vertex_ai/<seu-modelo>

  # ... nano, embedding, speech-to-text no mesmo padrão ...

router_settings:
  enable_tag_filtering: true
```

Substitua `<seu-modelo>` por um ID real da tabela em "Modelos
Homologados" acima (ex.: `gemini-2.5-flash`) — evite fixar um nome de
modelo específico como referência de longo prazo aqui: a família Gemini
lança novas gerações com frequência, e o ID exato muda mais rápido do
que este documento é atualizado. O caminho da credencial e o projeto/
região não têm variável de ambiente reservada nesta integração — como o
Vertex sai do fluxo padrão gerado, trate esses valores com o mesmo
cuidado de segurança dado a uma credencial: fora do controle de versão,
permissões restritas no arquivo montado no container.

> **Papel `audio_transcription` não tem um caminho pronto no template
> padrão** — ver "Atenção — transcrição de áudio" logo abaixo: não há
> endpoint de transcrição dedicado no Vertex nessa integração. Se optar
> por usar o caminho multimodal (áudio como bloco `input_audio` para um
> Gemini de chat), adapte o alias `speech-to-text` do mesmo jeito, com
> `model` apontando para um Gemini de chat (ex.: o mesmo do alias `nano`).

Para liberar um modelo Claude via Model Garden (após a aprovação de
acesso) sem mexer nos 5 aliases fixos, use o catálogo opcional
`LITELLM_MODEL_CATALOG` (variável de CI/CD tipo File, JSON
`[{"model": "...", "roles": [...]}]`) — ver `docs/INSTALL.md`. O gerador
rejeita qualquer item que tente redefinir um dos 5 nomes reservados; como
o catálogo também segue o contrato `api_base`/`api_key`/`api_version`, um
modelo extra do Vertex precisa da mesma adaptação manual descrita acima.

> **Atenção — transcrição de áudio**: modelos de transcrição nativos do
> Vertex (Chirp) não funcionam via endpoint `/v1/audio/transcriptions`
> nessa integração. O caminho suportado é enviar o áudio como bloco
> multimodal (`type: input_audio`) para `/v1/chat/completions`, apontando
> para um modelo Gemini de chat — não para um modelo de transcrição
> dedicado.

> **Atenção — erro `invalid_grant` na autenticação**: costuma ser causado
> por *clock skew* entre o host e o Google (a assinatura do JWT da service
> account é sensível a diferenças de poucos minutos no relógio). Se a
> credencial estiver correta e o erro persistir, verifique a sincronização
> de horário do host antes de investigar a credencial em si.

## Factory de Modelos

O arquivo `sei_ia/services/llm_models/get_model.py` é o ponto central para
obtenção de modelos — o código não muda entre providers, pois a aplicação
sempre fala com o LiteLLM Proxy, nunca diretamente com o Vertex AI. A
função recebe o **papel do agente**; internamente resolve o tier
(`standard`/`mini`/`nano`) e monta a tag `agents:<agent_tag>` mandada ao
proxy:

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

# Reasoning usa o modelo base com Responses API configurada pelo fluxo de chat.

# Com LangChain chains
chain = prompt | get_model("principal")
```

## Embeddings

Embeddings também são gerados via LiteLLM Proxy:

- Modelo: `text-embedding-004`
- Dimensões: 768
- Máximo de tokens: consulte a documentação do modelo no Vertex AI

**Arquivo**: `sei_ia/services/embedder/embedding_generator.py`

> **Alternativa validada**: `gemini-embedding-2` (3072 dimensões) também
> está homologado (ver "Modelos Homologados" acima). Trocar de um para o
> outro é uma troca de provider de embedding — vale o mesmo cuidado de
> dimensão do aviso abaixo.

> **Atenção**: a dimensão do vetor de embedding (768) é diferente da usada
> por modelos Azure/OpenAI comuns como `text-embedding-3-small` (1536).
> Trocar de provider de embedding exige garantir que a coluna do banco
> (`vector(N)`) e o valor de dimensão configurado na aplicação estejam
> alinhados com o modelo em uso — e, se houver embeddings já persistidos
> com a dimensão antiga, eles precisam ser reprocessados, não apenas
> reconfigurados.
>
> No `etl-airflow`, o provider de embedding resolve o tokenizador
> (usado para dividir documentos em chunks) tentando primeiro reconhecer o
> nome do modelo configurado via `tiktoken` e, se falhar, consultando um
> header de resposta específico do Azure OpenAI. Como esse header não
> existe ao usar o Vertex AI, o nome do modelo configurado para essa
> finalidade **precisa** ser um nome que o `tiktoken` reconheça diretamente
> (por exemplo, um nome de modelo OpenAI real usado apenas como
> aproximação para estimativa de tamanho de chunk) — caso contrário a
> divisão em chunks falha para todo documento processado.

## Tratamento de Erros

O sistema trata erros de conexão com o proxy/Vertex AI:

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

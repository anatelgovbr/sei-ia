# AWS Bedrock

> Como configurar o SEI-IA Assistente para usar, via AWS Bedrock, os
> modelos já homologados no projeto.

> Fonte de verdade do formato do `litellm_config.yaml`:
> `litellm_config.template.yaml` na raiz do monorepo e
> `docs/INSTALL.md` (seção "Configuração dos modelos LLM e LiteLLM").

## Arquitetura

O SEI-IA Assistente utiliza **LiteLLM Proxy** para comunicação com o AWS
Bedrock. Isso permite:

- Centralizar credenciais e configurações no proxy
- Facilitar troca de modelos sem alterar código

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Assistente    │ ──── │  LiteLLM Proxy  │ ──── │   AWS Bedrock   │
│   (ChatOpenAI)  │      │  localhost:4000 │      │                 │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

A autenticação no Bedrock é feita com as credenciais de um **usuário IAM
comum** (Access Key ID + Secret Access Key), ao qual se anexa uma
política liberando o uso do serviço — o mesmo tipo de usuário que
qualquer pessoa usaria para acessar o console da AWS.

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
| `audio_transcription` | Transcrição de áudio (Whisper). |

No `litellm_config.yaml` cada papel é atendido por um dos **5 aliases
fixos** — `standard`, `mini`, `nano`, `embedding`, `speech-to-text`. São
nomes **reservados**: o gerador de config em CI/CD rejeita qualquer
entrada de `LITELLM_MODEL_CATALOG` que tente redefinir um deles. Não são
detalhe de implementação — é o que você de fato escreve em `model_name`:

| Alias (`model_name`) | Papéis que atende | Variável do modelo físico |
|---|---|---|
| `standard` | `principal` | `LITELLM_STANDARD_MODEL` |
| `mini` | `classificador`, `busca_web` | `LITELLM_MINI_MODEL` |
| `nano` | `explorador`, `ocr`, `triagem_busca` | `LITELLM_NANO_MODEL` |
| `embedding` | `embedding` | `LITELLM_EMBEDDING_MODEL` |
| `speech-to-text` | `audio_transcription` | `LITELLM_STT_MODEL` |

Cada alias tem sua própria credencial AWS (Access Key ID + Secret Access
Key + região — não o par `api_base`/`api_key` que o gerador de CI/CD
normalmente preenche via `LITELLM_*_API_*`; ver "Configuração do LiteLLM
Proxy" abaixo para o porquê isso importa) — `standard`, `mini` e `nano`
podem usar contas AWS, regiões ou até providers diferentes entre si, sem
depender uns dos outros.

> **`nano` e `embedding` são um contrato entre apps, não só do
> Assistente**: `libs/sei_extraction` (compartilhada por Assistente,
> Similaridade e ETL) usa `"nano"` como default de `ocr_model`, e o
> `etl-airflow` replica `"embedding"` como alias padrão de roteamento
> (`jobs/envs.py`). Trocar o que esses dois aliases apontam no
> `litellm_config.yaml` muda o modelo de OCR/embedding usado pelas outras
> aplicações também, não só pelo Assistente.

> **Importante**: um modelo físico adicional pode ser liberado para mais
> de um papel ao mesmo tempo sem mexer nos 5 aliases fixos — use o
> catálogo opcional (`LITELLM_MODEL_CATALOG`, ver "Configuração do
> LiteLLM Proxy" abaixo).

> **Atenção — não existe `speech-to-text` no Bedrock**: não há um
> equivalente ao Whisper, e nenhum modelo de chat aceita áudio como
> content block via API Converse — o schema do `ContentBlock` até declara
> o tipo `audio`, mas nenhum modelo o implementa, e a página oficial de
> "modelos e features suportadas" da AWS não lista áudio para nenhum
> modelo de chat. O único caminho nativo de áudio no Bedrock é o
> `amazon.nova-sonic-v1:0`, que exige uma API de streaming bidirecional
> (`InvokeModelWithBidirectionalStream`) incompatível com o padrão de
> requisição/resposta usado por essa integração. **Não configure o alias
> `speech-to-text` apontando para o Bedrock** — não há modelo homologado
> para essa função neste provider.

## Modelos Homologados

Modelos validados no Bedrock por família, com o resultado por cenário
(classificador, explorador, OCR/visão) e o comportamento real de
`reasoning_effort` (aceita/ignora o parâmetro, e se o nível realmente muda
o custo de raciocínio):

| Família | Modelos | Classificador / Explorador | OCR (visão) | `reasoning_effort` |
|---|---|---|---|---|
| Anthropic Claude | sonnet-4-5, haiku-4-5, sonnet-4-6, opus-4-5, opus-4-7, opus-4-8, sonnet-5, opus-5 | OK em todos | OK em todos (visão nativa) | Requer o formulário FTU antes de qualquer chamada (ver "Pré-requisitos"). Varia por versão: `sonnet-4-5`/`haiku-4-5`/`sonnet-4-6`/`opus-4-5` gastam tokens reais de raciocínio em `low`/`medium`/`high`; `opus-5`/`sonnet-5`/`opus-4-7`/`opus-4-8` aceitam o parâmetro sem erro mas nunca gastam tokens de raciocínio |
| DeepSeek | r1 | OK | Sem visão | Sempre ligado — não desliga com `none`; só aceita `none`, `low`/`medium`/`high` retornam erro 400 |
| Qwen | qwen3-32b | OK | Sem visão | Parâmetro aceito, sem efeito (o raciocínio nativo do modelo não é exposto por essa chave nesta integração) |
| OpenAI (open-weight) | gpt-oss-120b, gpt-oss-20b | OK | Sem visão | Não desliga com `none`; `low`/`medium`/`high` funcionam |
| OpenAI (gpt-5.x) | gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna | OK | OK | `none`/`low`/`medium`/`high` funcionam, todos com efeito real |

> **Nota**: esta tabela cobre os modelos de maior adoção no mercado
> (Anthropic, OpenAI, Qwen, DeepSeek) entre os que passaram pela
> validação — o catálogo do Bedrock tem outras famílias (Amazon Nova,
> Meta Llama, Mistral, Writer) também testadas, mas fora do escopo deste
> resumo.

`bedrock/amazon.titan-embed-text-v2:0`: 1024 dimensões, alias `embedding`.

> **Nota**: a disponibilidade de modelos depende da conta e da região
> usadas — reavalie esta lista antes de assumi-la como definitiva para uma
> conta/região diferente da usada na validação.

## Limitações

- **Nenhum modelo de chat do Bedrock suporta áudio/transcrição** — ver
  observação em "Papéis e os 5 aliases fixos" acima.
- **Anthropic Claude exige o formulário "First Time Use" (FTU)** uma vez
  por conta/organização antes de qualquer chamada, além do acesso IAM (ver
  "Pré-requisitos"). Sem o formulário preenchido, a chamada falha mesmo
  com credenciais e permissões corretas.
- **Comportamento de `reasoning_effort` não é uniforme, nem dentro da
  mesma família de modelo** (ver coluna da tabela acima) — não assumir o
  comportamento de um modelo a partir de outro da mesma família sem
  validar individualmente, principalmente antes de liberar um novo modelo
  no alias `standard`.
- **O gate de assinatura no AWS Marketplace (ver "Pré-requisitos") é por
  modelo, não por família** — membros de uma mesma família podem ter
  status de acesso diferente entre si; não presuma que todo modelo de uma
  família está liberado só porque outro da mesma família funcionou.

## Configuração

### Pré-requisitos na AWS

- Uma conta AWS com acesso ao serviço Bedrock na região desejada (ex.:
  `us-east-1`).
- **Acesso a modelos serverless é habilitado por padrão** em todas as
  regiões comerciais, para a maioria dos provedores (Amazon, Meta,
  Mistral, DeepSeek, Qwen, OpenAI open-weight) — não é mais necessário
  clicar em "Request model access" no console para esses.
- **Exceção: modelos Anthropic (Claude) continuam exigindo o formulário
  "First Time Use" (FTU)**, uma vez por conta/organização, preenchido no
  console (**Bedrock → Model access → Modify model access**, ao marcar um
  modelo Anthropic) ou via API (`PutUseCaseForModelAccess`). Sem esse
  formulário, a chamada falha mesmo com credenciais e permissões IAM
  corretas — mesmo modelos Anthropic já habilitados por padrão em outras
  contas exigem o FTU nesta.
- **Gate independente: modelos com product ID no AWS Marketplace** (parte
  do catálogo Writer e algumas variantes OpenAI gpt-5.x) exigem assinatura
  ativa na conta. Na primeira invocação o Bedrock tenta assinar
  automaticamente em segundo plano (até 15 min); exige IAM
  `aws-marketplace:Subscribe`/`Unsubscribe`/`ViewSubscriptions` e forma de
  pagamento válida na conta. Sem isso, a chamada falha com erro pedindo a
  assinatura.
- O acesso a modelo é liberado **por região** — repita os passos acima em
  cada região onde os modelos forem usados.
- Um usuário IAM com uma política anexada autorizando o uso do Bedrock
  (ver abaixo).

### Credencial (usuário IAM)

**Passo a passo para gerar a chave:**

**1. Fazer login no Console da AWS**

- Acesse [console.aws.amazon.com](https://console.aws.amazon.com) com uma
  conta que tenha permissão para gerenciar usuários IAM.

**2. Conferir/solicitar acesso aos modelos no Bedrock**

- Na barra de busca superior, digite `Bedrock` e entre no serviço.
- No menu lateral, acesse **Model access** e confirme que os modelos
  desejados estão com status `Access granted` — para a maioria já vem
  assim por padrão (ver "Pré-requisitos" acima). Para Anthropic, preencha
  o formulário de uso ali mesmo, ao marcar o modelo.

**3. Criar o usuário IAM**

- No menu lateral do console, acesse **IAM → Usuários**.
- Clique em **Criar usuário** (ou **Adicionar usuários**).
- Informe um nome — pode ser escolhido livremente, não há um padrão
  obrigatório.
- Não é necessário habilitar acesso ao console (login via senha); esse
  usuário só precisa de acesso programático.

**4. Atribuir a permissão ao usuário**

- Na etapa de permissões, anexe uma política que autorize o uso do
  Bedrock (ex.: `AmazonBedrockFullAccess` para testes, ou uma política
  customizada restrita às ações `bedrock:InvokeModel` e
  `bedrock:InvokeModelWithResponseStream` sobre os ARNs dos modelos
  específicos que serão usados).

  > **Importante — motivo de segurança**: prefira uma política
  > customizada com o menor escopo possível (apenas os modelos
  > realmente usados) em vez de uma política de acesso total ao
  > Bedrock. Isso limita o impacto caso a credencial vaze, e evita que
  > o usuário tenha acesso a modelos ou operações não previstos pela
  > integração.

- Conclua a criação do usuário.

**5. Gerar a chave de acesso (Access Key)**

- Na lista de usuários, clique no usuário recém-criado para abri-lo.
- Vá até a aba **Credenciais de segurança**.
- Em **Chaves de acesso**, clique em **Criar chave de acesso**.
- Selecione o caso de uso (ex.: "Aplicativo em execução fora da AWS") e
  confirme.
- A AWS gera um **Access Key ID** e uma **Secret Access Key**. A Secret
  Access Key só é exibida **uma única vez** nesse momento — baixe o
  arquivo `.csv` ou copie os dois valores imediatamente, pois não é
  possível recuperá-la depois (só é possível gerar uma nova).

**Como usar:**

- Trate o par Access Key ID / Secret Access Key como uma credencial
  sensível, equivalente a uma senha — nunca commite esses valores em
  controle de versão.
- Repita esse processo para cada alias que apontar para o Bedrock com uma
  conta/usuário IAM diferente (ex.: `standard` numa conta, `mini`/`nano`
  em outra) — cada alias tem sua própria credencial no `security.env`.

### Variáveis de Ambiente

```bash
# URL do proxy LiteLLM
LITELLM_PROXY_URL=http://localhost:4000

# API key do proxy (opcional, depende da configuração do proxy)
# LITELLM_PROXY_API_KEY=sua_api_key

# Limites de contexto e output — os modelos homologados (Qwen3-32b,
# DeepSeek R1) têm janela de contexto total (entrada + saída) de 32768
# tokens; ver "Atenção" abaixo.
ASSISTENTE_OUTPUT_TOKENS_STANDARD_MODEL=4096
ASSISTENTE_CTX_LEN_STANDARD_MODEL=32768
```

> **Atenção — limites de contexto/output**: se essas variáveis forem
> herdadas de uma configuração feita para outro provider (com janela de
> contexto maior), as requisições falham com erro do tipo *"This model's
> maximum context length is 32768 tokens. However, you requested N
> output tokens..."* — ajuste `ASSISTENTE_OUTPUT_TOKENS_*` e
> `ASSISTENTE_CTX_LEN_*` conforme os valores acima antes de usar os
> modelos homologados no Bedrock.

### Configuração do LiteLLM Proxy

**O contrato gerado por CI/CD (`os.environ/LITELLM_*_API_BASE`/`API_KEY`/
`API_VERSION`) não serve para o Bedrock** — ele foi pensado para conexões
estilo OpenAI/Azure (uma API key simples). O Bedrock autentica com
**Access Key ID + Secret Access Key + região** (`aws_access_key_id`,
`aws_secret_access_key`, `aws_region_name`), campos que não existem em
`security_example.env` nem no gerador de CI/CD desta branch. Usar o
Bedrock em algum dos 5 aliases exige editar manualmente a entrada
correspondente no `litellm_config.yaml` **já gerado** (ou a cópia local
do template, se não passar pelo pipeline interno), trocando
`api_base`/`api_key`/`api_version` por `aws_access_key_id`/
`aws_secret_access_key`/`aws_region_name`. O `model_name` do alias não
muda — só o conteúdo de `litellm_params`.

**Exemplo — alias `mini` adaptado para o Bedrock** (mesmo padrão para
`standard`/`nano`/`embedding`; não configure `speech-to-text` — ver
"Papéis" acima):

```yaml
model_list:
  # ... standard, tal como gerado ...

  - model_name: mini
    litellm_params:
      model: bedrock/<seu-modelo>          # ver "Modelos Homologados" acima
      aws_access_key_id: "<sua-access-key-id>"
      aws_secret_access_key: "<sua-secret-access-key>"
      aws_region_name: "us-east-1"
      max_completion_tokens: 4096
      tags: ["agents:classificador", "agents:busca_web"]
    model_info:
      base_model: bedrock/<seu-modelo>

  # ... nano, embedding no mesmo padrão ...

router_settings:
  enable_tag_filtering: true
```

Substitua `<seu-modelo>` por um ID real da tabela em "Modelos
Homologados" acima (ex.: `qwen.qwen3-32b-v1:0`) — evite fixar um nome de
modelo específico como referência de longo prazo aqui: o catálogo do
Bedrock muda com frequência (novas versões, modelos descontinuados), e o
ID exato muda mais rápido do que este documento é atualizado. As
credenciais AWS não têm variável de ambiente reservada nesta integração
— como o Bedrock sai do fluxo padrão gerado, trate esses valores com o
mesmo cuidado de segurança dado a uma credencial: fora do controle de
versão, permissões restritas.

Cada alias pode usar um usuário/conta IAM diferente — não precisam
compartilhar a mesma credencial AWS.

> **Atenção — credenciais literais no config, se o container não tiver
> variáveis de ambiente**: se o serviço do LiteLLM Proxy no
> `docker-compose.yml` não tiver um bloco `environment:` com
> `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (ou os nomes que você usar),
> qualquer referência a essas variáveis no `litellm_config.yaml` não
> resolve sem recriar o container. Nesse caso, ou se adiciona o bloco
> `environment:` ao serviço (recomendado, para não expor a credencial em
> texto plano no arquivo de config), ou as credenciais são embutidas
> literalmente no `litellm_config.yaml` — nesse último caso, trate o
> arquivo com o mesmo cuidado de segurança de uma credencial (fora do
> controle de versão, permissões restritas).

> **Atenção — o modelo DeepSeek R1 exige inference profile**: o ID correto
> é `bedrock/us.deepseek.r1-v1:0` — sem o prefixo `us.`, a chamada falha
> com `ValidationException: ...on-demand throughput isn't supported...`,
> pedindo o ID de uma inference profile.

> **Atenção — `max_completion_tokens` pode ser aplicado mesmo com um
> `max_tokens` menor na requisição**: se o `litellm_config.yaml` define
> `max_completion_tokens` em um valor que excede a janela real do modelo,
> a chamada falha mesmo que a aplicação peça explicitamente um
> `max_tokens` menor — o valor do config prevalece. Ajuste
> `max_completion_tokens` no proxy à janela real do modelo, não apenas o
> `max_tokens` do lado da aplicação.

Para liberar um modelo extra sem mexer nos 5 aliases fixos (ex.: um
Claude, depois do formulário FTU, disponível como opção adicional no
alias `standard`), use o catálogo opcional `LITELLM_MODEL_CATALOG`
(variável de CI/CD tipo File, JSON `[{"model": "...", "roles": [...]}]`)
— ver `docs/INSTALL.md`. O gerador rejeita qualquer item que tente
redefinir um dos 5 nomes reservados; como o catálogo também segue o
contrato `api_base`/`api_key`/`api_version`, um modelo extra do Bedrock
precisa da mesma adaptação manual (`aws_access_key_id`/
`aws_secret_access_key`/`aws_region_name`) descrita acima.

## Embeddings

Embeddings também são gerados via LiteLLM Proxy:

- Modelo: `amazon.titan-embed-text-v2:0`
- Dimensões: 1024
- Máximo de tokens: consulte a documentação do modelo no Bedrock

**Arquivo**: `sei_ia/services/embedder/embedding_generator.py`

> **Atenção**: se a aplicação já tiver sido usada com outro provider de
> embedding, a dimensão do vetor (1024) pode ser diferente da configurada
> anteriormente. Trocar de provider de embedding exige garantir que a
> coluna do banco (`vector(N)`) e o valor de dimensão configurado na
> aplicação estejam alinhados com o modelo em uso — e, se houver
> embeddings já persistidos com a dimensão antiga, eles precisam ser
> reprocessados, não apenas reconfigurados.

## Tratamento de Erros

O sistema trata erros de conexão com o proxy/Bedrock:

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

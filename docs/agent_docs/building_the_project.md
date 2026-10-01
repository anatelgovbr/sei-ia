# Building the project

Como buildar o SEI-IA. Há **dois modos**, e confundi-los é a maior fonte de erro:

1. **Dev — uma app por vez.** `.venv` própria dentro de `aplicacoes/<app>`, build e execução locais via `uv`. É o loop de desenvolvimento.
2. **Stack inteira — deploy.** Todas as imagens Docker sobem juntas via `make up`. Não é loop de dev; é o que roda em ambiente.

> App canônica nos exemplos: `assistente`. `similaridade` e `etl-airflow` seguem o mesmo padrão, salvo divergências apontadas.

## Fronteira entre desenvolvimento e CD

O código é alterado e validado apenas na **worktree da tarefa**. O checkout persistente de deploy no servidor não é ambiente de desenvolvimento: não edite arquivos, não execute comandos Git, testes, `docker compose` ou `make up` nele.

Nos ambientes gerenciados, build e deploy são responsabilidade exclusiva do **GitLab CI/CD**. O build ocorre no checkout limpo do job, antes dos testes; depois que a mudança chega à branch do ambiente, o deploy atualiza o checkout persistente, gera as configurações e ativa a candidata já construída, sem rebuild. O mecanismo está em [git_workflow.md](git_workflow.md), `.gitlab/ci/build-candidates.yml` e `.gitlab/scripts/deploy_changed.sh`.

## Pré-requisitos

- **Dev local:** `uv` + Python 3.12 (pin `>=3.12,<3.13` em `aplicacoes/assistente/pyproject.toml:12`). Sempre `.venv`/`uv`, nunca o Python do sistema.
- **Stack:** Docker Engine ≥ 27.1.1, Compose ≥ 2.29, Buildx ≥ 0.13 — requisitos operacionais completos em `docs/INSTALL.md`.

## Dev — buildar uma app

Trabalhe **de dentro** de `aplicacoes/<app>`, cada uma com sua própria `.venv`:

- `make install` — cria a `.venv` (`uv sync`) e instala os hooks de pre-commit — `aplicacoes/assistente/Makefile:1-5`.
- `make run-uvicorn` — sobe a app local (porta 8199 no `assistente`) — `aplicacoes/assistente/Makefile:48-51`.

As libs compartilhadas entram como **editáveis** apontando para `../../libs/*` — `aplicacoes/assistente/pyproject.toml:258-262`. É por isso que o build roda de dentro do diretório da app: é lá que o path relativo resolve.

## Stack — buildar imagens Docker

Cada app vira imagem `sei-ia/<app>:local`. Os builds usam **`context: .` (raiz do repo)**, não o diretório da app — ex. `docker-compose.yml:68-71` (`assistente`). Cada imagem compartilhada tem um único serviço representante com `build`: `similaridade` constrói a imagem usada também por `similaridade-feedback`, e `etl-airflow-webserver` constrói a imagem usada por todo o plano Airflow. Isso evita builds concorrentes duplicados para a mesma tag.

Gotcha: o Dockerfile do Assistente espelha a árvore do repo nos metadados (`/app/aplicacoes/assistente` + `/app/libs`) para o lock resolver os paths `../../libs/*`; o código local depois é exposto pelo `PYTHONPATH`, sem pacote editável. Num `/app` plano o `../../` escapa a raiz e o `uv` recusa normalizar — explicado em `aplicacoes/assistente/assistente.dockerfile:28-30`.

## Stack — subir tudo

Do raiz do repo:

- `make config` — exige os dois arquivos privados, garante `SEARXNG_SECRET_KEY` em `security.env` via helper dedicado e valida a renderização do Compose sem imprimir segredos.
- `make up` — executa `config`, garante certificado e volumes, constrói as imagens distintas com `docker compose --parallel 3 build` (configurável por `BUILD_PARALLELISM`) e sobe com `--no-build --remove-orphans`.
- `make down` — derruba a stack sem remover os bind mounts persistentes.
- `make check` — valida a stack já iniciada em um contêiner efêmero; não para os demais serviços.

As regras ficam em `Makefile:1-66`. `BUILD_PARALLELISM` usa três por padrão e pode ser reduzido em hosts com menos memória. `ensure-volumes` usa `sudo mkdir`/`sudo chown` para subdiretórios com UIDs próprios de Airflow, Postgres e Solr; a raiz configurada em `VOL_SEIIA_DIR` deve existir antes. A release externa é **somente código-fonte**: não há modo alternativo por imagens próprias pré-publicadas.

## Configuração de ambiente: `.env` (dev) vs. arquivos de deploy

O carregamento de config **difere** entre dev e deploy — não confundir.

### Dev — `.env` local por app

Cada app lê um `.env` **do próprio diretório** (`aplicacoes/<app>/.env`), porque é de lá que se roda em dev:

- O mesmo `.env` é carregado por **dois mecanismos**: o pydantic `BaseSettings` lê o arquivo direto e preenche o objeto `Settings` tipado (`env_file=".env"`, `aplicacoes/assistente/sei_ia/configs/settings_config.py:20-22`) — caminho principal, consumido via `settings.<CAMPO>`; e `load_dotenv()` (`sei_ia/main.py:42`) exporta as mesmas vars para `os.environ`, cobrindo libs de terceiros que leem o ambiente do processo direto. Preencher o `.env` alimenta os dois; nos containers o compose injeta env vars reais e o `load_dotenv()` é no-op.
- O dev cria o `.env` copiando o template versionado `aplicacoes/<app>/.env.example` (`assistente` e `similaridade`; o `etl-airflow` não tem — usa config nativa do Airflow) e preenchendo os valores. O `.env` é **gitignored** (`.gitignore:19`) — cada dev tem o seu.

### Deploy — `default.env` + `security.env`

A stack **não** usa o `.env` por app. Todos os alvos principais fixam `docker-compose.yml`, carregam `default.env` + `security.env` e ativam o profile oficial `web-search` (`Makefile:5`). Os serviços recebem essas configurações por `env_file` e por mapeamentos explícitos no Compose.

O Compose preserva os fallbacks históricos das senhas de PostgreSQL, RabbitMQ,
Airflow e Solr para manter compatibilidade com instalações existentes. O fluxo
documentado continua registrando os nomes em `security.env`, e upgrades devem copiar
os valores já usados pelos volumes em vez de rotacioná-los implicitamente. O Solr
reutiliza `SOLR_PASSWORD` para autenticação e para proteger seu keystore TLS efêmero
(`ops/solr/entrypoint.sh:4-48`).

- **`default.env`** — **versionado**. Defaults não secretos, incluindo usuário/UID/GID, pasta de volumes, TZ, rede e limites do ambiente de referência.
- **`security.env`** — **gerado no deploy interno** por `generate_security_env` em `.gitlab/scripts/generate_config_files.sh`; contém credenciais, endpoints e parâmetros específicos do ambiente, inclusive `LOG_LEVEL` e `ASSISTENTE_USE_LANGFUSE`. É gitignored; o contrato versionado é `security_example.env`. Na instalação externa, o operador copia esse template e mantém exatamente os mesmos nomes (`SEARXNG_SECRET_KEY` é gerada e persistida automaticamente por `make config`/`make up` ou na migração quando vazia; `LITELLM_PROXY_API_KEY` é resolvida ou gerada automaticamente na migração). O checker reprova variável ausente, extra, duplicada, inválida ou obrigatória vazia.

O gerador valida `ASSISTENTE_USE_LANGFUSE` como `true|false` e `LOG_LEVEL` como
`DEBUG|INFO|WARNING|ERROR` antes de substituir `security.env`. O deploy compara os
digests de `security.env` e `litellm_config.yaml` antes e depois da geração. Mudança
de conteúdo força `docker compose up --force-recreate` mesmo quando o SHA não mudou;
o log informa somente os nomes dos arquivos alterados (`.gitlab/scripts/generate_config_files.sh:37`;
`.gitlab/scripts/deploy_changed.sh:1449`).

### `litellm_config.yaml` — config do proxy LiteLLM

- **Copiado sem expor credenciais** de `litellm_config.template.yaml` no deploy interno e na instalação externa. O YAML é gitignored e mantém modelos, endpoints e chaves como `os.environ/VAR`; `model_name` permanece um alias fixo (`standard`, `mini`, `nano`, `embedding`, `speech-to-text`). Quando o catálogo opcional estiver configurado (ver `git_workflow.md`), o gerador preenche os marcadores com entradas extras e níveis de reasoning dos aliases de texto que apontam para o mesmo modelo físico; as credenciais dessas entradas continuam sendo referências ao ambiente (`litellm_config.template.yaml:1`; `.gitlab/scripts/generate_config_files.sh:138`).
- **Função:** configura o proxy LiteLLM com cinco aliases fixos, separados dos modelos físicos informados por `LITELLM_{STANDARD,MINI,NANO,EMBEDDING,STT}_MODEL`. Cada entrada declara `tags: ["agents:<papel>"]`, e `router_settings.enable_tag_filtering` restringe cada chamada ao papel enviado pelo Assistente. Não existe mais `think`/`think-low`/`think-none`: `reasoning_effort` é parâmetro de request (`litellm_config.template.yaml:2`; `services/llm_models/get_model.py:32`).
- Os modelos de texto não fixam `max_completion_tokens`, e `get_model` não envia
  `max_tokens`: o limite efetivo da resposta fica a cargo do provider. O
  `session_stream` também não mantém reserva própria de saída; o Deep Agents usa o
  profile de contexto para offload, compactação e recuperação de overflow. As
  variáveis históricas `ASSISTENTE_OUTPUT_TOKENS_*` permanecem no settings,
  mas não configuram a saída do Session.
- O catálogo opcional, configurado conforme `git_workflow.md`, não faz parte de `security.env`: seu JSON contém `model`, `roles` e `reasoning_effort_levels`. As entradas extras preservam nomes físicos para overrides e podem atender mais de um papel. O gerador rejeita catálogo inválido ou redeclaração de alias reservado. O override de `ChatRequest.model` e o `reasoning_effort` são validados contra `GET /model/info`; falha de catálogo ou valor incompatível não passa silenciosamente (`.gitlab/scripts/generate_config_files.sh:138`; `services/llm_models/model_catalog.py:75-189`).
- **Fronteiras de autenticação:** `LITELLM_PROXY_API_KEY` autentica Assistente,
  ETL e checker perante o proxy local. Cada entrada usa sua própria credencial de
  provedor: `LITELLM_{STANDARD,MINI,NANO,EMBEDDING,STT}_API_KEY`, acompanhada do
  `API_BASE` e `API_VERSION` do mesmo tier. Não existe herança implícita da
  credencial Standard para Mini ou Nano.
- **Failover de reasoning:** antes do primeiro conteúdo, falhas recuperáveis do provider podem disparar uma tentativa com `reasoning_effort="none"`. O Session registra a transição e reinicializa a janela antes de reprocessar; os detalhes ficam em `routers/session/stream.py`. A remoção dos endpoints clássicos não altera esse comportamento.
- A janela do `session_stream` vem do profile local selecionado por `ASSISTENTE_SESSION_MAIN_MODEL`: `get_model_config` resolve o `max_ctx_len` a partir de `ASSISTENTE_CTX_LEN_{STANDARD,MINI,NANO}_MODEL` (`settings_config.py:203-223,242-248`; `services/llm_models/get_model.py:58-102`). O agente passa esse valor ao profile do Deep Agents e não consulta `/model/info` para descobrir a janela (`agents/session_agent/agent.py:237-243,348-357`). Ao trocar o modelo de um tier, mantenha o limite local alinhado à janela efetiva; a diferença entre filesystem e injected está em `service_communication_patterns.md`.

## Como o CI/CD builda (e por que difere)

O CD cria uma **imagem candidata final por componente afetado**, antes dos testes, no Docker local do servidor. Não existe imagem monolítica: uma mudança só na Assistente cria apenas a candidata da Assistente; uma mudança numa lib compartilhada seleciona todas as imagens que realmente copiam essa lib. Uma imagem pode alimentar vários containers, como Similaridade + Feedback e os cinco processos Airflow. O catálogo de componente, imagem, build e serviços de runtime está em `.gitlab/scripts/release_manifest.py`.

O fluxo é `precheck → build:candidates → quality/test → Sonar → deploy`. O job inicial usa o checkout limpo da pipeline e atribui à candidata uma referência imutável de release. Depois do smoke, publica também a referência local `ci-<pipeline>` que os jobs de teste consomem sem pull. O alias de cache de cada componente é calculado dos arquivos Git rastreados que seus `COPY` recebem, `.dockerignore`, Dockerfile, `build`/args efetivos do Compose e plataforma do daemon. Portanto uma alteração só em CI reutiliza a imagem local, enquanto lock, biblioteca copiada, Dockerfile ou argumento de build gera outra chave. O gateway só captura sua imagem-fonte, não participa desse cache. Uma atualização de tag externa mutável do `FROM` exige a política própria de refresh da base, pois o Dockerfile só consegue registrar a referência declarada. O deploy **não pode buildar**: ele exige a referência da release, ativa exatamente essa imagem com `docker compose up --no-build` e confere o image ID do container antes de promover a release (`.gitlab/ci/build-candidates.yml`; `.gitlab/scripts/deploy_changed.sh`).

O cálculo da candidata não recebe credenciais de runtime. Antes de renderizar o
Compose, `.gitlab/scripts/render_candidate_compose.py` deriva do contrato
`security_example.env` um arquivo temporário com valores fictícios determinísticos.
Esse arquivo satisfaz somente a interpolação e mantém o fingerprint estável; o
deploy continua gerando `security.env` com os valores reais. O mesmo render é um
gate `pre-push` na configuração da raiz. O CD usa somente `docker-compose.yml` por
padrão em todos os ambientes; arquivos adicionais exigem `COMPOSE_FILES` explícito.

No primeiro push de uma branch, `CI_COMMIT_BEFORE_SHA` é zero e o GitLab trata
todas as `rules:changes` como verdadeiras. Como todos os jobs de teste por imagem
podem ser criados nesse caso, `build:candidates` garante os aliases `ci-<pipeline>`
de todas as aplicações. Cada componente ainda usa seu fingerprint: uma candidata
presente é apenas retaggeada; se estiver ausente, somente aquela imagem é
reconstruída antes dos jobs com `pull_policy: never`
(`.gitlab/scripts/deploy_changed.sh:551`).

Depois que testes e Sonar aprovam uma feature no servidor de desenvolvimento, o Sonar grava um comprovante local atômico ligado à árvore Git inteira e à assinatura completa da candidata. Se o merge produzir exatamente os mesmos inputs, `build:candidates` valida esse comprovante e os jobs de quality, teste e Sonar da pipeline de `dev` encerram sem repetir os gates; o deploy continua verificando e ativando o mesmo image ID. O cache por componente não relaxa esse comprovante: ele apenas evita reconstruir uma imagem já presente quando um SHA novo alterou arquivos fora dos seus inputs. Merge com conflito, alteração adicional, configuração de build diferente, comprovante ausente ou pipeline de outro ambiente executa todos os gates. O comprovante é local e não tenta atravessar o isolamento entre servidores (`.gitlab/ci/build-candidates.yml`; `.gitlab/ci/sonar.yml`; `.gitlab/scripts/release_manifest.py`).

Cada release bem-sucedida grava um manifesto local completo em `.runtime/releases`: imagens alteradas apontam para os novos IDs e imagens não alteradas são herdadas da release em execução. O manifesto só vira `current.json` depois dos healthchecks e da verificação dos IDs. O rollback valida **todas** as imagens da release anterior antes de alterar containers e recria todos os serviços que compartilham cada imagem; se faltar qualquer artefato, falha sem modificar a implantação (`.gitlab/scripts/release_manifest.py`; `.gitlab/scripts/rollback.sh`).

### Agente de métricas (Telegraf) — somente CD

Os jobs `deploy-*` executam `.gitlab/scripts/deploy_telegraf.sh` depois de `deploy_changed.sh`, no mesmo lock (`.gitlab/ci/deploy-dev.yml:24-25`). O script sobe o projeto Compose separado `seiia-telegraf` (`.gitlab/monitoring/telegraf/docker-compose.yml`), que expõe métricas do host, dos containers e da ocupação do `/home` por usuário em `:50055/metrics` (formato Prometheus, pull). O agente não faz parte da stack: não entra no `docker-compose.yml` raiz, no `make up` nem nos env files, e instalações externas não o recebem. Por isso usa `network_mode: host`, proibido na stack (`.gitlab/monitoring/telegraf/docker-compose.yml:12`).

- **Identidade:** o hostname real da máquina, mais a tag `ambiente`, que vem de `CI_ENVIRONMENT_NAME`. Não há CI var nova.
- **Privilégio:** o agente roda como root sem nenhum poder de root (`cap_drop: ALL`), exceto `CAP_DAC_READ_SEARCH`, que permite ler e listar ignorando permissões. Ele também tem `no-new-privileges` e não usa `privileged` (`.gitlab/monitoring/telegraf/docker-compose.yml:18-26`). O entrypoint da imagem trocaria para o usuário `telegraf` e perderia a capability, por isso o binário é chamado direto. Como root, ele é dono do `docker.sock` e dispensa o GID do grupo `docker`. O `:ro` do socket não restringe a API do Docker, e a capability permite também ler o conteúdo de arquivos, não só os tamanhos.
- **Ocupação do `/home`:** `inputs.exec` roda `home_usage.sh` a cada 20 min (`.gitlab/monitoring/telegraf/telegraf.conf:43-48`). Sempre publica o `df` do sistema de arquivos (`home_usage_fs_*`). Só quando a ocupação atinge `HOME_USAGE_LIMITE_PERCENT` (90%, no próprio `telegraf.conf`) faz a varredura cara, com `du -sxk` por pasta de primeiro nível, publicando `home_usage_used_mb` e `home_usage_used_percent` (sobre a capacidade do `/home`) com a tag `usuario`. Enquanto continuar acima, repete a cada 20 min. `home_usage_coleta_varredura` diz se a última execução varreu (1) ou pulou (0). Abaixo do limite não há séries por usuário. Uma pasta lida só em parte sai com `erro=1`, em vez de ser omitida. Blocos compartilhados (reflink/hardlink) entram no total de cada pasta, então a soma dos usuários pode passar do usado do disco. O `expiration_interval` de 45 min impede que o `prometheus_client` apague as séries entre coletas, com folga para uma varredura atrasada, que de outro modo faria o alerta por usuário oscilar (`telegraf.conf:58`).
- **Recreate:** o hash do `telegraf.conf` e do `home_usage.sh` entra no ambiente do container, porque mudar só o bind não recria (`docker-compose.yml:35`). Sem mudança, o `up` mantém o container.
- **Smoke test:** o deploy só passa se o `/metrics` trouxer séries do host (`cpu_usage_idle`) e dos containers (`docker_container_cpu_*`) em até 180 s (a CPU só aparece a partir da 2ª coleta de 30 s). Em seguida, prova que a capability vale listando cada pasta de `/home` de dentro do agente (`.gitlab/scripts/deploy_telegraf.sh:38-50`).
- **Classificação e rollback:** mudanças em `.gitlab/monitoring/` caem no ignore de `.gitlab/*` de `deploy_changed.sh`, então não disparam deploy da stack. O rollback não toca no agente.

### Cache local de build

Os ambientes não dependem de registry ou proxy de pacotes compartilhado. Cada servidor reaproveita, nesta ordem:

1. a imagem final candidata já existente — nenhum passo do Dockerfile executa;
2. as layers do BuildKit integrado do daemon (driver `docker`, builder `default`) — se os metadados/lock não mudaram, a instalação de dependências é pulada inteira;
3. os downloads UV e APT/DNF em cache mounts do BuildKit — se uma layer precisar ser refeita, wheels grandes como Torch são lidos do cache local em vez de baixados novamente. Similaridade e Jobs API usam o mesmo cache UV de Python 3.10, pertencente ao UID 4000; o Airflow mantém outro cache UV no UID 50000. Essa separação evita permissões incompatíveis e mantém o cache reutilizável entre as duas imagens (`aplicacoes/similaridade/api_sei.dockerfile`; `aplicacoes/etl-airflow/jobs_api.dockerfile`; `aplicacoes/etl-airflow/airflow.dockerfile`).

A migração para o builder integrado não importa as layers nem os cache mounts do antigo `seiia-bridge`. O primeiro build integrado é frio; os cache mounts serão populados novamente no daemon e só então acelerarão novas reconstruções. O cache `/cache` do runner usado pelo grupo `ci-test` é separado.

Os testes usam a candidata local como imagem do job (`pull_policy: never`) e executam o Python de sistema e o código já presentes nela. O checkout contribui apenas a suíte e os auxiliares de teste, copiados para o filesystem efêmero do job; uma guarda recusa importar um módulo do checkout. O único install do job é o grupo travado `ci-test`, exportado sem as dependências da aplicação e instalado com `uv pip install --system --python /usr/local/bin/python --no-deps`. Seus downloads ficam no cache UV local do runner, fora do checkout e sem archive GitLab (`.gitlab/ci/quality-and-test.yml`; `.gitlab/scripts/run_candidate_tests.sh`).

Os Dockerfiles copiam `pyproject.toml` + lock antes do código. O Assistente exporta os requisitos externos do lock e faz `uv pip sync --system --strict --require-hashes`, usando o índice CPU do PyTorch e o cache UV montado no host; o código e as libs locais entram depois via `PYTHONPATH`, sem `.venv` nem cópia entre stages (`aplicacoes/assistente/assistente.dockerfile:36-46`). Os sdists atuais são Python puro; se um lock futuro exigir compilação nativa, o build falha sem toolchain e a dependência precisa de tratamento explícito. Similaridade e Jobs API baixam o CPython 3.10 travado para um virtualenv isolado em `/home/seisimi/.venv`; o Airflow mantém o Python do seu image base e instala requisitos travados no ambiente oficial `/home/airflow/.local`. Só depois entra o código local: Similaridade e Jobs API o instalam sem nova resolução; o Airflow expõe suas fontes Python pelo `PYTHONPATH`, sem copiar uma árvore `.local` entre stages nem reinstalar o projeto a cada alteração (`aplicacoes/etl-airflow/airflow.dockerfile`). Assim uma troca apenas de código reaproveita a layer das dependências. Os caches são aceleradores descartáveis; a versão instalada continua sendo decidida pelo lock, nunca pelo conteúdo do cache.

A promoção `dev → homologação → main`, o isolamento físico dos caches e as regras de branch/MR estão na documentação interna de workflow (não incluída no mirror externo).

## Rede e builder do Docker (redes corporativas)

Em redes corporativas onde a default bridge do Docker é desativada, os targets Docker declarados no Compose usam `build.network: host` durante os passos `RUN`. Compose 2.33 perde esse campo ao traduzir para Bake; por isso os builds via Compose fixam `COMPOSE_BAKE=false` e usam o caminho nativo, que propaga `network: host` ao BuildKit integrado `default`. O Sonar usa o mesmo driver diretamente com `docker buildx build --builder default --network host`. O modo `host` vale somente durante o build: os containers de runtime continuam na rede externa `docker-host-bridge`, os probes usam `--network none` e o deploy ativa imagens existentes com `--no-build`.

Quando os runners tiverem Compose v2.37.3 ou superior, validado nos próprios runners, o workaround `COMPOSE_BAKE=false` poderá ser reavaliado; até lá ele é uma guarda de rede, não um fallback de builder.

O helper `.gitlab/scripts/ensure_buildx_builder.sh` e `.gitlab/buildkit/buildkitd.toml` permanecem apenas para rollback manual temporário de instalações antigas. O pipeline nunca os chama; o helper exige `BUILDX_LEGACY_ROLLBACK=1`. A mudança não remove um container ou builder legado já existente no host. A configuração de rede e o passo-a-passo completo estão em `docs/INSTALL.md`.

## Certificado HTTPS e confiança no SEI

As três APIs do SEI são servidas por um único `gateway-nginx` (`docker-compose.yml:118-166`). Assistente, Similaridade e Feedback recebem HTTP interno; certificado e chave não entram nas imagens nem nos comandos Gunicorn (`docker-compose.yml:65-220`). O gateway usa `init: true`, `TZ=America/Sao_Paulo`, rotação `json-file` de `20m × 5` e access log estruturado somente para respostas `4xx`/`5xx`; `/health` permanece sempre silencioso. O request buffering e `client_max_body_size 100M` do Assistente continuam ativos (`docker-compose.yml:118-166`; `ops/gateway/nginx.conf:7-60`).

O par `.runtime/certs/seiia.cert.{pem,key}` é preparado **no host** por `ops/scripts/ensure_certs.sh`, executado por `make up`, `make check` e pelo deploy. Sem arquivos preexistentes, o script cria e marca um certificado autoassinado gerenciado. Um par fornecido pelo operador é validado quanto a formato, correspondência da chave, validade e SAN, mas nunca é sobrescrito silenciosamente.

- **Hostname canônico:** `SEIIA_GATEWAY_HOST` é obrigatório, vira alias Docker do gateway e precisa estar no SAN. `SEIIA_CERT_DNS` adiciona nomes secundários.
- **Trust no módulo:** o PHP do SEI exige uma CA bundle legível em `/opt/sei/config/mod-ia/seiia.cert.pem`. Para o certificado autoassinado, use o PEM público gerado; para PKI do órgão, use a cadeia de CA apropriada.
- **Sem fallback dentro de imagem:** nenhuma imagem fabrica certificado alternativo. O procedimento para mesmo host e hosts separados está em `docs/INSTALL.md`.

## Gotchas de build

- `../../libs/*` fora da raiz → `uv` recusa normalizar. Buildar do diretório da app; no Docker, manter o espelhamento dos metadados — `aplicacoes/assistente/assistente.dockerfile:28-30`.
- `make check` roda `uv lock --locked` — lockfile dessincronizado com o `pyproject.toml` quebra o check — `aplicacoes/assistente/Makefile:9-10`.
- Python preso em 3.12 — `aplicacoes/assistente/pyproject.toml:12`.

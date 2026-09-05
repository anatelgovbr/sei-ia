# Instalação do Servidor de Soluções de IA do módulo SEI IA

- Este guia descreve a instalação nova, por código-fonte, do *Servidor de Soluções
  de IA* do módulo SEI IA em um servidor Linux dedicado.
- Para instalar o servidor é obrigatório ter o Módulo SEI IA previamente instalado
  e configurado no SEI e no SIP do ambiente correspondente.
- Execute as etapas na ordem apresentada e use os arquivos da mesma tag. Não misture
  `default.env`, `security_example.env`, `litellm_config.template.yaml` ou arquivos
  Compose de versões diferentes.
- **Para atualizar uma instalação existente**, siga o
  [Guia de Atualização](UPGRADE.md). Uma instalação 1.2.x deve usar
  o [procedimento específico de 1.2.x para 1.3](upgrades/1.2-to-1.3.md),
  que preserva configurações e dados.
- **ATENÇÃO:** o servidor não deve ser compartilhado com outras soluções. O
  dimensionamento e os limites versionados consideram o uso dedicado pela stack.
- **ATENÇÃO:** a instalação somente é considerada concluída quando `make check`
  termina sem erros e o Assistente responde pela interface do SEI.

---

## Sumário

- [1. Pré-requisitos](#1-pré-requisitos)
  - [1.1. Versões homologadas](#11-versões-homologadas)
  - [1.2. Instalação do SEI e do Módulo SEI IA](#12-instalação-do-sei-e-do-módulo-sei-ia)
  - [1.3. Servidor e recursos](#13-servidor-e-recursos)
  - [1.4. Configurações na rede local do órgão](#14-configurações-na-rede-local-do-órgão)
- [2. Passos para instalação](#2-passos-para-instalação)
  - [2.1. Criar usuário, diretórios e rede Docker](#21-criar-usuário-diretórios-e-rede-docker)
  - [2.2. Baixar uma tag estável](#22-baixar-uma-tag-estável)
  - [2.3. Definir os parâmetros locais no `default.env`](#23-definir-os-parâmetros-locais-no-defaultenv)
  - [2.4. Configurar o `security.env`](#24-configurar-o-securityenv)
    - [2.4.1. Criar e proteger o arquivo](#241-criar-e-proteger-o-arquivo)
    - [2.4.2. Serviços internos](#242-serviços-internos)
    - [2.4.3. LiteLLM e provedores de modelos](#243-litellm-e-provedores-de-modelos)
    - [2.4.4. Integrações e recursos opcionais](#244-integrações-e-recursos-opcionais)
    - [2.4.5. Escolha do DNS do gateway](#245-escolha-do-dns-do-gateway)
    - [2.4.6. Exemplo completo](#246-exemplo-completo)
    - [2.4.7. Validar o contrato](#247-validar-o-contrato)
- [3. Configuração dos modelos LLM e LiteLLM](#3-configuração-dos-modelos-llm-e-litellm)
  - [3.1. Prepare o LiteLLM](#31-prepare-o-litellm)
    - [3.1.1. Credenciais do LiteLLM](#311-credenciais-do-litellm)
  - [3.2. Descrição dos agentes e seus modelos](#32-descrição-dos-agentes-e-seus-modelos)
- [4. Configuração do certificado HTTPS](#4-configuração-do-certificado-https)
  - [4.1. Certificado gerado automaticamente](#41-certificado-gerado-automaticamente)
  - [4.2. Certificado emitido pela PKI do órgão](#42-certificado-emitido-pela-pki-do-órgão)
- [5. Executar o deploy](#5-executar-o-deploy)
- [6. Configuração da confiança TLS no SEI](#6-configuração-da-confiança-tls-no-sei)
  - [6.1. SEI e SEI IA no mesmo host Docker](#61-sei-e-sei-ia-no-mesmo-host-docker)
  - [6.2. SEI e SEI IA em hosts diferentes](#62-sei-e-sei-ia-em-hosts-diferentes)
- [7. Mapeamento da integração no SEI](#7-mapeamento-da-integração-no-sei)
- [8. Health Checker geral do ambiente](#8-health-checker-geral-do-ambiente)
- [9. Resolução de problemas conhecidos](#9-resolução-de-problemas-conhecidos)
- [10. Dimensionamento](#10-dimensionamento)

---

## 1. Pré-requisitos

### 1.1. Versões homologadas

Instale as três versões como um conjunto:

| Componente | Versão |
|---|---:|
| SEI | 5.0.4.22 |
| Módulo SEI IA | 1.5.0 |
| Servidor de Soluções de IA | 1.3 |

### 1.2. Instalação do SEI e do Módulo SEI IA

Instale o SEI `5.0.4.22` conforme seu manual oficial. Baixe o Módulo SEI IA `1.5.0`
em [Releases do módulo](https://github.com/anatelgovbr/mod-sei-ia/releases) e siga o
README incluído no pacote. O procedimento do módulo é a fonte de verdade para a
instalação no SEI e no SIP.

Os pontos que devem estar concluídos antes de instalar este servidor são:

1. conferir no módulo os requisitos de PHP, extensões e PyMuPDF;
2. copiar os arquivos do módulo para as árvores correspondentes do SEI e do SIP;
3. declarar `'IaIntegracao' => 'ia'` na lista `Modulos` de
   `ConfiguracaoSEI.php`, preservando o charset do arquivo;
4. confirmar o módulo em **Infra > Módulos**;
5. executar os scripts `sip_atualizar_versao_modulo_ia.php` e
   `sei_atualizar_versao_modulo_ia.php` com o PHP CLI correto;
6. confirmar que os dois scripts terminam com `FIM`, sem erros;
7. confirmar `VERSAO_MODULO_IA=1.5.0` tanto no SEI quanto no SIP;
8. disponibilizar os recursos do módulo aos perfis que utilizarão o Assistente.

A configuração do hostname das integrações e do certificado será concluída depois
que o gateway estiver em execução.

### 1.3. Servidor e recursos

Use um servidor Linux dedicado. O ambiente de referência possui 16 vCPUs, 128 GB
de RAM e 450 GB de disco. A infraestrutura do SEI não está incluída nesses valores.

Instale e valide:

```bash
git --version
make --version
openssl version
docker version
docker compose version
docker buildx version
```

Versões mínimas: Docker Engine 27.1.1, Compose 2.29 e Buildx 0.13. O Docker deve ser
rootful: o checker usa o socket local para validar os contêineres.

### 1.4. Configurações na rede local do órgão

O servidor precisa de:

- saída HTTPS e DNS para baixar o código, imagens base e dependências de build;
- relógio sincronizado por NTP;
- portas `8088/tcp`, `8082/tcp` e `8086/tcp` livres para o gateway;
- porta `8081/tcp` livre no loopback para a interface administrativa do Airflow;
- um hostname DNS reservado para o gateway, por exemplo
  `seiia.producao.orgao.gov.br`.

Verifique conflitos antes da instalação:

```bash
ss -ltn | grep -E ':(8088|8082|8086|8081)\b' || true
docker network ls
df -h /opt /var
free -h
```

As permissões mínimas de rede são:

| Origem | Destino | Porta/protocolo | Finalidade |
|---|---|---|---|
| Servidor SEI IA | SEI | HTTP ou HTTPS do SEI | consumo do Webservice do Módulo SEI IA |
| Nós PHP do SEI | Gateway SEI IA | `8088/tcp` | Assistente |
| Nós PHP do SEI | Gateway SEI IA | `8082/tcp` | Similaridade |
| Nós PHP do SEI | Gateway SEI IA | `8086/tcp` | Feedback |
| Administradores autorizados | Servidor SEI IA | `8081/tcp` no loopback/túnel | interface administrativa do Airflow |
| Servidor SEI IA | Internet ou repositórios internos aprovados | HTTPS e DNS | código-fonte, imagens base, pacotes e provedores de modelos |

As portas HTTPS devem aceitar conexões somente dos servidores do SEI e dos pontos
administrativos autorizados. A interface do Airflow é publicada apenas em
`127.0.0.1:8081`; para administração remota, use túnel SSH ou um acesso controlado
equivalente.

Antes de seguir, valide DNS, rota, firewall e o acesso ao provedor de modelos a
partir do servidor. Uma credencial correta não resolve um endpoint que o host não
alcança.

## 2. Passos para instalação

### 2.1. Criar usuário, diretórios e rede Docker

Os valores versionados usam o usuário `seiia` com UID/GID `4000`. Antes de criá-lo,
confirme que esses IDs estão livres:

```bash
getent passwd 4000 || true
getent group 4000 || true
```

Se houver conflito, escolha IDs livres e atualize `NB_UID` e `NB_GID` em
`default.env` antes do primeiro `make up`.

Exemplo com os valores padrão:

```bash
sudo useradd --create-home --shell /bin/bash --uid 4000 seiia
sudo usermod --append --groups docker seiia
sudo install --directory --owner=seiia --group=docker --mode=0750 /opt/sei-ia
sudo install --directory --owner=seiia --group=docker --mode=0750 /var/seiia/volumes
```

Encerre e abra novamente a sessão do usuário para aplicar o grupo `docker`. Confirme
sem `sudo`:

```bash
docker info >/dev/null
```

Crie a rede externa usada pela stack. Não fixe um subnet sem antes verificar as
redes corporativas, VPNs e redes Docker existentes. Consulte a equipe de redes e
liste rotas e subnets já utilizadas:

```bash
ip route
docker network ls -q | xargs -r docker network inspect \
  --format '{{.Name}}: {{range .IPAM.Config}}{{.Subnet}} {{end}}'
```

Quando a equipe fornecer uma faixa aprovada, crie a rede com `--subnet` e
`--gateway`:

```bash
docker network create --driver bridge \
  --subnet <SUBNET_APROVADA> --gateway <GATEWAY_APROVADO> \
  docker-host-bridge
```

Se o órgão optar pela alocação automática, use o comando abaixo, inspecione a faixa
escolhida pelo Docker e confirme que ela não se sobrepõe à LAN, VPN ou redes de
outros hosts antes de iniciar a stack:

```bash
docker network create --driver bridge docker-host-bridge
docker network inspect docker-host-bridge
```

Se o órgão usar outro nome, altere somente `COMPOSE_NETWORK_NAME` em `default.env`.
O nome precisa corresponder a uma rede externa já existente.

Em hosts com SELinux enforcing, rotule `/var/seiia/volumes`, `/opt/sei-ia/.runtime`
e os arquivos de configuração para uso por contêineres conforme a política do
órgão. Não desabilite o SELinux para contornar erros de permissão.

### 2.2. Baixar uma tag estável

Execute como o usuário `seiia`:

```bash
git clone --branch v1.3.0 --single-branch \
  https://github.com/anatelgovbr/sei-ia.git /opt/sei-ia
cd /opt/sei-ia
git status --short
git describe --tags --exact-match
```

O status deve estar limpo e a tag deve ser `v1.3.0`. Não instale diretamente de uma
branch de trabalho.

### 2.3. Definir os parâmetros locais no `default.env`

O arquivo contém somente parâmetros não sensíveis e limites para o ambiente de
referência. Antes da primeira subida, revise pelo menos:

- `NB_USER`, `NB_UID` e `NB_GID`;
- `VOL_SEIIA_DIR`;
- `COMPOSE_NETWORK_NAME`;
- `TZ`;
- os limites de CPU e memória, apenas se o dimensionamento aprovado pelo órgão for
  diferente do ambiente de referência.

Não copie limites de um ambiente de laboratório. A soma dos limites e das réplicas
precisa caber no host dedicado com margem para Docker, kernel, cache de disco e picos
do Solr.

O `default.env` não recebe credenciais, tokens nem chaves. Esses valores e os
endpoints específicos do órgão pertencem ao `security.env`, configurado na próxima
etapa.

### 2.4. Configurar o `security.env`

O `security.env` concentra credenciais, nomes de modelos, endpoints de provedores e
os endereços privados da integração. Ele não é versionado. Preencha-o a partir do
template da mesma tag e mantenha todas as variáveis declaradas em
`security_example.env`.

#### 2.4.1. Criar e proteger o arquivo

Crie o arquivo e restrinja a leitura:

```bash
cd /opt/sei-ia
cp security_example.env security.env
chmod 600 security.env
```

Não adicione, remova nem repita nomes de variáveis. As variáveis opcionais continuam
presentes, com valor vazio. Os textos entre `<` e `>` nas tabelas e no exemplo abaixo
são marcadores: substitua todos eles pelos valores reais antes do deploy.

Gere segredos independentes. Exemplos:

```bash
openssl rand -hex 32
printf 'sk-%s\n' "$(openssl rand -hex 32)"
```

Use o primeiro formato para senhas/chaves gerais e o segundo para
`LITELLM_PROXY_API_KEY` em instalações novas. Não rotacione automaticamente as
credenciais de uma instalação existente.

#### 2.4.2. Serviços internos

Preencha primeiro as credenciais dos serviços persistentes. Os exemplos não são
senhas reais.

| Variável | Como preencher | Exemplo |
|---|---|---|
| `ENVIRONMENT` | mantenha o contrato externo de produção | `prod` |
| `DB_SEIIA_USER` | usuário do PostgreSQL/pgvector do SEI IA | `seiia_app` |
| `DB_SEIIA_PWD` | senha exclusiva do PostgreSQL/pgvector | `<SEGREDO_DB_SEIIA>` |
| `SOLR_USER` | usuário administrativo do Solr | `seiia` |
| `SOLR_PASSWORD` | senha exclusiva do Solr | `<SEGREDO_SOLR>` |
| `AIRFLOW_POSTGRES_DB` | nome do metastore do Airflow | `airflow` |
| `AIRFLOW_POSTGRES_USER` | usuário do metastore do Airflow | `airflow` |
| `AIRFLOW_POSTGRES_PASSWORD` | senha exclusiva do metastore | `<SEGREDO_POSTGRES_AIRFLOW>` |
| `AIRFLOW_AMQP_USER` | usuário do RabbitMQ usado pelo Airflow | `airflow` |
| `AIRFLOW_AMQP_PASSWORD` | senha exclusiva do RabbitMQ | `<SEGREDO_RABBITMQ>` |
| `_AIRFLOW_WWW_USER_USERNAME` | usuário inicial da interface administrativa | `seiia_admin` |
| `_AIRFLOW_WWW_USER_PASSWORD` | senha inicial forte da interface | `<SENHA_UI_AIRFLOW>` |
| `AIRFLOW__WEBSERVER__SECRET_KEY` | chave de assinatura das sessões; gere com `openssl rand -hex 32` | `<64_HEXADECIMAIS>` |

Em uma atualização, preserve os usuários e senhas que os volumes existentes já
utilizam. Trocar uma credencial sem migrar o serviço impede a abertura dos dados
persistentes.

#### 2.4.3. LiteLLM e provedores de modelos

Gere a chave local do proxy com o formato exigido pelo checker:

| Variável | Como preencher | Exemplo |
|---|---|---|
| `LITELLM_PROXY_API_KEY` | chave apresentada por Assistente, ETL e checker ao proxy local; gere com `printf 'sk-%s\n' "$(openssl rand -hex 32)"` | `sk-<64_HEXADECIMAIS>` |

Depois preencha, para cada tier, o modelo físico, o endpoint e a credencial fornecida
pelo provedor:

| Tier | Modelo | Endpoint | Chave do provedor | Versão da API |
|---|---|---|---|---|
| Standard | `LITELLM_STANDARD_MODEL` — `openai/modelo-principal` | `LITELLM_STANDARD_API_BASE` — `https://modelos.orgao.gov.br/v1` | `LITELLM_STANDARD_API_KEY` — `<CHAVE_STANDARD>` | `LITELLM_STANDARD_API_VERSION` — vazio ou `2025-03-01-preview` |
| Mini | `LITELLM_MINI_MODEL` — `openai/modelo-mini` | `LITELLM_MINI_API_BASE` — `https://modelos.orgao.gov.br/v1` | `LITELLM_MINI_API_KEY` — `<CHAVE_MINI>` | `LITELLM_MINI_API_VERSION` — vazio ou `2025-03-01-preview` |
| Nano | `LITELLM_NANO_MODEL` — `openai/modelo-nano` | `LITELLM_NANO_API_BASE` — `https://modelos.orgao.gov.br/v1` | `LITELLM_NANO_API_KEY` — `<CHAVE_NANO>` | `LITELLM_NANO_API_VERSION` — vazio ou `2025-03-01-preview` |
| Embedding | `LITELLM_EMBEDDING_MODEL` — `openai/modelo-embedding` | `LITELLM_EMBEDDING_API_BASE` — `https://modelos.orgao.gov.br/v1` | `LITELLM_EMBEDDING_API_KEY` — `<CHAVE_EMBEDDING>` | `LITELLM_EMBEDDING_API_VERSION` — vazio ou `2025-03-01-preview` |
| Speech-to-text | `LITELLM_STT_MODEL` — `openai/modelo-transcricao` | `LITELLM_STT_API_BASE` — `https://modelos.orgao.gov.br/v1` | `LITELLM_STT_API_KEY` — `<CHAVE_STT>` | `LITELLM_STT_API_VERSION` — vazio ou `2025-03-01-preview` |

O prefixo do modelo deve ser aceito pelo LiteLLM, como `azure/...` ou `openai/...`.
Standard, Mini e Nano podem apontar para o mesmo deployment, mas cada tier mantém
suas quatro variáveis. A versão da API só pode ficar vazia quando o provedor não usa
esse parâmetro. Consulte a [seção 3](#3-configuração-dos-modelos-llm-e-litellm) para
o papel de cada tier e a separação entre a chave local do proxy e as chaves dos
provedores.

#### 2.4.4. Integrações e recursos opcionais

| Variável | Obrigatoriedade | Como preencher | Exemplo |
|---|---|---|---|
| `SEI_ADDRESS` | Obrigatória | URL base do SEI, sem `/sei/controlador_ws.php` | `https://sei.orgao.gov.br` |
| `SEI_API_DB_IDENTIFIER_SERVICE` | Obrigatória | Chave de Acesso do serviço `consultarDocumentoExternoIA` do sistema `Usuario_IA`, gerada no painel do SEI | `<CHAVE_DE_ACESSO_GERADA_NO_SEI>` |
| `SEIIA_GATEWAY_HOST` | Obrigatória | DNS/FQDN do gateway, sem protocolo, porta ou caminho | `seiia.orgao.gov.br` |
| `SEIIA_CERT_DNS` | Opcional | Nomes DNS adicionais do certificado, separados por vírgula | vazio ou `seiia-alias.orgao.gov.br` |
| `SEARXNG_SECRET_KEY` | Obrigatória, com geração automática | Deixe vazia inicialmente para `make config`, `make up` ou `make check` gerar e salvar a chave | vazio |
| `LANGFUSE_URL` | Opcional | Preencha junto com as duas chaves somente se `ASSISTENTE_USE_LANGFUSE=true` no `default.env` | vazio ou `https://langfuse.orgao.gov.br` |
| `LANGFUSE_PUBLIC_KEY` | Opcional | Chave pública do mesmo projeto Langfuse | vazio ou `<CHAVE_PUBLICA_LANGFUSE>` |
| `LANGFUSE_SECRET_KEY` | Opcional | Chave secreta do mesmo projeto Langfuse | vazio ou `<CHAVE_SECRETA_LANGFUSE>` |

> **ATENÇÃO:** `SEI_API_DB_IDENTIFIER_SERVICE` não é uma chave arbitrária. O script
> de instalação do Módulo SEI IA cria o sistema `Usuario_IA` e o serviço
> `consultarDocumentoExternoIA`, mas a Chave de Acesso deve ser gerada no SEI em
> **Administração > Sistemas > Usuario_IA > Serviços >
> consultarDocumentoExternoIA > Gerar Chave de Acesso**.

#### 2.4.5. Escolha do DNS do gateway

Reserve um FQDN estável e exclusivo para o gateway, por exemplo
`seiia.orgao.gov.br`. Substitua o exemplo pelo nome aprovado pelo órgão e publique
um registro DNS `A` e/ou `AAAA` apontando o FQDN para o servidor SEI IA. Use
exatamente o mesmo nome, sem protocolo, porta ou caminho:

1. em `SEIIA_GATEWAY_HOST` no `security.env`;
2. no SAN do certificado apresentado pelo gateway;
3. na URL base cadastrada nas integrações do Módulo SEI IA, com o prefixo
   `https://` somente nessa tela.

Não use o endereço IP como substituto do FQDN. Antes da validação pelo SEI, confirme
no próprio nó PHP que o FQDN resolve para o endereço esperado e que as portas do
gateway estão acessíveis.

Nunca coloque credenciais em `default.env`, `litellm_config.yaml`, arquivos Compose,
commits ou chamados de suporte.

#### 2.4.6. Preencher o template

Não copie credenciais de exemplos de documentação. O arquivo
`security_example.env` da tag é a fonte de verdade para nomes, ordem e comentários
das variáveis. Copie-o para `security.env` e preencha localmente todos os campos
obrigatórios descritos nas seções anteriores.

Use valores diferentes para cada senha ou chave. Gere os segredos aleatórios com
os comandos indicados no próprio template e mantenha vazias somente as integrações
opcionais que não serão habilitadas. O arquivo `security.env` não deve ser
commitado nem enviado em chamados de suporte.

#### 2.4.7. Validar o contrato

Depois de copiar `litellm_config.template.yaml` conforme a
[seção 3.1](#31-prepare-o-litellm), valide a interpolação do Compose:

```bash
cd /opt/sei-ia
make config
```

O comando gera `SEARXNG_SECRET_KEY` quando necessário e deve terminar com código
zero. Depois do deploy, `make check` valida o inventário exato dos dois arquivos
`.env`: variável ausente, extra, duplicada, inválida ou obrigatória vazia reprova a
instalação.

## 3. Configuração dos modelos LLM e LiteLLM

O LiteLLM é o proxy local entre as aplicações e os provedores de modelos. Assistente,
ETL e Health Checker chamam o proxy com uma chave local; o proxy usa as credenciais
do provedor configuradas em `security.env` para encaminhar cada requisição.

### 3.1. Prepare o LiteLLM

O template publica cinco aliases fixos: `standard`, `mini`, `nano`, `embedding` e
`speech-to-text`. O `make check` exige cada alias com suas respectivas tags; uma
entrada com nome físico e as mesmas tags não substitui esse contrato. Os modelos
físicos permanecem em `litellm_params.model` e `model_info.base_model` via ambiente.

| Alias (`model_name`) | Modelo físico no `security.env` | Papéis autorizados | Uso principal |
|---|---|---|---|
| `standard` | `LITELLM_STANDARD_MODEL` | `agents:principal` | resposta final, coordenação da sessão e pesquisa profunda |
| `mini` | `LITELLM_MINI_MODEL` | `agents:classificador`, `agents:busca_web` | classificação/extração e planejamento de consultas web |
| `nano` | `LITELLM_NANO_MODEL` | `agents:explorador`, `agents:ocr`, `agents:triagem_busca` | exploração de documentos, OCR com capacidade multimodal e triagem de evidências web |
| `embedding` | `LITELLM_EMBEDDING_MODEL` | `agents:embedding` | geração de vetores para documentos e consultas |
| `speech-to-text` | `LITELLM_STT_MODEL` | `agents:audio_transcription` | transcrição de anexos de áudio |

Mantenha os aliases da primeira coluna em `model_name`, mesmo quando dois deles
usam o mesmo modelo. Configure os modelos do provedor nas variáveis correspondentes
do `security.env`, sem alterar os aliases no template.

As tags esperadas são:

```text
agents:principal
agents:classificador
agents:busca_web
agents:explorador
agents:ocr
agents:triagem_busca
agents:embedding
agents:audio_transcription
```

Não existem mais os modelos ou aliases `think`, `think-low` e `think-none`.
Raciocínio é uma característica da chamada do papel `principal`: o Assistente envia
`reasoning_effort` quando aplicável, usando o mesmo modelo Standard.

#### 3.1.1. Credenciais do LiteLLM

As seis chaves protegem fronteiras diferentes:

| Chave | Quem apresenta a chave | O que ela libera |
|---|---|---|
| `LITELLM_PROXY_API_KEY` | Assistente, ETL e checker | acesso autenticado ao proxy LiteLLM local e às entradas publicadas |
| `LITELLM_STANDARD_API_KEY` | proxy LiteLLM | acesso ao provedor do modelo Standard |
| `LITELLM_MINI_API_KEY` | proxy LiteLLM | acesso ao provedor do modelo Mini |
| `LITELLM_NANO_API_KEY` | proxy LiteLLM | acesso ao provedor do modelo Nano |
| `LITELLM_EMBEDDING_API_KEY` | proxy LiteLLM | acesso ao provedor do modelo de embeddings |
| `LITELLM_STT_API_KEY` | proxy LiteLLM | acesso ao provedor de speech-to-text |

Standard, Mini, Nano, Embedding e speech-to-text possuem endpoint, chave e versão de
API próprios. Os valores podem coincidir quando o provedor entregar o mesmo contrato,
mas nenhuma entrada herda silenciosamente a credencial de outra. `*_API_VERSION`
pode ficar vazio somente quando o provedor não utiliza esse parâmetro.

Exemplo de preenchimento no `security.env` usando nomes fictícios:

```dotenv
LITELLM_STANDARD_MODEL=openai/modelo-principal
LITELLM_STANDARD_API_BASE=https://modelos.exemplo.orgao.gov.br/v1
LITELLM_STANDARD_API_VERSION=
LITELLM_MINI_MODEL=openai/modelo-mini
LITELLM_MINI_API_BASE=https://modelos-mini.exemplo.orgao.gov.br/v1
LITELLM_MINI_API_VERSION=
LITELLM_NANO_MODEL=openai/modelo-nano
LITELLM_NANO_API_BASE=https://modelos-nano.exemplo.orgao.gov.br/v1
LITELLM_NANO_API_VERSION=
```

Use os nomes, endpoints e as chaves fornecidos pelo provedor do órgão. Preencha a
chave diretamente no arquivo privado, sem reproduzi-la em documentação, terminal
compartilhado ou chamado. Não copie os valores fictícios do exemplo.

Copie o template sem substituir as referências `os.environ/VAR` por credenciais:

```bash
cd /opt/sei-ia
cp litellm_config.template.yaml litellm_config.yaml
chmod 600 litellm_config.yaml
```

O arquivo gerado mantém aliases literais e referências ao ambiente para modelos
físicos, endpoints e credenciais. Os valores sensíveis permanecem somente no
`security.env`. O `make check` verifica a saúde do proxy e a presença dos cinco
aliases com suas oito tags obrigatórias; essa checagem não substitui o teste
funcional pelo SEI.

### 3.2. Descrição dos agentes e seus modelos

Nem todo papel representa um agente independente. Alguns são tarefas especializadas
executadas dentro do fluxo principal.

| Agente ou operação | Modelo configurado | Papel | Função |
|---|---|---|---|
| Agente principal da sessão | Standard (`LITELLM_STANDARD_MODEL`) | `principal` | interpreta o pedido, decide quais documentos e ferramentas consultar, coordena subagentes e produz a resposta final; usa Responses API e reasoning |
| Subagente explorador | Nano (`LITELLM_NANO_MODEL`) | `explorador` | no modo filesystem, lê um documento específico da sessão e devolve evidências estruturadas ao principal; na pesquisa profunda, o mesmo papel atua como `compress_llm` |
| Classificação e extração | Mini (`LITELLM_MINI_MODEL`) | `classificador` | classifica a complexidade da solicitação e extrai informações de páginas ou evidências usadas pela pesquisa profunda |
| Planejador de busca web | Mini (`LITELLM_MINI_MODEL`) | `busca_web` | formula consultas especulativas antes do agente principal; a ferramenta `WebResearchAgent` coleta e grava páginas sem executar outro LLM internamente |
| Triagem de evidências web | Nano (`LITELLM_NANO_MODEL`) | `triagem_busca` | seleciona evidências relevantes e identifica lacunas antes de entregar o material pesquisado ao principal |
| OCR | Nano (`LITELLM_NANO_MODEL`) | `ocr` | interpreta páginas digitalizadas ou imagens quando a extração textual comum não é suficiente |
| Vetorização | Embedding (`LITELLM_EMBEDDING_MODEL`) | `embedding` | gera embeddings usados pelo Assistente e pela ETL para indexação e recuperação vetorial |
| Transcrição | Speech-to-text (`LITELLM_STT_MODEL`) | `audio_transcription` | converte anexos de áudio em texto antes que o conteúdo seja entregue ao fluxo do Assistente |

Não há um agente separado de imagem ou de anexos: imagens são entregues ao principal
como conteúdo multimodal, e os anexos são preparados antes da construção do agente.

A busca web do Assistente usa SearXNG e os serviços de crawling da própria stack.
Ela não usa Bing Grounding, Azure AI Agent, `AZURE_WEB_AGENT_ID` nem
`BING_CONNECTION_NAME`. A opção é habilitada na configuração do Assistente no SEI.

## 4. Configuração do certificado HTTPS

O gateway Nginx encerra TLS nas três portas públicas. Os backends permanecem HTTP
dentro da rede Docker. Antes do primeiro `make up`, escolha entre deixar o comando
gerar um par autoassinado ou fornecer o certificado institucional do órgão.

### 4.1. Certificado gerado automaticamente

Quando os dois arquivos ainda não existem, o primeiro `make up` gera:

```text
/opt/sei-ia/.runtime/certs/seiia.cert.pem
/opt/sei-ia/.runtime/certs/seiia.cert.key
```

O certificado cobre `SEIIA_GATEWAY_HOST`; a chave gerada fica com modo `0600`. O PEM público
autoassinado é também o material de confiança que será fornecido ao servidor SEI.
Nunca copie a chave privada para o SEI.

### 4.2. Certificado emitido pela PKI do órgão

Antes do primeiro `make up`, coloque o par diretamente nos caminhos esperados:

```bash
cd /opt/sei-ia
mkdir -p .runtime/certs
install -m 0644 /caminho/seguro/certificado-com-cadeia.pem \
  .runtime/certs/seiia.cert.pem
install -m 0600 /caminho/seguro/chave-privada.pem \
  .runtime/certs/seiia.cert.key
```

- `seiia.cert.pem`: certificado do gateway seguido da cadeia intermediária servida
  pelo Nginx;
- `seiia.cert.key`: chave privada RSA ou EC correspondente, sem senha interativa.

O modo `0600` é o padrão recomendado. O modo `0640` também é aceito quando o grupo
é restrito aos administradores ou ao serviço responsável. Escrita ou execução pelo
grupo e qualquer permissão para outros usuários não são aceitas.

O certificado deve estar válido e conter `SEIIA_GATEWAY_HOST` no SAN. O script valida
o par e não sobrescreve silenciosamente um certificado fornecido pelo operador.

Para o módulo, forneça depois uma CA bundle confiável emitida pela PKI. Ela pode ser
diferente do certificado e da cadeia servidos pelo Nginx.

## 5. Executar o deploy

Depois de preparar o contrato privado e decidir o TLS, execute:

```bash
cd /opt/sei-ia
make up
```

`make up` completa `SEARXNG_SECRET_KEY` quando necessário, valida a composição,
preserva ou gera o certificado, prepara os diretórios persistentes, limita a três o
número de builds simultâneos e só então inicia os serviços. Na primeira execução, o
download e o build podem demorar. Em um host com
menos memória disponível, reduza a concorrência, por exemplo:

```bash
make BUILD_PARALLELISM=2 up
```


Aguarde até os serviços permanentes ficarem `running` e `healthy`. O contêiner de
inicialização do Airflow termina com código zero; ele não permanece em execução.
Depois da subida, execute obrigatoriamente:

```bash
make check
```

O comando deve terminar com código zero e sem erros.

Para interromper e iniciar novamente a stack de forma controlada:

```bash
cd /opt/sei-ia
make down
make up
make check
```

`make down` preserva os dados. `make down-volumes` remove volumes Compose e não faz
parte da operação normal nem de um upgrade.

Não use `docker-compose.debug.yml` na instalação padrão. Ele publica PostgreSQL,
Solr, Redis e LiteLLM somente no loopback do host e existe apenas para diagnóstico
local controlado.

## 6. Configuração da confiança TLS no SEI

O certificado ou a CA que assina o gateway precisa estar no nó onde o PHP do SEI
executa. Esta instalação não altera automaticamente o truststore do SEI: o órgão
deve instalar a confiança conforme seu sistema operacional e seu modelo de deploy.

### 6.1. SEI e SEI IA no mesmo host Docker

Declare `docker-host-bridge` como rede externa também no Compose do SEI e conecte o
serviço PHP/HTTP do SEI a ela. Exemplo de override a adaptar ao nome real do serviço:

```yaml
services:
  httpd:
    networks:
      - default
      - seiia-runtime
    volumes:
      - /caminho/ca-bundle-confiavel.pem:/opt/sei/config/mod-ia/seiia.cert.pem:ro

networks:
  seiia-runtime:
    name: docker-host-bridge
    external: true
```

No campo `name`, use o valor efetivo de `COMPOSE_NETWORK_NAME` da stack SEI IA. O
exemplo mostra o valor padrão.

O alias Docker criado no gateway é o valor de `SEIIA_GATEWAY_HOST`. Confirme dentro
do contêiner do SEI:

```bash
getent hosts <SEIIA_GATEWAY_HOST>
curl --cacert /opt/sei/config/mod-ia/seiia.cert.pem \
  https://<SEIIA_GATEWAY_HOST>:8088/health
```

Para o certificado autoassinado gerado pela stack, a origem desse bind pode ser
`/opt/sei-ia/.runtime/certs/seiia.cert.pem`. Para certificado institucional, monte a
CA bundle aprovada pela PKI, não a chave privada e não obrigatoriamente o certificado
folha.

### 6.2. SEI e SEI IA em hosts diferentes

1. publique no DNS o FQDN de `SEIIA_GATEWAY_HOST` apontando para o host do SEI IA;
2. permita `8088/tcp`, `8082/tcp` e `8086/tcp` do servidor SEI até esse host;
3. copie somente o PEM autoassinado ou a CA bundle da PKI para cada nó PHP do SEI;
4. monte o arquivo, legível pelo PHP, em
   `/opt/sei/config/mod-ia/seiia.cert.pem`;
5. confirme resolução DNS, rota, SAN e relógio a partir do próprio nó do SEI.

Valide as três portas a partir do servidor ou contêiner do SEI:

```bash
for port in 8088 8082 8086; do
  curl --fail --silent --show-error \
    --cacert /opt/sei/config/mod-ia/seiia.cert.pem \
    "https://<SEIIA_GATEWAY_HOST>:${port}/health"
done
```

Cada resposta deve indicar sucesso. Não use `curl -k`: isso esconderia exatamente os
problemas de CA e hostname que o módulo precisa validar.

## 7. Mapeamento da integração no SEI

Antes de cadastrar as integrações, confirme que a Chave de Acesso foi gerada em
**Administração > Sistemas > Usuario_IA > Serviços >
consultarDocumentoExternoIA > Gerar Chave de Acesso** e copiada para
`SEI_API_DB_IDENTIFIER_SERVICE` no `security.env`. Sem essa chave, o Servidor de
Soluções de IA não consegue consultar os documentos do SEI.

Entre novamente no SEI com perfil administrador e abra
**Administração > Inteligência Artificial > Mapeamento das Integrações**.

Nos dois registros criados pelo módulo, a integração da solução de IA e a integração
da interface LLM, informe a mesma URL base:

```text
https://<SEIIA_GATEWAY_HOST>
```

Não inclua porta, barra final ou caminho. Mantenha os registros ativos e use a ação
de validação da tela. O Módulo SEI IA 1.5.0 já contém o mapeamento de operações
exigido por esta release; não altere manualmente as URLs individuais.

Conclua as demais parametrizações negociais descritas no README do módulo, incluindo
as permissões de perfil e as configurações do Assistente e da Similaridade. Para a
recomendação de documentos, configure ao menos um tipo de documento como alvo em
**Administração > Inteligência Artificial > Pesquisa de Documentos**.

Para ativar o Assistente, abra **Administração > Inteligência Artificial >
Assistente IA > Configurações do Assistente IA**, marque **Exibir** em **Exibir
Funcionalidade** e selecione **Salvar**.

## 8. Health Checker geral do ambiente

Com toda a stack em execução:

```bash
cd /opt/sei-ia
make check
```

O comando constrói e executa um checker efêmero, grava seus artefatos no volume de
logs e não derruba a stack. A instalação só é aceita quando ele termina com código
zero e **sem erros**. Avisos devem ser lidos e justificados; não considere uma
execução incompleta como aprovação.

| Seção do checker | O que valida | Resultado exigido |
|---|---|---|
| ENVS | inventário exato de `default.env` e `security.env`, duplicidades, valores obrigatórios e formatos | nenhuma variável ausente, extra, duplicada ou obrigatória vazia |
| CONECTIVIDADE | DNS, endpoints internos e serviços externos configurados | todos os destinos obrigatórios alcançáveis |
| ENDPOINTS | `/health` e contratos esperados das APIs | respostas válidas nas APIs do gateway e nos serviços internos |
| LITELLM PROXY | saúde do proxy e presença de `standard`, `mini`, `nano`, `embedding` e `speech-to-text` com suas oito tags `agents:*` | nenhum alias obrigatório ausente ou com papéis incompletos |
| CERTIFICADO | validade temporal e SAN do gateway | `SEIIA_GATEWAY_HOST` e nomes adicionais presentes no SAN |
| SOLR | autenticação e acesso aos cores | consultas de validação sem erro |
| BANCOS INTERNOS | conexão e tabelas do Assistente e Similaridade | tabelas obrigatórias acessíveis |
| DOCKER | containers, healthchecks, reinícios, OOM e erros recentes | serviços esperados saudáveis e sem erro não tratado |
| AIRFLOW | importação e listagem das DAGs | nenhuma falha de importação |

Os artefatos ficam no volume Docker `health_checker_logs`, sob `logs/<data>`. Para
localizar o ponto de montagem no host:

```bash
docker volume inspect sei-ia_health_checker_logs
```

O nome pode receber outro prefixo se o projeto Compose tiver sido deliberadamente
renomeado. Use o campo `Mountpoint` retornado pelo próprio Docker; não presuma o
caminho físico do volume.

## 9. Resolução de problemas conhecidos

| Sintoma | Causa provável | Verificação/correção |
|---|---|---|
| `network ... declared as external, but could not be found` | Rede externa não criada ou nome divergente | Compare `COMPOSE_NETWORK_NAME` com `docker network ls` e crie a rede correta. |
| Conflito de subnet ou serviço inacessível | Rede Docker sobreposta a LAN/VPN | Inspecione todas as subnets e recrie a rede com uma faixa aprovada pela equipe de rede. |
| `address already in use` | Porta 8088, 8082, 8086 ou 8081 ocupada | Identifique o processo com `ss -ltnp`; não publique os serviços internos como solução. |
| Falha de build por DNS/timeout | Host sem egress, proxy ou DNS para BuildKit | Valide resolução e HTTPS no host e no builder; configure o proxy corporativo antes de repetir. |
| `permission denied` em volume | UID/GID, proprietário ou SELinux incorretos | Compare `default.env`, `ls -ln` e os contextos SELinux; execute `make ensure-volumes` após corrigir a raiz. |
| Falha TLS por hostname | DNS usado pelo SEI não está no SAN | Corrija `SEIIA_GATEWAY_HOST`/certificado e valide com `openssl x509 -text`; não desative a verificação. |
| `unable to get local issuer certificate` | CA bundle ausente ou cadeia incorreta no SEI | Monte o PEM/CA correto em `/opt/sei/config/mod-ia/seiia.cert.pem`. |
| Certificado e chave não formam par | Arquivos de PKI trocados | Compare as chaves públicas e instale o par correto; o script não sobrescreve o material do órgão. |
| LiteLLM retorna 401/403 | Chave do proxy divergente | Confirme a mesma `LITELLM_PROXY_API_KEY` no contrato e recrie os serviços sem expor o valor. |
| Alias ou tag de modelo ausente | `litellm_config.yaml` alterado ou incompleto | Compare com o template da mesma tag e confira os cinco aliases e suas tags conforme a seção 3.1. |
| Airflow não inicializa | Credenciais/metastore ou migração falharam | Leia o log de `etl-airflow-init`; corrija a primeira falha antes de executar `make up` novamente. |
| Checker acusa variável extra/ausente | `security.env` veio de outra versão | Recrie-o a partir do `security_example.env` da mesma tag e transfira somente os valores correspondentes. |
| Assistente não aparece no SEI | Funcionalidade ainda não exibida | Em **Administração > Inteligência Artificial > Assistente IA > Configurações do Assistente IA**, marque **Exibir** em **Exibir Funcionalidade** e salve. |

Não use comandos globais de remoção de contêineres, volumes ou imagens. Eles podem
afetar outras aplicações do host e apagar evidências úteis para o diagnóstico.

## 10. Dimensionamento

Os limites versionados em `default.env` representam o ambiente de referência. Antes
de reduzi-los ou ampliá-los, some memória e CPU de todas as réplicas e preserve
margem para Docker, kernel, cache de arquivos, builds e picos do Solr.

| Componente | Variáveis principais | Observação |
|---|---|---|
| Solr | `SOLR_JAVA_MEM`, `SOLR_MEM_LIMIT`, `SOLR_CPU_LIMIT` | o limite do container deve ser maior que o heap Java |
| Airflow | `AIRFLOW_WORKERS_REPLICAS`, `AIRFLOW_WORKER_MEM_LIMIT`, `AIRFLOW_WORKER_CPU_LIMIT` | cada réplica multiplica o consumo configurado |
| PostgreSQL/pgvector | `PGVECTOR_MEM_LIMIT`, `PGVECTOR_CPU_LIMIT` | cresce com embeddings e volume documental |
| Assistente | `ASSISTENTE_MEM_LIMIT`, `ASSISTENTE_CPU_LIMIT` | considerar sessões simultâneas e processamento de anexos |
| Busca web | limites `SEARXNG_*`, `FASTCRW_*`, `LIGHTPANDA_*`, `CHROME_*`, `BYPARR_*` e `MARKER_*` | cada serviço deve caber no dimensionamento total da stack |

Não copie limites reduzidos de um laboratório para produção. O dimensionamento deve
ser proporcional ao acervo e à concorrência do órgão.

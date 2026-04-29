# Instalação do Servidor de Soluções de IA do módulo SEI IA

- Este guia descreve os procedimentos para instalação do *Servidor de Soluções de IA* do módulo SEI IA, em um ambiente Linux.
- É importante observar que este manual não tem como objetivo fornecer conhecimento sobre as tecnologias adotadas. Para isto recomendamos buscar fontes mais apropriadas.
- Para instalar o *Servidor de Soluções de IA do Módulo SEI IA* é mandatório ter o [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia) previamente instalado e configurado no SEI do ambiente correspondente. **Ou seja, antes, instale o módulo no SEI!**
- **Para atualização de versão**, seguir o [Guia de Atualização do Servidor de Soluções de IA do módulo SEI IA](UPGRADE.md).
- **ATENÇÃO:** O Servidor a ser instalado NÃO DEVE ser compartilhado com outras soluções.
- **ATENÇÃO:** Na seção [Health Checker Geral do Ambiente](#health-checker-geral-do-ambiente) temos um detalhamento de como usar os testes automatizados para validar a conformidade da instalação e configuração, nesta seção também orientamos como deve ser feita a leitura dos logs que indicarão eventuais erros e necessidades de ajustes para a total conformidade da instalação e configuração.

---
## Sumário

- [Instalação do Servidor de Soluções de IA do módulo SEI IA](#instalação-do-servidor-de-soluções-de-ia-do-módulo-sei-ia)
  - [Pré-requisitos](#pré-requisitos)
  - [Passos para Instalação](#passos-para-instalação)
  - [Health Checker Geral do Ambiente](#health-checker-geral-do-ambiente)
  - [Testes de Acessos](#testes-de-acessos)
  - [Configuração do Certificado HTTPS no SEI](#configuração-do-certificado-https-no-sei)
  - [Mapeamento da Integração no SEI](#mapeamento-da-integração-no-sei)
  - [Resolução de Problemas Conhecidos](#resolução-de-problemas-conhecidos)
  - [Pontos de Atenção para Escalabilidade](#pontos-de-atenção-para-escalabilidade)
  - [Backup periódico dos dados do Servidor de Soluções de IA](#backup-periódico-dos-dados-do-servidor-de-soluções-de-ia)
  - [Guia de utilização de certificado SSL proprietário](#guia-de-utilização-de-certificado-ssl-proprietário)
  - [Anexos](#anexos)

## Pré-requisitos

Os pré-requisitos aqui apresentados foram testados no ambiente da Anatel, considerando os dados e a carga de trabalho da Anatel. Outras configurações de alocação de recursos podem ser avaliadas por pessoas devidamente capacitadas.

- **CPU**:
  - Provisionado: 16 Cores com 2.10GHz
  - Consumo na ANATEL (Produção):
    - médio: 60%
    - máximo: 100%

- **Memória**:
  - Provisionado: 128GB
  - Consumo na ANATEL (Produção):
    - mínimo: 64GB
    - máximo: 115GB

- **Espaço em Disco**:
  - Provisionado: 450GB.
  - Consumo na ANATEL (Produção):
      | Aplicação  | Caminho                                          | Tamanho em disco |
      |------------|--------------------------------------------------|------------------|
      | Solr       | /var/lib/docker/volumes/sei_ia_solr-db-volume    | 100 GB           |
      | PostgreSQL | /var/lib/docker/volumes/sei_ia_pgvector-db-volume-all | 300 GB      |
      | Docker     | /var/lib/docker/                                 | 50 GB            |

- **ATENÇÃO**: As informações acima sobre **"Consumo na ANATEL (Produção)"**, em 04/11/2024, possuem como contexto os números abaixo do SEI de Produção na Agência:
  - **Quantidade de Processos**: 1.5 milhão
  - **Quantidade de Documentos Gerados** (Editor do SEI - salvos no banco): 4.2 milhões
  - **Quantidade de Documentos Externos** (Filesystem do SEI): 8 milhões
  - **Usuários Internos**: cerca de 1.800, dentre servidores públicos e colaboradores em geral
> **Realidade de Cada Órgão**:
>  - A partir dos dados acima, cada órgão deve avaliar o ambiente do SEI e prever recursos proporcionais, especialmente sobre o Solr e o PostgreSQL, pois essas duas aplicações na arquitetura apresentam crescimento diretamente proporcional ao volume de documentos existentes no ambiente do SEI.
> - Ao final deste Manual são fornecidas algumas dicas de escalabilidade para ajustar o sistema conforme a demanda.

### Configurações na Rede Local do Órgão

Para garantir a comunicação entre os serviços do *Servidor de Soluções de IA* e o SEI, são necessárias as seguintes permissões de conexões de rede:

1. **Do Servidor de Soluções de IA para o SEI**:
   - **HTTP do SEI**: Permissão de acesso ao host e porta do SEI, para permitir acesso ao Webservice do Módulo SEI IA (p. ex., 192.168.2.17:8000).

2. **Do servidor do SEI para o Servidor de Soluções de IA**:
   - **Portas Necessárias**:
      - **Airflow**: Porta 8081
        - Também pode ser liberada a conexão para o Administrador do ambiente computacional do SEI, para ter acesso às DAGS das tasks de toda a arquitetura de Soluções de IA.
      - **API SEI IA**: Porta 8082
      - **API SEI IA Feedback**: Porta 8086
      - **API SEI IA Assistente**: Porta 8088

As configurações de rede acima são mandatórias para o funcionamento correto dos sub-módulos de recomendação de processos/documentos e do Assistente.

**ATENÇÃO**: Se as configurações de conexões na rede local do órgão não forem efetivadas, conforme acima, antes dos "Passos para Instalação", abaixo, e não for garantido que estão funcionando adequadamente, poderá ter problemas no meio do deploy do servidor ou durante o funcionamento de algumas das aplicações. Assim que criadas as conexões indicadas, é importante testá-las a partir do servidor correspondente, antes de seguir para os "Passos para Instalação". Seguir para a instalação somente depois que confirmar que as conexões em ambos os sentidos estiverem efetivamente funcionando.

## Passos para Instalação

Antes de começar a instalação, certifique-se de que os seguintes pacotes estejam instalados no Linux do servidor:
- Docker Engine (versão >= 27.1.1).
- Docker Compose (versão >= 2.29).

Caso não estejam instalados, consulte o pequeno tutorial de instalação do Docker na seção de [Anexos](#anexos) deste Manual.
- Também é possível seguir a documentação oficial do Docker para a instalação do [Docker Engine](https://docs.docker.com/engine/install/) e do [Docker Compose](https://docs.docker.com/compose/install/), desde que observados os requisitos de compatibilidade com as versões docker e docker compose homologadas para o SEI IA.

> **Observação**:
> - Todos os comandos ilustrados neste Manual são exemplos de comandos executados via terminal/console/CLI.

1. **Criar o usuário:**

```bash
sudo useradd -m -s /bin/bash -u 4000 seiia
```

Atualize a senha do usuario com o comando

```bash
sudo passwd seiia
```

2. **Adicionar o usuário ao grupo docker:**

```bash
sudo usermod -aG docker seiia
```

3. **Adicionar o usuário ao grupo root:**

Nesse caso deve-se atentar ao sistema operacional usado.

**Debian/Ubuntu**

```bash
sudo usermod -aG sudo seiia
```

**RHEL/CentOS/Fedora**

```bash
sudo usermod -aG wheel seiia
```

4. **Criar as pastas necessárias:**

```bash
sudo mkdir -p /var/seiia/volumes
```

> Esse caminho é o valor padrão de `VOL_SEIIA_DIR` em `default.env`. Se for alterar, ajuste também `default.env` antes de subir a stack.

5. **Corrigir as permissoes de pastas:**

```bash
sudo chown -R seiia:docker /var/seiia/volumes
```

6. **Acessar o usuario:**

Antes de iniciar a instalação tenha certeza de que está no usuário correto.

```bash
su seiia
```

7. **Iniciar o Docker:**

   Inicie o serviço do Docker.

   ```bash
   sudo systemctl start docker
   docker --version # deve aparecer algo como Docker version 27.2.0, build 3ab4256
   ```

8. **Criar a rede Docker**

   O Docker utiliza como default a faixa de IP `172.17.*.*`, que pode ser utilizada internamente por uma organização e causar conflitos. Desta forma, se faz necessária a utilização de uma faixa de IPs dedicadas para os containers Docker rodando no Servidor, com objetivo de evitar erros de roteamento causados pela sobreposição de endereços IP.

   A restrição da subnet deve ser feita através da criação de *user defined bridge network*. Também deve remover a default bridge, como forma de evitar o uso de uma bridge fora da subnet, dado que novos containers adotam a default bridge por padrão se uma rede não for especificada e se a default bridge estiver disponível.

   Para os seguintes procedimentos, é necessário assegurar que o Docker está instalado e parado.

   ```bash
   sudo systemctl stop docker
   ```

   A remoção da default bridge é feita através de uma configuração do daemon.json, através de:

   ```bash
   sudo vim /etc/docker/daemon.json
   ```

   Deve ser configurado o daemon.json com o seguinte conteúdo:

   ```bash
   {
        "bridge": "none"
   }
   ```

   Após a configuração é necessário inicializar o Docker e verificar o resultado obtido:

   ```bash
   sudo systemctl start docker
   docker network ls
   ```

   O resultado deve exibir uma lista de docker networks, sem a presença da bridge, conforme abaixo:

   ```bash
   NETWORK ID     NAME                 DRIVER    SCOPE
   7cee8287f256   host                 host      local
   0355f600e1d7   none                 null      local
   ```

   O próximo passo é a criação da *user defined bridge network* com a definição da subnet e gateway em conformidade com a política de endereçamento do órgão.

   **Como descobrir uma faixa segura para usar:**

   1. **Pergunte à equipe de redes do órgão** qual sub-rede privada está livre para uso interno do servidor, e peça também o gateway. Esse é o caminho mais seguro.
   2. Se você precisa decidir sozinho, liste o que já está em uso no host:

      ```bash
      # Rotas configuradas no host (rede local que o host conhece)
      ip route

      # Sub-redes de outras redes Docker já existentes
      docker network ls -q | xargs -r docker network inspect \
        --format '{{.Name}}: {{range .IPAM.Config}}{{.Subnet}} {{end}}'
      ```

      Escolha uma `/24` em RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) **fora** do que aparecer nas saídas acima e que não conflite com a rede corporativa.

   Anote três valores e use no comando abaixo:
   - `<SUBNET>`  — sua sub-rede em CIDR (ex.: `10.90.0.0/24`)
   - `<IP_RANGE>` — geralmente igual a `<SUBNET>`
   - `<GATEWAY>` — primeiro IP da sub-rede (ex.: `10.90.0.1`)

   ```bash
   docker network create --driver=bridge --subnet=<SUBNET> --ip-range=<IP_RANGE> --gateway=<GATEWAY> docker-host-bridge
   ```

   É mandatório que os valores de *--subnet*, *--ip-range* e *--gateway* sejam adequadamente definidos pelo órgão. Errar a sub-rede causa um problema difícil de diagnosticar — o servidor SEI IA fica isolado da rede do órgão (incluindo o próprio SEI). **Confirme antes de criar.**

   O nome da rede (`docker-host-bridge`) **deve permanecer** é o valor de `COMPOSE_NETWORK_NAME` em `default.env` e é também usado pelo builder do Docker (passo 11).

9. **Clonar o repositório dos códigos-fonte do *Servidor de Soluções de IA***

  > **Observação**:
  > - Aqui consta apenas um exemplo, fazendo o clone direto de Tag de Release estável do projeto no GitHub para o Servidor. Trocar no comando de exemplo abaixo do `git clone` o trecho `[identificacao_release_estavel]` pela identificação correta da Release estável de interesse, constante na [página de Releases do projeto](https://github.com/anatelgovbr/sei-ia/releases), por exemplo, `v1.0.0`, `v1.0.1`, `v1.2.0` etc.
> - Contudo, caso o órgão possua procedimentos e ferramentas de deploy próprias para seu ambiente computacional, como GitLab e Jenkins, deve adaptar esse passo aos seus próprios procedimentos.
> - Alternativamente, é possível fazer o download direto da release e utilizar os seguintes comandos para configuração:
> ```bash
> # Coloque o arquivo da release no diretório /opt/sei-ia
> cd /opt/sei-ia
> unzip sei-ia-v.1.0.0.zip . # O nome do arquivo pode mudar. ATENÇÃO: para subir o arquivo zip antes no servidor.
> ```
>   - **Atenção:** mantenha a estrutura de código deste projeto no GitHub dentro da pasta **/opt/sei-ia**.
>   - Enquanto o projeto estiver privado no github, para realizar o clone é necessário utilizar as credenciais do usuário do GitHub que possua acesso autorizado no repositório.

   Instale o Git, seguindo os passos da [documentação oficial](https://git-scm.com/downloads/linux) ou da seção de [Anexos deste Manual](#anexos) que orienta a instalar o Git no Servidor.

   ```bash
   git clone --branch [identificacao_release_estavel] --single-branch git@github.com:anatelgovbr/sei-ia.git
   cd sei-ia
   ```

> **Observação**
> Para clonar o repositório com um usuário específico, enquanto o repositório está privado no GitHub, substitua `USERNAME` pelo usuário autorizado:
> ```bash
> git clone --branch [identificacao_release_estavel] --single-branch https://USERNAME@github.com/anatelgovbr/sei-ia.git
> cd sei-ia
> ```
> - Assim que for dado o comando acima, será apresentada linhas de comando solicitando as credenciais de acesso no GitHub do usuário informado, conforme suas configurações pessoais no cadastro dele no GitHub.


10. **Configuração do Arquivo security.env**

O arquivo `security.env`, na raiz do projeto, contém as variáveis de configuração necessárias para o ambiente do Servidor de Soluções de IA do módulo SEI IA.

> **Mudança em relação a versões anteriores**: a partir da estrutura monorepo, existe **um único** `security.env` na raiz, no lugar dos antigos `env_files/{security,dev,homol,prod}.env`.

O repositório disponibiliza um arquivo de exemplo em `security_example.env`. Para realizar a configuração, crie uma cópia desse arquivo e utilize-a como base para o arquivo final de configuração:

```bash
cp security_example.env security.env
chmod 600 security.env
```

> ⚠️ Atenção: o arquivo `security.env` contém informações sensíveis.
> Não versionar este arquivo em repositórios públicos e restrinja as permissões de acesso no servidor.

As tabelas abaixo foram organizadas com base no novo arquivo `security.env`.


### Ambiente

| Variável              | Descrição | Exemplo |
|-----------------------|-----------|---------|
| `GID_DOCKER`         | O GID (Group ID) do grupo Docker no host do ambiente de instalação. Deve ser obtido executando o comando: <code>cat /etc/group &#124; grep ^docker: &#124; cut -d: -f3</code> | 983 |
| `ENVIRONMENT`        | Indicativo do tipo de ambiente de instalação. Para usuários externos, manter sempre como "prod". Opções disponíveis: dev, homol, prod. | `prod` |

### Banco de Dados da Aplicação SEI IA

| Variável        | Descrição | Exemplo |
|----------------|-----------|---------|
| `DB_SEIIA_USER` | Usuário de acesso ao banco de dados PostgreSQL interno do Servidor de IA. | `seiia_user` |
| `DB_SEIIA_PWD`  | Senha do usuário de banco a ser criado. **Não deve conter**: "`'`" (aspas simples), "`"`" (aspas duplas), "`\`", "` `" (espaço), "`$`", "`(`", "`)`", "`:`", "`@`", "`;`", "`` ` ``" (crase), "`&`", "`*`", "`+`" (mais), "`-`" (menos), "`=`", "`/`", "`?`", "`!`", "`[`", "`]`", "`{`", "`}`", "`<`", "`>`", "`\|`", "`%`", "`^`", "`~`".                   | `iJI_YTuygb`                 |

### Solr da Aplicação SEI IA

| Variável       | Descrição | Exemplo |
|---------------|-----------|---------|
| `SOLR_USER`   | Usuário de acesso ao Solr SEI IA. | `seiia` |
| `SOLR_PASSWORD` | Senha do usuário de acesso ao Solr SEI IA. | `solr_password` |

### Airflow

| Variável                     | Descrição | Exemplo |
|------------------------------|-----------|---------|
| `_AIRFLOW_WWW_USER_USERNAME` | Usuário para acesso à UI do Airflow. Não alterar. | `seiia` |
| `_AIRFLOW_WWW_USER_PASSWORD` | Senha para acesso à UI do Airflow. Não alterar. | `seiia` |
| `AIRFLOW_POSTGRES_USER` | Usuário de acesso ao PostgreSQL do Airflow. Não alterar. | `seiia` |
| `AIRFLOW_POSTGRES_PASSWORD` | Senha para acesso ao PostgreSQL do Airflow. Não alterar. | `seiia` |
| `AIRFLOW_AMQP_USER` | Usuário para acesso ao RabbitMQ do Airflow. Não alterar. | `seiia` |
| `AIRFLOW_AMQP_PASSWORD` | Senha para acesso ao RabbitMQ do Airflow. Não alterar. | `seiia` |
| `AIRFLOW__WEBSERVER__SECRET_KEY` | Chave secreta para assinatura de sessões do webserver do Airflow. **Gerada automaticamente pelo script de deploy** caso não esteja definida em `security.env`. | *(auto-gerada)* |

#### Configuração de Modelos LLM - LiteLLM Proxy

**A partir da versão 1.2, o SEI IA usa o LiteLLM Proxy para gerenciar conexões com Azure OpenAI.**

O LiteLLM Proxy centraliza a configuração de todos os modelos de IA em um único arquivo YAML. As chaves de API e endpoints do Azure OpenAI são configurados diretamente neste arquivo.

##### Obter informações do Azure OpenAI

Antes de configurar, obtenha as seguintes informações do Azure Portal para cada modelo:

1. **Acesse o Azure Portal**: https://portal.azure.com
2. **Navegue até Azure OpenAI**: Busque por "Azure OpenAI" nos recursos
3. **Selecione seu recurso**: Clique no recurso Azure OpenAI
4. **Obtenha o Endpoint e API Key**:
   - Vá em "Keys and Endpoint"
   - Copie o **Endpoint** (ex: https://meurecurso.openai.azure.com)
   - Copie a **API Key** (KEY 1 ou KEY 2)
5. **Obtenha o nome do Deployment**:
   - Vá em "Model deployments" > "Manage Deployments"
   - No Azure OpenAI Studio, vá em "Deployments"
   - Anote o **nome exato** de cada deployment

Você precisará destas informações para **cada modelo** que for usar (standard, mini, think, embedding).

##### Configurar o arquivo `litellm_config.yaml`

O repositório disponibiliza um arquivo de exemplo em `litellm_config.template.yaml`, na raiz do projeto. Para realizar a configuração, crie uma cópia desse arquivo e utilize-a como base para o arquivo final de configuração:

```bash
cp litellm_config.template.yaml litellm_config.yaml
chmod 600 litellm_config.yaml
```

> ⚠️ Atenção: o arquivo `litellm_config.yaml` contém informações sensíveis.
> Não versionar este arquivo em repositórios públicos e restrinja as permissões de acesso no servidor.

Em seguida, edite o arquivo `litellm_config.yaml` e preencha as informações necessárias para integração com o Azure OpenAI, como:

```yaml
model_list:
  # Modelo Standard - Modelo principal para respostas do assistente
  - model_name: standard
    litellm_params:
      model: azure/gpt-4.1                              # Nome do deployment no Azure
      api_base: https://seu-endpoint.openai.azure.com   # Endpoint do Azure
      api_key: sua-api-key-standard                     # API Key do Azure
      api_version: "2025-03-01-preview"
      max_completion_tokens: 32768

  # Modelo Mini - Modelo econômico para tarefas mais simples
  - model_name: mini
    litellm_params:
      model: azure/gpt-4.1-mini
      api_base: https://seu-endpoint.openai.azure.com
      api_key: sua-api-key-mini
      api_version: "2025-03-01-preview"
      max_completion_tokens: 32768

  # Modelo Think - Modelo com raciocínio avançado (GPT-5)
  - model_name: think
    litellm_params:
      model: azure/gpt-5.2
      api_base: https://seu-endpoint-think.openai.azure.com
      api_key: sua-api-key-think
      api_version: "2025-03-01-preview"
      max_completion_tokens: 102400
      reasoning_effort: "medium"                        # Apenas para GPT-5

  # Modelo Embedding - Para geração de embeddings (RAG)
  - model_name: embedding
    litellm_params:
      model: azure/text-embedding-3-small
      api_base: https://seu-endpoint-embedding.openai.azure.com
      api_key: sua-api-key-embedding
      api_version: "2025-03-01-preview"
```

**Observações importantes:**

- O campo model: deve seguir o formato azure/<nome-do-deployment>, utilizando exatamente o nome configurado no Azure OpenAI Studio.
- O parâmetro reasoning_effort é exclusivo dos modelos GPT-5 (think) e não deve ser utilizado com modelos GPT-4.1.
- Cada modelo pode estar associado a endpoints diferentes, conforme os recursos configurados no Azure.
- Utilize a versão de API 2025-03-01-preview para todos os modelos (GPT-4.1, GPT-5 e embeddings).
  - Versão da API vs. modelo (Azure OpenAI): a variável api_version define o contrato da API e deve permanecer inalterada, pois não está vinculada à versão do modelo. Alterá-la pode causar incompatibilidades. Já a versão do modelo deve ser mantida sempre atualizada, preferencialmente com atualização automática habilitada.
- Modelo Think – modelo com raciocínio avançado (GPT-5): modelos da família gpt-5.x podem não estar disponíveis por padrão no Azure OpenAI. É necessário solicitar liberação para a assinatura no portal do Azure antes de criar o endpoint correspondente.

**Exemplo prático:**

Se no Azure você configurou:
- Recurso: "minha-org-openai"
- Endpoint: `https://minha-org-openai.openai.azure.com`
- Deployment do modelo gpt-4.1 com nome: `gpt-4-deployment`
- API Key: `abc123xyz456`

Configure assim:
```yaml
- model_name: standard
  litellm_params:
    model: azure/gpt-4-deployment                          # Nome do deployment
    api_base: https://minha-org-openai.openai.azure.com    # Endpoint
    api_key: abc123xyz456                                   # API Key
    api_version: "2025-03-01-preview"
    max_completion_tokens: 32768
```

##### Variáveis do security.env


O arquivo `security.env` já possui valores padrão configurados. As principais variáveis relacionadas ao LiteLLM Proxy são:

| Variável | Descrição | Valor Padrão |
|----------|-----------|--------------|
| `ASSISTENTE_LITELLM_PROXY_URL` | URL do proxy no Docker | `http://litellm:4000` |
| `ASSISTENTE_LITELLM_PROXY_API_KEY` | API Key do proxy (vazio se sem auth) | *(vazio)* |
| `ASSISTENTE_EMBEDDING_MODEL` | Modelo de embeddings | `text-embedding-3-small` |
| `ASSISTENTE_EMBEDDING_ENCODING_NAME` | Encoding tiktoken para tokenização (**não alterar se já possui base de dados**) | `o200k_base` |
| `ASSISTENTE_DEFAULT_RESPONSE_MODEL` | Modelo padrão | `standard` |

**Importante sobre `EMBEDDING_ENCODING_NAME`:**
- Este parâmetro define qual encoding (tokenizador) será usado para dividir os documentos em chunks antes de gerar embeddings
- **Se você já possui uma base de dados de embeddings criada**, NÃO altere este valor, pois mudá-lo tornará os novos embeddings incompatíveis com os existentes
- Para instalações novas, pode usar `o200k_base` (padrão) ou `cl100k_base`

##### Verificar a configuração

Após editar o `litellm_config.yaml`, reinicie o container e verifique a saúde dos modelos:

```bash
# Verificar saúde dos modelos (requer jq instalado)
curl -s http://localhost:4000/health | jq '{
  status: (if .unhealthy_count == 0 then "healthy" else "unhealthy" end),
  healthy_count: .healthy_count,
  unhealthy_count: .unhealthy_count,
  models: [.healthy_endpoints[].model] | unique
}'
```

**Saída esperada:**
```json
{
  "status": "healthy",
  "healthy_count": 5,
  "unhealthy_count": 0,
  "models": [
    "azure/gpt-4.1",
    "azure/gpt-4.1-mini",
    "azure/gpt-5.2",
    "azure/text-embedding-3-small"
  ]
}
```

> **Nota:** Se não tiver o `jq` instalado, pode usar `curl http://localhost:4000/health` diretamente. A saída será mais verbosa mas conterá as mesmas informações em `healthy_endpoints` e `unhealthy_endpoints`.

**Se algum modelo aparecer como "unhealthy" ou em `unhealthy_endpoints`, verifique:**
- API Key está correta
- Endpoint está acessível e corresponde ao recurso Azure
- Nome do deployment corresponde ao configurado em `model:` (ex: `azure/gpt-4.1`)
- Parâmetros específicos do modelo (ex: `reasoning_effort` só é válido para GPT-5)

#### WsIa (API REST CENTRAL DE INTEGRAÇÃO COM OS DADOS DO SEI)

| Variável             | Descrição                                                                              | Exemplo |
|----------------------|----------------------------------------------------------------------------------------|---------|
| `SEI_ADDRESS`        | Endereço raiz do SEI.                                                                   | http://www.sei.gov.br |
| `SEI_API_DB_IDENTIFIER_SERVICE`   | Chave de Acesso que deve ser gerada na Administração do SEI, pelo menu Administração > Sistemas > "Usuario_IA" > Serviços > "consultarDocumentoExternoIA".                |         |
| `SEI_API_DB_TIMEOUT` | Timeout padrão da conexão da aplicação SEI IA junto à API do SEI de integração dos dados do SEI.  | 120     |
| `SEI_API_DB_USER` | SiglaSistema criado automaticamente pelo script de instalação do Módulo SEI IA. Não alterar.  | `Usuario_IA` |

### Integração com WebSearch (Bing) - Opcional

A integração com WebSearch (Bing Grounding) permite que o Assistente utilize informações externas (internet) para complementar respostas.

> **ATENÇÃO**:
> - Esta funcionalidade é **opcional**
> - Caso não seja configurada, o sistema continuará funcionando normalmente
> - Para desabilitar completamente, basta não configurar as variáveis abaixo e desativar a opção de WebSearch na Administração do SEI

#### Variáveis de Ambiente - WebSearch

| Variável | Descrição |
|----------|----------|
| `PROJECT_ENDPOINT` | Endpoint do projeto no Azure AI Foundry |
| `AZURE_TENANT_ID` | Identificador do tenant no Entra ID |
| `AZURE_SUBSCRIPTION_ID` | Identificador da assinatura Azure |
| `AZURE_CLIENT_ID` | Client ID do App registrado no Entra ID |
| `AZURE_CLIENT_SECRET` | Client Secret do App registrado no Entra ID |
| `AGENT_ID` | Identificador do Agent configurado no Azure AI Foundry |
| `AZURE_WEB_AGENT_ID` | Identificador do Agent com WebSearch habilitado |
| `BING_CONNECTION_NAME` | Nome da conexão com o Bing Grounding |
| `MODEL_DEPLOYMENT_NAME` | Nome do deployment do modelo no Azure |

#### Configuração Básica

Para utilização do WebSearch, é necessário:

1. Criar um registro de aplicativo no Entra ID para autenticação
2. Criar um projeto no Azure AI Foundry
3. Provisionar o recurso de Bing Grounding Search
4. Configurar um Agent no projeto
5. Criar uma conexão com o recurso de Bing Grounding  
   - Observação: a associação do Agent com o Bing Grounding está disponível apenas para modelos compatíveis (ex: GPT-4.1)
6. Associar a conexão ao Agent
7. Preencher as variáveis no arquivo `security.env`

#### Observações

- Caso as variáveis não sejam informadas:
  - O Assistente continuará funcionando normalmente
  - Apenas não realizará consultas externas, e essa funcionalidade deverá ser desabilitada na Administração do SEI
- Recomenda-se validar:
  - Permissões do aplicativo no Entra ID
  - Existência da conexão com Bing Grounding
  - Associação correta entre Agent e Connection
- Em ambientes com restrição de acesso à internet, recomenda-se manter o WebSearch desabilitado

11. **Preparar o builder do Docker (Buildx + DNS)**

   Em redes corporativas/governamentais o BuildKit do Docker tenta usar DNS públicos (`8.8.8.8`) por padrão, que costumam ser bloqueados. Sem o passo abaixo, comandos `RUN apt-get update`/`RUN dnf install` dentro do build falham com `Temporary failure in name resolution`.

   O repositório já traz a solução:

   ```bash
   cd /opt/sei-ia
   bash .gitlab/scripts/ensure_buildx_builder.sh
   ```

   O script cria (ou reutiliza) o builder `seiia-bridge`, que roda dentro da rede `docker-host-bridge` e usa o `buildkitd.toml` do projeto para fixar nameservers internos. Se sua rede exige DNS específicos, edite `.gitlab/buildkit/buildkitd.toml` antes de rodar o script.

   > **Pré-requisito**: `docker buildx` instalado. Se `docker buildx version` falhar, veja a seção [Anexos](#anexos) deste manual ou a documentação oficial em <https://github.com/docker/buildx>.

12. **Executar o deploy**
 > **ATENÇÃO**:
 > - Para instalar o *Servidor de Soluções de IA do Módulo SEI IA* é mandatório ter o [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia) previamente instalado e configurado no SEI do ambiente correspondente. **Ou seja, antes, instale o módulo no SEI!**
 > - A funcionalidade de "Pesquisa de Documentos" (recomendação de documentos similares) somente funcionará depois que configurar pelo menos um Tipo de Documento como Alvo da Pesquisa no menu Administração > Inteligência Artificial > Pesquisa de Documentos (na seção "Tipos de Documentos Alvo da Pesquisa").

  Vamos criar o diretório que será utilizado como `volume bind`.
  ***IMPORTANTE*** : o usuário deve ter permissão sudo para criar o volume em `/var`.
  ```bash
  source default.env
  sudo mkdir --parents --mode=750 $VOL_SEIIA_DIR && sudo chown seiia:docker $VOL_SEIIA_DIR
  ```

  Executar o deploy com o usuário seiia:
  ```bash
  su seiia
  cd /opt/sei-ia
  make up
  ```

   `make up` valida os volumes, executa o build local das imagens (a partir do código em `aplicacoes/`) e sobe os containers. **A primeira execução pode levar 20–40 minutos**, pois envolve download das imagens base e build de todas as aplicações. Logo, é necessária **autorização para o servidor acessar o Docker Hub e o GitHub**.

   > **Alternativa — usar imagens pré-publicadas (sem build local)**: se o órgão prefere não buildar, é possível subir a stack apontando para imagens publicadas no GitHub Container Registry (`ghcr.io/anatelgovbr/...:<tag>`). Nesse caso, crie um override `docker-compose.images.yml` com `build: !reset null` e `image: ghcr.io/...:<tag>` para cada serviço, e suba com `docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.images.yml up -d`. A lista oficial de tags fica na [página de Releases do projeto](https://github.com/anatelgovbr/sei-ia/releases).

   Resultado da finalização do deploy:

   ![Resultado após deploy finalizado](image/deploy_finalizado.png)

Nas seções a seguir são apresentados os procedimentos para **validar a instalação e a configuração do Servidor de IA**, bem como para **interpretar o estado de saúde dos serviços executados**.

A validação deve ser realizada por meio do mecanismo de *Health Checker*. Para instruções detalhadas sobre os testes disponíveis, interpretação dos resultados e localização dos logs gerados, consulte o documento [Health Checker Geral do Ambiente](#health-checker-geral-do-ambiente).

## Health Checker Geral do Ambiente

O Health Checker é executado pelo comando `make check` após o deploy. Ele faz uma checagem geral de conexões, mapeamento e problemas comuns.

1. **Estrutura do Log**
   Os logs seguem a seguinte estrutura:
   - **Timestamp:** Data e hora do evento.
   - **Nível de severidade:**
     - **INFO:** Informações gerais e mensagens de sucesso.
     - **WARNING:** Avisos de possíveis problemas ou inconsistências.
     - **ERROR:** Erros que requerem atenção imediata.
     - **Mensagem:** Detalhes do evento ou do problema detectado.

### Explicação dos Logs por Seção

#### 1. **Testes**

##### 1.1 **ENVS**
- **Descrição:** Esta seção descreve variáveis de ambiente encontradas em arquivos `.env`.
- **Objetivo:** Verificar se todas as variáveis necessárias estão presentes e com valores corretos.
- **Tipos de Mensagens Comuns:**
  - **Variáveis Sobrando:** Variáveis que estão definidas mas não são utilizadas pelo sistema.
  - **Variáveis Duplicadas:** Variáveis que aparecem mais de uma vez, podendo causar conflitos.
  - **Variáveis Vazias ou Inválidas:** Variáveis sem valor ou com valores incorretos.

##### 1.2 **CONECTIVIDADE**

###### 1.2.1 **TESTE DE CONECTIVIDADE - RESUMO**
- **Descrição:** Verifica a disponibilidade e acessibilidade de endpoints ou serviços externos.
- **Objetivo:** Confirmar se os sistemas externos estão acessíveis.
- **Mensagens Comuns:**
  - **Falha de Conexão:** O sistema não conseguiu acessar o serviço especificado.
  - **Tempo de Resposta Alto:** O serviço respondeu lentamente, sugerindo um possível problema de desempenho.

###### 1.2.2 **TESTE DE SAÚDE DOS ENDPOINTS**
- **Descrição:** Realiza uma verificação do status (saúde) de endpoints críticos da aplicação.
- **Objetivo:** Confirmar que os endpoints principais estão funcionando corretamente.
- **Mensagens Comuns:**
  - **Serviço Indisponível:** O endpoint não respondeu conforme esperado.
  - **Falha ao Testar:** Testes não puderam ser realizados devido a erro de configuração ou conectividade.

###### 1.2.3 **TESTE DE CONEXÃO COM SOLR do SEI IA**
- **Descrição:** Verifica a conectividade com o servidor SOLR IA, utilizado para busca e indexação de dados.
- **Objetivo:** Garantir que a aplicação consiga se comunicar corretamente com o servidor SOLR.
- **Mensagens Comuns:**
  - **Falha de Conexão:** Erro ao tentar conectar ao SOLR.
  - **Configuração de Endpoint Inválida:** A URL ou as credenciais de conexão podem estar incorretas.

##### 1.3 **TESTE DE CONEXÃO COM BANCO DE DADOS**


###### 1.3.2 **INTERNOS**

**1.3.2.1 TABELAS DO ASSISTENTE**
- **Descrição:** Verifica a conexão e o estado das tabelas do banco de dados utilizadas pelo Assistente Virtual.
- **Objetivo:** Garantir que o sistema do Assistente Virtual tenha acesso adequado ao banco de dados interno.
- **Mensagens Comuns:**
  - **Tabela Inexistente:** Falta de tabelas necessárias para o funcionamento do Assistente.
  - **Erro de Consulta:** Falhas em queries ou na execução de operações SQL.

**1.3.2.2 TABELAS DE SIMILARIDADE**
- **Descrição:** Verifica a integridade e acessibilidade das tabelas usadas para comparação de dados (por exemplo, comparação de documentos ou consultas de similaridade).
- **Objetivo:** Assegurar que as operações de comparação de dados funcionem corretamente.
- **Mensagens Comuns:**
  - **Falha ao Buscar Dados:** Erros ao tentar recuperar dados das tabelas de similaridade.
  - **Desempenho Baixo:** Consultas muito lentas ou com alta latência.

##### 1.4 **DOCKER**

###### 1.4.1 **DOCKER - LOGS**
- **Descrição:** Relata o estado dos containers Docker executando a aplicação.
- **Objetivo:** Verificar se todos os containers estão em funcionamento e sem problemas de saúde.
- **Mensagens Comuns:**
  - **Containers Parados:** Containers não estão em execução ou foram reiniciados inesperadamente.
  - **Falha de Saúde:** Containers com status `unhealthy` que indicam falhas internas.
  - **Reinicializações Frequentes:** Containers que estão reiniciando constantemente devido a falhas.

##### 1.5 **AIRFLOW**
- **Descrição:** Registra as execuções dos DAGs (Direcionadores de Fluxos de Trabalho) do Airflow, incluindo falhas de execução ou dependências não atendidas.
- **Objetivo:** Garantir que as tarefas programadas no Airflow sejam executadas corretamente.
- **Mensagens Comuns:**
  - **Falhas de Tarefa:** Tarefas que não foram executadas ou falharam durante a execução.
  - **Dependências Não Satisfeitas:** Problemas ao tentar executar tarefas devido a dependências não resolvidas.

##### 1.6 **RESUMO - TESTES**
- **Descrição:** Apresenta um resumo geral de todos os testes realizados, destacando falhas críticas e informações importantes.
- **Objetivo:** Facilitar a visão geral dos resultados dos testes, indicando onde ações corretivas são necessárias.
- **Mensagens Comuns:**
  - **Falhas Identificadas:** Relatórios com falhas graves, como falta de conectividade ou erros de autenticação.
  - **Testes Bem-Sucedidos:** Indicação de que todas as verificações foram realizadas com sucesso, e o sistema está em bom estado.

Caso deseje executar o Health Checker manualmente, execute o comando:
```bash
cd /opt/sei-ia
make check
```

Aguarde a finalização dos testes. Os logs estarão disponíveis, por padrão, em:
`/var/lib/docker/volumes/sei_ia_health_checker_logs/_data/logs/{DATA}`

Além disso, será gerado um arquivo `.zip` para facilitar a transmissão dos dados.

A compreensão do LOG deve iniciar pela criteriosa análise de:
`/var/lib/docker/volumes/sei_ia_health_checker_logs/_data/logs/{DATA}/tests_{DATA}.log`,
que tem sua estrutura descrita a seguir.

**Dica:** Os containers do Airflow podem emitir alguns erros e avisos devido a pequenas falhas momentâneas de comunicação entre eles, que podem ser ignorados.

> **Observação:**
> 1. Por questões de segurança, essa pasta, por padrão, não é acessível. É necessário entrar como `root` para ter acesso a esses arquivos.
> 2. Caso os arquivos não estejam nesse local, oriente-se pelo local de montagem dos seus volumes Docker com o comando:
>    ```bash
>    docker volume inspect sei_ia_health_checker_logs
>    ```
>    A saída deve ser algo como:
>    ```bash
>    [
>        {
>            "CreatedAt": "2024-12-05T00:20:58Z",
>            "Driver": "local",
>            "Labels": {
>                "com.docker.compose.project": "sei_ia",
>                "com.docker.compose.version": "2.29.2",
>                "com.docker.compose.volume": "health_checker_logs"
>            },
>            "Mountpoint": "/var/lib/docker/volumes/sei_ia_health_checker_logs/_data", <- LOCAL DO ARQUIVO
>            "Name": "sei_ia_health_checker_logs",
>            "Options": null,
>            "Scope": "local"
>        }
>    ]
>    ```

## Testes de Acessos

Você pode verificar o status das aplicações rodando o comando abaixo:

```bash
docker ps --format "table {{.Names}}	{{.Status}}"
```

O comando acima deverá retornar algo semelhante à imagem abaixo:

![Docker Status](image/docker_status.png)

* **Vale ressaltar que algumas aplicações podem levar até 5 minutos para atingir o status de "healthy".** Então, espere esse tempo e confira novamente.

Caso um longo tempo tenha se passado e ainda não tenha obtido o status **healthy**, favor seguir as orientações do [Health Checker](#health-checker-geral-do-ambiente) e rever os passos anteriores deste manual, até que não haja mais ERROR no log do Health Checker. Caso os erros persistam, deve ser repostado o problema para a Anatel, juntamente com o arquivo gerado pelo Health Checker.

Após a finalização do deploy, o Airflow iniciará a indexação dos documentos já existentes no SEI do ambiente correspondente. Esse processo pode levar dias para ser concluído, dependendo do volume de documentos a serem indexados e da capacidade computacional alocada para o servidor.

Se a instalação não for concluída com sucesso **e for exclusivamente a primeira instalação**, antes de realizar uma nova instalação é necessário realizar a limpeza completa do ambiente, para eliminar qualquer lixo que a instalação com erro possa deixar no ambiente.

Utilize os comando abaixo para a limpeza total do ambiente:

```bash
docker stop $(docker ps -a -q)
docker rm $(docker ps -a -q)
docker system prune -a --volumes
# Verifique se os volumes foram deletados:
docker volumes ls
# caso nao tenham sido deverá ser removido com o comando docker volume rm [nome-do-volume]
```

Após finalizar o deploy, você poderá realizar testes acessando cada solução da arquitetura:

| Solução                                     | URL de Acesso                          | Descrição                                                                                   | Recomendações                                                                       |
|---------------------------------------------|----------------------------------------|---------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| Airflow                                     | http://[Servidor_Solucoes_IA]:8081    | Orquestrador de tarefas para gerar insumos necessários à recomendação de documentos e embeddings. | - Alterar a senha do Airflow                                                   |
| API SEI IA                                  | https://[Servidor_Solucoes_IA]:8082    | API que utiliza Solr para encontrar processos e documentos semelhantes no banco de dados do SEI. | - Bloquear em nível de rede o acesso a todos, exceto aos servidores do SEI do ambiente correspondente. |
| API SEI IA Feedback                         | https://[Servidor_Solucoes_IA]:8086/docs | API para registrar feedbacks dos usuários sobre as recomendações feitas pela API SEI.           | - Bloquear em nível de rede o acesso a todos, exceto aos servidores do SEI do ambiente correspondente. |
| API SEI IA Assistente                       | https://[Servidor_Solucoes_IA]:8088    | API que fornece funcionalidades do Assistente de IA do SEI.                                      | - Bloquear em nível de rede o acesso a todos, exceto aos servidores do SEI do ambiente correspondente. |
| Solr do Servidor de Soluções de IA  | https://[Servidor_Solucoes_IA]:8084    | Interface do Solr do Servidor de Soluções de IA, utilizado na recomendação de processos e de documentos similares.                                    | - Por padrão, já vem bloqueado.                                                 |
| Banco de Dados do Servidor de Soluções de IA (PostgreSQL)  | [Servidor_Solucoes_IA]:5432  | Banco de dados PostgreSQL interno, que armazena informações do SEI e os embeddings no seu módulo pgvector.                   | - Por padrão, já vem bloqueado.                                                 |

> **Observações:**
> * Por padrão, as portas de acesso externo à rede Docker criada no passo 5 de Instalação **às aplicações Solr e PostgreSQL** não possuem direcionamento para ambiente externo. E não deve ter esse redirecionamento! Essas duas aplicações **são totalmente internas** e armazenam dados indexados dos documentos do SEI. Ou seja, são os bancos de dados das soluções de IA rodando no servidor e o acesso a eles deve ter alta restrição, sendo recomendável manter acessível apenas internamente no servidor.
> * Seria uma falha de segurança abrir um acesso externo a essas duas aplicações sem controle, sem restringir o acesso em nível de rede local do órgão para apenas quem pode acessar.
> * Consideramos que o Administrador do ambiente computacional do SEI, caso precise conferir algo no Solr e PostgreSQL interno do Servidor de Soluções de IA, pode acessar diretamente a partir do acesso dele ao próprio servidor.
> * No monorepo, o arquivo `docker-compose.override.yml` (carregado automaticamente pelo `make up`) expõe portas de Postgres, Solr, Redis e LiteLLM no host para conveniência operacional/diagnóstico. **Em produção**, o acesso a essas portas deve ser bloqueado em nível de firewall do órgão. Se preferir não expor, suba a stack ignorando o override:
>
> ```bash
> cd /opt/sei-ia
> docker compose --env-file default.env --env-file security.env -f docker-compose.yml up -d
> ```
>
> Aguarde a finalização e em seguida prossiga com os testes.

### Airflow
- **URL**: http://[Servidor_Solucoes_IA]:8081
- **Descrição**: Orquestrador de tarefas para gerar insumos necessários à recomendação de documentos e embeddings.

**Recomendamos bloquear o acesso de rede, exceto para o administrador do ambiente computacional.

#### Principais DAGs
- **documents_indexing**: Processa os documentos para serem indexados no Solr do SEI IA para recomendação.
- **documents_update_index**: Atualiza o índice de documentos no Solr do SEI IA.
- **process_indexing**: Processa os processos para serem indexados no Solr do SEI IA para recomendação.
- **process_update_index**: Cria a fila para indexar os processos e documentos no Solr do SEI IA.
- **system_clean_airflow_logs**: Realiza a limpeza de logs do Airflow.
- **system_create_mlt_weights_config**: Gera o arquivo de pesos para a pesquisa de documentos relevantes da API SEI IA.

Ao acessar o Airflow, será apresentada a tela:
![Airflow Interface](image/airflow_interface.png)

No primeiro acesso, o usuário padrão é `seiia` (variável _AIRFLOW_WWW_USER_USERNAME no security.env) e a senha padrão é `seiia` (variável _AIRFLOW_WWW_USER_PASSWORD no security.env).

A senha padrão acima **deve ser alterada**! Seguir os passos abaixo para alterar a senha padrão do Airflow.
  - Inicialmente, você deve acessar `Your Profile`
  ![Airflow troca de senha - Passo 1](image/airflow_2.png)
  - Em seguida, clique em `Reset my password`
  ![Airflow troca de senha - Passo 2](image/airflow_3.png)
  - Por fim, insira sua nova senha (`password`), confirme-a (`confirm password`) e clique em `save`
  ![Airflow troca de senha - Passo 3](image/airflow_4.png)
  - Sua senha foi alterada com sucesso.

#### Monitoramento e Significado das Cores das DAGs

Para garantir o funcionamento correto do sistema, acompanhe o status das DAGs, que usam um esquema de cores para indicar o estado atual de cada uma:
- **Verde escuro**: Execução bem-sucedida, indicando que a DAG foi concluída sem erros.
- **Verde claro**: DAG em execução. Caso esteja em execução por um longo período, pode indicar um possível atraso ou alta carga de processamento.
- **Vermelho**: Falha na execução. Verifique e corrija o erro para evitar impacto nas recomendações e na criação de embeddings para o RAG.
- **Cinza**: DAG sem execução agendada ou manual. Pode ser normal em processos que são executados apenas em intervalos específicos.
- **Amarelo**: Indica que a execução foi interrompida antes de sua conclusão. Necessita ser retomada ou reiniciada conforme necessário.

#### Como Obter o Log de Execução em Caso de Falha (DAG Vermelha)

Se uma DAG estiver marcada em vermelho, isso indica que houve uma falha durante a execução. Para investigar o problema:
1. **Clique no nome da DAG** para abrir uma visão detalhada.
2. Navegue até a execução com falha (marcada em vermelho no diagrama).
3. **Clique na tarefa específica que falhou** para acessar as opções de log.
4. Selecione a aba **Log** para ver o histórico detalhado de execução e identificar o erro.

Essa análise dos logs ajudará a entender a causa da falha e facilitará a correção do problema antes de reiniciar a DAG.

### API de Recomendação de Processos e Documentos do SEI IA
- **URL**: http://[Servidor_Solucoes_IA]:8082
- **Descrição**: API que utiliza Solr para encontrar processos e documentos semelhantes no banco de dados do SEI.
![Tela da API de Recomendação de Processos do SEI IA](image/API_SEIIA.png)
- **Health Check**:
  - API
      ```bash
      curl -X 'GET' 'http://[Servidor_Solucoes_IA]:8082/health' -H 'accept: application/json'
      ```

      deve retornar:

      ```bash
      {
         "status":"OK",
         "response_time": null
      }
      ```
  - Banco de dados
      ```bash
      curl -X 'GET' 'http://[Servidor_Solucoes_IA]:8082/health/database' -H 'accept: application/json'
      ```
      deve retornar:
      ```bash
      {
         "status":"OK",
         "response_time": null
      }
      ```
  - Recomendação de processos
      ```bash
      curl -X 'GET' 'http://[Servidor_Solucoes_IA]:8082/health/process-recommendation' -H 'accept: application/json'
      ```
      deve retornar:
      ```bash
      {
         "status":"OK",
         "response_time": tempo de resposta
      }
      ```
  - Recomendação de documentos
      ```bash
      curl -X 'GET' 'http://[Servidor_Solucoes_IA]:8082/health/document-recommendation' -H 'accept: application/json'
      ```
      deve retornar:
      ```bash
      {
         "status":"OK",
         "response_time": tempo de resposta
      }
      ```

### API SEI IA Feedback de Processos
- **URL**: http://[Servidor_Solucoes_IA]:8086/docs
- **Descrição**: API para registrar feedbacks dos usuários sobre as recomendações feitas pela API SEI.
![Tela da API de Feedback de Processos do SEI IA](image/API_SEIIA_feedback.png)
- **Health Check**:
   ```bash
   curl -X 'GET' 'http://[Servidor_Solucoes_IA]:8086/health' -H 'accept: application/json'
   ```
   deve retornar:
   ```bash
   {
      "status":"OK",
      "timestamp":"DATA"
   }
   ```

### API SEI IA Assistente
- **URL**: http://[Servidor_Solucoes_IA]:8088
- **Descrição**: API que fornece funcionalidades do Assistente de IA do SEI.
![Tela do Assistente de IA do SEI IA](image/API_SEIIA_ASSISTENTE.png)
- **Health Check**:
   ```bash
   curl -X 'GET' 'http://[Servidor_Solucoes_IA]:8088/health' -H 'accept: application/json'
   ```
   deve retornar:
   ```bash
   {"status":"OK"}
   ```

### Bancos de Dados

#### Solr do Servidor de Soluções de IA
- **URL**: http://[Servidor_Solucoes_IA]:8084
- **Descrição**: Interface do Solr do Servidor de Soluções de IA, utilizado na recomendação de processos e de documentos similares.
![Tela do Solr do Servidor de Soluções de IA do SEI](image/Solr_SEIIA.png)

#### PostgreSQL
- **URL**: [Servidor_Solucoes_IA]:5432
- **Descrição**: Banco de dados PostgreSQL interno, que armazena informações do SEI e os embeddings no seu módulo pgvector.

## Configuração do Certificado HTTPS no SEI

> **Esta etapa é obrigatória** a partir da estrutura monorepo. Sem ela, o passo "Validar Integração" da próxima seção falha com erro de DNS (`Could not resolve host: seiia`) ou de TLS (`certificate issuer has been marked as not trusted`).

A integração do SEI com o Assistente exige HTTPS pelo hostname `seiia`. Para o "Validar Integração" no SEI funcionar, dois pontos precisam estar resolvidos no ambiente onde o SEI está rodando:

1. **DNS** — o servidor (ou container) do SEI precisa resolver `seiia` para o IP do Nginx do Assistente.
2. **TLS** — o certificado autoassinado do Assistente precisa estar no truststore do sistema operacional onde o SEI roda, para que o `libcurl`/PHP confie nele.

### Como o certificado é gerado

O serviço `assistente-nginx` (build a partir de `aplicacoes/assistente/nginx.dockerfile`) **gera automaticamente** um certificado autoassinado durante o build, com:
- `CN = ${NB_USER}` (padrão `seiia`, vindo de `default.env`)
- `Subject Alternative Name (SAN): DNS:${NB_USER},DNS:localhost,IP:127.0.0.1`

Não é necessário gerar nada manualmente — o cert já está dentro da imagem. O que precisamos é **extraí-lo** e **entregá-lo ao SEI**.

### 1. Extrair o PEM do container `assistente-nginx`

Execute como `seiia`, no servidor onde o SEI IA está instalado:

```bash
cd /opt/sei-ia
mkdir -p .runtime/certs
docker compose --env-file default.env --env-file security.env exec -T assistente-nginx \
  cat /etc/ssl/certs/seiia.cert.pem > .runtime/certs/seiia.cert.pem
```

Isso gera `/opt/sei-ia/.runtime/certs/seiia.cert.pem`. Esse é o arquivo que será entregue ao SEI nos passos seguintes.

### 2. Configurar conforme o cenário do SEI

Identifique como o SEI está instalado no seu ambiente e siga **apenas** o cenário aplicável.

#### Cenário A — SEI rodando em CONTAINER Docker (`ops_sei-docker`)

Esse é o caso quando o SEI foi instalado pelo deploy oficial via [ops_sei-docker](https://github.com/anatelgovbr/sei) e o Apache (`httpd`) está como container.

**A.1 — Editar o `docker-compose.yml` do SEI**

Em `ops_sei-docker/docker-compose.yml`, ajuste o serviço `httpd` para:

- Estar nas redes `default` (atual) **e** `seiia-bridge` (a ser declarada).
- Bind-mountar o PEM extraído em (1) na pasta de anchors do SO do `httpd`.
- Rodar `update-ca-trust extract` antes do bootstrap original do SEI.

```yaml
services:
  httpd:
    networks:
      - default
      - seiia-bridge
    volumes:
      - /opt/sei-ia/.runtime/certs/seiia.cert.pem:/etc/pki/ca-trust/source/anchors/seiia.crt:ro
    command: bash -lc "update-ca-trust extract && exec /command.sh"

networks:
  seiia-bridge:
    name: docker-host-bridge
    external: true
```

Por que cada coisa:
- **`networks`** — coloca o `httpd` em **duas** redes: continua se comunicando com `database`, `solr`, `memcached` etc. via `default`, e ganha acesso ao SEI IA via `docker-host-bridge` (onde o nome `seiia` resolve para o Nginx do Assistente, graças ao alias declarado no `docker-compose.yml` do SEI IA).
- **`volumes`** — bind-mount **read-only** do PEM. O caminho de destino é o diretório de anchors do RHEL/CentOS (sistema base mais comum da imagem do `httpd` do SEI). Para Debian/Ubuntu, o destino seria `/usr/local/share/ca-certificates/seiia.crt` e o comando seria `update-ca-certificates` (ver Cenário B).
- **`command`** — `update-ca-trust extract` regenera o `/etc/pki/tls/certs/ca-bundle.crt` incluindo o anchor montado **antes** do bootstrap original do SEI rodar. Sem isso, o cert ficaria nos anchors mas fora do bundle que o `libcurl` consulta, e o PHP rejeitaria com `certificate issuer has been marked as not trusted`.

**A.2 — Subir o `httpd`**

```bash
cd /opt/sei/fontes/sei/ops_sei-docker
docker compose up -d --force-recreate httpd
```

**A.3 — Validar (de dentro do `httpd`)**

```bash
# Resolução do hostname (deve retornar um IP da sub-rede docker-host-bridge)
docker exec httpd getent hosts seiia

# Cert presente nos anchors
docker exec httpd ls /etc/pki/ca-trust/source/anchors/seiia.crt

# HTTPS via curl (mesmo stack que o PHP usa)
docker exec httpd curl -sS https://seiia/health
# resposta esperada: {"status":"OK"}

# HTTPS via PHP (réplica do que o "Validar Integração" executa)
docker exec httpd php -r '$c=curl_init("https://seiia/health");curl_setopt($c,CURLOPT_RETURNTRANSFER,1);echo curl_exec($c).PHP_EOL;'
# resposta esperada: {"status":"OK"}
```

Se os quatro comandos retornarem o esperado, pode prosseguir para [Mapeamento da Integração no SEI](#mapeamento-da-integração-no-sei).

#### Cenário B — SEI rodando direto no HOST (Apache/PHP nativo)

Esse é o caso quando o Apache/PHP do SEI está instalado direto no Linux do servidor, sem containerização.

**B.1 — Resolver o hostname `seiia`**

Descubra o IP do `assistente-nginx` na bridge:

```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  $(docker compose -f /opt/sei-ia/docker-compose.yml ps -q assistente-nginx)
```

Anote o IP (ex.: `10.90.0.5`) e adicione em `/etc/hosts` do servidor SEI:

```bash
sudo bash -c 'echo "10.90.0.5 seiia" >> /etc/hosts'
```

> Em órgãos com DNS interno, o caminho mais robusto é cadastrar `seiia` como registro A apontando para o IP do servidor SEI IA, em vez de usar `/etc/hosts`. **Isso só funciona se o servidor SEI IA também tiver o IP da bridge roteável** ou se você publicar a porta 443 do `assistente-nginx` no host (alterando `ASSISTENTE_PORT=443` em `default.env`).

**B.2 — Instalar o cert no truststore do SO do servidor SEI**

**RHEL / CentOS / Fedora**:

```bash
sudo cp /opt/sei-ia/.runtime/certs/seiia.cert.pem /etc/pki/ca-trust/source/anchors/seiia.crt
sudo update-ca-trust extract
```

**Ubuntu / Debian**:

```bash
sudo cp /opt/sei-ia/.runtime/certs/seiia.cert.pem /usr/local/share/ca-certificates/seiia.crt
sudo update-ca-certificates
```

**B.3 — Reiniciar o Apache/PHP**

Para o `libcurl` carregado pelo PHP reler o trust store:

```bash
# RHEL/CentOS/Fedora
sudo systemctl restart httpd php-fpm

# Ubuntu/Debian
sudo systemctl restart apache2 php*-fpm
```

**B.4 — Validar**

```bash
# Resolução
getent hosts seiia

# HTTPS via curl
curl -sS https://seiia/health
# resposta esperada: {"status":"OK"}

# HTTPS via PHP
php -r '$c=curl_init("https://seiia/health");curl_setopt($c,CURLOPT_RETURNTRANSFER,1);echo curl_exec($c).PHP_EOL;'
# resposta esperada: {"status":"OK"}
```

Se os três comandos retornarem o esperado, pode prosseguir para [Mapeamento da Integração no SEI](#mapeamento-da-integração-no-sei).

### Quando refazer este procedimento

- Sempre que `assistente-nginx` for buildado novamente com `--no-cache` (a chave/cert ficam dentro da imagem; um rebuild forçado pode regenerá-los).
- Sempre que `NB_USER` for alterado em `default.env` (o cert é gerado com base nesse valor).

Nesses casos, repita o passo **1** (extrair o PEM) e, no Cenário A, recrie o `httpd` com `--force-recreate` para que `update-ca-trust extract` rode novamente. No Cenário B, repita os passos **B.2** e **B.3**.

### Alternativa para produção: certificado de CA confiada

Substituir o autoassinado por um certificado emitido por uma CA confiada pelo SO **elimina os passos 1 e 2.B (truststore)** — sobra só a parte de DNS/rede. Veja a seção [Guia de utilização de certificado SSL proprietário](#guia-de-utilização-de-certificado-ssl-proprietário) para esse caminho.

## Mapeamento da Integração no SEI

**SEI > Administração > Inteligência Artificial > Mapeamento das Integrações**

Conforme consta orientado no [README do Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia?tab=readme-ov-file#orienta%C3%A7%C3%B5es-negociais), somente com tudo configurado na Administração do módulo no SEI do ambiente correspondente será possível o uso adequado de toda a solução.

Assim, com todas as soluções do servidor em status "Up", conforme verificado acima, a primeira verificação no SEI para confirmar que a comunicação entre SEI <> Servidor de Soluções de IA está funcionando com sucesso é configurar os dois registros existentes no menu do SEI de Administração > Inteligência Artificial > Mapeamento das Integrações.
- Nos dois registros existentes no menu acima, é necessário entrar na tela "Alterar Integração" para cadastrar o host do Servidor de Soluções de IA instalado e "Validar" a integração, conforme print abaixo.

![Mapeamento das Integrações OK na Administração do SEI](image/mod_sei_Validar_Integracao_com_Servidor_1.png)

Se o SEI não se conectar com sucesso ao Servidor de Soluções de IA que acabou de instalar, conforme acima, vai dar uma mensagem de crítica abaixo e, com isso, é necessário ajustar configurações de rede para que a comunicação funcione.

![Mapeamento das Integrações não OK na Administração do SEI](image/mod_sei_Validar_Integracao_com_Servidor_2.png)

## Resolução de Problemas Conhecidos

- **Erro de montagem de arquivo**:

  ```bash
  Error response from daemon: failed to create task for container: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: error mounting "/opt/sei/sei-ia/solr_config/log4j2.xml" to rootfs at "/opt/solr/server/resources/log4j2.xml": create mount destination for /opt/solr/server/resources/log4j2.xml mount: cannot mkdir in /var/lib/docker/overlay2/...: not a directory: unknown
  ```

  Solução:

  ```bash
  rmdir /opt/sei/sei-ia/solr_config/log4j2.xml
  touch /opt/sei/sei-ia/solr_config/log4j2.xml
  ```

- **Erro de limite de CPU**:

  ```bash
  Error response from daemon: Range of CPUs is from 0.01 to 4.00, as there are only 4 CPUs available
  ```

  Solução: alterar o arquivo `default.env` e modificar todas as chaves que possuem `CPU_LIMIT` para valores compatíveis com a quantidade de CPUs do servidor.

- **Erro de nome de container duplicado**:

  ```bash
  Error response from daemon: Conflict. The container name "/3bd4ff6aae26_sei_ia-jobs_api-1" is already in use by container "64856a9070ccf94bbc1803a98749bee282813cd6d65dab51ecab827449ee0423".
  ```

  Solução: Identificar qual o processo que ainda está rodando:

  ```bash
  docker ps -a
  ```

  Buscar o ID do container e parar:

  ```bash
  docker stop [NUMERO_do_container] # no exemplo seria 3bd4ff6aae26
  ```

- **Dependência falhando ao iniciar**:

  ```bash
  dependency failed to start: container sei_ia-rabbitmq-pd-1 is unhealthy
  ```

  Solução: Por padrão, ao rodar novamente o comando de inicialização, volta a funcionar. Se persistir, deve-se verificar a quantidade de memória disponível no sistema.

  ```bash
  cd /opt/sei-ia
  make up
  ```

## Pontos de Atenção para Escalabilidade

* Caso necessário, podem ser alteradas as variáveis de `..._MEM_LIMIT` no `default.env`.
* Não devem ser alteradas para valores menores, pois isso afetará o funcionamento do sistema.

### Pontos de Montagem de Volumes

Os pontos de montagem dos volumes Docker estão localizados em `/var/lib/docker/volumes/`.
* Esses volumes tendem a crescer de acordo com a quantidade de documentos e processos armazenados, conforme descrito nos requisitos de sistema.

É possível também alterar os pontos de montagem dos volumes Docker modificando o arquivo `daemon.json`. Mais informações podem ser encontradas na [documentação do Docker](https://docs.docker.com/reference/cli/dockerd/#configure-runtimes-using-daemonjson).
  - Como alternativa, pode-se criar links simbólicos para cada um dos volumes.

- Exemplo de criação de um link simbólico para `/var/lib/docker/volumes/sei_ia_pgvector-db-volume-all`:
  - Deve parar o Docker para evitar problemas durante a movimentação dos dados:

   ```bash
   sudo systemctl stop docker
   ```

  - Mova a pasta de volumes para o novo caminho:

  ```bash

  sudo mv /var/lib/docker/volumes/sei_ia_pgvector-db-volume-all /novo/caminho/para/volumes
  ```

  - Crie o link simbólico apontando para o novo local dos volumes:

  ```bash

  sudo ln -s /novo/caminho/para/volumes /var/lib/docker/volumes/sei_ia_pgvector-db-volume-all
  ```

  - Reinicie o Docker:

  ```bash
  sudo systemctl start docker
  ```

### Ajustes Necessários

Ao escalar a solução, considere os seguintes pontos:

- **Solr**:
  - Aumente a alocação de memória se houver necessidade de lidar com uma maior quantidade de documentos ou consultas simultâneas. Uma boa prática é aumentar a memória em incrementos de 2 GB.
  - Para isso, altere no arquivo `default.env`:

   | Variável                        | Descrição                                                                                  |
   |---------------------------------|--------------------------------------------------------------------------------------------|
   | `SOLR_JAVA_MEM="-Xms8g -Xmx24g"` | Define as opções de memória Java para Solr, com um mínimo de 8 GB e um máximo de 24 GB.     |
   | `SOLR_MEM_LIMIT=28g`            | Define o limite de memória para Solr como 8 GB.                                           |
   | `SOLR_CPU_LIMIT='8'`            | Define o limite de CPU para Solr como 8 unidades de CPU.                                   |

- **Airflow**:
  - O Airflow pode ser escalado horizontalmente adicionando mais workers. Para mais informações, consulte a [documentação do Airflow](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/overview.html).
  - Em nossa solução, é possível configurar mais workers na variável `AIRFLOW_WORKERS_REPLICAS` no `default.env`, lembrando que cada réplica usa em média 6 GB.

- **Postgres**:
  - Para aumentar o desempenho, considere aumentar a memória disponível. Monitore o uso de disco e ajuste conforme necessário.

   | Variável                    | Descrição                                                     |
   |-----------------------------|---------------------------------------------------------------|
   | `PGVECTOR_MEM_LIMIT=16g`     | Define o limite de memória para Pgvector como 16 GB.           |
   | `PGVECTOR_CPU_LIMIT='4'`    | Define o limite de CPU para Pgvector como 4 unidades de CPU.  |

## Backup periódico dos dados do Servidor de Soluções de IA

Um ponto importante em relação ao Servidor de Soluções de IA é a realização de backup periódico, principalmente dos bancos de dados utilizados pelas aplicações. Todos os dados do servidor são armazenados em volumes Docker e, via de regra, estão localizados na pasta `/var/lib/docker/volume`. O comando abaixo lista os volumes relacionados ao servidor:

```bash
docker volume ls | grep "^sei_ia-"
```

## Guia de utilização de certificado SSL proprietário

Este guia tem como objetivo auxiliar na configuração de um certificado SSL proprietário para as aplicações de backend do SEI IA.

### Passos para a configuração do certificado SSL proprietário

**IMPORTANTE:** O usuário que vai executar o script deve ter permissão sudo.

1. **Criar a pasta certificado na raiz do projeto:**

```bash
sudo mkdir certificado
```

2. **Configuração do certificado:**

   **Opção A - Se você já possui um certificado SSL:**

   Copie os arquivos .key e .pem para a pasta certificado:
   ```bash
   cp [caminho do arquivo .key] certificado/seiia.key
   cp [caminho do arquivo .pem] certificado/seiia.pem
   ```

   **Opção B - Se você NÃO possui um certificado SSL:**

   O certificado será criado automaticamente durante a execução do script.

3. **Executar o script de ativação:**

```bash
sudo bash certificado_ssl_proprietario/script_ativar_ssl_proprietario.sh
```

## Anexos

### **Instalar Git - OPCIONAL**

> **Observação**:
> - É possível instalar sem o Git, sobretudo caso o órgão possua procedimentos e ferramentas de Deploy próprios de seu ambiente computacional, como um GitLab e Jenkins, deve adequar este passo aos seus próprios procedimentos.
> - Apenas tenha certeza de manter a estrutura de código deste projeto no GitHub dentro da pasta **/opt/sei-ia**.

   Siga a documentação oficial para instalar o Git: [Documentação Git](https://git-scm.com/book/pt-br/v2/Come%C3%A7ando-Instalando-o-Git)

   Aqui está o resumo dos comandos necessários para Ubuntu/Debian:
   ```bash
   sudo apt-get update
   sudo apt-get install git
   ```

   Aqui está o resumo dos comandos necessários para o CentOS/RHEL:
   ```bash
   sudo yum install git-all
   ```

### **Instalar Docker - CASO AINDA NÃO ESTEJA INSTALADO**

   Siga a documentação oficial para instalar o Docker: [Documentação Docker](https://docs.docker.com/engine/install/)

   Aqui está o resumo dos comandos necessários para Ubuntu/Debian:
   ```bash
   for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove $pkg; done

   # Adicionar a chave GPG oficial do Docker:
   sudo apt-get update
   sudo apt-get install ca-certificates curl
   sudo install -m 0755 -d /etc/apt/keyrings
   sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   sudo chmod a+r /etc/apt/keyrings/docker.asc

   # Adicionar o repositório do Docker:
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

   # Instalar o Docker
   sudo apt-get update
   sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

   Aqui está o resumo dos comandos necessários para o CentOS/RHEL:
   ```bash
   # Remover pacotes antigos do Docker, caso existam
   for pkg in docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine podman containerd runc; do sudo yum remove $pkg; done

   # Instalar o Docker
   sudo yum install -y yum-utils
   sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
   sudo yum install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

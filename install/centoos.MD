# Instalação do SEI-IA no CentOS/RedHat

Este guia descreve os passos para instalar o SEI-IA em um servidor CentOS Stream.

## Pré-requisitos

- **CPU**: CPU Intel(R) Xeon(R) 2.10GHz / RAM 128G
- **MEMÓRIA**: Mínimo de 128GB
- **ESPAÇO EM DISCO**: Mínimo de 35 GB

Antes de começar a instalação, certifique-se de que os seguintes pacotes estejam instalados no sistema:

**TODOS OS COMANDOS ILUSTRADOS NESSE DOCUMENTO SÃO DADOS VIA TERMINAL**

```bash
sudo yum update
sudo yum install net-tools curl
```

## Passos para Instalação

1. **Criar a pasta para o SEI**

   ```bash
   sudo mkdir /opt/sei
   sudo chmod 777 /opt/sei
   cd /opt/sei
   ```
2. **Instalar Git**

   ```bash
   sudo yum install git
   git clone https://git.anatel.gov.br/processo_eletronico/sei.git
   ```
3. **Instalar Docker**
   Siga a documentação oficial para instalar o Docker no CentOS. Aqui está o resumo dos comandos necessários:

   ```bash
   # Remover pacotes antigos do Docker, caso existam
   for pkg in docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine podman containerd runc; do sudo yum remove $pkg; done

   # Instalar o Docker
   sudo yum install -y yum-utils
   sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
   sudo yum install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```
4. **Iniciar o Docker**

   ```bash
   sudo systemctl start docker
   sudo systemctl enable docker
   docker --version
   ```
5. **Configurar o ambiente SEI**
   Entre no diretório do SEI e configure o arquivo `.env` (usando o MySQL como exemplo):

   ```bash
   cd sei/ops
   sudo docker compose up -d
   ```

   **Nota**: Se o seu usuário não tiver permissões Docker, recomenda-se criar um usuário com acesso ao Docker.

## Instalação do SEI-IA

1. **Preparar o ambiente**
   Instale o Docker e o Git conforme descrito anteriormente. Crie um usuário específico para o SEI-IA:

   ```bash
   sudo adduser seiia
   sudo usermod -aG docker seiia
   sudo mkdir /opt/sei-ia-storage
   sudo chmod 777 /opt/sei-ia-storage
   ```
2. **Clonar o repositório SEI-IA**
   Troque para o usuário criado e clone o repositório via SSH:

   ```bash
   su seiia
   git clone git@github.com:anatelgovbr/sei-ia.git
   ```
3. **Criar a rede Docker**
   Crie uma rede Docker customizada para a instalação:

   ```bash
   docker network create --driver=bridge --subnet=192.168.144.0/24 --ip-range=192.168.144.0/24 --gateway=192.168.144.1 docker-host-bridge
   ```
4. **Configurar o arquivo `security.env`**
   Certifique-se de conhecer o tipo de instalação do SEI (neste caso, MySQL). Preencha os seguintes campos:

   ```bash
   #### Ambiente
   ENVIRONMENT=prod  # Define o ambiente como "prod" (produção).

   GID_DOCKER=****   # O GID (Group ID) do grupo Docker no host; deve ser obtido executando o comando no terminal: 
                     # "cat /etc/group | grep docker | cut -d: -f3".

   #### Banco SEI
   export DB_SEI_USER=****      # Usuário para acessar o banco de dados SEI.
   export DB_SEI_PWD=*****      # Senha para o banco de dados SEI.
   export DB_SEI_HOST=*****     # Endereço do host do banco de dados SEI.
   export DB_SEI_DATABASE=****  # Nome do banco de dados SEI.
   export DB_SEI_PORT=*****     # Porta de conexão do banco de dados SEI.
   export DB_SEI_SCHEMA=*****   # Esquema do banco de dados SEI (caso for MySQL é o mesmo do database).
   export DATABASE_TYPE=*****    # Tipo de banco de dados (ex: mssql, mysql, oracle.).

   #### Assistente do SEI (você deve escolher o usuário e a senha na primeira instalação.)
   export ASSISTENTE_PGVECTOR_USER=*****         # Usuário para acessar o banco de dados PGVector do Assistente, será criado no momento da primeira instalação.
   export ASSISTENTE_PGVECTOR_PWD=*****          # Senha para o banco de dados PGVector do Assistente, será criado no momento da primeira instalação.
   ```
5. **Executar o deploy**
   Execute o script de deploy:

   ```bash
   sudo bash deploy-externo-imgs.sh 
   ```

   Este passo pode levar bastante tempo, pois é realizado o download de todas as imagens.
6. **Testes de acessos**
   Após finalizado o deploy, você poderá realizar os testes.

## Resolução de Problemas

- **Erro ao criar tarefa para o container**:

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

  Solução: Alterar o arquivo `prod.env` (caso o `ENVIRONMENT` seja diferente, alterar o `.env` específico) e modificar todas as chaves que possuem `CPU_LIMIT`.
- **Erro de nome de container duplicado**:

  ```bash
  Error response from daemon: Conflict. The container name "/3bd4ff6aae26_sei_ia-jobs_api-1" is already in use by container "64856a9070ccf94bbc1803a98749bee282813cd6d65dab51ecab827449ee0423".
  ```

  Solução:

  ```bash
  docker ps -a
  docker stop [NUMERO_do_container] # no exemplo seria 3bd4ff6aae26
  ```
- **Dependência falhando ao iniciar**:

  ```bash
  Error response from daemon: dependency failed to start: container sei_ia-rabbitmq-pd-1 is unhealthy
  ```

  Solução: Ao rodar novamente o comando de inicialização, deve voltar a funcionar.

  ```bash
  sudo bash deploy-externo-imgs.sh 
  ```

## Exemplo de `security.env`:

```bash
# Essenciais no momento da instalação
#### Ambiente
export GID_DOCKER=999 #OBTER GID DO GRUPO DOCKER NO HOST: "cat /etc/group | grep docker | cut -d: -f3"

#### Banco SEI
export DB_SEI_USER=root
export DB_SEI_PWD=P@ssword
export DB_SEI_HOST=localhost  # ou o endereço do host onde o banco de dados está localizado
export DB_SEI_DATABASE=sei    # o nome do seu banco de dados
export DB_SEI_PORT=3306       # porta padrão do MySQL
export DB_SEI_SCHEMA=sei      # normalmente o mesmo que o banco de dados em MySQL
export DATABASE_TYPE=mysql    # tipo do banco de dados do SEI já instalado, pode ser mysql, mssql ou oracle

#### Banco Postgres aplicação 
## O Usuário deve criar usuário e senha para o Postgres
# export POSTGRES_USER=usuario_sei
# export POSTGRES_PASSWORD=senhasei

#### Assistente do SEI
## O Usuário deve criar usuário e senha para o PGVECTOR
export ASSISTENTE_PGVECTOR_USER=usuario_sei
export ASSISTENTE_PGVECTOR_PWD=senhasei

# Não Essenciais para instalação

# Não altere as variáveis abaixo!!!
ENVIRONMENT=prod # Ambiente que estará sendo instalado, pode ser devel, homol, prod

#### Git
export GIT_TOKEN=''

#### Assistente do SEI
export ASSISTENTE_PGVECTOR_HOST=pgvector_all # nome do container do pg_vector
export ASSISTENTE_PGVECTOR_PORT=5432 # porta do container do pgvector
export ASSISTENTE_PGVECTOR_DB=sei_ia_assistente # nome do banco de dados do container do pgvector usado pelo assistente
```

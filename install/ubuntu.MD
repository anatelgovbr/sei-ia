# Instalação SEI-IA no Ubuntu Server Minimal / Debian

Este guia descreve os passos para instalar o SEI-IA em um servidor Ubuntu minimal.

## Pré-requisitos

- **CPU**: Mínimo de 4 núcleos
- **MEMÓRIA**: Mínimo de 32 GB
- **ESPAÇO EM DISCO**: Mínimo de 35 GB

Antes de começar a instalação, certifique-se de que os seguintes pacotes estejam instalados no sistema:

**TODOS OS COMANDOS ILUSTRADOS NESSE DOCUMENTO SÃO DADOS VIA TERMINAL**

```bash
sudo apt update
sudo apt install net-tools htop curl
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
   sudo apt-get install git
   ```

3. **Instalar Docker**
   Siga a documentação oficial para instalar o Docker no Ubuntu: [Documentação Docker](https://docs.docker.com/engine/install/ubuntu/)

   Aqui está o resumo dos comandos necessários:

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

4. **Iniciar o Docker**
   ```bash
   sudo service docker start
   docker --version
   ```

5. **Preparar o ambiente**
   Instale o Docker e o Git conforme descrito anteriormente. Crie um usuário específico para o SEI-IA:

   ```bash
   sudo adduser seiia
   sudo usermod -aG docker seiia
   sudo mkdir /opt/sei-ia-storage
   sudo mkdir /opt/seiia
   sudo chmod 777 /opt/sei-ia-storage
   sudo chmod 777 /opt/seiia
   cd /opt
   sudo chown seiia seiia
   ```

6. **Clonar o repositório SEI-IA**
   Troque para o usuário criado e clone o repositório via SSH:

   ```bash
   su seiia
   git clone git@github.com:anatelgovbr/sei-ia.git
   cd sei-ia
   ```

7. **Criar a rede Docker**
   Crie uma rede Docker customizada para a instalação:

   ```bash
   docker network create --driver=bridge --subnet=192.168.144.0/24 --ip-range=192.168.144.0/24 --gateway=192.168.144.1 docker-host-bridge
   ```

8. **Configurar o arquivo `env_files/security.env`**
   Certifique-se de conhecer o tipo de instalação do SEI (neste caso, MySQL). Preencha os seguintes campos:

   ```bash
   #### Ambiente
   ENVIRONMENT=prod  # Define o ambiente como "prod" (produção).

   GID_DOCKER=****   # O GID (Group ID) do grupo Docker no host; deve ser obtido executando o comando no terminal: 
                     # "cat /etc/group | grep docker | cut -d: -f3".

   #### Banco Sei
   export DB_SEI_USER=****      # Usuário para acessar o banco de dados SEI.
   export DB_SEI_PWD=*****      # Senha para o banco de dados SEI.
   export DB_SEI_HOST=*****     # Endereço do host do banco de dados SEI.
   export DB_SEI_DATABASE=****  # Nome do banco de dados SEI.
   export DB_SEI_PORT=*****     # Porta de conexão do banco de dados SEI.
   export DB_SEI_SCHEMA=*****   # Esquema do banco de dados SEI (caso for mysql é o mesmo do database).
   export DATABASE_TYPE=*****    # Tipo de banco de dados (ex: mssql, mysql, oracle.).

   #### Assistente do Sei (você deve escolher o usuário e a senha na primeira instalação.)
   export ASSISTENTE_PGVECTOR_USER=*****         # Usuário para acessar o banco de dados PGVector do Assistente, será criado no momento da primeira instalação.
   export ASSISTENTE_PGVECTOR_PWD=*****          # Senha para o banco de dados PGVector do Assistente, será criado no momento da primeira instalação.
   ```

9. **Configurações adicionais**
   Corrija os seguintes parâmetros no arquivo `security.env`:

   ```bash
   ASSISTENTE_PGVECTOR_HOST=pgvector_all
   ASSISTENTE_PGVECTOR_DB=sei_assistente
   LOGLEVEL=INFO
   ```

10. **Executar o deploy**
    Execute o script de deploy:

    ```bash
    sudo bash deploy-externo-imgs.sh 
    ```

    Este passo pode levar bastante tempo, pois é realizado o download de todas as imagens. 

11. **Testes de acessos**
    Após finalizado o deploy, você poderá realizar os testes.

## Resolução de problemas

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

  Solução: Alterar o arquivo `prod.env` (caso o `ENVIRONMENT` seja diferente, alterar o `.env` específico) e modificar todas as chaves que possuem `CPU_LIMIT`.

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

  Solução: Por padrão, ao rodar novamente o comando de inicialização, volta a funcionar.
  ```bash
  sudo bash deploy-externo-imgs.sh 
  ```

## Conclusão
Após seguir esses passos, tanto o SEI quanto o SEI-IA devem estar instalados e configurados corretamente no seu servidor Ubuntu minimal.

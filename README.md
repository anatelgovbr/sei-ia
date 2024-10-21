# Módulo SEI IA - Aplicações de backend

## Requisitos
- Requisito Mínimo é o SEI 4...
- Docker Community Edition (versão >= 27.0.3)
- Hardware: CPU Intel(R) Xeon(R) 2.10GHz / RAM 128G

## Orientações preliminares
A instalação das aplicações de backend do módulo SEI IA foi projetada tendo como objetivo principal a simplificação máxima do processo, automatizando todos os procedimentos possíveis. Ainda assim, há alguns procedimentos que, ou por segurança ou por estarem relacionados ao ambiente de instalação, necessitam ser manualmente realizados pelo usuário.

Sendo assim, sugere-se fortemente que, antes de iniciar a instalação do SEI IA, seja feita uma leitura integral desse manual, pois dúvidas que possam surgir no início da instalação podem ser esclarecidas pela leitura prévia das orientações que constam nesse manual.

## Procedimentos para Instalação

### 1. Configuração de Rede do Docker
O docker utiliza como default a faixa de IP  172.17.\*.\*. Considere se o seu ambiente de rede também utiliza esta faixa de IPs para outro propósito. Se for esse o caso, faz-se necessária a utilização de uma faixa de IPs dedicadas para os containers docker, com objetivo de evitar erros de roteamento causados pela sobreposição de endereços IP.

Caso o bloco de IPs default do Docker entre em conflito com a sua rede, sugerimos usar outra subrede para os containers do SEI IA. Poderia-se usar, por exemplo, o bloco 192.168.144.0/24, pois essa subnet permite utilizar até 252 containers, mais que suficientes para as aplicações do SEI IA.

A restrição da subnet deve ser feita através da criação de user defined bridge network para cada docker host. Também sugerimos a remoção da default bridge, como forma de evitar o uso de uma bridge fora da subnet, dado que novos containers adotam a default bridge por padrão se uma rede não for especificada e se a default bridge estiver disponível.

Uma vez definida a subrede a ser utilizada para o SEI IA, o próximo passo é a criação da rede `docker-host-bridge`. Segue um exemplo do comando a ser executado, considerando que o bloco de rede a ser usado é o **192.168.144.0/24**:

```bash
docker network create --driver=bridge --subnet=192.168.144.0/24 --ip-range=192.168.144.0/24 --gateway=192.168.144.1 docker-host-bridge
``` 

É importante certificar-se de que a rede `docker-host-bridge` foi criada, o que pode ser feito com o comando `docker network ls`, como poder ser visto abaixo:

```
$ docker network ls

NETWORK ID     NAME                 DRIVER    SCOPE
1a9d40cca392   docker-host-bridge   bridge    local
7cee8287f256   host                 host      local
0355f600e1d7   none                 null      local
```

|**IMPORTANTE**|
|--|
| A criação da rede `docker-host-bridge` é um requisito **obrigatório** para a instalação do SEI IA.|

### 3. Criação do usuário de instalação do SEI IA
É necessário criar um usuário específico para a instalação e atualização do módulo SEI IA.
Sugerimos usar o nome `seiia` para esse usuário. É obrigatório que o usuário criado tenha acesso de administrador no Docker, o que geralmente é realizado ao definir-se que o usuário de instalação faz parte do grupo `docker` no momento da sua criação.
Para criar o usuário `seiia` e colocá-lo no grupo `docker` você pode usar o comando abaixo:
```bash
useradd -G docker seiia
```

**Observação**: o comando `useradd` somente pode ser executado por usuários administradores. Caso você não tenha accesso de administrador, fale com a sua equipe de TI para obter mais informações sobre como proceder para criar o usuário de instalação do SEI IA.

### 4. **Fazer download do projeto SEI IA**
Os comandos para o download do projeto SEI IA devem ser realizados pelo usuário de instalação (criado no passo anterior)!

```bash
su seiia
cd /opt
git clone https://github.com/anatelgovbr/sei-ia.git
cd sei-ia
```

**Observação**: embora não seja obrigatório fazer o download do SEI IA na pasta `/opt`, sugerimos **fortemente** que esse padrão seja seguido.

### 5. Configurações do Ambiente

| **IMPORTANTE**|
|--|
| É obrigatório que o arquivo `security.env` esteja **totalmente** configurado para que a instalação possa ser realizada! |

Editar e preencher no arquivo `env_files/security.env` as variáveis de ambiente de acesso ao banco de dados do SEI e configurações adicionais.

| Variável                          | Descrição                                                                           |
|-----------------------------------|-------------------------------------------------------------------------------------|
| `ENVIRONMENT`                     | Define o ambiente de execução da aplicação. Valores suportados: dev \| homol \| prod|
| `GID_DOCKER`²                     | GID do grupo Docker no host².                                                       |
| `DB_SEI_USER`                     | Usuário do banco de dados do SEI com permissão de leitura.                          |
| `DB_SEI_PWD`                      | Senha do usuário do banco de dados do SEI com permissão de leitura.                 |
| `DB_SEI_HOST`                     | Nome do host do banco de dados do SEI.                                              |
| `DB_SEI_DATABASE`                 | Nome do banco de dados do SEI.                                                      |
| `DB_SEI_PORT`                     | Porta do banco de dados do SEI.                                                     |
| `DB_SEI_SCHEMA`                   | Esquema do banco de dados do SEI.                                                   |
| `DATABASE_TYPE`                   | Tipo de banco de dados do SEI. Valores suportados: mysql \| mssql \| oracle         |
| `SEI_SOLR_ADDRESS`                | Endereço do servidor Solr do SEI.                                                   |
| `SEI_SOLR_CORE`                   | Core do servidor Solr utilizado para armazenar os documentos do SEI.                |
| `SEI_IAWS_URL`                    | URL de acesso à API IAWS do SEI.                                                    |
| `SEI_IAWS_KEY`                    | Chave de acesso à API IAWS do SEI.                                                  |
| `POSTGRES_DATABASE`               | **Não altere essa variável, pois ela já está devidamente preenchida.**              |
| `POSTGRES_USER`                   | Usuário do banco de dados Postgres da aplicação.                                    |
| `ASSISTENTE_PGVECTOR_USER`        | **Não altere essa variável, pois ela já está devidamente preenchida.**              |
| `ASSISTENTE_PGVECTOR_PWD`         | **Não altere essa variável, pois ela já está devidamente preenchida.**              |
| `POSTGRES_PASSWORD`               | Senha do banco de dados Postgres da aplicação.                                      |
| `OPENAI_API_VERSION`              | Versão da API da OpenAI.                                                            |
| `AZURE_OPENAI_ENDPOINT`           | Endpoint da Azure OpenAI.                                                           |
| `AZURE_OPENAI_ENDPOINT_GPT4o`     | Endpoint da API na Azure OpenAI para o modelo GPT-4o.                               |
| `AZURE_OPENAI_KEY_GPT4o`          | Chave de conexão à API da Azure OpenAI para o modelo GPT-4o.                        |
| `GPT_MODEL_4o_128k`               | Nome do modelo GPT-4o 128K na Azure OpenAI.                                         |
| `AZURE_OPENAI_ENDPOINT_GPT4o_mini`| Endpoint da API na Azure OpenAI para o modelo GPT-4o mini.                          |

¹ Caso você tenha dúvidas sobre o preenchimento mais apropriada para o seu caso, sugerimos conversar com sua equipe de TI sobre essa questão. Caso tenha somente um ambiente de execução para o SEI IA, então use a opção **prod**.
² **DICA**: se a configuração default do Docker não foi alterada, então você pode usar esse comando para obter o GID do docker `grep "^docker:" /etc/group | cut -d: -f3`


### 6. Subir a aplicação

Uma vez configurado o ambiente (passo anterior), a instalação será realizada integralmente ao rodar o script `deploy.sh`, como pode ser visto abaixo.

| **IMPORTANTE**|
|--|
| O comando abaixo deve ser executado pelo usuário de instalação (`seiia`) à partir da pasta de instalação (`/opt/sei-ia`)! |

```bash
sh ./deploy-externo-imgs.sh
```

O script `deploy-externo-imgs.sh` executa todos os comandos necessários para subir as aplicações necessárias (backend) para o módulo SEI IA.

Você pode verificar o status das aplicações rodando o comando abaixo:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

O comando acima deverá retornar algo semelhante ao texto abaixo:
```bash
NAMES                             STATUS
sei_ia-langfuse_assistente-1      Up 2 minutes
sei_ia-nginx_assistente-1         Up 2 minutes
sei_ia-pgvector_assistente_pd-1   Up 2 minutes (healthy)
sei_ia-api_assistente-1           Up 2 minutes
sei_ia-api_sei-1                  Up 2 minutes (healthy)
sei_ia-airflow-worker-2           Up 2 minutes (healthy)
sei_ia-airflow-scheduler-pd-1     Up 2 minutes (healthy)
sei_ia-airflow-worker-3           Up 2 minutes (healthy)
sei_ia-airflow-triggerer-pd-1     Up 2 minutes (healthy)
sei_ia-airflow-worker-1           Up 2 minutes (healthy)
sei_ia-airflow-webserver-pd-1     Up 2 minutes (healthy)
sei_ia-jobs_api-1                 Up 2 minutes
sei_ia-airflow_postgres-pd-1      Up 3 minutes (healthy)
sei_ia-rabbitmq-pd-1              Up 3 minutes (healthy)
sei_ia-pgvector_pd-1              Up 13 minutes (healthy)
sei_ia-solr_pd-1                  Up 13 minutes (healthy)

```

|**IMPORTANTE**|
|--|
| Pode acontecer que algumas aplicações ainda não estejam com status `healthy`, dependendo do tempo em que elas estão UP. Geralmente, de 2 a 4 minutos após o fim do script `deploy.sh`, todas as aplicações estarão no status `healthy`.|

### 7. Backup periódico dos dados das aplicações do SEI IA

Um ponto importante em relação ao uso do módulo SEI IA é a realização de backup periódico, principalmente dos bancos de dados utilizados pela aplicações.
Todos os dados das aplicações de backend do módulo SEI IA são armazenados em volumes Docker e, via de regra, estão localizados na pasta `/var/lib/docker/volume`.
O comando abaixo lista os volumes relacionados às aplicações de backend do módulo SEI IA:
```bash
docker volume ls|grep "^sei_ia-"
```

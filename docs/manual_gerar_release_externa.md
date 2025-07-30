# Guia Interno de Deploy para Externos
Esse guia tem por objetivo explicitar ao time SEI IA o fluxo de procedimentos para geração e atualização do deploy para externos.


## Padrão de nomes branch e tag 
A geração das imagens está interrelacionada com o sistema de tags do Gitlab para os projetos que compõem o SEI IA. 

O padrão para nome das branchs e tags nos projetos seguem a convenção de utilizar o formato `<versão>.<sufixo>.<correção>` para branchs e `v<versão>.<sufixo>.<correção>`.

```markdown
# Exemplo
**branch**: 1.1.0
**tag**: v1.1.0
```
## 1. Deploy externo
## 1.2. Geração das Imagens no Dockerhub

O script `externo/create_imgs_rc.py` é um programa interativo que vai solicitar algumas informações para a geração e upload das imagens no Dockerhub. 

```python
#trecho do script externo/create_imgs_rc.py
load_dotenv("env_files/security.env")
load_dotenv("env_files/default.env")
load_dotenv("env_files/prod.env")

GIT_TOKEN = os.environ["GIT_TOKEN"]
GIT_URL_SEIIA = f"https://oauth2:{GIT_TOKEN}@git.anatel.gov.br/processo_eletronico/sei-ia"
DOCKER_LOGIN = "anatelgovbr"
docker_compose_file = "docker-compose-prod.yaml"

repos_dict = [
    {
        "repo": "assistente",
        "tag": "1.1.2",
        "service": "api_assistente",
        "env_tag": "API_ASSISTENTE_VERSION",
        "dockerfile": "assistente.dockerfile",
        "url_repo": "assistente.git",
    },
    ...
```

O script irá carregar as variáveis de ambiente dos arquivos `env_files/security.env, env_files/default.env e env_files/prod.env` e seguir o fluxo para cada item da lista `repos_dict`. Caso seja necessário adicionar ou retirar um repositório basta alterar a lista. Explicação do fluxo do script:
1. **clone do repo** `repos_dict["repo"]`, na **tag** `repos_dict["tag"]`
1. **build da imagem** do `repos_dict["service"]:repos_dict["env_tag"]` utilizando o dockerfile `repos_dict["dockerfile"]`.
1. **checagem se as imagens foram criadas com sucesso**
1. **push para o dockerhub**

No início do script será solicitado a confirmação das tags e o desejo de realizar o push das imagens.

Sequência de passos para geração e upload das imagens do Dockehub:

1. Criação da branch 1.1.0, e tag v1.1.0 (no caso do exemplo acima) nos projetos **deploy**, **asistente**, **api**, **app-api** e **jobs** do SEI IA
1. `docker login -u anatelgovbr` (credenciais disponíveis no [Painel Produção da Anatel](https://painelproducao.anatel.gov.br/painelproducao/jsp/list-senha.jsp)).
1. execução do script `source .venv/bin/activate && python externo/create_imgs_rc.py` a partir da pasta raiz do projeto **deploy**

obs. Caso necessário, crie o ambiente virtual .venv e execute o comando `source .venv/bin/activate && pip install -e .`


## 1.2. Upload do SEI IA interno para o repositório SEI IA externo no Gitlab

Upload do SEI IA interno para o repositório SEI IA externo no Gitlab
O script externo/upload-seiia.sh automatiza o processo de transferência do código do repositório interno para o repositório externo, realizando as adaptações necessárias para o deploy externo.

O script realiza as seguintes operações:

1. Clonagem do repositório deploy a partir do Gitlab interno usando uma tag específica
1. Limpeza de arquivos , porém **mantem os arquivos e pastas necessários para o deploy externo**
1. Ajustes nos arquivos de configuração:
    
    * Remoção de variáveis sensíveis do security.env
    * Modificação do default.env para configurações externas
    * Desativação de recursos internos como Langfuse e telemetria
    * Substituição de arquivos específicos para o ambiente externo
1. Sincronização com o repositório externo no Gitlab

Sequência de passos para upload no repositório externo

* Certifique-se de que a tag desejada (ex: 1.1.0) já existe nos repositórios internos
* Execute o script a partir da pasta externo do projeto deploy:

```bash
cd externo && sh upload-seiia.sh --tag <TAG>
```



Obs:
* É necessário ter acesso SSH configurado para os repositórios do Gitlab
* O parâmetro --tag é obrigatório e deve corresponder a uma tag existente

## 1.3 Upload SEI IA Github  (ainda não implementado)

######## 


# 2. Dificuldades enfrentadas para o processo de migração 1.0 -> 1.1

Essa sessão tem por objetivo demonstrar as dificuldades enfrentadas e contornadas para o processo de migração da versão 1.0 para 1.1. Com o relato da experiência, tentar evitar para os próximos releases realizar alterações pontuais no nosso projeto base que futuramente possam se tornar entraves para a criação de um novo release.

## 2.1 Vários docker-compose, deploy*.sh e arquivos de configuração

para o deploy externo , tinhamos os arquivos:

```
@docker-compose-ext.yml
@docker-compose-prod.yml
@deploy.sh
@deploy-externo.sh
@env_files/security.env
@env_files/default.env
@env_files/prod.env
@externo/env_files/security.env
@externo/env_files/default.env
@externo/env_files/prod.env
```

Com essa replicação de arquivos, repetindo o mesmo código para o deploy interno e externo, nós caímos no problema clássico do not repeat yourself. Isso ocasionou arquivos praticamente idênticos para resolver a mesma coisa. Ao longo do desenvolvimento do nosso projeto, com melhorias e alterações no projeto interno, acaba degradando os outros arquivos específicos para o deploy externo, porque acabam não sendo atualizados. 

Por exemplo, o docker-compose-prod é praticamente igual docker-compose-ext. Uma alteração na linha do docker-compose-prod precisava ser replicado no docker-compose-ext. Esse mesmo processo pode ser refletido para o deploy.sh e o deploy-externo.sh, assim como a pasta env-files e externo env-files e seus arquivos de variáveis. Essa duplicação tornou os scripts para o deploy externo desatualizados e incompatível com a nossa realidade atual do projeto. do projeto. 


#### 2.1.1 Resolução - Replicação arquivos docker-compose:

Para o caso de arquivos docker-compose replicados, foi utilizada a estratégia de override, ou seja, apenas as linhas que necessitam de alteração no docker-compose-ext.yml (e demais arquivos compose) são declaradas. No momento de chamar o serviço para subir, é declarado o `-f <./docker-compose.yml>` após o arquivo padrão para que sejam substituídos apenas os trechos desejados. Vale destacar também , o uso do `--profile externo` para selecionar os serviços que irão deploy.

Exemplo:

```bash
docker compose --profile externo \
  -f docker-compose-prod.yaml \
  -f docker-compose-ext.yaml \
  -p $PROJECT_NAME \
  up \
  --no-build -d
```

### 2.1.2 Resolução - Replicação de variáveis de ambiente

Com o objetivo de evitar existir arquivos duplicados, a pasta externo/env_files para o deploy externo foi removida. 
Eu removi as variáveis que nós utilizamos apenas para o desenvolvimento interno durante o script de upload para o GitLab, `externo/upload-seiia.sh`, removendo as variáveis, pastas e arquivos desnecessários.

Para o caso de variáveis de ambiente que necessitam de serem adaptados para um novo formato, por exemplo, a variável de ambiente deve existir no deploy interno, externo, porém houve uma alteração no valor declarado ou no nome utilizado. Para isso foi criado o script de `externo/scripts/migracao/1.0_1.1/migracao_1.0_1.1.py`, basicamente ele faz um de-para entre o env files antigo para o env files da versão que será atualizada.

Por exemplo:

```
env_antiga (alteracao): SOLR_ADDRESS: http://... 
env_nova: SOLR_ADDRESS:$SOLR_HOST

env_antiga (copiar do arquivo env files antigo): DB_SEI_USER: <usuário já configurado>
env_nova: DB_SEI_USER: <usuário já configurado>
```


## 2.2 Bind de volumes

Na versão 1.0, nós tínhamos a declaração dos volumes dos serviços utilizando o bind padrão do docker, porém na versão nova, 1.1.0, nós utilizamos o bind do volume por caminho de diretório de rede.

### Resolução
Para a migração dos binds de volume, eu usei a estratégia do override, do Docker Composer, alterando as linhas que fazem os apontamentos de volume e adicionando um serviço a mais para realizar a cópia de arquivo do Solr que estavam desatualizados. 
Foi necessário também criar um novo arquivo de deploy.sh para que o script que levanta a stack utilizasse o override de volumes.

```
novos arquivos
@externo/scripts/migracao/1.0_1.1/docker-compose-vol-override-1.0-1.1.yml
@externo/scripts/migracao/1.0_1.1/deploy-externo-1.0-1.1.sh
```


## 2.3 Atualização do healthcheck

O health check faz checagem na configuração das variáveis de ambiente. Se as Dags do Airflow estão rodando, se a conexão com os bancos estão funcionando e se os serviços estão health.  A checagem funciona em sua maioria, com comparação `==` ou checagem de `status==200`.

Com a migração, temos as trocas de variáveis de ambiente, serviços, etc, e causa relatos de erros se não atualizado.  

### Resolução (ainda não implementada)

O script de migração `externo/scripts/migracao/1.0_1.1/migracao_1.0_1.1.py` foi um caminho para solucionar o healthcheck , uma vez que ele tenta ajustar as variáveis de ambiente, entretanto não foi suficiente e ainda é necessário atualizar o script e serviço do healthcheck conferindo como ele está checando as conexões das APIs com os bancos de dados . Acredito ter sido causado pela adoção do protocolo https:// mas necessita de análise. 


# Guia de Atualização do Servidor de Soluções de IA do módulo SEI IA

Esta seção descreve os procedimentos para atualizar a versão do Servidor de Soluções de IA quando envolve simples Update, relativo ao segundo dígito no controle de versões (v1.**x**.0). Por exemplo: da v1.0.**0** para v1.1.**0**; da v1.1.**0** para v1.2.**0**; da v1.2.**0** para v1.3.**0**.


## Atualização da v1.1.x para v1.2.x

Esta seção descreve o processo de migração do SEI IA versão 1.1.x para 1.2.x.

### Resumo das Alterações em Variáveis de Ambiente

#### security.env - Novas Variáveis (OBRIGATÓRIAS para o uso do WebSearch)

| Variável | Descrição |
|----------|-----------|
| `PROJECT_ENDPOINT` | URL base da API do Azure AI Projects |
| `AZURE_TENANT_ID` | Tenant (Azure AD) |
| `AZURE_SUBSCRIPTION_ID` | Assinatura Azure |
| `AGENT_ID` | Agente pré-configurado no Azure AI Studio |
| `AZURE_WEB_AGENT_ID` | Agente Web/Bot |
| `AZURE_CLIENT_SECRET` | Credencial sensível |
| `AZURE_CLIENT_ID` | ID do cliente do Registro de Aplicativo |
| `BING_CONNECTION_NAME` | Nome identificador do Bing Grounding |
| `MODEL_DEPLOYMENT_NAME` | Nome identificador do modelo configurado |

A integração com WebSearch (Bing Grounding) permite que o Assistente utilize informações externas (internet) para complementar respostas.

> **ATENÇÃO**:
> - Esta funcionalidade é **opcional**
> - Caso não seja configurada, o sistema continuará funcionando normalmente
> - Para desabilitar completamente, basta não configurar as variáveis abaixo e desativar a opção de WebSearch na Administração do SEI

Para utilização do WebSearch, é necessário:

1. Criar um registro de aplicativo no Entra ID para autenticação
2. Criar um projeto no Azure AI Foundry
3. Provisionar o recurso de Bing Grounding Search
4. Configurar um Agent no projeto
5. Criar uma conexão com o recurso de Bing Grounding  
   - Observação: a associação do Agent com o Bing Grounding está disponível apenas para modelos compatíveis (ex: GPT-4.1)
6. Associar a conexão ao Agent
7. Preencher as variáveis no arquivo `security.env`

##### Observações

- Caso as variáveis não sejam informadas:
  - O Assistente continuará funcionando normalmente
  - Apenas não realizará consultas externas, e essa funcionalidade deverá ser desabilitada na Administração do SEI
- Recomenda-se validar:
  - Permissões do aplicativo no Entra ID
  - Existência da conexão com Bing Grounding
  - Associação correta entre Agent e Connection
- Em ambientes com restrição de acesso à internet, recomenda-se manter o WebSearch desabilitado

#### security.env - Valores Alterados

| Variável | Versão 1.1.x | Versão 1.2.x |
|----------|--------------|--------------|
| `ASSISTENTE_TIMEOUT_API` | 600 | 900 |
| `ASSISTENTE_MAX_LENGTH_CHUNK_SIZE` | 512 | 1512 |
| `AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG` | 16 | 24 |
| `ASSISTENTE_MEM_LIMIT` | 2gb | 6gb |
| `ASSISTENTE_FATOR_LIMITAR_RAG` | 2 | 4 |
| `ASSISTENTE_OUTPUT_TOKENS_THINK_MODEL` | 100000 | 90000 |

#### security.env - Variáveis Removidas (movidas para llm_config/litellm_config.yaml)

As variáveis abaixo deixaram de existir no `security.env`. Seus valores devem ser configurados diretamente no arquivo `llm_config/litellm_config.yaml`:

- `OPENAI_API_VERSION` → campo `api_version` de cada modelo (novo valor: `2025-03-01-preview`)
- `ASSISTENTE_EMBEDDING_API_KEY` → campo `api_key` do modelo `embedding`
- `ASSISTENTE_EMBEDDING_ENDPOINT` → campo `api_base` do modelo `embedding`
- `ASSISTENTE_API_KEY_STANDARD_MODEL` → campo `api_key` do modelo `standard`
- `ASSISTENTE_ENDPOINT_STANDARD_MODEL` → campo `api_base` do modelo `standard`
- `ASSISTENTE_NAME_STANDARD_MODEL` → campo `model` do modelo `standard`
- `ASSISTENTE_API_KEY_MINI_MODEL` → campo `api_key` do modelo `mini`
- `ASSISTENTE_ENDPOINT_MINI_MODEL` → campo `api_base` do modelo `mini`
- `ASSISTENTE_NAME_MINI_MODEL` → campo `model` do modelo `mini`
- `ASSISTENTE_API_KEY_THINK_MODEL` → campo `api_key` do modelo `think`
- `ASSISTENTE_ENDPOINT_THINK_MODEL` → campo `api_base` do modelo `think`
- `ASSISTENTE_NAME_THINK_MODEL` → campo `model` do modelo `think`
- `ASSISTENTE_FATOR_LIMITAR_RAG_FALSO`

#### llm_config/litellm_config.yaml - Configuração Obrigatória

A partir da versão 1.2, o SEI IA utiliza o **LiteLLM Proxy** para centralizar as conexões com o Azure OpenAI. As API keys, endpoints e nomes dos modelos são configurados neste arquivo, e não mais no `security.env`.

Use o arquivo `llm_config/litellm_config_example.yaml` como referência. Para cada modelo (`standard`, `mini`, `think`, `embedding`), preencha:

| Campo | Descrição | Equivalente em 1.1.x |
|-------|-----------|----------------------|
| `api_base` | URL do endpoint Azure OpenAI | `ASSISTENTE_*_ENDPOINT_*_MODEL` |
| `api_key` | Chave de API Azure OpenAI | `ASSISTENTE_*_API_KEY_*_MODEL` |
| `model` | `azure/<nome do modelo implantado>` | `ASSISTENTE_NAME_*_MODEL` |
| `api_version` | Versão da API (`2025-03-01-preview`) | `OPENAI_API_VERSION` |

### Alterações em Docker Compose

1. **Volume Removido**: `airflow_jobs_vol:/home/airflow/app/jobs` não é mais mapeado
2. **Novo Serviço**: `redis_cache` (Redis 7.2-alpine) adicionado
3. **Healthcheck Alterado**: `api_assistente` agora usa Python ao invés de curl

### Instruções de Migração

#### Passo 1: Backup

```bash
# Criar backup dos arquivos de configuração em pasta temporária
cp -r env_files /tmp/env_files_1.1_backup

# Backup dos volumes (recomendado)
docker compose -p sei_ia down
tar -czvf backup_volumes_$(date +%Y%m%d).tar.gz /var/seiia/volumes/
```

#### Passo 2: Atualizar repositório

```bash
# Extrair o novo pacote de instalação
unzip sei-ia-externo-1.2.x.zip -d /diretorio/de/deploy
cd /diretorio/de/deploy/sei-ia-externo
```

#### Passo 3: Migrar Variáveis de Ambiente

Execute o script Python passando o caminho da pasta de backup criada no Passo 1:

```bash
cd [diretorio do deploy]
python migracao/1.1_1.2/migracao_1.1_1.2.py /tmp/env_files_1.1_backup
```

O script irá:
- Criar backup automático dos arquivos atuais em `env_files/backup_<timestamp>/`
- Copiar os valores personalizados de infraestrutura (banco, Solr, Airflow, SEI) para os novos arquivos
- Mostrar lista de ações necessárias ao final

> **Nota**: As variáveis de LLM (API keys, endpoints, nomes de modelos) **não são migradas** pelo script, pois foram movidas para `llm_config/litellm_config.yaml`. Configure-as manualmente conforme o Passo 4.

#### Passo 4: Configurar llm_config/litellm_config.yaml e security.env

**4a. Configurar o LiteLLM Proxy** — edite `llm_config/litellm_config.yaml` usando `llm_config/litellm_config_example.yaml` como referência, preenchendo os valores de `api_base`, `api_key` e `model` com os que estavam no `security.env` da versão 1.1.x:

```bash
nano llm_config/litellm_config.yaml
```

**4b. Configurar variáveis Azure** — As variáveis Azure Web Agent já estão presentes no `security.env` como `****`. Edite o arquivo e preencha os valores.

```bash
nano env_files/security.env
```

> **Nota**: Se não utilizar Azure Web Agent, mantenha os valores como `****`

**4c. `AIRFLOW__WEBSERVER__SECRET_KEY`** — Esta variável é **gerada automaticamente pelo script de deploy** caso não esteja presente em `env_files/security.env`. Nenhuma ação necessária.

#### Passo 5: Executar Migração

> **Atenção**: O script de deploy verifica automaticamente se o `llm_config/litellm_config.yaml` ainda contém valores de exemplo (`your-api-key-here`). Se sim, a execução é interrompida até que as credenciais sejam preenchidas.

```bash
chmod +x migracao/1.1_1.2/deploy-externo-1.1-1.2.sh
./migracao/1.1_1.2/deploy-externo-1.1-1.2.sh
```

## Atualização da v1.0.x para v1.1.x

- **Atenção**: Os volumes referentes ao airflow serão excluídos durante o processo.

Va para a pasta onde foi realizado o último deploy e seguida os passos para o Update:

1. Pare os containers:

```bash
cd [diretorio do deploy antigo]
docker stop $(docker ps -a -q)
```

2. Remova os containers:
   **ATENÇÃO**: Não remova os volumes!

```bash
docker rm $(docker ps -a -q)
```

3. Copiar os arquivos env_files antigo para um diretório temporário
```bash
mv env_files /tmp/env_files_old
```

4. Git fetch e trocar o repositório git para a branch 1.1.x
```bash
git fetch origin
git pull
git reset --hard
git checkout -b 1.1.x
```

```
5. Executar o script de migração das variáveis de ambiente. É necessário preencher o caminho da pasta em que a pasta env_files_old foi salva.
```bash
python migracao/1.0_1.1/migracao_1.0_1.1.py
```


6. Preencher as novas variáveis de ambiente no arquivo `env_files/security.env`:


| Variável                       | Descrição                                                                 | Exemplo                                      |
|--------------------------------|--------------------------------------------------------------------------|----------------------------------------------|
| `SOLR_USER`                    | Usuário de acesso ao Dashboard do Solr.                                  | `seiia` |
| `SOLR_PASSWORD`                | Senha do usuário de acesso ao Dashboard do Solr.                         | `solr_password` |
| `ASSISTENTE_EMBEDDING_API_KEY` | Chave de API para o assistente de embedding no Azure OpenAI Service.     | `minha_chave_embedding`                     |
| `ASSISTENTE_EMBEDDING_ENDPOINT`| Endpoint para o assistente de embedding no Azure OpenAI Service.        | `https://meuendpointembedding.openai.azure.com` |
| `ASSISTENTE_EMBEDDING_MODEL`      | Modelo de embeddings para o RAG do Assistente.          | `text-embedding-3-small`      |
| `ASSISTENTE_API_KEY_STANDARD_MODEL` | Chave de API para o modelo standard  | `sua_chave_standard` |
| `ASSISTENTE_ENDPOINT_STANDARD_MODEL` | URL do endpoint para o modelo standard  | `https://endpoint-standard.openai.azure.com` |
| `ASSISTENTE_NAME_STANDARD_MODEL` | Nome do modelo standard. | `gpt-4.1`   |
| `ASSISTENTE_API_KEY_MINI_MODEL` | Chave de API para o modelo mini  | `sua_chave_mini` |
| `ASSISTENTE_ENDPOINT_MINI_MODEL` | URL do endpoint para o modelo mini  | `https://endpoint-mini.openai.azure.com` |
| `ASSISTENTE_NAME_MINI_MODEL` | Nome do modelo mini.  | `gpt-4.1-mini` |
| `ASSISTENTE_API_KEY_THINK_MODEL` | Chave de API para o modelo think | `sua_chave_think` |
| `ASSISTENTE_ENDPOINT_THINK_MODEL` | URL do endpoint para o modelo think | `https://endpoint-think.openai.azure.com` |
| `ASSISTENTE_NAME_THINK_MODEL` | Nome do modelo think.  | `o4-mini` |

**Nota:** As variáveis DB_SEI_ do env antigo foram substituídas por variáveis SEI_API_DB_ no novo security.env, que abstraem o acesso ao banco de dados do SEI via API. Preencha essas com base nas configurações do seu ambiente SEI, conforme descrito na seção geral de configuração do security.env.

7. Executar o script de deploy apropriado para a migração

  Vamos criar os diretório que serão utilizados como `volume bind`
  ***IMPORTANTE*** : o usuário deve ter permissão sudo para criar os volumer no /var
  ```
  source env_files/default.env
  sudo mkdir --parents --mode=750 $VOL_SEIIA_DIR && sudo chown seiia:docker $VOL_SEIIA_DIR
  ```

  ```bash
  bash migracao/1.0_1.1/deploy-externo-1.0-1.1.sh
  ```

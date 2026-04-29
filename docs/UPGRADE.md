# Guia de Atualização — Servidor de Soluções de IA do SEI IA

Este guia descreve os procedimentos para atualizar a versão do *Servidor de Soluções de IA*. Cada seção cobre uma transição específica entre versões.

> **O processo de atualização do monorepo (a partir da v1.x para a próxima versão) ainda está em definição.** Este arquivo será atualizado quando o fluxo for fechado. Por enquanto, ele documenta as atualizações **anteriores** (v1.0 → v1.1 e v1.1 → v1.2), que ocorreram na estrutura antiga do projeto, e fornece um esboço preliminar do fluxo previsto para a estrutura monorepo.

---

## Sumário

- [Atualização para versões do monorepo (em definição)](#atualização-para-versões-do-monorepo-em-definição)
- [Atualização da v1.1.x para v1.2.x](#atualização-da-v11x-para-v12x)
- [Atualização da v1.0.x para v1.1.x](#atualização-da-v10x-para-v11x)

---

## Atualização para versões do monorepo (em definição)

> **Status**: o procedimento definitivo está sendo finalizado. Use este esboço como referência preliminar.

A nova estrutura do projeto (monorepo) muda alguns detalhes em relação ao processo antigo:

- Não existem mais os arquivos `env_files/{security,dev,homol,prod}.env`. Há **um único `security.env`** na raiz.
- Não existe mais `llm_config/litellm_config.yaml`. O arquivo é agora **`litellm_config.yaml`** na raiz, gerado a partir de `litellm_config.template.yaml`.
- Não existe mais `deploy-externo.sh`. Os comandos são `make up`, `make down` e `make check`.
- O código-fonte das aplicações está versionado neste repositório (`aplicacoes/`); o build pode ser feito local ou substituído por imagens pré-publicadas (ver `docker-compose.images.yml` no [INSTALL.md](INSTALL.md#102-usar-imagens-pré-publicadas-alternativa)).

### Esboço do fluxo de atualização

```bash
# 1. Backup dos arquivos de configuração e dos volumes
cp /opt/sei-ia/security.env          /tmp/security.env.bak
cp /opt/sei-ia/litellm_config.yaml   /tmp/litellm_config.yaml.bak
cp /opt/sei-ia/default.env           /tmp/default.env.bak

cd /opt/sei-ia
make down
sudo tar -czvf /tmp/backup_volumes_$(date +%Y%m%d).tar.gz /var/seiia/volumes/

# 2. Atualizar o repositório para a nova tag
cd /opt/sei-ia
git fetch --tags
git checkout <nova-tag>

# 3. Reconciliar variáveis de ambiente
#    - Comparar default.env do repositório com /tmp/default.env.bak (se houve customização local)
#    - Conferir security_example.env: novas variáveis precisam ser preenchidas em security.env
#    - Conferir litellm_config.template.yaml: novos modelos precisam ser refletidos em litellm_config.yaml
diff /tmp/default.env.bak /opt/sei-ia/default.env
diff <(grep -v '^#\|^$' /opt/sei-ia/security_example.env | cut -d= -f1) \
     <(grep -v '^#\|^$' /opt/sei-ia/security.env | cut -d= -f1)

# 4. Recriar o builder do Docker (caso o buildkitd.toml tenha mudado)
bash /opt/sei-ia/.gitlab/scripts/ensure_buildx_builder.sh

# 5. Subir a nova versão
make up

# 6. Validar
make check
```

> **Atenção**: a etapa 3 (reconciliar variáveis) é **a mais sensível**. Cada release deve descrever quais variáveis foram adicionadas, removidas ou alteradas, e este guia será atualizado com tabelas específicas a cada nova tag.

### O que verificar em cada release

- **Notas da release** no [GitHub](https://github.com/anatelgovbr/sei-ia/releases) — descrevem mudanças incompatíveis.
- **`security_example.env`** — novas variáveis ou variáveis removidas.
- **`litellm_config.template.yaml`** — novos campos ou aliases de modelos.
- **`default.env`** — mudanças em limites de CPU/memória ou novos parâmetros do Airflow.
- **`docker-compose.yml`** — novos serviços, mudança de imagens base, novos volumes.

---

## Atualização da v1.1.x para v1.2.x

> Esta seção se refere à **estrutura antiga** do projeto (anterior ao monorepo). É mantida aqui como referência para órgãos que estejam fazendo essa transição específica.

### Resumo das alterações em variáveis de ambiente

#### `security.env` — novas variáveis (obrigatórias para uso do WebSearch)

| Variável | Descrição |
|---|---|
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

> **Atenção**:
> - Esta funcionalidade é **opcional**.
> - Caso não seja configurada, o sistema continuará funcionando normalmente.
> - Para desabilitar completamente, basta não configurar as variáveis acima e desativar a opção de WebSearch na Administração do SEI.

Para habilitar:

1. Criar registro de aplicativo no Entra ID.
2. Criar projeto no Azure AI Foundry.
3. Provisionar o recurso Bing Grounding Search.
4. Configurar um Agent no projeto.
5. Criar uma conexão com o recurso Bing Grounding (associação Agent + Bing requer modelo compatível, ex.: GPT-4.1).
6. Associar a conexão ao Agent.
7. Preencher as variáveis acima em `security.env`.

#### `security.env` — valores alterados

| Variável | v1.1.x | v1.2.x |
|---|---|---|
| `ASSISTENTE_TIMEOUT_API` | 600 | 900 |
| `ASSISTENTE_MAX_LENGTH_CHUNK_SIZE` | 512 | 1512 |
| `AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG` | 16 | 24 |
| `ASSISTENTE_MEM_LIMIT` | 2gb | 6gb |
| `ASSISTENTE_FATOR_LIMITAR_RAG` | 2 | 4 |
| `ASSISTENTE_OUTPUT_TOKENS_THINK_MODEL` | 100000 | 90000 |

#### `security.env` — variáveis removidas (movidas para `litellm_config.yaml`)

As variáveis abaixo deixaram de existir no `security.env`. Os valores agora ficam em `litellm_config.yaml`:

- `OPENAI_API_VERSION` → `api_version` de cada modelo (novo valor: `2025-03-01-preview`)
- `ASSISTENTE_EMBEDDING_API_KEY` → `api_key` do modelo `embedding`
- `ASSISTENTE_EMBEDDING_ENDPOINT` → `api_base` do modelo `embedding`
- `ASSISTENTE_API_KEY_STANDARD_MODEL` → `api_key` do modelo `standard`
- `ASSISTENTE_ENDPOINT_STANDARD_MODEL` → `api_base` do modelo `standard`
- `ASSISTENTE_NAME_STANDARD_MODEL` → `model` do modelo `standard`
- `ASSISTENTE_API_KEY_MINI_MODEL` → `api_key` do modelo `mini`
- `ASSISTENTE_ENDPOINT_MINI_MODEL` → `api_base` do modelo `mini`
- `ASSISTENTE_NAME_MINI_MODEL` → `model` do modelo `mini`
- `ASSISTENTE_API_KEY_THINK_MODEL` → `api_key` do modelo `think`
- `ASSISTENTE_ENDPOINT_THINK_MODEL` → `api_base` do modelo `think`
- `ASSISTENTE_NAME_THINK_MODEL` → `model` do modelo `think`
- `ASSISTENTE_FATOR_LIMITAR_RAG_FALSO`

#### `litellm_config.yaml` — configuração obrigatória

A partir da v1.2 o SEI IA usa o **LiteLLM Proxy** para centralizar as conexões com Azure OpenAI. Para cada modelo (`standard`, `mini`, `think`, `embedding`), preencher:

| Campo | Descrição | Equivalente em v1.1.x |
|---|---|---|
| `api_base` | URL do endpoint Azure OpenAI | `ASSISTENTE_*_ENDPOINT_*_MODEL` |
| `api_key` | Chave de API Azure OpenAI | `ASSISTENTE_*_API_KEY_*_MODEL` |
| `model` | `azure/<nome do deployment>` | `ASSISTENTE_NAME_*_MODEL` |
| `api_version` | Versão da API (`2025-03-01-preview`) | `OPENAI_API_VERSION` |

### Alterações em Docker Compose

1. Volume `airflow_jobs_vol:/home/airflow/app/jobs` removido.
2. Novo serviço `redis_cache` (Redis 7.2-alpine) adicionado.
3. Healthcheck do `api_assistente` agora usa Python no lugar de curl.

### Instruções de migração (estrutura antiga, pré-monorepo)

#### Passo 1 — Backup

```bash
cp -r env_files /tmp/env_files_1.1_backup
docker compose -p sei_ia down
tar -czvf backup_volumes_$(date +%Y%m%d).tar.gz /var/seiia/volumes/
```

#### Passo 2 — Atualizar o repositório

```bash
unzip sei-ia-externo-1.2.x.zip -d /diretorio/de/deploy
cd /diretorio/de/deploy/sei-ia-externo
```

#### Passo 3 — Migrar variáveis

```bash
cd [diretorio do deploy]
python migracao/1.1_1.2/migracao_1.1_1.2.py /tmp/env_files_1.1_backup
```

O script:
- Cria backup automático em `env_files/backup_<timestamp>/`.
- Copia valores de banco, Solr, Airflow e SEI para os novos arquivos.
- Lista ações restantes ao final.

> As variáveis de LLM **não são migradas pelo script** (foram movidas para `llm_config/litellm_config.yaml`). Configure-as manualmente no Passo 4.

#### Passo 4 — Configurar `litellm_config.yaml` e `security.env`

**4a.** Edite `llm_config/litellm_config.yaml` usando `llm_config/litellm_config_example.yaml` como referência, preenchendo `api_base`, `api_key` e `model` com os valores que estavam no `security.env` da v1.1.x.

**4b.** Edite `env_files/security.env` e preencha as variáveis Azure Web Agent (presentes como `****`). Se não usar Azure Web Agent, mantenha `****`.

**4c.** `AIRFLOW__WEBSERVER__SECRET_KEY` é gerada automaticamente pelo script de deploy. Nenhuma ação necessária.

#### Passo 5 — Executar a migração

> O script de deploy verifica se `litellm_config.yaml` ainda contém `your-api-key-here` e aborta se sim, até as credenciais serem preenchidas.

```bash
chmod +x migracao/1.1_1.2/deploy-externo-1.1-1.2.sh
./migracao/1.1_1.2/deploy-externo-1.1-1.2.sh
```

---

## Atualização da v1.0.x para v1.1.x

> Esta seção se refere à **estrutura antiga** do projeto (anterior ao monorepo). Mantida como referência histórica.

> **Atenção**: os volumes do Airflow são **excluídos** durante o processo.

Vá para a pasta onde foi feito o último deploy:

#### 1. Parar os containers

```bash
cd [diretorio do deploy antigo]
docker stop $(docker ps -a -q)
```

#### 2. Remover os containers (não os volumes!)

```bash
docker rm $(docker ps -a -q)
```

#### 3. Mover `env_files` antigo para diretório temporário

```bash
mv env_files /tmp/env_files_old
```

#### 4. Atualizar o repositório para a branch 1.1.x

```bash
git fetch origin
git pull
git reset --hard
git checkout -b 1.1.x
```

#### 5. Migrar as variáveis de ambiente

```bash
python migracao/1.0_1.1/migracao_1.0_1.1.py
```

(Informe o caminho onde `env_files_old` foi salvo, conforme o prompt do script.)

#### 6. Preencher novas variáveis em `env_files/security.env`

| Variável | Descrição | Exemplo |
|---|---|---|
| `SOLR_USER` | Usuário do Dashboard do Solr. | `seiia` |
| `SOLR_PASSWORD` | Senha do Dashboard do Solr. | `solr_password` |
| `ASSISTENTE_EMBEDDING_API_KEY` | Chave de API do embedding (Azure OpenAI). | `minha_chave_embedding` |
| `ASSISTENTE_EMBEDDING_ENDPOINT` | Endpoint do embedding (Azure OpenAI). | `https://meu-endpoint.openai.azure.com` |
| `ASSISTENTE_EMBEDDING_MODEL` | Modelo de embeddings. | `text-embedding-3-small` |
| `ASSISTENTE_API_KEY_STANDARD_MODEL` | Chave do modelo standard. | `sua_chave_standard` |
| `ASSISTENTE_ENDPOINT_STANDARD_MODEL` | Endpoint do modelo standard. | `https://endpoint-standard.openai.azure.com` |
| `ASSISTENTE_NAME_STANDARD_MODEL` | Nome do modelo standard. | `gpt-4.1` |
| `ASSISTENTE_API_KEY_MINI_MODEL` | Chave do modelo mini. | `sua_chave_mini` |
| `ASSISTENTE_ENDPOINT_MINI_MODEL` | Endpoint do modelo mini. | `https://endpoint-mini.openai.azure.com` |
| `ASSISTENTE_NAME_MINI_MODEL` | Nome do modelo mini. | `gpt-4.1-mini` |
| `ASSISTENTE_API_KEY_THINK_MODEL` | Chave do modelo think. | `sua_chave_think` |
| `ASSISTENTE_ENDPOINT_THINK_MODEL` | Endpoint do modelo think. | `https://endpoint-think.openai.azure.com` |
| `ASSISTENTE_NAME_THINK_MODEL` | Nome do modelo think. | `o4-mini` |

> **Nota**: variáveis `DB_SEI_*` do env antigo foram substituídas por `SEI_API_DB_*` no novo `security.env`, abstraindo o acesso ao banco de dados do SEI via API. Preencha conforme as configurações do seu ambiente SEI.

#### 7. Executar o deploy

```bash
source env_files/default.env
sudo mkdir --parents --mode=750 $VOL_SEIIA_DIR && sudo chown seiia:docker $VOL_SEIIA_DIR
bash migracao/1.0_1.1/deploy-externo-1.0-1.1.sh
```

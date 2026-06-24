# Guia de Configuração: Integração com Google Cloud Vertex AI

Este guia orienta o administrador do sistema sobre como configurar o **SEI-IA** para utilizar a plataforma **Vertex AI** (Gemini Enterprise Agent Platform) do Google Cloud, habilitando modelos como Gemini, Gemma, Anthropic Claude, entre outros.

A integração é realizada de forma transparente utilizando o **LiteLLM Proxy** contido na stack do SEI-IA.

---

## Passo 1: Configuração no Google Cloud Platform (GCP)

Para permitir a autenticação do LiteLLM no Google Cloud, siga as etapas abaixo:

1. **Acessar o Console**: Vá para o [Google Cloud Console](https://console.cloud.google.com/).
2. **Selecionar o Projeto**: Escolha o projeto do GCP que deseja utilizar para faturamento e consumo das APIs de IA.
3. **Ativar a API do Vertex AI**:
   * Vá em **APIs & Services** > **Library**.
   * Busque por **Vertex AI API** e clique em **Enable**.
4. **Criar uma Conta de Serviço (Service Account)**:
   * Vá em **IAM & Admin** > **Service Accounts**.
   * Clique em **Create Service Account**.
   * Nomeie a conta (ex: `sei-ia-proxy`) e clique em **Create and Continue**.
5. **Conceder Permissões (Roles)**:
   * Na etapa de permissões, adicione a role **Vertex AI User** (`roles/aiplatform.user`).
   * Clique em **Done** para concluir a criação.
6. **Gerar a Chave de Acesso JSON**:
   * Na lista de contas de serviço, clique na conta criada.
   * Vá na aba **Keys** > **Add Key** > **Create New Key**.
   * Escolha o formato **JSON** e clique em **Create**.
   * O download do arquivo `.json` contendo as credenciais privadas será iniciado. Guarde esse arquivo em local seguro.

---

## Passo 2: Configuração no Servidor SEI-IA

No servidor onde a stack do SEI-IA está instalada, configure as variáveis de ambiente nos arquivos `.env` para carregar as credenciais do GCP.

### 1. No arquivo `default.env`
Certifique-se de que a região e o ID do projeto no GCP estão preenchidos:
```ini
LITELLM_VERTEX_PROJECT="seu-project-id-no-gcp"
LITELLM_VERTEX_LOCATION="us-central1" # Região de preferência para o Vertex AI
```

### 2. No arquivo `security.env`
Adicione o conteúdo do arquivo JSON da chave privada como uma string de linha única, além de mapear os modelos desejados:

```ini
# Configuração dos modelos apontando para o provedor Vertex AI
LITELLM_STANDARD_MODEL="vertex_ai/gemini-2.5-pro"
LITELLM_MINI_MODEL="vertex_ai/gemini-3.5-flash"
LITELLM_NANO_MODEL="vertex_ai/gemini-3.1-flash-lite"
LITELLM_EMBEDDING_MODEL="vertex_ai/gemini-embedding-2"

# JSON da conta de serviço obtido no Passo 1 (copie o conteúdo completo do arquivo .json e coloque em uma linha)
LITELLM_VERTEX_CREDENTIALS='{"type": "service_account", "project_id": "seu-project-id", ...}'
```

> [!TIP]
> Caso queira utilizar outros modelos suportados pelo Vertex AI Model Garden, basta definir o prefixo `vertex_ai/` seguido do nome do modelo no GCP. Exemplos:
> * `LITELLM_STANDARD_MODEL="vertex_ai/claude-sonnet-4-6"`
> * `LITELLM_STANDARD_MODEL="vertex_ai/gemma-4-26b-a4b-it-maas"`

---

## Passo 3: Aplicar as Configurações

Para regenerar a configuração do LiteLLM Proxy e reiniciar a stack de containers:

1. **Rodar o Script de Configuração**:
   Se você utiliza o GitLab CI ou rodar localmente no host:
   ```bash
   bash .gitlab/scripts/generate_config_files.sh
   ```
   *(Este comando lerá o template e as novas variáveis de ambiente para gerar o arquivo `litellm_config.yaml` mapeando corretamente as credenciais do Vertex AI).*

2. **Reiniciar os Serviços**:
   ```bash
   make down
   make up
   ```

3. **Verificar os Logs**:
   Certifique-se de que o container do LiteLLM iniciou sem erros de autenticação:
   ```bash
   docker compose logs infra-litellm
   ```

4. **Executar a Verificação Integrada**:
   Rode os testes internos para certificar-se de que a comunicação está funcionando:
   ```bash
   make check
   ```

# Guia de Integração: Google Cloud Vertex AI (Gemini Enterprise Agent Platform)

Este documento instrui o administrador sobre como integrar o **SEI-IA** com o **Vertex AI** (Gemini Enterprise Agent Platform) do Google Cloud, habilitando modelos como a família **Gemini 3.5 / 2.5**, **Gemma 4**, **Anthropic Claude**, **GPT-OSS**, entre outros.

---

## 1. Passo a Passo no Google Cloud Platform (GCP)

1. **Acessar o Console**: Entre no [Google Cloud Console](https://console.cloud.google.com/).
2. **Selecionar o Projeto**: Selecione o projeto GCP onde o Vertex AI será consumido.
3. **Habilitar a API do Vertex AI**:
   * Navegue até **APIs & Services** > **Library**.
   * Busque por **Vertex AI API** e clique em **Enable**.
4. **Criar uma Conta de Serviço (Service Account)**:
   * Acesse **IAM & Admin** > **Service Accounts**.
   * Clique em **Create Service Account**.
   * Defina um nome (ex.: `sei-ia-vertex-sa`) e avance.
5. **Conceder Permissão de Acesso**:
   * Atribua o papel (Role) **Vertex AI User** (`roles/aiplatform.user`).
6. **Gerar a Chave Privada em JSON**:
   * Selecione a Service Account criada > aba **Keys** > **Add Key** > **Create new key**.
   * Selecione o formato **JSON** e faça o download do arquivo `.json`.

---

## 2. Configuração no SEI-IA

No repositório do SEI-IA (em sua instalação de produção ou desenvolvimento):

### A. Variáveis de Ambiente (`env_files/security.env` e `env_files/default.env`)

No arquivo `env_files/default.env`:
```ini
export LITELLM_VERTEX_PROJECT="seu-projeto-gcp-id"
export LITELLM_VERTEX_LOCATION="us-central1"
```

No arquivo `env_files/security.env`:
```ini
export LITELLM_VERTEX_PROJECT="seu-projeto-gcp-id"
export LITELLM_VERTEX_LOCATION="us-central1"
# Cole o conteúdo do arquivo JSON da Service Account em uma única linha ou passe o caminho do arquivo:
export LITELLM_VERTEX_CREDENTIALS='{"type": "service_account", "project_id": "seu-projeto-gcp-id", ...}'
```

### B. Configuração do LiteLLM (`llm_config/litellm_config.yaml`)

Edite o arquivo `llm_config/litellm_config.yaml` (copiado a partir de `llm_config/litellm_config_example.yaml`) e defina os modelos desejados:

```yaml
model_list:
  - model_name: standard
    litellm_params:
      model: vertex_ai/gemini-2.5-pro # Ou vertex_ai/claude-sonnet-4-6, vertex_ai/gemma-4-26b-a4b-it-maas
      vertex_project: os.environ/LITELLM_VERTEX_PROJECT
      vertex_location: os.environ/LITELLM_VERTEX_LOCATION
      vertex_credentials: os.environ/LITELLM_VERTEX_CREDENTIALS
      max_completion_tokens: 32768
    model_info:
      base_model: gemini-2.5-pro

  - model_name: mini
    litellm_params:
      model: vertex_ai/gemini-3.5-flash # Ou vertex_ai/gemini-3.1-flash-lite, vertex_ai/claude-haiku-4-5
      vertex_project: os.environ/LITELLM_VERTEX_PROJECT
      vertex_location: os.environ/LITELLM_VERTEX_LOCATION
      vertex_credentials: os.environ/LITELLM_VERTEX_CREDENTIALS
      max_completion_tokens: 32768
    model_info:
      base_model: gemini-3.5-flash

  - model_name: think
    litellm_params:
      model: vertex_ai/gemini-2.5-pro # Ou vertex_ai/claude-opus-4-8, vertex_ai/gpt-oss-120b-maas
      vertex_project: os.environ/LITELLM_VERTEX_PROJECT
      vertex_location: os.environ/LITELLM_VERTEX_LOCATION
      vertex_credentials: os.environ/LITELLM_VERTEX_CREDENTIALS
      max_completion_tokens: 102400
      stream_timeout: 1800
      timeout: 1800
    model_info:
      base_model: gemini-2.5-pro

  - model_name: embedding
    litellm_params:
      model: vertex_ai/gemini-embedding-2
      vertex_project: os.environ/LITELLM_VERTEX_PROJECT
      vertex_location: os.environ/LITELLM_VERTEX_LOCATION
      vertex_credentials: os.environ/LITELLM_VERTEX_CREDENTIALS
    model_info:
      base_model: gemini-embedding-2
```

---

## 3. Aplicação do Deploy e Verificação

1. **Executar o Deploy Externo**:
   ```bash
   ./deploy-externo.sh
   ```

2. **Verificar a Saúde dos Serviços**:
   ```bash
   docker compose -f docker-compose-prod.yaml logs litellm
   ```

3. **Validação com Testes Integrados**:
   ```bash
   python3 -m tests.connectivity_tests
   ```

# Documentação da API do Servidor de Soluções do SEI IA

Aqui você pode encontrar uma breve descrição dos endpoints das APIs do servidor de soluções do SEI IA. O sistema é composto por:

- API Assistente de IA do servidor de soluções do SEI IA
- API de Recomendação de Processos e Documentos do servidor de soluções do SEI IA
- API SEI IA Feedback de Processos do servidor de soluções do SEI IA

---

## Assistente

### Endpoints

#### 1. Testes

##### `GET /tests`

Executa uma bateria de testes.

**Parâmetros:**

- `cached` (query) - Flag para utilizar o cache, se disponível. **Padrão:** `false`.

**Respostas:**

- **200**: Resposta bem-sucedida.
- **422**: Erro de validação.

---

#### 2. Testes de Timeout

##### `POST /tests/timeout/{timeout}`

Modelo de testes de timeout.

**Parâmetros:**

- `timeout` (path) - Tempo de espera em segundos antes de retornar a resposta.

**Respostas:**

- **200**: Resposta bem-sucedida.
- **422**: Erro de validação.

---

#### 3. Verificação de Saúde

##### `GET /health`

Realiza uma verificação de saúde da API.

**Respostas:**

- **200**: Retorna o status de saúde.

---

#### 4. Retorno de Documento

##### `GET /document/id_documento/{id_documento}`

Retorna o documento.

**Parâmetros:**

- `id_documento` (path) - ID do documento.

**Respostas:**

- **200**: Resposta bem-sucedida.
- **422**: Erro de validação.

---

#### 5. Retorno de Documento Externo

##### `GET /document/external/id_documento/{id_documento}`

Retorna o documento externo.

**Parâmetros:**

- `id_documento` (path) - ID do documento.

**Respostas:**

- **200**: Resposta bem-sucedida.
- **422**: Erro de validação.

---

#### 6. Retorno de Documento Interno

##### `GET /document/internal/id_documento/{id_documento}`

Retorna o documento interno.

**Parâmetros:**

- `id_documento` (path) - ID do documento.

**Respostas:**

- **200**: Resposta bem-sucedida.
- **422**: Erro de validação.

---

#### 7. Resposta do GPT-4 (128k)

##### `POST /llm_lang/chat_gpt_4o_128k`

Modelo de resposta do GPT-4.

**Corpo da Requisição:**

- **CompletationRequest2**: Representa uma solicitação de resposta do modelo GPT-4.

**Respostas:**

- **200**: Resposta bem-sucedida.
- **204**: Documento sem conteúdo.
- **400**: Requisição inválida.
- **401**: Falta chave para GPT.
- **403**: Acesso negado.
- **404**: Documento não encontrado.
- **422**: Texto no formato incorreto.
- **500**: Erro interno do servidor.

---

#### 8. Resposta do GPT-4 (128k)

##### `POST /llm_lang/chat_gpt_4_128k`

Modelo de resposta do GPT-4.

**Corpo da Requisição:**

- **CompletationRequest2**: Representa uma solicitação de resposta do modelo GPT-4.

**Respostas:**

- **200**: Resposta bem-sucedida.
- **204**: Documento sem conteúdo.
- **400**: Requisição inválida.
- **401**: Falta chave para GPT.
- **403**: Acesso negado.
- **404**: Documento não encontrado.
- **422**: Texto no formato incorreto.
- **500**: Erro interno do servidor.

---

#### 9. Resposta do GPT-4 Mini (128k)

##### `POST /llm_lang/chat_gpt_4o_mini_128k`

Modelo de resposta do GPT-4 Mini.

**Corpo da Requisição:**

- **CompletationRequest2**: Representa uma solicitação de resposta do modelo GPT-4 Mini.

**Respostas:**

- **200**: Resposta bem-sucedida.
- **204**: Documento sem conteúdo.
- **400**: Requisição inválida.
- **401**: Falta chave para GPT.
- **403**: Acesso negado.
- **404**: Documento não encontrado.
- **422**: Texto no formato incorreto.
- **500**: Erro interno do servidor.

---

#### 10. Feedback

##### `POST /feedback/feedback`

Feedback para resposta dos modelos.

**Corpo da Requisição:**

- **FeedbackRequest**: Representa uma solicitação de feedback.

**Respostas:**

- **200**: Retorna o número do ID de feedback.
- **422**: Erro de validação.

---

## API de Feedback do SEI IA

Grava o feedback do usuário sobre uma recomendação feita pela API de recomendação de processos SEI.

### Endpoints

#### 1. Inserir Feedback para Processos de Recomendação

- **Endpoint**: `/process-recommenders/feedbacks`
- **Método**: `POST`
- **Descrição**: Insere feedbacks para processos de recomendação na base de dados.

##### Requisição

**Request Body**:

```json
{
  "type": "array",
  "items": {
    "$ref": "#/components/schemas/Feedback"
  },
  "example": [
    {
      "id_recommendation": 1,
      "result": [
        {
          "id_recommended": 456,
          "like_flag": 1,
          "ranking_user": 1,
          "sugesty": "Sugestão 1",
          "racional": "Racional 1"
        },
        {
          "id_recommended": 789,
          "like_flag": 0,
          "ranking_user": 2,
          "sugesty": "Sugestão 2",
          "racional": "Racional 2"
        }
      ]
    }
  ]
}
```

##### Respostas

- **200**: Resposta bem-sucedida.
- **422**: Erro de validação.

---

#### 2. Inserir Feedback para Documentos de Recomendação

- **Endpoint**: `/document-recommenders/feedbacks`
- **Método**: `POST`
- **Descrição**: Insere feedbacks para documentos de recomendação na base de dados.

##### Requisição

**Request Body**:

```json
{
  "type": "array",
  "items": {
    "$ref": "#/components/schemas/Feedback"
  },
  "example": [
    {
      "id_recommendation": 1,
      "result": [
        {
          "id_recommended": 456,
          "like_flag": 1,
          "ranking_user": 1,
          "sugesty": "Sugestão 1",
          "racional": "Racional 1"
        },
        {
          "id_recommended": 789,
          "like_flag": 0,
          "ranking_user": 2,
          "sugesty": "Sugestão 2",
          "racional": "Racional 2"
        }
      ]
    }
  ]
}
```

##### Respostas

- **200**: Resposta bem-sucedida.
- **422**: Erro de validação.

---

#### 3. Realizar um Health Check

- **Endpoint**: `/health`
- **Método**: `GET`
- **Descrição**: Endpoint para realizar um health check.

##### Respostas

- **200**: Retorna o status de saúde do sistema.

```json
{
  "status": "OK",
  "timestamp": "2024-09-20 14:50:32"
}
```

---

## Documentação da API de Recomendação de Processos SEI

É uma API responsável pela recomendação de processos e documentos, calculada pela similaridade "More Like This" entre esses documentos.

### Endpoints

#### 1. Wmlt Process Recommendations By Id Protocolo

- **URL:** `/process-recommenders/weighted-mlt-recommender/recommendations/{id_protocolo}`
- **Método:** `GET`
- **Descrição:** Recomendações de processos ponderadas pelo ID do protocolo.
- **Parâmetros:**
  - `id_protocolo` (path, obrigatório): ID do protocolo, deve ser um número.
  - `id_user` (query, opcional): ID do usuário (inteiro ou nulo).
  - `rows` (query, opcional): Número de resultados a serem retornados (inteiro, padrão: 10).
  - `fq` (query, opcional): Filtros adicionais (array de strings ou nulo).
  - `debug` (query, opcional): Ativar modo de depuração (booleano, padrão: false).
  - `extraction_method` (query, opcional): Método de extração (enum: `bm25`, `lda`, `solr`, padrão: `solr`).
- **Respostas:**
  - **200 OK:** Resposta bem-sucedida, retorna um objeto JSON com as recomendações.
  - **422 Unprocessable Entity:** Erro de validação.

---

#### 2. Has Id Protocolo

- **URL:** `/process-recommenders/weighted-mlt-recommender/indexed-ids/{id_protocolo}`
- **Método:** `GET`
- **Descrição:** Verifica se o ID do protocolo existe.
- **Parâmetros:**
  - `id_protocolo` (path, obrigatório): ID do protocolo (inteiro).
- **Respostas:**
  - **200 OK:** Resposta bem-sucedida, retorna um objeto vazio.
  - **422 Unprocessable Entity:** Erro de validação.

---

#### 3. Get Doc2Doc Search

- **URL:** `/document-recommenders/mlt-recommender/recommendations`
- **Método:** `GET`
- **Descrição:** Realiza uma busca entre documentos.
- **Parâmetros:**
  - `text` (query, opcional): Texto para busca (string).
  - `list_id_doc` (query, opcional): Lista de IDs de documentos (array de inteiros).
  - `list_type_id_doc` (query, opcional): Lista de tipos de documentos (array de inteiros).
  - `rows` (query, opcional): Número de resultados a serem retornados (inteiro, padrão: 10).
  - `include_citations` (query, opcional): Incluir citações (booleano, padrão: false).
  - `text_weight` (query, opcional): Peso do texto na recomendação (número entre 0 e 1, padrão: 0.5).
  - `normalized` (query, opcional): Normalizar resultados (booleano, padrão: false).
  - `fq` (query, opcional): Filtros adicionais (array de strings).
  - `id_user` (query, opcional): ID do usuário (inteiro).
- **Respostas:**
  - **200 OK:** Resposta bem-sucedida, retorna um objeto JSON com os resultados.
  - **422 Unprocessable Entity:** Erro de validação.

---

#### 4. Perform a Health Check

- **URL:** `/health`
- **Método:** `GET`
- **Descrição:** Realiza uma verificação de saúde da API.
- **Respostas:**
  - **200 OK:** Retorna o status de saúde como um objeto JSON.

---

#### 5. Perform a Solr Health Check

- **URL:** `/health/solr`
- **Método:** `GET`
- **Descrição:** Realiza uma verificação de saúde do serviço Solr.
- **Parâmetros:**
  - `core_name` (query, opcional): Nome do núcleo Solr a ser verificado (string).
- **Respostas:**
  - **200 OK:** Retorna o status de saúde como um objeto JSON.
  - **422 Unprocessable Entity:** Erro de validação.

---

#### 6. Perform a Database Health Check

- **URL:** `/health/database`
- **Método:** `GET`
- **Descrição:** Verifica a conexão com o banco de dados.
- **Respostas:**
  - **200 OK:** Retorna o status de saúde como um objeto JSON.

---

#### 7. Perform a Process Recommendation Health Check

- **URL:** `/health/process-recommendation`
- **Método:** `GET`
- **Descrição:** Verifica a saúde do sistema criando uma recomendação de processo.
- **Respostas:**
  - **200 OK:** Retorna o status de saúde como um objeto JSON.

---

#### 8. Perform a Document Recommendation Health Check

- **URL:** `/health/document-recommendation`
- **Método:** `GET`
- **Descrição:** Verifica a saúde do sistema criando uma recomendação de documento.
- **Respostas:**
  - **200 OK:** Retorna o status de saúde como um objeto JSON.

--- 
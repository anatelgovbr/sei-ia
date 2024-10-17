# Documentacao de API

## Assistente

### Endpoints

#### 1. Testes

##### `GET /tests`

Executa bateria de testes.

**Parâmetros:**

* `cached` (query) - Flag para utilizar o cache, se disponível. **Padrão:** `false`.

**Respostas:**

* **200** : Resposta bem-sucedida.
* **422** : Erro de validação.

---

#### 2. Testes de Timeout

#### `POST /tests/timeout/{timeout}`

Modelo de testes de timeout.

**Parâmetros:**

* `timeout` (path) - Tempo de espera em segundos antes de retornar a resposta.

**Respostas:**

* **200** : Resposta bem-sucedida.
* **422** : Erro de validação.

---

#### 3. Verificação de Saúde

##### `GET /health`

Realiza uma verificação de saúde da API.

**Respostas:**

* **200** : Retorna o status de saúde.

---

#### 4. Retorno de Documento

##### `GET /document/id_documento/{id_documento}`

Retorna o documento.

**Parâmetros:**

* `id_documento` (path) - ID do documento.

**Respostas:**

* **200** : Resposta bem-sucedida.
* **422** : Erro de validação.

---

#### 5. Retorno de Documento Externo

##### `GET /document/external/id_documento/{id_documento}`

Retorna o documento externo.

**Parâmetros:**

* `id_documento` (path) - ID do documento.

**Respostas:**

* **200** : Resposta bem-sucedida.
* **422** : Erro de validação.

---

#### 6. Retorno de Documento Interno

#### `GET /document/internal/id_documento/{id_documento}`

Retorna o documento interno.

**Parâmetros:**

* `id_documento` (path) - ID do documento.

**Respostas:**

* **200** : Resposta bem-sucedida.
* **422** : Erro de validação.

---

#### 7. Resposta do GPT-4 (128k)

#### `POST /llm_lang/chat_gpt_4o_128k`

Modelo de resposta do GPT-4.

**Corpo da Requisição:**

* **CompletationRequest2** : Representa uma solicitação de resposta do modelo GPT-4.

**Respostas:**

* **200** : Resposta bem-sucedida.
* **204** : Documento sem conteúdo.
* **400** : Requisição inválida.
* **401** : Falta chave para GPT.
* **403** : Acesso negado.
* **404** : Documento não encontrado.
* **422** : Texto no formato incorreto.
* **500** : Erro interno do servidor.

---

#### 8. Resposta do GPT-4 (128k)

##### `POST /llm_lang/chat_gpt_4_128k`

Modelo de resposta do GPT-4.

**Corpo da Requisição:**

* **CompletationRequest2** : Representa uma solicitação de resposta do modelo GPT-4.

**Respostas:**

* **200** : Resposta bem-sucedida.
* **204** : Documento sem conteúdo.
* **400** : Requisição inválida.
* **401** : Falta chave para GPT.
* **403** : Acesso negado.
* **404** : Documento não encontrado.
* **422** : Texto no formato incorreto.
* **500** : Erro interno do servidor.

---

#### 9. Resposta do GPT-4 Mini (128k)

##### `POST /llm_lang/chat_gpt_4o_mini_128k`

Modelo de resposta do GPT-4 Mini.

**Corpo da Requisição:**

* **CompletationRequest2** : Representa uma solicitação de resposta do modelo GPT-4 Mini.

**Respostas:**

* **200** : Resposta bem-sucedida.
* **204** : Documento sem conteúdo.
* **400** : Requisição inválida.
* **401** : Falta chave para GPT.
* **403** : Acesso negado.
* **404** : Documento não encontrado.
* **422** : Texto no formato incorreto.
* **500** : Erro interno do servidor.

---

#### 10. Feedback

##### `POST /feedback/feedback`

Feedback para resposta dos modelos.

**Corpo da Requisição:**

* **FeedbackRequest** : Representa uma solicitação de feedback.

**Respostas:**

* **200** : Retorna o número do ID de feedback.
* **422** : Erro de validação.

---

### Componentes

#### Schemas

##### CompletationRequest2

Representa uma solicitação de resposta com ID do usuário, texto, prompt do sistema, ID do documento e temperatura.

##### DocumentResponse

Modelo de resposta que contém o conteúdo e tokens do documento.

##### FeedbackRequest

Modelo de solicitação de feedback com ID da mensagem, estrelas e comentário opcional.

##### HTTPValidationError

Modelo de erro de validação.

##### HealthCheck

Modelo de resposta para verificação de saúde.

##### IdProcedimentos

Modelo de identificação de procedimentos.

##### ValidationError

Modelo de erro de validação.

## Feedback

grava o feedback do usuario de uma recomendacao feita pela api  de recomendacao de processos SEI

### Endpoints

#### 1. Inserir Feedback para Processos de Recomendação

 **Endpoint** : `/process-recommenders/feedbacks`
 **Método** : `POST`
 **Descrição** : Insere feedbacks para processos de recomendação na base de dados.

##### Requisição

* **Request Body** :

{    "type": "array",
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

##### Respostas

* **200** : Resposta bem-sucedida.
* **422** : Erro de validação.

---

#### 2. Inserir Feedback para Documentos de Recomendação

 **Endpoint** : `/document-recommenders/feedbacks`
 **Método** : `POST`
 **Descrição** : Insere feedbacks para documentos de recomendação na base de dados.

##### Requisição

* **Request Body** :

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

##### Respostas

* **200** : Resposta bem-sucedida.
* **422** : Erro de validação.

---

#### 3. Realizar um Health Check

 **Endpoint** : `/health`
 **Método** : `GET`
 **Descrição** : Endpoint para realizar um health check.

##### Respostas

* **200** : Retorna o status de saúde do sistema.

{
    "status": "OK",
    "timestamp": "2024-09-20 14:50:32"
  }

---

### Componentes

#### Schemas

##### 1. Feedback

* **Descrição** : Classe que representa a requisição de feedback para um processo.
* **Atributos** :
* **id_recommendation** : `integer` - ID da recomendação de processo originária.
* **result** : `array of FeedbackItem` - Cada item avaliado pelo usuário.

##### 2. FeedbackItem

* **Descrição** : Classe que representa o resultado do feedback de um processo específico.
* **Atributos** :
* **id_recommended** : `integer` - ID recomendado.
* **like_flag** : `integer` - Avaliação do usuário em relação à recomendação de processo.
* **sugesty** : `string` - Sugestão do usuário.
* **racional** : `string` - Racional para a recomendação.
* **ranking_user** : `integer` - Ranking do usuário.

##### 3. HTTPValidationError

* **Descrição** : Classe para erros de validação.
* **Atributos** :
* **detail** : `array of ValidationError` - Detalhes sobre a validação.

##### 4. HealthCheck

* **Descrição** : Classe que representa o estado de saúde do sistema.
* **Atributos** :
* **status** : `string` - Status do sistema. Valor padrão é "OK".
* **timestamp** : `string` - Timestamp do status.

##### 5. ValidationError

* **Descrição** : Classe que representa um erro de validação.
* **Atributos** :
* **loc** : `array` - Localização do erro.
* **msg** : `string` - Mensagem de erro.
* **type** : `string` - Tipo de erro.

## Documentação da API de Recomendação de Processos SEI

É um API responsavel pela recomendacao de processos e documentos, calculado pela similaridade More Like This entre esses documentos.

### Endpoints

#### 1. Wmlt Process Recommendations By Id Protocolo

* **URL:** `/process-recommenders/weighted-mlt-recommender/recommendations/{id_protocolo}`
* **Método:** `GET`
* **Descrição:** Recomendações de processos ponderadas pelo ID do protocolo.
* **Parâmetros:**
  * `id_protocolo` (path, obrigatório): ID do protocolo, deve ser um número.
  * `id_user` (query, opcional): ID do usuário (inteiro ou nulo).
  * `rows` (query, opcional): Número de resultados a serem retornados (inteiro, padrão: 10).
  * `fq` (query, opcional): Filtros adicionais (array de strings ou nulo).
  * `debug` (query, opcional): Ativar modo de depuração (booleano, padrão: false).
  * `extraction_method` (query, opcional): Método de extração (enum: `bm25`, `lda`, `solr`, padrão: `solr`).
* **Respostas:**
  * **200 OK:** Resposta bem-sucedida, retorna um objeto JSON com as recomendações.
  * **422 Unprocessable Entity:** Erro de validação.

---

#### 2. Has Id Protocolo

* **URL:** `/process-recommenders/weighted-mlt-recommender/indexed-ids/{id_protocolo}`
* **Método:** `GET`
* **Descrição:** Verifica se o ID do protocolo existe.
* **Parâmetros:**
  * `id_protocolo` (path, obrigatório): ID do protocolo (inteiro).
* **Respostas:**
  * **200 OK:** Resposta bem-sucedida, retorna um objeto vazio.
  * **422 Unprocessable Entity:** Erro de validação.

---

#### 3. Get Doc2Doc Search

* **URL:** `/document-recommenders/mlt-recommender/recommendations`
* **Método:** `GET`
* **Descrição:** Realiza uma busca entre documentos.
* **Parâmetros:**
  * `text` (query, opcional): Texto para busca (string).
  * `list_id_doc` (query, opcional): Lista de IDs de documentos (array de inteiros).
  * `list_type_id_doc` (query, opcional): Lista de tipos de documentos (array de inteiros).
  * `rows` (query, opcional): Número de resultados a serem retornados (inteiro, padrão: 10).
  * `include_citations` (query, opcional): Incluir citações (booleano, padrão: false).
  * `text_weight` (query, opcional): Peso do texto na recomendação (número entre 0 e 1, padrão: 0.5).
  * `normalized` (query, opcional): Normalizar resultados (booleano, padrão: false).
  * `fq` (query, opcional): Filtros adicionais (array de strings).
  * `id_user` (query, opcional): ID do usuário (inteiro).
* **Respostas:**
  * **200 OK:** Resposta bem-sucedida, retorna um objeto JSON com os resultados.
  * **422 Unprocessable Entity:** Erro de validação.

---

#### 4. Perform a Health Check

* **URL:** `/health`
* **Método:** `GET`
* **Descrição:** Realiza um verificação de saúde da API.
* **Respostas:**
  * **200 OK:** Retorna o status de saúde como um objeto JSON.

---

#### 5. Perform a Solr Health Check

* **URL:** `/health/solr`
* **Método:** `GET`
* **Descrição:** Realiza uma verificação de saúde do serviço Solr.
* **Parâmetros:**
  * `core_name` (query, opcional): Nome do núcleo Solr a ser verificado (string).
* **Respostas:**
  * **200 OK:** Retorna o status de saúde como um objeto JSON.
  * **422 Unprocessable Entity:** Erro de validação.

---

#### 6. Perform a Database Health Check

* **URL:** `/health/database`
* **Método:** `GET`
* **Descrição:** Verifica a conexão com o banco de dados.
* **Respostas:**
  * **200 OK:** Retorna o status de saúde como um objeto JSON.

---

#### 7. Perform a Process Recommendation Health Check

* **URL:** `/health/process-recommendation`
* **Método:** `GET`
* **Descrição:** Verifica a saúde do sistema criando uma recomendação de processo.
* **Respostas:**
  * **200 OK:** Retorna o status de saúde como um objeto JSON.

---

#### 8. Perform a Document Recommendation Health Check

* **URL:** `/health/document-recommendation`
* **Método:** `GET`
* **Descrição:** Verifica a saúde do sistema criando uma recomendação de documento.
* **Respostas:**
  * **200 OK:** Retorna o status de saúde como um objeto JSON.

---

### Componentes

#### Esquemas

##### 1. DocumentRecommendation

* **Descrição:** Esquema para recomendação de documento.
* **Propriedades:**
  * `id_user`: ID do usuário (inteiro).
  * `id_documento`: ID do documento (inteiro).
  * `id_documento_consumed`: ID do documento consumido (inteiro).
  * `id_recomendacao_documento`: ID da recomendação do documento (inteiro ou nulo).

##### 2. ExtractionMethodEnum

* **Descrição:** Métodos de extração disponíveis.
* **Valores:** `bm25`, `lda`, `solr`.

##### 3. HTTPValidationError

* **Descrição:** Erro de validação.
* **Propriedades:**
  * `detail`: Detalhes sobre o erro (array de ValidationError).

##### 4. HealthCheck

* **Descrição:** Modelo de resposta para verificar a saúde.
* **Propriedades:**
  * `status`: Status da verificação (string).
  * `response_time`: Tempo de resposta (número ou nulo).

##### 5. ProcessRecommendation

* **Descrição:** Esquema para recomendação de processo.
* **Propriedades:**
  * `id_user`: ID do usuário (inteiro).
  * `id_protocolo`: ID do protocolo (inteiro).
  * `id_protocolo_consumed`: ID do protocolo consumido (inteiro).
  * `id_recomendacao_processo`: ID da recomendação do processo (inteiro ou nulo).

##### 6. RecommendationByIdProtocoloItem

* **Descrição:** Item de recomendação pelo ID do protocolo.
* **Propriedades:**
  * `id_protocolo`: ID do protocolo (string).
  * `score`: Pontuação (número).

##### 7. RecommnedationByIdProtocoloResponseWithRegisterRecommendation

* **Descrição:** Resposta com recomendações e registro.
* **Propriedades:**
  * `recommendation`: Lista de recomendações (array de RecommendationByIdProtocoloItem).
  * `debug`: Informação de depuração (objeto).
  * `id`: ID (inteiro).

##### 8. ValidationError

* **Descrição:** Erro de validação específico.
* **Propriedades:**
  * `loc`: Localização do erro (array de strings ou inteiros).
  * `msg`: Mensagem do erro (string).
  * `type`: Tipo do erro (string).

-- *****************************************
-- SEI SIMILARIDADE
CREATE DATABASE "${POSTGRES_DB_SIMILARIDADE}";

-- Switch to the target database context
\c "${POSTGRES_DB_SIMILARIDADE}"

CREATE EXTENSION IF NOT EXISTS vector;

ALTER DATABASE ${POSTGRES_DB_SIMILARIDADE} SET search_path TO public;
ALTER USER ${POSTGRES_USER} IN DATABASE ${POSTGRES_DB_SIMILARIDADE} SET search_path TO public;

CREATE TABLE IF NOT EXISTS "version_register" (
    id SERIAL PRIMARY KEY,
    hash VARCHAR(255),
    branch VARCHAR(255),
    tag VARCHAR(255),
    url VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- o funcionamento das DAGs para os externos depende da existência de pelo menos 1 registro nessa tabela
-- INSERT INTO version_register
--         (hash, branch, tag, url)
--         VALUES('HASH_EXTERNOS','BRANCH_EXTERNOS','TAG_EXTERNOS','EXTERNOS/jobs.git');

-- *****************************************
-- ASSISTENTE
CREATE DATABASE "${POSTGRES_DB}";

-- Switch to the target database context
\c "${POSTGRES_DB}"

CREATE SCHEMA "${POSTGRES_DB_ASSISTENTE_SCHEMA}";

CREATE EXTENSION IF NOT EXISTS vector;

ALTER DATABASE ${POSTGRES_DB} SET search_path TO ${POSTGRES_DB}, public;
ALTER USER ${POSTGRES_USER} IN DATABASE ${POSTGRES_DB} SET search_path TO ${POSTGRES_DB}, public;

SET search_path TO ${POSTGRES_DB}, public;

CREATE TABLE IF NOT EXISTS "models" (
    id SERIAL PRIMARY KEY,
    modelo VARCHAR(255) NOT NULL,
    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO models
        (modelo, created_on)
        VALUES('maritalk', CURRENT_TIMESTAMP);
INSERT INTO models
        (modelo, created_on)
        VALUES('GPT-35-4k', CURRENT_TIMESTAMP);
INSERT INTO models
        (modelo, created_on)
        VALUES('GPT-35-16k', CURRENT_TIMESTAMP);
INSERT INTO models
        (modelo, created_on)
        VALUES('GPT-4-8k', CURRENT_TIMESTAMP);
INSERT INTO models
        (modelo, created_on)
        VALUES('GPT-4-32k', CURRENT_TIMESTAMP);
INSERT INTO models
        (modelo, created_on)
        VALUES('GPT-4-turbo-128k', CURRENT_TIMESTAMP);
INSERT INTO models
        (modelo, created_on)
        VALUES('GPT-4o-128k', CURRENT_TIMESTAMP);
INSERT INTO models
        (modelo, created_on)
        VALUES('GPT-4o-mini-128k', CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS "requests" (
    id SERIAL PRIMARY KEY,
    endpoint_name VARCHAR NOT NULL,
    request TEXT,
    response TEXT,
    status_code INT NOT NULL,
    client_ip VARCHAR NOT NULL,
    id_usuario INT,
    id_message INT,
    intent_selector_jumped INT,
    intent_selector_code VARCHAR,
    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "messages" (
    id SERIAL PRIMARY KEY,
    id_usuario INTEGER,
    id_modelo INTEGER,
    temperatura FLOAT,
    prompt TEXT,
    system_prompt TEXT,
    assistent TEXT,
    n_tokens_prompt INTEGER,
    n_tokens_assistent INTEGER,
    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "ip_message" (
    id SERIAL PRIMARY KEY,
    full_req TEXT,
    id_message INTEGER,
    ip TEXT,
    id_documento TEXT,
    n_tokens_doc INTEGER,
    id_procedimentos TEXT,
    n_reqs INTEGER,
    endpoint_name TEXT,
    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "feedback" (
    id SERIAL PRIMARY KEY,
    id_mensagem INTEGER REFERENCES messages(id),
    stars INTEGER,
    comment TEXT,
    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "embeddings_400_50" (
  id_documento INT,
  chunk_id INT,
  embedding VECTOR,
  emb_text TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  metadata_ JSONB,
  PRIMARY KEY (id_documento, chunk_id)
);

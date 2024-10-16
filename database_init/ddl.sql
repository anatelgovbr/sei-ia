SET client_encoding = 'UTF8';
CREATE EXTENSION vector;


-- CREATE TABLE feedback_storage (
--   id SERIAL PRIMARY KEY,
--   id_prot_base BIGINT NOT NULL,
--   desc_prot_base VARCHAR(200),
--   id_prot_recommend BIGINT NOT NULL,
--   desc_prot_recommend VARCHAR(200),
--   like_flag INT,
--   racional VARCHAR(250),
--   similarity REAL,
--   ranking INT,
--   sugesty VARCHAR(500),
--   api_recommender_url VARCHAR(1000),
--   api_version VARCHAR(20),
--   app_version VARCHAR(20),
--   id_username BIGINT,
--   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
--   valid BOOLEAN,
--   username VARCHAR(20)
-- );

-- CREATE TABLE feedback_first_priority (
--   id_protocolo BIGINT PRIMARY KEY
-- );

-- CREATE TABLE feedback_second_priority (
--   id_protocolo BIGINT PRIMARY KEY
-- );

-- CREATE TABLE authentication_app (
--   id_usuario VARCHAR(200) PRIMARY KEY,
--   senha VARCHAR(200) NOT NULL,
--   nome VARCHAR(200) NOT NULL
-- );

CREATE TABLE log_consume (
  id SERIAL PRIMARY KEY,
  time_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  api_recomend_url TEXT NOT NULL,
  status_code INT NOT NULL,
  id_protocol BIGINT[] NOT NULL,
  id_user BIGINT
);

-- CREATE TABLE log_recommendations (
--     id SERIAL PRIMARY KEY,
--     id_protocolo_search BIGINT NOT NULL,
--     id_protocolo_interest BIGINT NOT NULL,
--     email_user VARCHAR(200) NOT NULL,
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- );

CREATE TABLE feedback_jurisprudence (
    id SERIAL PRIMARY KEY,
    id_recommendation BIGINT NOT NULL,
    id_recommended BIGINT NOT NULL,
    like_flag INTEGER NOT NULL,
    ranking_user INTEGER NOT NULL,
    sugesty VARCHAR(255),
    racional VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE log_update_mlt (
    id SERIAL PRIMARY KEY,
    id_tipo_procedimento INTEGER,
    id_protocolo VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dt_update TIMESTAMP NOT NULL,
    update_status VARCHAR(50),
    priority INTEGER NOT NULL
);


CREATE TABLE queue_update_mlt (
    id_tipo_procedimento INTEGER,
    id_protocolo VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dt_update TIMESTAMP NOT NULL,
    update_status VARCHAR(50),
    priority INTEGER NOT NULL,
    PRIMARY KEY (id_protocolo, update_status)
);

CREATE TABLE version_register (
    id SERIAL PRIMARY KEY,
    hash VARCHAR(255),
    branch VARCHAR(255),
    tag VARCHAR(255),
    url VARCHAR(255),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Função para armazenar na tabela log_update_mlt qualquer alteração ou inserção
CREATE OR REPLACE FUNCTION log_queue_update()
RETURNS TRIGGER AS $$
BEGIN
    -- Verificar se é uma inserção ou atualização
    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        INSERT INTO log_update_mlt (id_tipo_procedimento, id_protocolo, dt_update, update_status, priority)
        VALUES (NEW.id_tipo_procedimento, NEW.id_protocolo, NEW.dt_update, NEW.update_status, NEW.priority);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Trigger que chama a função definida acima na tabela queue_update_mlt
CREATE TRIGGER log_changes BEFORE INSERT OR UPDATE ON queue_update_mlt
FOR EACH ROW EXECUTE FUNCTION log_queue_update();

CREATE INDEX idx_log_protocolo_status_date ON log_update_mlt (id_protocolo, update_status, created_at);

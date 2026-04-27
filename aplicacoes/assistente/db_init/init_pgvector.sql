CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE SEI_LLM; -- Banco de dados para o monitorador langfuse
CREATE SCHEMA sei_llm;

SET search_path TO sei_llm, public;


CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    id_mensagem INTEGER REFERENCES messages(id),
    stars INTEGER,
    comment TEXT,
    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


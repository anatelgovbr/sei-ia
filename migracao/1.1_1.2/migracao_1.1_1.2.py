#!/usr/bin/env python3
"""
Script de migração de variáveis de ambiente da versão 1.1.x para 1.2.x do SEI IA.

Este script:
1. Faz backup dos arquivos de ambiente atuais
2. Copia security_example.env → security.env (base 1.2 limpa)
3. Injeta os valores personalizados do arquivo antigo (1.1.x) no novo arquivo

Uso:
    python migracao_1.1_1.2.py <caminho_para_arquivos_antigos>

Exemplo:
    python migracao_1.1_1.2.py /backup/env_files_1.1
"""

import os
import re
import shutil
import sys
from datetime import datetime


def read_env_file(file_path):
    """Lê variáveis de um arquivo .env, ignorando comentários."""
    env_vars = {}
    if os.path.exists(file_path):
        with open(file_path) as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith("#"):
                    match = re.match(r"(export\s+)?(\w+)=(.*)", line)
                    if match:
                        _, key, value = match.groups()
                        value = value.strip()
                        # Valor entre aspas duplas: extrai apenas o conteúdo interno,
                        # descartando qualquer comentário inline após o fechamento das aspas
                        if value.startswith('"'):
                            end = value.find('"', 1)
                            if end != -1:
                                value = value[1:end]
                        # Valor entre aspas simples: idem
                        elif value.startswith("'"):
                            end = value.find("'", 1)
                            if end != -1:
                                value = value[1:end]
                        else:
                            # Valor sem aspas: remove comentário inline (# precedido de espaço)
                            value = re.sub(r"\s+#.*$", "", value).strip()
                        env_vars[key.strip()] = value
    return env_vars


def update_env_file(new_file_path, mapping, old_vars):
    """Atualiza o arquivo .env com valores do arquivo antigo."""
    if not os.path.exists(new_file_path):
        print(f"Aviso: O arquivo {new_file_path} não existe.")
        return set()

    with open(new_file_path) as file:
        lines = file.readlines()

    updated_lines = []
    updated_vars = set()

    for line in lines:
        stripped_line = line.strip()
        if stripped_line and not stripped_line.startswith("#"):
            match = re.match(r"(export\s+)?(\w+)=(.+)", stripped_line)
            if match:
                export_prefix, key, current_value = match.groups()
                export_prefix = export_prefix or ""

                if key in mapping:
                    old_key = mapping[key]
                    if old_key in old_vars:
                        new_value = old_vars[old_key]
                        # Adiciona aspas apenas se o valor contém espaços ou tabs
                        if " " in new_value or "\t" in new_value:
                            new_value = f'"{new_value}"'
                        updated_lines.append(f"{export_prefix}{key}={new_value}\n")
                        updated_vars.add(key)
                        continue

        updated_lines.append(line)

    with open(new_file_path, "w") as file:
        file.writelines(updated_lines)

    return updated_vars


def prepare_security_env(env_dir):
    """Copia security_example.env → security.env para usar o template 1.2 como base."""
    example = os.path.join(env_dir, "security_example.env")
    dest = os.path.join(env_dir, "security.env")

    if not os.path.exists(example):
        print(
            f"  - Aviso: {example} não encontrado. Usando security.env existente como base."
        )
        return False

    shutil.copy2(example, dest)
    print("  - Template 1.2 copiado: security_example.env -> security.env")
    return True


def backup_files(env_dir):
    """Cria backup dos arquivos de ambiente."""
    backup_dir = os.path.join(
        env_dir, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(backup_dir, exist_ok=True)

    for env_file in ["default.env", "prod.env", "security.env", "homol.env", "dev.env"]:
        src = os.path.join(env_dir, env_file)
        if os.path.exists(src):
            dst = os.path.join(backup_dir, env_file)
            shutil.copy2(src, dst)
            print(f"  - Backup: {env_file} -> {backup_dir}/")

    return backup_dir


# Mapeamento de variáveis: chave_nova -> chave_antiga
# Variáveis que mantêm o mesmo nome mas precisam ser preservadas.
#
# NOTA: variáveis de LLM (API keys, endpoints, nomes de modelos, tokens, embeddings)
# NÃO são migradas aqui. Na versão 1.2 essas configurações foram movidas para
# llm_config/litellm_config.yaml e devem ser configuradas manualmente nesse arquivo.
MAPPING_SECURITY = {
    "GID_DOCKER": "GID_DOCKER",
    "ENVIRONMENT": "ENVIRONMENT",
    "DB_SEIIA_USER": "DB_SEIIA_USER",
    "DB_SEIIA_PWD": "DB_SEIIA_PWD",
    "SOLR_USER": "SOLR_USER",
    "SOLR_PASSWORD": "SOLR_PASSWORD",
    "_AIRFLOW_WWW_USER_USERNAME": "_AIRFLOW_WWW_USER_USERNAME",
    "_AIRFLOW_WWW_USER_PASSWORD": "_AIRFLOW_WWW_USER_PASSWORD",
    "AIRFLOW_POSTGRES_USER": "AIRFLOW_POSTGRES_USER",
    "AIRFLOW_POSTGRES_PASSWORD": "AIRFLOW_POSTGRES_PASSWORD",
    "AIRFLOW_AMQP_USER": "AIRFLOW_AMQP_USER",
    "AIRFLOW_AMQP_PASSWORD": "AIRFLOW_AMQP_PASSWORD",
    "SEI_ADDRESS": "SEI_ADDRESS",
    "SEI_API_DB_IDENTIFIER_SERVICE": "SEI_API_DB_IDENTIFIER_SERVICE",
    "SEI_API_DB_TIMEOUT": "SEI_API_DB_TIMEOUT",
    "SEI_API_DB_USER": "SEI_API_DB_USER",
}

MAPPING_DEFAULT = {
    "VOL_SEIIA_DIR": "VOL_SEIIA_DIR",
    "AIRFLOW_UID": "AIRFLOW_UID",
    "AIRFLOW_PROJ_DIR": "AIRFLOW_PROJ_DIR",
    "SOLR_HOST": "SOLR_HOST",
    "SOLR_ADDRESS": "SOLR_ADDRESS",
    "SOLR_MLT_JURISPRUDENCE_CORE": "SOLR_MLT_JURISPRUDENCE_CORE",
    "SOLR_MLT_PROCESS_CORE": "SOLR_MLT_PROCESS_CORE",
    "DB_SEIIA_HOST": "DB_SEIIA_HOST",
    "DB_SEIIA_PORT": "DB_SEIIA_PORT",
    "DB_SEIIA_SIMILARIDADE": "DB_SEIIA_SIMILARIDADE",
    "DB_SEIIA_ASSISTENTE": "DB_SEIIA_ASSISTENTE",
    "DB_SEIIA_ASSISTENTE_SCHEMA": "DB_SEIIA_ASSISTENTE_SCHEMA",
    "ASSISTENTE_MAX_RETRIES": "ASSISTENTE_MAX_RETRIES",
    "ASSISTENTE_TOKEN_MAX": "ASSISTENTE_TOKEN_MAX",
    "ASSISTENTE_TESTS_ID_DOC_INT": "ASSISTENTE_TESTS_ID_DOC_INT",
    "ASSISTENTE_TESTS_ID_DOC_EXT": "ASSISTENTE_TESTS_ID_DOC_EXT",
    "ASSISTENTE_EMBEDDING_PROVIDER": "ASSISTENTE_EMBEDDING_PROVIDER",
    "ASSISTENTE_CHUNK_OVERLAP": "ASSISTENTE_CHUNK_OVERLAP",
    "LIB_CONNECTION": "LIB_CONNECTION",
}

MAPPING_PROD = {
    "LOG_LEVEL": "LOG_LEVEL",
    "AIRFLOW__CELERY__WORKER_CONCURRENCY": "AIRFLOW__CELERY__WORKER_CONCURRENCY",
    "AIRFLOW_WORKERS_REPLICAS": "AIRFLOW_WORKERS_REPLICAS",
    "AIRFLOW_WORKER_MEM_LIMIT": "AIRFLOW_WORKER_MEM_LIMIT",
    "AIRFLOW_WORKER_CPU_LIMIT": "AIRFLOW_WORKER_CPU_LIMIT",
    "AIRFLOW_POSTGRES_MEM_LIMIT": "AIRFLOW_POSTGRES_MEM_LIMIT",
    "AIRFLOW_POSTGRES_CPU_LIMIT": "AIRFLOW_POSTGRES_CPU_LIMIT",
    "RABBITMQ_MEM_LIMIT": "RABBITMQ_MEM_LIMIT",
    "RABBITMQ_CPU_LIMIT": "RABBITMQ_CPU_LIMIT",
    "AIRFLOW_WEBSERVER_MEM_LIMIT": "AIRFLOW_WEBSERVER_MEM_LIMIT",
    "AIRFLOW_WEBSERVER_CPU_LIMIT": "AIRFLOW_WEBSERVER_CPU_LIMIT",
    "AIRFLOW_SCHEDULER_MEM_LIMIT": "AIRFLOW_SCHEDULER_MEM_LIMIT",
    "AIRFLOW_SCHEDULER_CPU_LIMIT": "AIRFLOW_SCHEDULER_CPU_LIMIT",
    "AIRFLOW_SCHEDULER_CPU_SHARES": "AIRFLOW_SCHEDULER_CPU_SHARES",
    "AIRFLOW_TRIGGERER_MEM_LIMIT": "AIRFLOW_TRIGGERER_MEM_LIMIT",
    "AIRFLOW_TRIGGERER_CPU_LIMIT": "AIRFLOW_TRIGGERER_CPU_LIMIT",
    "API_SEI_MEM_LIMIT": "API_SEI_MEM_LIMIT",
    "API_SEI_CPU_LIMIT": "API_SEI_CPU_LIMIT",
    "APP_API_MEM_LIMIT": "APP_API_MEM_LIMIT",
    "APP_API_CPU_LIMIT": "APP_API_CPU_LIMIT",
    "SOLR_JAVA_MEM": "SOLR_JAVA_MEM",
    "SOLR_MEM_LIMIT": "SOLR_MEM_LIMIT",
    "SOLR_CPU_LIMIT": "SOLR_CPU_LIMIT",
    "PGVECTOR_MEM_LIMIT": "PGVECTOR_MEM_LIMIT",
    "PGVECTOR_CPU_LIMIT": "PGVECTOR_CPU_LIMIT",
    "ASSISTENTE_CPU_LIMIT": "ASSISTENTE_CPU_LIMIT",
    "ASSISTENTE_NGINX_MEM_LIMIT": "ASSISTENTE_NGINX_MEM_LIMIT",
    "ASSISTENTE_NGINX_CPU_LIMIT": "ASSISTENTE_NGINX_CPU_LIMIT",
    "ASSISTENTE_CONTEXT_MAX_TOKENS": "ASSISTENTE_CONTEXT_MAX_TOKENS",
    "LANGFUSE_MEM_LIMIT": "LANGFUSE_MEM_LIMIT",
    "LANGFUSE_CPU_LIMIT": "LANGFUSE_CPU_LIMIT",
    "CADVISOR_MEM_LIMIT": "CADVISOR_MEM_LIMIT",
    "CADVISOR_CPU_LIMIT": "CADVISOR_CPU_LIMIT",
    "NODE_EXPORTER_MEM_LIMIT": "NODE_EXPORTER_MEM_LIMIT",
    "NODE_EXPORTER_CPU_LIMIT": "NODE_EXPORTER_CPU_LIMIT",
    "EMBEDDING_MAX_ACTIVE_RUNS": "EMBEDDING_MAX_ACTIVE_RUNS",
}


def main():
    print("=" * 70)
    print("  MIGRAÇÃO SEI IA: Versão 1.1.x -> 1.2.x")
    print("=" * 70)
    print()

    # Verificar argumentos
    if len(sys.argv) < 2:
        old_dir = input(
            "Digite o caminho para o diretório dos arquivos antigos (env_files da versão 1.1.x): "
        ).strip()
    else:
        old_dir = sys.argv[1]

    if not os.path.exists(old_dir):
        print(f"Erro: O diretório {old_dir} não existe.")
        sys.exit(1)

    new_dir = "env_files"
    if not os.path.exists(new_dir):
        print(
            f"Erro: O diretório {new_dir} não existe. Execute este script a partir do diretório de deploy."
        )
        sys.exit(1)

    # Verificar arquivos necessários
    required_old_files = ["security.env"]
    for f in required_old_files:
        if not os.path.exists(os.path.join(old_dir, f)):
            print(f"Erro: Arquivo obrigatório {f} não encontrado em {old_dir}")
            sys.exit(1)

    print(f"Diretório de origem (1.1.x): {old_dir}")
    print(f"Diretório de destino (1.2.x): {new_dir}")
    print()

    # Criar backup dos arquivos atuais (antes de qualquer alteração)
    print("[1/4] Criando backup dos arquivos atuais...")
    backup_dir = backup_files(new_dir)
    print(f"  - Backup criado em: {backup_dir}")
    print()

    # Preparar security.env a partir do template 1.2
    print("[2/4] Preparando security.env com template da versão 1.2...")
    prepare_security_env(new_dir)
    print()

    # Ler arquivos antigos
    print("[3/4] Lendo variáveis dos arquivos antigos e aplicando migração...")
    old_security = read_env_file(os.path.join(old_dir, "security.env"))
    old_default = (
        read_env_file(os.path.join(old_dir, "default.env"))
        if os.path.exists(os.path.join(old_dir, "default.env"))
        else {}
    )
    old_prod = (
        read_env_file(os.path.join(old_dir, "prod.env"))
        if os.path.exists(os.path.join(old_dir, "prod.env"))
        else {}
    )

    print(f"  - security.env: {len(old_security)} variáveis lidas")
    print(f"  - default.env: {len(old_default)} variáveis lidas")
    print(f"  - prod.env: {len(old_prod)} variáveis lidas")

    # Security.env
    if old_security:
        updated = update_env_file(
            os.path.join(new_dir, "security.env"), MAPPING_SECURITY, old_security
        )
        print(f"  - security.env: {len(updated)} variáveis migradas")

    # Default.env
    if old_default:
        updated = update_env_file(
            os.path.join(new_dir, "default.env"), MAPPING_DEFAULT, old_default
        )
        print(f"  - default.env: {len(updated)} variáveis migradas")

    # Prod.env
    if old_prod:
        updated = update_env_file(
            os.path.join(new_dir, "prod.env"), MAPPING_PROD, old_prod
        )
        print(f"  - prod.env: {len(updated)} variáveis migradas")
    print()

    print("[4/4] Verificando variáveis Azure no security.env...")
    print(
        "  - As variáveis Azure Web Agent estão no security.env como placeholders ****."
    )
    print("  - Preencha-as manualmente conforme as AÇÕES NECESSÁRIAS abaixo.")
    print()

    # Resumo final
    print("=" * 70)
    print("  MIGRAÇÃO CONCLUÍDA")
    print("=" * 70)
    print()
    print("AÇÕES NECESSÁRIAS:")
    print()
    print("1. PREENCHA AS VARIÁVEIS NO security.env:")
    print("   As variáveis Azure Web Agent estão marcadas com **** no arquivo")
    print("   env_files/security.env. Preencha-as diretamente:")
    print("     - PROJECT_ENDPOINT")
    print("     - AZURE_TENANT_ID")
    print("     - AZURE_SUBSCRIPTION_ID")
    print("     - AGENT_ID / AZURE_WEB_AGENT_ID")
    print("     - AZURE_CLIENT_SECRET / AZURE_CLIENT_ID")
    print("     - BING_CONNECTION_NAME")
    print("     - MODEL_DEPLOYMENT_NAME")
    print()
    print("2. CONFIGURE O ARQUIVO llm_config/litellm_config.yaml:")
    print("   Use llm_config/litellm_config_example.yaml como referência.")
    print("   Localize no seu security.env da versão 1.1.x os valores antigos e")
    print("   preencha para cada modelo (standard, mini, think, embedding):")
    print("     - api_base:    ASSISTENTE_*_ENDPOINT / ASSISTENTE_EMBEDDING_ENDPOINT")
    print("     - api_key:     ASSISTENTE_*_API_KEY  / ASSISTENTE_EMBEDDING_API_KEY")
    print("     - model:       azure/<ASSISTENTE_NAME_*_MODEL>")
    print('     - api_version: "2025-03-01-preview"  (atualizado de 2024-10-21)')
    print()
    print("3. VERIFIQUE MUDANÇAS DE VALORES PADRÃO (default.env / prod.env):")
    print("     - ASSISTENTE_TIMEOUT_API: 600 -> 900")
    print("     - ASSISTENTE_MAX_LENGTH_CHUNK_SIZE: 512 -> 1512")
    print("     - AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG: 16 -> 24")
    print("     - ASSISTENTE_MEM_LIMIT: 2gb -> 6gb")
    print("     - ASSISTENTE_FATOR_LIMITAR_RAG: 2 -> 4")
    print("     - ASSISTENTE_OUTPUT_TOKENS_THINK_MODEL: 100000 -> 90000")
    print()
    print("4. EXECUTE O SCRIPT DE DEPLOY:")
    print("   ./deploy-externo-1.1-1.2.sh")
    print()
    print("5. EM CASO DE PROBLEMAS, RESTAURE O BACKUP DE:")
    print(f"   {backup_dir}")
    print()


if __name__ == "__main__":
    main()

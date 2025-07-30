import os
import re

# Função para ler variáveis de um arquivo .env antigo, ignorando comentários
def read_old_env_file(file_path):
    env_vars = {}
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Extrair chave e valor, considerando 'export'
                    match = re.match(r'(export\s+)?(\w+)=(.+)', line)
                    if match:
                        _, key, value = match.groups()
                        env_vars[key.strip()] = value.strip()
    return env_vars

# Função para atualizar o novo arquivo .env, mantendo 'export' e ordem
def update_new_env_file(new_file_path, mapping, old_vars):
    # Se o arquivo novo não existir, criar um vazio
    if not os.path.exists(new_file_path):
        print(f"Aviso: O arquivo {new_file_path} não existe. Criando um novo arquivo.")
        with open(new_file_path, 'w') as file:
            pass  # Arquivo vazio

    # Ler o conteúdo atual do arquivo novo
    with open(new_file_path, 'r') as file:
        lines = file.readlines()

    updated_lines = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line and not stripped_line.startswith('#'):
            # Verificar se a linha contém uma variável
            match = re.match(r'(export\s+)?(\w+)=(.+)', stripped_line)
            if match:
                export_prefix, key, _ = match.groups()
                export_prefix = export_prefix or ''  # Preserva 'export ' se presente
                # Verificar se a chave está no mapeamento
                for old_key, new_key in mapping.items():
                    if key == new_key:
                        for old_file_vars in old_vars.values():
                            if old_key in old_file_vars:
                                new_value = old_file_vars[old_key]
                                updated_lines.append(f"{export_prefix}{key}={new_value}\n")
                                break
                        else:
                            updated_lines.append(line)  # Mantém a linha original se não houver atualização
                        break
                else:
                    updated_lines.append(line)  # Mantém a linha original se não estiver no mapeamento
            else:
                updated_lines.append(line)  # Mantém linhas que não são variáveis
        else:
            updated_lines.append(line)  # Mantém comentários e linhas vazias

    # Escrever as linhas atualizadas de volta no arquivo
    with open(new_file_path, 'w') as file:
        file.writelines(updated_lines)

# Mapeamento de variáveis antigas para novas (mantido igual ao seu)
mapping = {
    'default.env': {
        'PROJECT_NAME': 'PROJECT_NAME',
        'AIRFLOW_UID': 'AIRFLOW_UID',
        'AIRFLOW_PROJ_DIR': 'AIRFLOW_PROJ_DIR',
        'SOLR_MLT_JURISPRUDENCE_CORE': 'SOLR_MLT_JURISPRUDENCE_CORE',
        'SOLR_MLT_PROCESS_CORE': 'SOLR_MLT_PROCESS_CORE',
        'ASSISTENTE_PGVECTOR_HOST': 'DB_SEIIA_HOST',
        'ASSISTENTE_PGVECTOR_PORT': 'DB_SEIIA_PORT',
        'POSTGRES_DB_SIMILARIDADE': 'DB_SEIIA_SIMILARIDADE',
        'ASSISTENTE_PGVECTOR_DB': 'DB_SEIIA_ASSISTENTE',
        'POSTGRES_DB_ASSISTENTE_SCHEMA': 'DB_SEIIA_ASSISTENTE_SCHEMA',
        'VOL_SEIIA_DIR': 'VOL_SEIIA_DIR'
    },
    'prod.env': {
        'LOG_LEVEL': 'LOG_LEVEL',
        'AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG': 'AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG',
        'AIRFLOW__CELERY__WORKER_CONCURRENCY': 'AIRFLOW__CELERY__WORKER_CONCURRENCY',
        'AIRFLOW_WORKERS_REPLICAS': 'AIRFLOW_WORKERS_REPLICAS',
        'AIRFLOW_WORKER_MEM_LIMIT': 'AIRFLOW_WORKER_MEM_LIMIT',
        'AIRFLOW_WORKER_CPU_LIMIT': 'AIRFLOW_WORKER_CPU_LIMIT',
        'AIRFLOW_POSTGRES_MEM_LIMIT': 'AIRFLOW_POSTGRES_MEM_LIMIT',
        'AIRFLOW_POSTGRES_CPU_LIMIT': 'AIRFLOW_POSTGRES_CPU_LIMIT',
        'RABBITMQ_MEM_LIMIT': 'RABBITMQ_MEM_LIMIT',
        'RABBITMQ_CPU_LIMIT': 'RABBITMQ_CPU_LIMIT',
        'AIRFLOW_WEBSERVER_MEM_LIMIT': 'AIRFLOW_WEBSERVER_MEM_LIMIT',
        'AIRFLOW_WEBSERVER_CPU_LIMIT': 'AIRFLOW_WEBSERVER_CPU_LIMIT',
        'AIRFLOW_SCHEDULER_MEM_LIMIT': 'AIRFLOW_SCHEDULER_MEM_LIMIT',
        'AIRFLOW_SCHEDULER_CPU_LIMIT': 'AIRFLOW_SCHEDULER_CPU_LIMIT',
        'AIRFLOW_SCHEDULER_CPU_SHARES': 'AIRFLOW_SCHEDULER_CPU_SHARES',
        'AIRFLOW_TRIGGERER_MEM_LIMIT': 'AIRFLOW_TRIGGERER_MEM_LIMIT',
        'AIRFLOW_TRIGGERER_CPU_LIMIT': 'AIRFLOW_TRIGGERER_CPU_LIMIT',
        'API_SEI_MEM_LIMIT': 'API_SEI_MEM_LIMIT',
        'API_SEI_CPU_LIMIT': 'API_SEI_CPU_LIMIT',
        'APP_API_MEM_LIMIT': 'APP_API_MEM_LIMIT',
        'APP_API_CPU_LIMIT': 'APP_API_CPU_LIMIT',
        'SOLR_JAVA_MEM': 'SOLR_JAVA_MEM',
        'SOLR_MEM_LIMIT': 'SOLR_MEM_LIMIT',
        'SOLR_CPU_LIMIT': 'SOLR_CPU_LIMIT',
        'PGVECTOR_MEM_LIMIT': 'PGVECTOR_MEM_LIMIT',
        'PGVECTOR_CPU_LIMIT': 'PGVECTOR_CPU_LIMIT',
        'ASSISTENTE_MEM_LIMIT': 'ASSISTENTE_MEM_LIMIT',
        'ASSISTENTE_CPU_LIMIT': 'ASSISTENTE_CPU_LIMIT',
        'ASSISTENTE_NGINX_MEM_LIMIT': 'ASSISTENTE_NGINX_MEM_LIMIT',
        'ASSISTENTE_NGINX_CPU_LIMIT': 'ASSISTENTE_NGINX_CPU_LIMIT',
        'ASSISTENTE_LANGFUSE_MEM_LIMIT': 'LANGFUSE_MEM_LIMIT',
        'ASSISTENTE_LANGFUSE_CPU_LIMIT': 'LANGFUSE_CPU_LIMIT'
    },
    'security.env': {
        'GID_DOCKER': 'GID_DOCKER',
        'POSTGRES_USER': 'DB_SEIIA_USER',
        'POSTGRES_PASSWORD': 'DB_SEIIA_PWD',
        "_AIRFLOW_WWW_USER_USERNAME": "_AIRFLOW_WWW_USER_USERNAME",
        "_AIRFLOW_WWW_USER_PASSWORD": "_AIRFLOW_WWW_USER_PASSWORD",
        "AIRFLOW_POSTGRES_USER": "AIRFLOW_POSTGRES_USER",
        "AIRFLOW_POSTGRES_PASSWORD": "AIRFLOW_POSTGRES_PASSWORD",
        "AIRFLOW_AMQP_USER": "AIRFLOW_AMQP_USER",
        "AIRFLOW_AMQP_PASSWORD": "AIRFLOW_AMQP_PASSWORD"
    }
}

# Solicitar caminhos dos diretórios
old_dir = input("Digite o caminho para o diretório dos arquivos antigos (default_old.env, prod_old.env, security_old.env): ")
new_dir = "env_files" #input("Digite o caminho para o diretório dos arquivos novos (default.env, prod.env, security.env): ")

# Definir caminhos dos arquivos
old_files = {
    'default.env': os.path.join(old_dir, 'default.env'),
    'prod.env': os.path.join(old_dir, 'prod.env'),
    'security.env': os.path.join(old_dir, 'security.env')
}
new_files = {
    'default.env': os.path.join(new_dir, 'default.env'),
    'prod.env': os.path.join(new_dir, 'prod.env'),
    'security.env': os.path.join(new_dir, 'security.env')
}

# Ler arquivos antigos
old_vars = {}
for key, path in old_files.items():
    if os.path.exists(path):
        old_vars[key] = read_old_env_file(path)
    else:
        print(f"Erro: O arquivo {path} não foi encontrado.")
        exit(1)

# Atualizar novos arquivos
for new_file_name, new_file_path in new_files.items():
    update_new_env_file(new_file_path, mapping[new_file_name], old_vars)
    print(f"\nArquivo {new_file_name} atualizado em {new_file_path}.")

print("\nAtualização concluída. Os valores das variáveis mapeadas foram atualizados.")
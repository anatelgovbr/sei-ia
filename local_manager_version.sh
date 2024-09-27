#!/bin/bash
#Arquivo utilizado para atualizar a tabela version_manager no banco de dados quando o deploy é feito localmente usando deploy.sh. 
#O arquivo é chamado automaticamente

venv_name="manager_env"

python3 -m venv "$venv_name"

source "$venv_name/bin/activate"

cd autodeployer

pip install --upgrade pip

pip install .

export POSTGRES_USER=seiia; export POSTGRES_PASSWORD=****; python local_manager_version.py

deactivate

rm -rf "$venv_name"

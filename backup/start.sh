#!/bin/bash

# Iniciar todos os containers com nomes que começam com "sei_similaridade_deploy"
docker start $(docker ps -aq --filter "name=sei_")

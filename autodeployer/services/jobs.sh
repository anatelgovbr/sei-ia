#!/bin/bash
set -e # If any command fails, the script exits

container_path="/home/airflow/app/jobs"
local_path="/app/tmp/api_deployer/sei_similaridade_deploy/tmp/jobs"
checksum_file="checksum.txt"

calculate_directory_hash_local() {
    local path="$1"

    combined_hash=$(find "$path" -type f ! -path "$path/jobs/dags/*" ! -path "$path/.git/*" ! -path "*/dags/*" -not -name '*.pyc' \
        -exec sha256sum {} + | sort | awk '{print $1}' | sha256sum | awk '{print $1}')

    echo "$combined_hash"
}

# Function to read the hash from the checksum file inside the container
read_hash_from_container() {
    local container_name="$1"
    local container_path="$2"
    local checksum_file="$3"

    # Check if the file exists inside the container
    if docker exec "$container_name" test -f "$container_path/$checksum_file"; then
        # Read the hash from the file
        hash_container=$(docker exec "$container_name" cat "$container_path/$checksum_file")
    else
        # If the file does not exist, set hash_container to empty
        hash_container=""
    fi

    echo "$hash_container"
}

# Check if the environment is dev, homol, or prod
if [ "$ENVIRONMENT" != "dev" ] && [ "$ENVIRONMENT" != "homol" ] && [ "$ENVIRONMENT" != "prod" ]; then
    echo "Error: Could not identify a valid environment."
    exit 1
fi

# Identify branch according to environment
if [ "$ENVIRONMENT" = "dev" ]; then
    branch_deploy='desenvolvimento'
    branch_jobs='desenvolvimento'

elif [ "$ENVIRONMENT" = "homol" ]; then
    branch_deploy='homologacao'
    branch_jobs='homologacao'

elif [ "$ENVIRONMENT" = "prod" ]; then
    branch_deploy='master'
    branch_jobs='main'

fi
echo "Environment branch defined: $branch_deploy"

# Adjust working directory and paths
cd /app/

# rm -rf tmp/api_deployer

# # Clonar o repositório do DEPLOY
# git clone -b "$branch_deploy" --single-branch --depth 1 "https://oauth2:$GIT_TOKEN@$GIT_BASE_URL/deploy.git" tmp/api_deployer/sei_similaridade_deploy
# echo "`date`: Repo deploy cloned ($branch_deploy)"

# cat tmp/api_deployer/sei_similaridade_deploy/env_files/default.env > .env
# echo "" >> .env
# cat "tmp/api_deployer/sei_similaridade_deploy/env_files/$ENVIRONMENT.env" >> .env
# echo "" >> .env
# cat ./security.env >> .env

# cp .env "/app/tmp/api_deployer/sei_similaridade_deploy/.env"
source .env

# Adjust working directory
cd "/app/tmp/api_deployer/sei_similaridade_deploy/"

git clone -b "$branch_jobs" --single-branch --depth 1 "https://oauth2:$GIT_TOKEN@$GIT_BASE_URL/jobs.git" tmp/jobs

echo "Repo jobs cloned ($branch_jobs)"

# Copia Dockerfile para o diretorio jobs
cp ./tmp/jobs/airflow.dockerfile ./airflow.dockerfile
cp ./tmp/jobs/jobs_api.dockerfile ./jobs_api.dockerfile

# Copia arquivo env do Airflow
cp ./tmp/jobs/jobs/configs/airflow.env .


# Calculate the hash of the local directory
hash_local=$(calculate_directory_hash_local "$local_path")

# Check if there is at least one container running that has the volume
volume_name="sei_similaridade_deploy_airflow-jobs"
container_with_volume=$(docker ps --filter "volume=$volume_name" --format "{{.Names}}" | head -n 1)

if [ -z "$container_with_volume" ]; then
    echo "No container found with the volume: $volume_name"
    containers_found=false
else
    containers_found=true
fi

# Read the hash from the container's checksum file
if [ "$containers_found" = true ]; then
    hash_container=$(read_hash_from_container "$container_with_volume" "$container_path" "$checksum_file")
else
    hash_container=""
fi


echo "hash local: $hash_local"
echo "hash container: $hash_container"


# Compare the hashes
if [ "$hash_container" = "$hash_local" ] && [ "$containers_found" = true ]; then
    echo "The two directories are identical and a container with the shared volume was found."

    # Copy the files from the dags folder to the volume through the container
    echo "Copying files from the dags folder to the volume through the container: $container_with_volume"
    docker cp "$local_path/jobs/dags/." "$container_with_volume:$container_path/dags/"

else
    echo "The two directories are different or no container with the volume was found."

    # Proceed with the full deployment
    echo "Executing the full deployment."

    # Start Docker Compose services
    docker compose -f docker-compose-prod.yaml build --build-arg CACHEBUST=$(date +%s) airflow-webserver-pd
    docker compose -f docker-compose-prod.yaml build --build-arg CACHEBUST=$(date +%s) jobs_api

    # Bring up the services
    docker compose -f docker-compose-prod.yaml -p "$PROJECT_NAME" --profile airflow up -d --force-recreate
    docker compose -f docker-compose-prod.yaml -p "$PROJECT_NAME" up jobs_api -d --force-recreate

    echo "success"
    docker compose -f docker-compose-prod.yaml -p "$PROJECT_NAME" exec airflow-webserver-pd /bin/bash -c \
    "airflow dags list | awk '{print \$1}' | grep -v 'DAG_ID' | xargs -I {} airflow dags unpause {}; exit 0"

    # After full deployment, write the hash_local into checksum.txt inside the container
    # Now that the containers are up, find the container with the volume again

    container_with_volume=$(docker ps --filter "volume=$volume_name" --format "{{.Names}}" | head -n 1)
    if [ -n "$container_with_volume" ]; then
        echo "Writing the new hash to checksum.txt inside the container: $container_with_volume"
        docker exec --user root "$container_with_volume" bash -c "echo '$hash_local' > '$container_path/$checksum_file'"
    else
        echo "Error: Could not find container with the volume after deployment."
    fi

    exit 0
fi

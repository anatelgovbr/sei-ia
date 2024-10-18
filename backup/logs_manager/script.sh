#!/bin/bash

script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

containers=(
    "sei_similaridade_deploy-api_sei-1"
    "sei_similaridade_deploy-app-api-feedback-1"
    "sei_similaridade_deploy-solr-1"
    "sei_similaridade_deploy-pgvector-1"
)

log_dir="$script_dir/logs"

mkdir -p "$log_dir"

for container in "${containers[@]}"; do
    log_file="$log_dir/${container}_$(date +'%Y-%m-%d').txt"
    temp_file="$log_dir/${container}_temp.txt"

    echo "Getting logs for container: $container"

    if [ -e "$log_file" ]; then
        if [ "$container" == "sei_similaridade_deploy-solr-1" ]; then
            (docker logs "$container" | grep -v " INFO  (" ; cat "$log_file") >& "$temp_file"
        else
            docker logs "$container" >& "$temp_file"
        fi
    else
        echo "Creating log file for container: $container"
        
        if [ "$container" == "sei_similaridade_deploy-solr-1" ]; then
            docker logs "$container" | grep -v " INFO  (" >& "$temp_file"
        else
            docker logs "$container" >& "$temp_file"
        fi
    fi

    cat "$temp_file" >> "$log_file"
    awk '!seen[$0]++' "$log_file" > "$temp_file"
    mv "$temp_file" "$log_file"
done

echo "Script execution complete."
exit 0
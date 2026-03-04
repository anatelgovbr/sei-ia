## Pontos de Atenção para Escalabilidade

* Caso necessário, podem ser alteradas as variáveis de `..._MEM_LIMIT` no `env_files/prod.env`.
* Não devem ser alteradas para valores menores, pois isso afetará o funcionamento do sistema.

### Pontos de Montagem de Volumes

Os pontos de montagem dos volumes Docker estão localizados em `/var/lib/docker/volumes/`.
* Esses volumes tendem a crescer de acordo com a quantidade de documentos e processos armazenados, conforme descrito nos requisitos de sistema.

É possível também alterar os pontos de montagem dos volumes Docker modificando o arquivo `daemon.json`. Mais informações podem ser encontradas na [documentação do Docker](https://docs.docker.com/reference/cli/dockerd/#configure-runtimes-using-daemonjson).
  - Como alternativa, pode-se criar links simbólicos para cada um dos volumes.

- Exemplo de criação de um link simbólico para `/var/lib/docker/volumes/sei_ia_pgvector-db-volume-all`:
  - Deve parar o Docker para evitar problemas durante a movimentação dos dados:

   ```bash
   sudo systemctl stop docker
   ```

  - Mova a pasta de volumes para o novo caminho:

  ```bash

  sudo mv /var/lib/docker/volumes/sei_ia_pgvector-db-volume-all /novo/caminho/para/volumes
  ```

  - Crie o link simbólico apontando para o novo local dos volumes:

  ```bash

  sudo ln -s /novo/caminho/para/volumes /var/lib/docker/volumes/sei_ia_pgvector-db-volume-all
  ```

  - Reinicie o Docker:

  ```bash
  sudo systemctl start docker
  ```

### Ajustes Necessários

Ao escalar a solução, considere os seguintes pontos:

- **Solr**:
  - Aumente a alocação de memória se houver necessidade de lidar com uma maior quantidade de documentos ou consultas simultâneas. Uma boa prática é aumentar a memória em incrementos de 2 GB.
  - Para isso, altere no arquivo `env_files/prod.env`:

   | Variável                        | Descrição                                                                                  |
   |---------------------------------|--------------------------------------------------------------------------------------------|
   | `SOLR_JAVA_MEM="-Xms8g -Xmx24g"` | Define as opções de memória Java para Solr, com um mínimo de 8 GB e um máximo de 24 GB.     |
   | `SOLR_MEM_LIMIT=28g`            | Define o limite de memória para Solr como 8 GB.                                           |
   | `SOLR_CPU_LIMIT='8'`            | Define o limite de CPU para Solr como 8 unidades de CPU.                                   |

- **Airflow**:
  - O Airflow pode ser escalado horizontalmente adicionando mais workers. Para mais informações, consulte a [documentação do Airflow](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/overview.html).
  - Em nossa solução, é possível configurar mais workers na variável `AIRFLOW_WORKERS_REPLICAS` no `env_files/prod.env`, lembrando que cada réplica usa em média 6 GB.

- **Postgres**:
  - Para aumentar o desempenho, considere aumentar a memória disponível. Monitore o uso de disco e ajuste conforme necessário.

   | Variável                    | Descrição                                                     |
   |-----------------------------|---------------------------------------------------------------|
   | `PGVECTOR_MEM_LIMIT=16g`     | Define o limite de memória para Pgvector como 16 GB.           |
   | `PGVECTOR_CPU_LIMIT='4'`    | Define o limite de CPU para Pgvector como 4 unidades de CPU.  |

## Backup periódico dos dados do Servidor de Soluções de IA

Após a análise dos **Pontos de Atenção para Escalabilidade**, é fundamental estabelecer uma rotina de **backup periódico dos dados do Servidor de Soluções de IA**, especialmente dos bancos de dados utilizados pelas aplicações.

A adoção de uma política de backup adequada é essencial para:
- Garantir a integridade das informações
- Permitir a recuperação do ambiente em caso de falhas
- Minimizar impactos operacionais em situações de indisponibilidade

Os procedimentos recomendados para a realização de backup estão descritos no documento:

- [Backup periódico dos dados do Servidor de Soluções de IA](docs/BACKUP.md)

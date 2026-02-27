## Health Checker Geral do Ambiente

O Health Checker é executado como último comando do script `deploy-externo.sh`. Ele faz uma checagem geral de conexões , mapeamento e problemas comuns.

1. **Estrutura do Log**
   Os logs seguem a seguinte estrutura:
   - **Timestamp:** Data e hora do evento.
   - **Nível de severidade:**
     - **INFO:** Informações gerais e mensagens de sucesso.
     - **WARNING:** Avisos de possíveis problemas ou inconsistências.
     - **ERROR:** Erros que requerem atenção imediata.
     - **Mensagem:** Detalhes do evento ou do problema detectado.

### Explicação dos Logs por Seção

#### 1. **Testes**

##### 1.1 **ENVS**
- **Descrição:** Esta seção descreve variáveis de ambiente encontradas em arquivos `.env`.
- **Objetivo:** Verificar se todas as variáveis necessárias estão presentes e com valores corretos.
- **Tipos de Mensagens Comuns:**
  - **Variáveis Sobrando:** Variáveis que estão definidas mas não são utilizadas pelo sistema.
  - **Variáveis Duplicadas:** Variáveis que aparecem mais de uma vez, podendo causar conflitos.
  - **Variáveis Vazias ou Inválidas:** Variáveis sem valor ou com valores incorretos.

##### 1.2 **CONECTIVIDADE**

###### 1.2.1 **TESTE DE CONECTIVIDADE - RESUMO**
- **Descrição:** Verifica a disponibilidade e acessibilidade de endpoints ou serviços externos.
- **Objetivo:** Confirmar se os sistemas externos estão acessíveis.
- **Mensagens Comuns:**
  - **Falha de Conexão:** O sistema não conseguiu acessar o serviço especificado.
  - **Tempo de Resposta Alto:** O serviço respondeu lentamente, sugerindo um possível problema de desempenho.

###### 1.2.2 **TESTE DE SAÚDE DOS ENDPOINTS**
- **Descrição:** Realiza uma verificação do status (saúde) de endpoints críticos da aplicação.
- **Objetivo:** Confirmar que os endpoints principais estão funcionando corretamente.
- **Mensagens Comuns:**
  - **Serviço Indisponível:** O endpoint não respondeu conforme esperado.
  - **Falha ao Testar:** Testes não puderam ser realizados devido a erro de configuração ou conectividade.

###### 1.2.3 **TESTE DE CONEXÃO COM SOLR do SEI IA**
- **Descrição:** Verifica a conectividade com o servidor SOLR IA, utilizado para busca e indexação de dados.
- **Objetivo:** Garantir que a aplicação consiga se comunicar corretamente com o servidor SOLR.
- **Mensagens Comuns:**
  - **Falha de Conexão:** Erro ao tentar conectar ao SOLR.
  - **Configuração de Endpoint Inválida:** A URL ou as credenciais de conexão podem estar incorretas.

##### 1.3 **TESTE DE CONEXÃO COM BANCO DE DADOS**


###### 1.3.2 **INTERNOS**

**1.3.2.1 TABELAS DO ASSISTENTE**
- **Descrição:** Verifica a conexão e o estado das tabelas do banco de dados utilizadas pelo Assistente Virtual.
- **Objetivo:** Garantir que o sistema do Assistente Virtual tenha acesso adequado ao banco de dados interno.
- **Mensagens Comuns:**
  - **Tabela Inexistente:** Falta de tabelas necessárias para o funcionamento do Assistente.
  - **Erro de Consulta:** Falhas em queries ou na execução de operações SQL.

**1.3.2.2 TABELAS DE SIMILARIDADE**
- **Descrição:** Verifica a integridade e acessibilidade das tabelas usadas para comparação de dados (por exemplo, comparação de documentos ou consultas de similaridade).
- **Objetivo:** Assegurar que as operações de comparação de dados funcionem corretamente.
- **Mensagens Comuns:**
  - **Falha ao Buscar Dados:** Erros ao tentar recuperar dados das tabelas de similaridade.
  - **Desempenho Baixo:** Consultas muito lentas ou com alta latência.

##### 1.4 **DOCKER**

###### 1.4.1 **DOCKER - LOGS**
- **Descrição:** Relata o estado dos containers Docker executando a aplicação.
- **Objetivo:** Verificar se todos os containers estão em funcionamento e sem problemas de saúde.
- **Mensagens Comuns:**
  - **Containers Parados:** Containers não estão em execução ou foram reiniciados inesperadamente.
  - **Falha de Saúde:** Containers com status `unhealthy` que indicam falhas internas.
  - **Reinicializações Frequentes:** Containers que estão reiniciando constantemente devido a falhas.

##### 1.5 **AIRFLOW**
- **Descrição:** Registra as execuções dos DAGs (Direcionadores de Fluxos de Trabalho) do Airflow, incluindo falhas de execução ou dependências não atendidas.
- **Objetivo:** Garantir que as tarefas programadas no Airflow sejam executadas corretamente.
- **Mensagens Comuns:**
  - **Falhas de Tarefa:** Tarefas que não foram executadas ou falharam durante a execução.
  - **Dependências Não Satisfeitas:** Problemas ao tentar executar tarefas devido a dependências não resolvidas.

##### 1.6 **RESUMO - TESTES**
- **Descrição:** Apresenta um resumo geral de todos os testes realizados, destacando falhas críticas e informações importantes.
- **Objetivo:** Facilitar a visão geral dos resultados dos testes, indicando onde ações corretivas são necessárias.
- **Mensagens Comuns:**
  - **Falhas Identificadas:** Relatórios com falhas graves, como falta de conectividade ou erros de autenticação.
  - **Testes Bem-Sucedidos:** Indicação de que todas as verificações foram realizadas com sucesso, e o sistema está em bom estado.

Caso deseje executar o Health Checker manualmente  execute o comando:
```bash
source env_files/default.env
docker compose -f docker-compose-healthchecker.yml -p $PROJECT_NAME --build
```

Aguarde a finalização dos testes. Os logs estarão disponíveis, por padrão, em:
`/var/lib/docker/volumes/sei_ia_health_checker_logs/_data/logs/{DATA}`

Além disso, será gerado um arquivo `.zip` para facilitar a transmissão dos dados.

A compreensão do LOG deve iniciar pela criteriosa análise de:
`/var/lib/docker/volumes/sei_ia_health_checker_logs/_data/logs/{DATA}/tests_{DATA}.log`,
que tem sua estrutura descrita a seguir.

**Dica:** Os containers do Airflow podem emitir alguns erros e avisos devido a pequenas falhas momentâneas de comunicação entre eles, que podem ser ignorados.

> **Observação:**
> 1. Por questões de segurança, essa pasta, por padrão, não é acessível. É necessário entrar como `root` para ter acesso a esses arquivos.
> 2. Caso os arquivos não estejam nesse local, oriente-se pelo local de montagem dos seus volumes Docker com o comando:
>    ```bash
>    docker volume inspect sei_ia_health_checker_logs
>    ```
>    A saída deve ser algo como:
>    ```bash
>    [
>        {
>            "CreatedAt": "2024-12-05T00:20:58Z",
>            "Driver": "local",
>            "Labels": {
>                "com.docker.compose.project": "sei_ia",
>                "com.docker.compose.version": "2.29.2",
>                "com.docker.compose.volume": "health_checker_logs"
>            },
>            "Mountpoint": "/var/lib/docker/volumes/sei_ia_health_checker_logs/_data", <- LOCAL DO ARQUIVO
>            "Name": "sei_ia_health_checker_logs",
>            "Options": null,
>            "Scope": "local"
>        }
>    ]
>    ```

## Testes de Acesso

Após a conclusão do deploy, é necessário realizar testes de acesso para verificar se cada solução da arquitetura está respondendo corretamente.

Esses testes permitem confirmar:
- A disponibilidade dos serviços
- A comunicação entre os componentes
- O correto funcionamento do ambiente após a instalação

Os procedimentos detalhados para execução dos testes, estão descritos no documento, [Testes de Acessos](docs/TESTES.md).

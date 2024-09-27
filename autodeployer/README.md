O Autoployer é responsável por detectar as alterações no repositório e realizar automaticamente o deploy da aplicação.

#### Concepção
Ao realizar um deploy o autodeployer cria um arquivo .json contendo a identificação de qual merge request foi utilizado para subir o serviço, caso o identificador da aplicação seja inferior ao identificador da branch, é ativado o arquivo de deploy do serviço. Estrutura de pastas:

```
autodeployer/
├── README.md
├── app_monitor.py
├── merge_checker.py
├── utils.py
├── deploy_version_manager.py
├── services/
│ ├── jobs.sh
├── status/
| ├── .keep
│ └── jobs-dev-details.json
├── setup.cfg
````

*Arquivos python*

    app_monitor.py : Arquivo principal da aplicação que monitora a aplicação e o git.

    merge_checker.py : Arquivo que captura qual merge request mais atual da branch no git, e compara com a aplicação.

    utils.py : Arquivo com método auxiliar para printar no terminal o stdout do autodeployer.

    deply_verion_manager.py : Contém métodos para armazenar no banco Postgres o número da versão dos serviços.


*services* : Scripts de deploy para cada serviço. ex: jobs.sh

*status* : Armazena o arquivo.json com as informações do deploy da aplicação

ex:
```json
{"url_last_merge": "https://git.anatel.gov.br/processo_eletronico/sei-ia/sei-similaridade/jobs/-/merge_requests/428", "deployed": true}
```

### Arquivo setup.cfg

```toml
[alias_env]
desenvolvimento = dev
homologacao = homol
producao = prod

[autodeploy_envs]
jobs = dev,homol,prod

[rss_link_main_branch]
jobs = https://git.anatel.gov.br/processo_eletronico/sei-ia/sei-similaridade/jobs/-/merge_requests.atom?feed_token=******&scope=all&state=merged&target_branch=main&sort=updated_desc

[repo_local_path]
root_path = autodeployer
jobs = jobs
```

[alias_env] - Aliase para o nome das branchs no git em relação ao nome dado na aplicação

[autodeploy_envs] - lista de branchs que serão monitorados pelo autodeployer

[rss_link_main_branch] - Link do RSS dos merge requests do repositório git para a branch principal

[repo_local_path] - lista de serviços monitorados
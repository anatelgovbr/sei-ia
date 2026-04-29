# Servidor de Soluções de IA do Módulo SEI IA

O *Servidor de Soluções de IA* contém as ferramentas necessárias para o funcionamento do [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia), composto, de forma simplificada, pelos sub-módulos:

- **SEI-IA-SIMILARIDADE** — recomendação de processos similares e de documentos similares.
- **SEI-IA-ASSISTENTE** — Assistente baseado em Inteligência Artificial Generativa (GenAI), para executar prompts dos usuários e interagir com documentos do SEI.
- **SEI-IA-ETL-AIRFLOW** — orquestração das tarefas de indexação e geração de embeddings.

## Orientações Preliminares

A instalação foi projetada para ser o mais automática possível. Ainda assim, há passos que precisam ser executados manualmente pelo administrador do ambiente, por questões de segurança ou por dependerem de informações específicas da rede do órgão.

> **Antes de começar, leia integralmente este README e o [Manual de Instalação](docs/INSTALL.md)**. Dúvidas que surgirem no início podem ser esclarecidas ao longo do material.

- **ATENÇÃO**: o servidor de SEI IA **não deve ser compartilhado** com outras soluções.
- **ATENÇÃO**: para instalar o *Servidor de Soluções de IA do Módulo SEI IA* é mandatório ter o [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia) previamente instalado e configurado no SEI do ambiente correspondente.

## Estrutura do Repositório

A partir desta versão, este repositório passou a ser um **monorepo**: o código-fonte de todas as aplicações (Assistente, Similaridade, ETL/Airflow) está versionado junto com a configuração do `docker compose`. Isso permite duas formas de instalação:

- **Build local** — as imagens são construídas no servidor a partir do código deste repositório (caminho padrão).
- **Imagens pré-publicadas** — as imagens são puxadas do GitHub Container Registry, sem build local (alternativa para órgãos que preferem não buildar).

Os dois caminhos estão documentados no [Manual de Instalação](docs/INSTALL.md).

```
sei-ia/
├── aplicacoes/                      # Código-fonte das aplicações
│   ├── assistente/
│   ├── similaridade/
│   └── etl-airflow/
├── ops/                             # Suporte de infraestrutura (Solr, Postgres, healthchecker)
├── docs/                            # Manuais (INSTALL.md, UPGRADE.md)
├── docker-compose.yml               # Stack principal
├── docker-compose.override.yml      # Portas para acesso externo (debug)
├── default.env                      # Variáveis NÃO sensíveis (versionado)
├── security_example.env             # Modelo de variáveis sensíveis
├── litellm_config.template.yaml     # Modelo da config dos modelos LLM
├── Makefile                         # Atalhos make up / make down / make check
└── .gitlab/                         # Pipelines e scripts de build/deploy
```

## Requisitos Mínimos

Os requisitos abaixo se referem **apenas** ao Servidor de Soluções de IA — não se confundem com a infraestrutura alocada ao SEI.

O servidor é baseado em Docker. Recomendamos servidor Linux. **Não recomendamos Windows com WSL em produção.**

- **Docker**:
  - Docker Engine ≥ 27.1.1
  - Docker Compose ≥ 2.29
  - Docker Buildx ≥ 0.13
- **Servidor Linux** (referência da Anatel em produção):
  - **CPU**: 16 cores @ 2.10 GHz
  - **RAM**: 128 GB
  - **Disco**: 450 GB
- **Requisito mínimo do SEI**:
  - Versão **v4.1.5** (não compatível com versões anteriores).
  - Para versões mais recentes do SEI, conferir compatibilidade previamente.

> **Realidade de cada órgão**: Solr e PostgreSQL crescem proporcionalmente ao volume de documentos do SEI. Cada órgão deve dimensionar conforme seu próprio volume.

## Download

O download do pacote de instalação deve ser obtido na [seção Releases deste projeto](https://github.com/anatelgovbr/sei-ia/releases).

Alternativamente, é possível clonar o repositório em uma tag estável:

```bash
git clone --branch <tag> --single-branch https://github.com/anatelgovbr/sei-ia.git /opt/sei-ia
```

## Instalação

As instruções completas de instalação estão em **[docs/INSTALL.md](docs/INSTALL.md)**.

Resumo dos passos principais:

1. Preparar usuário, pastas e Docker no servidor.
2. Criar a rede Docker dedicada (`docker-host-bridge`).
3. Clonar o repositório em `/opt/sei-ia`.
4. Preparar o builder do Docker (Buildx + DNS).
5. Configurar `security.env` (a partir de `security_example.env`).
6. Configurar `litellm_config.yaml` (a partir de `litellm_config.template.yaml`).
7. Subir a stack: `make up`.
8. Configurar a integração HTTPS com o SEI.
9. Validar: `make check`.

## Atualização

As instruções de atualização de versão estão em **[docs/UPGRADE.md](docs/UPGRADE.md)**.

## Suporte

Em caso de dúvidas ou problemas, abra uma issue em <https://github.com/anatelgovbr/sei-ia/issues>.

# Instalação / Installation

> Guia completo para instalação do SEI-IA Assistente

## Pré-requisitos / Prerequisites

| Requisito | Versão |
|-----------|--------|
| Python | 3.12.x |
| uv | Última versão |
| Docker | 20.10+ |
| Docker Compose | 2.0+ |
| PostgreSQL | 13+ com pgvector |
| Redis | 6.0+ |

---

## Instalação com uv (Recomendado)

O projeto utiliza [uv](https://docs.astral.sh/uv/) como gerenciador de pacotes.

### 1. Clone o repositório

```bash
git clone https://github.com/Anatel/sei-ia.git
cd sei-ia/assistente
```

### 2. Instale o uv (se não tiver)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. Crie o ambiente virtual e instale dependências

```bash
# Criar ambiente e instalar dependências
uv sync

# Para instalar com extras de desenvolvimento
uv sync --extra dev

# Para instalar com OpenTelemetry
uv sync --extra otel
```

### 4. Configure as variáveis de ambiente

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite com suas configurações
nano .env
```

Consulte [Variáveis de Ambiente](environment.md) para detalhes.

### 5. Inicie os serviços auxiliares

```bash
# PostgreSQL com pgvector e Redis
docker-compose -f docker-compose-local.yml up -d postgres redis
```

### 6. Execute a aplicação

```bash
# Desenvolvimento
uv run uvicorn sei_ia.main:app --reload --port 8088

# Produção
uv run gunicorn sei_ia.main:app -c sei_ia/configs/gunicorn_conf.py
```

---

## Instalação com Docker (Produção)

### 1. Build da imagem

```bash
docker build -f assistente.dockerfile -t sei-ia-assistente .
```

### 2. Execute com Docker Compose

```bash
docker-compose -f docker-compose-local.yml up -d
```

---

## Instalação com Make

O projeto inclui um `Makefile` com comandos úteis:

```bash
# Instalar tudo
make install

# Verificar código (lint + testes)
make check

# Rodar testes
make test

# Rodar aplicação (porta 8199)
make run-uvicorn

# Gerar documentação
make docs
```

---

## Verificando a Instalação

### Health Check

```bash
curl http://localhost:8088/health
```

Resposta esperada:
```json
{"status": "OK"}
```

### Documentação da API

Acesse no navegador:
- Swagger UI: `http://localhost:8088/docs`
- ReDoc: `http://localhost:8088/`

---

## Troubleshooting

### Erro: pgvector não encontrado

```bash
# Instalar extensão pgvector no PostgreSQL
docker exec -it postgres psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Erro: Conexão recusada ao Redis

```bash
# Verificar se o Redis está rodando
docker ps | grep redis

# Iniciar se necessário
docker-compose -f docker-compose-local.yml up -d redis
```

### Erro de dependências

```bash
# Limpar cache e reinstalar
uv cache clean
uv sync --reinstall
```

---

## Próximos Passos

- [Variáveis de Ambiente](environment.md) - Configure as credenciais
- [Quickstart](quickstart.md) - Faça sua primeira requisição

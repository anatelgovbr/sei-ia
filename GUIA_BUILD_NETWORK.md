# Guia — Build Docker usando a rede `docker-host-bridge`

## Problema

No servidor, o `make up` pode quebrar durante o build das imagens com erro parecido com:

```text
failed to solve: process "/bin/sh -c ..." did not complete successfully: network bridge not found
```

ou falhar em comandos como:

```text
apt-get update
apt-get install
wget
curl
dnf install
```

Isso acontece porque a rede configurada no `docker-compose.yml` vale para os containers em runtime, mas não necessariamente para os passos `RUN` executados durante o build das imagens.

No `docker-compose.yml`, a rede runtime é:

```yaml
networks:
  seiia:
    name: ${COMPOSE_NETWORK_NAME:-docker-host-bridge}
    external: true
```

Essa configuração conecta os containers prontos na rede `docker-host-bridge`, mas o BuildKit pode continuar tentando usar a rede default `bridge` durante o build. Neste servidor, a rede `bridge` pode não existir ou não funcionar corretamente, causando o erro:

```text
network bridge not found
```

A solução é usar um builder BuildKit explicitamente criado na rede `docker-host-bridge`.

---

## Sequência recomendada

Execute tudo a partir da raiz do projeto:

```bash
cd /opt/sei-ia
```

### 1. Garantir que a rede existe

```bash
docker network inspect docker-host-bridge >/dev/null 2>&1 || docker network create docker-host-bridge
```

### 2. Verificar se o `buildx` existe

```bash
docker buildx version
```

Se esse comando funcionar, pule para o passo 4.

Se falhar, instale o plugin conforme o passo 3.

---

## 3. Instalar Docker Buildx quando o APT não encontra o pacote

Em alguns servidores, este comando falha:

```bash
sudo apt-get install -y docker-buildx-plugin
```

Erro comum:

```text
E: Impossível encontrar o pacote docker-buildx-plugin
```

Isso indica que o repositório APT configurado não possui o pacote do plugin. O caminho mais rápido é instalar o binário do Buildx manualmente no usuário atual.

```bash
mkdir -p ~/.docker/cli-plugins
```

```bash
ARCH="$(uname -m)"; case "$ARCH" in x86_64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; *) echo "Arquitetura não suportada: $ARCH"; exit 1;; esac; VERSION="$(curl -fsSL https://api.github.com/repos/docker/buildx/releases/latest | sed -n 's/.*"tag_name": "\(v[^"]*\)".*/\1/p' | head -1)"; echo "Instalando buildx $VERSION para linux-$ARCH"; curl -fL "https://github.com/docker/buildx/releases/download/${VERSION}/buildx-${VERSION}.linux-${ARCH}" -o ~/.docker/cli-plugins/docker-buildx; chmod +x ~/.docker/cli-plugins/docker-buildx
```

Confirme:

```bash
docker buildx version
```

Se o servidor não tiver acesso ao GitHub, configure o repositório oficial da Docker no APT ou copie o binário `docker-buildx` manualmente para:

```text
~/.docker/cli-plugins/docker-buildx
```

---

## 4. Recriar o builder BuildKit na rede correta

Remova builder antigo, se existir:

```bash
docker buildx rm seiia-bridge 2>/dev/null || true
```

Crie o builder usando a rede `docker-host-bridge`:

```bash
BUILDX_BUILDER_NAME=seiia-bridge BUILDX_BUILDER_NETWORK=docker-host-bridge bash .gitlab/scripts/ensure_buildx_builder.sh
```

Confirme:

```bash
docker buildx ls
```

```bash
docker buildx inspect seiia-bridge --bootstrap
```

O builder esperado é `seiia-bridge`.

---

## 5. Testar build antes de subir tudo

Teste primeiro o serviço que estava quebrando:

```bash
BUILDX_BUILDER=seiia-bridge DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 docker compose --env-file default.env --env-file security.env build --progress=plain assistente
```

Se o erro original era em outro serviço, substitua `assistente` pelo serviço desejado. Exemplos:

```bash
BUILDX_BUILDER=seiia-bridge DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 docker compose --env-file default.env --env-file security.env build --progress=plain similaridade
```

```bash
BUILDX_BUILDER=seiia-bridge DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 docker compose --env-file default.env --env-file security.env build --progress=plain infra-solr
```

---

## 6. Subir o stack

Depois que o build isolado passar:

```bash
BUILDX_BUILDER=seiia-bridge DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 make up
```

---

## Atenção com nomes das variáveis

Use exatamente estes nomes, com underscore:

```text
BUILDX_BUILDER
DOCKER_BUILDKIT
COMPOSE_DOCKER_CLI_BUILD
BUILDX_BUILDER_NAME
BUILDX_BUILDER_NETWORK
```

Não use:

```text
BUILDXBUILDER
DOCKERBUILDKIT
COMPOSEDOCKERCLIBUILD
BUILDXBUILDERNAME
BUILDXBUILDERNETWORK
```

Sem os underscores, o Docker Compose ignora a configuração e volta para o builder default.

---

## Atenção com quebra de linha usando `\`

Se usar comandos multi-linha, a barra `\` precisa ser o último caractere da linha. Não pode haver espaço depois dela.

Mais seguro: use os comandos em uma linha só, como neste guia.

Erro típico quando há espaço depois do `\` ou variável digitada errado:

```text
: comando não encontrado
```

---

## Como saber que ainda está errado

Se o log mostrar algo assim:

```text
WARN Docker Compose is configured to build using Bake, but buildx isn't installed
```

então o Buildx não está instalado ou não foi encontrado pelo Docker CLI.

Se o log mostrar:

```text
docker:default
```

é sinal de que o Compose ainda está usando o builder default, não o `seiia-bridge`.

Se o log mostrar:

```text
network bridge not found
```

é sinal de que o build ainda está tentando usar a rede default `bridge`.

---

## Diagnóstico rápido

```bash
docker network inspect docker-host-bridge --format '{{.Name}}'
```

```bash
docker buildx version
```

```bash
docker buildx ls
```

```bash
docker buildx inspect seiia-bridge --bootstrap
```

```bash
BUILDX_BUILDER=seiia-bridge DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 docker compose --env-file default.env --env-file security.env build --progress=plain assistente
```

---

## Arquivos relacionados

O projeto já possui os arquivos necessários para preparar o builder:

```text
.gitlab/scripts/ensure_buildx_builder.sh
.gitlab/buildkit/buildkitd.toml
```

O script `ensure_buildx_builder.sh` cria ou reutiliza o builder `seiia-bridge` na rede informada por `BUILDX_BUILDER_NETWORK`.

O arquivo `buildkitd.toml` fixa os DNS usados pelo BuildKit durante os passos `RUN` dos Dockerfiles.

---

## Comando final esperado

Na prática, depois do Buildx instalado e do builder criado, o comando operacional é:

```bash
BUILDX_BUILDER=seiia-bridge DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 make up
```

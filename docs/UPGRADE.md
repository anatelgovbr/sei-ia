# Guia de Atualização do Servidor de Soluções de IA do SEI IA

- Este guia orienta a escolha do procedimento de atualização do *Servidor de
  Soluções de IA*.
- Cada transição possui um documento próprio. Execute os guias adjacentes em ordem
  quando a origem e o destino atravessarem mais de uma linha de release.
- **ATENÇÃO:** nunca remova volumes durante uma atualização. Usuários, senhas e
  caminhos já associados aos dados persistentes devem ser preservados.
- **ATENÇÃO:** uma atualização somente é concluída quando todos os critérios de
  aprovação definidos pelo procedimento específico terminam sem erros.

---

## Sumário

- [1. Como escolher o procedimento](#1-como-escolher-o-procedimento)
- [2. Matriz de upgrades](#2-matriz-de-upgrades)
- [3. Regras comuns](#3-regras-comuns)

---

## 1. Como escolher o procedimento

Identifique primeiro a versão que está funcionando no servidor e a versão de
destino. Não use o procedimento de instalação limpa para atualizar uma stack com
dados. Também não pule diretamente uma linha intermediária: uma instalação 1.1.x
deve chegar à 1.2.x antes de executar a migração para 1.3.x.

Exemplo:

```text
1.1.x  →  1.2.x  →  1.3.x
```

## 2. Matriz de upgrades

| Origem | Destino | Guia | Mudança principal |
|---|---|---|---|
| 1.0.x | 1.1.x | [1.0 → 1.1](upgrades/1.0-to-1.1.md) | API do SEI, credenciais do Solr e novos modelos |
| 1.1.x | 1.2.x | [1.1 → 1.2](upgrades/1.1-to-1.2.md) | adoção do proxy LiteLLM e WebSearch da linha antiga |
| 1.2.x | 1.3.x | [1.2 → 1.3](upgrades/1.2-to-1.3.md) | monorepo, migração de configuração, build local, SearXNG e gateway TLS |

A combinação de destino da última linha usa SEI 5.0.4.22, Módulo SEI IA 1.5.0 e
Servidor de Soluções de IA 1.3. Atualize o SEI e o módulo quando o guia da
transição exigir.

## 3. Regras comuns

| Regra | Motivo |
|---|---|
| Use uma tag estável, nunca uma branch de trabalho. | uma tag identifica o conjunto de código, templates e migradores testado |
| Preserve usuários e senhas de PostgreSQL, RabbitMQ, Solr e Airflow. | trocar a credencial sem migrar o serviço impede a abertura dos volumes existentes |
| Pare somente a stack do SEI IA. | o SEI pode permanecer disponível quando o guia específico não exigir sua atualização |
| Nunca use `down -v`, `make down-volumes` ou remoção manual de `VOL_SEIIA_DIR`. | esses comandos apagam o estado que o upgrade deve preservar |
| Use os templates da tag de destino. | copiar arquivos antigos inteiros deixa variáveis ausentes ou obsoletas |
| Mantenha `security.env`, `litellm_config.yaml`, chaves TLS e backups fora do Git. | são artefatos privados do ambiente |
| Faça backup consistente conforme a política do órgão. | cópia de arquivos de bancos em escrita não substitui dump ou snapshot coordenado |

Não existe um procedimento genérico executável neste índice. Cada guia versionado
define o baseline, a reconciliação de configuração e modelos, o deploy, o TLS, as
integrações e os critérios de aprovação da respectiva transição. Para 1.2.x →
1.3, use sempre o migrador documentado; não tente executar manualmente o de/para
das variáveis.

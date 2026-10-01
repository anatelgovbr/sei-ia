# Benchmark de latência: sessão vs fluxo clássico

Este experimento compara os endpoints `/llm_lang/session_stream` e
`/llm_lang/stream` no mesmo ambiente. Ele mede latência, qualidade, tokens, custo
estimado e chamadas de ferramentas sem alterar o comportamento normal da aplicação.

O desenho da coleta e as decisões de instrumentação estão em [DESIGN.md](DESIGN.md).
O runner específico da história de contexto longo, deliberadamente sem caminho
clássico, está documentado em [LONG_CONTEXT.md](LONG_CONTEXT.md).

## Layout

- `dataset/session-classico/` e `scripts/session-classico/` pertencem ao comparativo;
- `dataset/long-context/` e `scripts/long-context/` pertencem à bateria Long Context;
- `scripts/shared/` contém apenas código consumido pelos dois fluxos;
- `apresentacoes/` contém os HTMLs, relatórios, metodologia e o pacote final do
  benchmark redesign;
- `artifacts/`, configs e rate cards permanecem na raiz do experimento.

## Preparação

Use o ambiente Python de `aplicacoes/assistente`. As credenciais continuam fora do
Git, em `security.env`. Os documentos extraídos dos processos ficam em
`dataset/docs/`, que também é ignorado.

Para usar o projeto Langfuse `comparativo-deepagents-classico`, leia as
credenciais do arquivo local `langfuse-comparativo.env` na raiz do monorepo e
carregue-o no ambiente antes de executar os runners. Esse arquivo é ignorado pelo
Git e não deve ser incluído em commits, logs ou artefatos.

A stack isolada usa projeto, rede externa dedicada, rede nginx-app interna, porta
HTTPS 8188 e volumes próprios. Seu serviço continua se chamando `assistente-nginx`,
mas é declarado integralmente no overlay: usa a imagem oficial fixada do Nginx,
`nginx.isolated.conf` e o par `.runtime/certs/seiia.cert.{pem,key}` da worktree.
Ele depende somente do Assistente e não herda serviços, portas nem dependências do
gateway central. Nginx e app participam das duas redes: a dedicada fornece o gateway
da porta publicada e a interna mantém o alias privado do backend. O launcher
fail-closed remove contaminação do shell, renderiza JSON e valida esses invariantes
antes de permitir o `up` (`docker-compose.isolated.yml:45-69`;
`scripts/shared/isolated_compose.py:189-208`).

```bash
uv run python experimentos/latencia-session-vs-classico/scripts/shared/isolated_compose.py render \
  --workload session \
  --security-env ../../security.env \
  --evidence-root /raiz/privada/do/pacote \
  --render-output /raiz/privada/compose.raw.json \
  --arm terra-luna \
  --context-tokens 1050000 \
  --mini-context-tokens 1050000 \
  --nano-context-tokens 1050000 \
  --reasoning-effort low
```

O comando `up` usa os mesmos argumentos, repete o render no mesmo processo e chama
somente os serviços isolados com `--no-build`. A rede externa dedicada deve existir
antes; o launcher não cria, reinicia ou reaproveita containers de outro projeto.
`SEI_ADDRESS` e `SEI_API_DB_ADDRESS` herdados são descartados e recarregados juntos
da fonte privada aprovada. O JSON renderizado contém configuração efetiva e deve
permanecer em raiz `0700`, arquivo `0600`.

`--workload session` também remove do ambiente herdado qualquer pin de evidence e
recusa um render que ainda exponha o setting ao app. Long Context usa
`--workload long-context --evidence-index /var/seiia/benchmark-evidence/evidence-index.json`;
somente esse modo acrescenta o override que injeta o índice protegido.

O benchmark novo usa `benchmark-redesign/benchmark.py` para `preflight`, `canary` e
`battery`. Os três comandos exigem a prova W→R do braço; canário usa um dos três QIDs
fixos e bateria executa os dez QIDs Session, N=1, sem Classic, warmup ou retry.

## Dataset

`dataset/session-classico/cases.json` contém as perguntas e rubricas do comparativo.
O manifesto `dataset/session-classico/benchmark-decision-v2.json` seleciona a suíte
decisória de dez casos. A
matriz cobre documentos pequenos, médios e grandes, com e sem busca web.

A campanha independente de contexto longo usa
`dataset/long-context/benchmark-long-context-v2.json`. Esse manifesto não contém perguntas,
golds ou documentos: guarda apenas referências protegidas, hashes e parâmetros
reproduzíveis dos nove itens e três corpora. Seu contrato, schemas e os dois canários
autorizados estão documentados em [LONG_CONTEXT.md](LONG_CONTEXT.md).

```bash
uv run python experimentos/latencia-session-vs-classico/scripts/session-classico/upsert_dataset.py \
  --create-dataset --decision-suite
```

O envio ao Langfuse é idempotente. Cada item usa um identificador derivado do nome do
dataset e do QID.

## Execução

O benchmark redesenhado usa o mesmo runner para os dois braços. O preflight sem
inferência só libera canário e bateria quando a prova de `cache_read` está
observada e reconciliada:

```bash
uv run python experimentos/latencia-session-vs-classico/benchmark-redesign/benchmark.py \
  preflight --arm gpt54 \
  --cache-proof /raiz/privada/cache-proof.json \
  --output /raiz/privada/preflight-gpt54.json

uv run python experimentos/latencia-session-vs-classico/benchmark-redesign/benchmark.py \
  canary --arm gpt54 \
  --cache-proof /raiz/privada/cache-proof.json \
  --run-name <run-gpt54> --artifacts-dir /raiz/privada/artifacts-gpt54

uv run python experimentos/latencia-session-vs-classico/benchmark-redesign/benchmark.py \
  battery --arm gpt54 \
  --cache-proof /raiz/privada/cache-proof.json \
  --run-name <run-gpt54> --artifacts-dir /raiz/privada/artifacts-gpt54
```

Troque `gpt54` por `terra-luna` para executar o segundo braço. O canário usa um dos
três QIDs declarados em `benchmark-redesign/arms.json`; a bateria usa os dez QIDs
Session, N=1, sem Classic, warmup ou retry automático. Ledgers e tentativas ficam
nos artefatos protegidos. Uma repetição precisa de decisão explícita e novo ID.

### Configurações GPT-5.4 e Terra/Luna

`benchmark-redesign/arms.json` define os dois braços e aponta para a rate card
`rate_cards/benchmark-redesign-v2.json`. O braço `gpt54` mantém os deployments
`seiia-ds`, `seiia-ds-mini` e `seiia-ds-nano`. O braço `terra-luna` usa Terra em
`standard` e Luna em `mini`, OCR, judge e `nano/explorador`. Os nomes canônicos de
Terra e Luna registrados na rate card são `gpt-5.6-terra` e `gpt-5.6-luna`.
O detalhamento por papel pertence ao [plano do benchmark](benchmark-redesign/plan.md).

Os runners recebem aliases, modelo canônico, provider, preços e janelas pela
configuração e pelas variáveis do ambiente. Não há alias de geração fixado no
runner. As rate cards `gpt56-session-v1.json` e `gpt56-session-v2.json` continuam
somente como artefatos históricos de execuções anteriores.

## Métricas

O runner registra:

- tempo até o primeiro conteúdo e tempo total;
- nota do juiz e sinal de alucinação;
- tokens por modelo e custo calculado pela rate card;
- usage OCR em bucket próprio; o benchmark redesenhado compara `cache_read` e não
  trata `cache_write` como operação ou componente de custo;
- chamadas de ferramentas e páginas obtidas pela busca web.

`reasoning` informa a análise de uso, mas não entra novamente no custo de saída.
Fontes devolvidas pela ferramenta não são contadas como páginas baixadas sem uma
confirmação do crawler.

## Retenção de resultados

Os arquivos `measurements.jsonl`, `progress.jsonl`, relatórios detalhados e cópias
da rate card ficam locais e são ignorados pelo Git. Eles contêm IDs de trace, IDs
temporários de sessão e telemetria que não participa da apresentação.

Os artefatos versionados em `artifacts/` alimentam as duas apresentações:

- `presentation-data.json` contém os campos exibidos ou validados pelo comparativo,
  além da configuração dos runs que originaram seus números. Ele não inclui trace
  IDs, IDs de tópico, métricas de ferramentas ou caminhos locais;
- `long-context-presentation-data.json` reconcilia os nove itens Long Context por
  ID e contém exatamente o conteúdo auditável exibido: pergunta, resposta, gold,
  critérios, avaliação do judge, scores, trace, ocorrências, hashes e referências
  lógicas às fontes protegidas. Documentos, evidence excerpts, SSEs e traces brutos
  não são copiados para o artefato.

A campanha vigente de contexto longo está consolidada no
[`apresentacoes/RELATORIO_LONG_CONTEXT_V2_BATERIA_COMPLETA_2026-07-24.md`](apresentacoes/RELATORIO_LONG_CONTEXT_V2_BATERIA_COMPLETA_2026-07-24.md).
Relatórios de canários e campanhas anteriores foram removidos quando superseded;
ledger, SSE, evidence, documentos e traces brutos correspondentes continuam
preservados somente nos outputs locais protegidos. O Git conserva o contrato,
manifesto, schemas, prompts genéricos hasheados e os campos de pergunta, resposta e
judge aprovados para a apresentação auditável — nunca o corpus ou os evidence
excerpts usados pelo juiz.

## Troca de modelos

`benchmark-redesign/arms.json` é a fonte comum dos aliases de `standard`, `mini` e
`nano/explorador`, do effort e da rate card. O launcher recebe `--arm` e injeta esses
aliases na stack. Os runners Session e Long Context também aceitam os mesmos campos
por argumentos: `--standard-model`, `--mini-model`, `--nano-model`,
`--reasoning-effort`, `--n`, `--rate-card` e `--reuse-historical-baseline`.
A rate card resolve alias, modelo canônico, provider e preços; não há manifesto ou
runner específico por geração de modelo. Use `--plan-only` para conferir a matriz
sem credenciais, rede ou execução.

Uma troca de configuração exige somente atualizar o arm, incluir os aliases e os
model cards na rate card versionada e fornecer as variáveis privadas do ambiente.
Payloads, golds, datasets, schemas e runners não mudam. Session e Long Context
continuam com runners separados porque medem metodologias diferentes; a apresentação
final alinha os artefatos persistidos, sem somar os datasets em um ranking único.

A stack isolada reutiliza a imagem existente e monta em read-only somente
`sei_ia`, `sei_extraction` e `sei_api` da worktree. Alterações nesses fontes ou
na seleção de modelos usam `up --no-build`. Rebuild é reservado a mudanças de
dependências, Dockerfile ou imagem-base.

Na bateria Session configurada, os dez tópicos são reservados antes da primeira
célula e cada POST passa por ledger append-only com `post_started`. SSE sem `end`,
frame `error`, contrato fresh divergente ou judge ausente dispara fail-fast. Depois
de `post_started`, a única retomada permitida usa SSE/trace já persistidos; o runner
não chama outro endpoint nem repete a inferência.

O pin `BENCHMARK_EVIDENCE_INDEX` é específico do pacote Long Context. O launcher o
remove durante Session; manter esse índice global faz uma pergunta fora da árvore
pinada falhar com `request_tree_mismatch` antes da geração.

A base comum está em
[`apresentacoes/METODOLOGIA_CENTRAL_BENCHMARKS_ASSISTENTE_SEI_IA.md`](apresentacoes/METODOLOGIA_CENTRAL_BENCHMARKS_ASSISTENTE_SEI_IA.md),
e as diferenças entre os dois estudos estão em
[`apresentacoes/RELATORIO_DIFERENCAS_METODOLOGICAS_SESSION_CLASSICO_VS_LONG_CONTEXT.md`](apresentacoes/RELATORIO_DIFERENCAS_METODOLOGICAS_SESSION_CLASSICO_VS_LONG_CONTEXT.md).
## Apresentações

- [`apresentacoes/README.md`](apresentacoes/README.md) é o índice dos entregáveis.
- [`apresentacoes/apresentacao-comparativo.html`](apresentacoes/apresentacao-comparativo.html) apresenta Session
  standard, mini, Luna e clássico nos dez QIDs de `benchmark-decision-v2`. Sua fonte
  versionada é [`artifacts/presentation-data.json`](artifacts/presentation-data.json).
- [`apresentacoes/apresentacao-long-context.html`](apresentacoes/apresentacao-long-context.html) apresenta a
  bateria Long Context V2 e permite auditar os nove casos, incluindo pergunta,
  resposta, judge e trace. Sua fonte versionada é
  [`artifacts/long-context-presentation-data.json`](artifacts/long-context-presentation-data.json).
- [`apresentacoes/benchmark-redesign/report.html`](apresentacoes/benchmark-redesign/report.html)
  é o relatório final do benchmark redesign; seu HTML e Markdown são gerados por
  `benchmark-redesign/build_report.py`.

Para reconstruir e validar os blocos gerados das duas apresentações, execute:

```bash
node experimentos/latencia-session-vs-classico/scripts/session-classico/build_comparison_presentation.mjs
node experimentos/latencia-session-vs-classico/scripts/long-context/build_long_context_presentation.mjs
node experimentos/latencia-session-vs-classico/scripts/long-context/build_long_context_presentation.mjs --check
uv run python experimentos/latencia-session-vs-classico/benchmark-redesign/build_report.py
uv run python experimentos/latencia-session-vs-classico/benchmark-redesign/build_report.py --check
```

Os geradores validam os respectivos schemas e cardinalidades antes de atualizar o
HTML. O gerador Long Context exige os nove IDs canônicos em ordem e rejeita item sem
pergunta, resposta, judge, trace ou gate aprovado.

## Fotografia consolidada de 14, 15 e 21/07/2026

A coleta abaixo usa N=1 por caso. Ela orienta a promoção, mas não sustenta inferência
estatística.

| Métrica | Session standard | Session mini | Session Luna | Clássico atualizado |
|---|---:|---:|---:|---:|
| Qualidade média | 0,807 | 0,756 | 0,761 | 0,588 |
| Tempo total médio | 70,76 s | 53,02 s | 68,33 s | 96,36 s |
| Custo total | US$ 2,782 | US$ 0,439 | US$ 0,669 | US$ 2,296 |

Essa fotografia histórica usa os mesmos dez QIDs de `benchmark-decision-v2`. A
rodada Luna antiga configurava Luna nos aliases standard e mini e mantinha Nano no
OCR; isso não descreve a alocação atual do braço Terra/Luna.

O clássico respondeu os dez casos depois da repetição de `LARGE-NEG-01` com a
autoindexação corrigida. O tempo desse caso inclui o processamento e a indexação dos
documentos durante a requisição.

## Limitações

- N=1 mede uma fotografia operacional. Use N>=3 para comparar configurações.
- O estado de cache de documentos e do índice vetorial muda a latência do primeiro
  acesso e precisa ser controlado entre endpoints.
- O juiz varia em perguntas web. Compare medianas e registre as fontes consultadas.
- A execução por `testclient` valida o fluxo, mas não produz latência comparável à API
  HTTP.

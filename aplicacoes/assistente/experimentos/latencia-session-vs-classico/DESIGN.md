# Desenho do benchmark decisório

## Problema

O runner já compara latência e qualidade, mas o endpoint clássico grava o trace fora do run e nenhum dos fluxos produz uma medição estruturada de ferramentas. O resultado impede comparar tokens, custo e exploração sem reconstruir dados manualmente.

## Uso

```bash
EXP_DATASET_NAME=benchmark-decision-v2 \
uv run python experimentos/latencia-session-vs-classico/scripts/session-classico/upsert_dataset.py \
  --create-dataset --decision-suite

EXP_DATASET_NAME=benchmark-decision-v2 EXP_TRANSPORT=http \
uv run python experimentos/latencia-session-vs-classico/scripts/session-classico/run_experiment.py \
  --decision-suite --rate-card rate_cards/v2.json --run-name decision-current
```

O segundo comando grava `measurements.jsonl`, `summary.json`, `report.md` e a rate card usada em `artifacts/<run-name>/`.

## Forma

- `sei_ia.services.benchmark_metrics` contém o callback opcional de ferramentas. Ele só é ativado pelo header de experimento, registra início, fim e erro por `run_id`, e produz dados JSON sem escrever logs.
- Os endpoints carregam o callback e anexam o resumo ao frame SSE `metadata`. O clássico também cria uma operação explícita para sua busca web, que chama `_arun()` fora do mecanismo de tools.
- `scripts/session-classico/benchmark_reporting.py` é puro. Ele lê tokens, rate card e registros do runner, calcula custo e renderiza os artefatos. `reasoning` informa a análise, mas não entra outra vez no custo.
- `dataset/session-classico/benchmark-decision-v2.json` é a lista versionada dos dez QIDs atuais. Ela referencia `cases.json`, que continua sendo a fonte das perguntas e rubricas no mesmo diretório.
- `artifacts/presentation-data.json` preserva somente os campos necessários para validar e reconstruir a apresentação atual. Os resultados brutos permanecem fora do Git.

## Decisão de síntese

O desenho usa a coleta opcional por callback como base e acrescenta a ponte explícita para a busca do clássico. Isso preserva o comportamento de produção e evita contar spans ou URLs como se fossem chamadas de ferramenta. A telemetria do clássico declara o que observou, pois sua busca web não atravessa callbacks LangChain.

## Trade-offs aceitos

- Aceitamos custo monetário indisponível até a rate card interna ser preenchida, em troca de nunca inventar preços.
- Aceitamos que `web_references_returned` não é sinônimo de páginas baixadas. O relatório usa esse nome para o clássico e `web_pages_fetched` apenas quando a ferramenta informa referências de crawl bem-sucedido.
- Aceitamos N=1 como fotografia operacional. O relatório mostra denominadores e não afirma significância estatística.

## Alternativas descartadas

- Inferir ferramentas por spans Langfuse. Os spans misturam infraestrutura e orquestração, e a busca clássica não entra neles como tool.
- Acoplar a geração do relatório aos routers. Os routers devem apenas produzir telemetria do request; arquivos e agregações pertencem ao runner.

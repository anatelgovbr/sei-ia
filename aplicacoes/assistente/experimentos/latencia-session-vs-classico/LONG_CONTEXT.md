# Benchmark de context disclosure

O benchmark usa o dataset interno `benchmark-long-context` e somente o endpoint
Deep Agents `/llm_lang/session_stream`. O runner é separado do comparativo histórico
para não herdar caminho clássico, `TestClient`, warmup, retry de inferência,
concorrência ou agregação. A base normativa comum dos benchmarks está em
[apresentacoes/METODOLOGIA_CENTRAL_BENCHMARKS_ASSISTENTE_SEI_IA.md](apresentacoes/METODOLOGIA_CENTRAL_BENCHMARKS_ASSISTENTE_SEI_IA.md).

Trocas de `standard`/`mini`, reasoning e rate card são configuração de runtime
do próprio runner v2. O manifesto, o contrato congelado e os resultados
históricos não são alterados nem reexecutados.

Antes dos preflights, renderize a stack com
`isolated_compose.py --workload long-context --evidence-index
/var/seiia/benchmark-evidence/evidence-index.json`. O launcher inclui o override
do pin somente nesse modo e recusa Long Context sem índice. Session usa o mesmo
launcher com `--workload session`, sem `--evidence-index`.

## Contrato fixo

- projeto Langfuse: `comparativo-deepagents-classico`;
- dataset: nome e ID fixos, exatamente nove identidades (três por caso);
- desenho corrente: `benchmark-long-context-evidence-v4-ocr-fresh-20260724`;
- hashes UTF-8 de pergunta/gold ancorados no código, sem conteúdo bruto;
- tipo, categoria e espécie de âncora do alvo fixos por ID;
- transporte HTTP sequencial, N=1, um tópico novo por item;
- `use_websearch=false`, `skip_memory=true`, `no_cache=true`, `trace=true`;
- no benchmark, `no_cache=false` é recusado antes da preparação; sessão/checkpointer
  são resetados, metadados processuais são rebuscados, Redis documental é bypassado
  e os bytes vêm fresh do SEI;
- threshold efetivo `200000`, configurado no container e nunca enviado no payload;
- execução real restrita à stack isolada local em `https://127.0.0.1:8188`;
- a stack isolada monta o evidence index em read-only e usa o snapshot somente como referência: rotas textuais determinísticas mantêm hash textual; `FORCE_DOWNLOAD` valida hash do binário fresh + identidade versionada/configurada do pipeline, exige saída não vazia e confere que o mesmo texto fresh foi materializado;
- a preparação emite heartbeat `status` sanitizado abaixo do timeout do proxy.
- o readback do Langfuse aguarda a ingestão completa com janela padrão de 900 s,
  até 120 retries, polling inicial de 4 s, fator de backoff 1,5 e teto de 30 s;
- `404` persistente é reportado como trace ausente, uma árvore sem término como
  trace incompleto e erros HTTP não recuperáveis como erro terminal;
- retries ocorrem somente na leitura/avaliação da observabilidade, nunca na
  inferência nem no POST do benchmark.

A v3 ancorou naturalmente o par documental do canário sem mudar árvore, IDs,
contagens ou fatos do gold. A v4 preserva essas referências, mas deixa de exigir
igualdade textual de OCR não determinístico: o contrato fresh passa a pinçar o
binário e a configuração do pipeline. `scripts/long-context/long_context_contract.py` fecha a versão
ativa exposta pelo runtime.

## Métricas v3

`scripts/long-context/long_context_scorer.py` separa dimensões que não podem ser confundidas:

- `target_alignment`: a resposta trata o alvo pedido;
- `completude`: checklist específico do alvo, sem exigir citação;
- `groundedness`: claims sustentados / claims verificáveis;
- claim sem evidência suficiente: `unverified`, tornando groundedness e
  hallucination `N/D`;
- hallucination: somente claim contradito ou comprovadamente inventado;
- `entendimento_abstrato`: 0/0,5/1, independente de citação e target alignment.

Fato verdadeiro sobre outro documento pode ter groundedness 1 e, simultaneamente,
`target_alignment=false` e completude baixa. O scorer nunca converte automaticamente
alvo errado ou evidência estreita do gold em alucinação.

## Evidência protegida

`scripts/long-context/long_context_evidence.py` cruza arquivos realmente abertos com o inventário de
conteúdo observado no endpoint. Cada documento é verificado por path hash e hash
de conteúdo contra um índice protegido. Para o judge, o runner seleciona somente
os menores excertos lexicalmente relevantes dos documentos abertos/citados.

Excertos, claims, resposta, rationale e mapeamentos ficam apenas no resultado
protegido `0600`. O ledger recebe somente hashes, contagens, booleanos, categorias
e scores. O trace segue o
[contrato de mascaramento do Session](../../../../docs/agent_docs/service_communication_patterns.md#langfuse-no-session-stream),
mas o trace raiz ainda contém o request sanitizado e a resposta integral. Seu acesso
e qualquer download bruto são protegidos.
Divergência de conteúdo determinístico, binário/pipeline fresh divergente, saída
OCR vazia, arquivo sem índice ou pacote vazio falha como lacuna de observabilidade;
não há fallback. No modo benchmark, falha por documento é propagada imediatamente
com etapa e identificador hasheado, em vez de ser omitida da sessão. O pacote do
juiz usa os bytes fresh do filesystem já materializado/validado, nunca o texto OCR
congelado. Essa exportação só existe com evidence pin ativo na stack isolada; o
header de coleta sozinho não libera conteúdo em configuração normal. Conteúdo fresh
fica no SSE/artefato protegido `0600` e não entra no resumo, relatório ou ledger.

Cada execução também conserva o dump SSE bruto em `stream.raw.sse` dentro do item
protegido, com permissão `0600`; ele permanece local e não entra no Git ou no
relatório sanitizado.

## Segurança e credenciais

O runner usa `LANGFUSE_URL`, `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` como
nomes padrão. Os antigos `LANGFUSE_COMPARATIVO_*` permanecem somente como fallback
de compatibilidade. Antes de ler o dataset, `/api/public/projects` deve retornar o
projeto exato. A configuração vem de arquivo protegido por `--env-file`; valores
nunca entram em argumentos, logs ou artefatos sanitizados. O arquivo SEI é passado
separadamente por `--sei-env-file`: o runner lê esse arquivo sem herdar sobrescritas do shell,
fecha o escopo de produção por hashes e compara a credencial e os dois endpoints
com o runtime do container.

O preflight estático continua validando modelo, threshold e pinning, mas não libera
reserva. Antes de qualquer evento de autorização/reserva, o runner chama
`GET /llm_lang/session_benchmark_live_preflight` no mesmo container que atenderá o
POST. Esse GET usa o `sei_client` efetivo para consultar o processo selecionado e
falha fechado em 401/403, host público/API cruzado, resposta vazia, processo
incompatível ou contrato inválido. Somente status, hashes, tipo da resposta e
duração são persistidos.

A stack isolada fixa `ASSISTENTE_LANGFUSE_TRUNCATE_PAYLOADS=false` para manter sem
truncamento os campos permitidos pela política geral de mascaramento. Esse opt-out
não desativa a remoção ou o mascaramento de conteúdo. O contrato e suas exceções
estão em
[`environment.md`](../../docs/getting-started/environment.md#observabilidade). Trace
bruto baixado deve permanecer `0600` e não entra em relatório.

## Modos

O default só faz project gate, leitura do dataset e validação, sem executar a
bateria. A saída JSONL começa com uma linha por cada um dos nove IDs, inclusive se
o guard do dataset falhar; todas declaram `execution_attempted=false`.

O fluxo legado mantém as duas fases explícitas. Primeiro, `--execute-canary` executa
somente `case-0960k-q2-synthesis` e grava uma tentativa no ledger protegido:

```bash
uv run python experimentos/latencia-session-vs-classico/scripts/long-context/run_long_context_benchmark.py \
  --env-file <config-protegida> \
  --base-url https://127.0.0.1:8188 \
  --protected-root <root-protegido> \
  --run-name <run> \
  --judge-url <proxy-local> --judge-model <modelo> \
  --evidence-index <indice-protegido> \
  --execute-canary
```

Somente um ledger com `canary_gate_status=passed` libera `--continue-run` no mesmo
`run-name`. A continuação pula identidades registradas e rejeita duplicatas como
violação de N=1. Campanhas autorizadas que precisam continuar após falha usam
`--execute-full-battery`: o ledger deve começar vazio e as nove identidades são
tentadas uma vez em ordem canônica, com progresso sanitizado por item. Todo modo
real chama o preflight sem corpus antes do primeiro POST; isso não consome item. O
preflight também expõe profile/modelo principal e janela configurada para a v2
recusar qualquer configuração diferente de `standard` ou abaixo de 500.000 tokens.

## Barreira do canário

Além de HTTP/SSE, context disclosure, telemetria, contagens e trace associado, o
canário exige pacote de evidência completo e:

- `target_alignment=true`;
- completude >= 0,8;
- groundedness >= 0,8;
- entendimento abstrato = 1;
- hallucination_count = 0;
- zero claims `unverified`.

Qualquer `N/D` ou violação bloqueia a continuação. A ordem de disclosure usa a
sequência monotônica de início das tools. Juiz, scorer e evaluator são excluídos
de `calls_llm`.

## Validação offline

```bash
uv run pytest -n 0 \
  tests/unit/test_long_context_benchmark.py \
  tests/unit/test_benchmark_metrics.py \
  tests/unit/test_session_router.py
ruff check \
  experimentos/latencia-session-vs-classico/scripts/long-context/long_context_*.py \
  experimentos/latencia-session-vs-classico/scripts/long-context/run_long_context_benchmark.py \
  sei_ia/services/benchmark_metrics.py \
  sei_ia/routers/session/stream.py \
  tests/unit/test_long_context_benchmark.py \
  tests/unit/test_benchmark_metrics.py \
  tests/unit/test_session_router.py
```

## Campanha v2 (nova, sem alterar a bateria v3)

A campanha v2 é isolada do baseline acima. O Git conserva somente o manifesto
`dataset/long-context/benchmark-long-context-v2.json`, schemas, contrato, prompts versionados e
hashes. Perguntas, golds, rubricas, metadados processuais, evidências, respostas,
SSE e traces integrais são resolvidos por referências `protected://` e permanecem
em uma árvore local com diretórios `0700` e arquivos `0600`.

O contrato `benchmark-decision-v2-long-context-adapter-1` mantém as métricas
canônicas `groundedness`, `completeness`, `citation_quality`, `hallucination`,
`negativa_correta` e `overall`. `target_alignment` e `hallucination_count` são
auxiliares. Claim `unsupported` entra no denominador de groundedness sem ligar
alucinação; somente `contradicted`/invenção liga alucinação. O gate não usa
`entendimento_abstrato`. `pending_trace` e `pending_evaluation` são estados
recuperáveis; `technical_unavailable` é o único estado que representa `N/D`.

A política `long-context-v2-canary-gates-v2-20260724` separa quatro dimensões:
qualidade, comparabilidade, observabilidade e integridade/técnico. Groundedness e
completeness conservam os limiares históricos de 0,8 somente como diagnóstico;
`citation_quality` e `overall` continuam sem threshold. Qualidade bloqueia apenas
resposta vazia, `target_alignment=false`, `hallucination=true` ou, em item
`insufficient-evidence`, `negativa_correta=false`. As demais dimensões continuam
bloqueantes no gate final e indicam separadamente a causa da recusa.

A telemetria v2 contabiliza apenas generations folha e deduplica por observation ID.
Ela persiste profile solicitado, deployment, modelo canônico e provedor, separa
input fresco/cache/output/reasoning e calcula custos de agente e juiz separadamente
com a rate card da campanha hasheada. No usage do Langfuse, `output` é saída visível
e exclui `output_reasoning`; o total e o billing de saída somam ambos exatamente uma
vez. A configuração comum em
`benchmark-redesign/arms.json` resolve `standard`, `mini`, `OCR`, judge e
`nano/explorador` pela rate card e pelo ambiente. O braço GPT-5.4 usa seus três
deployments; no braço Terra/Luna, Luna ocupa `mini`, OCR, judge e `nano/explorador`.
Os detalhes por papel ficam no [plano do benchmark](benchmark-redesign/plan.md).
As rate cards `gpt56-session-v1.json` e `gpt56-session-v2.json` são históricas e não
definem a campanha redesenhada.

A validação offline não acessa Langfuse nem executa modelo:

```bash
uv run python experimentos/latencia-session-vs-classico/scripts/long-context/run_long_context_v2.py \
  --validate-only \
  --protected-bundle-root <bundle-protegido>
uv run pytest -n 0 tests/unit/test_long_context_v2.py
```

O modo de inferência da v2 mantém `case-0960k-q2-synthesis` como default histórico.
`--canary-item-id` aceita somente um ID presente no manifesto; a seleção explícita
deve estar vinculada à autorização humana correspondente. O ledger da campanha
reserva o item antes do POST e recusa uma segunda reserva, inclusive após mudança de
contrato ou run name. A exceção única autorizada é a substituição da tentativa
pré-agente executada no escopo SEI incorreto: ela exige o execution/trace congelado,
prova protegida de zero generations/tools/juiz/tokens/custo, motivo
`wrong_sei_environment_pre_agent` e autorização do capitão hasheada. A remediação
OCR posterior também exige predecessor e prova pré-agente exatos, além de uma
autorização própria, e só pode ser consumida uma vez; uma quarta tentativa é
recusada. Retry existe somente para avaliação e ingestão/readback do trace; não há
retry do endpoint.

```bash
uv run python experimentos/latencia-session-vs-classico/scripts/long-context/run_long_context_v2.py \
  --execute-canary \
  --env-file <config-protegida> \
  --sei-env-file <security-env-de-producao> \
  --base-url https://127.0.0.1:8188 \
  --protected-bundle-root <bundle-protegido> \
  --protected-output-root <output-protegido> \
  --run-name <run-v2> \
  --canary-item-id <item-autorizado> \
  --replace-invalid-execution-id <execution-id-autorizado-quando-aplicavel>
```

Antes de subir a stack isolada, remova a variável conflitante do shell com
`env -u SEI_ADDRESS docker compose ...`; `docker compose config` e uma inspeção
sanitizada dentro do container devem comprovar os mesmos hashes de produção. O GET
live ainda é obrigatório e não pode ser substituído por essa inspeção estática.

O runner grava relatório integral e dumps somente no output protegido e emite no
stdout apenas o resumo sanitizado. Ele persiste `no_cache` solicitado/efetivo, reset
de sessão comprovado, fontes documental/processual, comparabilidade de cold start e
separa preparação, stream até terminal,
avaliação e readback; as duas últimas etapas não entram na latência de inferência.
O canário histórico usou `frozen_evidence_snapshot`: qualidade, telemetria e custos
seguem preservados nos artefatos locais, mas sua latência não é comparável a cold
start SEI e ele não integra o agregado oficial. Comparabilidade é dimensão
independente da qualidade e continua bloqueante quando exigida. No segundo canário,
a tentativa original terminou antes do agente por ambiente SEI incorreto; não houve
retry, julgamento, tokens ou custo. Predecessor, substituição e autorizações
permanecem no ledger/output protegido, sem relatório intermediário versionado.
Se o processo cair depois do POST, o modo
`--resume-readback` exige o mesmo `--run-name`, a avaliação oficial e o trace já
vinculados no ledger; ele recupera apenas trace/usage/custo e nunca chama o endpoint
ou o juiz. Scores Langfuse usam IDs determinísticos para a retomada ser idempotente.
Mudanças de política de gate usam `--reclassify-existing`: o modo lê somente o
resultado protegido e o ledger do run, deriva um novo artefato e anexa o evento
`gate_reclassified`. Não chama endpoint, agente, juiz, OCR ou Langfuse e não cria
outra avaliação oficial.
Sem autorização externa, o runner encerra no gate com `stop_after_canary=true` e
`full_battery_authorized=false`. A bateria excepcional usa autorização hasheada e
modos explícitos `--full-battery-dry-run`, `--execute-full-battery` e
`--resume-full-battery`. O dry-run prova a partição e o SEI live sem POST; a execução
reserva cada item sequencialmente no ledger. Resultado fresh válido é reutilizado,
predecessor frozen fica preservado fora do agregado oficial e somente itens faltantes
recebem POST. Score contínuo baixo não interrompe; comparabilidade ou integridade
sistêmica interrompem. Respostas/trace completos cuja falha ocorreu apenas no
pós-processamento podem retomar evidence/juiz/readback sem repetir inferência. A
campanha autorizada está em
[`apresentacoes/RELATORIO_LONG_CONTEXT_V2_BATERIA_COMPLETA_2026-07-24.md`](apresentacoes/RELATORIO_LONG_CONTEXT_V2_BATERIA_COMPLETA_2026-07-24.md).

# Memória do experimento de latência

## Stack isolada e escopo SEI

- Na interpolação do Compose, variáveis `SEI_ADDRESS` e
  `SEI_API_DB_ADDRESS` herdadas pelo processo têm precedência sobre
  `--env-file`. O `env_file` do serviço ainda pode carregar `SEI_ADDRESS`,
  criando um par cruzado com `SEI_API_DB_ADDRESS` interpolado de outra origem.
- Antes de iniciar a stack isolada, remova ambas as variáveis do ambiente ou
  use um invocador que carregue somente as fontes aprovadas. Não imprima os
  valores.
- Valide primeiro o Compose renderizado e depois o ambiente efetivo do
  container por hashes de endpoints e origens. Só prossiga após o GET de
  runtime, o GET live read-only do SEI e a prova de zero POST.
- Preserve o preflight de coerência público/API em
  `sei_ia/routers/session/benchmark.py`. HTTP 409 bloqueia o benchmark; nunca
  contorne essa validação.
- Ative `BENCHMARK_EVIDENCE_INDEX` somente nas células cobertas pelo pacote
  montado. O índice Long Context não cobre a bateria Session completa; deixar o
  pin global causa `request_tree_mismatch` nos processos ausentes. Quando
  habilitado, o pin continua obrigatório e fail-closed.
- Selecione `--workload session` ou `--workload long-context` no launcher. Session
  remove os pins herdados e Long Context injeta o índice por override próprio;
  nunca alterne os modos chamando Compose diretamente.

## Modelos auxiliares da preparação documental

- A preparação ocorre antes do modelo principal e pode chamar OCR para páginas
  escaneadas. Fixe `ASSISTENTE_OCR_MODEL` no alias publicado
  pelo LiteLLM transversal; o profile literal `nano` não é um deployment.
- Fixe também `LITELLM_NANO_MODEL`: o agente usa esse profile
  auxiliar em contextos longos, independentemente do alias de OCR.
- Mantenha o alias de OCR no manifesto, na configuração efetiva e no preflight
  runtime. Se ele mudar, gere um pacote privado sucessor: o alias faz parte de
  `fresh_extraction_pipeline_sha256`; nunca contorne ou desative o pin.
- A alocação de papéis é autoritativa em
  `benchmark-redesign/arms.json` e `benchmark-redesign/plan.md`. O launcher e os
  runners carregam os três aliases do arm; nunca fixe um modelo fora da configuração
  selecionada. Usage OCR fica no scope `ocr`, fora das generations do trace, e
  preserva campos brutos do provider sem transformá-los em custo.
- Separe os budgets de retry: `ASSISTENTE_MAX_RETRIES=0` bloqueia retry de LLM;
  o transporte GET do SEI usa `ASSISTENTE_SEI_API_MAX_RETRIES`. Não zere o
  segundo por herança ao exigir zero retry de inferência.
- Corpo HTTP 200 não JSON do SEI é falha transitória do GET e usa o mesmo
  budget de retry do transporte. Propague o erro esgotado: a extração de
  metadados não pode convertê-lo em conjunto vazio, pois isso simula ausência
  canônica e gera `fresh_process_metadata_missing` enganoso.

## Modelos, telemetria e ciclo local

- Resolva aliases, modelo canônico, provider e preços pela rate card passada aos
  runners existentes. Não crie mapa hardcoded ou runner específico por modelo.
- Preserve rate cards usadas como artefatos históricos imutáveis. Mudança oficial
  de preço ou model card cria sucessor versionado; planos, readback e resultados
  carregam sua identidade/hash e recusam agregação entre cards incompatíveis.
- O juiz Long Context usa o deployment do profile `mini` da campanha. O
  dry-run deve validar também URL e chave explícitas do proxy do juiz; não fixe
  o alias histórico no runner.
- No benchmark redesenhado, `cache_write` não é operação, métrica comparativa nem
  componente de custo. Campos brutos homônimos do provider podem ser preservados
  como telemetria, mas não entram em gate ou preço. `cache_read` deve ser observado
  e reconciliado ponta a ponta. O runner incorpora usage do judge a
  `tokens_by_model` e `tokens_by_scope.judge`.
- Rate limit durante geração invalida a célula, mesmo com reasoning parcial.
  Preserve trace/SSE e lineage; respeite `retry-after` quando exposto ou 15
  minutos conservadores desde o terminal quando não houver header. Nunca
  declare zero tokens/custo para essa tentativa.
- A stack isolada reutiliza a imagem existente e monta somente os fontes
  necessários da worktree em read-only. Use `up --no-build` para Python,
  configuração e modelos; rebuild somente para dependência, Dockerfile ou
  imagem-base.
- Use `scripts/shared/isolated_compose.py`: ele fixa projeto/rede/porta, recusa
  contaminação efetiva, valida o JSON renderizado e só permite `up --no-build`
  depois dos gates. Não invoque o Compose manualmente para esta campanha.
- A bateria Session reserva todos os tópicos antes da primeira célula. Cada célula
  persiste `post_reserved` e `post_started`; depois dessa fronteira, falha exige
  recuperação de SSE/trace, nunca novo POST. O primeiro resultado inválido bloqueia
  todas as células posteriores.
- O nginx experimental e o app participam de `benchmark_assistente_frontend`; o
  app mantém ali o alias `api_assistente`. Ambos usam também a rede externa
  **dedicada** da campanha, necessária para materializar o gateway da porta 8188.
  Nunca os conecte à rede compartilhada de uma stack de ambiente.
- O benchmark redesenhado não configura operação explícita de cache write.
  `no_cache=True` continua desabilitando somente cache/sessão da aplicação; cache
  read do provider é telemetria separada e deve permanecer mensurável.
- Política de campanha fica neste diretório. O produto expõe somente os dois GETs
  sanitizados em `routers/session/benchmark.py`, o header opt-in de diagnóstico e
  a validação protegida de evidence. Não adicione rate card, ledger, custo ou
  configuração de prompt cache a `Settings`, `get_model` ou às libs compartilhadas.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.

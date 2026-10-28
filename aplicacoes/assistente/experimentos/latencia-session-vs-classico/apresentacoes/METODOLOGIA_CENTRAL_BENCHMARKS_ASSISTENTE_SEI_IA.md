# Metodologia central dos benchmarks do Assistente SEI IA

## Finalidade e força normativa

Este documento define o contrato mínimo para benchmarks reproduzíveis do Assistente
SEI IA. Protocolos podem acrescentar controles, mas não relaxar identidade,
rastreabilidade, segurança ou comparabilidade sem nova versão e justificativa.

Há dois protocolos atuais:

1. **Comparação Session vs Classic** — comparação de arms para um mesmo conjunto de
   perguntas.
2. **Capacidade Long Context / Context Disclosure** — teste do `session_stream` em
   corpora acima da janela direta; não é comparação contra o clássico.

## 1. Identidade da campanha

Antes de qualquer chamada:

- fixar nome e ID do dataset, projeto, schema e versão do desenho;
- enumerar IDs esperados e rejeitar ausências, extras ou duplicatas;
- ancorar pergunta, gold, rubrica e target por hash ou versão imutável;
- registrar código/HEAD, run name, endpoint, configuração de modelos e rate card;
- separar identidade do desenho de avaliação da identidade runtime de documentos;
- executar readback do dataset após publicação e antes da campanha.

Alteração de pergunta, gold, rubrica, corpus, judge ou gate cria nova versão. Não se
reescreve resultado antigo para fazê-lo parecer produzido pelo contrato novo.

## 2. Gold set e evidência

O gold set deve declarar o alvo factual e a extensão da evidência suficiente. Para
negativas, deve especificar o que foi procurado e por que a ausência é avaliável.
Rubricas não podem premiar fato correto sobre alvo errado.

Conteúdo SEI, respostas, excertos, prompts internos e traces brutos ficam fora do
Git. Manifestos versionados usam referências protegidas e hashes. Resultado
sanitizado pode conter contagens, scores, categorias, IDs de trace autorizados e
hashes, nunca conteúdo documental.

## 3. Ambiente isolado

Cada campanha registra e valida:

- stack/namespace isolado, endpoint e transporte reais;
- banco, Redis, filesystem e serviços auxiliares próprios quando o estado influencia
  o resultado;
- credenciais carregadas de arquivos protegidos, nunca de argumentos/logs;
- host/projeto externos confirmados por API autenticada;
- modelos/deployments efetivos, provider e limites de contexto;
- relógio e timeout coerentes com proxy, SSE e readback.

Preflight não pode consumir item experimental. Falha de identidade ou ambiente
bloqueia antes da reserva/POST.

## 4. Política de modelos

Modelo principal, auxiliares, OCR, embeddings e judge devem ser fixados por aliases
e resolvidos para deployments/modelos canônicos no runtime. Troca de modelo no meio
da campanha invalida comparabilidade, salvo arm explicitamente definido.

Rate card é versionada e hasheada. Custo ausente fica indisponível; nunca se assume
zero. Reasoning, cache read, input fresco e output são contabilizados sem dupla
contagem.

## 5. Cache, estado e materialização

A política precisa ser explícita por camada:

- sessão/checkpointer;
- cache documental;
- índice vetorial;
- cache do provedor/modelo;
- OCR/extraction;
- histórico de conversa.

`no_cache` só pode ser afirmado quando o runtime prova o efeito, não apenas porque o
payload pediu. Warmup, pré-indexação ou pré-materialização devem ser iguais entre
arms comparáveis ou declarados como parte do arm.

Em Long Context fresh, sessão/checkpointer são resetados, conteúdo e metadata vêm do
SEI, Redis documental é purgado/bypassado e o snapshot pinned atua apenas como
validador. Rota textual determinística valida conteúdo; rota OCR valida binário
fresh, pipeline versionado e saída não vazia.

## 6. Unidade experimental, N e concorrência

Cada protocolo declara unidade, N, ordem, concorrência e critério de reuso. O ledger
reserva antes da chamada e recusa duplicata.

- N=1 é diagnóstico/fotografia operacional; não sustenta significância.
- Comparações de promoção ou percentis exigem N≥3 por célula, preferencialmente com
  ordem randomizada ou blocos.
- Concorrência 1 isola itens; concorrência maior mede throughput e forma outro
  experimento.
- Resultado só pode ser reutilizado se identidade, ambiente, freshness e contrato
  forem comprovadamente equivalentes.

## 7. Retries

Retry de inferência não é mecanismo de seleção. Por padrão é zero. Repetição exige
falha técnica invalidante comprovada, autorização e vínculo append-only com o
predecessor; score baixo nunca autoriza replay.

Retry de judge ou readback pode ocorrer quando previsto, pois não altera a resposta
do agente. Tentativas são preservadas e existe uma única avaliação oficial por item.

## 8. Observabilidade e Langfuse

Cada resultado deve vincular trace completo e verificar:

- início/fim do agente e árvore sem spans pendentes;
- generations folha deduplicadas;
- modelo/deployment/profile e usage por chamada;
- tools com sequência, ator, outcome e referências sanitizadas;
- dataset run/item correspondente;
- ingestão/readback completo antes do fechamento.

O trace pode conter material protegido e obedece à mesma retenção do SSE. Relatórios
Git não incorporam dumps.

Preparações longas precisam, em campanhas futuras, de spans por etapa: metadata
processual, purge/cache, consulta SEI, download, OCR/extraction, escrita/tokenização
e validação. Heartbeat prova vida, não atribui causalidade.

## 9. Tempos

Definir relógio, origem e inclusões antes da execução.

### SSE

- `total_até_terminal`: início do POST/SSE até `end` ou terminal classificado;
- `preparação`: subconjunto do total, do início da coleta até a sessão materializada;
- `pós_preparação = total_até_terminal − preparação`;
- `avaliação` e `trace_readback`: reportados separadamente e excluídos da inferência.

Nunca exibir preparação e total como barras independentes somáveis. Gráfico correto
é empilhado: preparação + pós-preparação = total.

### Comparações

Comparar latências somente com mesmo escopo. `TestClient` não é comparável a HTTP
real; cold start não é comparável a cache quente; execução que inclui indexação não
é equivalente a consulta sobre índice pronto.

## 10. Tokens e custo

Contabilizar por scope (`agent`, `judge`, e outros observados) e modelo:

- calls;
- input fresco;
- cache read;
- output visível;
- reasoning;
- total canônico;
- custo pela rate card.

Cobertura parcial deve ser rotulada. OCR ou serviço fora dos traces não é estimado.
Totais agregados incluem apenas scopes declarados.

## 11. Avaliação de qualidade

O judge recebe resposta, rubrica e somente a evidência autorizada/materializada. Seu
schema é validado; saída inválida pode ser rejulgada conforme política.

Dimensões canônicas de Long Context:

- `target_alignment`;
- `groundedness` por claims verificáveis;
- `completeness` contra checklist do alvo;
- `citation_quality`;
- `hallucination` apenas para contradição/invenção;
- `negativa_correta` quando aplicável;
- `overall` como síntese diagnóstica.

Claim não sustentado reduz groundedness, mas não vira alucinação automaticamente.

## 12. Gates técnicos versus métricas diagnósticas

Relatórios devem separar:

1. **qualidade catastrófica:** resposta vazia, alvo errado, alucinação ou negativa
   incorreta;
2. **comparabilidade:** ambiente, cold start/cache, modelo e contrato;
3. **observabilidade:** evidence, trace, usage e telemetria;
4. **integridade/técnico:** ledger, N, transporte e retenção.

Scores contínuos são diagnósticos salvo decisão prévia versionada. Um score baixo
não pode interromper campanha ou provocar retry ad hoc.

## 13. Tratamento de falhas

Classificar antes de decidir:

- qualidade baixa: registrar e continuar;
- falha técnica isolada: registrar; continuar se o contrato permitir;
- falha sistêmica/comparabilidade falsa/integridade inválida: parar;
- falha após agente completo: recuperar evidence/judge/readback somente se SSE,
  trace e filesystem preservados provarem a resposta; não repetir inferência.

Toda correção é append-only: predecessor, causa, decisão e substituição ficam
ligados. Fallback silencioso é proibido.

## 14. Rastreabilidade e retenção

Artefatos protegidos usam diretórios `0700`, arquivos `0600` e nenhum symlink.
Preservar:

- autorização e ledger;
- payload/SSE/trace/evidence protegidos;
- tentativas de judge;
- resultado protegido e sanitizado;
- hashes finais e readback;
- diagnóstico de incidentes.

No Git ficam contrato, código, schemas, metodologia e relatório sanitizado vigente.
Relatórios superseded podem ser removidos do branch sem apagar evidência local.

## 15. Critérios de comparabilidade

Dois resultados só são comparáveis quando coincidem, ou diferem como arm explícito,
em:

- dataset/gold/rubrica;
- endpoint e transporte;
- ambiente e origem dos documentos;
- política de cache/materialização;
- modelos e rate card;
- N, concorrência, warmup e retries;
- escopo temporal e cobertura de usage;
- judge/gates.

Diferença não controlada deve aparecer como limitação, não como ganho do método.

## Protocolo A — Session vs Classic

Use `benchmark-decision-v2`, os mesmos QIDs por arm e HTTP real. Defina arms Session
e Classic antes da rodada; configure cache/indexação de forma simétrica ou rotule o
custo de indexação. Normalize telemetria de tools, inclusive busca clássica. Compare
qualidade, tempo total, tokens e custo entre arms. Para promoção, execute N≥3.

## Protocolo B — Long Context / Context Disclosure

Use `benchmark-long-context` e apenas `/llm_lang/session_stream`. Fixe threshold
200.000, `no_cache=true`, concorrência 1, N=1 diagnóstico, sem websearch/warmup/retry
de inferência. Materialize corpus fresh e valide-o com identidade pinned. Execute
factual, synthesis e insufficient-evidence por faixa. Meça capacidade, exploração,
qualidade, total até terminal, preparação incluída e pós-preparação.

O objetivo não é vencer o clássico: é verificar acesso seletivo e resposta ancorada
quando o corpus excede a janela direta. O limite direto desejado de 500.000 tokens e
trade-offs de concorrência/cache são hipóteses para novas campanhas, não conclusões
da bateria atual.

## Checklist de fechamento

- dataset/projeto/IDs lidos de volta;
- reservas e N reconciliados;
- traces e usage completos;
- gates por dimensão;
- tempos sem sobreposição enganosa;
- custo com cobertura declarada;
- permissões e hashes validados;
- relatório sanitizado e metodologia atualizados;
- artefatos protegidos preservados;
- MR atualizado sem merge não autorizado.

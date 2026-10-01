# Diferenças metodológicas: Session vs Classic e Long Context

## Resumo executivo

Os dois estudos respondem perguntas diferentes e não devem ser colocados na mesma
linha de ranking:

- **Session vs Classic** compara alternativas de atendimento para o mesmo conjunto
de casos. A unidade de análise é método × pergunta; qualidade, latência e custo são
comparativos entre arms.
- **Long Context / Context Disclosure** mede se o `session_stream` consegue gerir
corpora muito maiores que a janela de injeção direta. A unidade é corpus × tipo de
pergunta; não existe arm clássico.

Ambos usam N=1 por item e são fotografias operacionais, não testes de significância.
A base normativa comum está em
[METODOLOGIA_CENTRAL_BENCHMARKS_ASSISTENTE_SEI_IA.md](METODOLOGIA_CENTRAL_BENCHMARKS_ASSISTENTE_SEI_IA.md).

## Comparação estruturada

| Dimensão | Session vs Classic | Long Context v2 |
|---|---|---|
| Objetivo | Comparar abordagens de resposta | Provar capacidade e gestão seletiva de contexto |
| Pergunta decisória | Qual método entrega melhor equilíbrio qualidade/tempo/custo? | O Session responde com evidência em corpora acima da janela direta? |
| Dataset | `benchmark-decision-v2`, 10 QIDs | `benchmark-long-context`, 9 itens em 3 corpora |
| Arms | Session standard, mini, Luna e clássico | Somente `session_stream` com modelos default |
| Unidade experimental | arm × QID | corpus × factual/synthesis/insufficient-evidence |
| Transporte | endpoints Session e clássico por HTTP | `/llm_lang/session_stream` por HTTP SSE |
| Materialização | Depende do arm e do estado controlado de documentos/índice | Fresh do SEI, filesystem de sessão e validação pinned obrigatória |
| Cache | Deve ser alinhado entre arms e declarado | `no_cache=true`, sessão/checkpointer resetados, zero warmup |
| Concorrência | Runs controlados por método | 1; oito POSTs fresh sequenciais e um resultado fresh reutilizado |
| Retry | Não usar para selecionar melhor resposta | Nunca no agente; somente judge/readback quando autorizado |
| Qualidade | Judge/rubrica comparáveis entre arms | Groundedness, completeness, citation quality, overall e condições catastróficas |
| Ferramentas | Telemetria normalizada, incluindo ponte da busca clássica | Exploração do filesystem: `ls`, `grep`, `read_file`, tarefas e planejamento |
| Custo | Rate card aplicado por arm/modelo | Usage observado de agente e juiz; OCR de preparação indisponível |
| Interpretação | Diferença entre métodos | Capacidade do Session dentro de uma faixa; não é Session vs Classic |

## Experimento Session vs Classic

O comparativo usa os mesmos dez QIDs e rubricas para quatro configurações. O runner
mede tempo até conteúdo/terminal, qualidade do judge, tokens, custo e ferramentas.
O clássico tem uma ponte explícita de observabilidade para sua busca web, pois ela
não atravessa o callback de tools. Os modelos Session standard/mini/Luna e o fluxo
clássico são arms, não etapas de uma mesma execução.

Comparabilidade exige o mesmo dataset versionado, ambiente, transporte HTTP e
política de cache. Um caso em que o clássico indexa durante a requisição precisa
ser marcado: esse tempo é real para aquela condição, mas não equivale a uma consulta
com índice previamente pronto. O N=1 orienta decisão e diagnóstico; diferenças
pequenas não sustentam superioridade estatística.

## Experimento Long Context / Context Disclosure

O threshold efetivo é fixo em 200.000 tokens. Acima dele, o agente não recebe todo
o corpus no prompt: a sessão materializa documentos como arquivos, expõe inventário
e o agente constrói contexto com busca e leitura seletivas. O limite desejado para
injeção direta é 500.000 tokens, a ser avaliado em experimento futuro; não foi
alterado nesta bateria.

Os corpora canônicos têm 960.682, 5.120.866 e 6.260.548 tokens, com 59, 331 e 61
documentos. Cada faixa contém uma pergunta factual, uma síntese e uma pergunta de
evidência insuficiente. O dataset guarda identidade/hashes; perguntas, golds,
evidência e respostas brutas permanecem protegidos fora do Git.

O contrato oficial foi N=1, concorrência 1, `no_cache=true`, zero warmup e zero
retry de inferência. Um factual fresh válido foi reutilizado e oito POSTs fresh
completaram os nove itens. Score contínuo baixo permaneceu diagnóstico; bloqueariam
resposta vazia, alvo errado, alucinação, negativa incorreta, comparabilidade falsa,
observabilidade insuficiente ou integridade sistêmica.

## Como ler o tempo: total, preparação e agente

`stream_terminal_s` é o **total desde o início do POST/SSE até o frame terminal**.
`session_preparation_s` está contido nesse total. A terceira medida é derivada:

`post_preparation_stream_s = stream_terminal_s − session_preparation_s`

Logo, nunca se soma “preparação + stream”. O relatório completo foi corrigido para
usar “total até terminal”, “preparação (incluída)” e “pós-preparação”. Avaliação do
judge e readback Langfuse são medidos à parte e excluídos da latência de inferência.

## Diagnóstico causal dos casos 5120k

### Fatos

- 5120k: 331 arquivos materializados, ~18,0 MB, 132 rotas binárias fresh e 199
  textuais; preparação de 719,70–757,24 s.
- 6260k: 61 arquivos, ~18,3 MB, 39 rotas binárias e 22 textuais; preparação de
  47,97–60,80 s.
- Os três itens 5120k comprovaram `no_cache`, reset, fonte `sei_no_cache`, corpus
  completo e validação aprovada.
- Q1/Q2 5120k gastaram 73,46/66,93 s após preparação; seus traces do agente duraram
  66,82/64,31 s. Q3 gastou 242,17 s após preparação, com 84 tools e 29 calls.

### Cadeia causal

- **Trigger:** fan-out de 331 documentos fresh, 132 deles na rota binária, com
  concorrência máxima 30.
- **Masking condition:** nomenclatura “Prep.” versus “Stream” e uso de tokens como
  aproximação de trabalho por documento.
- **Sintoma:** 809,91–961,88 s até terminal.
- **Primeira divergência:** materialização pré-agente; q1 6260k percorre o mesmo
  fluxo lógico e chega ao agente em 47,97 s.
- **Inferência:** consulta/download/extração/OCR/validação por documento dominam a
  preparação do 5120k. Q3 soma exploração posterior mais extensa.
- **Contrafactual mínimo:** manter corpus/pergunta e permitir pré-materialização
  controlada, ou variar apenas concorrência, deve reduzir preparação sem redução
  proporcional do wall do agente. O 6260k já é contrafactual observacional contra a
  hipótese “mais tokens sempre demora mais”.
- **Refutação possível:** spans internos mostrando pouca duração no fan-out e espera
  dominante em reset/checkpointer ou metadata processual.

### Lacunas

A preparação só tem duração total e heartbeat. Faltam spans separados para consulta
processual, purge Redis, SEI, download, OCR, escrita/tokenização e validação. Os
resumos também não retêm MIME nem tamanho binário agregados. Portanto, a atribuição
ao bloco de materialização é factual; a divisão interna é inferencial.

## Resultados e limites de interpretação

Na bateria Long Context, 9/9 itens passaram os gates, sem alucinação ou desalinhamento
e com negativas corretas 3/3. Foram 5.797.991 tokens, 292 tools e USD 5,45067944.
Groundedness médio foi 0,8413 e overall médio 0,9511. O resultado prova capacidade
na amostra e no contrato, não throughput, percentil de latência ou estabilidade.

O custo de OCR não aparece nos traces do agente. O juiz teve retry contratual em um
item, mas uma única avaliação oficial por item. Recuperações pós-processamento
reutilizaram SSE/trace/filesystem completos e não repetiram inferência.

## Higiene do projeto de avaliação

O inventário autenticado encontrou os dois datasets canônicos e um dataset legado.
A API pública autenticada permite readback e operações de itens/runs, mas respondeu
`405` à deleção do dataset inteiro. Conforme a política da tarefa, não houve UI,
banco direto nem deleção de itens/runs como substituto. A remoção do container legado
permanece bloqueada até existir operação pública oficial; os dois canônicos foram
preservados sem mutação.

Resultados completos: [RELATORIO_LONG_CONTEXT_V2_BATERIA_COMPLETA_2026-07-24.md](RELATORIO_LONG_CONTEXT_V2_BATERIA_COMPLETA_2026-07-24.md).

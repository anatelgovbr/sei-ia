# Plano para benchmark Session constante e simples

Status: **implementado; execução unattended das duas configurações autorizada em 2026-08-03**.

## Objetivo e braços

Comparar duas configurações fixas com os mesmos payloads e gold answers de cada dataset, `N` fixo e uma única camada de configuração compartilhada pelos runners nativos:

- **Braço A — Session — GPT-5.4 / GPT-5.4-mini / GPT-5.4-nano**
- **Braço B — Session — Terra / Luna**

Os nomes acima são os únicos nomes de braços. O benchmark não reutiliza a nomenclatura de campanhas anteriores.

## Alocação por papel — contrato confirmado

| Papel | Braço A: profile / alias | Modelo canônico | Reasoning/effort | Braço B: profile / alias | Modelo canônico | Reasoning/effort |
|---|---|---|---|---|---|---|
| standard | `standard` / `seiia-ds` | `gpt-5.4` | `low` | `standard` / `seiia-ds-gpt-terra` | `gpt-5.6-terra` | `low` |
| subagentes/mini | `mini` / `seiia-ds-mini` | `gpt-5.4-mini` | observado por generation | `mini` / `seiia-ds-gpt-luna` | `gpt-5.6-luna` | observado por generation |
| OCR | `mini` / `seiia-ds-mini` | `gpt-5.4-mini` | sem override de effort | `mini` / `seiia-ds-gpt-luna` | `gpt-5.6-luna` | sem override de effort |
| judge | `mini` / `seiia-ds-mini` | `gpt-5.4-mini` | temperature 0 | `mini` / `seiia-ds-gpt-luna` | `gpt-5.6-luna` | sem temperature |
| nano/explorador | `nano` / `seiia-ds-nano` | `gpt-5.4-nano` | observado por generation | `nano` / `seiia-ds-gpt-luna` | `gpt-5.6-luna` | observado por generation |
| classificador | `mini` / `seiia-ds-mini` | `gpt-5.4-mini` | observado por generation | `mini` / `seiia-ds-gpt-luna` | `gpt-5.6-luna` | observado por generation |

## Fluxo completo

### 0. Contrato e template aprovados

Congelar braços, papéis, aliases, modelos canônicos, reasoning/effort, bateria, payloads, golds, `N`, schema, métricas, rate cards e formato append-only. Aprovar este plano e o template não autoriza chamadas.

### 1. Pre-flight e validação instrumental do cache read

O pre-flight responde apenas **“a bateria pode começar?”**. Primeiro, os checks estáticos/read-only conferem:

- aliases, modelos canônicos, papéis e reasoning/effort;
- endpoint e presença/coerência de credenciais, sem revelar valores;
- SEI e LiteLLM do ambiente correto, Langfuse e rate cards versionados;
- payloads, gold answers e hashes;
- `no_cache=True` no benchmark, isolamento de rede e stack;
- diretório privado, permissões e ledger append-only;
- capacidade e sinais de rate limit.

Esses checks não fazem inferência. O pre-flight também valida, com evidência já autorizada e persistida, que `cache_read` atravessa provider/LiteLLM, Langfuse e normalizador com provenance. Não existe operação nem custo `cache_write` no contrato deste benchmark; qualquer campo bruto homônimo eventualmente emitido é telemetria do provider e não entra em gate, agregação comparativa ou preço. O gate bloqueia somente se a instrumentação não conseguir observar e reconciliar `cache_read`.

### 2. Canário

Executar um item previamente escolhido, uma vez, com a configuração congelada. O canário prova somente que runner, endpoint, SSE, trace, artefatos, judge, ledger e métricas obrigatórias atravessam o caminho de ponta a ponta. Ele não prova representatividade estatística, não valida toda a bateria e não autoriza mudar payload, gold, `N`, papéis, schema, rate card ou metodologia.

### 3. Bateria sequencial

Executar a mesma bateria nos dois braços, `N` fixo, concorrência 1, sem warmup, sem retry automático e com artefato append-only. Cada tentativa recebe ID próprio antes do POST. Uma falha técnica é preservada como resultado da tentativa e não é convertida em julgamento de qualidade.

### 4. Judge contra gold

Aplicar o mesmo judge e o mesmo JSON Schema aos resultados tecnicamente concluídos. Validar o schema do judge. Métricas e flags contra o gold permanecem visíveis; não há gate composto/binário de qualidade.

### 5. Agregação

Os agregadores nativos leem os ledgers append-only e produzem dados alinhados por caso, configuração e papel. Mantêm separadas:

- integridade técnica da tentativa;
- qualidade contra gold;
- preparação, ferramentas e resposta;
- latência;
- tokens obrigatórios: input, output, reasoning e cache read;
- custo por componente e total, com rate card, data, versão e provenance.

### 6. Relatório HTML

Gerar uma página semântica e auditável: conclusão e limitações antes das tabelas; alocação por papel antes dos resultados; métricas correspondentes lado a lado; paths e IDs quebráveis; texto e ícones além de cor. O template bloqueia visualmente a aprovação da bateria enquanto a prova de cache read não estiver aprovada.

### 7. Decisão de repetição

Não existe retry, recovery ou reclassificação automática. Uma tentativa adicional exige decisão explícita, justificativa registrada e novo ID; a tentativa original permanece no ledger. A decisão não altera retrospectivamente qualidade, status ou métricas anteriores.

## Gates mínimos

| Gate | Critério | Efeito |
|---|---|---|
| Pre-flight | checks estáticos/read-only verdes e cache read observado/reconciliado | autoriza apenas o canário |
| Técnico por caso | HTTP 200, SSE terminal `end`, trace e artefatos persistidos | torna a tentativa elegível ao judge |
| Schema do judge | JSON válido no schema simples e invariantes semânticas preservadas | permite agregar a avaliação |

Não haverá gate composto ou binário de qualidade. Qualidade será apresentada como métricas e flags contra gold. Ausência de qualquer métrica obrigatória de tokens, inclusive cache read, bloqueia o início da bateria ou denuncia quebra instrumental durante a execução.

## Manter, mudar e remover

### Manter

Payloads, gold answers, bateria, `N` fixo, `no_cache`, tokens de input/output/reasoning/cache read, custos, ferramentas, preparação, resposta, judge contra gold, hashes e rastreabilidade.

### Mudar

Duas configurações somente; uma camada comum de configuração para os runners Session e Long Context; schemas simples por metodologia; falha técnica separada de qualidade; ledger append-only; mapeamento de modelos por configuração; contrato versionado do campo de cache read comprovado ponta a ponta.

### Remover

Gates compostos de qualidade, campanhas sucessoras como fluxo normal, classificação retroativa, recovery automático, retries automáticos e caminhos paralelos de runner/agregação.

## Critérios de aceite do desenho

1. A alocação exata de judge/OCR/nano e reasoning/effort está congelada na tabela acima.
2. Os dois braços podem ser trocados somente por argumentos/configuração.
3. A mesma configuração atende aos runners nativos Session e Long Context, sem lógica exclusiva de geração de modelo.
4. O pre-flight usa somente checks sem inferência e evidência instrumental previamente autorizada.
5. O contrato captura o `usage` bruto de cache read e o reconcilia com Langfuse e agregador.
6. Nenhuma bateria começa sem cache read observável e reconciliado.
7. O ledger é append-only; repetição exige decisão explícita e novo ID.
8. O relatório separa integridade técnica, qualidade e telemetria sem gate composto de qualidade.

## Execução autorizada

A autorização unattended cobre os canários distintos e as duas baterias Session sequenciais. Uma nova tentativa do mesmo item continua proibida sem novo ID; falhas e métricas ausentes permanecem append-only. Cache write não é operação, métrica comparativa nem componente de custo em nenhum braço.

# Bateria completa long-context v2 — 24/07/2026

## Escopo autorizado

A execução foi autorizada pelo documento de decisão SHA-256
`2984a3c55aea2f4b1134d3dcce690d32de9eaa8b473fb37304738c70be9ac3a9`.
O contrato efetivo foi `/llm_lang/session_stream`, N=1, concorrência 1,
`no_cache=true`, sessão/checkpointer resetados, origem processual/documental fresh do
SEI, evidence runtime v4, threshold 200.000, zero warmup, zero retry de inferência e
`use_websearch=false`.

O readiness sem POST confirmou stack isolada, modelos default, dataset/projeto,
preflight live SEI HTTP 200 e a partição oficial. O ledger anexou a autorização antes
do primeiro POST.

## Distinção do predecessor frozen

O synthesis histórico `case-0960k-q2-synthesis`, trace
`e6a7270a864fd886e20379b4292a8362`, preserva qualidade, 503.881 tokens e custo USD
0,37534475. Ele não integra a bateria oficial porque usou
`frozen_evidence_snapshot` como fonte e sua latência não é comparável ao cold start
fresh exigido.

A bateria oficial reutilizou somente o factual fresh já válido e fez oito POSTs
fresh, incluindo uma substituição única do synthesis. Portanto, os nove itens
oficiais são: um resultado fresh reutilizado + oito inferências fresh novas. Nenhuma
inferência válida foi repetida.

## Incidentes e recuperação sem replay

1. O primeiro synthesis fresh terminou com `end`, mas o adaptador do juiz ainda
   comparava o conteúdo fresh aberto com texto OCR congelado. A causa foi corrigida
   para usar exclusivamente arquivos fresh materializados e validados. Q2 e Q3 do
   corpus 0960k foram completados a partir dos SSEs/traces existentes, sem novo POST,
   agente ou OCR.
2. Depois de transporte, juiz e trace completos de `case-5120k-q1-factual`, um
   arquivo operacional de lock estava `0644`. O gate de retenção detectou a falha;
   ela foi corrigida para `0600` e registrada append-only como falha local de
   permissão, sem repetir inferência ou avaliação.
3. `case-5120k-q3-insufficient-evidence` terminou o agente, mas a exportação fresh
   calculou hash após normalização de CRLF e emitiu `error` 409. O hash passou a ser
   calculado sobre os bytes exatos antes do decode. O filesystem preservado provou
   331/331 documentos e a resposta/trace estavam completos; evidence, juiz e
   readback foram finalizados offline, sem replay.

Conteúdo fresh bruto só é exportado quando o runtime pinned do benchmark está ativo.
Mero header de coleta em configuração normal não libera conteúdo. SSE, traces,
respostas e evidence packages permanecem em artefatos `0600`; resultado sanitizado,
relatório Git e ledger não contêm conteúdo bruto.

## Resultados oficiais por item

| Item | Origem | Trace | Total até terminal s | Preparação s¹ | Pós-prep. s | G | C | CQ | Overall | Qualidade | Tools | Tokens | USD |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| `case-0960k-q1-factual` | fresh reutilizado | `6b861e49b3319821c1fcfbff83174d22` | 125,23 | 62,60 | 62,63 | 0,7500 | 1,00 | 1,00 | 0,90 | válida | 29 | 572.012 | 0,61587523 |
| `case-0960k-q2-synthesis` | fresh novo | `6688f70f14fb97b7bcab22f3fb03f731` | 172,53 | 69,64 | 102,90 | 1,0000 | 1,00 | 1,00 | 1,00 | válida | 40 | 735.981 | 0,50057972 |
| `case-0960k-q3-insufficient-evidence` | fresh novo | `0b74a714971f03c5ae999460eb3a393b` | 180,32 | 51,19 | 129,14 | 0,9091 | 1,00 | 0,98 | 0,98 | válida | 51 | 635.183 | 0,49564324 |
| `case-5120k-q1-factual` | fresh novo | `675da88325c4192661353dda1701555c` | 830,70 | 757,24 | 73,46 | 1,0000 | 1,00 | 1,00 | 1,00 | válida | 21 | 523.995 | 0,62149175 |
| `case-5120k-q2-synthesis` | fresh novo | `1e746810b464f8a2b33c727c1a95eba9` | 809,91 | 742,98 | 66,93 | 1,0000 | 1,00 | 1,00 | 0,96 | válida | 24 | 684.129 | 0,68166950 |
| `case-5120k-q3-insufficient-evidence` | fresh novo, pós-agente recuperado | `c2681ee15d461d5f01df705751237cde` | 961,88 | 719,70 | 242,17 | 0,4375 | 1,00 | 0,93 | 0,90 | válida | 84 | 1.679.890 | 1,68096700 |
| `case-6260k-q1-factual` | fresh novo | `aad80d9a7a2e1ca2af5b9586eb520c3d` | 77,07 | 47,97 | 29,10 | 0,8000 | 1,00 | 0,90 | 0,95 | válida | 7 | 199.294 | 0,15263650 |
| `case-6260k-q2-synthesis` | fresh novo | `b02fd25e43410fe628495a259bd2e8ac` | 108,76 | 60,80 | 47,96 | 0,8571 | 1,00 | 1,00 | 1,00 | válida | 9 | 273.612 | 0,28506300 |
| `case-6260k-q3-insufficient-evidence` | fresh novo | `4a48a2f43334e25debdad34ddbace832` | 137,49 | 47,99 | 89,50 | 0,8182 | 1,00 | 0,90 | 0,87 | válida | 27 | 493.895 | 0,41675350 |

¹ A preparação é subconjunto do total até o frame terminal, não uma parcela a ser
somada. O pós-preparação é derivado por `total até terminal − preparação`.

G = groundedness; C = completeness; CQ = citation quality. Métricas contínuas são
diagnósticas e não bloqueantes. Todos os itens tiveram resposta não vazia,
`target_alignment=true` e `hallucination=false`; os três negativos tiveram
`negativa_correta=true`. Todos os gates finais passaram, inclusive groundedness
0,4375 do negativo 5120k.

### Diagnóstico causal do tempo 5120k

O corpus 5120k materializa 331 documentos (~18,0 MB de texto), com 132 identidades
binárias fresh e 199 rotas textuais determinísticas. O 6260k materializa volume
semelhante (~18,3 MB), mas em apenas 61 documentos, dos quais 39 têm identidade
binária fresh. Assim, tokens ou bytes não explicam a diferença: o primeiro ponto de
divergência comprovado está no fan-out pré-agente por documento.

Com `no_cache=true`, cada item zera sessão/checkpointer, purga o cache documental,
rebusca metadados e conteúdo no SEI, executa download/extração/OCR quando exigido,
grava/tokeniza e valida a materialização. A concorrência efetiva é limitada a 30. Nos q1
e q2 5120k, 91–92% do total ocorreu nessa preparação; os traces do agente duraram
66,82 s e 64,31 s, próximos do pós-preparação observado. Q3 agrega uma segunda causa:
além dos 719,70 s de preparação, explorou 84 tools e 29 calls de agente, consumindo
242,17 s depois da preparação.

**Conclusão:** o trigger é a composição de 331 documentos sob materialização fresh;
a condição que mascarava o diagnóstico era chamar o tempo inclusivo até o terminal
de “stream” ao lado da preparação. O sintoma são totais de 809,91–961,88 s, mas a
divergência começa antes do agente. O contrafactual observacional 6260k percorre o
mesmo fluxo no-cache e chega ao agente em 47,97–60,80 s. A atribuição interna exata
continua limitada: faltam spans separados para consulta SEI, purge, download, OCR,
escrita/tokenização e validação. Esses spans poderiam refutar a inferência de que o
fan-out/download-OCR domina, por exemplo se mostrassem espera predominante no reset
ou na consulta processual.

O juiz teve uma tentativa aceita em oito itens. O negativo 6260k teve uma resposta
do juiz rejeitada pelo contrato e uma segunda aceita; esse retry de avaliação era
autorizado e não repetiu o agente. Cada item possui uma única avaliação oficial.

## Agregado dos nove itens

- status: `completed`;
- itens oficiais: 9/9;
- POSTs fresh: 8/8;
- reuso fresh: 1;
- calls de agente: 168;
- calls de juiz observadas: 10;
- tools: 292;
- tokens canônicos: 5.797.991;
- custo agente: USD 5,35392149;
- custo juiz: USD 0,09675795;
- custo total observado: **USD 5,45067944**;
- soma dos tempos até terminal: 3.403,90 s;
- dentro desse total, preparação fresh: 2.560,10 s;
- pós-preparação derivado: 843,80 s;
- mediana do tempo até terminal: 172,53 s;
- máximo: 961,88 s;
- groundedness médio: 0,8413;
- completeness médio: 1,0000;
- citation quality médio: 0,9678;
- overall médio: 0,9511;
- alucinações: 0;
- desalinhamentos de alvo: 0;
- negativas corretas: 3/3.

| Modelo | Calls | Tokens | USD |
|---|---:|---:|---:|
| `gpt-5.4` | 100 | 5.399.679 | 5,29020250 |
| `gpt-5.4-mini` | 19 | 101.343 | 0,09937470 |
| `gpt-5.4-nano` | 59 | 296.969 | 0,06110224 |

Usage/custo das chamadas OCR de preparação não pertencem aos traces do agente e
continuam indisponíveis; nenhum valor foi estimado.

## Auditoria e retenção

- artefato agregado protegido SHA-256:
  `e28c3e42c514dcb992b6b508719e02c0f77e123f1d2ff1d03ae7ceb107c2a20a`;
- agregado sanitizado SHA-256:
  `fcdbd3746307c31a43f498e7257d6f68f82802f30faf465ba926ed21ad1656bd`;
- ledger append-only SHA-256:
  `5ee121c9304fa77df04e2bea6f2625b13368ded6c27e11765c87fbb3bd62b8b7`;
- diretórios `0700`, arquivos `0600`, zero symlinks/violações;
- nenhuma bateria adicional, no-mistakes ou merge foi realizada.

A bateria completa autorizada terminou válida. Os artefatos históricos e todos os
predecessores permaneceram preservados; correções e recuperações foram registradas
por novos eventos, sem reescrever avaliações oficiais.

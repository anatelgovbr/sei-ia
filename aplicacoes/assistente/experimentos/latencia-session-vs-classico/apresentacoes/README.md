# Apresentações do benchmark

Esta pasta reúne os entregáveis humanos do experimento e os arquivos que permitem
reconstruí-los. Os contratos de execução continuam no diretório do experimento;
esta pasta não duplica `DESIGN.md`, `LONG_CONTEXT.md` ou `benchmark-redesign/arms.json`.

## Entregáveis

| Entregável | Fonte e reconstrução |
|---|---|
| [Comparativo Session](apresentacao-comparativo.html) | `../artifacts/presentation-data.json` · `../scripts/session-classico/build_comparison_presentation.mjs` |
| [Long Context V2](apresentacao-long-context.html) | `../artifacts/long-context-presentation-data.json` · `../scripts/long-context/build_long_context_presentation.mjs` |
| [Relatório Long Context](RELATORIO_LONG_CONTEXT_V2_BATERIA_COMPLETA_2026-07-24.md) | Relatório metodológico e operacional da bateria de nove casos |
| [Diferenças metodológicas](RELATORIO_DIFERENCAS_METODOLOGICAS_SESSION_CLASSICO_VS_LONG_CONTEXT.md) | Comparação entre as unidades experimentais |
| [Metodologia central](METODOLOGIA_CENTRAL_BENCHMARKS_ASSISTENTE_SEI_IA.md) | Regras comuns de execução, judge, custo e auditoria |

## Benchmark redesign

O pacote [benchmark-redesign](benchmark-redesign/) contém o snapshot sanitizado,
o template final, o Markdown e o HTML gerado. O gerador é
`../benchmark-redesign/build_report.py`:

```bash
uv run python experimentos/latencia-session-vs-classico/benchmark-redesign/build_report.py
uv run python experimentos/latencia-session-vs-classico/benchmark-redesign/build_report.py --check
```

`arms.json` é a fonte autoritativa dos papéis. Em Terra/Luna, o papel
`nano/explorador` resolve para `seiia-ds-gpt-luna` / `gpt-5.6-luna`. O gerador
mantém tokens observados como vieram do snapshot e sinaliza qualquer deployment
observado que não pertença à alocação declarada; ele não reatribui métricas.

Na comparação caso a caso, o HTML aplica fill verde ao vencedor de cada métrica:
menor latência, maior quality e menor custo. Empates recebem fill nos dois lados.
Valores decimais, inclusive USD, aparecem com exatamente três casas; contagens
permanecem inteiras.

## O que foi preservado

Datasets, `artifacts/` e rate cards permanecem no lugar porque são fontes ou
referências de testes. O antigo `benchmark-redesign/report-template.html` era o
template de aprovação sem resultados; ele foi renomeado para
`benchmark-redesign/approval-template.html`. O novo `report-template.html` é o
template do relatório final.

O relatório detalhado não apareceu na branch anterior porque existia fora da
worktree Git e não havia um gerador versionado para produzi-lo. Agora a entrada,
as regras e as duas saídas fazem parte do mesmo pacote revisável.

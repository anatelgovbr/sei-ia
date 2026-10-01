# Benchmark Session — GPT-5.4 versus Terra/Luna

Relatório gerado por `benchmark-redesign/build_report.py`. Os mesmos dez casos
foram executados uma vez por braço. Todos os valores decimais, inclusive USD,
usam exatamente 3 casas decimais.

## Conclusão

Terra/Luna apresentou latência total mediana de **57,095 s**, qualidade mediana de **0,980**, custo total de **US$ 1,537** e **2/10** flags de alucinação.

Leitura provisória: Terra/Luna apresenta os melhores agregados desta fotografia; a promoção deve aguardar a reconciliação do bucket observado `seiia-ds-nano` com a alocação Luna.

* Redução da latência total mediana: **36,010%**.
* Delta da qualidade mediana: **+0,050**.
* Redução do custo total: **71,660%**.

## Alocação por papel

Fonte: `benchmark-redesign/arms.json`, resolvida pela rate card.

| Papel | Session — GPT-5.4 / GPT-5.4-mini / GPT-5.4-nano | Session — Terra / Luna |
|---|---|---|
| standard | `seiia-ds` → `gpt-5.4` | `seiia-ds-gpt-terra` → `gpt-5.6-terra` |
| subagentes/mini | `seiia-ds-mini` → `gpt-5.4-mini` | `seiia-ds-gpt-luna` → `gpt-5.6-luna` |
| OCR | `seiia-ds-mini` → `gpt-5.4-mini` | `seiia-ds-gpt-luna` → `gpt-5.6-luna` |
| judge | `seiia-ds-mini` → `gpt-5.4-mini` | `seiia-ds-gpt-luna` → `gpt-5.6-luna` |
| nano/explorador | `seiia-ds-nano` → `gpt-5.4-nano` | `seiia-ds-gpt-luna` → `gpt-5.6-luna` |
| classificador | `seiia-ds-mini` → `gpt-5.4-mini` | `seiia-ds-gpt-luna` → `gpt-5.6-luna` |

## Métricas

| Métrica | Session — GPT-5.4 / GPT-5.4-mini / GPT-5.4-nano | Session — Terra / Luna |
|---|---:|---:|
| TTFC mediana | 77,695 s | 48,645 s |
| Latência total mediana | 89,230 s | 57,095 s |
| Latência total média | 185,388 s | 98,691 s |
| Quality overall mediana | 0,930 | 0,980 |
| Quality overall média | 0,771 | 0,854 |
| Groundedness mediana | 0,870 | 0,990 |
| Completeness mediana | 1,000 | 1,000 |
| Citation quality mediana | 0,880 | 0,925 |
| Alucinações | 3/10 | 2/10 |
| Custo USD total | US$ 5,423 | US$ 1,537 |

### Distribuição de latência total

| Braço | mín. | p25 | mediana | média | p75 | p90 | máx. |
|---|---:|---:|---:|---:|---:|---:|---:|
| Session — GPT-5.4 / GPT-5.4-mini / GPT-5.4-nano | 8,000 | 22,815 | 89,230 | 185,388 | 171,083 | 607,259 | 699,770 |
| Session — Terra / Luna | 4,960 | 21,918 | 57,095 | 98,691 | 167,098 | 221,105 | 325,910 |

## Tokens por deployment observado

| Deployment | Input | Cache read | Output | Reasoning | Gerações |
|---|---:|---:|---:|---:|---:|
| `seiia-ds-gpt-luna` | 25.459 | 0 | 5.643 | 4.676 | 20 |
| `seiia-ds-gpt-terra` | 505.556 | 819.200 | 6.937 | 1.186 | 36 |
| `seiia-ds-nano` | 31.442 | 38.784 | 2.990 | 0 | 20 |

> ⚠ A fonte de tokens registra `seiia-ds-nano` como deployment observado, embora esse alias não esteja na alocação declarada para este braço. A tabela de papéis continua derivada de `arms.json`; o gerador não reassocia tokens históricos. Reconcilie a execução antes de usar a atribuição por deployment como evidência de papel.

## Comparação caso a caso

O vencedor é o menor valor para latência/custo e o maior valor para quality.
Empates devem ser destacados nos dois lados no HTML.

| QID | Session — GPT-5.4 / GPT-5.4-mini / GPT-5.4-nano total | Session — Terra / Luna total | Session — GPT-5.4 / GPT-5.4-mini / GPT-5.4-nano quality | Session — Terra / Luna quality | Session — GPT-5.4 / GPT-5.4-mini / GPT-5.4-nano USD | Session — Terra / Luna USD |
|---|---:|---:|---:|---:|---:|---:|
| `WEB-FII-01` | 699,770 s | 199,160 s | 0,390 | 0,580 | US$ 2,670 | US$ 0,153 |
| `LARGE-WEB-01` | 596,980 s | 325,910 s | 0,210 | 0,250 | US$ 1,066 | US$ 0,522 |
| `LARGE-NEG-01` | 90,720 s | 70,910 s | 0,980 | 0,980 | US$ 0,127 | US$ 0,082 |
| `LARGE-OFICIOS-01` | 119,820 s | 209,460 s | 0,980 | 0,850 | US$ 0,520 | US$ 0,215 |
| `Q23` | 87,740 s | 66,030 s | 0,810 | 0,980 | US$ 0,573 | US$ 0,186 |
| `Q19` | 20,920 s | 20,190 s | 0,960 | 0,980 | US$ 0,155 | US$ 0,127 |
| `Q17` | 28,500 s | 27,100 s | 0,900 | 1,000 | US$ 0,148 | US$ 0,128 |
| `SMALL-WEB-01` | 188,170 s | 48,160 s | 0,520 | 1,000 | US$ 0,129 | US$ 0,099 |
| `SMALL-NEG-01` | 8,000 s | 4,960 s | 0,980 | 0,980 | US$ 0,020 | US$ 0,016 |
| `SMALL-CONF-01` | 13,260 s | 15,030 s | 0,980 | 0,940 | US$ 0,013 | US$ 0,009 |

## Limitações

* N=1 por caso não sustenta significância estatística.
* A bateria não isola causalmente standard, mini, OCR, judge ou nano/explorador.
* Tokens observados são preservados como fonte; o gerador não reassocia deployment histórico a papel configurado.
* BRL não é exibido porque a rate card não fixa câmbio.

## Rastreabilidade

* Run GPT: `benchmark-redesign-gpt54-full-v2-20260803-10cells`
* Run Terra/Luna: `benchmark-redesign-terra-luna-full-v2-20260803-10cells`
* Commit da execução: `4b835df396d9073ed2a4ab3b09928b281228fc71`
* Rate card: `benchmark-redesign-v2`, SHA-256 `fc23ccea7dbe447890c85779f8a962296310209a2e20f453e2727212e92219da`
* Configuração: `benchmark-redesign/arms.json`

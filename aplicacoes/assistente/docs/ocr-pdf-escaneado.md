# OCR para PDFs Escaneados


PDFs escaneados nao possuem texto nativo - sao compostos apenas por imagens dos documentos originais. 
```


O algoritmo classifica cada pagina e aplica a estrategia apropriada:

```
┌─────────────────────────────────────────────────────────────┐
│                      PDF de Entrada                         │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Analisar cada pagina:                          │
│              - Extrair texto nativo                         │
│              - Contar imagens                               │
│              - Filtrar metadados                            │
└─────────────────────────┬───────────────────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            │                           │
            ▼                           ▼
┌───────────────────────┐   ┌───────────────────────┐
│   texto < 50 chars    │   │   texto >= 50 chars   │
│   E tem imagens?      │   │   OU sem imagens      │
│                       │   │                       │
│   = ESCANEADA         │   │   = TEXTO NATIVO      │
└───────────┬───────────┘   └───────────┬───────────┘
            │                           │
            ▼                           ▼
┌───────────────────────┐   ┌───────────────────────┐
│  Renderizar PNG       │   │  Usar texto extraido  │
│  Enviar para LLM      │   │  pelo PyMuPDF         │
│  com visao (OCR)      │   │  (rapido, sem custo)  │
└───────────┬───────────┘   └───────────┬───────────┘
            │                           │
            └─────────────┬─────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│           Combinar textos na ordem das paginas              │
└─────────────────────────────────────────────────────────────┘
```

## Configuracao

As configuracoes estao em `settings_config.py`:

| Variavel | Padrao | Descricao |
|----------|--------|-----------|
| `OCR_ENABLED` | `True` | Habilita/desabilita o OCR |
| `OCR_MIN_TEXT_THRESHOLD` | `50` | Minimo de caracteres para considerar texto nativo |
| `OCR_DPI` | `150` | Resolucao para renderizar paginas como imagem |
| `OCR_MAX_CONCURRENT_PAGES` | `5` | Maximo de paginas processadas em paralelo |
| `OCR_MODEL` | `think` | Modelo Azure para OCR |

**Variaveis de ambiente :**
```bash
ASSISTENTE_OCR_ENABLED=true
ASSISTENTE_OCR_MIN_TEXT_THRESHOLD=50
ASSISTENTE_OCR_DPI=150
ASSISTENTE_OCR_MAX_CONCURRENT_PAGES=5
ASSISTENTE_OCR_MODEL=think
```



### Funcoes Principais

**`pdf_ocr_extractor.py`:**

```python
# Analisa paginas e classifica como escaneada ou texto nativo
analyze_pdf_pages(pdf_path: str) -> list[PageAnalysis]

# Verifica rapidamente se PDF tem paginas escaneadas
has_scanned_pages(pdf_path: str) -> bool

# Extrai texto usando estrategia hibrida (async)
extract_text_hybrid(pdf_path, pag_ini, pag_fim) -> str

# Wrapper sincrono para extract_text_hybrid
extract_text_hybrid_sync(pdf_path, pag_ini, pag_fim) -> str
```

**`external.py` (modificado):**

```python
def _get_text_pdf_from_file(pdf_file, pag_ini, pag_fim):
    # ...
    if settings.OCR_ENABLED:
        if has_scanned_pages(pdf_file):
            return extract_text_hybrid_sync(pdf_file, pag_ini, pag_fim)
    # fallback para extracao apenas via PyMyuPDF
```

## Uso

O OCR e acionado automaticamente quando:

1. `OCR_ENABLED=True` (padrao)
2. O PDF contem paginas com menos de 50 caracteres de texto util E imagens

Nao e necessaria nenhuma configuracao adicional no request da API.

## Performance

| Metodo | Tempo | Custo |
|--------|-------|-------|
| Texto nativo (PyMuPDF) | ~instantaneo | Gratis |
| OCR (LLM com visao) | ~20-30s por pagina | Tokens LiteLLM proxy |

**Otimizacoes:**
- Paginas escaneadas sao processadas em **paralelo** (ate 5 simultaneas)
- Semaforo limita concorrencia para evitar rate limit
- Paginas com texto nativo nao passam pelo OCR


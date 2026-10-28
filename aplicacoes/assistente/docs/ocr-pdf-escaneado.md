# OCR para PDFs com conteúdo visual

O extrator preserva o texto nativo e envia ao OCR apenas as páginas visuais sem
texto útil suficiente. Isso cobre tanto imagens raster incorporadas quanto
desenhos vetoriais.

Para classificar uma página, o extrator:

1. lê o texto nativo e conta as imagens incorporadas;
2. se o texto útil estiver abaixo do limite e não houver imagens, conta os
   desenhos vetoriais;
3. seleciona a página para OCR quando o texto for insuficiente e houver imagem
   ou desenho;
4. mantém a extração nativa quando houver texto suficiente ou quando a página
   estiver realmente vazia.

A contagem de desenhos só ocorre no caso inconclusivo. A rasterização em PNG só
ocorre depois da seleção e apenas para as páginas enviadas ao OCR.

## Configuração

Os campos, aliases de ambiente e valores padrão pertencem a
`sei_ia/configs/settings_config.py` e
`libs/sei_extraction/src/sei_extraction/config.py`. As opções são
`OCR_ENABLED`, `OCR_MIN_TEXT_THRESHOLD`, `OCR_DPI`,
`OCR_MAX_CONCURRENT_PAGES` e `OCR_MODEL`. Sem override em `OCR_MODEL`, o OCR usa o
alias público `nano`; um override explícito continua sendo enviado como informado.

## Funções principais

A implementação fica em `libs/sei_extraction/src/sei_extraction/ocr/vision.py`:

- `analyze_pdf_pages` classifica cada página e registra texto útil, imagens e
  desenhos;
- `has_scanned_pages` verifica somente o intervalo `pag_ini` a `pag_fim`;
- `extract_text_hybrid_sync` combina OCR e texto nativo na ordem das páginas.

`libs/sei_extraction/src/sei_extraction/parsers/pdf.py` decide entre a extração
nativa e a híbrida.

## Uso

O OCR é acionado quando está habilitado e o intervalo solicitado contém pelo
menos uma página com texto útil insuficiente e conteúdo raster ou vetorial.
Páginas nativas, páginas vazias e páginas fora do intervalo não são enviadas ao
OCR.

Não é necessária configuração adicional no request da API.

## Performance

| Metodo | Tempo | Custo |
|--------|-------|-------|
| Texto nativo (PyMuPDF) | ~instantaneo | Gratis |
| OCR (LLM com visao) | ~20-30s por pagina | Tokens LiteLLM proxy |

**Otimizações:**

- Páginas selecionadas são processadas em paralelo até o limite configurado.
- O limite de concorrência evita excesso de requisições.
- Páginas com texto nativo suficiente não passam pelo OCR.

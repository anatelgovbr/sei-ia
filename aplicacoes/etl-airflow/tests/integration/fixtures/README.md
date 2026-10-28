# Fixtures para Testes de Integração - Document Extraction

Este diretório contém fixtures capturados de requisições reais da API do SEI para uso em testes de integração.

## Estrutura

```
fixtures/
├── document_reader_api_responses.json  # Requisições e respostas HTTP capturadas
└── files/                               # Arquivos binários baixados (PDF, XLSX)
    ├── Despacho_Ordinatorio_8470598.pdf
    ├── Termo_8562422_Anexo_IV_TR_ErroMaterialCorrigido.pdf
    └── Planejamento_de_Demandas.xlsx
```

## Documentos de Teste

### 1. Documento HTML (ID: 9758178)
- **Tipo**: Documento interno (HTML)
- **Descrição**: Portaria de Pessoal da Anatel
- **Fluxo testado**:
  - `md_ia_consulta_documento` → metadados
  - `md_ia_consulta_conteudo_documento_async` → conteúdo HTML
  - Conversão HTML para Markdown

### 2. Documento com Anexos PDF (ID: 9664647)
- **Tipo**: Documento interno com 2 anexos PDF
- **Descrição**: Email/Correspondência com anexos
- **Fluxo testado**:
  - `md_ia_consulta_documento` → metadados
  - `md_ia_consulta_conteudo_documento_async` → XML do email + IdAnexos
  - `md_ia_download_arquivo_documento_externo` (2x) → download dos PDFs
  - Extração de texto dos PDFs
  - Consolidação: `<conteudo_principal> + <anexo_1> + <anexo_2>`

### 3. Documento XLSX (ID: 8665099)
- **Tipo**: Documento externo (planilha Excel)
- **Descrição**: Planejamento de Demandas
- **Fluxo testado**:
  - `md_ia_consulta_documento` → metadados (content_type="xlsx")
  - `md_ia_download_arquivo_documento_externo` → download do XLSX
  - Extração de texto de múltiplas sheets
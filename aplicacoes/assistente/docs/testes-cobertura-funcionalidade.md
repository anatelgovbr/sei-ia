# Cobertura de funcionalidades e testes end-to-end

Este documento detalha os testes end-to-end (E2E) do agente Session no SEI-IA Assistente, mapeia o papel de cada método de teste e apresenta o panorama consolidado de cobertura da aplicação.

## Testes end-to-end do agente Session

A suíte E2E do Session valida o endpoint `/llm_lang/session_stream`, seus modos de contexto, processamento de anexos e busca web.

### 1. `test_session_stream.py` (fluxo principal do chat)

Testa o ciclo de vida da sessão, continuidade de turnos e protocolo SSE:

- `test_cria_e_retoma_sessao_em_dois_turnos`: cria a sessão no primeiro turno e retoma o mesmo `session_key` no segundo turno, preservando a memória conversacional e os arquivos no filesystem.
- `test_semeia_historico_real_da_sessao`: valida que mensagens anteriores do SEI (passadas no payload) entram na janela de contexto do agente antes da nova pergunta.
- `test_skip_memory_ignora_turno_anterior_sem_perder_documentos`: confirma que a flag `skip_memory: true` remove o histórico conversacional da janela de inferência, mas preserva os documentos já materializados no manifesto.
- `test_preserva_agrupamento_de_multiplos_processos_e_documentos`: assegura que requisições contendo mais de um processo e múltiplos documentos tenham suas estruturas agrupadas e identificadas sem perda.

### 2. `test_session_modes.py` (estratégia de contexto do agente)

Valida a decisão arquitetural de transição entre contexto direto e exploração em disco:

- `test_injected_responde_com_contexto_injetado_sem_explorar`: quando o volume documental cabe na janela, injeta o texto diretamente nas tags de contexto e responde sem acionar chamadas de ferramentas.
- `test_filesystem_le_documento_antes_de_responder`: quando o volume excede o limite do modo injetado, ativa o modo filesystem e exige que o modelo invoque `read_file` antes de emitir a resposta.
- `test_filesystem_explorador_le_e_devolve_evidencia`: para tarefas complexas, valida a delegação da busca para um subagente explorador e a posterior consolidação da resposta pelo agente principal.

### 3. `test_session_uploads.py` (uploads de arquivos e mídias)

Testa a recepção, validação, extração e entrega de arquivos anexados:

- `test_matriz_corresponde_aos_formatos_suportados_em_producao`: confere a lista canônica de extensões aceitas pela API.
- `test_matriz_de_formatos_entrega_upload_ao_turno_do_agente`: executa a extração de cada formato suportado (PDF, DOCX, PPTX, XLSX, ODT, HTML, CSV, XML, RTF, mídias) e entrega o conteúdo textual estruturado ao turno do agente.
- `test_audio_expoe_instrucao_de_transcricao_ao_modelo`: confirma que anexos de áudio injetam instruções específicas de transcrição no prompt de sistema.
- `test_imagem_expoe_instrucao_multimodal_ao_modelo`: valida a conversão de imagens em blocos multimodais base64 na mensagem do usuário.
- `test_texto_simples_nao_recebe_instrucoes_de_midia`: assegura que prompts não recebam diretivas de mídia desnecessárias quando o upload for apenas textual.
- `test_upload_sem_texto_chega_com_estado_empty`: valida que anexos sem conteúdo extraível sejam marcados com estado `empty`, sem interromper a sessão.
- `test_upload_indisponivel_nao_aborta_a_sessao_nem_e_removido`: isola falhas transitórias de download ou extração de um anexo, permitindo que a sessão responda sobre os demais arquivos e preservando o anexo com falha para nova tentativa.
- `test_falha_de_transcricao_e_exposta_sem_abortar_sessao`: erros no backend de transcrição retornam aviso controlado ao usuário sem quebrar o streaming SSE.
- `test_tsv_e_observado_como_formato_nao_suportado`: extensões fora da allowlist são rejeitadas com erro informativo padronizado.
- `test_mistura_tipos_preserva_disponiveis_e_isola_o_nao_suportado`: em um envio com múltiplos arquivos mistos, processa os arquivos válidos e isola o formato inválido.
- `test_upload_permanece_no_checkpoint_para_o_turno_seguinte`: arquivos anexados permanecem acessíveis no diretório da sessão nos turnos seguintes.
- `test_remocao_no_sei_acontece_somente_depois_da_resposta_do_agente`: garante que a chamada de expurgo temporário no SEI ocorra somente após a conclusão bem-sucedida do stream.
- `test_falha_do_agente_mantem_upload_no_sei_para_retry`: caso o agente falhe durante o processamento, o arquivo não é descartado no SEI, permitindo reenvio.

### 4. `test_session_websearch.py` (busca web)

Testa o fluxo integrado de pesquisa na internet:

- `test_websearch_executa_tool_persiste_fontes_e_renderiza_citacoes`: executa a cadeia de busca (SearXNG e raspagem com fastCRW/byparr), persiste páginas coletadas no subdiretório `web/` da sessão, valida o gate de relevância e gera as referências e links no streaming SSE.

---

## Cobertura global da aplicação

A suíte automatizada do Assistente combina testes unitários, testes de integração e cenários end-to-end:

- **Total de testes aprovados:** 1.301 testes (1.188 unitários, 94 end-to-end e 19 testes de integração/serviço).
- **Volume de código monitorado:** 8.458 declarações (statements).
- **Taxa de cobertura consolidada:** 72,93%.

### Cobertura por subsistema

| Subsistema | Módulos principais | Cobertura | Status |
|---|---|---|---|
| **Roteamento de Sessão** | `routers/session/stream.py`, `uploads.py`, `observability.py` | 82% a 95% | Cobertura alta em streaming SSE, montagem de payloads e telemetria. |
| **Agente Session** | `agents/session_agent/agent.py`, `prompts.py`, `mode.py`, `inject.py` | 86% a 100% | Lógica de decisão, injeção de contexto e prompts totalmente cobertos. |
| **Gestão de Arquivos (FS)** | `services/session_fs/manager.py`, `types.py`, `history.py` | 85% a 90% | Ciclo de vida de pastas, manifesto, limpeza por TTL e checkpoints. |
| **Modelos e Voz (STT)** | `services/llm_models/speech_to_text.py`, `stream_citations.py` | 94% a 96% | Transcrição de áudio, formatação de citações e catálogo de modelos. |
| **Extração de Uploads** | `data/etl/extract/uploads.py` | 95,8% | Parsers de PDF, planilhas, documentos de texto e imagens. |
| **Configurações Centrais** | `configs/settings_config.py`, `logging_config.py` | 93% a 98% | Leitura de variáveis de ambiente, validação Pydantic e logging. |
| **Middlewares e Segurança** | `middleware/middleware_exception_handlers.py`, `timeout.py` | 90% a 100% | Sanitização de erros HTTP, timeout 408 e cabeçalho `id_request`. |
| **Cache e Redis** | `services/cache/topic_attachments.py`, `redis_client.py` | 40% a 75% | Cache de documentos e anexos de tópicos; conexões de rede mockadas nos testes locais. |
| **Pesquisa Web** | `agents/websearch/web_research_agent.py`, `searx_crawl_tool.py` | 75% a 94% | Planejamento de queries, raspagem de páginas e desduplicação de links. |

---

## Como rodar os testes e verificar a cobertura

A partir do diretório `aplicacoes/assistente`, execute:

1. **Executar todos os testes com relatório de cobertura:**
   ```bash
   uv run pytest -n auto tests
   ```

2. **Executar apenas os testes end-to-end:**
   ```bash
   uv run pytest -n auto tests/e2e
   ```

3. **Executar apenas os testes unitários:**
   ```bash
   uv run pytest -n auto tests/unit
   ```

4. **Gerar relatório detalhado de cobertura em HTML:**
   ```bash
   uv run pytest --cov=sei_ia --cov-report=html tests
   ```
   O relatório interativo é gerado em `htmlcov/index.html`.

"""
Testes unitários para sei_ia/agents/rag/stream_processor_final.py.

Cobre linhas não cobertas:
- _process_accumulated: retorna "" quando accumulator está vazio (linha 72)
- _process_accumulated: fallback "[N]" quando find_chunk_metadata retorna None (linha 118)
- flush(): retorna conteúdo pendente quando accumulator não está vazio (linhas 274-276)
"""

from unittest.mock import patch


def _make_user_state() -> dict:
    return {
        "id_procedimentos": [],
        "chunks_metadata": [],
        "web_search_results": [],
        "id_to_formatted_map": {},
    }


def _make_processor(user_state=None):
    from sei_ia.agents.rag.stream_processor_final import StreamTagProcessorFinal

    state = user_state or _make_user_state()

    with patch(
        "sei_ia.agents.rag.stream_processor_final.get_document_count", return_value=0
    ):
        return StreamTagProcessorFinal(state)


# ---------------------------------------------------------------------------
# Linha 72: _process_accumulated retorna "" quando accumulator vazio
# ---------------------------------------------------------------------------


def test_process_accumulated_acumulador_vazio_retorna_string_vazia():
    """_process_accumulated com accumulator='' deve retornar ''."""
    processor = _make_processor()

    # Garantir accumulator vazio
    processor.accumulator = ""
    result = processor._process_accumulated()

    assert result == ""


# ---------------------------------------------------------------------------
# Linha 118: fallback "[N]" quando find_chunk_metadata retorna None
# ---------------------------------------------------------------------------


def test_process_token_chunk_metadata_none_usa_numero_sequencial():
    """
    Quando find_chunk_metadata retorna None para uma tag <doc_ID_INDEX></doc_ID_INDEX>,
    o output deve usar "[N]" como fallback.
    """
    processor = _make_processor()

    with patch(
        "sei_ia.agents.rag.stream_processor_final.find_chunk_metadata",
        return_value=None,
    ):
        # Tag completa de chunk: <doc_1_0></doc_1_0>
        result = processor.process_token("<doc_1_0></doc_1_0>")

    assert "[1]" in result


def test_process_token_documento_sem_numero_visivel_nao_expoe_id_interno():
    """A ausência do número SEI não pode usar o ID técnico como fallback."""
    processor = _make_processor()

    result = processor.process_token("<doc_123></doc_123>")

    assert "Documento SEI (número não disponível)" in result
    assert "123" not in result


def test_process_token_upload_disponivel_exibe_apenas_nome_do_arquivo(caplog):
    """Upload disponível vira fonte cujo tooltip contém somente seu nome."""
    state = _make_user_state()
    state["upload_id_to_filename_map"] = {"2173": "solicitacao.pdf"}
    processor = _make_processor(state)

    result = processor.process_token("<upload_2173></upload_2173>")

    assert "[1]" in result
    assert 'title="solicitacao.pdf"' in result
    assert "Documento SEI" not in result
    assert "Arquivo avulso" not in result
    assert "número não disponível" not in result
    assert "Número SEI não encontrado" not in caplog.text


def test_process_token_upload_indisponivel_nao_cria_citacao_nem_consume_indice():
    """Tag de upload fora do mapa disponível é descartada sem virar fonte."""
    processor = _make_processor()

    result = processor.process_token("Antes <upload_2054></upload_2054> depois")
    result += processor.process_token("<doc_99></doc_99>")

    assert result.startswith("Antes  depois")
    assert "upload_2054" not in result
    assert "[1]" in result
    assert "[2]" not in result


def test_process_token_documento_upload_web_mantem_indices_distintos_com_mesmo_id():
    """Os namespaces doc/upload evitam colisão e preservam a ordem global."""
    state = _make_user_state()
    state.update(
        {
            "id_to_formatted_map": {"42": "16016297"},
            "upload_id_to_filename_map": {"42": "laudo.pdf"},
            "tool_web_search": [
                {
                    "idx": 1,
                    "content": "Fonte web de teste",
                    "references": [{"url": "https://example.test", "title": "Teste"}],
                }
            ],
        }
    )
    processor = _make_processor(state)

    result = processor.process_token("<doc_42></doc_42><upload_42></upload_42><web_1>")

    assert "Documento SEI nº 16016297" in result
    assert 'title="laudo.pdf"' in result
    assert "[1]" in result
    assert "[2]" in result
    assert "[3]" in result


def test_process_token_upload_fragmentado_espera_tag_completa():
    """A tag de upload pode chegar em múltiplos tokens do stream."""
    state = _make_user_state()
    state["upload_id_to_filename_map"] = {"2054": "13 Laudo 1.pdf"}
    processor = _make_processor(state)

    first = processor.process_token("<upload_2054></up")
    second = processor.process_token("load_2054>")

    assert first == ""
    assert "[1]" in second
    assert 'title="13 Laudo 1.pdf"' in second


# ---------------------------------------------------------------------------
# Linhas 274-276: flush() com conteúdo pendente
# ---------------------------------------------------------------------------


def test_flush_com_conteudo_pendente_retorna_e_limpa():
    """flush() deve retornar o conteúdo do accumulator e zerá-lo."""
    processor = _make_processor()
    processor.accumulator = "texto pendente final"

    result = processor.flush()

    assert result == "texto pendente final"
    assert processor.accumulator == ""


def test_flush_sem_conteudo_retorna_string_vazia():
    """flush() com accumulator vazio deve retornar ''."""
    processor = _make_processor()
    processor.accumulator = ""

    result = processor.flush()

    assert result == ""


def test_flush_anexa_secao_referencias_apos_marcador_web():
    """Após processar <web_1>, o flush anexa a seção 'Referências' com a URL."""
    state = _make_user_state()
    state["tool_web_search"] = [
        {
            "idx": 1,
            "content": "trecho da pagina um",
            "references": [{"url": "https://um.com", "title": "Um"}],
        }
    ]
    processor = _make_processor(state)

    out = processor.process_token("Afirmação.<web_1> fim.")
    # o hover do marcador mostra o trecho, não a URL
    assert 'title="trecho da pagina um"' in out

    section = processor.flush()
    assert "Referências:" in section
    assert "https://um.com" in section


def test_flush_sem_marcador_web_nao_anexa_secao():
    """Sem marcadores web citados, o flush não anexa seção de referências."""
    processor = _make_processor()
    processor.accumulator = "fim"

    result = processor.flush()

    assert result == "fim"
    assert "Referências" not in result

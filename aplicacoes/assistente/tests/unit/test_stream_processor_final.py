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

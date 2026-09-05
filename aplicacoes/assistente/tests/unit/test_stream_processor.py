"""Testes unitários para o módulo stream_processor.

Módulo testado: sei_ia/agents/rag/stream_processor.py
"""

from unittest.mock import patch

from sei_ia.agents.rag.stream_processor import (
    StreamTagProcessor,
    process_stream_with_tags,
)


def make_processor(rag_chunks=None, id_procedimentos=None):
    state = {
        "rag_chunks_data": rag_chunks or [],
        "id_procedimentos": id_procedimentos or [],
        "rag_documents_count": 0,
    }
    return StreamTagProcessor(state)


class TestStreamTagProcessorTokenNormal:
    """Tokens normais passam direto sem buffering."""

    def test_texto_simples_retorna_igual(self):
        p = make_processor()
        assert p.process_token("ola") == "ola"

    def test_espaco_retorna_igual(self):
        p = make_processor()
        assert p.process_token(" ") == " "

    def test_varios_tokens_normais(self):
        p = make_processor()
        resultado = "".join(p.process_token(c) for c in "abc")
        assert resultado == "abc"


class TestStreamTagProcessorTagDetection:
    """Início de tag faz o processador entrar em modo de acúmulo."""

    def test_inicio_de_tag_retorna_vazio(self):
        p = make_processor()
        assert p.process_token("<doc_") == ""

    def test_estado_inside_tag_ativo_apos_inicio(self):
        p = make_processor()
        p.process_token("<doc_")
        assert p.inside_tag is True

    def test_tag_incompleta_acumula_sem_retornar(self):
        p = make_processor()
        saida = ""
        for token in ["<", "d", "o", "c", "_", "1", "2", "3"]:
            saida += p.process_token(token)
        assert saida == ""


class TestStreamTagProcessorIsTagComplete:
    """_is_tag_complete identifica corretamente tags completas."""

    def test_tag_chunk_completa(self):
        p = make_processor()
        p.tag_buffer = "<doc_123_1></doc_123_1>"
        assert p._is_tag_complete() is True

    def test_tag_doc_completa(self):
        p = make_processor()
        p.tag_buffer = "<doc_999></doc_999>"
        assert p._is_tag_complete() is True

    def test_tag_incompleta_retorna_false(self):
        p = make_processor()
        p.tag_buffer = "<doc_123_1>"
        assert p._is_tag_complete() is False

    def test_buffer_vazio_retorna_false(self):
        p = make_processor()
        p.tag_buffer = ""
        assert p._is_tag_complete() is False

    def test_texto_sem_tag_retorna_false(self):
        p = make_processor()
        p.tag_buffer = "texto normal"
        assert p._is_tag_complete() is False


class TestStreamTagProcessorFlush:
    """flush retorna conteúdo pendente."""

    def test_flush_sem_tag_pendente_retorna_vazio(self):
        p = make_processor()
        assert p.flush() == ""

    def test_flush_com_tag_incompleta_retorna_tag(self):
        p = make_processor()
        p.inside_tag = True
        p.tag_buffer = "<doc_123"
        resultado = p.flush()
        assert resultado == "<doc_123"

    def test_flush_sem_inside_tag_retorna_vazio(self):
        p = make_processor()
        p.inside_tag = False
        p.tag_buffer = "algo"
        assert p.flush() == ""


class TestStreamTagProcessorTagNaoReconhecida:
    """Tag não reconhecida é retornada como está."""

    def test_tag_invalida_retorna_original(self):
        p = make_processor()
        p.tag_buffer = "<doc_abc_xyz>"
        p.inside_tag = True
        resultado = p._process_complete_tag()
        assert resultado == "<doc_abc_xyz>"


class TestProcessStreamWithTags:
    """Função auxiliar process_stream_with_tags."""

    def test_delega_para_processor(self):
        p = make_processor()
        assert process_stream_with_tags("oi", p) == "oi"

    def test_retorna_string(self):
        p = make_processor()
        assert isinstance(process_stream_with_tags("x", p), str)


class TestStreamTagProcessorChunkTag:
    """Processamento completo de tag de chunk via process_token."""

    def test_tag_chunk_completa_retorna_tooltip(self):
        p = make_processor()
        p.inside_tag = True
        p.tag_buffer = "<doc_1_1>"
        chunk_meta = {
            "chunk_index": "1",
            "id_documento_formatado": "001",
            "full_text": "conteúdo do chunk",
        }
        with (
            patch(
                "sei_ia.agents.rag.stream_processor.find_chunk_metadata",
                return_value=chunk_meta,
            ),
            patch(
                "sei_ia.agents.rag.stream_processor.create_chunk_tooltip",
                return_value="[1]",
            ),
        ):
            result = p.process_token("</doc_1_1>")
        assert result == "[1]"
        assert p.inside_tag is False
        assert p.tag_buffer == ""

    def test_process_complete_tag_chunk_chama_find_metadata(self):
        p = make_processor()
        p.tag_buffer = "<doc_5_2></doc_5_2>"
        meta = {"chunk_index": "2", "id_documento_formatado": "005", "full_text": ""}
        with (
            patch(
                "sei_ia.agents.rag.stream_processor.find_chunk_metadata",
                return_value=meta,
            ) as mock_find,
            patch(
                "sei_ia.agents.rag.stream_processor.create_chunk_tooltip",
                return_value="[2]",
            ),
        ):
            result = p._process_complete_tag()
        mock_find.assert_called_once_with("2", "5", p.user_state)
        assert result == "[2]"


class TestStreamTagProcessorDocTag:
    """Processamento completo de tag de documento via process_token."""

    def test_tag_doc_completa_retorna_tooltip(self):
        p = make_processor()
        p.inside_tag = True
        p.tag_buffer = "<doc_42>"
        with patch(
            "sei_ia.agents.rag.stream_processor.create_doc_tooltip",
            return_value="[ref]",
        ):
            result = p.process_token("</doc_42>")
        assert result == "[ref]"
        assert p.inside_tag is False

    def test_process_complete_tag_doc_registra_documento_unico(self):
        p = make_processor()
        p.tag_buffer = "<doc_99></doc_99>"
        with patch(
            "sei_ia.agents.rag.stream_processor.create_doc_tooltip", return_value="[1]"
        ):
            p._process_complete_tag()
        assert "99" in p.doc_index_map
        assert p.doc_index_map["99"] == 1

    def test_process_complete_tag_doc_segundo_acesso_usa_indice_existente(self):
        p = make_processor()
        p.doc_index_map = {"42": 1}
        p.unique_doc_ids = ["42"]
        p.tag_buffer = "<doc_42></doc_42>"
        with patch(
            "sei_ia.agents.rag.stream_processor.create_doc_tooltip", return_value="[1]"
        ) as mock_tooltip:
            p._process_complete_tag()
        mock_tooltip.assert_called_once_with("42", None, 1, p.doc_count)


class TestStreamTagProcessorIsTagStart:
    """Casos adicionais de _is_tag_start."""

    def test_doc_no_inicio_do_buffer_nao_detecta_como_inicio(self):
        p = make_processor()
        # <doc_ está no buffer mas não no final — condição tag_pos < len-5
        p.buffer = "<doc_1> texto normal"
        result = p._is_tag_start("x")
        assert result is False

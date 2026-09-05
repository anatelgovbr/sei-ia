"""Testes unitários para os templates de prompt de completação.

Módulo testado: sei_ia/agents/prompts/completation.py
"""

from sei_ia.agents.prompts.completation import (
    COMPLETATION_WITH_DOC,
    COMPLETATION_WITH_DOC_INSTRUCTION,
    INTERMEDIATE_COMPLETATION_WITH_DOC,
    INTERMEDIATE_COMPLETATION_WITH_DOC_FOR_FALSE_RAG,
)


class TestCompletationWithDocInstruction:
    def test_formatacao_basica(self):
        result = COMPLETATION_WITH_DOC_INSTRUCTION.format(
            instruction="Resuma o documento.",
            text="Qual é o prazo?",
            conteudo_documentos="[conteúdo]",
        )
        assert "Resuma o documento." in result
        assert "Qual é o prazo?" in result
        assert "[conteúdo]" in result

    def test_contem_marcadores_solicitacao(self):
        result = COMPLETATION_WITH_DOC_INSTRUCTION.format(
            instruction="X", text="Y", conteudo_documentos="Z"
        )
        assert "SOLICITACAO" in result
        assert "INSTRUCOES" in result

    def test_placeholders_obrigatorios(self):
        import pytest

        with pytest.raises(KeyError):
            COMPLETATION_WITH_DOC_INSTRUCTION.format(instruction="X", text="Y")


class TestCompletationWithDoc:
    def test_formatacao_basica(self):
        result = COMPLETATION_WITH_DOC.format(
            text="Resuma o processo.",
            conteudo_documentos="Conteúdo do documento aqui.",
        )
        assert "Resuma o processo." in result
        assert "Conteúdo do documento aqui." in result

    def test_contem_marcador_solicitacao(self):
        result = COMPLETATION_WITH_DOC.format(text="X", conteudo_documentos="Y")
        assert "SOLICITACAO" in result

    def test_contem_delimitadores_conteudo(self):
        result = COMPLETATION_WITH_DOC.format(text="X", conteudo_documentos="Y")
        assert "[conteúdo dos documentos]" in result

    def test_placeholder_faltando_lanca_keyerror(self):
        import pytest

        with pytest.raises(KeyError):
            COMPLETATION_WITH_DOC.format(text="X")


class TestIntermediateCompletationWithDoc:
    def test_formatacao_basica(self):
        result = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="001",
            protocolo_processo="00000.000000/0000-00",
            doc="Texto do documento.",
        )
        assert "Texto do documento." in result
        assert "001" not in result
        assert "00000.000000/0000-00" not in result

    def test_contem_delimitadores_doc(self):
        result = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="007",
            protocolo_processo="proc",
            doc="conteudo",
        )
        assert "<conteudo>" in result
        assert "</conteudo>" in result
        assert "[doc_007---]" not in result
        assert "está transcrito abaixo" not in result

    def test_placeholder_faltando_lanca_keyerror(self):
        import pytest

        with pytest.raises(KeyError):
            INTERMEDIATE_COMPLETATION_WITH_DOC.format(id_documento_formatado="1")


class TestIntermediateCompletationWithDocForFalseRag:
    def test_formatacao_basica(self):
        result = INTERMEDIATE_COMPLETATION_WITH_DOC_FOR_FALSE_RAG.format(
            id_documento_formatado="002",
            metadata_proc="Processo X",
            metadata_doc="Documento Y",
            doc="Conteúdo Z",
        )
        assert "002" in result
        assert "Processo X" in result
        assert "Conteúdo Z" in result

    def test_contem_secao_metadados(self):
        result = INTERMEDIATE_COMPLETATION_WITH_DOC_FOR_FALSE_RAG.format(
            id_documento_formatado="003",
            metadata_proc="P",
            metadata_doc="D",
            doc="C",
        )
        assert "metadados" in result

"""
Testes unitários para o delimitador de conteúdo dos documentos.

O contexto completo de procedimento/documento é montado por
context_formatters.py; este template legado deve apenas isolar conteúdo bruto
em <conteudo> quando ainda for usado por fluxos antigos.
"""

from sei_ia.agents.prompts.completation import INTERMEDIATE_COMPLETATION_WITH_DOC


class TestIntermediateCompletationWithDoc:
    """Testes do template mínimo de conteúdo."""

    def test_template_contem_placeholder_doc(self):
        assert "{doc}" in INTERMEDIATE_COMPLETATION_WITH_DOC

    def test_template_nao_contem_placeholder_protocolo_processo(self):
        assert "{protocolo_processo}" not in INTERMEDIATE_COMPLETATION_WITH_DOC

    def test_template_nao_contem_placeholder_id_documento(self):
        assert "{id_documento_formatado}" not in INTERMEDIATE_COMPLETATION_WITH_DOC

    def test_template_formata_apenas_conteudo(self):
        result = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="10000001",
            protocolo_processo="00000.000000/0000-00",
            doc="Conteúdo do documento de teste.",
        )

        assert "<conteudo>" in result
        assert "</conteudo>" in result
        assert "Conteúdo do documento de teste." in result
        assert "10000001" not in result
        assert "00000.000000/0000-00" not in result

    def test_delimitadores_antigos_nao_sao_emitidos(self):
        result = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="10000001",
            protocolo_processo="00000.000000/0000-00",
            doc="Conteúdo.",
        )

        assert "[doc_10000001---]" not in result
        assert "[\\doc_10000001---]" not in result
        assert "está transcrito abaixo" not in result
        assert "delimitado por" not in result

    def test_conteudo_do_documento_preservado_integralmente(self):
        conteudo = "DOCUMENTO DE TESTE\nCláusula 1: ...\nReferência interna: 99999999"
        result = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado="10000001",
            protocolo_processo="00000.000000/0000-00",
            doc=conteudo,
        )

        assert conteudo in result

"""Testes unitários para os prompts de identificação de disclaimer.

Módulo testado: sei_ia/agents/prompts/disclaimer_need_identifier.py
"""

from sei_ia.agents.prompts.disclaimer_need_identifier import (
    DICT_DISCLAIMER_CASES,
    PONDER_DISCLAIMER_ADDITION_PROMPT,
)

CASOS_VALIDOS = {
    "orientacao_sobre_uso_do_sei",
    "totalidade_do_sei",
    "outro",
}


class TestDictDisclaimerCases:
    def test_possui_tres_casos(self):
        assert len(DICT_DISCLAIMER_CASES) == 3

    def test_casos_esperados_presentes(self):
        assert set(DICT_DISCLAIMER_CASES.keys()) == CASOS_VALIDOS

    def test_todos_os_valores_sao_strings_nao_vazias(self):
        for caso, descricao in DICT_DISCLAIMER_CASES.items():
            assert isinstance(descricao, str), f"Caso '{caso}' não é string"
            assert len(descricao.strip()) > 0, f"Caso '{caso}' tem descrição vazia"

    def test_caso_orientacao_menciona_sei(self):
        assert "SEI" in DICT_DISCLAIMER_CASES["orientacao_sobre_uso_do_sei"]

    def test_caso_totalidade_menciona_sei(self):
        assert "SEI" in DICT_DISCLAIMER_CASES["totalidade_do_sei"]

    def test_caso_outro_e_fallback(self):
        assert "não se enquadra" in DICT_DISCLAIMER_CASES["outro"]


class TestPonderDisclaimerAdditionPrompt:
    def test_formatacao_basica(self):
        result = PONDER_DISCLAIMER_ADDITION_PROMPT.format(
            intentions="lista de intenções",
            prompt="Qual o prazo do processo?",
        )
        assert "lista de intenções" in result
        assert "Qual o prazo do processo?" in result

    def test_contem_instrucao_json(self):
        result = PONDER_DISCLAIMER_ADDITION_PROMPT.format(intentions="X", prompt="Y")
        assert "JSON" in result

    def test_contem_campo_caso(self):
        result = PONDER_DISCLAIMER_ADDITION_PROMPT.format(intentions="X", prompt="Y")
        assert '"caso"' in result

    def test_contem_campo_justificativa(self):
        result = PONDER_DISCLAIMER_ADDITION_PROMPT.format(intentions="X", prompt="Y")
        assert '"justificativa"' in result

    def test_contem_tres_opcoes_de_caso(self):
        result = PONDER_DISCLAIMER_ADDITION_PROMPT.format(intentions="X", prompt="Y")
        for caso in CASOS_VALIDOS:
            assert caso in result, f"Caso '{caso}' não está no prompt"

    def test_placeholder_faltando_lanca_keyerror(self):
        import pytest

        with pytest.raises(KeyError):
            PONDER_DISCLAIMER_ADDITION_PROMPT.format(intentions="X")

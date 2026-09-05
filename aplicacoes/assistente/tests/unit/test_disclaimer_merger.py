"""Testes unitários para disclaimer_merger.

Módulo testado: sei_ia/agents/disclaimer/disclaimer_merger.py
"""

import pytest

from sei_ia.agents.disclaimer.disclaimer_merger import prepare_disclaimer_for_response


def _state(**kwargs):
    base = {
        "disclaimer_case": None,
        "id_procedimentos": None,
    }
    base.update(kwargs)
    return base


class TestPrepareDisclaimerForResponse:
    """Testes para prepare_disclaimer_for_response."""

    @pytest.mark.asyncio
    async def test_sem_disclaimer_case_retorna_none(self):
        result = await prepare_disclaimer_for_response(_state(disclaimer_case=None))
        assert result["disclaimer_text"] is None

    @pytest.mark.asyncio
    async def test_caso_outro_retorna_none(self):
        result = await prepare_disclaimer_for_response(_state(disclaimer_case="outro"))
        assert result["disclaimer_text"] is None

    @pytest.mark.asyncio
    async def test_caso_desconhecido_retorna_none(self):
        result = await prepare_disclaimer_for_response(
            _state(disclaimer_case="fora_do_escopo_tecnologico")
        )
        assert result["disclaimer_text"] is None

    @pytest.mark.asyncio
    async def test_orientacao_sem_procedimentos_retorna_disclaimer(self):
        result = await prepare_disclaimer_for_response(
            _state(disclaimer_case="orientacao_sobre_uso_do_sei", id_procedimentos=[])
        )
        assert result["disclaimer_text"] is not None
        assert "não ensina o uso do SEI" in result["disclaimer_text"]

    @pytest.mark.asyncio
    async def test_orientacao_com_procedimentos_retorna_none(self):
        proc_mock = object()
        result = await prepare_disclaimer_for_response(
            _state(
                disclaimer_case="orientacao_sobre_uso_do_sei",
                id_procedimentos=[proc_mock],
            )
        )
        assert result["disclaimer_text"] is None

    @pytest.mark.asyncio
    async def test_totalidade_sei_sem_procedimentos_retorna_disclaimer(self):
        result = await prepare_disclaimer_for_response(
            _state(disclaimer_case="totalidade_do_sei", id_procedimentos=[])
        )
        assert result["disclaimer_text"] is not None
        assert "SEI como um todo" in result["disclaimer_text"]

    @pytest.mark.asyncio
    async def test_totalidade_sei_com_procedimentos_retorna_none(self):
        proc_mock = object()
        result = await prepare_disclaimer_for_response(
            _state(
                disclaimer_case="totalidade_do_sei",
                id_procedimentos=[proc_mock],
            )
        )
        assert result["disclaimer_text"] is None

    @pytest.mark.asyncio
    async def test_retorno_e_dict_com_disclaimer_text(self):
        result = await prepare_disclaimer_for_response(
            _state(disclaimer_case="orientacao_sobre_uso_do_sei", id_procedimentos=[])
        )
        assert isinstance(result, dict)
        assert "disclaimer_text" in result

    @pytest.mark.asyncio
    async def test_id_procedimentos_none_tratado_como_sem_procs(self):
        result = await prepare_disclaimer_for_response(
            _state(disclaimer_case="orientacao_sobre_uso_do_sei", id_procedimentos=None)
        )
        assert result["disclaimer_text"] is not None

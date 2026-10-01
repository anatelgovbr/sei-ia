"""Classificador de complexidade (mini). Mocka o modelo; testa parsing+fallback."""

import pytest

from sei_ia.agents.session_agent import classifier


class _FakeMsg:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    async def ainvoke(self, _prompt):
        return _FakeMsg(self._content)


@pytest.mark.asyncio
@pytest.mark.parametrize("nivel", ["easy", "medium", "high"])
async def test_classifica_nivel_valido(monkeypatch, nivel):
    monkeypatch.setattr(
        classifier, "get_model", lambda *a, **k: _FakeLLM(f'{{"nivel": "{nivel}"}}')
    )
    assert await classifier.classify_complexity("pergunta") == nivel


@pytest.mark.asyncio
async def test_classificador_deixa_temperatura_no_default_do_modelo(monkeypatch):
    captured: dict = {}

    def fake_get_model(*args, **kwargs):
        captured.update(kwargs)
        return _FakeLLM('{"nivel": "medium"}')

    monkeypatch.setattr(classifier, "get_model", fake_get_model)

    assert await classifier.classify_complexity("pergunta") == "medium"
    assert "temperature" not in captured


@pytest.mark.asyncio
async def test_fallback_em_json_invalido(monkeypatch):
    monkeypatch.setattr(classifier, "get_model", lambda *a, **k: _FakeLLM("nao-json"))
    assert await classifier.classify_complexity("x") == "medium"


@pytest.mark.asyncio
async def test_fallback_em_nivel_desconhecido(monkeypatch):
    monkeypatch.setattr(
        classifier, "get_model", lambda *a, **k: _FakeLLM('{"nivel": "trivial"}')
    )
    assert await classifier.classify_complexity("x") == "medium"


@pytest.mark.asyncio
async def test_fallback_em_excecao(monkeypatch):
    class _Boom:
        async def ainvoke(self, _prompt):
            raise RuntimeError("proxy down")

    monkeypatch.setattr(classifier, "get_model", lambda *a, **k: _Boom())
    assert await classifier.classify_complexity("x") == "medium"

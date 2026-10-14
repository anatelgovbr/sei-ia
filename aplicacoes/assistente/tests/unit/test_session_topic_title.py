"""Título do tópico (mini). Mocka o modelo; testa prompt, normalização e falhas."""

import pytest

from sei_ia.agents.session_agent import topic_title


class _FakeMsg:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content
        self.prompts: list[str] = []
        self.configs: list[dict | None] = []

    async def ainvoke(self, prompt, config=None):
        self.prompts.append(prompt)
        self.configs.append(config)
        return _FakeMsg(self._content)


@pytest.mark.asyncio
async def test_gera_titulo_a_partir_da_pergunta(monkeypatch):
    llm = _FakeLLM('{"titulo": "Resumo do processo 53500.000123/2024-01"}')
    captured: dict = {}

    def fake_get_model(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return llm

    monkeypatch.setattr(topic_title, "get_model", fake_get_model)

    title = await topic_title.generate_topic_title(
        "resuma o processo 53500.000123/2024-01", callbacks=["cb"]
    )

    assert title == "Resumo do processo 53500.000123/2024-01"
    assert captured["args"] == (topic_title.settings.SESSION_CLASSIFIER_MODEL,)
    assert captured["kwargs"] == {"response_format": {"type": "json_object"}}
    assert "resuma o processo 53500.000123/2024-01" in llm.prompts[0]
    assert llm.configs == [{"callbacks": ["cb"]}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"  \\"Prazo  de\\nrecurso\\".  "', "Prazo de recurso"),
        ('"**Análise do ofício**"', "Análise do ofício"),
        ('"“Minuta de despacho”:"', "Minuta de despacho"),
    ],
)
async def test_normaliza_titulo(monkeypatch, raw, expected):
    monkeypatch.setattr(
        topic_title, "get_model", lambda *a, **k: _FakeLLM(f'{{"titulo": {raw}}}')
    )
    assert await topic_title.generate_topic_title("x") == expected


@pytest.mark.asyncio
async def test_trunca_titulo_longo_em_limite_de_palavra(monkeypatch):
    longo = " ".join(["palavra"] * 30)
    monkeypatch.setattr(
        topic_title, "get_model", lambda *a, **k: _FakeLLM(f'{{"titulo": "{longo}"}}')
    )

    title = await topic_title.generate_topic_title("x")

    assert title is not None
    assert len(title) <= topic_title.MAX_CHARS
    assert title.endswith("palavra…")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    ["nao-json", '{"titulo": ""}', '{"titulo": "  \\"\\" "}', '{"titulo": 42}', "{}"],
)
async def test_none_em_resposta_invalida(monkeypatch, content):
    monkeypatch.setattr(topic_title, "get_model", lambda *a, **k: _FakeLLM(content))
    assert await topic_title.generate_topic_title("x") is None


@pytest.mark.asyncio
async def test_none_em_excecao(monkeypatch):
    class _Boom:
        async def ainvoke(self, _prompt):
            raise RuntimeError("proxy down")

    monkeypatch.setattr(topic_title, "get_model", lambda *a, **k: _Boom())
    assert await topic_title.generate_topic_title("x") is None

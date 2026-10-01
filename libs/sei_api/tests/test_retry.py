from __future__ import annotations

import json

import pytest
import sei_api._base as base_mod
from requests.exceptions import HTTPError, Timeout
from sei_api import SeiApiClient, SeiApiConfig, SeiApiError, SeiApiTimeoutError

MAX = 3


@pytest.fixture
def client() -> SeiApiClient:
    return SeiApiClient(
        SeiApiConfig(
            base_url="http://sei.test",
            sigla_sistema="X",
            identificacao_servico="tok",
            max_retries=MAX,
            backoff_initial_wait=0,
            retry_backoff_factor=1,
        )
    )


class FakeResponse:
    """Mímica de requests.Response: status real e raise_for_status fiel."""

    def __init__(self, status_code: int = 200, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text
        self.encoding = "utf-8"
        self.url = "http://sei.test"
        self.content = (
            text.encode("utf-8") if text else json.dumps(self._json).encode("utf-8")
        )

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(f"{self.status_code} Error", response=self)

    def json(self):
        if isinstance(self._json, Exception):
            raise self._json
        return self._json


def _count_get(monkeypatch, side_effect):
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        result = side_effect(calls["n"])
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(base_mod.requests, "request", fake_get)
    return calls


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_retry_ate_max(monkeypatch, client, status):
    calls = _count_get(monkeypatch, lambda n: FakeResponse(status))
    with pytest.raises(SeiApiError) as exc:
        client._request_json("ep")
    assert calls["n"] == MAX
    assert exc.value.status_code == status


def test_5xx_depois_sucesso(monkeypatch, client):
    calls = _count_get(
        monkeypatch,
        lambda n: FakeResponse(500) if n == 1 else FakeResponse(200, {"data": []}),
    )
    assert client._request_json("ep") == {"data": []}
    assert calls["n"] == 2


@pytest.mark.parametrize("status", [400, 401, 404])
def test_4xx_nao_retentado(monkeypatch, client, status):
    calls = _count_get(monkeypatch, lambda n: FakeResponse(status))
    with pytest.raises(SeiApiError) as exc:
        client._request_json("ep")
    assert calls["n"] == 1
    assert exc.value.status_code == status


def test_404_como_vazio_quando_declarado(monkeypatch, client):
    calls = _count_get(monkeypatch, lambda n: FakeResponse(404))
    assert client._request_json("ep", empty_statuses=(404,)) == {"data": []}
    assert calls["n"] == 1


def test_timeout_retry_ate_max_e_levanta_timeout_default(monkeypatch, client):
    calls = _count_get(monkeypatch, lambda n: Timeout("slow"))
    with pytest.raises(SeiApiTimeoutError):
        client._request_json("ep", document_id_hint="42")
    assert calls["n"] == MAX


def test_timeout_exc_factory_injetado(monkeypatch):
    class AppTimeout(Exception):
        pass

    c = SeiApiClient(
        SeiApiConfig(
            base_url="http://sei.test",
            sigla_sistema="X",
            identificacao_servico="tok",
            max_retries=MAX,
            backoff_initial_wait=0,
            retry_backoff_factor=1,
        ),
        timeout_exc_factory=lambda doc_id: AppTimeout(doc_id),
    )
    _count_get(monkeypatch, lambda n: Timeout("slow"))
    with pytest.raises(AppTimeout):
        c._request_json("ep")


def test_json_invalido_consumes_o_mesmo_budget_do_transporte(monkeypatch, client):
    calls = _count_get(monkeypatch, lambda n: FakeResponse(200, text="nao-json"))

    with pytest.raises(SeiApiError) as exc:
        client._request_json("ep")

    assert calls["n"] == MAX
    assert exc.value.status_code == 502


def test_token_sanitizado_no_erro(monkeypatch, client):
    err = HTTPError("boom ?IdentificacaoServico=SUPERSECRET&x=1")
    err.response = None
    _count_get(monkeypatch, lambda n: err)
    with pytest.raises(SeiApiError) as exc:
        client._request_json("ep")
    assert "SUPERSECRET" not in exc.value.detail
    assert "<anonimizado>" in exc.value.detail


# Os endpoints binários (download/remoção) passam por _run_with_retry como o
# _request_raw, então herdam a mesma política de retry de 5xx/Timeout.
_DOWNLOAD_CALLS = [
    ("md_ia_download_arquivo_documento_externo", ("1", "pdf")),
    ("md_ia_download_arquivo_avulso", (1, "pdf")),
    ("md_ia_remove_arquivos_avulsos", ([1],)),
]


@pytest.mark.parametrize(("method_name", "args"), _DOWNLOAD_CALLS)
def test_download_5xx_retentado_ate_max(monkeypatch, client, method_name, args):
    calls = _count_get(monkeypatch, lambda n: FakeResponse(503))
    with pytest.raises(SeiApiError) as exc:
        getattr(client, method_name)(*args)
    assert calls["n"] == MAX
    assert exc.value.status_code == 503


@pytest.mark.parametrize(("method_name", "args"), _DOWNLOAD_CALLS)
def test_download_timeout_vira_412(monkeypatch, client, method_name, args):
    calls = _count_get(monkeypatch, lambda n: Timeout("slow"))
    with pytest.raises(SeiApiTimeoutError):
        getattr(client, method_name)(*args)
    assert calls["n"] == MAX


@pytest.mark.parametrize(("method_name", "args"), _DOWNLOAD_CALLS)
def test_download_4xx_nao_retentado(monkeypatch, client, method_name, args):
    calls = _count_get(monkeypatch, lambda n: FakeResponse(404))
    with pytest.raises(SeiApiError) as exc:
        getattr(client, method_name)(*args)
    assert calls["n"] == 1
    assert exc.value.status_code == 404

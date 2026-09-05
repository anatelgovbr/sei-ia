from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from sei_api import SeiApiClient, SeiApiConfig, SeiApiError

CFG = SeiApiConfig(
    base_url="http://sei.test",
    sigla_sistema="X",
    identificacao_servico="tok",
    max_retries=3,
    backoff_initial_wait=0,
    retry_backoff_factor=1,
)

_DUMMY_REQUEST = httpx.Request("GET", "http://sei.test/ep")


def _resp(
    status: int, body: dict | None = None, text: str | None = None
) -> httpx.Response:
    raw = text if text is not None else (json.dumps(body) if body is not None else "")
    return httpx.Response(status_code=status, text=raw, request=_DUMMY_REQUEST)


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    r = _resp(status)
    return httpx.HTTPStatusError(f"HTTP {status}", request=_DUMMY_REQUEST, response=r)


def _patch_do_get(side_effects: list):
    """Patch ``_do_get_async`` to yield items from ``side_effects`` in order.

    Items are either ``httpx.Response`` instances (returned as-is) or exception
    instances (raised), mirroring what the real ``_do_get_async`` would produce.
    """
    call_count = {"n": 0}

    async def fake(self, url, params):
        n = call_count["n"]
        call_count["n"] += 1
        result = side_effects[min(n, len(side_effects) - 1)]
        if isinstance(result, BaseException):
            raise result
        return result

    ctx = patch("sei_api._async.AsyncMixin._do_get_async", fake)
    return ctx, call_count


# ------------------------------------------------------------------
# md_ia_consulta_documento_async
# ------------------------------------------------------------------


async def test_documento_async_sucesso_200():
    body = {
        "data": [
            {
                "IdProcedimento": "1",
                "NumeroDocumento": "DOC-001",
                "EspecificacaoDocumento": "Ofício",
                "IdTipoDocumento": "5",
                "NomeArquivo": "doc.pdf",
                "DataInclusao": "01/01/2024",
                "NomeTipoDocumento": "Ofício",
                "IdDocumento": "42",
                "StaTipoDocumento": "E",
                "NumeroProcesso": "PROC-001",
                "SinArmazenarCache": "S",
            }
        ]
    }
    ctx, _ = _patch_do_get([_resp(200, body)])
    with ctx:
        df = await SeiApiClient(CFG).md_ia_consulta_documento_async("42")
    assert len(df) == 1
    assert df.iloc[0]["num_doc"] == "DOC-001"


async def test_documento_async_retenta_5xx_ate_max_e_levanta():
    ctx, calls = _patch_do_get([_http_status_error(500)] * 3)
    with ctx:
        with pytest.raises(SeiApiError) as exc_info:
            await SeiApiClient(CFG).md_ia_consulta_documento_async("99")
    assert calls["n"] == 3
    assert exc_info.value.status_code == 500


async def test_documento_async_retenta_5xx_e_sucede():
    ctx, calls = _patch_do_get([_http_status_error(500), _resp(200, {"data": []})])
    with ctx:
        df = await SeiApiClient(CFG).md_ia_consulta_documento_async("99")
    assert calls["n"] == 2
    assert df.empty


# ------------------------------------------------------------------
# md_ia_consulta_conteudo_documento_async — 404 path
# ------------------------------------------------------------------


async def test_conteudo_async_404_retorna_none():
    ctx, _ = _patch_do_get([_resp(404, text="not found")])
    with ctx:
        result = await SeiApiClient(CFG).md_ia_consulta_conteudo_documento_async("77")
    assert result["id_documento"] == "77"
    assert result["content_doc"] is None


# ------------------------------------------------------------------
# md_ia_consulta_conteudo_documento_async — IdAnexos with extractor
# ------------------------------------------------------------------


async def test_conteudo_async_anexos_com_extractor(tmp_path):
    xml_body = (
        "<root><atributo nome='Anexos'><valores>"
        "<valor id='10'>relatorio.pdf</valor>"
        "</valores></atributo></root>"
    )
    body = {
        "data": {
            "ConteudoDocumento": xml_body,
            "IdAnexos": [10],
            "TipoConteudo": "email",
            "Assunto": "Teste",
        }
    }

    fake_file = tmp_path / "fake.pdf"
    fake_file.write_bytes(b"%PDF fake")

    def extractor(path, ext):
        return "TEXTO DO ANEXO"

    ctx, _ = _patch_do_get([_resp(200, body)])
    with ctx:
        client = SeiApiClient(CFG, content_extractor=extractor)
        client.md_ia_download_arquivo_documento_externo = MagicMock(
            return_value=str(fake_file)
        )
        result = await client.md_ia_consulta_conteudo_documento_async("55")

    assert result["content_doc"] is not None
    assert "TEXTO DO ANEXO" in result["content_doc"]
    assert "relatorio.pdf" in result["content_doc"]


# ------------------------------------------------------------------
# md_ia_consulta_conteudo_documento_async — IdAnexos sem extractor levanta
# ------------------------------------------------------------------


async def test_conteudo_async_anexos_sem_extractor_levanta():
    body = {
        "data": {
            "ConteudoDocumento": "<root/>",
            "IdAnexos": [10],
            "TipoConteudo": "email",
        }
    }
    ctx, _ = _patch_do_get([_resp(200, body)])
    with ctx:
        with pytest.raises(SeiApiError) as exc_info:
            await SeiApiClient(CFG).md_ia_consulta_conteudo_documento_async("55")
    assert exc_info.value.status_code == 500
    assert "content_extractor" in exc_info.value.detail


# ------------------------------------------------------------------
# _request_json_async — corpo em Latin-1 e JSON inválido
# ------------------------------------------------------------------


async def test_request_json_async_corpo_latin1_decodifica_e_retorna():
    body = {"data": [{"EspecificacaoDocumento": "instaurações"}]}
    raw = json.dumps(body, ensure_ascii=False).encode("latin-1")
    resp = httpx.Response(status_code=200, content=raw, request=_DUMMY_REQUEST)
    ctx, _ = _patch_do_get([resp])
    with ctx:
        payload = await SeiApiClient(CFG)._request_json_async("ep")
    assert payload == body


async def test_request_json_async_json_invalido_levanta_502():
    resp = httpx.Response(
        status_code=200, content=b"nao e json", request=_DUMMY_REQUEST
    )
    ctx, _ = _patch_do_get([resp])
    with ctx:
        with pytest.raises(SeiApiError) as exc_info:
            await SeiApiClient(CFG)._request_json_async("ep")
    assert exc_info.value.status_code == 502


async def test_request_json_async_json_invalido_consumes_o_mesmo_budget():
    responses = [
        httpx.Response(status_code=200, content=b"nao e json", request=_DUMMY_REQUEST)
        for _ in range(CFG.max_retries)
    ]
    ctx, calls = _patch_do_get(responses)
    with ctx:
        with pytest.raises(SeiApiError) as exc_info:
            await SeiApiClient(CFG)._request_json_async("ep")

    assert calls["n"] == CFG.max_retries
    assert exc_info.value.status_code == 502


async def test_request_json_async_retenta_json_invalido_e_aceita_resposta_valida():
    valid = {"data": [{"IdProcedimento": "1"}]}
    ctx, calls = _patch_do_get(
        [
            httpx.Response(
                status_code=200,
                content=b"temporariamente nao e json",
                request=_DUMMY_REQUEST,
            ),
            _resp(200, valid),
        ]
    )
    with ctx:
        payload = await SeiApiClient(CFG)._request_json_async("ep")

    assert payload == valid
    assert calls["n"] == 2


async def test_request_json_async_latin1_invalido_ainda_levanta_502():
    resp = httpx.Response(
        status_code=200, content=b"\xf5 nao e json", request=_DUMMY_REQUEST
    )
    ctx, _ = _patch_do_get([resp])
    with ctx:
        with pytest.raises(SeiApiError) as exc_info:
            await SeiApiClient(CFG)._request_json_async("ep")
    assert exc_info.value.status_code == 502


async def test_conteudo_async_corpo_latin1_decodifica_e_retorna():
    body = {
        "data": {
            "ConteudoDocumento": "Ofício de instaurações",
            "TipoConteudo": "html",
        }
    }
    raw = json.dumps(body, ensure_ascii=False).encode("latin-1")
    resp = httpx.Response(status_code=200, content=raw, request=_DUMMY_REQUEST)
    ctx, _ = _patch_do_get([resp])
    with ctx:
        result = await SeiApiClient(CFG).md_ia_consulta_conteudo_documento_async("77")
    assert result["content_doc"] == "Ofício de instaurações"


# ------------------------------------------------------------------
# _mutations async — corpo em Latin-1 (httpx estourava UnicodeDecodeError)
# ------------------------------------------------------------------


def _mock_async_delete(monkeypatch, response: httpx.Response):
    import sei_api._mutations as mutations_mod

    class _FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def delete(self, _url, params=None, headers=None):  # noqa: ARG002
            return response

    monkeypatch.setattr(mutations_mod.httpx, "AsyncClient", _FakeAsyncClient)


async def test_remove_documentos_cancelados_latin1_retorna_true(monkeypatch):
    raw = json.dumps(
        {"status": "success", "Mensagem": "instaurações"}, ensure_ascii=False
    ).encode("latin-1")
    resp = httpx.Response(status_code=200, content=raw, request=_DUMMY_REQUEST)
    _mock_async_delete(monkeypatch, resp)
    client = SeiApiClient(CFG)
    assert await client.md_ia_remove_documentos_indexaveis_cancelados_async(1) is True


async def test_remove_processos_cancelados_latin1_retorna_true(monkeypatch):
    raw = json.dumps(
        {"status": "success", "Mensagem": "instaurações"}, ensure_ascii=False
    ).encode("latin-1")
    resp = httpx.Response(status_code=200, content=raw, request=_DUMMY_REQUEST)
    _mock_async_delete(monkeypatch, resp)
    client = SeiApiClient(CFG)
    assert await client.md_ia_remove_processos_indexaveis_cancelados_async(1) is True


async def test_conteudo_async_json_invalido_levanta_502():
    resp = httpx.Response(
        status_code=200, content=b"nao e json", request=_DUMMY_REQUEST
    )
    ctx, _ = _patch_do_get([resp])
    with ctx:
        with pytest.raises(SeiApiError) as exc_info:
            await SeiApiClient(CFG).md_ia_consulta_conteudo_documento_async("77")
    assert exc_info.value.status_code == 502

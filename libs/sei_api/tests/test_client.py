from __future__ import annotations

import json

import pytest
import requests

import sei_api._base as base_mod
from sei_api import SeiApiClient, SeiApiConfig, SeiApiError
from tests.test_retry import FakeResponse

CFG = SeiApiConfig(
    base_url="http://sei.test",
    sigla_sistema="X",
    identificacao_servico="tok",
    max_retries=3,
    backoff_initial_wait=0,
    retry_backoff_factor=1,
)


def _ok(monkeypatch, payload):
    monkeypatch.setattr(
        base_mod.requests, "request", lambda *a, **k: FakeResponse(200, payload)
    )


def test_build_url_e_params():
    c = SeiApiClient(CFG)
    assert c._build_api_url("ep") == "http://sei.test/ep"
    p = c._build_params("ep", {"id": 7})
    assert p == {
        "servico": "ep",
        "SiglaSistema": "X",
        "IdentificacaoServico": "tok",
        "id": 7,
    }


def test_lista_tipo_documento_parse(monkeypatch):
    _ok(monkeypatch, {"data": [{"TipoDocumento": "Ofício", "IdTipoDocumento": "12"}]})
    df = SeiApiClient(CFG).md_ia_lista_tipo_documento()
    assert list(df.columns) == ["nome", "id_serie"]
    assert df.iloc[0]["nome"] == "Ofício"
    assert df.iloc[0]["id_serie"] == 12


def test_lista_tipo_documento_vazio(monkeypatch):
    _ok(monkeypatch, {"data": []})
    df = SeiApiClient(CFG).md_ia_lista_tipo_documento()
    assert df.empty
    assert list(df.columns) == ["nome", "id_serie"]


# ------------------------------------------------------------------
# _request_json — corpo em Latin-1 e JSON inválido
# ------------------------------------------------------------------


def _real_response(raw: bytes, status: int = 200):
    r = requests.Response()
    r.status_code = status
    r._content = raw
    r.url = "http://sei.test/ep"
    return r


def test_request_json_corpo_latin1_decodifica_e_retorna(monkeypatch):
    body = {"data": [{"EspecificacaoDocumento": "instaurações"}]}
    raw = json.dumps(body, ensure_ascii=False).encode("latin-1")
    monkeypatch.setattr(
        base_mod.requests, "request", lambda *a, **k: _real_response(raw)
    )
    assert SeiApiClient(CFG)._request_json("ep") == body


def test_request_json_json_invalido_levanta_502(monkeypatch):
    monkeypatch.setattr(
        base_mod.requests,
        "request",
        lambda *a, **k: _real_response(b"\xf5 nao e json"),
    )
    with pytest.raises(SeiApiError) as exc_info:
        SeiApiClient(CFG)._request_json("ep")
    assert exc_info.value.status_code == 502


def test_request_json_retenta_json_invalido_e_aceita_resposta_valida(monkeypatch):
    responses = iter(
        [
            _real_response(b"temporariamente nao e json"),
            _real_response(b'{"data": [{"IdProcedimento": "1"}]}'),
        ]
    )
    monkeypatch.setattr(base_mod.requests, "request", lambda *a, **k: next(responses))
    config = SeiApiConfig(
        base_url="http://sei.test",
        sigla_sistema="X",
        identificacao_servico="tok",
        max_retries=2,
        backoff_initial_wait=0,
        retry_backoff_factor=1,
    )

    assert SeiApiClient(config)._request_json("ep") == {
        "data": [{"IdProcedimento": "1"}]
    }


# ------------------------------------------------------------------
# _listings / _mutations / _files — corpos em Latin-1 e JSON inválido
# ------------------------------------------------------------------


def _latin1(body: dict) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("latin-1")


def _mock_request(monkeypatch, raw: bytes, status: int = 200):
    monkeypatch.setattr(
        base_mod.requests, "request", lambda *a, **k: _real_response(raw, status)
    )


def test_segmentos_relevantes_latin1_preserva_acentos(monkeypatch):
    body = {
        "data": [
            {
                "IdDocumentoRelevante": "1",
                "SegmentoDocumento": "Petição",
                "IdTipoDocumentoRelevante": "2",
                "PercentualRelevancia": "80",
            }
        ]
    }
    _mock_request(monkeypatch, _latin1(body))
    df = SeiApiClient(CFG).md_ia_lista_segmentos_documentos_relevantes()
    assert df.iloc[0]["segmento"] == "Petição"


def test_percentual_relevancia_metadados_latin1_mapeia_metadado(monkeypatch):
    body = {"data": [{"Metadado": "Especificação do Processo", "Relevancia": "30"}]}
    _mock_request(monkeypatch, _latin1(body))
    df = SeiApiClient(CFG).md_ia_lista_percentual_relevancia_metadados()
    assert df.iloc[0]["metadado"] == "metadata_process_specification"


_LISTAGENS_IDS = [
    ("md_ia_lista_processos_indexaveis", {"IdProcedimentos": [1, 2]}, [1, 2], []),
    (
        "md_ia_lista_processos_indexaveis_cancelados",
        {"IdProcedimentos": [3], "IdUltimoRegistroEntregue": 9},
        ([3], 9),
        ([], 0),
    ),
    ("md_ia_lista_documentos_indexaveis", {"IdDocumentos": [4]}, [4], []),
    (
        "md_ia_lista_documentos_indexaveis_cancelados",
        {"IdDocumentos": [5], "IdUltimoRegistroEntregue": 7},
        ([5], 7),
        ([], 0),
    ),
    ("md_ia_lista_documentos_vetorizaveis", {"IdDocumentos": [6]}, [6], []),
]


@pytest.mark.parametrize(
    ("method", "data", "expected", "_vazio"),
    _LISTAGENS_IDS,
    ids=[m for m, *_ in _LISTAGENS_IDS],
)
def test_listagens_ids_corpo_latin1_parseia(
    monkeypatch, method, data, expected, _vazio
):
    body = {"data": {**data, "Mensagem": "instaurações"}}
    _mock_request(monkeypatch, _latin1(body))
    assert getattr(SeiApiClient(CFG), method)() == expected


@pytest.mark.parametrize(
    ("method", "_data", "_expected", "vazio"),
    _LISTAGENS_IDS,
    ids=[m for m, *_ in _LISTAGENS_IDS],
)
def test_listagens_ids_json_invalido_retorna_vazio(
    monkeypatch, method, _data, _expected, vazio
):
    _mock_request(monkeypatch, b"\xf5 nao e json")
    assert getattr(SeiApiClient(CFG), method)() == vazio


def test_documentos_elegiveis_similares_latin1_parseia(monkeypatch):
    import sei_api._listings as listings_mod

    raw = _latin1({"data": [10, 11], "Mensagem": "instaurações"})
    monkeypatch.setattr(
        listings_mod.requests, "get", lambda *a, **k: _real_response(raw)
    )
    client = SeiApiClient(CFG)
    assert client.md_ia_lista_documentos_elegiveis_processos_similares("1") == [10, 11]


def test_documentos_elegiveis_similares_json_invalido_retorna_vazio(monkeypatch):
    import sei_api._listings as listings_mod

    monkeypatch.setattr(
        listings_mod.requests,
        "get",
        lambda *a, **k: _real_response(b"\xf5 nao e json"),
    )
    client = SeiApiClient(CFG)
    assert client.md_ia_lista_documentos_elegiveis_processos_similares("1") == []


def test_atualiza_processos_indexaveis_latin1_retorna_true(monkeypatch):
    import sei_api._mutations as mutations_mod

    raw = _latin1({"status": "success", "Mensagem": "instaurações"})
    monkeypatch.setattr(
        mutations_mod.requests, "put", lambda *a, **k: _real_response(raw)
    )
    assert SeiApiClient(CFG).md_ia_atualiza_processos_indexaveis(1) is True


def test_remove_arquivos_avulsos_latin1_retorna_payload(monkeypatch):
    body = {"status": "success", "data": [{"Mensagem": "instaurações"}]}
    _mock_request(monkeypatch, _latin1(body))
    assert SeiApiClient(CFG).md_ia_remove_arquivos_avulsos([1]) == body


def test_remove_arquivos_avulsos_json_invalido_retorna_default(monkeypatch):
    _mock_request(monkeypatch, b"\xf5 nao e json")
    result = SeiApiClient(CFG).md_ia_remove_arquivos_avulsos([1])
    assert result == {"status": "success", "data": []}


# ------------------------------------------------------------------
# _decode_json_body — cascata UTF-8 (BOM) → cp1252 → Latin-1
# ------------------------------------------------------------------


def test_decode_json_body_utf8_com_bom_parseia():
    from sei_api._base import _decode_json_body

    assert _decode_json_body(b'\xef\xbb\xbf{"a": 1}') == {"a": 1}


def test_decode_json_body_cp1252_aspas_curvas_viram_unicode():
    from sei_api._base import _decode_json_body

    raw = '{"t": "“texto”"}'.encode("cp1252")
    assert raw == b'{"t": "\x93texto\x94"}'
    assert _decode_json_body(raw) == {"t": "“texto”"}


def test_decode_json_body_latin1_puro_parseia():
    from sei_api._base import _decode_json_body

    raw = '{"t": "instaurações"}'.encode("latin-1")
    assert _decode_json_body(raw) == {"t": "instaurações"}


def test_decode_json_body_json_invalido_levanta_jsondecodeerror():
    from sei_api._base import _decode_json_body

    with pytest.raises(json.JSONDecodeError):
        _decode_json_body(b"\xf5 nao e json")
    with pytest.raises(json.JSONDecodeError):
        _decode_json_body(b"nao e json")


@pytest.mark.parametrize(
    ("method", "_data", "_expected", "vazio"),
    _LISTAGENS_IDS,
    ids=[m for m, *_ in _LISTAGENS_IDS],
)
def test_listagens_ids_corpo_vazio_retorna_vazio(
    monkeypatch, method, _data, _expected, vazio
):
    _mock_request(monkeypatch, b"   ")
    assert getattr(SeiApiClient(CFG), method)() == vazio

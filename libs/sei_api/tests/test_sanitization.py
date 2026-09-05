"""Anonimização do IdentificacaoServico em SeiApiError.from_source_exc.

Portado das asserções ainda relevantes do fork (test_sei_db_handlers_sanitization.py).
Cobre só o que mapeia para o comportamento atual da lib: from_source_exc muta a
exceção de origem in-place para limpar a cadeia __cause__ e o detail. Os testes
do fork sobre decorators (_handle_api_errors*) e o logging record factory ficaram
de fora — são internos do fork que a lib não tem.
"""

from __future__ import annotations

import httpx
import requests
from sei_api import SeiApiError

IDENTIFICACAO_SERVICO = (
    "1ad5be0dd4296ebc07007090397641f36f4e405e157e0600ee02047151e5ea0dcd9eb2c4"
)


def _requests_http_error(status_code: int = 404) -> requests.HTTPError:
    prepared = requests.Request(
        "GET",
        "https://seisu41.su.anatel.gov.br/sei/controlador_ws.php/md_ia_download_arquivo_avulso",
        params={
            "servico": "md_ia_download_arquivo_avulso",
            "SiglaSistema": "Usuario_IA",
            "IdentificacaoServico": IDENTIFICACAO_SERVICO,
            "IdArquivoAvulso": "4",
        },
    ).prepare()
    assert prepared.url is not None
    response = requests.Response()
    response.status_code = status_code
    response.url = prepared.url
    response.request = prepared
    try:
        response.raise_for_status()
    except requests.HTTPError as err:
        return err
    raise RuntimeError("Esperava HTTPError, mas raise_for_status não falhou.")


def test_from_source_exc_muta_args_e_url_in_place():
    err = _requests_http_error()
    assert IDENTIFICACAO_SERVICO in str(err)
    assert IDENTIFICACAO_SERVICO in err.request.url
    assert IDENTIFICACAO_SERVICO in err.response.url

    sei_exc = SeiApiError.from_source_exc(err, status_code=404)

    assert IDENTIFICACAO_SERVICO not in sei_exc.detail
    assert "<anonimizado>" in sei_exc.detail
    assert IDENTIFICACAO_SERVICO not in str(err)
    assert IDENTIFICACAO_SERVICO not in err.request.url
    assert IDENTIFICACAO_SERVICO not in err.response.url


def test_from_source_exc_nao_quebra_com_httpx_url_imutavel():
    request = httpx.Request(
        "GET",
        "https://seisu41.su.anatel.gov.br/sei/controlador_ws.php"
        f"?IdentificacaoServico={IDENTIFICACAO_SERVICO}&IdDocumento=42",
    )
    response = httpx.Response(404, request=request)
    err = httpx.HTTPStatusError(
        f"404 Not Found for url https://x?IdentificacaoServico={IDENTIFICACAO_SERVICO}",
        request=request,
        response=response,
    )

    sei_exc = SeiApiError.from_source_exc(err, status_code=404)

    assert IDENTIFICACAO_SERVICO not in sei_exc.detail
    assert "<anonimizado>" in sei_exc.detail

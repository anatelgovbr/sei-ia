from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from requests.exceptions import ConnectionError

from api_sei.exception_handling.exceptions import (
    ResourceNotFoundException,
    SolrException,
)
from api_sei.resources.custom_parsedquery import (
    JOBS_API_ADDRESS,
    SOLR_INDEX_VISIBILITY_ATTEMPTS,
    SOLR_INDEX_VISIBILITY_INTERVAL_SECONDS,
    SOLR_INDEX_VISIBILITY_REQUEST_TIMEOUT_SECONDS,
    auth,
    get_all_str_search_fields,
)


class _FakeClock:
    def __init__(self):
        self.elapsed = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.elapsed += seconds


@pytest.fixture
def fake_clock(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(
        "api_sei.resources.custom_parsedquery.time.monotonic",
        clock.monotonic,
    )
    monkeypatch.setattr(
        "api_sei.resources.custom_parsedquery.time.sleep",
        clock.sleep,
    )
    return clock


def _http_ok(payload):
    response = Mock()
    response.status_code = 200
    response.text = ""
    response.json.return_value = payload
    return response


@patch("api_sei.db_models.solr_select.requests.get")
def test_etl_fallback_accepts_list_response_after_solr_miss(mock_get):
    mock_get.side_effect = [
        _http_ok({"response": {"numFound": 0, "docs": []}}),
        _http_ok(
            [
                {
                    "id_protocolo": "17734309",
                    "metadata_name_id_type_process": "Fiscalização",
                    "content_id_type_doc_1": "Conteúdo",
                }
            ]
        ),
        _http_ok(
            {
                "response": {
                    "numFound": 1,
                    "docs": [{"id_protocolo": "17734309"}],
                }
            }
        ),
    ]

    fields = get_all_str_search_fields("17734309", "http://solr/processos_bm25")

    assert fields == [
        "metadata_name_id_type_process",
        "content_id_type_doc_1",
    ]

    fallback_call = mock_get.call_args_list[1]
    fallback_url = fallback_call.args[0]
    assert fallback_url.startswith(
        f"{JOBS_API_ADDRESS}/process/unindexed/nr_process/17734309?"
    )
    assert parse_qs(urlparse(fallback_url).query) == {
        "rows": ["1"],
        "start": ["0"],
    }
    assert fallback_call.kwargs["auth"] is auth
    assert mock_get.call_count == 3


@patch("api_sei.resources.custom_parsedquery.SolrRequests.get")
def test_etl_fallback_polls_until_process_is_visible(mock_get, fake_clock):
    fallback_doc = {
        "id_protocolo": "17707332",
        "metadata_name_id_type_process": "Fiscalização",
        "content_id_type_doc_1": "Conteúdo",
    }
    indexed_doc = {"id_protocolo": "17707332"}
    mock_get.side_effect = [
        [],
        [fallback_doc],
        [],
        [],
        [indexed_doc],
    ]

    fields = get_all_str_search_fields("17707332", "http://solr/processos_bm25")

    assert fields == [
        "metadata_name_id_type_process",
        "content_id_type_doc_1",
    ]
    assert fake_clock.sleeps == [
        SOLR_INDEX_VISIBILITY_INTERVAL_SECONDS,
        SOLR_INDEX_VISIBILITY_INTERVAL_SECONDS,
    ]
    assert mock_get.call_count == 5
    solr_calls = [mock_get.call_args_list[index] for index in (0, 2, 3, 4)]
    assert {call.kwargs["url"] for call in solr_calls} == {
        "http://solr/processos_bm25/select?q=id_protocolo:17707332&fl=*"
    }
    assert all(call.kwargs["rows"] == 1 for call in solr_calls)
    assert all(call.kwargs["start"] == 0 for call in solr_calls)
    assert all(call.kwargs["auth"] is auth for call in solr_calls)
    assert "timeout" not in solr_calls[0].kwargs
    assert [solr_call.kwargs["timeout"] for solr_call in solr_calls[1:]] == [
        SOLR_INDEX_VISIBILITY_REQUEST_TIMEOUT_SECONDS
    ] * 3


@patch("api_sei.resources.custom_parsedquery.SolrRequests.get")
def test_etl_fallback_stops_after_five_bounded_checks(mock_get, fake_clock, caplog):
    fallback_doc = {
        "id_protocolo": "17707332",
        "metadata_process_specification": "Assunto",
    }
    mock_get.side_effect = [
        [],
        [fallback_doc],
        *([[]] * SOLR_INDEX_VISIBILITY_ATTEMPTS),
    ]

    fields = get_all_str_search_fields("17707332", "http://solr/processos_bm25")

    assert fields == ["metadata_process_specification"]
    assert mock_get.call_count == 2 + SOLR_INDEX_VISIBILITY_ATTEMPTS
    assert fake_clock.sleeps == [SOLR_INDEX_VISIBILITY_INTERVAL_SECONDS] * 4
    assert [
        solr_call.kwargs["timeout"] for solr_call in mock_get.call_args_list[2:]
    ] == [
        SOLR_INDEX_VISIBILITY_REQUEST_TIMEOUT_SECONDS
    ] * SOLR_INDEX_VISIBILITY_ATTEMPTS
    assert "did not make 17707332 visible after 5 check(s)" in caplog.text


@patch("api_sei.db_models.solr_select.requests.get")
def test_indexed_process_does_not_call_etl(mock_get):
    mock_get.return_value = _http_ok(
        {
            "response": {
                "numFound": 1,
                "docs": [
                    {
                        "id_protocolo": "17734309",
                        "metadata_process_specification": "Assunto",
                    }
                ],
            }
        }
    )

    fields = get_all_str_search_fields("17734309", "http://solr/processos_bm25")

    assert fields == ["metadata_process_specification"]
    assert mock_get.call_count == 1


@patch("api_sei.db_models.solr_select.requests.get")
def test_missing_process_still_returns_not_found(mock_get):
    mock_get.side_effect = [
        _http_ok({"response": {"numFound": 0, "docs": []}}),
        _http_ok({"error": "Processo não encontrado"}),
    ]

    with pytest.raises(ResourceNotFoundException):
        get_all_str_search_fields("99999999", "http://solr/processos_bm25")


@patch("api_sei.db_models.solr_select.requests.get")
def test_etl_transport_error_is_not_converted_to_not_found(mock_get):
    mock_get.side_effect = [
        _http_ok({"response": {"numFound": 0, "docs": []}}),
        ConnectionError("ETL indisponível"),
    ]

    with pytest.raises(SolrException) as exc_info:
        get_all_str_search_fields("17734309", "http://solr/processos_bm25")

    assert exc_info.value.status_code == 503


@pytest.mark.parametrize(
    "fallback_payload",
    [
        [],
        {"unexpected": "shape"},
        [None],
        ["unexpected"],
        [{}],
        [{"metadata_process_specification": "Assunto"}],
        [{"id_protocolo": "99999999"}],
    ],
)
@patch("api_sei.resources.custom_parsedquery.SolrRequests.get")
def test_invalid_etl_contract_returns_not_found_without_polling(
    mock_get, fake_clock, fallback_payload
):
    mock_get.side_effect = [[], fallback_payload]

    with pytest.raises(ResourceNotFoundException):
        get_all_str_search_fields("17734309", "http://solr/processos_bm25")

    assert mock_get.call_count == 2
    assert fake_clock.sleeps == []

"""tests solr mlt."""

from unittest.mock import Mock, patch

import pytest

from api_sei.db_models.solr_mlt import SolrMlt, process_mlt_qf
from api_sei.exception_handling.exceptions import ResourceNotFoundException
from api_sei.pydantic_models.solr_mlt import ExtractionMethodEnum, SolrMltConfigModel


def _config(**overrides):
    defaults = {
        "url": "http://fakehost:0000/solr/process",
        "fields": ["texto"],
        "id_field": "id_protocolo",
    }
    defaults.update(overrides)
    return SolrMltConfigModel(**defaults)


@pytest.fixture()
def mock_config() -> SolrMltConfigModel:
    """Creates a mock instance of the SolrMltConfigModel class with predefined values for the id_field, extra_fields.

    Returns:
        Mock: A mock instance of the SolrMltConfigModel class.
    """
    config = Mock(spec=SolrMltConfigModel)
    config.id_field = "doc_id"
    config.extra_fields = ["author", "title"]
    config.fields = ["text", "content"]
    config.url = "http://example.com/solr"

    return config


@pytest.fixture()
def solr_mlt(mock_config: SolrMltConfigModel) -> SolrMlt:
    """Fixture that creates an instance of the SolrMlt class with the provided mock_config.

    :param mock_config: A mock instance of the SolrMltConfigModel class.
    :type mock_config: SolrMltConfigModel
    :return: An instance of the SolrMlt class.
    :rtype: SolrMlt
    """
    return SolrMlt(config=mock_config)


def test_build_fl(solr_mlt: SolrMlt) -> None:
    """Test the _build_fl method of the SolrMlt class.

    This test verifies that the _build_fl method correctly builds the field list
    for the Solr More Like This (MLT) query. It checks if the result matches the
    expected field list.

    Parameters:
    - solr_mlt (SolrMlt): An instance of the SolrMlt class.

    Returns:
    - None

    Raises:
    - AssertionError: If the result does not match the expected field list.
    """
    result = solr_mlt._build_fl()
    expected_result = "doc_id,score,author,title"
    assert result == expected_result, (
        "The _build_fl method should return the correct field list"
    )  # noqa: S101


def test_build_initial_query(solr_mlt: SolrMlt) -> None:
    """Test the _build_initial_query method of the SolrMlt class.

    This test verifies that the _build_initial_query method correctly builds the initial query URL
    for retrieving more like this (MLT) documents from Solr. It checks if the built URL matches the
    expected result.

    Parameters:
    - solr_mlt (SolrMlt): An instance of the SolrMlt class.

    Returns:
    - None

    Raises:
    - AssertionError: If the built URL does not match the expected result.

    Note:
    - The test assumes that the SolrMlt class has the following attributes:
        - config (SolrMltConfigModel): The configuration object for the SolrMlt class.
        - _build_fl (function): A private method that builds the field list for the MLT query.

    - The test assumes that the SolrMltConfigModel class has the following attributes:
        - id_field (str): The name of the field used as the document ID in Solr.
        - fields (List[str]): The list of fields to retrieve in the MLT query.
        - url (str): The base URL of the Solr server.

    - The test assumes that the SolrMlt class has the following methods:
        - _build_fl (function): A private method that builds the field list for the MLT query.

    - The test assumes that the expected result is a string representing the URL of the MLT query.
    """
    solr_doc_id = "123"
    result = solr_mlt._build_initial_query(solr_doc_id)
    expected_result = "http://example.com/solr/mlt?q=doc_id:123&fl=doc_id,score,author,title&mlt.fl=text,content"
    assert result == expected_result, (
        "The _build_initial_query should build the correct query URL"
    )  # noqa: S101


@pytest.mark.parametrize(
    ("input_str", "expected_output"),
    [
        ("title(text)", "titletext"),
        ("(content)", "content"),
        ("title+content", "title content"),
        ("name+^content+age", "name ^content age"),
        ("+title(^content)", " title^content"),
        ("^name+(content)", "^name content"),
        ("^+", "^"),
        ("()", ""),
        ("+()", " "),
    ],
)
def test_process_mlt_qf(input_str: str, expected_output: str) -> None:
    """Test the `process_mlt_qf` function with different input strings and expected output.

    Parameters:
        input_str (str): The input string to be processed.
        expected_output (str): The expected output of the `process_mlt_qf` function.

    Returns:
        None

    This function uses the `pytest.mark.parametrize` decorator to run the test multiple times with different input
    and expected output values. It asserts that the output of the `process_mlt_qf` function matches the expected output.
    """
    assert process_mlt_qf(input_str) == expected_output, (
        f"Expected {expected_output}, but {process_mlt_qf(input_str)}"
    )  # noqa: S101


class TestAddMltFilters:
    def test_no_filters_applied_with_defaults(self):
        mlt = SolrMlt(_config())
        assert mlt._add_mlt_filters("BASE") == "BASE"

    def test_all_filters_applied_when_non_default(self):
        config = _config(maxdfpct=50, maxqt=30, mintf=3, mindf=6, minwl=2, maxwl=10)
        mlt = SolrMlt(config)
        result = mlt._add_mlt_filters("BASE")
        assert result == (
            "BASE&mlt.maxdfpct=50&mlt.maxqt=30&mlt.mintf=3&mlt.mindf=6"
            "&mlt.minwl=2&mlt.maxwl=10"
        )


class TestAddMltWeights:
    def test_no_boost_no_qf(self):
        mlt = SolrMlt(_config())
        assert mlt._add_mlt_weights("BASE") == "BASE"

    def test_boost_true_adds_flag(self):
        mlt = SolrMlt(_config(boost=True))
        assert mlt._add_mlt_weights("BASE") == "BASE&mlt.boost=true"

    def test_mlt_qf_processed_and_appended(self):
        mlt = SolrMlt(_config(mlt_qf="titulo+conteudo"))
        assert mlt._add_mlt_weights("BASE") == "BASE&mlt.qf=titulo conteudo"


class TestAddSelectFilters:
    def test_no_filters(self):
        mlt = SolrMlt(_config())
        assert mlt._add_select_filters("BASE", None, None) == "BASE"

    def test_pfq_only(self):
        mlt = SolrMlt(_config())
        assert (
            mlt._add_select_filters("BASE", [1, 2], None)
            == "BASE&fq=id_protocolo:( 1 2 )"
        )

    def test_pfq_and_nfq(self):
        mlt = SolrMlt(_config())
        result = mlt._add_select_filters("BASE", [1], [2])
        assert result == "BASE&fq=id_protocolo:( 1 ) AND -id_protocolo:( 2 )"


class TestBuildMltQuery:
    def test_builds_full_query_with_filters_and_weights(self):
        mlt = SolrMlt(_config(boost=True, maxqt=30))
        result = mlt._build_mlt_query("123", None, None)
        assert result == (
            "http://fakehost:0000/solr/process/mlt?q=id_protocolo:123"
            "&fl=id_protocolo,score&mlt.fl=texto&mlt.maxqt=30&mlt.boost=true"
        )

    def test_appends_debug_flag_when_configured(self):
        mlt = SolrMlt(_config(debug=True))
        result = mlt._build_mlt_query("123", None, None)
        assert result == (
            "http://fakehost:0000/solr/process/mlt?q=id_protocolo:123"
            "&fl=id_protocolo,score&mlt.fl=texto&debug_query=on&wt=json"
        )


class TestBuildLikeQuery:
    def test_uses_camelcase_interesting_terms_param(self):
        mlt = SolrMlt(_config())
        result = mlt._build_like_query("123")
        assert result == (
            "http://fakehost:0000/solr/process/mlt?q=id_protocolo:123"
            "&fl=id_protocolo,score&mlt.fl=texto"
            "&mlt.boost=true&wt=json&mlt.interestingTerms=details"
        )


class TestBuildMoreQuery:
    def test_uses_given_parsedquery(self):
        mlt = SolrMlt(_config(debug=True))
        result = mlt._build_more_query("titulo:teste", [1], None)
        assert "q=titulo:teste" in result
        assert "&fq=id_protocolo:( 1 )" in result
        assert result.endswith("&debug_query=on&wt=json")

    def test_defaults_to_wildcard_when_empty(self):
        mlt = SolrMlt(_config())
        result = mlt._build_more_query("", None, None)
        assert "q=*:*" in result


class TestBuildMoreJson:
    def test_without_debug(self):
        mlt = SolrMlt(_config())
        jsn = mlt._build_more_json("titulo:teste", 10, None, None)
        assert jsn == {
            "params": {
                "fl": "id_protocolo,score",
                "rows": 10,
                "q": "titulo:teste",
                "fq": "id_protocolo:*",
            }
        }

    def test_with_debug_adds_all(self):
        mlt = SolrMlt(_config(debug=True))
        jsn = mlt._build_more_json("titulo:teste", 10, None, None)
        assert jsn["params"]["debug"] == "all"


class TestInterestingTermsToParsedquery:
    def test_converts_pairs_to_boosted_terms(self):
        result = SolrMlt.interestingterms_to_parsedquery(
            ["titulo:teste", 1.5, "corpo:abc", 2.0]
        )
        assert result == "titulo:teste^1.5 corpo:abc^2.0"

    def test_empty_list_returns_empty_string(self):
        assert SolrMlt.interestingterms_to_parsedquery([]) == ""


class TestProcessParsedquery:
    def test_without_mlt_qf_only_strips_parens(self):
        mlt = SolrMlt(_config())
        assert mlt.process_parsedquery("titulo:(teste)") == "titulo:teste"

    def test_with_mlt_qf_and_boost_multiplies_weights(self):
        mlt = SolrMlt(_config(mlt_qf="titulo^2", boost=True))
        result = mlt.process_parsedquery("titulo:teste^3.0 outro:abc^1.0")
        assert result == "titulo:teste^6.0 outro:abc^1.0"

    def test_with_mlt_qf_without_boost_uses_field_weight_directly(self):
        mlt = SolrMlt(_config(mlt_qf="titulo^2", boost=False))
        result = mlt.process_parsedquery("titulo:teste^3.0 outro:abc^1.0")
        assert result == "titulo:teste^2.0 outro:abc^1"


class TestMltRequest:
    def test_direct_request_type(self):
        mlt = SolrMlt(_config())
        fake_resp = {"response": {"docs": [{"id_protocolo": "1", "score": 1.0}]}}
        with patch(
            "api_sei.db_models.solr_mlt.SolrRequests.get", return_value=fake_resp
        ):
            result = mlt._mlt_request("123", 10, None, None, "direct")
        assert result["response"]["docs"][0]["id_protocolo"] == "1"

    def test_indirect_request_type_uses_real_solr_response_shape(self):
        """Regressão: o Solr real devolve a chave `interestingTerms` (camelCase) no
        JSON de resposta do handler MLT quando `mlt.interestingTerms=details` é usado
        (confirmado via curl contra o Solr real). Um response shape com essa grafia
        não pode quebrar `_mlt_request` no caminho indirect."""
        mlt = SolrMlt(_config())
        like_response = {
            "response": {"docs": []},
            "interestingTerms": ["texto:termo", 1.0, "texto:outro", 2.0],
        }
        more_response = {"response": {"docs": [{"id_protocolo": "1", "score": 1.0}]}}
        with patch(
            "api_sei.db_models.solr_mlt.SolrRequests.get",
            side_effect=[like_response, more_response],
        ) as mock_get:
            result = mlt._mlt_request("123", 10, None, None, "indirect")

        assert result["response"]["docs"][0]["id_protocolo"] == "1"
        like_call, more_call = mock_get.call_args_list
        assert "mlt.interestingTerms=details" in like_call.kwargs["url"]
        assert "q=texto:termo^1.0 texto:outro^2.0" in more_call.kwargs["url"]

    def test_unknown_request_type_raises_value_error(self):
        mlt = SolrMlt(_config())
        with pytest.raises(ValueError, match="Unknown request type bogus"):
            mlt._mlt_request("123", 10, None, None, "bogus")

    def test_custom_sections_parsedquery_uses_faster_custom_parsed_query(self):
        mlt = SolrMlt(
            _config(
                custom_query=True, parsedquery_field="sections_parsedquery_t", fields=[]
            )
        )
        fake_resp = {"response": {"docs": []}}
        with (
            patch(
                "api_sei.db_models.solr_mlt.read_fulltext_sections_fields",
                return_value=({"fulltext_a"}, {"sections_a"}),
            ),
            patch("api_sei.db_models.solr_mlt.FasterCustomParsedQuery") as mock_fcpq,
            patch(
                "api_sei.db_models.solr_mlt.SolrRequests.post", return_value=fake_resp
            ) as mock_post,
        ):
            mock_fcpq.return_value.get_parsedquery.return_value = "titulo:teste"
            result = mlt._mlt_request("123", 10, None, None, "custom")

        mock_fcpq.assert_called_once_with("123", ignore_fields={"fulltext_a"})
        assert mock_post.call_args.kwargs["payload"]["params"]["q"] == "titulo:teste"
        assert result == fake_resp

    def test_custom_solr_extraction_uses_faster_custom_parsed_query(self):
        mlt = SolrMlt(
            _config(
                custom_query=True,
                extraction_method=ExtractionMethodEnum.solr,
                fields=[],
            )
        )
        fake_resp = {"response": {"docs": []}}
        with (
            patch(
                "api_sei.db_models.solr_mlt.read_fulltext_sections_fields",
                return_value=(set(), {"sections_a"}),
            ),
            patch("api_sei.db_models.solr_mlt.FasterCustomParsedQuery") as mock_fcpq,
            patch(
                "api_sei.db_models.solr_mlt.SolrRequests.post", return_value=fake_resp
            ),
        ):
            mock_fcpq.return_value.get_parsedquery.return_value = "titulo:teste"
            mlt._mlt_request("123", 10, None, None, "custom")

        mock_fcpq.assert_called_once_with("123", ignore_fields={"sections_a"})

    def test_custom_bm25_extraction_uses_manual_extract(self):
        mlt = SolrMlt(
            _config(
                custom_query=True,
                extraction_method=ExtractionMethodEnum.bm25,
                fields=[],
            )
        )
        fake_resp = {"response": {"docs": []}}
        with (
            patch(
                "api_sei.db_models.solr_mlt.read_fulltext_sections_fields",
                return_value=(set(), {"sections_a"}),
            ),
            patch(
                "api_sei.db_models.solr_mlt.ManualExtractCustomParsedQuery"
            ) as mock_manual,
            patch(
                "api_sei.db_models.solr_mlt.SolrRequests.post", return_value=fake_resp
            ),
        ):
            mock_manual.return_value.get_parsedquery.return_value = "titulo:teste"
            mlt._mlt_request("123", 10, None, None, "custom")

        mock_manual.assert_called_once_with("123", ignore_fields={"sections_a"})

    def test_custom_lda_extraction_uses_lda_extract(self):
        mlt = SolrMlt(
            _config(
                custom_query=True, extraction_method=ExtractionMethodEnum.lda, fields=[]
            )
        )
        fake_resp = {"response": {"docs": []}}
        with (
            patch(
                "api_sei.db_models.solr_mlt.read_fulltext_sections_fields",
                return_value=(set(), {"sections_a"}),
            ),
            patch("api_sei.db_models.solr_mlt.LDAExtractCustomParsedQuery") as mock_lda,
            patch(
                "api_sei.db_models.solr_mlt.SolrRequests.post", return_value=fake_resp
            ),
        ):
            mock_lda.return_value.get_parsedquery.return_value = "titulo:teste"
            mlt._mlt_request("123", 10, None, None, "custom")

        mock_lda.assert_called_once_with("123", ignore_fields={"sections_a"})

    def test_custom_propagates_exception_from_parsedquery_extraction(self):
        mlt = SolrMlt(
            _config(
                custom_query=True,
                extraction_method=ExtractionMethodEnum.bm25,
                fields=[],
            )
        )
        with (
            patch(
                "api_sei.db_models.solr_mlt.read_fulltext_sections_fields",
                return_value=(set(), set()),
            ),
            patch(
                "api_sei.db_models.solr_mlt.ManualExtractCustomParsedQuery"
            ) as mock_manual,
        ):
            mock_manual.side_effect = RuntimeError("boom")
            with pytest.raises(RuntimeError, match="boom"):
                mlt._mlt_request("123", 10, None, None, "custom")

    def test_custom_empty_parsedquery_returns_empty_docs_without_post(self):
        mlt = SolrMlt(
            _config(
                custom_query=True,
                extraction_method=ExtractionMethodEnum.solr,
                fields=[],
            )
        )
        with (
            patch(
                "api_sei.db_models.solr_mlt.read_fulltext_sections_fields",
                return_value=(set(), set()),
            ),
            patch("api_sei.db_models.solr_mlt.FasterCustomParsedQuery") as mock_fcpq,
            patch("api_sei.db_models.solr_mlt.SolrRequests.post") as mock_post,
        ):
            mock_fcpq.return_value.get_parsedquery.return_value = "   "

            result = mlt._mlt_request("123", 10, None, None, "custom")

        assert result == {"response": {"docs": []}}
        mock_post.assert_not_called()

    def test_custom_empty_parsedquery_includes_empty_debug_data(self):
        mlt = SolrMlt(
            _config(
                custom_query=True,
                debug=True,
                extraction_method=ExtractionMethodEnum.solr,
                fields=[],
            )
        )
        with (
            patch(
                "api_sei.db_models.solr_mlt.read_fulltext_sections_fields",
                return_value=(set(), set()),
            ),
            patch("api_sei.db_models.solr_mlt.FasterCustomParsedQuery") as mock_fcpq,
            patch("api_sei.db_models.solr_mlt.SolrRequests.post") as mock_post,
        ):
            mock_fcpq.return_value.get_parsedquery.return_value = "   "

            result = mlt._mlt_request("123", 10, None, None, "custom")

        assert result == {
            "response": {"docs": []},
            "debug": {"parsedquery": "", "explain": {}},
        }
        mock_post.assert_not_called()


class TestMlt:
    def _fake_response(self, docs):
        return {"response": {"docs": docs}}

    def test_removes_self_from_recommendation_when_present(self):
        mlt = SolrMlt(_config())
        fake_response = self._fake_response(
            [
                {"id_protocolo": "123", "score": 10.0},
                {"id_protocolo": "456", "score": 5.0},
            ]
        )
        with patch.object(mlt, "_mlt_request", return_value=fake_response):
            result = mlt.mlt("123", rows=10, fq=None)
        assert result["recommendation"] == [
            {"id": "456", "id_protocolo": "456", "score": 5.0}
        ]

    def test_removes_last_element_when_self_not_present(self):
        mlt = SolrMlt(_config())
        fake_response = self._fake_response(
            [
                {"id_protocolo": "456", "score": 5.0},
                {"id_protocolo": "789", "score": 3.0},
            ]
        )
        with patch.object(mlt, "_mlt_request", return_value=fake_response):
            result = mlt.mlt("123", rows=10, fq=None)
        assert result["recommendation"] == [
            {"id": "456", "id_protocolo": "456", "score": 5.0}
        ]

    def test_normalized_scales_scores_by_ref_score(self):
        mlt = SolrMlt(_config(normalized=True))
        fake_response = self._fake_response(
            [
                {"id_protocolo": "123", "score": 10.0},
                {"id_protocolo": "456", "score": 5.0},
            ]
        )
        with patch.object(mlt, "_mlt_request", return_value=fake_response):
            result = mlt.mlt("123", rows=10, fq=None)
        assert result["recommendation"][0]["score"] == pytest.approx(0.5)

    def test_normalized_empty_response_returns_empty_recommendation(self):
        mlt = SolrMlt(_config(normalized=True))
        with patch.object(mlt, "_mlt_request", return_value=self._fake_response([])):
            result = mlt.mlt("123", rows=10, fq=None)

        assert result == {"recommendation": []}

    def test_fq_with_missing_ids_logs_warning_but_keeps_result(self, caplog):
        mlt = SolrMlt(_config())
        fake_response = self._fake_response(
            [
                {"id_protocolo": "123", "score": 10.0},
                {"id_protocolo": "456", "score": 5.0},
            ]
        )
        with patch.object(mlt, "_mlt_request", return_value=fake_response):
            result = mlt.mlt("999", rows=10, fq=[123, 456, 999])
        assert result["recommendation"] == [
            {"id": "123", "id_protocolo": "123", "score": 10.0}
        ]
        assert "not found" in caplog.text

    def test_debug_adds_parsedquery_and_explain(self):
        mlt = SolrMlt(_config(debug=True))
        fake_response = {
            "response": {
                "docs": [
                    {"id_protocolo": "123", "score": 10.0},
                    {"id_protocolo": "456", "score": 5.0},
                ]
            },
            "debug": {
                "parsedquery": "titulo:teste",
                "explain": {"456": "some\nexplanation"},
            },
        }
        with patch.object(mlt, "_mlt_request", return_value=fake_response):
            result = mlt.mlt("123", rows=10, fq=None)
        assert result["debug"]["parsedquery"] == "titulo:teste"
        assert result["debug"]["explain"]["456"] == ["some", "explanation"]


class TestFind:
    def test_returns_document_when_found(self):
        mlt = SolrMlt(_config())
        with patch(
            "api_sei.db_models.solr_mlt.SolrRequests.select_raw",
            return_value=[{"id_protocolo": "123", "score": 1.0}],
        ):
            result = mlt.find("123")
        assert result == {"id": "123", "id_protocolo": "123", "score": 1.0}

    def test_raises_when_not_found(self):
        mlt = SolrMlt(_config())
        with (
            patch(
                "api_sei.db_models.solr_mlt.SolrRequests.select_raw", return_value=[]
            ),
            pytest.raises(ResourceNotFoundException),
        ):
            mlt.find("999")


class TestFindMany:
    def test_returns_all_when_all_found(self):
        mlt = SolrMlt(_config())
        docs = [{"id_protocolo": "1"}, {"id_protocolo": "2"}]
        with patch("api_sei.db_models.solr_mlt.SolrRequests.get", return_value=docs):
            result = mlt.find_many(["1", "2"])
        assert result == docs

    def test_raises_when_some_missing(self):
        mlt = SolrMlt(_config())
        with (
            patch(
                "api_sei.db_models.solr_mlt.SolrRequests.get",
                return_value=[{"id_protocolo": "1"}],
            ),
            pytest.raises(ResourceNotFoundException),
        ):
            mlt.find_many(["1", "2"])

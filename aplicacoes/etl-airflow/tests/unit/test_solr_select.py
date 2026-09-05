import unittest
from unittest.mock import Mock, patch

import pandas as pd
from requests import ConnectionError as RequestsConnectionError
from requests import JSONDecodeError, Timeout

from jobs.db_models.solr_handlers import SolrHandlers
from jobs.exception_handling.exceptions import (
    FieldInURLException,
    RowsNotFoundException,
    SolrException,
)


class TestSolrHandlers(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_successful_select(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "some_data"}
        mock_get.return_value = mock_response

        url = "http://example.com"
        result = SolrHandlers.get(url=url, rows=1)

        self.assertEqual(result, {"data": "some_data"}, )

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_timeout_error(self, mock_get):
        mock_get.side_effect = Timeout("Request timeout")

        url = "http://example.com"
        with self.assertRaises(Exception) as context:
            SolrHandlers.select(url)

            self.assertEqual(str(context.exception), "Request timeout", str(context.exception))

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_non_200_status_code(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        url = "http://example.com"
        with self.assertRaises(Exception):
            SolrHandlers.select(url)

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_json_decode_error(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = JSONDecodeError("JSON decode error", "", 0)
        mock_get.return_value = mock_response

        url = "http://example.com"
        with self.assertRaises(Exception):
            SolrHandlers.select(url)

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_nested_field_not_found(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "some_data"}
        mock_get.return_value = mock_response

        url = "http://example.com"
        with self.assertRaises(Exception) as context:
            SolrHandlers.select(url=url, nested_fields=["non_existent_field"])

        self.assertEqual(str(context.exception), "JSON field error: 502 - Field: response")


class TestSolrHandlersGet(unittest.TestCase):
    def test_get_without_rows_raises(self):
        with self.assertRaises(RowsNotFoundException):
            SolrHandlers.get(url="http://example.com")

    def test_get_rows_in_url_raises(self):
        with self.assertRaises(FieldInURLException):
            SolrHandlers.get(url="http://example.com?rows=10", rows=1)

    def test_get_start_in_url_raises(self):
        with self.assertRaises(FieldInURLException):
            SolrHandlers.get(url="http://example.com?start=0", rows=1)

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_get_with_params(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "some_data"}
        mock_get.return_value = mock_response

        result = SolrHandlers.get(
            url="http://example.com", rows=5, params={"q": "*:*"}
        )

        self.assertEqual(result, {"data": "some_data"})
        self.assertEqual(mock_get.call_args.kwargs["params"], {"q": "*:*"})

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_get_connection_error(self, mock_get):
        mock_get.side_effect = RequestsConnectionError("boom")
        with self.assertRaises(SolrException):
            SolrHandlers.get(url="http://example.com", rows=1)


class TestSolrHandlersCount(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_count_success(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": {"numFound": 3}}
        mock_get.return_value = mock_response

        result = SolrHandlers.count(solr_url="http://example.com", solr_core="core")

        self.assertEqual(result, 3)

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_count_non_200_logs_and_raises(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "boom"
        mock_response.json.side_effect = JSONDecodeError("bad json", "", 0)
        mock_get.return_value = mock_response

        with self.assertRaises(JSONDecodeError):
            SolrHandlers.count(solr_url="http://example.com", solr_core="core")


class TestSolrHandlersCheckSolrService(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_check_solr_service_true(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Apache SOLR admin"
        mock_get.return_value = mock_response

        self.assertTrue(SolrHandlers.check_solr_service("http://example.com"))

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_check_solr_service_false_wrong_body(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "outra coisa qualquer"
        mock_get.return_value = mock_response

        self.assertFalse(SolrHandlers.check_solr_service("http://example.com"))

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_check_solr_service_exception_returns_false(self, mock_get):
        mock_get.side_effect = RequestsConnectionError("boom")

        self.assertFalse(SolrHandlers.check_solr_service("http://example.com"))


class TestSolrHandlersCheckCoreExists(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_check_core_exists_true(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        self.assertTrue(
            SolrHandlers.check_core_exists("http://example.com", "core")
        )

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_check_core_exists_false_status(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        self.assertFalse(
            SolrHandlers.check_core_exists("http://example.com", "core")
        )

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_check_core_exists_exception_returns_false(self, mock_get):
        mock_get.side_effect = RequestsConnectionError("boom")

        self.assertFalse(
            SolrHandlers.check_core_exists("http://example.com", "core")
        )


class TestSolrHandlersPost(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.requests.post")
    def test_post_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        result = SolrHandlers.post(url="http://example.com", payload={"a": 1})

        self.assertEqual(result, {"ok": True})

    @patch("jobs.db_models.solr_handlers.requests.post")
    def test_post_connection_error(self, mock_post):
        mock_post.side_effect = RequestsConnectionError("boom")

        with self.assertRaises(SolrException):
            SolrHandlers.post(url="http://example.com", payload={"a": 1})

    @patch("jobs.db_models.solr_handlers.requests.post")
    def test_post_timeout(self, mock_post):
        mock_post.side_effect = Timeout("boom")

        with self.assertRaises(SolrException):
            SolrHandlers.post(url="http://example.com", payload={"a": 1})


class TestSolrHandlersDelete(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_delete_success(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_get.return_value = mock_response

        result = SolrHandlers.delete(url="http://example.com")

        self.assertEqual(result, {"ok": True})

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_delete_connection_error(self, mock_get):
        mock_get.side_effect = RequestsConnectionError("boom")

        with self.assertRaises(SolrException):
            SolrHandlers.delete(url="http://example.com")

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_delete_timeout(self, mock_get):
        mock_get.side_effect = Timeout("boom")

        with self.assertRaises(SolrException):
            SolrHandlers.delete(url="http://example.com")


class TestSolrHandlersDropByField(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.requests.post")
    def test_drop_by_field_success_with_single_value(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        SolrHandlers.drop_by_field(
            id_values=123, solr_url="http://example.com", solr_core="core"
        )

        sent_data = mock_post.call_args.kwargs["data"]
        self.assertIn("<query>id_protocolo:123</query>", sent_data)

    @patch("jobs.db_models.solr_handlers.requests.post")
    def test_drop_by_field_failure_logs_error(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "boom"
        mock_post.return_value = mock_response

        SolrHandlers.drop_by_field(
            id_values=[1, 2], solr_url="http://example.com", solr_core="core"
        )

        mock_post.assert_called_once()


class TestSolrHandlersRetrieveResponse(unittest.TestCase):
    def test_retrieve_response_propagates_exception_input(self):
        with self.assertRaises(SolrException):
            SolrHandlers.retrieve_response(ConnectionError("boom"), [])

    def test_retrieve_response_missing_status_code_or_text(self):
        with self.assertRaises(SolrException):
            SolrHandlers.retrieve_response(object(), [])

    def test_retrieve_response_missing_json_method(self):
        response = Mock(spec=["status_code", "text"])
        response.status_code = 200
        response.text = "ok"

        with self.assertRaises(SolrException):
            SolrHandlers.retrieve_response(response, [])

    def test_retrieve_response_not_found(self):
        response = Mock()
        response.status_code = 404
        response.text = "not found"

        with self.assertRaises(SolrException):
            SolrHandlers.retrieve_response(response, [])


class TestSolrHandlersSelect(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_select_paginates_until_num_found(self, mock_get):
        count_response = Mock()
        count_response.status_code = 200
        count_response.json.return_value = {"response": {"numFound": 2}}

        batch_response = Mock()
        batch_response.status_code = 200
        batch_response.json.return_value = {"response": ["doc1", "doc2"]}

        mock_get.side_effect = [count_response, batch_response]

        result = SolrHandlers.select(
            url="http://example.com",
            nested_fields=["response"],
            batch_size=700,
        )

        self.assertEqual(result, ["doc1", "doc2"])

    @patch("jobs.db_models.solr_handlers.requests.get")
    def test_select_respects_k_results(self, mock_get):
        count_response = Mock()
        count_response.status_code = 200
        count_response.json.return_value = {"response": {"numFound": 2}}

        batch_response = Mock()
        batch_response.status_code = 200
        batch_response.json.return_value = {"response": ["doc1", "doc2"]}

        mock_get.side_effect = [count_response, batch_response]

        result = SolrHandlers.select(
            url="http://example.com",
            nested_fields=["response"],
            batch_size=700,
            k_results=1,
        )

        self.assertEqual(result, ["doc1"])


class TestSolrHandlersQueryPagination(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.requests.get")
    @patch("jobs.db_models.solr_handlers.SolrHandlers.count")
    def test_query_pagination_empty_result(self, mock_count, mock_get):
        mock_count.return_value = 0

        result = SolrHandlers.query_pagination(
            solr_url="http://example.com",
            solr_core="core",
            parameters={"fl": "id_protocolo, id_documento", "rows": 700},
            process_result_callback=lambda docs: pd.DataFrame(docs),
        )

        self.assertTrue(result.empty)
        mock_get.assert_not_called()

    @patch("jobs.db_models.solr_handlers.requests.get")
    @patch("jobs.db_models.solr_handlers.SolrHandlers.count")
    def test_query_pagination_single_page(self, mock_count, mock_get):
        mock_count.return_value = 1
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": {"docs": [{"id_protocolo": "1", "id_documento": "2"}]}
        }
        mock_get.return_value = mock_response

        result = SolrHandlers.query_pagination(
            solr_url="http://example.com",
            solr_core="core",
            parameters={"fl": "id_protocolo, id_documento", "rows": 700},
            process_result_callback=lambda docs: pd.DataFrame(docs),
        )

        self.assertEqual(len(result), 1)


class TestSolrHandlersProcessIndexed(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.SolrHandlers.query_pagination")
    @patch("jobs.db_models.solr_handlers.create_solr_core")
    def test_process_indexed(self, mock_create_core, mock_query_pagination):
        mock_query_pagination.return_value = pd.DataFrame(
            [
                {
                    "id_protocolo": 1,
                    "id_document": 2,
                    "id_type_process": 3,
                    "list_documents": 2,
                }
            ]
        )

        result = SolrHandlers.process_indexed(
            solr_url="http://example.com", solr_core="core", batch_size=700
        )

        mock_create_core.assert_called_once()
        self.assertEqual(result, [{"id_protocolo": 1, "id_document": 2, "id_type_process": 3}])


class TestSolrHandlersJurisprudenceIndexed(unittest.TestCase):
    @patch("jobs.db_models.solr_handlers.SolrHandlers.query_pagination")
    @patch("jobs.db_models.solr_handlers.create_solr_core")
    def test_jurisprudence_indexed(self, mock_create_core, mock_query_pagination):
        mock_query_pagination.return_value = pd.DataFrame([{"id_document": 1}])

        result = SolrHandlers.jurisprudence_indexed(
            solr_url="http://example.com", solr_core="core", batch_size=700
        )

        mock_create_core.assert_called_once()
        self.assertEqual(result, [{"id_document": 1}])

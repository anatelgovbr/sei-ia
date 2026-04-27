import unittest
from unittest.mock import Mock, patch

from jobs.dags.database.create_solr_core import create_solr_core


class TestCreateSolrCore(unittest.TestCase):
    @patch("jobs.dags.database.create_solr_core.requests.get")
    def test_skip_create_when_core_exists(self, mock_get):
        status_response = Mock()
        status_response.status_code = 200
        status_response.json.return_value = {"status": {"test_core": {"name": "test_core"}}}
        mock_get.return_value = status_response

        address = "http://example.com"
        name = "test_core"
        conf = "test_config"

        create_solr_core(address, name, conf)

        mock_get.assert_called_with(
            f"{address}/solr/admin/cores?action=STATUS&core={name}&indexInfo=false&wt=json",
            timeout=60,
            auth=None,
            verify=True,
        )

    @patch("jobs.dags.database.create_solr_core.requests.get")
    def test_create_core_when_status_is_empty(self, mock_get):
        status_response = Mock()
        status_response.status_code = 200
        status_response.json.return_value = {"status": {}}

        create_response = Mock()
        create_response.status_code = 200

        mock_get.side_effect = [status_response, create_response]

        address = "http://example.com"
        name = "test_core"
        conf = "test_config"

        create_solr_core(address, name, conf)

        self.assertEqual(mock_get.call_count, 2)
        mock_get.assert_any_call(
            f"{address}/solr/admin/cores?action=CREATE&name={name}&configSet={conf}",
            timeout=60,
            auth=None,
            verify=True,
        )

    @patch("jobs.dags.database.create_solr_core.requests.get")
    def test_create_core_failure(self, mock_get):
        status_response = Mock()
        status_response.status_code = 200
        status_response.json.return_value = {"status": {}}

        create_response = Mock()
        create_response.status_code = 500
        create_response.text = "Internal Server Error"

        mock_get.side_effect = [status_response, create_response]

        address = "http://example.com"
        name = "test_core"
        conf = "test_config"

        with self.assertRaises(Exception) as context:
            create_solr_core(address, name, conf)

        self.assertEqual(
            str(context.exception), f"Failed to create core:Internal Server Error"
        )

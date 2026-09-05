"""Tests for jobs/dags/database/delete_solr_core.py."""

from unittest.mock import MagicMock, patch

import pytest

from jobs.dags.database.delete_solr_core import delete_solr_core


class TestDeleteSolrCore:
    def test_deletes_core_when_reload_succeeds(self):
        reload_response = MagicMock(status_code=200)
        unload_response = MagicMock(status_code=200)

        with patch(
            "requests.get", side_effect=[reload_response, unload_response]
        ) as mock_get:
            delete_solr_core("http://solr", "core1")

        assert mock_get.call_count == 2
        unload_call_url = mock_get.call_args_list[1].args[0]
        assert "action=UNLOAD" in unload_call_url
        assert "deleteIndex=true" in unload_call_url
        assert "deleteDataDir=true" in unload_call_url
        assert "deleteInstanceDir=false" in unload_call_url

    def test_noop_when_reload_fails(self):
        reload_response = MagicMock(status_code=404)

        with patch("requests.get", return_value=reload_response) as mock_get:
            delete_solr_core("http://solr", "core1")

        mock_get.assert_called_once()

    def test_raises_when_unload_fails(self):
        reload_response = MagicMock(status_code=200)
        unload_response = MagicMock(status_code=500)

        with patch(
            "requests.get", side_effect=[reload_response, unload_response]
        ), pytest.raises(RuntimeError):
            delete_solr_core("http://solr", "core1")

    def test_respects_delete_flags(self):
        reload_response = MagicMock(status_code=200)
        unload_response = MagicMock(status_code=200)

        with patch(
            "requests.get", side_effect=[reload_response, unload_response]
        ) as mock_get:
            delete_solr_core(
                "http://solr",
                "core1",
                delete_index=False,
                delete_data_dir=False,
                delete_instance_dir=True,
            )

        unload_call_url = mock_get.call_args_list[1].args[0]
        assert "deleteIndex=false" in unload_call_url
        assert "deleteDataDir=false" in unload_call_url
        assert "deleteInstanceDir=true" in unload_call_url

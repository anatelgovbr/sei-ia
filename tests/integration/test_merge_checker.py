#!/usr/bin/env python
"""Módulo de teste para verificar a funcionalidade do verificador de merge."""

from unittest.mock import Mock, mock_open, patch

import pytest
import requests_mock
from merge_checker import (
    check_new_merge_from_rss,
    get_entries_from_rss,
    handle_merge_check,
)

# Example RSS feed data for mocking responses
RSS_FEED_EXAMPLE = """
<feed>
    <entry>
        <link href="http://new-merge-url.com"/>
    </entry>
</feed>
"""

# Mocked details JSON content
MOCKED_DETAILS_JSON = '{"url_last_merge": "http://old-merge-url.com"}'


@pytest.fixture()
def rss_response() -> str:
    """Fixture to return example RSS feed."""
    return RSS_FEED_EXAMPLE


@pytest.fixture()
def mocked_details_file() -> Mock:
    """Fixture to simulate reading from a JSON file."""
    return mock_open(read_data=MOCKED_DETAILS_JSON)


def test_get_entries_from_rss(rss_response: str) -> None:
    """Test retrieval of the last merge requests from an RSS feed."""
    url_rss = "http://example-rss-feed.com"
    with requests_mock.Mocker() as m:
        m.get(url_rss, text=rss_response)
        result = get_entries_from_rss(url_rss)
        assert result["link"]["@href"] == "http://new-merge-url.com" #noqa: S101


@patch("merge_checker.get_entries_from_rss")
def test_check_new_merge_from_rss(mock_get_last_merge: Mock) -> None:
    """Test to verify if there is a new merge from the RSS feed."""
    mock_get_last_merge.return_value = [{"link": {"@href": "http://new-merge-url.com"}}]
    url_rss = "http://example-rss-feed.com"
    url_last_merge = "http://old-merge-url.com"
    new_merge, url_current_merge = check_new_merge_from_rss(url_rss, url_last_merge)
    assert new_merge #noqa: S101
    assert url_current_merge == "http://new-merge-url.com" #noqa: S101

    # Test when there is no new merge
    mock_get_last_merge.return_value = [{"link": {"@href": "http://old-merge-url.com"}}]
    new_merge, url_current_merge = check_new_merge_from_rss(url_rss, url_last_merge)
    assert not new_merge #noqa: S101
    assert url_current_merge == "http://old-merge-url.com" #noqa: S101

    # Test when url_last_merge is None
    mock_get_last_merge.return_value = [{"link": {"@href": "http://new-merge-url.com"}}]
    new_merge, url_current_merge = check_new_merge_from_rss(url_rss, None)
    assert new_merge #noqa: S101
    assert url_current_merge == "http://new-merge-url.com" #noqa: S101


@patch("pathlib.Path.write_text")
@patch("pathlib.Path.open", new_callable=mock_open, read_data=MOCKED_DETAILS_JSON)
def test_handle_merge_check(
    mock_file: Mock, mock_write_text: Mock, rss_response: str# noqa: ARG001
) -> None:
    """Test to handle the merge check process."""
    service = "example-service"
    env_alias = "dev"
    url_rss = "http://example-rss-feed.com"
    with requests_mock.Mocker() as m:
        m.get(url_rss, text=rss_response)
        with patch(
            "merge_checker.get_entries_from_rss",
            return_value=[{"link": {"@href": "http://new-merge-url.com"}}],
        ):
            new_merge, details = handle_merge_check(service, env_alias, url_rss)
            assert new_merge #noqa: S101
            assert details["url_last_merge"] == "http://new-merge-url.com" #noqa: S101
            mock_write_text.assert_called_once_with('{"url_last_merge": "http://new-merge-url.com"}')

    # Test when there is no JSON details file
    with patch("pathlib.Path.exists", return_value=False) \
        and patch("merge_checker.get_entries_from_rss",
                  return_value=[{"link": {"@href": "http://new-merge-url.com"}}],
        ):

        new_merge, details = handle_merge_check(service, env_alias, url_rss)
        assert new_merge #noqa: S101
        assert details["url_last_merge"] == "http://new-merge-url.com" #noqa: S101
        mock_write_text.assert_called_with('{"url_last_merge": "http://new-merge-url.com"}')


@patch("pathlib.Path.write_text")
@patch("pathlib.Path.open", new_callable=mock_open, read_data=MOCKED_DETAILS_JSON)
def test_handle_merge_check_url_last_merge(
    mock_file: Mock, mock_write_text: Mock, rss_response: str # noqa: ARG001
) -> None:
    """Test reading url_last_merge from JSON file in handle_merge_check."""
    service = "example-service"
    env_alias = "dev"
    url_rss = "http://example-rss-feed.com"

    with requests_mock.Mocker() as m:
        m.get(url_rss, text=rss_response)

        with patch(
            "merge_checker.get_entries_from_rss",
            return_value=[{"link": {"@href": "http://old-merge-url.com"}}],
        ):
            new_merge, details = handle_merge_check(service, env_alias, url_rss)
            assert new_merge #noqa: S101
            assert details["url_last_merge"] == "http://old-merge-url.com" #noqa: S101


def test_get_entries_from_rss_key_error(rss_response: str) -> None: #noqa: ARG001
    """Test KeyError exception handling in get_entries_from_rss."""
    url_rss = "http://example-rss-feed.com"
    with requests_mock.Mocker() as m:
        # Simulate an invalid RSS response without 'entry' key
        invalid_rss_response = "<feed></feed>"
        m.get(url_rss, text=invalid_rss_response)

        with patch("logging.info") as mock_logging_info: #noqa: F841
            result = get_entries_from_rss(url_rss)
            assert result is None #noqa: S101


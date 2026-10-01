from unittest.mock import MagicMock, patch

from jobs.envs import _get_litellm_model_info


def test_litellm_model_info_uses_proxy_authentication() -> None:
    response = MagicMock()
    response.json.return_value = {
        "data": [
            {
                "model_name": "embedding",
                "litellm_params": {"model": "openai/model"},
                "model_info": {"base_model": "text-embedding-3-small"},
            }
        ]
    }

    with patch("requests.get", return_value=response) as request:
        result = _get_litellm_model_info(
            "http://litellm.local", "embedding", "proxy-secret"
        )

    request.assert_called_once_with(
        "http://litellm.local/model/info",
        headers={"Authorization": "Bearer proxy-secret"},
        timeout=5,
    )
    assert result["base_model"] == "text-embedding-3-small"

"""Tests for api_sei/routers/jurisprudence_recommender.py."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api_sei.routers.jurisprudence_recommender import get_doc2doc_search


class TestGetDoc2DocSearch:
    @pytest.mark.asyncio
    async def test_delegates_to_service_when_text_is_given(self):
        with patch(
            "api_sei.routers.jurisprudence_recommender.doc2doc_search",
            return_value={"id_recommendation": 1, "recommendation": []},
        ) as mock_service:
            result = await get_doc2doc_search(text="processo administrativo")

        assert result == {"id_recommendation": 1, "recommendation": []}
        kwargs = mock_service.call_args.kwargs
        assert kwargs["text"] == "processo administrativo"
        assert kwargs["fq"] is None
        assert kwargs["requested_at"] is not None

    @pytest.mark.asyncio
    async def test_delegates_to_service_when_list_id_doc_is_given(self):
        with patch(
            "api_sei.routers.jurisprudence_recommender.doc2doc_search",
            return_value={"id_recommendation": 1, "recommendation": []},
        ) as mock_service:
            result = await get_doc2doc_search(list_id_doc=[135629])

        assert result == {"id_recommendation": 1, "recommendation": []}
        mock_service.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_400_when_text_and_list_id_doc_are_both_empty(self):
        with pytest.raises(HTTPException) as excinfo:
            await get_doc2doc_search(text="", list_id_doc=[])

        assert excinfo.value.status_code == 400
        assert "não podem ser ambos vazios" in excinfo.value.detail

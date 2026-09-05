"""Testes unitários para sei_ia/routers/chat/gpt_4o_mini_128k.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestChatCompletationGpt4oMini128k:
    def test_chama_process_chat_completion_com_model_type_mini(self):
        from sei_ia.routers.chat.gpt_4o_mini_128k import (
            chat_completation_gpt_4o_mini_128k,
        )

        mock_request = MagicMock()
        mock_request.use_thinking = False
        mock_request_starlette = MagicMock()
        expected_result = {"choices": [{"message": {"content": "resposta"}}]}

        with patch(
            "sei_ia.routers.chat.gpt_4o_mini_128k.process_chat_completion",
            new_callable=AsyncMock,
            return_value=expected_result,
        ) as mock_process:
            result = asyncio.run(
                chat_completation_gpt_4o_mini_128k(mock_request, mock_request_starlette)
            )

        mock_process.assert_awaited_once()
        call_kwargs = mock_process.call_args.kwargs
        assert call_kwargs["model_data"]["agent_tag"] == "classificador"
        assert result == expected_result

    def test_use_thinking_preserva_model_type_mini(self):
        """Após a unificação via Responses API, use_thinking não troca o
        agent_tag — reasoning é ativado via `ChatOpenAI(use_responses_api=True)`."""
        from sei_ia.routers.chat.gpt_4o_mini_128k import (
            chat_completation_gpt_4o_mini_128k,
        )

        mock_request = MagicMock()
        mock_request.use_thinking = True
        mock_request_starlette = MagicMock()

        with patch(
            "sei_ia.routers.chat.gpt_4o_mini_128k.process_chat_completion",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_process:
            asyncio.run(
                chat_completation_gpt_4o_mini_128k(mock_request, mock_request_starlette)
            )

        call_kwargs = mock_process.call_args.kwargs
        assert call_kwargs["model_data"]["agent_tag"] == "classificador"

    def test_temperatura_zero(self):
        from sei_ia.routers.chat.gpt_4o_mini_128k import (
            chat_completation_gpt_4o_mini_128k,
        )

        mock_request = MagicMock()
        mock_request.use_thinking = False
        mock_request_starlette = MagicMock()

        with patch(
            "sei_ia.routers.chat.gpt_4o_mini_128k.process_chat_completion",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_process:
            asyncio.run(
                chat_completation_gpt_4o_mini_128k(mock_request, mock_request_starlette)
            )

        call_kwargs = mock_process.call_args.kwargs
        assert "temperature" not in call_kwargs["model_data"]

    def test_endpoint_name_correto(self):
        from sei_ia.routers.chat.gpt_4o_mini_128k import (
            chat_completation_gpt_4o_mini_128k,
        )

        mock_request = MagicMock()
        mock_request.use_thinking = False
        mock_request_starlette = MagicMock()

        with patch(
            "sei_ia.routers.chat.gpt_4o_mini_128k.process_chat_completion",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_process:
            asyncio.run(
                chat_completation_gpt_4o_mini_128k(mock_request, mock_request_starlette)
            )

        call_kwargs = mock_process.call_args.kwargs
        assert (
            call_kwargs["model_data"]["endpoint_name"]
            == "/llm_lang/chat_gpt_4o_mini_128k"
        )

    def test_retorna_resultado_do_process_chat_completion(self):
        from sei_ia.routers.chat.gpt_4o_mini_128k import (
            chat_completation_gpt_4o_mini_128k,
        )

        mock_request = MagicMock()
        mock_request.use_thinking = False
        mock_request_starlette = MagicMock()
        expected = {"id": "abc", "choices": []}

        with patch(
            "sei_ia.routers.chat.gpt_4o_mini_128k.process_chat_completion",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = asyncio.run(
                chat_completation_gpt_4o_mini_128k(mock_request, mock_request_starlette)
            )

        assert result == expected

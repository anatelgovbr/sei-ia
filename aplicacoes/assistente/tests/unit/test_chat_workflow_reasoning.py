"""Testes unitários dos helpers de reasoning/content em message_content."""

from __future__ import annotations

from types import SimpleNamespace

from sei_ia.services.llm_models.message_content import (
    extract_reasoning_delta_from_content,
)


class TestExtractDeltas:
    def test_content_str_legado(self):
        chunk = SimpleNamespace(content="Olá mundo")
        assert extract_reasoning_delta_from_content(chunk.content) == ""

    def test_content_list_reasoning_blocks(self):
        chunk = SimpleNamespace(
            content=[
                {
                    "type": "reasoning",
                    "summary": [
                        {"type": "summary_text", "text": "analisando "},
                        {"type": "summary_text", "text": "agora"},
                    ],
                    "index": 0,
                },
            ]
        )
        assert extract_reasoning_delta_from_content(chunk.content) == "analisando agora"

    def test_content_list_text_block(self):
        chunk = SimpleNamespace(
            content=[
                {"type": "text", "text": "resposta", "index": 1},
                {"type": "output_text", "text": " final"},
            ]
        )
        assert extract_reasoning_delta_from_content(chunk.content) == ""

    def test_content_none_retorna_string_vazia(self):
        chunk = SimpleNamespace(content=None)
        assert extract_reasoning_delta_from_content(chunk.content) == ""

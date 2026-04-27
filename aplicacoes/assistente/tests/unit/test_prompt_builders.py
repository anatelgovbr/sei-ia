"""
Testes unitários simplificados para prompt_builders.py
"""

import pytest

from sei_ia.agents.pergunta.prompt_builders import (
    _format_metadata_dict,
    build_prompt_with_complete_documents,
    build_prompt_with_grouped_chunks,
)
from tests.fixtures.mock_data import (
    create_mock_chunks,
    create_mock_user_state_direct_path,
    create_mock_user_state_rag_enhanced,
)


class TestPromptBuilders:
    """Testes simplificados para construtores de prompt."""

    def test_format_metadata_dict_simple(self):
        """Testa formatação simples de metadados."""
        # Arrange
        metadata = {
            "assunto": "Contratos",
            "orgao": "Ministério da Educação",
            "data": "2023-01-15",
        }

        # Act
        result = _format_metadata_dict(metadata)

        # Assert
        assert isinstance(result, str)
        assert "assunto: Contratos" in result
        assert "Ministério da Educação" in result
        assert "2023-01-15" in result

    def test_format_metadata_dict_empty(self):
        """Testa formatação de metadados vazios."""
        # Arrange
        metadata = {}

        # Act
        result = _format_metadata_dict(metadata)

        # Assert
        assert isinstance(result, str)
        assert result == "Não disponível"

    def test_build_prompt_with_complete_documents_empty(self):
        """Testa construção com conjunto vazio de documentos."""
        # Arrange
        document_ids = set()
        document_scores = {}
        user_state = create_mock_user_state_direct_path()

        # Act
        prompt = build_prompt_with_complete_documents(
            document_ids, document_scores, user_state
        )

        # Assert
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert user_state["user_request"] in prompt

    def test_build_prompt_with_grouped_chunks_single_document(self):
        """Testa construção com chunks normais."""
        # Arrange
        user_state = (
            create_mock_user_state_rag_enhanced()
        )  # Tem doc_001, doc_002, doc_003
        chunks = create_mock_chunks()  # Retorna chunks de doc_001 e doc_002

        # Act
        prompt = build_prompt_with_grouped_chunks(chunks, user_state)

        # Assert
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert user_state["user_request"] in prompt

        # Deve conter pelo menos alguns dos textos dos chunks
        chunk_texts_in_prompt = sum(1 for chunk in chunks if chunk["text"] in prompt)
        assert chunk_texts_in_prompt > 0

    def test_build_prompt_with_complete_documents_with_mock_docs(self):
        """Testa construção com documentos do user_state."""
        # Arrange
        user_state = create_mock_user_state_direct_path()
        document_ids = {"doc_001"}  # ID que existe no mock
        document_scores = {"doc_001": 0.85}

        # Act
        prompt = build_prompt_with_complete_documents(
            document_ids, document_scores, user_state
        )

        # Assert
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert user_state["user_request"] in prompt


if __name__ == "__main__":
    pytest.main([__file__])

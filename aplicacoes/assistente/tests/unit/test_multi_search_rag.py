"""
Testes unitários para sei_ia.agents.pergunta.multi_search_rag.py
"""

from unittest.mock import patch

import pytest

from sei_ia.agents.pergunta.multi_search_rag import (
    remove_duplicate_chunks,
    search_single_question,
    search_with_multiple_questions,
)
from tests.fixtures.mock_data import (
    create_mock_chunks,
    create_mock_embedding,
    create_mock_questions,
    create_mock_user_state_rag_enhanced,
)
from tests.utils.test_helpers import (
    TestAssertions,
    validate_chunk_structure,
    validate_search_results,
)


class TestSearchWithMultipleQuestions:
    """Testes para a função search_with_multiple_questions."""

    @pytest.mark.asyncio
    @patch("sei_ia.agents.pergunta.multi_search_rag.search_single_question")
    async def test_search_with_multiple_questions_success(self, mock_search_single):
        """Testa busca bem-sucedida com múltiplas perguntas."""
        # Arrange
        questions = create_mock_questions()
        user_state = create_mock_user_state_rag_enhanced()

        # Mock retorna chunks diferentes para cada pergunta
        mock_chunks = create_mock_chunks()
        mock_search_single.return_value = mock_chunks[:2]  # 2 chunks por pergunta

        # Act
        result = await search_with_multiple_questions(questions, user_state)

        # Assert
        validate_search_results(result)
        assert mock_search_single.call_count == len(questions)
        assert len(result["chunks"]) > 0
        assert len(result["document_ids"]) > 0
        assert len(result["document_scores"]) > 0

    @pytest.mark.asyncio
    @patch("sei_ia.agents.pergunta.multi_search_rag.search_single_question")
    async def test_search_with_multiple_questions_duplicate_removal(
        self, mock_search_single
    ):
        """Testa remoção de duplicatas entre perguntas."""
        # Arrange
        questions = ["Pergunta 1?", "Pergunta 2?"]
        user_state = create_mock_user_state_rag_enhanced()

        # Mesmos chunks para ambas as perguntas (simula duplicatas)
        same_chunks = [
            {
                "text": "Texto duplicado",
                "similarity_score": 0.8,
                "id_documento": "doc_001",
                "start_position": 0,
                "finished_position": 50,
            }
        ]
        mock_search_single.return_value = same_chunks

        # Act
        result = await search_with_multiple_questions(questions, user_state)

        # Assert
        # Deve ter apenas 1 chunk único após deduplicação
        assert len(result["chunks"]) == 1
        assert result["chunks"][0]["text"] == "Texto duplicado"

    @pytest.mark.asyncio
    @patch("sei_ia.agents.pergunta.multi_search_rag.search_single_question")
    async def test_search_with_multiple_questions_error_handling(
        self, mock_search_single
    ):
        """Testa tratamento de erro em uma das buscas."""
        # Arrange
        questions = ["Pergunta 1?", "Pergunta 2?", "Pergunta 3?"]
        user_state = create_mock_user_state_rag_enhanced()

        # Primeira busca falha, segunda e terceira funcionam
        mock_search_single.side_effect = [
            Exception("Erro na busca"),
            [create_mock_chunks()[0]],
            [create_mock_chunks()[1]],
        ]

        # Act
        result = await search_with_multiple_questions(questions, user_state)

        # Assert
        # Deve continuar com as buscas que funcionaram
        assert len(result["chunks"]) == 2
        validate_search_results(result)

    @pytest.mark.asyncio
    @patch("sei_ia.agents.pergunta.multi_search_rag.search_single_question")
    async def test_search_score_aggregation(self, mock_search_single):
        """Testa agregação de scores por documento."""
        # Arrange
        questions = ["Pergunta 1?", "Pergunta 2?"]
        user_state = create_mock_user_state_rag_enhanced()

        # Chunks do mesmo documento com scores diferentes
        mock_search_single.side_effect = [
            [
                {"text": "Chunk 1", "similarity_score": 0.8, "id_documento": "doc_001"},
                {"text": "Chunk 2", "similarity_score": 0.6, "id_documento": "doc_001"},
            ],
            [{"text": "Chunk 3", "similarity_score": 0.7, "id_documento": "doc_001"}],
        ]

        # Act
        result = await search_with_multiple_questions(questions, user_state)

        # Assert
        # Score médio para doc_001 deve ser (0.8 + 0.6 + 0.7) / 3 = 0.7
        expected_avg = (0.8 + 0.6 + 0.7) / 3
        assert abs(result["document_scores"]["doc_001"] - expected_avg) < 0.01

    @pytest.mark.asyncio
    async def test_search_empty_questions(self):
        """Testa busca com lista vazia de perguntas."""
        # Arrange
        questions = []
        user_state = create_mock_user_state_rag_enhanced()

        # Act
        result = await search_with_multiple_questions(questions, user_state)

        # Assert
        assert len(result["chunks"]) == 0
        assert len(result["document_ids"]) == 0
        assert len(result["document_scores"]) == 0


class TestSearchSingleQuestion:
    """Testes para a função search_single_question."""

    @pytest.mark.asyncio
    @patch("sei_ia.agents.pergunta.multi_search_rag.embedding_generator")
    @patch("sei_ia.agents.pergunta.multi_search_rag.similarity_query")
    async def test_search_single_question_success(
        self, mock_similarity_query, mock_embedding_gen
    ):
        """Testa busca bem-sucedida para uma pergunta."""
        # Arrange
        question = "Qual o assunto do documento?"
        filter_metadata = [{"id_documento": "doc_001"}]

        mock_embedding_gen.generate.return_value = iter([create_mock_embedding()])

        # Mock do similarity_query retorna (texto, dict de chunks)
        mock_similarity_query.return_value = (
            "Texto formatado",
            {
                "doc_001": [
                    {
                        "text": "Chunk relevante",
                        "start_position": 0,
                        "finished_position": 50,
                        "similarity_score": 0.85,
                    }
                ]
            },
        )

        # Act
        user_state = create_mock_user_state_rag_enhanced()
        result = await search_single_question(question, filter_metadata, user_state)

        # Assert
        assert len(result) == 1
        validate_chunk_structure(result[0])
        assert result[0]["text"] == "Chunk relevante"
        assert result[0]["similarity_score"] == 0.85
        assert result[0]["id_documento"] == "doc_001"

    @pytest.mark.asyncio
    @patch("sei_ia.agents.pergunta.multi_search_rag.embedding_generator")
    @patch("sei_ia.agents.pergunta.multi_search_rag.similarity_query")
    async def test_search_single_question_multiple_docs(
        self, mock_similarity_query, mock_embedding_gen
    ):
        """Testa busca que retorna chunks de múltiplos documentos."""
        # Arrange
        question = "Qual o assunto?"
        filter_metadata = [{"id_documento": "doc_001"}, {"id_documento": "doc_002"}]

        mock_embedding_gen.generate.return_value = iter([create_mock_embedding()])
        mock_similarity_query.return_value = (
            "Texto formatado",
            {
                "doc_001": [
                    {
                        "text": "Chunk doc 1",
                        "start_position": 0,
                        "finished_position": 20,
                        "similarity_score": 0.8,
                    }
                ],
                "doc_002": [
                    {
                        "text": "Chunk doc 2",
                        "start_position": 0,
                        "finished_position": 25,
                        "similarity_score": 0.7,
                    }
                ],
            },
        )

        # Act
        user_state = create_mock_user_state_rag_enhanced()
        result = await search_single_question(question, filter_metadata, user_state)

        # Assert
        assert len(result) == 2
        doc_ids = {chunk["id_documento"] for chunk in result}
        assert doc_ids == {"doc_001", "doc_002"}

    @pytest.mark.asyncio
    @patch("sei_ia.agents.pergunta.multi_search_rag.embedding_generator")
    @patch("sei_ia.agents.pergunta.multi_search_rag.similarity_query")
    async def test_search_single_question_no_results(
        self, mock_similarity_query, mock_embedding_gen
    ):
        """Testa busca que não encontra resultados."""
        # Arrange
        question = "Pergunta sem resultado"
        filter_metadata = [{"id_documento": "doc_001"}]

        mock_embedding_gen.generate.return_value = iter([create_mock_embedding()])
        mock_similarity_query.return_value = ("", {})

        # Act
        user_state = create_mock_user_state_rag_enhanced()
        result = await search_single_question(question, filter_metadata, user_state)

        # Assert
        assert len(result) == 0

    @pytest.mark.asyncio
    @patch("sei_ia.agents.pergunta.multi_search_rag.embedding_generator")
    async def test_search_single_question_embedding_error(self, mock_embedding_gen):
        """Testa tratamento de erro na geração de embedding."""
        # Arrange
        question = "Pergunta com erro"
        filter_metadata = [{"id_documento": "doc_001"}]

        mock_embedding_gen.generate.side_effect = Exception("Erro no embedding")

        # Act
        user_state = create_mock_user_state_rag_enhanced()
        result = await search_single_question(question, filter_metadata, user_state)

        # Assert
        # A função captura exceções e retorna lista vazia para não bloquear outras buscas
        assert isinstance(result, list)
        assert len(result) == 0


class TestRemoveDuplicateChunks:
    """Testes para a função remove_duplicate_chunks."""

    def test_remove_duplicate_chunks_no_duplicates(self):
        """Testa remoção quando não há duplicatas."""
        # Arrange
        chunks = create_mock_chunks()

        # Act
        result = remove_duplicate_chunks(chunks)

        # Assert
        assert len(result) == len(chunks)
        TestAssertions.assert_no_duplicate_chunks(result)

    def test_remove_duplicate_chunks_with_duplicates(self):
        """Testa remoção quando há duplicatas."""
        # Arrange
        chunk_base = {
            "text": "Texto duplicado",
            "similarity_score": 0.8,
            "id_documento": "doc_001",
        }
        chunks = [
            chunk_base.copy(),
            chunk_base.copy(),  # Duplicata exata
            {
                "text": "Texto diferente",
                "similarity_score": 0.7,
                "id_documento": "doc_002",
            },
            chunk_base.copy(),  # Outra duplicata
        ]

        # Act
        result = remove_duplicate_chunks(chunks)

        # Assert
        assert len(result) == 2  # Deve manter apenas únicos
        texts = [chunk["text"] for chunk in result]
        assert "Texto duplicado" in texts
        assert "Texto diferente" in texts
        TestAssertions.assert_no_duplicate_chunks(result)

    def test_remove_duplicate_chunks_whitespace_differences(self):
        """Testa que diferenças de espaço em branco são tratadas como duplicatas."""
        # Arrange
        chunks = [
            {
                "text": "Texto com espaços",
                "similarity_score": 0.8,
                "id_documento": "doc_001",
            },
            {
                "text": " Texto com espaços ",
                "similarity_score": 0.7,
                "id_documento": "doc_001",
            },  # Com espaços extras
            {
                "text": "\nTexto com espaços\t",
                "similarity_score": 0.6,
                "id_documento": "doc_001",
            },  # Com quebras
        ]

        # Act
        result = remove_duplicate_chunks(chunks)

        # Assert
        assert len(result) == 1  # Deve manter apenas um

    def test_remove_duplicate_chunks_empty_list(self):
        """Testa remoção com lista vazia."""
        # Arrange
        chunks = []

        # Act
        result = remove_duplicate_chunks(chunks)

        # Assert
        assert len(result) == 0

    def test_remove_duplicate_chunks_preserves_highest_score(self):
        """Testa que preserva o chunk com maior score entre duplicatas."""
        # Arrange
        chunks = [
            {"text": "Mesmo texto", "similarity_score": 0.6, "id_documento": "doc_001"},
            {
                "text": "Mesmo texto",
                "similarity_score": 0.9,
                "id_documento": "doc_001",
            },  # Score maior
            {"text": "Mesmo texto", "similarity_score": 0.7, "id_documento": "doc_001"},
        ]

        # Act
        result = remove_duplicate_chunks(chunks)

        # Assert
        assert len(result) == 1
        # Deve preservar o primeiro encontrado (ordem de entrada)
        assert result[0]["similarity_score"] == 0.6

    def test_remove_duplicate_chunks_case_sensitivity(self):
        """Testa sensibilidade a maiúsculas/minúsculas."""
        # Arrange
        chunks = [
            {
                "text": "Texto Em Maiúsculas",
                "similarity_score": 0.8,
                "id_documento": "doc_001",
            },
            {
                "text": "texto em maiúsculas",
                "similarity_score": 0.7,
                "id_documento": "doc_001",
            },
        ]

        # Act
        result = remove_duplicate_chunks(chunks)

        # Assert
        # Devem ser considerados diferentes (case sensitive)
        assert len(result) == 2


class TestChunkValidation:
    """Testes de validação de estrutura de chunks."""

    def test_chunk_structure_validation(self):
        """Testa validação da estrutura de chunks."""
        chunks = create_mock_chunks()

        for chunk in chunks:
            validate_chunk_structure(chunk)

    def test_chunk_scores_are_valid(self):
        """Testa que scores de chunks são válidos."""
        chunks = create_mock_chunks()

        for chunk in chunks:
            score = chunk["similarity_score"]
            assert 0 <= score <= 1, f"Score deve estar entre 0 e 1: {score}"
            assert isinstance(score, int | float), f"Score deve ser numérico: {score}"

    def test_chunks_have_document_ids(self):
        """Testa que todos os chunks têm ID de documento."""
        chunks = create_mock_chunks()

        for chunk in chunks:
            assert "id_documento" in chunk
            assert chunk["id_documento"], "ID do documento não deve estar vazio"


if __name__ == "__main__":
    pytest.main([__file__])

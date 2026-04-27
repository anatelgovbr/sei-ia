"""
Utilitários e helpers para testes da intenção pergunta.
"""

from sei_ia.data.pydantic_models import UserState


def assert_user_state_structure(user_state: UserState) -> None:
    """Valida que UserState tem a estrutura esperada."""
    required_fields = [
        "id_request",
        "id_usuario",
        "user_request",
        "intent",
        "all_tokens_counter",
        "general_max_ctx_len",
        "last_prompt",
    ]

    for field in required_fields:
        assert field in user_state, f"Campo {field} ausente no UserState"

    assert isinstance(user_state["id_procedimentos"], list), (
        "id_procedimentos deve ser lista"
    )
    assert len(user_state["id_procedimentos"]) > 0, (
        "Deve ter pelo menos um procedimento"
    )


def assert_direct_path_result(user_state: UserState) -> None:
    """Valida resultado do caminho direto."""
    assert not user_state["doc_rag"], "doc_rag deve ser False no caminho direto"
    assert user_state["rag_method"] is None, (
        "rag_method deve ser None no caminho direto"
    )
    assert user_state["last_prompt"], "last_prompt não deve estar vazio"
    assert user_state["user_request"] in user_state["last_prompt"], (
        "Pergunta deve estar no prompt"
    )


def assert_rag_enhanced_result(user_state: UserState, expected_method: str) -> None:
    """Valida resultado do RAG Enhanced."""
    assert user_state["doc_rag"], "doc_rag deve ser True no RAG Enhanced"
    assert user_state["rag_method"] == expected_method, (
        f"rag_method deve ser {expected_method}"
    )
    assert user_state["rag_documents_count"] is not None, (
        "rag_documents_count deve estar definido"
    )
    assert user_state["rag_chunks_count"] is not None, (
        "rag_chunks_count deve estar definido"
    )
    assert user_state["rag_documents_count"] > 0, "Deve ter encontrado documentos"
    assert user_state["rag_chunks_count"] > 0, "Deve ter encontrado chunks"


def validate_search_results(results: dict) -> None:
    """Valida estrutura dos resultados de busca."""
    required_keys = ["chunks", "document_ids", "document_scores"]
    for key in required_keys:
        assert key in results, f"Chave {key} ausente nos resultados"

    assert isinstance(results["chunks"], list), "chunks deve ser lista"
    assert isinstance(results["document_ids"], set), "document_ids deve ser set"
    assert isinstance(results["document_scores"], dict), "document_scores deve ser dict"

    # Validar estrutura dos chunks
    for chunk in results["chunks"]:
        assert "text" in chunk, "Chunk deve ter campo text"
        assert "similarity_score" in chunk, "Chunk deve ter similarity_score"
        assert "id_documento" in chunk, "Chunk deve ter id_documento"


def validate_chunk_structure(chunk: dict) -> None:
    """Valida estrutura de um chunk individual."""
    required_fields = ["text", "similarity_score", "id_documento"]
    for field in required_fields:
        assert field in chunk, f"Campo {field} ausente no chunk"

    assert isinstance(chunk["text"], str), "text deve ser string"
    assert isinstance(chunk["similarity_score"], int | float), (
        "similarity_score deve ser numérico"
    )
    assert 0 <= chunk["similarity_score"] <= 1, (
        "similarity_score deve estar entre 0 e 1"
    )


def validate_document_decision(fits: bool, total_tokens: int) -> None:
    """Valida resultado de decisão de documento."""
    assert isinstance(fits, bool)
    assert isinstance(total_tokens, int)
    assert total_tokens >= 0


class TestAssertions:
    """Classe com assertions customizadas para testes."""

    @staticmethod
    def assert_no_duplicate_chunks(chunks: list[dict]) -> None:
        """Valida que não há chunks duplicados."""
        texts = [chunk["text"] for chunk in chunks]
        assert len(texts) == len(set(texts)), "Não deve haver chunks duplicados"

    @staticmethod
    def assert_metadata_consistency(user_state: UserState) -> None:
        """Valida consistência dos metadados."""
        for proc in user_state["id_procedimentos"]:
            assert hasattr(proc, "metadata"), "Procedimento deve ter metadados"

            for doc in proc.id_documentos:
                assert hasattr(doc, "metadata"), "Documento deve ter metadados"
                assert hasattr(doc, "id_documento"), "Documento deve ter ID"

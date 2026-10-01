"""
Fixtures e dados mockados para testes da intenção pergunta.
"""

from sei_ia.data.pydantic_models import (
    ItemDocumentRequest,
    ItemRequestIdProcedimento,
    UserState,
)


def create_mock_user_state_direct_path() -> UserState:
    """Cria UserState para teste do caminho direto."""
    return {
        "id_request": "test_001",
        "id_usuario": "user_123",
        "ip": "127.0.0.1",
        "endpoint_name": "/test",
        "id_topico": None,
        "id_procedimentos": [
            ItemRequestIdProcedimento(
                id_procedimento="proc_001",
                id_documentos=[
                    ItemDocumentRequest(
                        id_documento="doc_001",
                        download_ext=False,
                        pag_doc_init=0,
                        pag_doc_end=0,
                        id_documento_formatado="DOC-001",
                        content="Conteúdo do documento de teste.",
                        metadata="Metadados do documento 1",
                        doc_tokens=100,
                        doc_paged=False,
                    )
                ],
                metadata="Metadados do procedimento 1",
            )
        ],
        "all_procs": ["proc_001"],
        "all_documents": ["doc_001"],
        "user_request": "Qual o assunto do documento?",
        "system_prompt": "Você é um assistente IA.",
        "original_request_body": "{}",
        "intent": "pergunta",
        "model_type": "standard",
        "model_name": "gpt-4.1",
        "temperature": 0.01,
        "general_max_output_tokens": 4000,
        "general_max_ctx_len": 900000,
        "limit_rag": 450000,
        "limit_false_rag": 90000,
        "use_websearch": False,
        "use_thinking": False,
        "summarize_history": False,
        "doc_paged": False,
        "doc_summarized": False,
        "doc_rag": False,
        "doc_false_rag": False,
        "all_tokens_counter": 50000,  # Baixo para forçar caminho direto
        "web_content": None,
        "last_prompt": "",
        "has_content": True,
        "rag_method": None,
        "rag_documents_count": None,
        "rag_chunks_count": None,
        "response": {},
    }


def create_mock_user_state_rag_enhanced() -> UserState:
    """Cria UserState para teste do RAG Enhanced."""
    user_state = create_mock_user_state_direct_path()

    # Modificar para forçar RAG
    user_state["all_tokens_counter"] = 1000000  # Alto para forçar RAG
    user_state["id_procedimentos"][0].id_documentos.extend(
        [
            ItemDocumentRequest(
                id_documento="doc_002",
                download_ext=False,
                pag_doc_init=0,
                pag_doc_end=0,
                id_documento_formatado="DOC-002",
                content="Segundo documento com mais conteúdo.",
                metadata="Metadados do documento 2",
                doc_tokens=200,
                doc_paged=False,
            ),
            ItemDocumentRequest(
                id_documento="doc_003",
                download_ext=False,
                pag_doc_init=0,
                pag_doc_end=0,
                id_documento_formatado="DOC-003",
                content="Terceiro documento para teste.",
                metadata="Metadados do documento 3",
                doc_tokens=150,
                doc_paged=False,
            ),
        ]
    )

    user_state["all_documents"].extend(["doc_002", "doc_003"])

    return user_state


def create_mock_chunks() -> list[dict]:
    """Cria lista de chunks mockados para testes."""
    return [
        {
            "text": "Este é o primeiro chunk de texto relevante.",
            "start_position": 0,
            "finished_position": 45,
            "similarity_score": 0.85,
            "id_documento": "doc_001",
        },
        {
            "text": "Segundo chunk com informações importantes.",
            "start_position": 46,
            "finished_position": 87,
            "similarity_score": 0.72,
            "id_documento": "doc_001",
        },
        {
            "text": "Chunk de outro documento com dados relevantes.",
            "start_position": 0,
            "finished_position": 46,
            "similarity_score": 0.68,
            "id_documento": "doc_002",
        },
    ]


def create_mock_search_results() -> dict:
    """Cria resultado mockado de busca múltipla."""
    chunks = create_mock_chunks()
    document_ids = {"doc_001", "doc_002"}
    document_scores = {
        "doc_001": 0.785,  # Média dos scores dos chunks do doc_001
        "doc_002": 0.68,
    }

    return {
        "chunks": chunks,
        "document_ids": document_ids,
        "document_scores": document_scores,
    }


def create_mock_questions() -> list[str]:
    """Cria lista de perguntas mockadas geradas pelo LLM."""
    return [
        "Qual é o assunto principal do documento?",
        "Sobre o que trata o documento mencionado?",
        "Que tópico o documento #4946026 aborda?",
        "Qual é o tema central do documento?",
        "O que é discutido no documento em questão?",
        "Qual matéria é tratada no documento?",
    ]


def create_mock_similarity_df():
    """Cria DataFrame mockado para similarity query.

    Nota: O campo emb_text foi removido do modelo. Use start_position e finished_position
    para recuperar o texto via ChunkContentRetriever.
    """
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "id_documento": "doc_001",
                "cosine_similarity": 0.85,
                "start_position": 0,
                "finished_position": 45,
            },
            {
                "id_documento": "doc_001",
                "cosine_similarity": 0.72,
                "start_position": 46,
                "finished_position": 87,
            },
            {
                "id_documento": "doc_002",
                "cosine_similarity": 0.68,
                "start_position": 0,
                "finished_position": 46,
            },
        ]
    )


def create_mock_embedding() -> list[float]:
    """Cria embedding mockado."""
    # Simulando um embedding de 1536 dimensões (padrão OpenAI)
    import random

    random.seed(42)  # Para reprodutibilidade
    return [random.uniform(-1, 1) for _ in range(1536)]


# Cenários específicos para diferentes testes


class MockScenarios:
    """Classe com diferentes cenários de teste."""

    @staticmethod
    def small_documents_fit_context():
        """Cenário: documentos pequenos que cabem no contexto."""
        user_state = create_mock_user_state_direct_path()
        user_state["all_tokens_counter"] = 30000
        return user_state

    @staticmethod
    def large_documents_need_rag():
        """Cenário: documentos grandes que precisam de RAG."""
        user_state = create_mock_user_state_rag_enhanced()
        user_state["all_tokens_counter"] = 1200000
        return user_state

    @staticmethod
    def rag_docs_fit_context():
        """Cenário: RAG encontra documentos que cabem no contexto."""
        user_state = create_mock_user_state_rag_enhanced()
        # Simular documentos menores que cabem após RAG
        for doc in user_state["id_procedimentos"][0].id_documentos:
            doc.doc_tokens = 1000  # Pequenos o suficiente para caber juntos
        return user_state

    @staticmethod
    def rag_docs_dont_fit_context():
        """Cenário: RAG encontra documentos que NÃO cabem no contexto."""
        user_state = create_mock_user_state_rag_enhanced()
        # Simular documentos grandes que não cabem
        for doc in user_state["id_procedimentos"][0].id_documentos:
            doc.doc_tokens = 500000  # Muito grandes para caber juntos
        return user_state

    @staticmethod
    def no_similar_chunks():
        """Cenário: nenhum chunk similar encontrado."""
        return {"chunks": [], "document_ids": set(), "document_scores": {}}

    @staticmethod
    def single_chunk_found():
        """Cenário: apenas um chunk encontrado."""
        return {
            "chunks": [create_mock_chunks()[0]],
            "document_ids": {"doc_001"},
            "document_scores": {"doc_001": 0.85},
        }


# Constantes úteis para testes
DEFAULT_CONTEXT_LIMIT = 900000
DEFAULT_RAG_LIMIT = 450000
TEST_EMBEDDING_DIM = 1536


def create_mock_documents_with_metadata() -> list[dict]:
    """Cria documentos mockados com metadados."""
    return [
        {
            "id_documento": "doc_001",
            "full_text": "Conteúdo completo do primeiro documento sobre contratos.",
            "metadata": {
                "assunto": "Contratos",
                "orgao": "Ministério da Educação",
                "data": "2023-01-15",
            },
        },
        {
            "id_documento": "doc_002",
            "full_text": "Conteúdo do segundo documento sobre licitações.",
            "metadata": {
                "assunto": "Licitações",
                "orgao": "Ministério da Saúde",
                "data": "2023-02-20",
            },
        },
    ]


def create_mock_grouped_chunks_by_doc() -> dict[str, list[dict]]:
    """Cria chunks agrupados por documento."""
    chunks = create_mock_chunks()
    return {"doc_001": chunks[:3], "doc_002": chunks[3:]}

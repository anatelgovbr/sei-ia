"""Testes unitários para modelos Pydantic de sei_ia/data/pydantic_models.py."""

from sei_ia.data.pydantic_models import (
    ChatRequest,
    ItemDocumentRequest,
    ItemRequestIdProcedimento,
)


class TestItemRequestIdProcedimentoValidators:
    """Testes para validators de ItemRequestIdProcedimento."""

    def test_na_substituido_por_vazio(self):
        item = ItemRequestIdProcedimento(
            id_procedimento="N/A",
            id_documentos=[ItemDocumentRequest(id_documento="d1")],
        )
        assert item.id_procedimento == ""

    def test_id_procedimento_normal_preservado(self):
        item = ItemRequestIdProcedimento(
            id_procedimento="00000.000000/0000-00",
            id_documentos=[ItemDocumentRequest(id_documento="d1")],
        )
        assert item.id_procedimento == "00000.000000/0000-00"

    def test_documentos_string_convertidos_para_objetos(self):
        item = ItemRequestIdProcedimento(
            id_procedimento="proc1",
            id_documentos=["doc_a", "doc_b"],
        )
        assert all(isinstance(d, ItemDocumentRequest) for d in item.id_documentos)

    def test_ids_preservados_na_conversao_de_strings(self):
        item = ItemRequestIdProcedimento(
            id_procedimento="proc1",
            id_documentos=["doc_x"],
        )
        assert item.id_documentos[0].id_documento == "doc_x"

    def test_lista_vazia_de_documentos(self):
        item = ItemRequestIdProcedimento(
            id_procedimento="proc1",
            id_documentos=[],
        )
        assert item.id_documentos == []

    def test_objetos_documento_nao_sao_retransformados(self):
        doc = ItemDocumentRequest(id_documento="doc1")
        item = ItemRequestIdProcedimento(
            id_procedimento="proc1",
            id_documentos=[doc],
        )
        assert item.id_documentos[0].id_documento == "doc1"


class TestChatRequestAllProcsAllowed:
    """Testes para ChatRequest.all_procs_allowed."""

    def test_retorna_lista_vazia_sem_procedimentos(self):
        req = ChatRequest(id_usuario=1, text="oi", id_procedimentos=None)
        assert req.all_procs_allowed() == []

    def test_retorna_lista_vazia_com_lista_vazia(self):
        req = ChatRequest(id_usuario=1, text="oi", id_procedimentos=[])
        assert req.all_procs_allowed() == []

    def test_retorna_id_de_um_procedimento(self):
        req = ChatRequest(
            id_usuario=1,
            text="oi",
            id_procedimentos=[
                ItemRequestIdProcedimento(
                    id_procedimento="proc1",
                    id_documentos=[ItemDocumentRequest(id_documento="d1")],
                )
            ],
        )
        assert req.all_procs_allowed() == ["proc1"]

    def test_retorna_ids_de_multiplos_procedimentos(self):
        req = ChatRequest(
            id_usuario=1,
            text="oi",
            id_procedimentos=[
                ItemRequestIdProcedimento(
                    id_procedimento="p1",
                    id_documentos=[ItemDocumentRequest(id_documento="d1")],
                ),
                ItemRequestIdProcedimento(
                    id_procedimento="p2",
                    id_documentos=[ItemDocumentRequest(id_documento="d2")],
                ),
            ],
        )
        result = req.all_procs_allowed()
        assert "p1" in result
        assert "p2" in result
        assert len(result) == 2


class TestChatRequestAllDocumentsAllowed:
    """Testes para ChatRequest.all_documents_allowed."""

    def test_retorna_lista_vazia_sem_procedimentos(self):
        req = ChatRequest(id_usuario=1, text="oi", id_procedimentos=None)
        assert req.all_documents_allowed() == []

    def test_retorna_id_documento(self):
        req = ChatRequest(
            id_usuario=1,
            text="oi",
            id_procedimentos=[
                ItemRequestIdProcedimento(
                    id_procedimento="p1",
                    id_documentos=[ItemDocumentRequest(id_documento="doc_abc")],
                )
            ],
        )
        assert "doc_abc" in req.all_documents_allowed()

    def test_retorna_todos_documentos_de_multiplos_procs(self):
        req = ChatRequest(
            id_usuario=1,
            text="oi",
            id_procedimentos=[
                ItemRequestIdProcedimento(
                    id_procedimento="p1",
                    id_documentos=[
                        ItemDocumentRequest(id_documento="d1"),
                        ItemDocumentRequest(id_documento="d2"),
                    ],
                ),
                ItemRequestIdProcedimento(
                    id_procedimento="p2",
                    id_documentos=[ItemDocumentRequest(id_documento="d3")],
                ),
            ],
        )
        result = req.all_documents_allowed()
        assert set(result) == {"d1", "d2", "d3"}

    def test_retorna_lista_vazia_com_procs_sem_documentos(self):
        req = ChatRequest(
            id_usuario=1,
            text="oi",
            id_procedimentos=[
                ItemRequestIdProcedimento(id_procedimento="p1", id_documentos=[])
            ],
        )
        assert req.all_documents_allowed() == []


class TestChatRequestModelOverride:
    """Testes para o campo `model` (override).

    A validação contra o catálogo do proxy LiteLLM não roda mais aqui — ela
    depende de rede (`GET /model/info`), então acontece em runtime, fora do
    parsing do Pydantic (ver `routers/chat/model_catalog.validate_model_override`
    e `tests/unit/test_model_catalog.py`). Aqui só garante que o campo é um
    passthrough simples.
    """

    def test_model_none_por_padrao(self):
        req = ChatRequest(id_usuario=1, text="oi")
        assert req.model is None

    def test_model_aceita_qualquer_string_sem_validar(self):
        req = ChatRequest(id_usuario=1, text="oi", model="openai/seiia-ds-gemini-pro")
        assert req.model == "openai/seiia-ds-gemini-pro"

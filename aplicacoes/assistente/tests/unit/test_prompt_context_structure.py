"""Testes da estrutura hierárquica do contexto SEI no last_prompt."""

from sei_ia.agents.prompts.context_formatters import format_procedures_context
from sei_ia.data.pydantic_models import ItemDocumentRequest, ItemRequestIdProcedimento


def _make_doc(
    *,
    id_documento: str = "doc_001",
    id_documento_formatado: str = "123456",
    metadata: str | None = None,
    content: str | None = "Texto do documento.",
):
    return ItemDocumentRequest(
        id_documento=id_documento,
        id_documento_formatado=id_documento_formatado,
        download_ext=False,
        pag_doc_init=0,
        pag_doc_end=0,
        metadata=metadata,
        content=content,
        doc_tokens=10,
        doc_paged=False,
    )


def _make_proc(*, docs=None, metadata: str | None = None):
    if docs is None:
        docs = [_make_doc()]
    return ItemRequestIdProcedimento(
        id_procedimento="proc_001",
        id_documentos=docs,
        metadata=metadata
        or (
            "ID do Processo: proc_001\n"
            "Número do Processo: 00000.000000/0000-00\n"
            "Descrição/Especificação do Processo: Processo de teste\n"
            "Tipo do Processo: Regulamentação: Teste"
        ),
    )


def test_formata_procedimento_com_metadados_e_documentos_aninhados():
    doc = _make_doc(
        id_documento="doc_001",
        id_documento_formatado="123456",
        metadata=(
            "ID do Documento: doc_001\n"
            "Número do Documento: 123456\n"
            "NomeTipoDocumento: Informe\n"
            "NumeroProcesso: 00000.000000/0000-00"
        ),
        content="Conteúdo efetivo do documento.",
    )
    prompt = format_procedures_context([_make_proc(docs=[doc])])

    assert "<procedimento_proc_001>" in prompt
    assert "ID do Processo: proc_001" in prompt
    assert "Número do Processo: 00000.000000/0000-00" in prompt
    assert "Tipo do Processo: Regulamentação: Teste" in prompt
    assert "<doc_doc_001>" in prompt
    assert "ID do Documento: doc_001" in prompt
    assert "NomeTipoDocumento: Informe" in prompt
    assert "NumeroProcesso: 00000.000000/0000-00" in prompt
    assert "<conteudo>\nConteúdo efetivo do documento.\n</conteudo>" in prompt
    assert prompt.index("<procedimento_proc_001>") < prompt.index("<doc_doc_001>")
    assert prompt.index("<metadados>") < prompt.index("<documentos>")


def test_preserva_ordem_dos_documentos_do_procedimento():
    doc_1 = _make_doc(
        id_documento="doc_001",
        id_documento_formatado="111",
        content="Primeiro documento.",
    )
    doc_2 = _make_doc(
        id_documento="doc_002",
        id_documento_formatado="222",
        content="Segundo documento.",
    )

    prompt = format_procedures_context([_make_proc(docs=[doc_1, doc_2])])

    assert prompt.index("<doc_doc_001>") < prompt.index("<doc_doc_002>")


def test_nao_emite_none_quando_metadata_ausente():
    doc = _make_doc(metadata=None, content="Texto sem metadados.")
    proc = _make_proc(docs=[doc], metadata=None)

    prompt = format_procedures_context([proc])

    assert "None" not in prompt
    assert "<metadados>" in prompt
    assert "<conteudo>\nTexto sem metadados.\n</conteudo>" in prompt


def test_remove_delimitadores_antigos_do_conteudo_cacheado():
    doc = _make_doc(
        content=(
            "-------\n"
            "# o conteúdo do documento #123456 do processo 00000.000000/0000-00\n"
            "está transcrito abaixo:\n"
            "(delimitado por [doc_123456---] conteúdo [\\doc_123456---])\n"
            "[doc_123456---]\n"
            "Texto limpo.\n"
            "[\\doc_123456---]"
        )
    )

    prompt = format_procedures_context([_make_proc(docs=[doc])])

    assert "<conteudo>\nTexto limpo.\n</conteudo>" in prompt
    assert "está transcrito abaixo" not in prompt
    assert "delimitado por" not in prompt
    assert "[doc_" not in prompt
    assert "[\\doc_" not in prompt

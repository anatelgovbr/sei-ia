"""Exceções de domínio para entradas inválidas de embeddings."""

from fastapi import HTTPException

from sei_ia.services.exceptions.http_exceptions import HTTPException400

MAX_PUBLIC_DOCUMENT_IDS = 5


class EmbeddingInputException(HTTPException400):
    """Erro local antes de uma chamada inválida ao provedor de embeddings."""

    def __init__(self, detail: str, document_id: str | None = None) -> None:
        self.document_id = document_id
        super().__init__(detail=detail)


class DocumentContentNotExtractableException(EmbeddingInputException):
    """Documento sem conteúdo que possa ser convertido em chunks."""

    def __init__(self, document_id: str) -> None:
        super().__init__(
            detail=(
                f"O documento {document_id} não possui conteúdo extraível "
                "para indexação."
            ),
            document_id=document_id,
        )


class EmptyEmbeddingInputException(EmbeddingInputException):
    """Lote vazio ou malformado bloqueado antes da chamada ao provedor."""

    def __init__(self, document_id: str | None = None) -> None:
        if document_id:
            detail = (
                f"A entrada de embedding do documento {document_id} está vazia; "
                "a chamada ao provedor foi bloqueada localmente."
            )
        else:
            detail = (
                "A entrada de embedding está vazia; "
                "a chamada ao provedor foi bloqueada localmente."
            )
        super().__init__(detail=detail, document_id=document_id)


class AutoIndexingException(HTTPException):
    """Falhas agregadas e sanitizadas da indexação automática."""

    def __init__(
        self,
        content_failure_count: int,
        document_ids: list[str],
        internal_failure_count: int,
    ) -> None:
        self.content_failure_count = content_failure_count
        self.internal_failure_count = internal_failure_count
        public_document_ids = document_ids[:MAX_PUBLIC_DOCUMENT_IDS]
        detail_parts = []

        if content_failure_count:
            content_label = (
                "documento sem conteúdo extraível"
                if content_failure_count == 1
                else "documentos sem conteúdo extraível"
            )
            content_detail = f"{content_failure_count} {content_label}"
            if public_document_ids:
                ids_detail = f"IDs: {', '.join(public_document_ids)}"
                remaining_count = content_failure_count - len(public_document_ids)
                if remaining_count > 0:
                    remaining_label = (
                        "documento" if remaining_count == 1 else "documentos"
                    )
                    ids_detail += (
                        f"; mais {remaining_count} {remaining_label} não exibidos"
                    )
                content_detail += f" ({ids_detail})"
            detail_parts.append(content_detail)

        if internal_failure_count:
            internal_label = (
                "falha interna" if internal_failure_count == 1 else "falhas internas"
            )
            detail_parts.append(f"{internal_failure_count} {internal_label}")

        status_code = 400 if content_failure_count else 500
        detail = f"A indexação automática falhou: {'; '.join(detail_parts)}."
        super().__init__(status_code=status_code, detail=detail)

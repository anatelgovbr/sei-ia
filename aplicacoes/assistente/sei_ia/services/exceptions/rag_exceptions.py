"""Exceções específicas para sistema RAG."""

from sei_ia.services.exceptions.http_exceptions import HTTPException400


class DocumentsNotIndexedException(HTTPException400):
    """Exceção lançada quando documentos necessários não estão indexados no banco vetorial."""

    def __init__(self, missing_documents: list[str], total_documents: int):
        """
        Inicializa exceção de documentos não indexados.

        Args:
            missing_documents: Lista de IDs de documentos não indexados
            total_documents: Total de documentos que deveriam estar indexados
        """
        self.missing_documents = missing_documents
        self.total_documents = total_documents
        self.missing_count = len(missing_documents)

        # Gerar mensagem detalhada
        if self.missing_count == total_documents:
            msg = f"Nenhum dos {total_documents} documentos dos processos está indexado no banco vetorial."
        else:
            msg = f"{self.missing_count} de {total_documents} documentos não estão indexados no banco vetorial."

        if self.missing_count <= 5:
            msg += f" Documentos faltantes: {', '.join(missing_documents)}."
        else:
            msg += f" Primeiros documentos faltantes: {', '.join(missing_documents[:5])}..."

        msg += " É necessário indexar os documentos antes de usar o sistema RAG."

        super().__init__(detail=msg)


class EmbeddingVerificationException(HTTPException400):
    """Exceção lançada quando há erro na verificação de embeddings."""

    def __init__(self, error_message: str):
        """
        Inicializa exceção de erro na verificação.

        Args:
            error_message: Mensagem de erro detalhada
        """
        msg = f"Erro ao verificar documentos indexados: {error_message}"
        super().__init__(detail=msg)

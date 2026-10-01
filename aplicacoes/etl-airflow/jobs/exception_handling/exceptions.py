"""Exceptions for the application."""


class ResourceNotFoundException(Exception):
    """Exception to use when a Solr index does not contain an id."""

    def __init__(self, message="Resource not found") -> None:
        self.message = message
        super().__init__(self.message)


class JsonFieldException(Exception):
    """Exception for JSON field errors."""

    def __init__(self, status_code=None, field=None) -> None:
        self.status_code = status_code
        self.field = field
        super().__init__(f"JSON field error: {status_code} - Field: {field}")


class SolrException(Exception):
    """Exception for Solr related errors."""

    def __init__(self, status_code=None, detail=None) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Solr error: {status_code} - {detail}")


class RowsNotFoundException(Exception):
    """Exception when rows parameter is not provided."""

    def __init__(self, message="Number of rows not defined") -> None:
        self.message = message
        super().__init__(self.message)


class FieldInURLException(Exception):
    pass


class SeiDBAPIError(Exception):
    """Exceção customizada para erros na chamada da API do SEI."""

    def __init__(self, status_code: int, detail: str):  # noqa: ANN204
        """Inicializa SeiDBAPIError com um código de status e mensagem de detalhe.

        Args:
            status_code (int): O código de status HTTP indicando o erro.
            detail (str): Uma mensagem detalhada descrevendo o erro.

        """
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"({status_code}) {detail}")

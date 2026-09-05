#!/usr/bin/env python
"""API exceptions."""

from typing import Any

from fastapi import HTTPException


class SolrCommunicationError(Exception):
    """Exception to use when there is an error communicating with Solr."""


class MalformedParameterException(HTTPException):
    """Exceção a ser usada quando houver um erro com os parâmetros."""

    def __init__(
        self, status_code: int = 422, detail: str = "Invalid Parameter"
    ) -> None:
        """Inicializa uma MalformedParameterException com um código de status e uma mensagem de detalhes.

        Parameters:
        status_code (int): O código de status HTTP da exceção. O padrão é 422.
        detail (str): Uma descrição do erro. O padrão é "Parâmetro inválido".
        """
        super().__init__(status_code=status_code, detail=detail)


class ParsedQueryEmptyException(HTTPException):
    """Exceção a ser usada quando houver um erro com os parâmetros."""

    def __init__(self, status_code: int = 204, detail: str = "Documento Vazio") -> None:
        """Inicializa uma ParsedQueryEmptyException com um código de status e uma mensagem de detalhes.

        Parameters:
        status_code (int): O código de status HTTP da exceção. O padrão é 204.
        detail (str): Uma descrição do erro. O padrão é "Documento Vazio".
        """
        super().__init__(status_code=status_code, detail=detail)


class ParsedQueryFieldException(HTTPException):
    """Exceção a ser usada quando houver um erro com os parâmetros."""

    @staticmethod
    def detail(field: str) -> str:
        """Gera uma mensagem de erro indicando que um campo não foi encontrado.

        Parameters:
        field (str): O nome do campo que não foi encontrado.

        Returns:
        str: Uma mensagem de erro formatada indicando que o campo não foi encontrado.
        """
        return f"Field {field} not found"

    def __init__(self, status_code: int = 201, field: str = "") -> None:
        """Inicializa uma ParsedQueryFieldException com um código de status e uma mensagem de detalhes.

        Parameters:
        status_code (int): O código de status HTTP da exceção. O padrão é 201.
        field (str): O nome do campo que não foi encontrado.
        """
        self.detail = self.detail(field)
        super().__init__(status_code=status_code, detail=self.detail)


class ResourceNotFoundException(HTTPException):
    """Exception to use when a Solr index does not cantain an id."""

    @staticmethod
    def detail(resource_name: str) -> str:
        """Gera uma mensagem de erro indicando que um recurso não foi encontrado.

        Parameters:
        resource_name (str): O nome do recurso que não foi encontrado.

        Returns:
        str: Uma mensagem de erro formatada indicando que o recurso não foi encontrado.
        """
        return f"ID: {resource_name} não encontrado"

    def __init__(self, status_code: int = 404, resource_name: str = "Resource") -> None:
        """Inicializa uma ResourceNotFoundException com um código de status e uma mensagem de detalhes.

        Parameters:
        status_code (int): O código de status HTTP da exceção. O padrão é 404.
        resource_name (str): O nome do recurso que não foi encontrado. O padrão é "Resource".
        """
        self.detail = self.detail(resource_name)
        self.resource_name = resource_name
        super().__init__(status_code=status_code, detail=self.detail)


class TableEmbeddingNotFoundException(HTTPException):
    """Exception to use when a Table does not exist in the database."""

    @staticmethod
    def detail(resource_name: str) -> str:
        """Gera uma mensagem de erro indicando que uma tabela de embedding não foi encontrada.

        Parameters:
        resource_name (str): O nome da tabela de embedding que não foi encontrada.

        Returns:
        str: Uma mensagem de erro formatada indicando que a tabela de embedding não foi encontrada.
        """
        return f"Tabela embedding: {resource_name} não encontrado"

    def __init__(self, status_code: int = 404, resource_name: str = "Resource") -> None:
        """Inicializa uma TableEmbeddingNotFoundException com um código de status e uma mensagem de detalhes.

        Parameters:
        status_code (int): O código de status HTTP da exceção. O padrão é 404.
        resource_name (str): O nome da tabela de embedding que não foi encontrada. O padrão é "Resource".
        """
        self.detail = self.detail(resource_name)
        super().__init__(status_code=status_code, detail=self.detail)


class JsonFieldException(HTTPException):
    """Exceção a ser usada quando houver um erro com os parâmetros."""

    def __init__(self, status_code: int = 502, field: str = "") -> None:
        """Inicialize uma JsonFieldException com um código de status e um nome de campo.

        Parameters:
            status_code (int): O código de status HTTP da exceção. O padrão é 502.
            field (str): O nome do campo JSON ausente. O padrão é uma string vazia.
        """
        detail = f"Missing json field {field}"
        super().__init__(status_code=status_code, detail=detail)

    def __str__(self) -> str:
        """Retorna uma representação de string da exceção.

        Returns:
            str: Uma representação de string da exceção.
        """
        return f"{self.detail}"


class SolrException(HTTPException):
    """Exceção para erros relacionados a requisições Solr."""

    def __init__(
        self,
        status_code: int,
        detail: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        """Inicializa uma SolrException com um código de status, detalhes e headers.

        Parameters:
            status_code (int): O código de status HTTP da exceção.
            detail (Any): Detalhes adicionais sobre a exceção.
            headers (Optional[Dict[str, Any]]): Headers para a resposta HTTP.
        """
        super().__init__(status_code=status_code, detail=detail, headers=headers)

    def __str__(self) -> str:
        """Retorna uma representação de string da exceção.

        Returns:
            str: Uma representação de string da exceção.
        """
        return f"{self.detail}"


class SQLAlchemyInsertError(Exception):
    """Custom exception to handle SQLAlchemy insert errors."""

    def __init__(
        self, message: str = "An error occurred during SQLAlchemy insert operation"
    ) -> None:
        """Inicializa uma SQLAlchemyInsertError com uma mensagem de erro.

        Parameters:
            message (str): Mensagem de erro da exceção. "An error occurred during SQLAlchemy insert operation."
        """
        self.message = message
        super().__init__(self.message)


class SQLAlchemySelectError(Exception):
    """Custom exception to handle SQLAlchemy select errors."""

    def __init__(
        self, message: str = "An error occurred during SQLAlchemy select operation"
    ) -> None:
        """Inicializa uma SQLAlchemySelectError com uma mensagem de erro.

        Parameters:
            message (str): Mensagem de erro da exceção. "An error occurred during SQLAlchemy select operation."
        """
        self.message = message
        super().__init__(self.message)


class RowsNotFoundError(Exception):
    """Exceção a linha nao encontrada."""


class FieldInURLError(Exception):
    """Campo em URL com erro."""


class SolrRequestError(Exception):
    """Exceção personalizada para erros relacionados a requisições Solr."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Inicializa uma exce o SolrRequestException.

        Args:
        message (str): Mensagem de erro.
        status_code (Optional[int], optional): C digo de status HTTP. Defaults to None.
        """
        self.status_code = status_code
        super().__init__(message)


class SEIDatabaseConnectionError(Exception):
    """Exceção levantada quando não há banco de dados SEI configurado corretamente."""


class MLTRequestError(Exception):
    """Exceção levantada quando há erro na requisição MLT."""


class CustomParseValueError(Exception):
    """Exceção levantada quando há erro na requisição MLT."""

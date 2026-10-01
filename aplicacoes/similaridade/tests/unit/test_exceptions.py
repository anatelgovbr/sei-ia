"""Tests for the exception classes themselves (constructors/str)."""
import unittest

from api_sei.exception_handling.exceptions import (
    MalformedParameterException,
    ParsedQueryEmptyException,
    ParsedQueryFieldException,
    SolrException,
    SolrRequestError,
    TableEmbeddingNotFoundException,
)


class TestMalformedParameterException(unittest.TestCase):
    def test_defaults(self):
        exc = MalformedParameterException()
        self.assertEqual(exc.status_code, 422)
        self.assertEqual(exc.detail, "Invalid Parameter")

    def test_custom_detail(self):
        exc = MalformedParameterException(status_code=400, detail="bad param")
        self.assertEqual(exc.status_code, 400)
        self.assertEqual(exc.detail, "bad param")


class TestParsedQueryEmptyException(unittest.TestCase):
    def test_defaults(self):
        exc = ParsedQueryEmptyException()
        self.assertEqual(exc.status_code, 204)
        self.assertEqual(exc.detail, "Documento Vazio")


class TestParsedQueryFieldException(unittest.TestCase):
    def test_detail_mentions_field(self):
        exc = ParsedQueryFieldException(field="metadata_x")
        self.assertEqual(exc.status_code, 201)
        self.assertEqual(exc.detail, "Field metadata_x not found")


class TestTableEmbeddingNotFoundException(unittest.TestCase):
    def test_detail_mentions_resource(self):
        exc = TableEmbeddingNotFoundException(resource_name="embd_doc_x")
        self.assertEqual(exc.status_code, 404)
        self.assertEqual(exc.detail, "Tabela embedding: embd_doc_x não encontrado")


class TestSolrException(unittest.TestCase):
    def test_str_returns_detail(self):
        exc = SolrException(status_code=500, detail="falha no solr")
        self.assertEqual(str(exc), "falha no solr")


class TestSolrRequestError(unittest.TestCase):
    def test_stores_status_code(self):
        exc = SolrRequestError("timeout", status_code=504)
        self.assertEqual(exc.status_code, 504)
        self.assertEqual(str(exc), "timeout")

    def test_status_code_defaults_to_none(self):
        exc = SolrRequestError("erro generico")
        self.assertIsNone(exc.status_code)

import unittest

from fastapi import HTTPException
from pydantic import ValidationError

from api_sei.pydantic_models.document_recommenders import (
    RecommendationItemDocument, RecommendationResponseDocument)
from api_sei.pydantic_models.log_recommendation import LogRecommendation
from api_sei.pydantic_models.n_embeddings_recommender import \
    NEmbeddingRecomenderRequest
from api_sei.pydantic_models.process_recommenders import (
    IdField, RecommendationByEmbd, RecommendationByIdProtocoloItem,
    RecommendationByIdProtocoloResponse, RecommendationItem,
    RecommendationResponse)
from api_sei.pydantic_models.solr_mlt import (DebugField, DetailedSolrJson,
                                              DocsItem, GenericSolrJson,
                                              SolrMltConfigModel)


class TestRecommendationDocuments(unittest.TestCase):
    def test_recommendation_item_document(self):
        item_data = {"id": "123", "score": 0.95}
        item = RecommendationItemDocument(**item_data)
        self.assertEqual(item.id, "123")
        self.assertEqual(item.score, 0.95)

        with self.assertRaises(ValidationError) as context:
            RecommendationItemDocument(score=0.95)
        self.assertIn("1 validation error for RecommendationItemDocument", str(context.exception))

    def test_recommendation_response_document(self):
        response_data = {
            "recommendation": [
                {"id": "123", "score": 0.95},
                {"id": "456", "score": 0.85},
            ],
            "debug": {"info": "debug info"},
        }
        response = RecommendationResponseDocument(**response_data)
        self.assertEqual(len(response.recommendation), 2)
        self.assertEqual(response.recommendation[0].id, "123")
        self.assertEqual(response.debug, {"info": "debug info"})

        with self.assertRaises(ValidationError) as context:
            RecommendationResponseDocument(debug={"info": "debug info"})
        self.assertIn(
            "1 validation error for RecommendationResponseDocument", str(context.exception)
        )

        with self.assertRaises(ValidationError) as context:
            RecommendationResponseDocument(recommendation=[{"id": "123", "score": "invalid"}])
        self.assertIn(
            "1 validation error for RecommendationResponseDocument",
            str(context.exception),
            str(context.exception),
        )


class TestLogRecommendation(unittest.TestCase):
    def test_valid_log_recommendation(self):
        data = {
            "id_protocolo_search": 123,
            "id_protocolo_interest": 456,
            "email_user": "test@example.com",
            "created_at": "2022-01-01 12:34:56",
        }
        log_recommendation = LogRecommendation(**data)
        self.assertEqual(log_recommendation.id_protocolo_search, 123)
        self.assertEqual(log_recommendation.id_protocolo_interest, 456)
        self.assertEqual(log_recommendation.email_user, "test@example.com")
        self.assertEqual(log_recommendation.created_at, "2022-01-01 12:34:56")

    def test_invalid_email_format(self):
        data = {
            "id_protocolo_search": 123,
            "id_protocolo_interest": 456,
            "email_user": "invalid_email",
        }
        with self.assertRaises(ValueError) as context:
            LogRecommendation(**data)
        self.assertIn("Invalid email format", str(context.exception))

    def test_invalid_timestamp_format(self):
        data = {
            "id_protocolo_search": 123,
            "id_protocolo_interest": 456,
            "email_user": "test@example.com",
            "created_at": "invalid_timestamp",
        }
        with self.assertRaises(ValueError) as context:
            LogRecommendation(**data)
        self.assertIn(
            "Invalid timestamp format. It should be in the format 'YYYY-MM-DD HH:MM:SS'",
            str(context.exception),
        )


class TestNEmbeddingRecomenderRequest(unittest.TestCase):
    def test_valid_request(self):
        data = {"id_protocolo": 123, "fq": [1, 2, 3], "rows": 10}
        request = NEmbeddingRecomenderRequest(**data)
        self.assertEqual(request.id_protocolo, 123)
        self.assertEqual(request.fq, [1, 2, 3])
        self.assertEqual(request.rows, 10)

    def test_invalid_id_protocolo(self):
        data = {"id_protocolo": None, "fq": [1, 2, 3], "rows": 10}
        with self.assertRaises(ValidationError) as context:
            NEmbeddingRecomenderRequest(**data)
        self.assertIn("none is not an allowed value", str(context.exception.errors()))

    def test_invalid_fq(self):
        data = {"id_protocolo": 123, "fq": [1, "invalid", 3], "rows": 10}
        with self.assertRaises(ValidationError) as context:
            NEmbeddingRecomenderRequest(**data)
        self.assertIn("value is not a valid integer", str(context.exception.errors()))

    def test_invalid_rows(self):
        data = {"id_protocolo": 123, "fq": [1, 2, 3], "rows": 0}
        with self.assertRaises(HTTPException) as context:
            NEmbeddingRecomenderRequest(**data)
        self.assertIn(
            "O campo 'rows' deve ser um número inteiro positivo.", str(context.exception.detail)
        )


class TestRecommendationClasses(unittest.TestCase):
    def test_recommendation_item(self):
        data = {"nr_processo": "123", "score": 0.95}
        item = RecommendationItem(**data)
        self.assertEqual(item.id, "123")
        self.assertEqual(item.score, 0.95)

    def test_recommendation_response(self):
        data = {
            "recommendation": [{"nr_processo": "123", "score": 0.95}],
            "debug": {"info": "debug info"},
        }
        response = RecommendationResponse(**data)
        self.assertEqual(len(response.recommendation), 1)
        self.assertEqual(response.recommendation[0].id, "123")
        self.assertEqual(response.debug, {"info": "debug info"})

    def test_recommendation_by_id_protocolo_item(self):
        data = {"id_protocolo": "123", "score": 0.95}
        item = RecommendationByIdProtocoloItem(**data)
        self.assertEqual(item.id, "123")
        self.assertEqual(item.score, 0.95)

    def test_recommendation_by_id_protocolo_response(self):
        data = {
            "recommendation": [{"id_protocolo": "123", "score": 0.95}],
            "debug": {"info": "debug info"},
        }
        response = RecommendationByIdProtocoloResponse(**data)
        self.assertEqual(len(response.recommendation), 1)
        self.assertEqual(response.recommendation[0].id, "123")
        self.assertEqual(response.debug, {"info": "debug info"})

    def test_id_field_enum(self):
        self.assertEqual(IdField.id_process, "id_process")
        self.assertEqual(IdField.id_protocolo, "id_protocolo")
        self.assertEqual(IdField.id_protocolo_processo, "id_protocolo_processo")

    def test_recommendation_by_embd(self):
        data = {"id_protocolo": "123"}
        recommendation = RecommendationByEmbd(**data)
        self.assertEqual(recommendation.id, "123")


class TestSolrMltConfigModel(unittest.TestCase):
    def test_valid_solr_mlt_config_model(self):
        data = {
            "maxqt": 25,
            "fields": ["field1", "field2"],
            "url": "http://example.com/solr",
        }
        solr_mlt_config = SolrMltConfigModel(**data)
        self.assertEqual(solr_mlt_config.maxqt, 25)
        self.assertEqual(solr_mlt_config.fields, ["field1", "field2"])
        self.assertEqual(solr_mlt_config.url, "http://example.com/solr")

    def test_invalid_solr_mlt_config_model(self):
        # Test missing required fields
        with self.assertRaises(ValidationError) as context:
            SolrMltConfigModel()
        self.assertIn("2 validation errors for SolrMltConfigModel", str(context.exception))

        # Test invalid extraction method
        data = {
            "maxqt": 25,
            "fields": ["field1", "field2"],
            "url": "http://example.com/solr",
            "extraction_method": "invalid_method",
        }
        with self.assertRaises(ValidationError) as context:
            SolrMltConfigModel(**data)
        self.assertIn("value is not a valid enumeration member", str(context.exception))


class TestDebugField(unittest.TestCase):
    def test_valid_debug_field(self):
        data = {
            "explain": {"field1": "explanation"},
            "parsedquery": "example parsed query",
        }
        debug_field = DebugField(**data)
        self.assertEqual(debug_field.explain, {"field1": "explanation"})
        self.assertEqual(debug_field.parsedquery, "example parsed query")


class TestDocsItem(unittest.TestCase):
    def test_valid_docs_item(self):
        data = {
            "id_protocolo": "123",
            "score": 0.95,
        }
        docs_item = DocsItem(**data)
        self.assertEqual(docs_item.id_protocolo, "123")
        self.assertEqual(docs_item.score, 0.95)


class TestDetailedSolrJson(unittest.TestCase):
    def test_valid_detailed_solr_json(self):
        data = {
            "response": {"docs": [{"id_protocolo": "123", "score": 0.95}]},
            "debug": {"explain": {"field1": "explanation"}, "parsedquery": "example parsed query"},
            "interesting_terms": [],
        }
        detailed_solr_json = DetailedSolrJson(**data)
        self.assertEqual(len(detailed_solr_json.response.docs), 1)
        self.assertEqual(detailed_solr_json.debug.explain, {"field1": "explanation"})
        self.assertEqual(detailed_solr_json.debug.parsedquery, "example parsed query")


class TestGenericSolrJson(unittest.TestCase):
    def test_valid_generic_solr_json(self):
        data = {
            "response": {"docs": [{"field1": "value1", "field2": "value2"}]},
            "debug": {"explain": {"field1": "explanation"}, "parsedquery": "example parsed query"},
        }
        generic_solr_json = GenericSolrJson(**data)
        self.assertEqual(len(generic_solr_json.response.docs), 1)
        self.assertEqual(generic_solr_json.debug.explain, {"field1": "explanation"})
        self.assertEqual(generic_solr_json.debug.parsedquery, "example parsed query")



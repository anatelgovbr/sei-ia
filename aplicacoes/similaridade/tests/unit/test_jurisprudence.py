import pytest
from pydantic import ValidationError
from api_sei.pydantic_models.jurisprudence import SolrJurisprudenceConfig, FoundIdsDocs

def test_solr_jurisprudence_config_valid():
    config = SolrJurisprudenceConfig(
        debug_query="true",
        wt="json",
        mlt_interesting_terms="details",
        rows=10,
        fl="id,score",
        mindf=1,
        mintf=1,
        fq="type:case"
    )
    assert config.debug_query == "true"
    assert config.wt == "json"
    assert config.mlt_interesting_terms == "details"
    assert config.rows == 10
    assert config.fl == "id,score"
    assert config.mindf == 1
    assert config.mintf == 1
    assert config.fq == "type:case"

def test_solr_jurisprudence_config_invalid():
    with pytest.raises(ValidationError):
        SolrJurisprudenceConfig(
            debug_query="true",
            wt="json",
            mlt_interesting_terms="details",
            rows="ten",  # should be an integer
            fl="id,score",
            mindf=1,
            mintf=1,
            fq="type:case"
        )

def test_found_ids_docs_valid():
    found_ids_docs = FoundIdsDocs(
        id_docs_found={"doc1", "doc2"},
        id_docs_not_found={"doc3"}
    )
    assert found_ids_docs.id_docs_found == {"doc1", "doc2"}
    assert found_ids_docs.id_docs_not_found == {"doc3"}


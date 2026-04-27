import logging
from datetime import datetime

from api_sei.db_models.get_content_lazy import get_tokenized_docs
from api_sei.db_models.jurisprudence import SolrJurisprudence
from api_sei.db_models.solr_knn import build_filter
from api_sei.envs import BASE_URL_JURISPRUDENCE
from api_sei.exception_handling.exceptions import ParsedQueryEmptyException
from api_sei.repository.recommendation import add_mlt_document_recommendation
from api_sei.resources.bm25 import extract_parsedquery, get_doc_score
from api_sei.resources.tokenizers_and_filters import solr_preprocessing
from api_sei.services.citations_search import add_citations
from api_sei.services.jurisprudence_search import (
    get_parsedquery_from_string,
    merge_unweighted_parsed_queries,
)

logger = logging.getLogger(__name__)
solr_jurisprudence = SolrJurisprudence()


def doc2doc_search(
    list_id_doc: list[int],
    list_type_id_doc: list[int],
    id_user: int,
    rows: int,
    text: str = "",
    include_citations: bool = False,
    text_weight: float = 0.5,
    normalized: bool = False,
    fq: list[int] = None,
    requested_at=None,
):
    if fq is None:
        fq = []
    if requested_at is None:
        requested_at = datetime.now()
    logger.debug("entrou em doc2doc_search")
    compound_fq = build_filter(
        "id_document", fq if fq else None, list_id_doc if list_id_doc else None
    )
    logger.debug("chamou build_filter")
    if list_type_id_doc:
        list_type_id_doc_str = f"id_type_document:( {' '.join([str(value) for value in list_type_id_doc])} )"
        compound_fq = f"{list_type_id_doc_str} AND {compound_fq}"

    found_id_docs = solr_jurisprudence.check_has_id_documents(list_id_doc)
    logger.debug("chamou check_has_id_documents")

    if found_id_docs.id_docs_not_found:
        list_parsedqueries_not_found = [
            extract_parsedquery(
                BASE_URL_JURISPRUDENCE, "content", doc["content"], max_tokens=25
            )
            for doc in get_tokenized_docs(found_id_docs.id_docs_not_found)
        ]
        logger.debug("chamou extract_parsedquery e get_tokenized_docs")
    else:
        list_parsedqueries_not_found = []

    if found_id_docs.id_docs_found:
        list_parsedqueries_found = [
            solr_jurisprudence.get_solr_using_debug_query(id_document)
            for id_document in found_id_docs.id_docs_found
        ]
        logger.debug("chamou get_solr_using_debug_query")
    else:
        list_parsedqueries_found = []

    parsedquery = " ".join(list_parsedqueries_not_found + list_parsedqueries_found)
    # Inclui texto, se houver
    if text.strip() and (not parsedquery.strip()):
        parsedquery = get_parsedquery_from_string(text)
        logger.debug("chamou get_parsedquery_from_string")
    elif text.strip():
        parsedquery = merge_unweighted_parsed_queries(
            [parsedquery, get_parsedquery_from_string(text)],
            [1 - text_weight, text_weight],
        )
        logger.debug("chamou merge_unweighted_parsed_queries")

    if normalized and parsedquery.strip():
        tokens = []
        if found_id_docs.id_docs_not_found:
            for doc in get_tokenized_docs(found_id_docs.id_docs_not_found):
                tokens.extend(doc["content"])
            logger.debug("chamou get_tokenized_docs")
        if found_id_docs.id_docs_found:
            for doc in solr_jurisprudence.get_docs(
                found_id_docs.id_docs_found, fl="id_document,content"
            ):
                tokens.extend(solr_preprocessing(doc["content"]))
            logger.debug("chamou get_docs e solr_preprocessing")
        if text:
            tokens.extend(solr_preprocessing(text))
            logger.debug("chamou solr_preprocessing")
        normalize_value = get_doc_score(
            BASE_URL_JURISPRUDENCE, parsedquery, {"content": tokens}
        )
        logger.debug("chamou get_doc_score")
    else:
        normalize_value = 1

    # Obtém a lista MLT da parsed query fornecida
    try:
        json_doc_list = solr_jurisprudence.get_solr_parsedquery(
            parsedquery=parsedquery,
            rows=rows,
            fq=compound_fq,
            normalize_value=normalize_value,
        )
    except ParsedQueryEmptyException:
        # Retorna lista vazia quando não há query válida
        json_doc_list = []

    # Inclui citações, caso solicitado
    if include_citations:
        json_doc_list = add_citations(json_doc_list)
        logger.debug("chamou add_citations")

    id_recommendation = add_mlt_document_recommendation(
        list_id_doc=list_id_doc,
        list_type_id_doc=list_type_id_doc,
        rows=rows,
        text=text,
        include_citations=include_citations,
        text_weight=text_weight,
        normalized=normalized,
        fq=fq,
        recommendation={"recommendation": json_doc_list},
        requested_at=requested_at,
        id_user=id_user,
    )
    logger.debug("chamou add_mlt_document_recommendation")
    return {"id_recommendation": id_recommendation, "recommendation": json_doc_list}

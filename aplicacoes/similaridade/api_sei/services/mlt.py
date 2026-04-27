import logging
import warnings
from datetime import datetime

from requests.exceptions import ConnectionError, JSONDecodeError, Timeout

from api_sei.db_models.solr_mlt import SolrMlt
from api_sei.db_models.solr_select import SolrRequests
from api_sei.envs import SOLR_ADDRESS, SOLR_MLT_PROCESS_CORE, auth
from api_sei.exception_handling.exceptions import SolrCommunicationError
from api_sei.pydantic_models.process_recommenders import IdField
from api_sei.pydantic_models.solr_mlt import ExtractionMethodEnum, SolrMltConfigModel
from api_sei.repository.recommendation import add_process_weighted_mlt_recommendation
from api_sei.resources.custom_parsedquery import get_all_str_search_fields
from api_sei.utils import replace_nan

logger = logging.getLogger(__name__)


def mlt_process_recommendations_service(
    id_value,
    rows,
    fq,
    normalized,
    mlt_fields=None,
    mintf=2,
    mindf=5,
    boost=False,
    mlt_qf=None,
    return_service=False,
    id_field="id_protocolo",
):
    """Mlt process recommendations"""
    url = f"{SOLR_ADDRESS}/solr/{SOLR_MLT_PROCESS_CORE}"
    if mlt_fields is None:
        mlt_fields = get_all_str_search_fields(id_value, url, id_field=id_field)

    solr_mlt_config = SolrMltConfigModel(
        mintf=mintf,
        mindf=mindf,
        url=url,
        fields=mlt_fields,
        id_field=IdField(id_field),
        mlt_qf=mlt_qf,
        boost=boost,
        normalized=normalized,
        extra_fields=["id_process", "protocolo_formatado"],
    )
    solr_mlt_service = SolrMlt(solr_mlt_config)

    try:
        response_mlt = solr_mlt_service.mlt(id_value, rows=rows, fq=fq)
    except (ConnectionError, JSONDecodeError, Timeout) as exc:
        logger.error(exc, exc_info=True)
        raise SolrCommunicationError from exc

    if return_service:
        return response_mlt, solr_mlt_service
    return response_mlt


def wmlt_process_recommendations_service(
    id_value,
    rows,
    fq,
    normalized=True,
    debug=False,
    return_service=False,
    parsedquery_field="fulltext_parsedquery_t",
    id_field="id_protocolo",
    extraction_method=ExtractionMethodEnum.solr,
    id_user=None,
    requested_at=None,
):
    """Weighted mlt process recommendations"""
    if requested_at is None:
        requested_at = datetime.now()
    if normalized is False:
        warnings.warn("wmlt is always normalized", stacklevel=2)

    url = f"{SOLR_ADDRESS}/solr/{SOLR_MLT_PROCESS_CORE}"

    solr_mlt_config = SolrMltConfigModel(
        url=url,
        fields=[],
        id_field=IdField(id_field),
        normalized=normalized,
        custom_query=True,
        debug=debug,
        extra_fields=["id_process", "protocolo_formatado"],
        parsedquery_field=parsedquery_field,
        extraction_method=extraction_method,
    )
    solr_mlt_service = SolrMlt(solr_mlt_config)

    try:
        response_mlt = solr_mlt_service.mlt(id_value, rows=rows, fq=fq)
        response_mlt = replace_nan(response_mlt)
    except JSONDecodeError as exc:
        logger.error(exc, exc_info=True)
        raise SolrCommunicationError from exc

    id = add_process_weighted_mlt_recommendation(
        id_protocolo=id_value,
        id_user=id_user,
        rows=rows,
        parsedquery_field=parsedquery_field,
        id_field=id_field,
        fq=fq,
        debug=debug,
        extraction_method=extraction_method,
        recommendation=response_mlt,
        requested_at=requested_at,
    )
    response_mlt["id"] = id
    if return_service:
        return response_mlt, solr_mlt_service
    return response_mlt


def has_id_protocolo_service(id_protocolo: int):
    ret = SolrRequests.get(
        url=f"{SOLR_ADDRESS}/solr/{SOLR_MLT_PROCESS_CORE}/select",
        params={"q": f"id_protocolo:{id_protocolo}"},
        nested_fields=["response", "numFound"],
        rows=0,
        auth=auth,
    )
    return bool(ret)

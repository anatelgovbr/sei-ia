"""Métodos e classes para lidar com solicitações ao Solr."""

import logging
import time
from typing import Any

from api_sei.db_models.solr_knn import build_filter
from api_sei.db_models.solr_select import SolrRequests
from api_sei.envs import auth
from api_sei.exception_handling.exceptions import (
    MalformedParameterException,
    ResourceNotFoundException,
)
from api_sei.pydantic_models.solr_mlt import (
    DetailedSolrJson,
    ExtractionMethodEnum,
    SolrMltConfigModel,
)
from api_sei.resources.bm25 import find_field, find_terms, find_weights
from api_sei.resources.custom_parsedquery import (
    FasterCustomParsedQuery,
    LDAExtractCustomParsedQuery,
    ManualExtractCustomParsedQuery,
    read_fulltext_sections_fields,
)
from api_sei.utils import response_normalization

logger = logging.getLogger(__name__)


def process_mlt_qf(mlt_qf: str) -> str:
    """Process the `mlt_qf` by removing parentheses, replacing "+" with "^", and joining the resulting with a space.

    Parameters:
        mlt_qf (str): The input string to be processed.

    Returns:
        str: The processed string with parentheses removed, "+" replaced with "^", and strings joined with a space.
    """
    return " ".join(
        mlt_qf.replace("(", "").replace(")", "").replace("^+", "^").split("+")
    )


class SolrMlt:
    """Classe que lida com as requisições MLT (More Like This) ao Solr."""

    def __init__(self, config: SolrMltConfigModel) -> None:
        """Inicializa o objeto SolrMlt com uma configuração específica.

        Parameters:
            config (SolrMltConfigModel): O modelo de configuração do Solr MLT.
        """
        self.config = config

    def _build_fl(self) -> str:
        """Constrói a string de campos a serem retornados pela consulta Solr.

        Returns:
            str: A string de campos a serem retornados.
        """
        list_score = [self.config.id_field, "score"]
        return ",".join(list_score + self.config.extra_fields)

    def _build_initial_query(self, solr_doc_id: str) -> str:
        """Constrói a query inicial para a consulta MLT no Solr.

        Parameters:
            solr_doc_id (str): O ID do documento Solr.

        Returns:
            str: A query inicial da consulta MLT.
        """
        fields = ",".join(self.config.fields)
        url = self.config.url.rstrip("/")
        return f"{url}/mlt?q={self.config.id_field}:{solr_doc_id}&fl={self._build_fl()}&mlt.fl={fields}"

    def _add_mlt_filters(self, query: str) -> str:
        """Adiciona os filtros MLT (More Like This) à query.

        Parameters:
            query (str): A query original.

        Returns:
            str: A query com os filtros MLT adicionados.
        """
        if self.config.maxdfpct is not None:
            query = query + f"&mlt.maxdfpct={self.config.maxdfpct}"
        if self.config.maxqt != 25:  # noqa: PLR2004
            query = query + f"&mlt.maxqt={self.config.maxqt}"
        if self.config.mintf != 2:  # noqa: PLR2004
            query = query + f"&mlt.mintf={self.config.mintf}"
        if self.config.mindf != 5:  # noqa: PLR2004
            query = query + f"&mlt.mindf={self.config.mindf}"
        if self.config.minwl is not None:
            query = query + f"&mlt.minwl={self.config.minwl}"
        if self.config.maxwl is not None:
            query = query + f"&mlt.maxwl={self.config.maxwl}"

        return query

    def _add_mlt_weights(self, query: str) -> str:
        """Adiciona os pesos MLT à query.

        Parameters:
            query (str): A query original.

        Returns:
            str: A query com os pesos MLT adicionados.
        """
        if self.config.boost:
            query = query + "&mlt.boost=true"
        if self.config.mlt_qf is not None:
            query = query + f"&mlt.qf={process_mlt_qf(self.config.mlt_qf)}"

        return query

    def _add_select_filters(self, query: str, pfq: str | None, nfq: str | None) -> str:
        """Adiciona os filtros de seleção à query.

        Parameters:
            query (str): A query original.
            pfq (str, opcional): O filtro positivo.
            nfq (str, opcional): O filtro negativo.

        Returns:
            str: A query com os filtros de seleção adicionados.
        """
        if (pfq is not None) or (nfq is not None):
            query = query + f"&fq={build_filter(self.config.id_field, pfq, nfq)}"
        return query

    def _build_mlt_query(
        self, solr_doc_id: str, pfq: str | None, nfq: str | None
    ) -> str:
        """Cria a query MLT baseada nos parâmetros de configuração.

        Parameters:
            solr_doc_id (str): O ID do documento Solr.
            pfq (str, opcional): O filtro positivo.
            nfq (str, opcional): O filtro negativo.

        Returns:
            str: A query MLT completa.
        """
        """Creates mlt query based on configuration parameters"""
        query = self._build_initial_query(solr_doc_id)
        query = self._add_mlt_filters(query)
        query = self._add_mlt_weights(query)
        query = self._add_select_filters(query, pfq, nfq)
        return self._add_debug(query)

    def _build_like_query(self, solr_doc_id: str) -> str:
        """Cria uma like-query baseada nos parâmetros de configuração.

        Parameters:
            solr_doc_id (str): O ID do documento Solr.

        Returns:
            str: A query like-query completa.
        """
        query = self._build_initial_query(solr_doc_id)
        query = self._add_mlt_filters(query)
        return query + "&mlt.boost=true&wt=json&mlt.interesting_terms=details"

    def _build_more_query(
        self, parsedquery: str, pfq: str | None, nfq: str | None
    ) -> str:
        """Cria uma more-query baseada nos parâmetros de configuração.

        Parameters:
            parsedquery (str): A query parseada.
            pfq (str, opcional): O filtro positivo.
            nfq (str, opcional): O filtro negativo.

        Returns:
            str: A query more-query completa.
        """
        url = self.config.url.rstrip("/")
        parsedquery = parsedquery or "*:*"
        query = (
            f"{url}/select?fl={self._build_fl()}&indent=true&q.op=OR&q={parsedquery}"
        )
        query = self._add_select_filters(query, pfq, nfq)
        return self._add_debug(query)

    def _build_more_json(
        self, parsedquery: str, rows: int, pfq: str | None, nfq: str | None
    ) -> dict[str, Any]:
        """Cria uma estrutura JSON para a consulta more-query.

        Parameters:
            parsedquery (str): A query parseada.
            rows (int): O número de linhas a serem retornadas.
            pfq (str, opcional): O filtro positivo.
            nfq (str, opcional): O filtro negativo.

        Returns:
            dict: Um dicionário JSON para a consulta more-query.
        """
        jsn = {
            "params": {
                "fl": self._build_fl(),
                "rows": rows,
                "q": parsedquery,
                "fq": build_filter(self.config.id_field, pfq, nfq),
            }
        }
        if self.config.debug:
            jsn["params"]["debug"] = "all"
        return jsn

    @staticmethod
    def interestingterms_to_parsedquery(it: list[Any]) -> str:
        """Converte os termos interessantes em uma query parseada.

        Parameters:
            it (List[Any]): Lista de termos interessantes.

        Returns:
            str: A query parseada gerada a partir dos termos interessantes.
        """
        return " ".join([f"{it[i]}^{it[i + 1]!s}" for i in list(range(len(it)))[0::2]])

    def process_parsedquery(self, parsedquery: str) -> str:
        """Processa a query parseada, ajustando os termos e pesos de acordo com a configuração.

        Parameters:
            parsedquery (str): A query parseada original.

        Returns:
            str: A query parseada processada.
        """
        parsedquery = parsedquery.replace("(", "").replace(")", "")

        if self.config.mlt_qf is not None:
            mlt_qf = process_mlt_qf(self.config.mlt_qf)
            field_values = find_terms(mlt_qf)
            field_weights = find_weights(mlt_qf)
            term_values = find_terms(parsedquery)
            term_weights = find_weights(parsedquery)
            new_term_weights = []
            for t, w in zip(term_values, term_weights, strict=False):
                f = find_field(t)
                b = 1
                if f in field_values:
                    b = field_weights[field_values.index(f)]

                if self.config.boost:
                    new_term_weights.append(w * b)
                else:
                    new_term_weights.append(b)

            parsedquery = " ".join(
                [
                    f"{t}^{w}"
                    for t, w in zip(term_values, new_term_weights, strict=False)
                ]
            )
        return parsedquery

    def _add_debug(self, query: str) -> str:
        """Adiciona a opção de debug à query se necessário.

        Parameters:
            query (str): A query original.

        Returns:
            str: A query com a opção de debug adicionada.
        """
        if self.config.debug:
            query += "&debug_query=on&wt=json"
        return query

    def _mlt_request(self, solr_doc_id, rows, pfq, nfq, request_type):
        if request_type == "indirect":
            like_q = self._build_like_query(solr_doc_id)
            like_start = time.time()
            solr_debug = SolrRequests.get(url=like_q, rows=0, auth=auth)

            like_end = time.time()
            logger.info(f"like query time (s): {like_end - like_start!s}")

            solr_debug = DetailedSolrJson(**solr_debug).dict()

            # parsedquery = solr_debug["debug"]["parsedquery"]

            parsedquery = self.interestingterms_to_parsedquery(
                solr_debug["interesting_terms"]
            )

            parsedquery = self.process_parsedquery(parsedquery)

            more_q = self._build_more_query(parsedquery, pfq, nfq)

            more_start = time.time()
            solr_response = SolrRequests.get(url=more_q, rows=rows, auth=auth)
            more_end = time.time()
            logger.info(f"more query time (s): {more_end - more_start!s}")

            solr_response = DetailedSolrJson(**solr_response).dict()

        elif request_type == "direct":
            mlt_q = self._build_mlt_query(solr_doc_id, pfq, nfq)
            solr_response = SolrRequests.get(url=mlt_q, rows=rows, auth=auth)
            solr_response = DetailedSolrJson(**solr_response).dict()

        elif request_type == "custom":
            url = self.config.url.rstrip("/")

            fulltext_fields, sections_fields = read_fulltext_sections_fields()

            try:
                if self.config.parsedquery_field == "sections_parsedquery_t":
                    faster_custom_parsed_query = FasterCustomParsedQuery(
                        solr_doc_id, ignore_fields=fulltext_fields
                    )
                    parsedquery = faster_custom_parsed_query.get_parsedquery(
                        ignore_fields=fulltext_fields
                    )
                elif self.config.extraction_method == ExtractionMethodEnum.bm25:
                    bm25_custom_parsed_query = ManualExtractCustomParsedQuery(
                        solr_doc_id, ignore_fields=sections_fields
                    )
                    parsedquery = bm25_custom_parsed_query.get_parsedquery(
                        ignore_fields=sections_fields
                    )
                elif self.config.extraction_method == ExtractionMethodEnum.lda:
                    lda_custom_parsed_query = LDAExtractCustomParsedQuery(
                        solr_doc_id, ignore_fields=sections_fields
                    )
                    parsedquery = lda_custom_parsed_query.get_parsedquery(
                        ignore_fields=sections_fields
                    )
                elif self.config.extraction_method == ExtractionMethodEnum.solr:
                    faster_custom_parsed_query = FasterCustomParsedQuery(
                        solr_doc_id, ignore_fields=sections_fields
                    )
                    parsedquery = faster_custom_parsed_query.get_parsedquery(
                        ignore_fields=sections_fields
                    )
                else:
                    raise MalformedParameterException(
                        status_code=422, detail=self.config.extraction_method
                    )
            except Exception as e:
                logger.exception(e, exc_info=True)
                raise e

            jsn = self._build_more_json(parsedquery, rows, pfq, nfq)

            solr_response = SolrRequests.post(
                url=f"{url}/select", payload=jsn, auth=auth
            )

        else:
            raise Exception(f"Unknown request type {request_type}")

        return solr_response

    def mlt(self, solr_doc_id, rows=10, fq=None):
        """Handles the mlt request and the parsing of the response"""
        logger.info(solr_doc_id)

        solr_response = self._mlt_request(
            solr_doc_id=solr_doc_id,
            rows=rows + 1,
            pfq=fq,
            nfq=None,
            request_type=("custom" if self.config.custom_query else "indirect"),
        )

        response_docs = solr_response["response"]["docs"]

        id_not_found = (len(fq) > len(response_docs)) if fq else False
        if id_not_found:
            missing_ids = ",".join(
                list(
                    set(map(str, fq))
                    - {str(d[self.config.id_field]) for d in response_docs}
                )
            )
            # raise ResourceNotFoundException(resource_name=missing_ids)
            logger.warning("%s not found", missing_ids)

        recommendation = {
            "recommendation": [
                {"id": doc[self.config.id_field], **doc} for doc in response_docs
            ]
        }

        if self.config.normalized:
            ref_score = recommendation["recommendation"][0]["score"]
            recommendation = response_normalization(recommendation, ref_score)

        if self.config.debug:
            recommendation["debug"] = {
                "parsedquery": solr_response["debug"]["parsedquery"],
                "explain": {
                    k: v.split("\n")
                    for k, v in solr_response["debug"]["explain"].items()
                },
            }

        # Busca e remove o processo solr_doc_id ("ele próprio") da lista de recomendação
        # ou, caso solr_doc_id não esteja na lista de recomendação, remove último elemento dessa lista
        no_auto_recommendation = [
            r for r in recommendation["recommendation"] if r["id"] != solr_doc_id
        ]
        if len(no_auto_recommendation) < len(
            recommendation["recommendation"]
        ):  # solr_doc_id foi achado e removido da recomendação?
            recommendation["recommendation"] = (
                no_auto_recommendation  # então atualiza a lista de recomendação
            )
        else:  # solr_doc_id NÃO foi achado na lista de recomendação retornada
            recommendation["recommendation"] = recommendation["recommendation"][
                :-1
            ]  # remove arbitrariamente o último elemento da lista

        return recommendation

    def find(self, solr_doc_id):
        """Finds vector for one specific doc id"""
        url = self.config.url.rstrip("/")

        response_docs = SolrRequests.select_raw(
            f"{url}/select?q={self.config.id_field}:{solr_doc_id}&fl={self._build_fl()}",
            nested_fields=["response", "docs"],
            auth=auth,
        )
        if len(response_docs) < 1:
            logger.error(f"Solr did not find {solr_doc_id}")
            raise ResourceNotFoundException(resource_name=solr_doc_id)

        doc = response_docs[0]

        return {"id": doc[self.config.id_field], **doc}

    def find_many(self, solr_doc_ids):
        url = self.config.url.rstrip("/")

        rows = len(solr_doc_ids)

        response_docs = SolrRequests.get(
            f"{url}/select?q={self.config.id_field}:({' '.join(map(str, solr_doc_ids))})&fl={self._build_fl()}",
            nested_fields=["response", "docs"],
            rows=rows,
            auth=auth,
        )

        if len(response_docs) < len(solr_doc_ids):
            missing_ids = ",".join(
                list(
                    set(map(str, solr_doc_ids))
                    - {str(d[self.config.id_field]) for d in response_docs}
                )
            )
            logger.error(f"Solr did not find {missing_ids}")
            raise ResourceNotFoundException(resource_name=missing_ids)

        return response_docs

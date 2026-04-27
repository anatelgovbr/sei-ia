"""handles knn requests to solr."""

import logging

from requests.exceptions import ConnectionError, JSONDecodeError, Timeout

from api_sei.db_models.solr_select import SolrRequests
from api_sei.exception_handling.exceptions import (
    ResourceNotFoundException,
    SolrCommunicationError,
)
from api_sei.pydantic_models.solr_knn import SolrKnnConfigModel

logger = logging.getLogger(__name__)


def build_filter(id_field: str, pfq: list, nfq: list) -> str:
    """Builds a filter query string based on the provided parameters.

    Args:
        id_field (str): The name of the field to filter on.
        pfq (list): A list of values to include in the positive filter query.
        nfq (list): A list of values to include in the negative filter query.

    Returns:
        str: The filter query string.

    The function builds a filter query string based on the provided parameters. It takes three arguments:
    - `id_field` (str): The name of the field to filter on.
    - `pfq` (list): A list of values to include in the positive filter query.
    - `nfq` (list): A list of values to include in the negative filter query.

    The function first initializes an empty list called `select_ids`. It then checks if `pfq` is not None. If it is not None,
    it appends a string to `select_ids` in the format `'{id_field}:({" ".join(map(str,pfq))})'`. If `pfq` is None, it
    appends a string to `select_ids` in the format `'{id_field}:*'`.

    Next, the function checks if `nfq` is not None. If it is not None, it appends a string to `select_ids` in the format
    `'-{id_field}:({" ".join(map(str,nfq))})'`.

    Finally, the function joins all the strings in `select_ids` with the 'AND' operator and returns the resulting filter
    query string.

    Example usage:
    ```
    filter_query = build_filter('id_field', [1, 2, 3], [4, 5, 6])
    print(filter_query)
    # Output: 'id_field:(1 2 3) AND -id_field:(4 5 6)'
    ```
    """
    select_ids = []
    if pfq is not None:
        select_ids.append("{}:( {} )".format(id_field, " ".join(map(str, pfq))))
    else:
        select_ids.append(f"{id_field}:*")
    if nfq is not None:
        select_ids.append("-{}:( {} )".format(id_field, " ".join(map(str, nfq))))

    return " AND ".join(select_ids)


class SolrKnn:
    """handles knn requests to solr"""

    def __init__(self, config: SolrKnnConfigModel):
        self.config = config

    def _build_filter(self, pfq, nfq):
        return build_filter(self.config.id_field, pfq, nfq)

    def _build_query(
        self,
        search_vector: str,
        rows: int,
        pfq: list | None = None,
        nfq: list | None = None,
    ) -> str:
        """Builds a query for a nearest neighbors (knn) search in Solr.

        Args:
            search_vector (str): The search vector to find nearest neighbors for.
            rows (int): The number of rows to return in the result.
            pfq (Optional[List[int]]): A list of positive filter query ids.
            nfq (Optional[List[int]]): A list of negative filter query ids.

        Returns:
            str: The constructed query string for the Solr knn search.

        """
        search_vector = str(search_vector)
        group_results = self.config.group_results
        field = self.config.field
        id_field = self.config.id_field
        url = self.config.url.rstrip("/")
        topk = 1000000  # >= index size

        select_ids = self._build_filter(pfq, nfq)

        # query = '%s/select?fl=%s,score&q=%s&rq={!rerank reRankQuery=$rqq reRankWeight=1}&rqq={!knn f=%s topK=%s}%s&rows=%s' % (
        #     url, id_field, select_ids, field, topk, search_vector, rows)

        query = (
            f"{url}/select?fl={id_field},score&q={{!knn f={field} topK={topk}}}",
            f"{search_vector}&rows={rows}&fq={select_ids}",
        )

        if group_results:
            query += f"&group=true&group.field={id_field}"

        return query

    def _get_request(
        self,
        search_vector: str,
        rows: int,
        pfq: list | None = None,
        nfq: list | None = None,
    ) -> list:
        """Sends a GET request to the Solr server to retrieve the nearest neighbors for a given search vector.

        Args:
            search_vector (str): The search vector to find nearest neighbors for.
            rows (int): The number of rows to return in the result.
            pfq (Optional[List[int]]): A list of positive filter query ids.
            nfq (Optional[List[int]]): A list of negative filter query ids.

        Returns:
            requests.Response: The response object containing the result of the Solr request.

        """
        url = self._build_query(search_vector, rows, pfq=pfq, nfq=nfq)

        return SolrRequests().select(url=url, timeout=60)

    def _build_json(self, search_vector, rows, pfq=None, nfq=None):
        search_vector = str(search_vector)
        field = self.config.field
        group_results = self.config.group_results
        id_field = self.config.id_field
        topk = 1000000  # >= index size

        select_ids = self._build_filter(pfq, nfq)

        jsn = {
            "params": {
                "fl": f"{id_field},score",
                "rows": rows,
                "q": f"{{!knn f={field} topK={topk}}}{search_vector}",
                "fq": select_ids,
            }
        }

        # jsn = {
        #     "params":{
        #         "fl": "%s,score" % (id_field),
        #         "rows": rows,
        #         "q": select_ids,
        #         "rq":'{!rerank reRankQuery=$rqq reRankWeight=1}',
        #         "rqq":'{!knn f=%s topK=%s}%s' % (field, topk, search_vector),
        #     }
        # }

        if group_results:
            jsn["params"]["group"] = "true"
            jsn["params"]["group.field"] = f"{id_field}"

        return jsn

    def _post_request(self, search_vector, rows, pfq=None, nfq=None):
        url = self.config.url.rstrip("/")
        jsn = self._build_json(search_vector, rows, pfq=pfq, nfq=nfq)

        return SolrRequests().post(url=f"{url}/select", payload=jsn, timeout=60)

    def find(self, solr_doc_id):
        """Finds vector for one specific doc id"""
        field = self.config.field
        id_field = self.config.id_field
        url = self.config.url.rstrip("/")

        response_docs = SolrRequests().select(
            url=f"{url}/select?q={id_field}:{solr_doc_id}",
            nested_fields=["response", "docs"],
            timeout=60,
        )

        if len(response_docs) < 1:
            raise ResourceNotFoundException(resource_name=solr_doc_id)

        vector = response_docs[0][field]

        vector = [float(x) for x in vector]

        return vector

    def knn(self, search_vector, solr_doc_id="", rows=10, fq=None):
        """Handles the knn request and the parsing of the response"""
        id_field = self.config.id_field
        group_results = self.config.group_results
        pfq = fq
        nfq = [solr_doc_id] if solr_doc_id else None
        try:
            solr_response = self._post_request(
                search_vector, rows, pfq=pfq, nfq=nfq
            ).json()
            if group_results:
                response_groups = solr_response["grouped"][id_field]["groups"]
                response_docs = [grp["doclist"]["docs"][0] for grp in response_groups]
            else:
                response_docs = solr_response["response"]["docs"]
        except (ConnectionError, JSONDecodeError, Timeout, KeyError, IndexError) as exc:
            logger.error(exc, exc_info=True)
            raise SolrCommunicationError() from exc

        id_not_found = (len(fq) > len(response_docs)) if fq else False
        if id_not_found:
            missing_ids = ",".join(
                list(set(map(str, fq)) - {str(d[id_field]) for d in response_docs})
            )
            # raise ResourceNotFoundException(resource_name=missing_ids)
            logger.warning("%s not found", missing_ids)

        recommendation = {
            "recommendation": [
                {"id": doc[id_field], "score": doc["score"]}
                for doc in response_docs
                if str(doc[id_field]) != str(solr_doc_id)
            ]
        }
        return recommendation

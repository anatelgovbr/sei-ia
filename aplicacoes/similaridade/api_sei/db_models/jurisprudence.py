import logging

from api_sei.db_models.solr_select import SolrRequests
from api_sei.envs import BASE_URL_JURISPRUDENCE_MLT, BASE_URL_JURISPRUDENCE_SELECT, auth
from api_sei.exception_handling.exceptions import (
    JsonFieldException,
    ParsedQueryEmptyException,
    ResourceNotFoundException,
)
from api_sei.pydantic_models.jurisprudence import FoundIdsDocs

logger = logging.getLogger(__name__)


class SolrJurisprudence:
    def get_docs(self, id_docs: list[int], fl: str = "id_document") -> list[dict]:
        """
        Dada uma lista de ids, retorna uma lista de documentos no formato definido pelo parâmetro 'fl'.

        Args:
            id_docs (List[int]): Uma lista de ids dos documentos a serem recuperados.
            fl (str): Os campos a serem recuperados. Padrão é 'id_document'.

        Returns:
            List[dict]: Uma lista de documentos no formato definido pelo parâmetro 'fl'.
        """
        if not id_docs:
            return []

        id_docs_str = " ".join([str(id_doc) for id_doc in id_docs])
        params = {"fl": fl, "q.op": "OR", "q": f"id_document:({id_docs_str})"}
        data = SolrRequests.select(
            url=BASE_URL_JURISPRUDENCE_SELECT,
            nested_fields=["response", "docs"],
            params=params,
            auth=auth,
        )
        return data

    def check_has_id_documents(self, id_docs: list[int]) -> FoundIdsDocs:
        if not id_docs:
            return FoundIdsDocs(id_docs_found=set(), id_docs_not_found=set())

        data = self.get_docs(id_docs)

        id_doc_found = {int(id_doc_dict.get("id_document")) for id_doc_dict in data}

        return FoundIdsDocs(
            id_docs_found=list(id_doc_found.intersection(set(id_docs))),
            id_docs_not_found=set(id_docs) - id_doc_found,
        )

    def __format_data(self, data_docs: list[dir]):
        new_keys = {"id_document": "id", "score": "score"}
        formatted_data = []
        for row in data_docs:
            formatted_data.append(
                {value: row[key] for (key, value) in new_keys.items()}
            )

        return {"recommendation": formatted_data}

    def __normalize_values(self, data_docs, max_score: float = None) -> list[dict]:
        """
        Normaliza os scores dos documentos para a faixa de 0 a 1.

        Caso o parâmetro 'max_score' seja None, o valor máximo dos scores será encontrado a partir da lista de documentos.

        :param data_docs: A lista de documentos com scores.
        :type data_docs: List[dict]
        :param max_score: O valor máximo dos scores. Se None, o valor máximo será encontrado a partir da lista de documentos.
        :type max_score: float
        :return: A lista de documentos com scores normalizados.
        :rtype: List[dict]
        """
        if not max_score:
            max_score = max(item["score"] for item in data_docs)

        # Normalize os scores para a faixa de 0 a 1
        for item in data_docs:
            item["score"] = (item["score"]) / (max_score)

        return data_docs

    def __get_self_score(self, nr_documento) -> float:
        """
        Recupera o score do documento para ele mesmo, ou seja, a relevância do documento para si mesmo.

        :param nr_documento: O número do documento.
        :type nr_documento: int
        :return: O score do documento para ele mesmo.
        :rtype: float
        """
        data_parsedquery = self.get_solr_using_debug_query(nr_documento)

        if not data_parsedquery:
            raise ParsedQueryEmptyException

        params = {
            "q": data_parsedquery,
            "fl": "id_document,score,id_type_document",
            "fq": f"id_document:{nr_documento}",
        }

        data = SolrRequests.select(
            url=BASE_URL_JURISPRUDENCE_SELECT,
            nested_fields=["response", "docs"],
            params=params,
            auth=auth,
        )

        return data[0].get("score")

    def __get_ids_and_score(
        self,
        fq: str,
        id_document: int,
        n_rows: int = 10,
        field_list: str = "id_document,score,id_type_document,score",
        sort_field: str = "score",
        type_sort: str = "desc",
        debug: bool = True,
    ):
        params = {
            "fq": fq,
            "q": f"id_document:{id_document}",
            "fl": field_list if isinstance(field_list, str) else ",".join(field_list),
            "sort": f"{sort_field} {type_sort}",
            "debugQuery": "on" if debug else "off",
            "mlt.mindf": 1,
            "mlt.mintf": 1,
        }

        data = SolrRequests.get(
            url=BASE_URL_JURISPRUDENCE_MLT,
            nested_fields=["response", "docs"],
            params=params,
            rows=n_rows,
            auth=auth,
        )

        return data

    def get_solr_using_debug_query(self, id_document: int):
        params = {
            "q": f"id_document:{id_document}",
            "debugQuery": "on",
            "wt": "json",
            "mlt.interestingTerms": "details",
            "fl": "id_document,score,id_type_document",
            "mlt.mindf": 1,
            "mlt.mintf": 1,
        }
        try:
            data_parsedquery = SolrRequests.get(
                url=BASE_URL_JURISPRUDENCE_MLT,
                nested_fields=["debug", "parsedquery"],
                params=params,
                rows=0,
                auth=auth,
            )
        except JsonFieldException as e:
            logger.error(f"Solr did not find {id_document!s}")
            raise ResourceNotFoundException(resource_name=id_document) from e

        return data_parsedquery

    def __parsedquery_list_to_set(self, parsedqueries: list[str]) -> set:
        resp = set()
        for parsedquery in parsedqueries:
            resp = resp.union(self.__parsedquery_to_set(parsedquery))

        return resp

    def __parsedquery_to_set(self, parsedquery) -> set:
        return set(parsedquery.split(" "))

    def get_solr_parsedquery(
        self, parsedquery: str, fq: str, normalize_value: float = None, rows: int = 10
    ) -> list[dict]:
        """
        Consulta o solr com o parsedquery e retorna os resultados

        Args:
            parsedquery (str): parsedquery a ser consultado
            fq (str): filtro a ser aplicado na consulta
            normalize_value (float): valor a ser dividido na normalização da pontuação
            rows (int): quantidade de linhas a serem retornadas

        Returns:
            List[dict]: lista de dicionários com id_document, score e id_type_document
        """
        if not parsedquery.strip():
            msg = "Os documentos selecionados estão vazios."
            logger.error(msg=msg)
            raise ParsedQueryEmptyException(detail=msg)

        params = {
            "q": f"{parsedquery}",
            "fl": "id_document,score,id_type_document",
            "fq": fq,
        }
        # TO DO:
        data = SolrRequests.get(
            url=BASE_URL_JURISPRUDENCE_SELECT,
            nested_fields=["response", "docs"],
            params=params,
            rows=rows,
            auth=auth,
        )

        data_docs = self.__normalize_values(data, normalize_value)

        return data_docs

    def get_jurisprudence_1doc(self, id_doc: int, rows: int, fq: str) -> list[dict]:
        """
        Recupera os documentos mais semelhantes a um determinado documento.

        Parameters
        ----------
        id_doc: int
            id do documento a ser buscado
        rows: int
            Número de resultados a serem retornados
        fq: str
            Filtro de pesquisa

        Returns
        -------
        List[dict]
            Uma lista de dicionarios com os ids dos documentos mais semelhantes,
            o score do documento e o tipo de documento.
        """
        try:
            data_docs = self.__get_ids_and_score(id_document=id_doc, n_rows=rows, fq=fq)
            max_score = self.__get_self_score(id_doc)
            data_docs = self.__normalize_values(data_docs, max_score=max_score)

            data_docs = self.__format_data(data_docs)
            return data_docs
        except Exception as exc:
            raise exc

    def get_jurisprudence_ndoc(
        self, list_id_doc: list[int], rows: int = 10, fq: str = ""
    ) -> list[dict]:
        """
        Recupera os documentos mais semelhantes entre os documentos enviados.

        Parameters
        ----------
        list_id_doc : List[int]
            Uma lista de ids dos documentos.
        rows : int
            O n mero de resultados a serem retornados. Padr o   10.
        fq : str
            Um filtro adicional a ser aplicado na pesquisa. Padr o   "".

        Returns
        -------
        List[dict]
            Uma lista de dicion rios contendo o id do documento, o score e o tipo de documento.
        """

        list_parsedqueries = [
            self.get_solr_using_debug_query(id_document) for id_document in list_id_doc
        ]
        parsedquery_full = " ".join(self.__parsedquery_list_to_set(list_parsedqueries))

        return self.get_solr_parsedquery(parsedquery=parsedquery_full, rows=rows, fq=fq)

"""Customized Parsed Query Resource."""

import logging
import re
from abc import ABC, abstractmethod
from enum import Enum

from fastapi import status

from api_sei.db_models.db_instances import app_db
from api_sei.db_models.get_content_lazy import get_tokenized_proc
from api_sei.db_models.models import ConfigMltFieldsWeights
from api_sei.db_models.solr_select import SolrRequests
from api_sei.envs import (
    JOBS_API_ADDRESS,
    SOLR_ADDRESS,
    SOLR_MLT_PROCESS_CORE,
    auth,
)
from api_sei.exception_handling.exceptions import (
    CustomParseValueError,
    ResourceNotFoundException,
    SolrRequestError,
)
from api_sei.resources.bm25 import extract, get_doc_score, simplified_bm25_tfidf
from api_sei.resources.lda import get_words_one_topic

BOOLEAN_FIELDS = [
    "metadata_id_unit_process_generator",
    "metadata_id_contact_interested",
]

MAX_SOLR_BOOLEAN_CLAUSES = (
    1000  # Solr's maxBooleanClauses is 1024; use 1000 for safety margin
)

# - Conteúdo dos Documentos: 70%
#     - sugiro considerar os principais tipos de documentos destacados pela análise do rafael, considerando um limiar
# - Metadados: 30%
#     - Tipo de Processo: 50%
#     - Processos Relacionados: 15% (sugiro avaliar como implementar isso, pois vejo como uma recursividade de
#       comparação entre processos, mas antes avaliando se tem ou não processo relacionado)
#     - Tipos de Documentos presentes: 15%
#     - Unidade Geradora do processo: 15%
#     - Especificação do processo: 3%
#     - Interessado do processo: 2%
#     - Citações (faltou um percentual pra isto e não lembro pq ficou em vermelho. pode estipular um valor qualquer, mas
#       mantendo a proporção pensada para os demais pesos.)

# mudei lá para ser da seguinte forma:


# - Unidade Geradora do processo: 10%
# - Especificação do processo: 5%
# - Interessado do processo: 3%
# - Citações 2%
class Speed(Enum):
    """Speed enum."""

    SPEED_1 = 1
    SPEED_2 = 2
    SPEED_3 = 3
    SPEED_4 = 4


logger = logging.getLogger(__name__)


SEARCH_FIELDS_PREFIXES = [
    "metadata_name_id_type_process",
    "metadata_id_unit_process_generator",
    "metadata_process_specification",
    "metadata_id_contact_interested",
    "metadata_info_related_processes",
    "metadata_name_id_type_doc_",
    "metadata_specification_id_type_doc_",
    "content_id_type_doc_",
    "metadata_citations",
]


def get_all_str_search_fields(
    nr_process: int, url: str, id_field: str = "id_protocolo"
) -> list:
    """Retrieves all the string search fields from Solr based on the given `nr_process` and `url`.

    Args:
        nr_process (int): The process number.
        url (str): The URL of the Solr instance.
        id_field (str, optional): The ID field to use for the query. Defaults to "id_protocolo".

    Returns:
        list: A list of string search fields.

    Raises:
        ResourceNotFoundException: If the `nr_process` is not found in Solr.

    """
    docs = SolrRequests.get(
        url=f"{url}/select?q={id_field}:{nr_process!s}&fl=*",
        nested_fields=["response", "docs"],
        rows=1,
        start=0,
        auth=auth,
    )

    if len(docs) > 0:
        all_docs_fields = list(docs[0].keys())
        pos_regex = re.compile(r"|".join(SEARCH_FIELDS_PREFIXES))
        search_fields = list(filter(pos_regex.search, all_docs_fields))
    else:
        try:
            logger.warning(f"Solr did not find {nr_process!s}")
            docs = SolrRequests.select(
                f"{JOBS_API_ADDRESS}/process/unindexed/nr_process/{nr_process}",
                auth=auth,
            )

            all_docs_fields = list(docs[0].keys())
            pos_regex = re.compile(r"|".join(SEARCH_FIELDS_PREFIXES))
            search_fields = list(filter(pos_regex.search, all_docs_fields))
        except Exception as err:
            raise ResourceNotFoundException(resource_name=nr_process) from err

    return search_fields


def init_weights_dict(
    mlt_fields: list, weights_dict: dict, d: dict, level: int = 0
) -> dict:
    """Initializes the weights dictionary for a given list of MLT fields based on the given input dictionary.

    Args:
        mlt_fields (list): A list of MLT fields.
        weights_dict (dict): The dictionary to be populated with the weights.
        d (dict): The dictionary to be used for populating the weights.
        level (int): The current level of the fields. Defaults to 0.

    Returns:
        dict: The populated weights dictionary.
    """
    for in_key in d:
        for out_key in mlt_fields:
            if in_key in out_key:
                weights_dict[out_key] = {
                    "level": level + (0 if in_key == out_key else 1),
                    "weight": 1,
                }

        if d[in_key].get("fields"):
            weights_dict = init_weights_dict(
                mlt_fields, weights_dict, d[in_key]["fields"], level + 1
            )

    return weights_dict


def update_weight_for_key(
    weights_dict: dict, in_key: str, weight: float, level: int
) -> None:
    """Atualiza o peso dos campos no dicionário com base na chave de entrada."""
    for out_key in weights_dict:
        if in_key in out_key and weights_dict[out_key]["level"] == level:
            weights_dict[out_key]["weight"] *= weight


def divide_weight_among_subfields(
    weights_dict: dict, in_key: str, subfields: list
) -> None:
    """Divide o peso entre os subcampos correspondentes no dicionário."""
    count = len(set(subfields))
    for out_key in weights_dict:
        if in_key in out_key:
            weights_dict[out_key]["weight"] /= count


def find_subfields(
    weights_dict: dict, in_key: str, level: int, fields: list | None = None
) -> list:
    """Encontra os subcampos correspondentes no dicionário de pesos."""
    subfields = []
    for out_key in weights_dict:
        if (in_key in out_key) and (weights_dict[out_key]["level"] == level):
            subfields.append(out_key)
        if fields:
            for subfield in fields:
                if subfield in out_key:
                    subfields.append(subfield)
    return subfields


def read_weight(weights_dict: dict, d: dict, level: int = 0) -> dict:
    """Atualiza recursivamente os pesos do dicionário com base nos pesos definidos no dicionário de entrada `d`.

    Parameters:
        weights_dict (dict): O dicionário contendo os pesos a serem atualizados.
        d (dict): O dicionário de entrada contendo os pesos a serem aplicados.
        level (int, opcional): O nível atual da recursão. O padrão é 0.

    Returns:
        dict: O `weights_dict` atualizado com os pesos multiplicados ou divididos com base no dicionário de entrada `d`.
    """
    for in_key in d:
        update_weight_for_key(weights_dict, in_key, d[in_key]["weight"], level)

        if d[in_key].get("variable_subfields"):
            subfields = find_subfields(
                weights_dict, in_key, level + 1, d[in_key].get("fields")
            )
            divide_weight_among_subfields(weights_dict, in_key, subfields)

        if d[in_key].get("fields"):
            weights_dict = read_weight(weights_dict, d[in_key]["fields"], level + 1)

    return weights_dict


def read_mlt_fields_weights(mlt_fields: list) -> dict:
    """Lê e calcula os pesos para uma lista de campos MLT.

    Esta função recupera uma configuração de pesos de campos de múltiplos termos de um arquivo JSON,
    inicializa um dicionário de pesos para os campos MLT especificados e atualiza os pesos
    com base na configuração.

    Parameters:
        mlt_fields (list): Uma lista de campos MLT para os quais os pesos precisam ser lidos e calculados.

    Returns:
        dict: Um dicionário contendo os pesos calculados para os campos MLT.
    """
    conf_mlt_fields_weights = app_db.execute_query_one(
        f"SELECT * FROM {ConfigMltFieldsWeights.__tablename__} ORDER BY id DESC"
    )
    if conf_mlt_fields_weights is None:
        raise ResourceNotFoundException(
            resource_name="ConfigMltFieldsWeights not found"
        )
    else:
        conf_mlt_fields_weights = conf_mlt_fields_weights[1]

    weights_dict = init_weights_dict(mlt_fields, {}, conf_mlt_fields_weights, 0)

    return read_weight(weights_dict, conf_mlt_fields_weights, 0)


def recursive_keys(d: dict, ks: list) -> list:
    """Percorre recursivamente um dicionário e retorna uma lista de suas chaves.

    Parameters:
    ----------
    d : dict
        O dicionário a ser percorrido.
    ks : list
        A lista à qual as chaves devem ser adicionadas.

    Returns:
    -------
    list
        A lista de chaves.
    """
    for k, v in d.items():
        ks.append(k)
        if isinstance(v, dict):
            ks = recursive_keys(v, ks)
    return ks


def read_fulltext_sections_fields() -> tuple:
    """Lê e retorna os campos de texto integral e seções de um dicionário de configuração de campos MLT.

    Esta função recupera uma configuração de pesos de campos de múltiplos termos de um arquivo JSON,
    extrai os campos de texto integral e seções do dicionário de configuração e retorna os conjuntos
    de campos.

    Returns:
        tuple: Um par de conjuntos, o primeiro contendo os campos de texto integral e o segundo
               contendo as seções.
    """
    conf_mlt_fields_weights = app_db.execute_query_one(
        f"SELECT * FROM {ConfigMltFieldsWeights.__tablename__} ORDER BY id DESC"
    )
    if conf_mlt_fields_weights is None:
        raise ResourceNotFoundException(
            resource_name="ConfigMltFieldsWeights not found"
        )
    else:
        conf_mlt_fields_weights = conf_mlt_fields_weights[1]

    fulltext_fields = set(
        conf_mlt_fields_weights["content"]["fields"]["content_id_type_doc_"][
            "fields"
        ].keys()
    )

    reserved_words = {"fields", "weight", "variable_subfields"}

    sections_fields = set(
        recursive_keys(
            conf_mlt_fields_weights["content"]["fields"]["content_id_type_doc_"], []
        )
    )

    sections_fields = sections_fields - set(fulltext_fields)

    sections_fields = sections_fields - reserved_words

    return fulltext_fields, sections_fields


class CustomParsedQuery:
    """Classe para construir uma consulta de pesquisa personalizada."""

    def __init__(self):  # noqa: ANN204, D107
        self.url = f"{SOLR_ADDRESS}/solr/{SOLR_MLT_PROCESS_CORE}"

    def process_boolean_field(
        self, id_protocolo: int, field_name: str, initial_weight: float
    ) -> str:
        """Processa um campo booleano de uma consulta de pesquisa personalizada.

        Esta função processa um campo booleano de uma consulta de pesquisa personalizada,
        ajustando os termos e pesos de acordo com a configuração.
        A função utiliza a consulta de similaridade de texto do Solr para obter os termos mais importantes
        do campo e, em seguida, calcula os pesos de cada termo com base na fórmula de BM25 simplificada.

        Parameters:
            id_protocolo (int): O identificador do protocolo a ser pesquisado.
            field_name (str): O nome do campo a ser processado.
            initial_weight (float): O peso inicial a ser utilizado na fórmula de BM25.

        Returns:
            str: A consulta de pesquisa personalizada processada.
        """
        query0b = (
            f"{self.url}/mlt?q=id_protocolo:{id_protocolo!s}&fl=id_protocolo,score&mlt.maxqt=25"
            f"&mlt.fl={field_name}&mlt.mintf=1&mlt.mindf=1&debugQuery=on&wt=json&mlt.interestingTerms=details&rows=0"
        )
        parsedquery = SolrRequests.select(
            url=query0b, nested_fields=["debug", "parsedquery"], timeout=60, auth=auth
        )

        interesting_terms = [
            v.replace(f"{field_name}:", "") for v in parsedquery.split()
        ]

        interesting_terms = [v for v in interesting_terms if v != "0"]

        query1 = f"{self.url}/select?q=*:*&rows=1&fl=numdocs()"
        for t in interesting_terms:
            query1 += f",docfreq({field_name},'{t}')"

        query1_response = SolrRequests.select(
            url=query1, nested_fields=[], timeout=60, auth=auth
        )
        if query1_response.status_code != status.HTTP_200_OK:
            raise SolrRequestError(message=query1_response.text)

        ns = []
        for t in interesting_terms:
            ns.append(
                query1_response.json()["response"]["docs"][0][
                    f"docfreq({field_name},'{t}')"
                ]
            )

        numdocs = query1_response.json()["response"]["docs"][0]["numdocs()"]

        n_terms = len(interesting_terms)

        weights = [
            initial_weight / (n_terms * simplified_bm25_tfidf(n, numdocs)) for n in ns
        ]

        return " ".join(
            [
                f"{field_name}:{t}^{w:.18f}"
                for t, w in zip(interesting_terms, weights, strict=False)
            ]
        )

    def process_text_similarity_field(
        self, id_protocolo: int, field_name: str, initial_weight: float
    ) -> str:
        """Processa um campo de texto semelhan a com base nos termos mais importantes do campo.

        Parameters:
            id_protocolo (int): O identificador do protocolo a ser pesquisado.
            field_name (str): O nome do campo a ser processado.
            initial_weight (float): O peso inicial a ser distribu do entre os termos.

        Returns:
            str: A consulta de pesquisa personalizada processada.
        """
        query0 = (
            f"{self.url}/mlt?q=id_protocolo:{id_protocolo!s}&fl=id_protocolo,score&mlt.maxqt=25&"
            f"mlt.fl={field_name}&mlt.mintf=1&mlt.mindf=1&debugQuery=on&wt=json&mlt.interestingTerms=details&rows=0"
        )
        original_parsedquery = SolrRequests.select(
            url=query0, nested_fields=["debug", "parsedquery"], timeout=60, auth=auth
        )

        interesting_terms = [
            v.replace(f"{field_name}:", "") for v in original_parsedquery.split()
        ]

        preprocessed_parsedquery = " ".join(
            [f"{field_name}:{t}" for t in interesting_terms]
        )

        if not preprocessed_parsedquery.strip():
            return ""

        query1 = (
            f"{self.url}/select?fl=id_protocolo,score&indent=true&q.op=OR&q={preprocessed_parsedquery}&"
            f"rows=1&fq=id_protocolo:{id_protocolo!s}"
        )

        query1_response = SolrRequests.select(
            url=query1, nested_fields=[], timeout=60, auth=auth
        )
        if query1_response.status_code != status.HTTP_200_OK:
            raise SolrRequestError(query1_response.text)

        query1_response_json = query1_response.json()

        query1_response_docs = query1_response_json["response"]["docs"]

        if len(query1_response_docs) == 0:
            raise SolrRequestError(query1_response_json)

        ref_score = query1_response_docs[0]["score"]

        n_terms = len(interesting_terms)

        weights = [initial_weight / (ref_score) for _ in range(n_terms)]

        return " ".join(
            [
                f"{field_name}:{t}^{w:.18f}"
                for t, w in zip(interesting_terms, weights, strict=False)
            ]
        )

    def get_parsedquery(
        self, id_protocolo: str, ignore_fields: set | None = None
    ) -> str:
        """Processa a consulta de pesquisa personalizada para um protocolo.

        Considerando todos os campos MLT (More Like This) e seus respectivos pesos.

        Parameters:
            id_protocolo (str): O identificador do protocolo a ser pesquisado.
            ignore_fields (set, optional): O conjunto de campos que devem ser ignorados
                durante a constru o da consulta. Se n o for fornecido, um conjunto vazio
                ser  utilizado.

        Returns:
            str: A consulta de pesquisa personalizada processada.
        """
        if ignore_fields is None:
            ignore_fields = set()
        mlt_fields = get_all_str_search_fields(
            id_protocolo, self.url, id_field="id_protocolo"
        )

        mlt_fields = [f for f in mlt_fields if f not in ignore_fields]

        mlt_fields_weights = read_mlt_fields_weights(mlt_fields)

        parsedqueries = []

        for mlt_field in mlt_fields_weights:
            w = mlt_fields_weights[mlt_field]["weight"]

            if mlt_field in BOOLEAN_FIELDS:
                parsedqueries.append(
                    self.process_boolean_field(id_protocolo, mlt_field, w)
                )
            else:
                parsedqueries.append(
                    self.process_text_similarity_field(id_protocolo, mlt_field, w)
                )

        return " ".join(parsedqueries)


class FasterCustomParsedQueryBaseClass(ABC):
    """Classe base para as extensões da classe FasterCustomParsedQuery."""

    def __init__(self, id_protocolo: str, ignore_fields: set | None = None, **kwargs):  # noqa: ANN003, ANN204, D107
        self.id_protocolo = id_protocolo

        self.ignore_fields = ignore_fields if ignore_fields else set()

        self.base_url = f"{SOLR_ADDRESS}/solr/{SOLR_MLT_PROCESS_CORE}"

        self.maxqt_per_field = 25

        self.all_fields = [
            f for f in self.get_all_fields() if f not in self.ignore_fields
        ]

        self.per_field_terms = self.get_interestingterms(**kwargs)

        self.boolean_fields_data = self.get_boolean_fields_data()

    def get_boolean_fields_data(self) -> dict:
        """Recupera o número total de documentos no índice e a frequência de cada termo em cada campo booleano.

        Returns:
            dict: Um dicionário com as seguintes chaves:
                - N: O número total de documentos no índice.
                - docfreq_<boolean_field>_<termo>: A frequência do termo <termo> no campo booleano <boolean_field>.
        """
        query = f"{self.base_url}/select?q=*:*&fl=numdocs()"
        for boolean_field in set(BOOLEAN_FIELDS).intersection(set(self.all_fields)):
            interesting_terms = self.per_field_terms[boolean_field]
            for t in interesting_terms:
                query += f",docfreq({boolean_field},'{t}')"
        return SolrRequests.get(query, ["response", "docs", 0], rows=1, auth=auth)

    def process_boolean_field(self, field_name: str, initial_weight: float) -> str:
        """Processa um campo booleano calculando pesos para termos relevantes com base suas frequências nos documentos.

        Parameters:
            field_name (str): O nome do campo booleano a ser processado.
            initial_weight (float): O peso inicial a ser distribuído entre os termos.

        Returns:
            str: Uma string de consulta parseada com os termos e seus pesos correspondentes.
        """
        interesting_terms = self.per_field_terms[field_name]

        if not interesting_terms:
            return ""

        ns = []
        for t in interesting_terms:
            ns.append(self.boolean_fields_data[f"docfreq({field_name},'{t}')"])

        numdocs = self.boolean_fields_data["numdocs()"]

        n_terms = len(interesting_terms)

        weights = [
            initial_weight / (n_terms * simplified_bm25_tfidf(n, numdocs)) for n in ns
        ]

        return " ".join(
            [
                f"{field_name}:{t}^{w:.18f}"
                for t, w in zip(interesting_terms, weights, strict=False)
            ]
        )

    def process_text_similarity_field(
        self, field_name: str, initial_weight: float
    ) -> str:
        """Processa um campo de similaridade de texto calculando pesos para termos relevantes com base na similaridade.

        Parameters:
            field_name (str): O nome do campo de similaridade de texto a ser processado.
            initial_weight (float): O peso inicial a ser distribuído entre os termos.

        Returns:
            str: Uma string de consulta parseada com os termos e seus pesos correspondentes.
        """
        interesting_terms = self.per_field_terms[field_name]

        preprocessed_parsedquery = " ".join(
            [f"{field_name}:{t}" for t in interesting_terms]
        )

        if not preprocessed_parsedquery.strip():
            return ""

        ref_score = self.get_self_score(preprocessed_parsedquery)

        n_terms = len(interesting_terms)

        weights = [initial_weight / (ref_score) for _ in range(n_terms)]

        return " ".join(
            [
                f"{field_name}:{t}^{w:.18f}"
                for t, w in zip(interesting_terms, weights, strict=False)
            ]
        )

    def get_parsedquery(self, ignore_fields: set | None = None) -> str:
        """Constrói e retorna uma consulta de busca personalizada para um protocolo.

        Este método processa campos para gerar uma consulta More Like This (MLT),
        considerando todos os campos relevantes e seus respectivos pesos, enquanto
        exclui quaisquer campos especificados no parâmetro ignore_fields.

        Parameters:
            ignore_fields (set, opcional): Um conjunto de campos a serem ignorados
                durante a construção da consulta. Se não fornecido, nenhum campo será ignorado.

        Returns:
            str: A consulta de busca personalizada construída.
        """
        mlt_fields = [f for f in self.all_fields if f not in ignore_fields]

        mlt_fields_weights = read_mlt_fields_weights(mlt_fields)

        parsedqueries = []

        for mlt_field in mlt_fields_weights:
            w = mlt_fields_weights[mlt_field]["weight"]

            if mlt_field in BOOLEAN_FIELDS:
                parsedqueries.append(self.process_boolean_field(mlt_field, w))
            else:
                parsedqueries.append(self.process_text_similarity_field(mlt_field, w))

        full_query = " ".join(parsedqueries)

        clauses = full_query.split()
        if len(clauses) > MAX_SOLR_BOOLEAN_CLAUSES:
            logger.warning(
                "Parsedquery has %d clauses, truncating to %d to respect Solr maxBooleanClauses",
                len(clauses),
                MAX_SOLR_BOOLEAN_CLAUSES,
            )

            def _clause_weight(clause: str) -> float:
                if "^" in clause:
                    try:
                        return float(clause.rsplit("^", 1)[-1])
                    except ValueError:
                        return 0.0
                return 0.0

            clauses.sort(key=_clause_weight, reverse=True)
            full_query = " ".join(clauses[:MAX_SOLR_BOOLEAN_CLAUSES])

        return full_query

    @abstractmethod
    def get_all_fields(self) -> list:
        """Recupera todos os campos de busca de texto do Solr com base no `nr_process` e `url` fornecidos.

        Raises:
            ResourceNotFoundException: Se o `nr_process` não for encontrado no Solr.

        Returns:
            list: Uma lista de campos de busca de texto.
        """

    @abstractmethod
    def get_interestingterms(self, **kwargs) -> dict:  # noqa: ANN003
        """Recupera os termos mais interessantes de cada campo de busca de texto.

        Implementado por subclasses para lidar com a extração de termos mais
        interessantes de cada campo de busca de texto.

        Returns:
            dict: Um dicion rio com os campos como chave e uma lista de termos
                mais interessantes como valor.
        """

    @abstractmethod
    def get_self_score(self, parsedquery: str) -> float:
        """Calculates the self score for the document using the parsed query.

        Parameters:
            parsedquery (str): The parsed query string to be used for scoring.

        Returns:
            float: The calculated self score of the document.
        """


class FasterCustomParsedQuery(FasterCustomParsedQueryBaseClass):
    """Extensão da classe FasterCustomParsedQuery para a busca com LDA."""

    def __init__(  # noqa: ANN204, D107
        self,
        id_protocolo: str,
        ignore_fields: set | None = None,
        speed_level: int = 2,
        *,
        parallel: bool = True,
    ):
        super().__init__(
            id_protocolo, ignore_fields, speed_level=speed_level, parallel=parallel
        )

    def get_all_fields(self) -> list:
        """Recupera todos os campos de busca de texto do Solr com base no `id_protocolo` e `base_url` fornecidos.

        Implementado por subclasses para lidar com a extração de campos de busca de texto.

        Returns:
            list: Uma lista de campos de busca de texto.
        """
        return get_all_str_search_fields(
            self.id_protocolo, self.base_url, id_field="id_protocolo"
        )

    def get_raw_interestingterms(
        self, *, parallel: bool, speed_level: int, raw_maxqt: int = 1024
    ):  # noqa: ANN201
        """Recupera interessantes brutos do Solr com base no nível de velocidade especificado na execução paralela.

        Este método consulta o Solr para obter termos interessantes de vários campos de um documento identificado por
        `id_protocolo`. Os campos são categorizados em campos de metadados e de conteúdo, e a função
        executa diferentes tipos de requisições com base no `speed_level`.

        Parameters:
            parallel (bool): Indica se as consultas devem ser executadas em paralelo para múltiplas requisições.
            speed_level (int): Define o agrupamento de campos e o tipo de requisições:
                - 1: Consulta todos os campos em uma única requisição.
                - 2: Consulta campos de metadados e de conteúdo em requisições separadas com tipos mistos de requisição.
                - 3: Consulta campos de metadados e de conteúdo em requisições únicas separadas.
                - 4: Consulta todos os campos em uma única requisição.
            raw_maxqt (int, opcional): Número máximo de termos interessantes a serem recuperados. O padrão é 1024.

        Returns:
            list: Uma lista ordenada de termos interessantes dos campos especificados.
        """
        field_groups, types_of_requests = self._get_field_groups_and_request_types(
            speed_level
        )
        it = []
        for field_group, type_of_request in zip(
            field_groups, types_of_requests, strict=False
        ):
            it += self._process_request_type(
                field_group=field_group,
                request_type=type_of_request,
                raw_maxqt=raw_maxqt,
                parallel=parallel,
            )
        return self.sort_terms(it)

    def _get_field_groups_and_request_types(self, speed_level: int) -> tuple:
        """Agrupa campos de busca de texto em grupos e define o tipo de requisicão a ser executado para cada nível.

        O n vel de velocidade define como os campos s o agrupados e como as requisi es s o feitas:
            - 1: Consulta todos os campos em uma nica requisi o.
            - 2: Consulta campos de metadados e de conte do em requisi es separadas, com tipos mistos de requisição.
            - 3: Consulta campos de metadados e de conte do em requisi es nicas separadas.
            - 4: Consulta todos os campos em uma nica requisi o.

        Parameters:
            speed_level (int): N vel de velocidade.

        Returns:
            tuple: Um par de listas, a primeira com os grupos de campos e a segunda com os tipos de requisi o.
        """
        metadata_fields = [field for field in self.all_fields if "metadata_" in field]
        content_fields = [field for field in self.all_fields if "content_" in field]

        if Speed(speed_level) == Speed.SPEED_1:
            return [self.all_fields], ["multiple"]
        elif Speed(speed_level) == Speed.SPEED_2:  # noqa: RET505
            return [metadata_fields, content_fields], ["single", "multiple"]
        elif Speed(speed_level) == Speed.SPEED_3:
            return [metadata_fields, content_fields], ["single", "single"]
        elif Speed(speed_level) == Speed.SPEED_4:
            return [self.all_fields], ["single"]
        else:
            msg = f"Nível de velocidade inválido: {speed_level}"
            raise CustomParseValueError(msg)

    def _process_request_type(
        self, field_group: list, request_type: str, raw_maxqt: int, *, parallel: bool
    ) -> list:
        """Processa o tipo de requisição (single ou multiple) e executa as consultas apropriadas."""
        if request_type == "single":
            return self._execute_single_request(field_group, raw_maxqt)
        elif request_type == "multiple":  # noqa: RET505
            return self._execute_multiple_requests(
                field_group=field_group, parallel=parallel
            )
        else:
            msg = f"Tipo de requisição inválido: {request_type}"
            raise CustomParseValueError(msg)

    def _execute_single_request(self, field_group: list, raw_maxqt: int) -> list:
        """Executa uma única requisição ao Solr para um grupo de campos."""
        return SolrRequests.get(
            (
                f"{self.base_url}/mlt?q=id_protocolo:{self.id_protocolo!s}&fl=id_protocolo,score"
                f"&mlt.maxqt={raw_maxqt}&mlt.fl={','.join(field_group)}"
                "&mlt.mintf=1&mlt.mindf=1&wt=json&mlt.interestingTerms=details&mlt.boost=true"
            ),
            ["interestingTerms"],
            rows=0,
            auth=auth,
        )

    def _execute_multiple_requests(self, field_group: list, *, parallel: bool) -> list:
        """Executa consultas independentes ao Solr para cada campo de um grupo.

        Retorna as respostas concatenadas.

        Se o grupo tiver mais de um campo e o parâmetro `parallel` for True,
        as consultas são executadas em paralelo utilizando SolrRequests.async_select.
        Caso contrário, as consultas são executadas sequencialmente com SolrRequests.get.

        :param field_group: lista de campos a serem pesquisados
        :param parallel: se True, executa as consultas em paralelo
        :return: lista de termos interessantes, concatenados pelas consultas
        """
        queries = [
            (
                f"{self.base_url}/mlt?q=id_protocolo:{self.id_protocolo!s}&fl=id_protocolo,score"
                f"&mlt.maxqt=25&mlt.fl={field_name}"
                "&mlt.mintf=1&mlt.mindf=1&wt=json&mlt.interestingTerms=details&mlt.boost=true"
            )
            for field_name in field_group
        ]

        it = []
        if len(queries) > 1 and parallel:
            async_result = SolrRequests.async_select(
                queries, ["interestingTerms"], auth=auth
            )
            for res in async_result:
                it += res
        else:
            for q in queries:
                it += SolrRequests.get(q, ["interestingTerms"], rows=0, auth=auth)
        return it

    def sort_terms(self, it: list) -> list:
        """Ordena a lista de termos interessantes recebida em 'it' pelo valor de cada termo.

        A lista 'it' é supostamente uma lista de pares, onde em cada par,
        o primeiro elemento é o nome do campo e o segundo elemento é o valor.

        A ordenação é feita em ordem decrescente, ou seja, os termos com valores mais altos
        ficam na frente da lista.

        Retorna a lista ordenada.
        """
        new_it = []
        for i, _ in sorted(enumerate(it[1::2]), key=lambda x: x[1], reverse=True):
            new_it += [it[i * 2], it[i * 2 + 1]]
        return new_it

    def get_interestingterms(
        self, *, parallel: bool = True, speed_level: int = 2, **kwargs
    ) -> dict:  # noqa: ANN003, ARG002
        """Recupera os termos mais interessantes de cada campo de busca de texto.

        Implementado por subclasses para lidar com a extração de termos interessantes de cada campo de busca de texto.

        Parameters:
        ----------
        parallel: bool
            Se True, as queries são feitas em paralelo. (padr o=True)
        speed_level: int
            N vel de velocidade para a extra o dos termos interessantes.
            0: n o faz nada.
            1: faz a extra o com mlt.
            2: faz a extra o com mlt e com o paralelismo.
            (padr o=2)
        **kwargs: dict
            Argumentos adicionais que podem ser usados pelas subclasses.

        Returns:
        -------
        dict:
            Um dicion rio com os campos como chave e uma lista de termos interessantes como valor.
        """
        it = self.get_raw_interestingterms(parallel=parallel, speed_level=speed_level)
        per_field_terms = {}
        for field in self.all_fields:
            interesting_terms = [
                t.replace(f"{field}:", "") for t in it[0::2] if f"{field}:" in t
            ]
            interesting_terms = [t for t in interesting_terms if t != "0"]
            per_field_terms[field] = interesting_terms[: self.maxqt_per_field]
        return per_field_terms

    def get_self_score(self, parsedquery: str) -> float:
        """Calcula a pontua o do pr prio documento com base em uma query parseada.

        Parameters:
            parsedquery (str): A string da query parseada.

        Returns:
            float: A pontua o calculada do documento.
        """
        url_str = (
            f"{self.base_url}/select?fl=id_protocolo,score&indent=true&q.op=OR&q={parsedquery}"
            f"&fq=id_protocolo:{self.id_protocolo!s}"
        )
        return SolrRequests.get(
            url_str, ["response", "docs", 0, "score"], rows=1, auth=auth
        )

    def get_field_terms(self, field_name: str) -> list:
        """Retorna a lista de termos interessantes de um campo.

        Parameters:
            field_name (str): O nome do campo.

        Returns:
            list: A lista de termos interessantes do campo.
        """
        return self.per_field_terms[field_name]


class ManualExtractCustomParsedQuery(FasterCustomParsedQueryBaseClass):
    """Classe base para consultas de extração de termos manualmente."""

    def __init__(self, id_protocolo: str, ignore_fields: set | None = None):  # noqa: ANN204, D107
        self.proc = self.get_proc(id_protocolo)

        super().__init__(id_protocolo, ignore_fields)

    def get_proc(self, id_protocolo: str) -> dict:
        """Recupera e tokeniza o conteúdo de um protocolo com base nos campos especificados.

        Este método identifica campos de texto e string para tokenização e recupera
        o conteúdo processado usando a função `get_tokenized_proc`.

        Parameters:
            id_protocolo (str): O identificador do protocolo cujo conteúdo será processado.

        Returns:
            dict: Um dicionário com os campos tokenizados do protocolo.
        """
        string_fields = [*BOOLEAN_FIELDS, "content_citations"]
        text_fields = set(SEARCH_FIELDS_PREFIXES) - set(string_fields)
        return get_tokenized_proc(id_protocolo, text_fields, string_fields)

    def get_all_fields(self) -> list:
        """Recupera todos os campos de busca de texto do Solr com base no `id_protocolo` e `base_url` fornecidos.

        Implementado por subclasses para lidar com a extra o de campos de busca de texto.

        Returns:
            list: Uma lista de campos de busca de texto.
        """
        return self.proc.keys()

    def get_interestingterms(self, **kwargs) -> dict:  # noqa: ANN003, ARG002
        """Recupera os termos mais interessantes de cada campo de busca de texto com base em BM25.

        A extra o   feita com base na fun o `extract` e retorna um dicion rio com os campos como chave e
        uma lista de termos interessantes como valor. A lista de termos tem tamanho igual a `maxqt_per_field`.
        """
        per_field_terms = {}
        for field in self.all_fields:
            extracted_terms = [
                t[0]
                for t in extract(
                    self.base_url,
                    field,
                    self.proc[field],
                    max_tokens=self.maxqt_per_field,
                )
            ]
            per_field_terms[field] = extracted_terms
        return per_field_terms

    def get_self_score(self, parsedquery: str) -> float:
        """Calcula a pontuação do próprio documento com base em uma query parseada.

        Parameters:
            parsedquery (str): A string da query parseada.

        Returns:
            float: A pontuação calculada do documento.
        """
        return get_doc_score(self.base_url, parsedquery, self.proc)


class LDAExtractCustomParsedQuery(ManualExtractCustomParsedQuery):
    """Extensão da classe FasterCustomParsedQuery para a busca com LDA."""

    def __init__(self, id_protocolo: str, ignore_fields: set | None = None):  # noqa: ANN204, D107
        if ignore_fields is None:
            ignore_fields = set()
        self.proc = self.get_proc(id_protocolo)
        super().__init__(id_protocolo, ignore_fields)

    def get_interestingterms(self, **kwargs) -> dict:  # noqa: ANN003, ARG002
        """Extrai os termos mais importantes de cada campo de texto com base em LDA.

        Returns:
            dict: Um dicionário com os campos como chave e uma lista de termos
            importantes como valor. A lista de termos tem tamanho igual a
            `maxqt_per_field`.
        """
        per_field_terms = {}
        for field in self.all_fields:
            per_field_terms[field] = get_words_one_topic(
                documents=[self.proc[field]], num_topics=1, n_words=self.maxqt_per_field
            )

        return per_field_terms

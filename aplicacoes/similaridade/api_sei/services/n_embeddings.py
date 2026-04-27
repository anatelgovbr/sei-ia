import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd
from fastapi import HTTPException

from api_sei.db_models.db_instances import app_db
from api_sei.db_models.solr_mlt import SolrMlt
from api_sei.db_models.solr_select import SolrRequests
from api_sei.envs import SOLR_ADDRESS, SOLR_MLT_PROCESS_CORE, auth
from api_sei.pydantic_models.solr_mlt import SolrMltConfigModel
from api_sei.resources.embed import (
    get_similarity_embedding as get_similarity_embedding_resource,
)

logger = logging.getLogger(__name__)


class SimilarityFactory(ABC):
    """Classe abstrata que representa um metodo de similaridade"""

    @abstractmethod
    def calc_similarity(self, maxsim_chunks: list[float]) -> float: ...

    def get_maxsim_chunks(self):
        return np.array(
            [np.max([1 - x for x in chunks]) for chunks in self.chunks_dist],
            dtype=np.float64,
        )  # 1-x para converter distancia em similaridade

    def calc(self):
        maxsim_chunks = self.get_maxsim_chunks()
        return self.calc_similarity(maxsim_chunks)


class SimilarityMean(SimilarityFactory):
    label: str = "mean"

    def __init__(self, chunks_dist: list[np.ndarray]):
        self.chunks_dist = chunks_dist

    def calc_similarity(self, maxsim_chunks: list[float]):
        return maxsim_chunks.mean()


@dataclass
class EmbeddingDocument:
    """Classe que representa um documento com seus embeddings para o metodo de similaridade
    n-embedding

    Args:
        id_documento: str - identificador do documento
        tp_documento: int - identificador do tipo de documento
        embds: List[np.ndarray] - lista de chunks de embeddings do documento
    """

    id_processo: str
    id_documento: str
    tp_documento: int
    embds: list[np.ndarray]


@dataclass
class NEmbeddingDocumentSimilarity:
    """Classe que representa o metodo de similaridade n-embedding doc2doc

    Args:
        doc_search: EmbeddingDocument - documento de busca
        doc_compare: EmbeddingDocument - documento de comparação
    """

    doc_search: EmbeddingDocument
    doc_compare: EmbeddingDocument
    embd_tablename: str

    def __post_init__(self):
        self.similarity = self._calc_similarity_doc_a_b(
            self.doc_search, self.doc_compare
        )

    def _calc_similarity(self, chunks_dist: list[np.ndarray]) -> list[float]:
        self.similarity_method = SimilarityMean(chunks_dist)
        return self.similarity_method.calc()

    def _calc_similarity_doc_a_b(
        self, search: EmbeddingDocument, doc_compare: EmbeddingDocument
    ):
        distances = self.dist_cosine_chunks(search, doc_compare)
        return self._calc_similarity(distances)

    def dist_cosine_chunks(self, search, doc_compare):
        distances = []
        for idx, _ in enumerate(search.embds):
            sql_query = f"""\
                SELECT
                id_documento,
                (
                    SELECT embd from {self.embd_tablename}
                    WHERE
                        id_documento = {search.id_documento}
                        AND chunk_idx = {idx}
                ) <=> embd as dist_cosine
                FROM {self.embd_tablename}
                WHERE
                    id_documento = {doc_compare.id_documento}
                ORDER BY dist_cosine;"""
            data_dist = app_db.get_dataframe(sql_query)["dist_cosine"].values
            distances.append(data_dist)
        return distances


class NEmbeddingDocumentRecommender:
    """Classe que representa o metodo de recomendação de documentos baseado no n-embedding doc2doc"""

    def __init__(
        self,
        search_id: int,
        tp_doc_allowed: list[int],
        embd_tablename: str,
        top_k: int = 5,
        top_k_first_tier: int = 50,
        validacao=None,
    ):
        """Classe para gerar recomendação de documentos , dado um id_documento

        Args:
            search_id (int): id do documento de busca
            tp_doc_allowed (List[int]): lista de tipos de documentos permitidos para comparação
            embd_tablename (str): nome da tabela de embeddings
            top_k (int, optional): quantidade de documentos a serem retornados. Defaults to 5.
            top_k_first_tier (int, optional): quantidade de documentos a serem retornados na primeira camada. Defaults to 50.
            validacao (List[int], optional): lista de nr_documento para validação. Defaults to None.
        """
        self.search_id = search_id
        self.tp_doc_allowed = tp_doc_allowed
        self.embd_tablename = embd_tablename
        self.top_k = top_k
        self.top_k_first_tier = top_k_first_tier
        self.validacao = validacao

    def run(self):
        self.doc_search = self.get_search_embds_from_db(id_documento=self.search_id)
        first_tier_docs = self._search_first_tier_documents(
            self.doc_search, validacao=self.validacao
        )

        if len(first_tier_docs) == 0:
            return []

        compare_docs = [
            self.get_search_embds_from_db(id_documento=id_doc)
            for id_doc in first_tier_docs["id_documento"].values
        ]
        recommendations = self.recommend(self.doc_search, compare_docs)
        return recommendations

    def recommend(self, doc_search, compare_docs: list[EmbeddingDocument]):
        """Recomenda os top-k documentos mais similares ao documento de busca"""
        similarities = []
        for compare_doc in compare_docs:
            similarity = NEmbeddingDocumentSimilarity(
                doc_search, compare_doc, embd_tablename=self.embd_tablename
            ).similarity
            similarities.append({"id": compare_doc.id_documento, "score": similarity})

        sorted_docs = sorted(similarities, key=lambda x: x["score"], reverse=True)
        return sorted_docs[: self.top_k]

    def get_search_embds_from_db(self, id_documento: int) -> EmbeddingDocument:
        df = app_db.get_dataframe(
            f"SELECT * FROM {self.embd_tablename} WHERE id_documento = {id_documento}"
        )
        embds = df["embd"].values
        return EmbeddingDocument(
            id_processo=df["id_processo"].values[0],
            id_documento=df["id_documento"].values[0],
            tp_documento=df["tp_documento"].values[0],
            embds=embds,
        )

    def _search_first_tier_documents(
        self, query_embd: list[str], validacao=None
    ) -> list[int]:
        """Strategy to split compare space because it needs NxN similarities

        Args:
            query_embd (List[str]): embeddings of text chunks from document to search.
                                    Pgvector return a list of str when

        Returns:
            List[int]: return list of unique top_k_first_tier id_documents
        """
        first_tier_list = pd.DataFrame()
        if validacao is None:
            for idx, _q_embd in enumerate(query_embd.embds):
                sql_query = f"""\
                        SELECT
                        id_documento,
                        (
                            SELECT embd from {self.embd_tablename}
                            WHERE
                                id_documento = {self.search_id} AND chunk_idx = {idx} \
                        ) <=> embd as dist_cosine
                        FROM {self.embd_tablename} \
                        WHERE
                            id_documento != {self.search_id}\
                            {"AND tp_documento IN (" + ",".join([str(x) for x in self.tp_doc_allowed]) + ")" if self.tp_doc_allowed else ""} \
                        ORDER BY dist_cosine;"""

                df = (
                    app_db.get_dataframe(sql_query)
                    .query("dist_cosine > 0")
                    .sort_values(by="dist_cosine", ascending=True)
                    .head(self.top_k_first_tier)
                )

                first_tier_list = pd.concat([first_tier_list, df], axis=0)

            first_tier_list = (
                first_tier_list.sort_values(by="dist_cosine", ascending=True)
                .drop_duplicates(subset=["id_documento"])
                .head(self.top_k_first_tier)
            )

            return first_tier_list

        if validacao:
            for idx, _ in enumerate(query_embd.embds):
                sql_query = f"""\
                        SELECT
                        id_documento,
                        (
                            SELECT embd from {self.embd_tablename}
                            WHERE
                                id_documento = {self.search_id} AND chunk_idx = {idx} \
                        ) <=> embd as dist_cosine
                        FROM {self.embd_tablename} \
                        WHERE
                            id_documento != {self.search_id}\
                            AND id_documento IN \
                                    ({",".join([str(x) for x in validacao])}) \
                            {"AND tp_documento IN (" + ",".join([str(x) for x in self.tp_doc_allowed]) + ")" if self.tp_doc_allowed else ""} \
                        ORDER BY dist_cosine;"""
                df = app_db.get_dataframe(sql_query)
                first_tier_list.extend(df["id_documento"].values)
                return list(set(first_tier_list))


def get_similarity_embedding(id_processo: int, list_id_processos: list[int], rows: int):
    if not isinstance(id_processo, int):
        raise HTTPException(
            status_code=400,
            detail="O campo 'id_processo' deve ser um inteiro válido maior que zero.",
        )

    if list_id_processos and (not isinstance(list_id_processos, list)):
        raise HTTPException(
            status_code=400, detail="A lista 'list_id_processo' não pode estar vazia."
        )

    if not isinstance(rows, int) and rows > 0:
        raise HTTPException(
            status_code=400,
            detail="O campo 'rows' deve ser um inteiro válido maior que zero.",
        )

    return get_similarity_embedding_resource(
        id_processo=id_processo, list_id_processos=list_id_processos, rows=rows
    )


def adapter_protocolo_formatado_id_protocolo(func, id_protocolo, fq, rows):
    url = f"{SOLR_ADDRESS}/solr/{SOLR_MLT_PROCESS_CORE}"
    solr_mlt_config = SolrMltConfigModel(
        url=url,
        fields=[],
        id_field="id_protocolo",
        extra_fields=["id_process", "protocolo_formatado"],
    )
    solr_mlt_service = SolrMlt(solr_mlt_config)
    source_doc = solr_mlt_service.find(id_protocolo)
    protocolo_formatado = source_doc.get("id_process") or source_doc.get(
        "protocolo_formatado"
    )
    if fq is not None:
        fq_mapper = {
            str(item["id_protocolo"]): item for item in solr_mlt_service.find_many(fq)
        }
        protocolo_formatado_fq = [
            str(
                fq_mapper[str(i)].get("id_process")
                or fq_mapper[str(i)].get("protocolo_formatado")
            )
            for i in fq
        ]
    else:
        protocolo_formatado_fq = None
    response = func(int(protocolo_formatado), protocolo_formatado_fq, rows)
    if fq is not None:
        response = {
            "recommendation": [
                {
                    "id": fq[protocolo_formatado_fq.index(str(item["id"]))],
                    "score": item["score"],
                }
                for item in response["recommendation"]
            ]
        }
    else:
        old_ids_str = " ".join([str(item["id"]) for item in response["recommendation"]])
        response_docs = SolrRequests.select(
            f"{url}/select?q=id_process:({old_ids_str}) OR protocolo_formatado:({old_ids_str})"
            + f"&fl=id_process,id_protocolo,protocolo_formatado&rows={rows}",
            nested_fields=["response", "docs"],
            auth=auth,
        )
        inverse_mapper = {
            (item.get("id_process") or item.get("protocolo_formatado")): item[
                "id_protocolo"
            ]
            for item in response_docs
            if ("id_process" in item or "protocolo_formatado" in item)
        }
        response = {
            "recommendation": [
                {
                    "id": inverse_mapper.get(str(item["id"])) or str(item["id"]),
                    "score": item["score"],
                }
                for item in response["recommendation"]
            ]
        }
        # logger.info(response)
    return response

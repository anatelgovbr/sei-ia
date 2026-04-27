#!/usr/bin/env python
"""Modelo de dados para solr mlt."""

from enum import Enum

from pydantic import BaseModel


class ExtractionMethodEnum(str, Enum):
    """Metodos de calculo de similaridade."""

    bm25 = "bm25"
    lda = "lda"
    solr = "solr"


class SolrMltConfigModel(BaseModel):
    """Parametro de configuração do solr mlt."""

    maxdfpct: int | None = None
    maxqt: int = 25
    boost: bool = False
    mintf: int = 2
    mindf: int = 5
    minwl: int | None = None
    maxwl: int | None = None
    fields: list[str]
    url: str
    id_field: str = "id"
    mlt_qf: str | None = None
    normalized: bool = False
    custom_query: bool = False
    debug: bool = False
    extra_fields: list[str] = []
    parsedquery_field: str = "fulltext_parsedquery_t"
    extraction_method: ExtractionMethodEnum = ExtractionMethodEnum.solr


class DebugField(BaseModel):
    """Parametro de configuração do solr mlt."""

    explain: dict
    parsedquery: str


class DocsItem(BaseModel):
    """Elementos que compoem o doc, sem o conteudo."""

    id_protocolo: str
    id_process: str = None
    protocolo_formatado: str = None
    score: float


class DetailedSolrJsonResponseField(BaseModel):
    """Lista de docs com os DocsItem."""

    docs: list[DocsItem]


class DetailedSolrJson(BaseModel):
    """Elementos de detalhamento  da resposta do json."""

    response: DetailedSolrJsonResponseField
    debug: DebugField = None
    interesting_terms: list[object] = None


class GenericSolrJsonResponseField(BaseModel):
    """Lista de docs."""

    docs: list[dict]


class GenericSolrJson(BaseModel):
    """Elementos de detalhamento da resposta do json."""

    response: GenericSolrJsonResponseField
    debug: DebugField = None

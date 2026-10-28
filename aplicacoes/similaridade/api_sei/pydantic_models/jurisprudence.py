"""jurisprudence."""

from pydantic import BaseModel


class SolrJurisprudenceConfig(BaseModel):
    """Configuracoes para a API de Jurisprudência."""

    debug_query: str
    wt: str
    mlt_interesting_terms: str
    rows: int
    fl: str
    mindf: int
    mintf: int
    fl: str
    fq: str


class FoundIdsDocs(BaseModel):
    """Estrurura para os ids de documentos encontrados e os ids de documentos não encontrados."""

    id_docs_found: set
    id_docs_not_found: set

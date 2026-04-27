"""Recomenda es de documentos baseados em outros documentos ou texto."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status

from api_sei.middleware.custom_middleware import MiddlewareCustom
from api_sei.services.jurisprudence import doc2doc_search

router = APIRouter(route_class=MiddlewareCustom)

logger = logging.getLogger(__name__)


@router.get("/document-recommenders/mlt-recommender/recommendations")
async def get_doc2doc_search(
    text: str = Query(default=""),
    list_id_doc: list[int] = Query(default=[], example=[135629]),
    list_type_id_doc: list[int] = Query(
        default=[4, 7, 8, 19, 94], example=[4, 7, 8, 19, 94]
    ),
    rows: int = Query(default=10),
    *,
    include_citations: bool = Query(default=False),
    text_weight: float = Query(default=0.5, ge=0, le=1),
    normalized: bool = Query(default=False),
    # fq: List[str] = Query(default=[]),
    id_user: int = Query(example=1234, default=None),
) -> dict:
    """Retorna uma lista de recomenda es de documentos baseadas em outros documentos ou texto.

    Parameters
    ----------
    text: str
        Texto a ser utilizado para busca de recomenda es.
    list_id_doc: List[int]
        Lista de ids de documentos a serem utilizados para busca de recomenda es.
    list_type_id_doc: List[int]
        Lista de tipos de documentos a serem utilizados para busca de recomenda es.
    rows: int
        N mero de resultados a serem retornados.
    include_citations: bool
        Se True, inclui recomenda es de cota es.
    text_weight: float
        Peso da parte do texto na busca. Deve ser um valor entre 0 e 1.
    normalized: bool
        Se True, normaliza os scores dos resultados.
    fq: List[str]
        Filtro de pesquisa adicional.
    id_user: int
        Id do usu rio que solicitou a recomenda o.

    Returns:
    -------
    List[dict]
        Uma lista de dicion rios com os ids dos documentos mais semelhantes,
        o score do documento e o tipo de documento.
    """
    if not text and not list_id_doc:
        logger.error(
            Exception("list_id_doc ou text não podem ser ambos vazios"), exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="list_id_doc ou text não podem ser ambos vazios",
        )

    return doc2doc_search(
        list_id_doc=list_id_doc,
        list_type_id_doc=list_type_id_doc,
        rows=rows,
        text=text,
        include_citations=include_citations,
        text_weight=text_weight,
        normalized=normalized,
        fq=None,
        requested_at=datetime.now(tz=timezone.utc),
        id_user=id_user,
    )

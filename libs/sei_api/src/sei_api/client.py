from __future__ import annotations

from ._async import AsyncMixin
from ._base import BaseSeiClient
from ._documents import DocumentsMixin
from ._files import FilesMixin
from ._listings import ListingsMixin
from ._mutations import MutationsMixin
from ._processes import ProcessesMixin


class SeiApiClient(
    ListingsMixin,
    MutationsMixin,
    DocumentsMixin,
    AsyncMixin,
    ProcessesMixin,
    FilesMixin,
    BaseSeiClient,
):
    """Cliente HTTP unificado da API do SEI.

    Substitui os três forks de ``SEIDBHandler`` (etl, assistente, similaridade).
    Construa com uma ``SeiApiConfig`` e, opcionalmente, um ``timeout_exc_factory``
    (exceção de timeout do app) e um ``content_extractor`` ``(path, ext) -> str``
    para o caminho de anexos de e-mail, ligado a ``sei_extraction.extract_document``.
    """

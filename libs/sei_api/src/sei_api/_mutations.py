from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
import requests

from ._base import _decode_json_body

if TYPE_CHECKING:
    from ._protocol import _ClientInternals

    _Base = _ClientInternals
else:
    _Base = object

logger = logging.getLogger(__name__)

_ACCEPT_JSON = {"accept": "application/json"}


class MutationsMixin(_Base):
    """Endpoints de escrita do SEI (PUT e DELETE).

    Projetado para compor com ``BaseSeiClient`` via herança múltipla.
    Lê ``self.config`` (``SeiApiConfig``) e ``self._build_api_url``/
    ``self._build_params`` da base.
    """

    def md_ia_atualiza_documentos_indexaveis(self, id_documento: int) -> bool:
        """Sinaliza ao SEI que ``id_documento`` deve ser re-indexado.

        Returns:
            True quando o SEI respondeu 200 OK.
        """
        endpoint = "md_ia_atualiza_documentos_indexaveis"
        url = self._build_api_url(endpoint)
        params = self._build_params(endpoint, {"IdDocumento": id_documento})
        response = requests.put(
            url,
            params=params,
            verify=self.config.verify_ssl,
            timeout=self.config.timeout_s,
        )
        response.raise_for_status()
        return response.status_code == requests.codes.ok

    def md_ia_atualiza_processos_indexaveis(self, id_procedimento: int) -> bool:
        """Sinaliza ao SEI que ``id_procedimento`` deve ser re-indexado.

        Returns:
            True quando o SEI respondeu com ``status == "success"``.
            False em 404 (procedimento não encontrado) ou erro HTTP.
        """
        endpoint = "md_ia_atualiza_processos_indexaveis"
        url = self._build_api_url(endpoint)
        params = self._build_params(endpoint, {"IdProcedimento": str(id_procedimento)})
        try:
            response = requests.put(
                url,
                params=params,
                headers=_ACCEPT_JSON,
                verify=self.config.verify_ssl,
                timeout=self.config.timeout_s,
            )
            if response.status_code == requests.codes.not_found:
                return False
            response.raise_for_status()
            return _decode_json_body(response.content).get("status", "") == "success"
        except requests.exceptions.HTTPError:
            return False

    async def md_ia_remove_documentos_indexaveis_cancelados_async(
        self, id_documento: int
    ) -> bool:
        """Remove da fila de indexação o documento cancelado ``id_documento``.

        Returns:
            True quando o SEI respondeu com ``status == "success"``.
            False em 404 ou erro HTTP.
        """
        endpoint = "md_ia_remove_documentos_indexaveis_cancelados"
        url = self._build_api_url(endpoint)
        params = self._build_params(endpoint, {"IdDocumento": str(id_documento)})
        try:
            async with httpx.AsyncClient(
                verify=self.config.verify_ssl, timeout=self.config.timeout_s
            ) as client:
                response = await client.delete(url, params=params, headers=_ACCEPT_JSON)
                if response.status_code == 404:
                    logger.warning(f"Documento {id_documento} não encontrado (404)")
                    return False
                if response.status_code != 200:
                    response.raise_for_status()
                return (
                    _decode_json_body(response.content).get("status", "") == "success"
                )
        except httpx.HTTPError:
            return False

    async def md_ia_remove_processos_indexaveis_cancelados_async(
        self, id_procedimento: int
    ) -> bool:
        """Remove da fila de indexação o processo cancelado ``id_procedimento``.

        Returns:
            True quando o SEI respondeu com ``status == "success"``.
            False em 404 ou erro HTTP.
        """
        endpoint = "md_ia_remove_processos_indexaveis_cancelados"
        url = self._build_api_url(endpoint)
        params = self._build_params(endpoint, {"IdProcedimento": str(id_procedimento)})
        try:
            async with httpx.AsyncClient(
                verify=self.config.verify_ssl, timeout=self.config.timeout_s
            ) as client:
                response = await client.delete(url, params=params, headers=_ACCEPT_JSON)
                if response.status_code == 404:
                    logger.warning(f"Processo {id_procedimento} não encontrado (404)")
                    return False
                if response.status_code != 200:
                    response.raise_for_status()
                return (
                    _decode_json_body(response.content).get("status", "") == "success"
                )
        except httpx.HTTPError:
            return False

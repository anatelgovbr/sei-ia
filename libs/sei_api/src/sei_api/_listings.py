from __future__ import annotations

import logging
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

import pandas as pd
import requests

from ._base import _decode_json_body

if TYPE_CHECKING:
    from ._protocol import _ClientInternals

    _Base = _ClientInternals
else:
    _Base = object

logger = logging.getLogger(__name__)

_MSG_EMPTY_RESPONSE = "API retornou resposta vazia"


def _normalize_metadado(txt: str) -> str:
    """Normaliza o nome do metadado para casar com as chaves de ``mapa``.

    A API devolve a forma humana ("Tipo de Processo"); ``mapa`` usa a forma
    normalizada ("tipo_de_processo"). Espelha o ``clean_txt`` do ETL: minúsculas,
    ``strip``, espaços viram ``_`` e acentos são removidos.
    """
    base = txt.lower().strip().replace(" ", "_")
    return "".join(
        c for c in unicodedata.normalize("NFD", base) if unicodedata.category(c) != "Mn"
    )


def _fetch_documentos_elegiveis_single(
    base_url: str,
    sigla_sistema: str,
    identificacao_servico: str,
    verify_ssl: bool,
    timeout_s: int,
    id_procedimento: str,
) -> list[int]:
    """GET a um único IdProcedimento no endpoint de documentos elegíveis."""
    service_endpoint = "md_ia_lista_documentos_elegiveis_processos_similares"
    url = f"{base_url}/{service_endpoint}"
    params = {
        "servico": service_endpoint,
        "SiglaSistema": sigla_sistema,
        "IdentificacaoServico": identificacao_servico,
        "IdProcedimento": str(id_procedimento),
    }
    response = requests.get(url, params=params, verify=verify_ssl, timeout=timeout_s)
    response.raise_for_status()
    if not response.content or not response.content.strip():
        return []
    try:
        return _decode_json_body(response.content).get("data", [])
    except ValueError:
        logger.exception(f"API retornou resposta não-JSON: {response.text[:100]}")
        return []


class ListingsMixin(_Base):
    """Endpoints de listagem e consulta da API do SEI."""

    def health_check(self) -> bool:
        """Verifica se a API está acessível fazendo uma requisição de ping.

        Aceita qualquer resposta HTTP (200/404/500/503) como sinal de que a API
        está no ar. Retorna False apenas em falhas de conectividade.
        """
        try:
            url = self._build_api_url("md_ia_lista_tipo_documento")
            params = self._build_params("md_ia_lista_tipo_documento")
            response = requests.get(
                url, params=params, verify=self.config.verify_ssl, timeout=10
            )
            return response.status_code in [200, 404, 500, 503]
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.SSLError,
        ) as exc:
            logger.warning(f"API do SEI não está acessível: {exc}")
            return False
        except Exception as exc:
            logger.info(f"API do SEI respondeu mas com erro: {exc}")
            return True

    def md_ia_lista_tipo_documento(self) -> pd.DataFrame:
        """Lista tipos de documento cadastrados no SEI.

        Returns:
            DataFrame com colunas ``nome``, ``id_serie``.
        """
        service_endpoint = "md_ia_lista_tipo_documento"
        columns = ["nome", "id_serie"]

        def parse(doc: dict) -> dict:
            return {
                "nome": doc["TipoDocumento"],
                "id_serie": int(doc["IdTipoDocumento"]),
            }

        payload = self._request_json(service_endpoint)
        return self._parse_records(payload, columns, parse)

    def md_ia_lista_segmentos_documentos_relevantes(self) -> pd.DataFrame:
        """Lista segmentos de documentos relevantes com seus pesos.

        Returns:
            DataFrame com colunas ``id_md_ia_adm_doc_relev``, ``segmento``,
            ``id_type_doc``, ``relevancia``.
        """
        import pandas as pd

        service_endpoint = "md_ia_lista_segmentos_documentos_relevantes"
        columns = ["id_md_ia_adm_doc_relev", "segmento", "id_type_doc", "relevancia"]

        def parse(doc: dict) -> dict:
            return {
                "id_md_ia_adm_doc_relev": int(doc["IdDocumentoRelevante"]),
                "segmento": doc.get("SegmentoDocumento", ""),
                "id_type_doc": int(doc["IdTipoDocumentoRelevante"]),
                "relevancia": int(doc["PercentualRelevancia"]),
            }

        resp = self._request_raw(service_endpoint)

        if resp.status_code == 404:
            logger.info(
                "Pesos de segmentos não cadastrados. Usando configuração padrão."
            )
            return pd.DataFrame(columns=columns)

        if resp.content:
            resp.raise_for_status()
            api_response = _decode_json_body(resp.content)
            api_docs = api_response.get("data", [])
            if not api_docs:
                return pd.DataFrame(columns=columns)
            return pd.DataFrame([parse(doc) for doc in api_docs])

        logger.info(
            "Nenhum segmento de documento relevante encontrado. Retornando DataFrame vazio."
        )
        return pd.DataFrame(columns=columns)

    def md_ia_lista_percentual_relevancia_metadados(self) -> pd.DataFrame:
        """Lista metadados com seus percentuais de relevância para similaridade.

        Returns:
            DataFrame com colunas ``id_md_ia_adm_config_similar``, ``metadado``,
            ``relevancia``, ``dth_alteracao``, ``id_metadado``.
        """
        import datetime

        import pandas as pd

        service_endpoint = "md_ia_lista_percentual_relevancia_metadados"
        columns = [
            "id_md_ia_adm_config_similar",
            "metadado",
            "relevancia",
            "dth_alteracao",
        ]

        def parse(doc: dict) -> dict:
            return {
                "metadado": _normalize_metadado(str(doc["Metadado"])),
                "relevancia": int(doc["Relevancia"]),
                "id_md_ia_adm_config_similar": 1,
                "dth_alteracao": datetime.datetime.now().replace(microsecond=0),
            }

        resp = self._request_raw(service_endpoint)

        if resp.status_code == 404:
            logger.info(
                "Pesos de metadados não cadastrados. Usando configuração padrão."
            )
            return pd.DataFrame(columns=columns)

        resp.raise_for_status()
        api_response = _decode_json_body(resp.content)
        api_docs = api_response.get("data", [])
        if not api_docs:
            return pd.DataFrame(columns=columns)

        df = pd.DataFrame([parse(doc) for doc in api_docs])

        mapa = {
            "tipo_de_processo": "metadata_name_id_type_process",
            "unidade_geradora_do_processo": "metadata_id_unit_process_generator",
            "especificacao_do_processo": "metadata_process_specification",
            "interessado_do_processo": "metadata_id_contact_interested",
            "processos_relacionados": "metadata_info_related_processes",
            "tipos_de_documentos": "metadata_name_id_type_doc_",
            "citacoes": "metadata_citations",
        }
        df["metadado"] = df["metadado"].map(mapa)
        df["id_metadado"] = df.index.map(lambda x: x + 1)
        return df

    def get_subprocessos_id_protocolo(self, id_procedimento: int) -> pd.DataFrame:
        """Retorna os subprocessos anexados a um processo.

        Args:
            id_procedimento: ID do procedimento principal.

        Returns:
            DataFrame com colunas ``id_protocolo_2`` (subprocessos) e
            ``id_protocolo_1`` (processo principal).
        """
        import pandas as pd

        service_endpoint = "md_ia_consulta_processo"

        payload = self._request_json(
            service_endpoint, extra_params={"IdProcedimentos": id_procedimento}
        )
        api_docs = payload.get("data", [])

        if api_docs:
            processos_anexados = api_docs[0].get("IdProcessosAnexados", [])
            return pd.DataFrame(
                {
                    "id_protocolo_2": processos_anexados,
                    "id_protocolo_1": [id_procedimento] * len(processos_anexados),
                }
            )
        return pd.DataFrame(columns=["id_protocolo_2", "id_protocolo_1"])

    def md_ia_lista_processos_indexaveis(
        self,
        quantidade_registros: int | None = None,
        id_ultimo_registro: int | None = None,
    ) -> list[str]:
        """Lista processos elegíveis para indexação.

        Args:
            quantidade_registros: Limite de registros a retornar.
            id_ultimo_registro: Cursor de paginação (ID do último registro recebido).

        Returns:
            Lista de IDs de procedimentos.
        """
        service_endpoint = "md_ia_lista_processos_indexaveis"
        extra = {
            "QuantidadeRegistros": (
                None if not quantidade_registros else str(quantidade_registros)
            ),
            "IdUltimoRegistro": (
                None if not id_ultimo_registro else str(id_ultimo_registro)
            ),
        }
        resp = self._request_raw(service_endpoint, extra_params=extra)

        if resp.status_code == 404 or (
            resp.status_code == 200 and "Nenhum" in resp.text
        ):
            logger.info("Nenhum novo processo a ser indexado.")
            return []

        if resp.status_code != 200:
            resp.raise_for_status()

        if not resp.content or not resp.content.strip():
            logger.warning(_MSG_EMPTY_RESPONSE)
            return []

        try:
            return list(
                _decode_json_body(resp.content).get("data", {})["IdProcedimentos"]
            )
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {resp.text[:100]}")
            return []

    def md_ia_lista_processos_indexaveis_cancelados(
        self,
        quantidade_registros: int | None = None,
        id_ultimo_registro: int | None = None,
    ) -> tuple[list[Any], int]:
        """Lista processos que foram cancelados e devem ser removidos do índice.

        Args:
            quantidade_registros: Limite de registros a retornar.
            id_ultimo_registro: Cursor de paginação.

        Returns:
            Tupla ``(ids, id_ultimo_registro_entregue)``.
        """
        service_endpoint = "md_ia_lista_processos_indexaveis_cancelados"
        extra = {
            "QuantidadeRegistros": (
                None if not quantidade_registros else str(quantidade_registros)
            ),
            "IdUltimoRegistro": (
                None if not id_ultimo_registro else str(id_ultimo_registro)
            ),
        }
        resp = self._request_raw(service_endpoint, extra_params=extra)

        if resp.status_code == 404 or (
            resp.status_code == 200 and "Nenhum" in resp.text
        ):
            logger.info("Nenhum novo processo a ser cancelado.")
            return [], 0

        resp.raise_for_status()

        if not resp.content or not resp.content.strip():
            logger.warning(_MSG_EMPTY_RESPONSE)
            return [], 0

        try:
            data = _decode_json_body(resp.content).get("data", {})
            return data.get("IdProcedimentos", []), data.get(
                "IdUltimoRegistroEntregue", 0
            )
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {resp.text[:100]}")
            return [], 0

    def md_ia_lista_documentos_indexaveis(
        self,
        quantidade_registros: int | None = None,
        id_ultimo_registro: int | None = None,
    ) -> list[str]:
        """Lista documentos elegíveis para indexação.

        Args:
            quantidade_registros: Limite de registros a retornar.
            id_ultimo_registro: Cursor de paginação.

        Returns:
            Lista de IDs de documentos.
        """
        service_endpoint = "md_ia_lista_documentos_indexaveis"
        extra = {
            "QuantidadeRegistros": quantidade_registros,
            "IdUltimoRegistro": id_ultimo_registro,
        }
        resp = self._request_raw(service_endpoint, extra_params=extra)

        if resp.status_code == 404 or (
            resp.status_code == 200 and "Nenhum" in resp.text
        ):
            logger.info("Nenhum novo documento a ser indexado.")
            return []

        if resp.status_code != 200:
            resp.raise_for_status()

        if not resp.content or not resp.content.strip():
            logger.warning(_MSG_EMPTY_RESPONSE)
            return []

        try:
            return _decode_json_body(resp.content).get("data", {})["IdDocumentos"]
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {resp.text[:100]}")
            return []

    def md_ia_lista_documentos_indexaveis_cancelados(
        self,
        quantidade_registros: int | None = None,
        id_ultimo_registro: int | None = None,
    ) -> tuple[list[Any], int]:
        """Lista documentos que foram cancelados e devem ser removidos do índice.

        Args:
            quantidade_registros: Limite de registros a retornar.
            id_ultimo_registro: Cursor de paginação.

        Returns:
            Tupla ``(ids, id_ultimo_registro_entregue)``.
        """
        service_endpoint = "md_ia_lista_documentos_indexaveis_cancelados"
        extra = {
            "QuantidadeRegistros": (
                None if not quantidade_registros else str(quantidade_registros)
            ),
            "IdUltimoRegistro": (
                None if not id_ultimo_registro else str(id_ultimo_registro)
            ),
        }
        resp = self._request_raw(service_endpoint, extra_params=extra)

        if resp.status_code == 404 or (
            resp.status_code == 200 and "Nenhum" in resp.text
        ):
            logger.info("Nenhum novo documento a ser cancelado.")
            return [], 0

        if resp.status_code != 200:
            resp.raise_for_status()

        if not resp.content or not resp.content.strip():
            logger.warning(_MSG_EMPTY_RESPONSE)
            return [], 0

        try:
            data = _decode_json_body(resp.content).get("data", {})
            return data.get("IdDocumentos", []), data.get("IdUltimoRegistroEntregue", 0)
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {resp.text[:100]}")
            return [], 0

    def md_ia_lista_documentos_vetorizaveis(
        self,
        quantidade_registros: int | None = None,
        id_ultimo_registro: int | None = None,
    ) -> list[str]:
        """Lista documentos prontos para geração de embeddings.

        Args:
            quantidade_registros: Limite de registros a retornar.
            id_ultimo_registro: Cursor de paginação.

        Returns:
            Lista de IDs de documentos vetorizáveis.
        """
        service_endpoint = "md_ia_lista_documentos_vetorizaveis"
        extra = {
            "QuantidadeRegistros": quantidade_registros,
            "IdUltimoRegistro": id_ultimo_registro,
        }
        resp = self._request_raw(service_endpoint, extra_params=extra)

        if resp.status_code == 404 or (
            resp.status_code == 200 and "Nenhum" in resp.text
        ):
            logger.info("Nenhum novo documento a ser vetorizado.")
            return []

        if resp.status_code != 200:
            resp.raise_for_status()

        if not resp.content or not resp.content.strip():
            logger.warning(_MSG_EMPTY_RESPONSE)
            return []

        try:
            return _decode_json_body(resp.content).get("data", {})["IdDocumentos"]
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {resp.text[:100]}")
            return []

    def md_ia_lista_documentos_elegiveis_processos_similares(
        self,
        id_procedimento: str,
    ) -> list[int]:
        """Lista documentos elegíveis para o mecanismo de processos similares.

        Aceita um único ID ou múltiplos IDs separados por vírgula. Quando
        múltiplos IDs são fornecidos, faz chamadas individuais em paralelo
        (a API aceita um único ``IdProcedimento`` por requisição) e deduplica
        o resultado.

        Args:
            id_procedimento: ID ou IDs separados por vírgula.

        Returns:
            Lista ordenada e deduplicada de IDs de documentos.
        """
        if not id_procedimento or not str(id_procedimento).strip():
            return []

        ids = [pid.strip() for pid in str(id_procedimento).split(",") if pid.strip()]

        cfg = self.config

        def _fetch_single(pid: str) -> list[int]:
            return _fetch_documentos_elegiveis_single(
                base_url=cfg.base_url,
                sigla_sistema=cfg.sigla_sistema,
                identificacao_servico=cfg.identificacao_servico,
                verify_ssl=cfg.verify_ssl,
                timeout_s=int(cfg.timeout_s),
                id_procedimento=pid,
            )

        if len(ids) == 1:
            return _fetch_single(ids[0])

        all_docs: set[int] = set()
        with ThreadPoolExecutor(max_workers=min(len(ids), 5)) as executor:
            futures = {executor.submit(_fetch_single, pid): pid for pid in ids}
            for future in as_completed(futures):
                pid = futures[future]
                try:
                    all_docs.update(future.result())
                except Exception:
                    logger.warning(
                        f"Falha ao buscar documentos elegíveis para processo {pid}"
                    )

        return sorted(all_docs)

"""sei_db_handlers module."""

import asyncio
import datetime
import logging
import random
import re
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from pathlib import Path

import httpx
import pandas as pd
import requests
import urllib3
from requests.exceptions import JSONDecodeError, RequestException

from jobs.configs.parameters import utils
from jobs.envs import (
    SEI_API_BACKOFF_BASE,
    SEI_API_BACKOFF_MAX,
    SEI_API_DB_ADDRESS,
    SEI_API_DB_CHUNK_SIZE,
    SEI_API_DB_IDENTIFIER_SERVICE,
    SEI_API_DB_TIMEOUT,
    SEI_API_DB_USER,
    SEI_API_MAX_CONCURRENCY,
    SEI_API_MAX_RETRIES,
    VERIFY_SSL,
)

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SeiDBAPIError(Exception):
    """Exceção customizada para erros na chamada da API do SEI."""

    def __init__(self, status_code: int, detail: str):  # noqa: ANN204
        """Inicializa SeiDBAPIError com um código de status e mensagem de detalhe.

        Args:
            status_code (int): O código de status HTTP indicando o erro.
            detail (str): Uma mensagem detalhada descrevendo o erro.

        """
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


class SeiDBAPIUnavailableError(Exception):
    """Exceção customizada para quando a API do SEI está indisponível."""

    def __init__(self, detail: str = "API do SEI indisponível"):  # noqa: ANN204
        """Inicializa SeiDBAPIUnavailableError com uma mensagem de detalhe.

        Args:
            detail (str): Uma mensagem detalhada descrevendo o erro.

        """
        self.detail = detail
        super().__init__(detail)


def regexp_replace(value):
    return str(value).strip()


def group_concat_distinct(series):
    return ", ".join(sorted({str(x) for x in series if x}))


class SEIDBHandler:
    @staticmethod
    def _build_api_url(service_endpoint: str) -> str:
        return f"{SEI_API_DB_ADDRESS}/{service_endpoint}"

    @staticmethod
    def _build_params(service_endpoint: str, extra_params: dict | None = None) -> dict:
        params = {
            "servico": service_endpoint,
            "SiglaSistema": SEI_API_DB_USER,
            "IdentificacaoServico": SEI_API_DB_IDENTIFIER_SERVICE,
        }
        if extra_params:
            params.update(extra_params)
        return params

    @staticmethod
    def _check_api_health() -> bool:
        """Verifica se a API do SEI está ativa e respondendo.

        Returns:
            bool: True se a API está ativa, False caso contrário.
        """
        try:
            url = SEIDBHandler._build_api_url("md_ia_lista_tipo_documento")
            params = SEIDBHandler._build_params("md_ia_lista_tipo_documento")
            response = requests.get(url, params=params, verify=VERIFY_SSL, timeout=10)
            return response.status_code in [200, 404, 500, 503]
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.SSLError,
        ) as e:
            logger.warning(f"API do SEI não está acessível: {e}")
            return False
        except Exception as e:
            logger.info(f"API do SEI respondeu mas com erro: {e}")
            return True

    def _check_api_availability(func: callable) -> callable:
        """Decorador para verificar se a API está ativa antes de executar o método."""

        def wrapper(*args: tuple, **kwargs: dict):
            if not SEIDBHandler._check_api_health():
                logger.error("API do SEI está indisponível")
                raise SeiDBAPIUnavailableError("API do SEI está indisponível")
            return func(*args, **kwargs)

        return wrapper

    def _handle_api_errors(func: callable) -> callable:
        """Decorador para tratar erros comuns em chamadas de API."""

        @wraps(func)
        def wrapper(*args: tuple, **kwargs: dict) -> pd.DataFrame:
            try:
                return func(*args, **kwargs)
            except JSONDecodeError as json_exc:
                raise SeiDBAPIError(
                    status_code=requests.codes.bad_gateway,
                    detail=f"Resposta inválida da API (JSON mal formado): {json_exc}",
                ) from json_exc
            except RequestException as req_exc:
                status_code = getattr(
                    getattr(req_exc, "response", None), "status_code", 500
                )
                raise SeiDBAPIError(
                    status_code=status_code,
                    detail=(
                        f"Falha na requisição à API do SEI "
                        f"({req_exc.__class__.__name__}): {req_exc}"
                    ),
                ) from req_exc
            except Exception as exc:
                raise SeiDBAPIError(
                    status_code=500, detail=f"Erro inesperado: {exc}"
                ) from exc

        return wrapper

    @staticmethod
    def _parse_api_response(
        response: requests.Response, columns: list, parse_single_doc: callable
    ) -> pd.DataFrame:
        response.raise_for_status()
        response.encoding = "utf-8"
        api_response = response.json()
        api_docs = api_response.get("data", [])
        if not api_docs:
            return pd.DataFrame(columns=columns)
        parsed_data = [parse_single_doc(doc) for doc in api_docs]
        return pd.DataFrame(parsed_data)

    @staticmethod
    @_handle_api_errors
    def get_subprocessos_id_protocolo(id_procedimento: int) -> pd.DataFrame:
        """Consulta a API do SEI para obter os subprocessos anexados a um processo.

        Args:
            id_procedimento (int): ID do procedimento principal.

        Returns:
            pd.DataFrame: DataFrame com as colunas id_protocolo_2 (subprocessos)
                e id_protocolo_1 (processo principal).
        """
        service_endpoint = "md_ia_consulta_processo"

        def parse(api_docs: list) -> pd.DataFrame:
            if len(api_docs) > 0:
                processos_anexados = api_docs[0].get("IdProcessosAnexados", [])
                return pd.DataFrame(
                    {
                        "id_protocolo_2": processos_anexados,
                        "id_protocolo_1": [id_procedimento] * len(processos_anexados),
                    }
                )
            return pd.DataFrame(columns=["id_protocolo_2", "id_protocolo_1"])

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdProcedimentos": id_procedimento}
        )
        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=SEI_API_DB_TIMEOUT
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        api_response = response.json()

        return parse(api_response.get("data", []))

    @staticmethod
    @_handle_api_errors
    def md_ia_consulta_documento(
        id_documentos: str,
        conteudo: bool = True,
        sin_filtra_documentos_relevantes: str = "N",
        sin_filtra_bloqueados: str = "N",
        sin_filtra_ativos: str = "N",
        chunk_size: int = SEI_API_DB_CHUNK_SIZE,
    ) -> pd.DataFrame:
        """Consulta a API do SEI para obter a lista de documentos.

        Args:
            id_documentos: Identificador único do documento
            conteudo: Se é para retornar o conteúdo dos documentos
            sin_filtra_documentos_relevantes: Flag para filtrar documentos relevantes (S/N)
            sin_filtra_bloqueados: Flag para filtrar documentos bloqueados (S/N)
            sin_filtra_ativos: Flag para filtrar documentos ativos (S/N)
            chunk_size: Número de documentos a serem consultados por vez.

        Returns:
            pd.DataFrame: Dataframe com as colunas:
            - id_protocolo: Identificador único do procedimento
            - documento_especificacao: Especificação do documento
            - id_type_document: Identificador único do tipo de documento
            - content_doc: Conteúdo do documento
            - content_type: Tipo de conteúdo do documento (extensão do arquivo)
            - dta_inclusao: Data de inclusão do documento
            - name_id_type_doc: Nome do tipo de documento
            - id_protocolo_documento: Identificador único do documento
            - tipo: Tipo de documento (externo ou interno)

        Raises:
            SeiDBAPIError: Em caso de erro na requisição ou na resposta da API
        """
        service_endpoint = "md_ia_consulta_documento"
        columns = [
            "id_protocolo",
            "documento_especificacao",
            "id_type_document",
            "content_doc",
            "content_type",
            "dta_inclusao",
            "name_id_type_doc",
            "id_protocolo_documento",
        ]

        def parse(doc: dict) -> dict:
            return {
                "id_protocolo": int(doc["IdProcedimento"]),
                "documento_especificacao": doc.get("EspecificacaoDocumento") or "",
                "id_type_document": int(doc["IdTipoDocumento"]),
                "content_type": doc["NomeArquivo"].split(".")[-1]
                if "." in doc["NomeArquivo"]
                else "html",
                "dta_inclusao": pd.to_datetime(
                    doc["DataInclusao"], dayfirst=True
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "name_id_type_doc": doc.get("NomeTipoDocumento", ""),
                "id_protocolo_documento": int(doc["IdDocumento"]),
                "content_doc": "",
            }

        all_dfs = []
        # dict.fromkeys preserva ordem e elimina duplicatas antes de chunkar,
        # evitando URLs excessivamente longas que causam ConnectTimeout no SEI.
        id_list = list(
            dict.fromkeys(i.strip() for i in str(id_documentos).split(",") if i.strip())
        )

        for i in range(0, len(id_list), chunk_size):
            id_documentos_chunk = ",".join(id_list[i : i + chunk_size])

            url = SEIDBHandler._build_api_url(service_endpoint)
            params = SEIDBHandler._build_params(
                service_endpoint,
                {
                    "SinFiltraDocumentosRelevantes": sin_filtra_documentos_relevantes,
                    "SinFiltraBloqueados": sin_filtra_bloqueados,
                    "SinFiltraAtivos": sin_filtra_ativos,
                    "IdDocumentos": id_documentos_chunk,
                },
            )
            try:
                response = requests.get(
                    url, params=params, verify=VERIFY_SSL, timeout=SEI_API_DB_TIMEOUT
                )

                if response.status_code == requests.codes.not_found:
                    continue

                df_chunk = SEIDBHandler._parse_api_response(response, columns, parse)
                if not df_chunk.empty:
                    all_dfs.append(df_chunk)
            except requests.exceptions.HTTPError:
                logger.warning(f"HTTP error for document chunk {id_documentos_chunk}")
                continue

        if not all_dfs:
            return pd.DataFrame(columns=columns)

        df_metadata = pd.concat(all_dfs, ignore_index=True)

        if conteudo and not df_metadata.empty:

            async def fetch_content_limited(ids, limit: int):
                sem = asyncio.Semaphore(limit)
                limits = httpx.Limits(
                    max_connections=limit,
                    max_keepalive_connections=limit,
                )

                async with httpx.AsyncClient(
                    limits=limits,
                    verify=VERIFY_SSL,
                    timeout=int(SEI_API_DB_TIMEOUT),
                    http2=True,
                ) as client:

                    async def bound_fetch(_id):
                        async with sem:
                            try:
                                return await SEIDBHandler.md_ia_consulta_conteudo_documento_async(
                                    id_documento=_id,
                                    client=client,
                                )
                            except SeiDBAPIError:
                                return {"id_documento": _id, "content_doc": None}

                    return await asyncio.gather(*(bound_fetch(_id) for _id in ids))

            res_conteudo = asyncio.run(
                fetch_content_limited(
                    df_metadata["id_protocolo_documento"].tolist(),
                    limit=SEI_API_MAX_CONCURRENCY,
                )
            )
            content_map = {
                str(res.get("id_documento")): res.get("content_doc")
                for res in res_conteudo
                if res
            }
            df_metadata["content_doc"] = (
                df_metadata["id_protocolo_documento"].astype(str).map(content_map)
            )
        return df_metadata

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_segmentos_documentos_relevantes() -> pd.DataFrame:
        """Consulta a API do SEI para obter a lista de segmentos de documentos relevantes.

        Retorna um DataFrame com as colunas:
        - id_md_ia_adm_doc_relev: Identificador único do registro de documento relevante
        - segmento: Segmento do documento relevante
        - id_type_doc: Identificador do tipo de documento relevante
        - relevancia: Percentual de relevância do documento

        Returns:
            pd.DataFrame: DataFrame com os segmentos de documentos relevantes.
                         Retorna DataFrame vazio se não houver registros.

        Raises:
        - SeiDBAPIException: Em caso de erro na requisição ou na resposta da API
        """
        service_endpoint = "md_ia_lista_segmentos_documentos_relevantes"
        columns = ["id_md_ia_adm_doc_relev", "segmento", "id_type_doc", "relevancia"]

        def parse(doc: dict) -> dict:
            return {
                "id_md_ia_adm_doc_relev": int(doc["IdDocumentoRelevante"]),
                "segmento": doc.get("SegmentoDocumento", ""),
                "id_type_doc": int(doc["IdTipoDocumentoRelevante"]),
                "relevancia": int(doc["PercentualRelevancia"]),
            }

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(service_endpoint)
        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=SEI_API_DB_TIMEOUT
        )

        if response.status_code == 404:
            logger.info(
                "Pesos de segmentos não cadastrados. Usando configuração padrão."
            )
            return pd.DataFrame(columns=columns)

        if response.text:
            return SEIDBHandler._parse_api_response(response, columns, parse)

        logger.info(
            "Nenhum segmento de documento relevante encontrado na API do SEI. Retornando DataFrame vazio."
        )
        return pd.DataFrame(columns=columns)

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_tipo_documento() -> pd.DataFrame:
        """Consulta a API do SEI para obter a lista de tipos de documento.

        Retorna um DataFrame com as colunas:
        - nome: Nome do tipo de documento
        - id_serie: Identificador único do tipo de documento

        Raises:
        - SeiDBAPIException: Em caso de erro na requisição ou na resposta da API
        """
        service_endpoint = "md_ia_lista_tipo_documento"
        columns = ["nome", "id_serie"]

        def parse(doc: dict) -> dict:
            return {
                "nome": doc["TipoDocumento"],
                "id_serie": int(doc["IdTipoDocumento"]),
            }

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(service_endpoint)
        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=SEI_API_DB_TIMEOUT
        )
        return SEIDBHandler._parse_api_response(response, columns, parse)

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_percentual_relevancia_metadados() -> pd.DataFrame:
        """Consulta a API do SEI para obter a lista de metadados com suas respectivas relevâncias.

        Retorna um DataFrame com as colunas:
        - id_md_ia_adm_config_similar: Identificador único da configuração de similaridade
        - metadado: Nome do metadado
        - relevancia: Percentual de relevância do metadado
        - dth_alteracao: Data de alteração do percentual de relevância do metadado

        Raises:
        - SeiDBAPIException: Em caso de erro na requisição ou na resposta da API
        """
        service_endpoint = "md_ia_lista_percentual_relevancia_metadados"
        columns = [
            "id_md_ia_adm_config_similar",
            "metadado",
            "relevancia",
            "dth_alteracao",
        ]

        def parse(doc: dict) -> dict:
            return {
                "metadado": utils.clean_txt(doc["Metadado"]),
                "relevancia": int(doc["Relevancia"]),
                "id_md_ia_adm_config_similar": 1,
                "dth_alteracao": datetime.datetime.now().replace(microsecond=0),
            }

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(service_endpoint)
        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=SEI_API_DB_TIMEOUT
        )

        if response.status_code == 404:
            logger.info(
                "Pesos de metadados não cadastrados. Usando configuração padrão."
            )
            return pd.DataFrame(columns=columns)

        df = SEIDBHandler._parse_api_response(response, columns, parse)

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

    @staticmethod
    @_handle_api_errors
    def md_ia_consulta_processo(
        id_procedimentos: str, chunk_size: int = 50, **kwargs
    ) -> pd.DataFrame:
        """Consulta a API do SEI para obter os metadados de um processo.

        Args:
            id_procedimentos (str): IDs dos procedimentos, separados por vírgula.
            chunk_size (int): Número de procedimentos a serem consultados por vez.

        Retorna um DataFrame com as colunas:
        - id_protocolo
        - protocolo_formatado
        - processo_especificacao
        - interessado
        - name_interested
        - id_type_process
        - id_unit_process_generator
        - name_id_unit_process_generator
        - name_id_type_process
        - name_id_type_doc (fixo como None)

        Raises:
        - SeiDBAPIException: Em caso de erro na requisição ou na resposta da API
        """
        service_endpoint = "md_ia_consulta_processo"
        columns = [
            "id_protocolo",
            "protocolo_formatado",
            "processo_especificacao",
            "interessado",
            "name_interested",
            "id_type_process",
            "id_unit_process_generator",
            "name_id_unit_process_generator",
            "name_id_type_process",
        ]

        def parse(api_docs: list) -> pd.DataFrame:
            list_api_docs = []
            for api_doc in api_docs:
                interessados = api_doc.get("Interessados", [])
                interessado_id = (
                    interessados[0].get("IdInteressado") if interessados else None
                )
                interessado_nome = (
                    interessados[0].get("NomeInteressado") if interessados else None
                )
                list_api_docs.append(
                    {
                        "id_protocolo": api_doc.get("IdProcedimento"),
                        "protocolo_formatado": api_doc.get("ProtocoloFormatado"),
                        "processo_especificacao": api_doc.get("EspecificacaoProcesso"),
                        "interessado": interessado_id,
                        "name_interested": interessado_nome,
                        "id_type_process": api_doc.get("IdTipoProcesso"),
                        "id_unit_process_generator": api_doc.get(
                            "IdUnidadeGeradoraProcesso"
                        ),
                        "name_id_unit_process_generator": api_doc.get(
                            "DescricaoUnidadeGeradoraProcesso"
                        ),
                        "name_id_type_process": api_doc.get("TipoProcesso"),
                    }
                )

            return pd.DataFrame(list_api_docs)

        all_dfs = []
        id_list = [i.strip() for i in str(id_procedimentos).split(",") if i.strip()]

        for i in range(0, len(id_list), chunk_size):
            chunk = id_list[i : i + chunk_size]
            id_procedimentos_chunk = ",".join(chunk)

            url = SEIDBHandler._build_api_url(service_endpoint)
            params = SEIDBHandler._build_params(
                service_endpoint, {"IdProcedimentos": id_procedimentos_chunk}
            )
            response = requests.get(
                url, params=params, verify=VERIFY_SSL, timeout=SEI_API_DB_TIMEOUT
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            if response.text:
                api_response = response.json()
                df_chunk = parse(api_response.get("data", []))
                if not df_chunk.empty:
                    all_dfs.append(df_chunk)

        if not all_dfs:
            return pd.DataFrame(columns=columns)

        return pd.concat(all_dfs, ignore_index=True)

    @staticmethod
    @_handle_api_errors
    def md_ia_atualiza_processos_indexaveis(id_procedimento: int) -> bool:
        """Atualiza a lista de processos indexáveis no sistema.

        Args:
            id_procedimento (int): ID do procedimento a ser atualizado.

        Returns:
            bool: True se a atualização foi bem sucedida, False caso contrário ou se o procedimento não for encontrado (404).

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API.
        """
        service_endpoint = "md_ia_atualiza_processos_indexaveis"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdProcedimento": str(id_procedimento)}
        )
        try:
            response = requests.put(
                url,
                params=params,
                headers={"accept": "application/json"},
                verify=VERIFY_SSL,
                timeout=int(SEI_API_DB_TIMEOUT),
            )

            if response.status_code == requests.codes.not_found:
                return False

            response.raise_for_status()
            api_response = response.json()
            return api_response.get("status", "") == "success"
        except requests.exceptions.HTTPError:
            return False

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_processos_indexaveis(
        quantidade_registros: int | None = None, id_ultimo_registro: int | None = None
    ) -> list[str]:
        """Retorna lista de processos que podem ser indexados pelo sistema.

        Returns:
            pd.DataFrame: DataFrame contendo a lista de processos indexáveis.

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API.
        """
        service_endpoint = "md_ia_lista_processos_indexaveis"

        def parse(doc: dict) -> dict:
            return list(doc["IdProcedimentos"])

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint,
            {
                "QuantidadeRegistros": None
                if not quantidade_registros
                else str(quantidade_registros),
                "IdUltimoRegistro": None
                if not id_ultimo_registro
                else str(id_ultimo_registro),
            },
        )
        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
        )

        if response.status_code == 404 or (
            response.status_code == 200 and "Nenhum" in response.text
        ):
            logger.info("Nenhum novo processo a ser indexado.")
            return []

        if response.status_code != 200:
            response.raise_for_status()

        response.encoding = "utf-8"

        if not response.text or not response.text.strip():
            logger.warning("API retornou resposta vazia")
            return []

        try:
            api_response = response.json()
            return parse(api_response.get("data", {}))
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {response.text[:100]}")
            return []

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_documentos_elegiveis_processos_similares(
        id_procedimento: str,
    ) -> list[int]:
        """Retorna lista de documentos elegíveis para processos similares.

        Aceita um único ID ou múltiplos IDs separados por vírgula. Quando
        múltiplos IDs são fornecidos, realiza chamadas individuais em paralelo
        via ThreadPoolExecutor (a API SEI aceita apenas um IdProcedimento por
        requisição).

        Args:
            id_procedimento (str): ID do procedimento ou IDs separados por vírgula.

        Returns:
            list[int]: Lista deduplicada de IDs de documentos elegíveis.
        """
        if not id_procedimento or not str(id_procedimento).strip():
            return []

        ids = [pid.strip() for pid in str(id_procedimento).split(",") if pid.strip()]

        if len(ids) == 1:
            return SEIDBHandler._fetch_documentos_elegiveis_single(ids[0])

        # A API SEI aceita apenas um IdProcedimento por chamada.
        # Fan-out paralelo via ThreadPoolExecutor: I/O-bound, requests é
        # thread-safe, sem risco de conflito com event loop do Airflow/Celery.
        all_docs: set[int] = set()
        with ThreadPoolExecutor(max_workers=min(len(ids), 5)) as executor:
            futures = {
                executor.submit(
                    SEIDBHandler._fetch_documentos_elegiveis_single, pid
                ): pid
                for pid in ids
            }
            for future in as_completed(futures):
                pid = futures[future]
                try:
                    all_docs.update(future.result())
                except Exception:
                    logger.warning(
                        f"Falha ao buscar documentos elegíveis para processo {pid}"
                    )

        return sorted(all_docs)

    @staticmethod
    def _fetch_documentos_elegiveis_single(id_procedimento: str) -> list[int]:
        """Faz a chamada HTTP para um único IdProcedimento."""
        service_endpoint = "md_ia_lista_documentos_elegiveis_processos_similares"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdProcedimento": str(id_procedimento)}
        )
        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
        )

        response.raise_for_status()

        if not response.text or not response.text.strip():
            return []

        try:
            api_response = response.json()
            return api_response.get("data", [])
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {response.text[:100]}")
            return []

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_processos_indexaveis_cancelados(
        quantidade_registros: int | None = None, id_ultimo_registro: int | None = None
    ) -> list[str]:
        """Retorna lista de processos indexáveis cancelados.

        Returns:
            pd.DataFrame: DataFrame contendo a lista de processos indexáveis cancelados.

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API.
        """

        def _parse(dict_cancelados: dict):
            ids = dict_cancelados.get("IdProcedimentos", [])
            id_ultimo = dict_cancelados.get("IdUltimoRegistroEntregue", 0)

            return ids, id_ultimo

        service_endpoint = "md_ia_lista_processos_indexaveis_cancelados"
        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint,
            {
                "QuantidadeRegistros": None
                if not quantidade_registros
                else str(quantidade_registros),
                "IdUltimoRegistro": None
                if not id_ultimo_registro
                else str(id_ultimo_registro),
            },
        )
        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
        )

        if response.status_code == 404 or (
            response.status_code == 200 and "Nenhum" in response.text
        ):
            logger.info("Nenhum novo processo a ser cancelado.")
            return [], 0

        response.raise_for_status()
        response.encoding = "utf-8"

        if not response.text or not response.text.strip():
            logger.warning("API retornou resposta vazia")
            return [], 0

        try:
            api_response = response.json()
            return _parse(api_response.get("data", {}))
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {response.text[:100]}")
            return [], 0

    @staticmethod
    @_handle_api_errors
    async def md_ia_remove_processos_indexaveis_cancelados(
        id_procedimento: int,
    ) -> bool:
        """Remove processos indexáveis cancelados do sistema.

        Args:
            id_procedimento (int): ID do procedimento a ser removido.

        Returns:
            bool: True se a remoção foi bem sucedida, False caso contrário.

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API.
        """
        service_endpoint = "md_ia_remove_processos_indexaveis_cancelados"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdProcedimento": str(id_procedimento)}
        )
        try:
            async with httpx.AsyncClient(
                verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
            ) as client:
                response = await client.delete(
                    url, params=params, headers={"accept": "application/json"}
                )

                if response.status_code == 404:
                    logger.warning(f"Processo {id_procedimento} não encontrado (404)")
                    return False
                if response.status_code != 200:
                    response.raise_for_status()

                api_response = response.json()
                return api_response.get("status", "") == "success"
        except httpx.HTTPError:
            return False

    @staticmethod
    @_handle_api_errors
    def get_process_metadata(
        id_procedimento: str, chunk_size: int = 50
    ) -> pd.DataFrame:
        """Consulta a API do SEI para obter os metadados de um processo.

        Args:
            id_procedimento (str): IDs dos procedimentos a serem consultados, separados por vírgula.
            chunk_size (int): Número de procedimentos a serem consultados por vez.

        Returns:
            pd.DataFrame: DataFrame contendo os metadados do processo, incluindo protocolo, especificação, interessado e processos relacionados.
        """
        service_endpoint = "md_ia_consulta_processo"
        colunas = [
            "id_protocolo",
            "protocolo_formatado",
            "processo_especificacao",
            "interessado",
            "processos_relacionados_1",
            "processos_relacionados_2",
            "id_type_process",
            "id_unit_process_generator",
            "name_id_type_process",
        ]

        def parse(api_dicts: list) -> pd.DataFrame:
            records = []
            for api_dict in api_dicts:
                processos_anexados = api_dict.get("IdProcessosAnexados") or []
                processos_pai = api_dict.get("ProcessosPaiRelacionado") or []
                descricao_pai_concatenada = "; ".join(
                    p.get("Especificacao") or "" for p in processos_pai
                )
                interessado_id = (
                    api_dict["Interessados"][0]["IdInteressado"]
                    if api_dict.get("Interessados")
                    else None
                )
                if len(processos_anexados) > 0:
                    for proc_rel_1 in processos_anexados:
                        records.append(
                            {
                                "id_protocolo": api_dict["IdProcedimento"],
                                "protocolo_formatado": api_dict["NumeroProcesso"],
                                "processo_especificacao": api_dict[
                                    "EspecificacaoProcesso"
                                ]
                                or api_dict["TipoProcesso"],
                                "interessado": interessado_id,
                                "processos_relacionados_1": int(proc_rel_1),
                                "processos_relacionados_2": descricao_pai_concatenada,
                                "id_type_process": api_dict["IdTipoProcesso"],
                                "id_unit_process_generator": api_dict[
                                    "IdUnidadeGeradoraProcesso"
                                ],
                                "name_id_type_process": api_dict["TipoProcesso"],
                            }
                        )
                else:
                    records.append(
                        {
                            "id_protocolo": api_dict["IdProcedimento"],
                            "protocolo_formatado": api_dict["NumeroProcesso"],
                            "processo_especificacao": api_dict["EspecificacaoProcesso"]
                            or api_dict["TipoProcesso"],
                            "interessado": interessado_id,
                            "processos_relacionados_1": None,
                            "processos_relacionados_2": descricao_pai_concatenada,
                            "id_type_process": api_dict["IdTipoProcesso"],
                            "id_unit_process_generator": api_dict[
                                "IdUnidadeGeradoraProcesso"
                            ],
                            "name_id_type_process": api_dict["TipoProcesso"],
                        }
                    )
            return pd.DataFrame(records, columns=colunas)

        all_dfs = []
        id_list = [i.strip() for i in str(id_procedimento).split(",") if i.strip()]

        url = SEIDBHandler._build_api_url(service_endpoint)

        for i in range(0, len(id_list), chunk_size):
            chunk = id_list[i : i + chunk_size]
            id_procedimentos_chunk = ",".join(chunk)

            params = SEIDBHandler._build_params(
                service_endpoint, {"IdProcedimentos": id_procedimentos_chunk}
            )
            response = requests.get(
                url, params=params, verify=VERIFY_SSL, timeout=SEI_API_DB_TIMEOUT
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            if response.text:
                api_response = response.json()
                df_chunk = parse(api_response.get("data", []))
                if not df_chunk.empty:
                    all_dfs.append(df_chunk)

        if not all_dfs:
            return pd.DataFrame(columns=colunas)

        return pd.concat(all_dfs, ignore_index=True)

    @staticmethod
    @_handle_api_errors
    def md_ia_download_arquivo_documento_externo(
        id_documento: str, doc_extension: str, id_anexo: int | None = None
    ) -> str:
        """Faz o download do arquivo de um documento externo do SEI ou anexo.

        Args:
            id_documento (str): ID do documento a ser baixado.
            doc_extension (str): Extensão esperada do arquivo (ex: "pdf").
            id_anexo (Optional[int]): ID do anexo (opcional; se fornecido, baixa o anexo específico).

        Returns:
            str: Caminho completo do arquivo salvo em /tmp/.

        Raises:
            SeiDBAPIError: Em caso de erro na requisição ou na resposta da API.
        """
        service_endpoint = "md_ia_download_arquivo_documento_externo"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdDocumento": id_documento}
        )
        if id_anexo is not None:
            params["IdAnexo"] = id_anexo

        response = requests.get(
            url,
            params=params,
            headers={"accept": "*/*"},
            verify=VERIFY_SSL,
            timeout=int(SEI_API_DB_TIMEOUT),
        )
        response.raise_for_status()

        content_disp = response.headers.get("content-disposition", "")
        logger.debug(f"Content-Disposition header: {content_disp}")

        filename_match = re.search(r'filename="(.+?)"', content_disp)
        if filename_match:
            raw_filename = filename_match.group(1)
            raw_filename = re.sub(r'[<>:"/\\|?*]', "_", raw_filename)
            raw_filename = re.sub(r"<[^>]+>", "", raw_filename)
            if len(raw_filename) > 100:
                raw_filename = raw_filename[:100]
            filename = raw_filename.strip()
        else:
            filename = f"doc_{id_documento}_{uuid.uuid4()}.{doc_extension}"

        if not filename.endswith(f".{doc_extension}"):
            filename = f"{filename}.{doc_extension}"

        save_path = Path("/tmp") / filename
        with save_path.open("wb") as f:
            f.write(response.content)

        logger.debug(
            f"Documento {id_documento} (anexo {id_anexo}) salvo em '{save_path}'"
        )
        return str(save_path)

    @staticmethod
    def _process_email_with_attachments(
        id_documento: str, xml_content: str, id_anexos: list[int]
    ) -> str:
        """Processa e-mail com anexos, retornando conteúdo augmentado.

        Fluxo:
        1. Parseia XML para mapear IdAnexo → filename
        2. Constrói conteúdo augmentado com email principal
        3. Processa cada anexo e extrai texto de acordo com a extensão

        Args:
            id_documento: ID do documento principal
            xml_content: XML do e-mail
            id_anexos: Lista de IDs dos anexos

        Returns:
            str: Conteúdo augmentado com anexos processados
        """
        # Import local para evitar import circular
        from jobs.document_extraction.parsers import (
            office_parser,
            pdf_parser,
            spreadsheet_parser,
        )

        try:
            root = ET.fromstring(xml_content)  # noqa: S314
            anexos = root.findall(".//atributo[@nome='Anexos']/valores/valor")
            anexo_map = {
                val.get("id"): val.text for val in anexos if val.get("id") and val.text
            }
        except ET.ParseError:
            logger.warning(f"Erro ao parsear XML de anexos do doc {id_documento}")
            anexo_map = {}

        augmented_content = f"<conteudo_principal_do_email>\n{xml_content}\n</conteudo_principal_do_email>\n"
        for idx, id_anexo in enumerate(id_anexos, start=1):
            filename = anexo_map.get(str(id_anexo), f"anexo_{id_anexo}.unknown")
            extension = Path(filename).suffix.lstrip(".").lower()

            try:
                file_path = SEIDBHandler.md_ia_download_arquivo_documento_externo(
                    id_documento, extension, id_anexo
                )

                if extension == "pdf":
                    anexo_text = pdf_parser.extract_text(file_path)
                elif extension in ["xlsx", "xls", "xlsb", "xlsm", "ods"]:
                    anexo_text = spreadsheet_parser.extract_text(file_path)
                elif extension in [
                    "docx",
                    "pptx",
                    "html",
                    "htm",
                    "csv",
                    "odt",
                    "odp",
                    "doc",
                    "json",
                    "ppt",
                    "rtf",
                    "txt",
                ]:
                    anexo_text = office_parser.extract_text(file_path)
                else:
                    with Path(file_path).open(
                        "r", encoding="utf-8", errors="ignore"
                    ) as f:
                        anexo_text = f.read()

                augmented_content += f"<anexo_{idx} - {filename}>\n{anexo_text}\n</anexo_{idx} - {filename}>\n"
                Path(file_path).unlink(missing_ok=True)

            except Exception as e:
                logger.exception(f"Erro ao processar anexo {id_anexo}: {e}")

        return augmented_content

    @staticmethod
    async def md_ia_consulta_conteudo_documento_async(
        id_documento: str, client: httpx.AsyncClient = None
    ) -> dict:
        """Versão assíncrona da consulta à API do SEI para obter o conteúdo de um documento.

        Retorna um dicionário com as chaves:
        - id_documento: Identificador único do documento
        - tipo_conteudo: Tipo de conteúdo do documento
        - content_doc: Conteúdo do documento

        Args:
            id_documento (str): Identificador único do documento a ser consultado.

        Raises:
            SeiDBAPIError: Em caso de erro na requisição ou na resposta da API
        """
        logger.info(
            f"🔍 [API BREAKPOINT 1] Iniciando md_ia_consulta_conteudo_documento_async para doc {id_documento}"
        )

        service_endpoint = "md_ia_consulta_conteudo_documento"
        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdDocumento": id_documento}
        )

        logger.info(f"🔍 [API BREAKPOINT 2] URL: {url}")
        logger.info(f"🔍 [API BREAKPOINT 2.1] Params: {params}")

        try:
            backoff_seconds = float(SEI_API_BACKOFF_BASE)
            attempt = 0
            while True:
                attempt += 1
                try:
                    if client is None:
                        limits = httpx.Limits(
                            max_connections=SEI_API_MAX_CONCURRENCY,
                            max_keepalive_connections=SEI_API_MAX_CONCURRENCY,
                        )
                        async with httpx.AsyncClient(
                            limits=limits,
                            verify=VERIFY_SSL,
                            timeout=int(SEI_API_DB_TIMEOUT),
                            http2=True,
                        ) as temp_client:
                            response = await temp_client.get(
                                url,
                                params=params,
                                headers={"accept": "application/json"},
                            )
                    else:
                        response = await client.get(
                            url, params=params, headers={"accept": "application/json"}
                        )

                    logger.info(
                        f"🔍 [API BREAKPOINT 3] Status HTTP: {response.status_code}"
                    )
                    logger.info(
                        f"🔍 [API BREAKPOINT 3.1] Response text length: {len(response.text) if response.text else 0}"
                    )

                    if response.status_code == 404:
                        logger.warning(
                            f"⚠️ [API BREAKPOINT 4] Conteúdo do documento {id_documento} não encontrado (404)"
                        )
                        return {"id_documento": id_documento, "content_doc": None}

                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        sleep_time = (
                            float(retry_after)
                            if retry_after
                            else backoff_seconds + random.random()  # noqa: S311
                        )
                        logger.info(
                            f"🔍 [API BREAKPOINT 5] Rate limit (429), aguardando {sleep_time}s..."
                        )
                        await asyncio.sleep(sleep_time)
                        backoff_seconds = min(
                            backoff_seconds * 2, float(SEI_API_BACKOFF_MAX)
                        )
                        if attempt < int(SEI_API_MAX_RETRIES):
                            continue
                        response.raise_for_status()

                    if 500 <= response.status_code < 600:
                        logger.warning(
                            f"⚠️ [API BREAKPOINT 6] Erro 5xx: {response.status_code}, tentativa {attempt}"
                        )
                        if attempt < int(SEI_API_MAX_RETRIES):
                            await asyncio.sleep(backoff_seconds + random.random())  # noqa: S311
                            backoff_seconds = min(
                                backoff_seconds * 2, float(SEI_API_BACKOFF_MAX)
                            )
                            continue
                        response.raise_for_status()

                    response.raise_for_status()

                    logger.info("🔍 [API BREAKPOINT 7] Resposta OK, parseando JSON...")

                    if response.text:
                        api_response = response.json()
                        logger.info("🔍 [API BREAKPOINT 8] JSON parseado com sucesso")
                        logger.info(
                            f"🔍 [API BREAKPOINT 8.1] API Response keys: {api_response.keys()}"
                        )

                        data = api_response.get("data", {})
                        logger.info(
                            f"🔍 [API BREAKPOINT 9] Data keys: {data.keys() if data else 'VAZIO'}"
                        )

                        content_doc = data.get("ConteudoDocumento")
                        tipo_conteudo = data.get("TipoConteudo")

                        logger.info(
                            f"🔍 [API BREAKPOINT 10] ConteudoDocumento length: {len(content_doc) if content_doc else 0}"
                        )
                        logger.info(
                            f"🔍 [API BREAKPOINT 10.1] TipoConteudo: {tipo_conteudo}"
                        )
                        logger.info(
                            f"🔍 [API BREAKPOINT 10.2] Primeiros 200 chars do conteúdo: {content_doc[:200] if content_doc else 'VAZIO'}"
                        )

                        if data.get("IdAnexos"):
                            logger.info(
                                f"🔍 [API BREAKPOINT 11] Documento {id_documento} possui {len(data['IdAnexos'])} anexo(s), processando..."
                            )
                            content_doc = SEIDBHandler._process_email_with_attachments(
                                id_documento=id_documento,
                                xml_content=content_doc,
                                id_anexos=data["IdAnexos"],
                            )

                        result = {
                            "id_documento": id_documento,
                            "tipo_conteudo": tipo_conteudo,
                            "content_doc": content_doc,
                        }

                        logger.info(
                            f"🔍 [API BREAKPOINT 12] Retornando resultado: content_doc={len(content_doc) if content_doc else 0} chars"
                        )
                        return result

                    logger.warning(
                        "⚠️ [API BREAKPOINT 13] Response.text VAZIO, retornando None"
                    )
                    return {"id_documento": id_documento, "content_doc": None}
                except (httpx.ConnectTimeout, httpx.ReadTimeout):
                    if attempt < int(SEI_API_MAX_RETRIES):
                        await asyncio.sleep(backoff_seconds + random.random())  # noqa: S311
                        backoff_seconds = min(
                            backoff_seconds * 2, float(SEI_API_BACKOFF_MAX)
                        )
                        continue
                    raise
        except httpx.HTTPError as e:
            status_code = getattr(getattr(e, "response", None), "status_code", 500)
            logger.exception(
                f"Erro ao consultar conteúdo do documento {id_documento}: "
                f"{e.__class__.__name__}: {e}"
            )
            raise SeiDBAPIError(
                status_code=status_code,
                detail=f"Falha na requisição à API do SEI ({e.__class__.__name__}): {e}",
            ) from e

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_documentos_indexaveis(
        quantidade_registros: int | None = None, id_ultimo_registro: int | None = None
    ) -> list[str]:
        service_endpoint = "md_ia_lista_documentos_indexaveis"

        def parse(doc: dict) -> dict:
            return doc["IdDocumentos"]

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint,
            {
                "QuantidadeRegistros": quantidade_registros,
                "IdUltimoRegistro": id_ultimo_registro,
            },
        )
        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
        )

        if response.status_code == 404 or (
            response.status_code == 200 and "Nenhum" in response.text
        ):
            logger.info("Nenhum novo documento a ser indexado.")
            return []

        if response.status_code != 200:
            response.raise_for_status()

        response.encoding = "utf-8"

        if not response.text or not response.text.strip():
            logger.warning("API retornou resposta vazia")
            return []

        try:
            api_response = response.json()
            return parse(api_response.get("data", {}))
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {response.text[:100]}")
            return []

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_documentos_indexaveis_cancelados(
        quantidade_registros: int | None = None, id_ultimo_registro: int | None = None
    ) -> list[str]:
        """Retorna lista de documentos indexáveis cancelados.

        Returns:
            tuple: Tupla contendo (lista de IDs de documentos, ID do último registro entregue).

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API.
        """

        def _parse(dict_cancelados: dict):
            ids = dict_cancelados.get("IdDocumentos", [])
            id_ultimo = dict_cancelados.get("IdUltimoRegistroEntregue", 0)

            return ids, id_ultimo

        service_endpoint = "md_ia_lista_documentos_indexaveis_cancelados"
        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint,
            {
                "QuantidadeRegistros": None
                if not quantidade_registros
                else str(quantidade_registros),
                "IdUltimoRegistro": None
                if not id_ultimo_registro
                else str(id_ultimo_registro),
            },
        )
        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
        )

        if response.status_code == 404 or (
            response.status_code == 200 and "Nenhum" in response.text
        ):
            logger.info("Nenhum novo documento a ser cancelado.")
            return [], 0

        if response.status_code != 200:
            response.raise_for_status()

        response.encoding = "utf-8"

        if not response.text or not response.text.strip():
            logger.warning("API retornou resposta vazia")
            return [], 0

        try:
            api_response = response.json()
            return _parse(api_response.get("data", {}))
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {response.text[:100]}")
            return [], 0

    @staticmethod
    @_handle_api_errors
    def md_ia_atualiza_documentos_indexaveis(id_documento: int) -> bool:
        service_endpoint = "md_ia_atualiza_documentos_indexaveis"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdDocumento": id_documento}
        )
        response = requests.put(
            url, params=params, verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
        )

        response.raise_for_status()

        return response.status_code == requests.codes.ok

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_documentos_vetorizaveis(
        quantidade_registros: int | None = None, id_ultimo_registro: int | None = None
    ) -> list[str]:
        """Retorna lista de documentos que podem ser vetorizados (embeddings) pelo sistema.

        Args:
            quantidade_registros (int): Quantidade de registros a serem retornados.
            id_ultimo_registro (int): ID do último registro retornado na chamada anterior.

        Returns:
            list[str]: Lista contendo IDs de documentos vetorizáveis.

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API.
        """
        service_endpoint = "md_ia_lista_documentos_vetorizaveis"

        def parse(doc: dict) -> list[str]:
            return doc["IdDocumentos"]

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint,
            {
                "QuantidadeRegistros": quantidade_registros,
                "IdUltimoRegistro": id_ultimo_registro,
            },
        )

        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
        )

        # Verificar se não há documentos (404 OU 200 com mensagem de texto)
        if response.status_code == 404 or (
            response.status_code == 200 and "Nenhum" in response.text
        ):
            logger.info("Nenhum novo documento a ser vetorizado.")
            return []

        if response.status_code != 200:
            response.raise_for_status()

        response.encoding = "utf-8"

        # Validar se a resposta é JSON válido antes de parsear
        if not response.text or not response.text.strip():
            logger.warning("API retornou resposta vazia")
            return []

        try:
            api_response = response.json()
            return parse(api_response.get("data", {}))
        except ValueError:
            logger.exception(f"API retornou resposta não-JSON: {response.text[:100]}")
            return []

    @staticmethod
    async def md_ia_atualiza_documentos_vetorizaveis_async(id_documento: int) -> bool:
        """Versão assíncrona - atualiza o status de vetorização de um documento no sistema SEI.

        Args:
            id_documento (int): ID do documento a ser atualizado.

        Returns:
            bool: True se a atualização foi bem sucedida, False caso contrário.

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API.
        """
        service_endpoint = "md_ia_atualiza_documentos_vetorizaveis"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdDocumento": id_documento}
        )

        try:
            async with httpx.AsyncClient(
                verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
            ) as client:
                response = await client.put(url, params=params)
                response.raise_for_status()
                return response.status_code == 200
        except httpx.HTTPError:
            logger.exception(f"Erro ao atualizar documento {id_documento}")
            return False

    @staticmethod
    async def md_ia_remove_documentos_indexaveis_cancelados(id_documento: int) -> bool:
        """Remove documentos indexáveis cancelados do sistema.

        Args:
            id_documento (int): ID do documento a ser removido.

        Returns:
            bool: True se a remoção foi bem sucedida, False caso contrário.

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API.
        """
        service_endpoint = "md_ia_remove_documentos_indexaveis_cancelados"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdDocumento": str(id_documento)}
        )
        try:
            async with httpx.AsyncClient(
                verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
            ) as client:
                response = await client.delete(
                    url, params=params, headers={"accept": "application/json"}
                )

                if response.status_code == 404:
                    logger.warning(f"Documento {id_documento} não encontrado (404)")
                    return False
                if response.status_code != 200:
                    response.raise_for_status()

                api_response = response.json()
                return api_response.get("status", "") == "success"
        except httpx.HTTPError:
            return False

    @staticmethod
    async def md_ia_consulta_processo_async(id_procedimentos: str) -> pd.DataFrame:
        """Versão assíncrona de md_ia_consulta_processo usando httpx.

        Args:
            id_procedimentos: String com IDs de procedimentos separados por vírgula

        Returns:
            DataFrame com metadados dos processos
        """
        service_endpoint = "md_ia_consulta_processo"
        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint,
            {
                "SinFiltraAtivos": "N",
                "SinFiltraBloqueados": "N",
                "SinFiltraDocumentosRelevantes": "N",
                "IdProcedimentos": id_procedimentos,
            },
        )

        async with httpx.AsyncClient(
            verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data_list = response.json().get("data", {})

        data_list_to_parse = []
        for data in data_list:
            protocolo_formatado = data.get("NumeroProcesso") or ""
            processo_especificacao = data.get("EspecificacaoProcesso") or ""
            nome_id_tipo_processo = data.get("TipoProcesso") or ""
            sigla_unid = data.get("SiglaUnidadeGeradoraProcesso") or ""
            desc_unid = data.get("DescricaoUnidadeGeradoraProcesso") or ""

            processos_pai = data.get("ProcessosPaiRelacionado") or []
            processos_filho = data.get("ProcessosFilhoRelacionado") or []

            linhas = []

            if processos_pai and processos_filho:
                for pai in processos_pai:
                    for filho in processos_filho:
                        linhas.append(
                            {
                                "id_procedimento": data.get("IdProcedimento"),
                                "id_protocolo_formatado": protocolo_formatado,
                                "processo_especificacao": processo_especificacao,
                                "nome_id_tipo_processo": nome_id_tipo_processo,
                                "rp1p_descricao": pai.get("Especificacao") or "",
                                "rp2p_descricao": filho.get("Especificacao") or "",
                                "rp1u_sigla": pai.get("SiglaUnidadeGeradoraProcesso")
                                or "",
                                "rp2u_sigla": filho.get("SiglaUnidadeGeradoraProcesso")
                                or "",
                                "sigla_unid": sigla_unid,
                                "desc_unid": desc_unid,
                            }
                        )
            elif processos_pai:
                for pai in processos_pai:
                    linhas.append(
                        {
                            "id_procedimento": data.get("IdProcedimento"),
                            "id_protocolo_formatado": protocolo_formatado,
                            "processo_especificacao": processo_especificacao,
                            "nome_id_tipo_processo": nome_id_tipo_processo,
                            "rp1p_descricao": pai.get("Especificacao") or "",
                            "rp2p_descricao": "",
                            "rp1u_sigla": pai.get("SiglaUnidadeGeradoraProcesso") or "",
                            "rp2u_sigla": "",
                            "sigla_unid": sigla_unid,
                            "desc_unid": desc_unid,
                        }
                    )
            elif processos_filho:
                for filho in processos_filho:
                    linhas.append(
                        {
                            "id_procedimento": data.get("IdProcedimento"),
                            "id_protocolo_formatado": protocolo_formatado,
                            "processo_especificacao": processo_especificacao,
                            "nome_id_tipo_processo": nome_id_tipo_processo,
                            "rp1p_descricao": "",
                            "rp2p_descricao": filho.get("Especificacao") or "",
                            "rp1u_sigla": "",
                            "rp2u_sigla": filho.get("SiglaUnidadeGeradoraProcesso")
                            or "",
                            "sigla_unid": sigla_unid,
                            "desc_unid": desc_unid,
                        }
                    )
            else:
                linhas.append(
                    {
                        "id_procedimento": data.get("IdProcedimento"),
                        "id_protocolo_formatado": protocolo_formatado,
                        "processo_especificacao": processo_especificacao,
                        "nome_id_tipo_processo": nome_id_tipo_processo,
                        "rp1p_descricao": "",
                        "rp2p_descricao": "",
                        "rp1u_sigla": "",
                        "rp2u_sigla": "",
                        "sigla_unid": sigla_unid,
                        "desc_unid": desc_unid,
                    }
                )
            data_list_to_parse.extend(linhas)
        return pd.DataFrame(data_list_to_parse)

    @staticmethod
    async def md_ia_consulta_processo_batch(
        id_procedimentos: list[str], batch_size: int = 100
    ) -> pd.DataFrame:
        """Consulta a API do SEI para obter os metadados de múltiplos processos em lote.

        Args:
            id_procedimentos: Lista de IDs de procedimentos
            batch_size: Tamanho máximo do lote (padrão: 100)

        Returns:
            DataFrame com metadados de todos os processos
        """
        if not id_procedimentos:
            return pd.DataFrame()

        chunk_size = max(1, min(batch_size, 100))
        chunks = [
            id_procedimentos[i : i + chunk_size]
            for i in range(0, len(id_procedimentos), chunk_size)
        ]

        if len(chunks) == 1:
            id_proc_str = ",".join(str(id_proc) for id_proc in chunks[0])
            return await SEIDBHandler.md_ia_consulta_processo_async(id_proc_str)

        async def fetch_chunk(chunk):
            id_proc_str = ",".join(str(id_proc) for id_proc in chunk)
            return await SEIDBHandler.md_ia_consulta_processo_async(id_proc_str)

        tasks = [fetch_chunk(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        dfs = [df for df in results if isinstance(df, pd.DataFrame) and not df.empty]
        if not dfs:
            return pd.DataFrame()

        return pd.concat(dfs, ignore_index=True)

    @staticmethod
    async def md_ia_consulta_documento_async(
        id_documentos: str,
        sin_filtra_documentos_relevantes: str = "N",
        sin_filtra_bloqueados: str = "N",
        sin_filtra_ativos: str = "N",
    ) -> pd.DataFrame:
        """Versão assíncrona de md_ia_consulta_documento usando httpx.

        Args:
            id_documentos: Identificador único do documento
            sin_filtra_documentos_relevantes: Flag para filtrar documentos relevantes
            sin_filtra_bloqueados: Flag para filtrar documentos bloqueados
            sin_filtra_ativos: Flag para filtrar documentos ativos

        Returns:
            DataFrame com metadados dos documentos
        """
        service_endpoint = "md_ia_consulta_documento"
        columns = [
            "id_protocolo",
            "num_doc",
            "documento_especificacao",
            "id_type_document",
            "content_doc",
            "formato_arquivo",
            "dta_inclusao",
            "name_id_type_doc",
            "id_protocolo_documento",
            "type_doc",
            "num_proc",
        ]

        def parse(doc: dict) -> dict:
            return {
                "id_protocolo": int(doc["IdProcedimento"]),
                "num_doc": doc["NumeroDocumento"],
                "documento_especificacao": doc.get("EspecificacaoDocumento") or "",
                "id_type_document": int(doc["IdTipoDocumento"]),
                "formato_arquivo": doc["NomeArquivo"],
                "dta_inclusao": pd.to_datetime(
                    doc["DataInclusao"], dayfirst=True
                ).strftime("%Y-%m-%d"),
                "name_id_type_doc": doc.get("NomeTipoDocumento", ""),
                "id_protocolo_documento": int(doc["IdDocumento"]),
                "type_doc": doc["StaTipoDocumento"],
                "num_proc": doc["NumeroProcesso"],
            }

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint,
            {
                "SinFiltraDocumentosRelevantes": sin_filtra_documentos_relevantes,
                "SinFiltraBloqueados": sin_filtra_bloqueados,
                "SinFiltraAtivos": sin_filtra_ativos,
                "IdDocumentos": id_documentos,
            },
        )

        async with httpx.AsyncClient(
            verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            response.encoding = "utf-8"
            api_response = response.json()
            api_docs = api_response.get("data", [])

        if not api_docs:
            return pd.DataFrame(columns=columns)

        parsed_data = [parse(doc) for doc in api_docs]
        return pd.DataFrame(parsed_data)

    @staticmethod
    async def md_ia_consulta_documento_batch(
        id_documentos: list[str],
        batch_size: int = 100,
        sin_filtra_documentos_relevantes: str = "N",
        sin_filtra_bloqueados: str = "N",
        sin_filtra_ativos: str = "N",
    ) -> pd.DataFrame:
        """Consulta a API do SEI para obter os metadados de múltiplos documentos em lote.

        Args:
            id_documentos: Lista de IDs de documentos
            batch_size: Tamanho máximo do lote (padrão: 100)
            sin_filtra_documentos_relevantes: Flag para filtrar documentos relevantes
            sin_filtra_bloqueados: Flag para filtrar documentos bloqueados
            sin_filtra_ativos: Flag para filtrar documentos ativos

        Returns:
            DataFrame com metadados de todos os documentos
        """
        if not id_documentos:
            return pd.DataFrame()

        chunk_size = max(1, min(batch_size, 100))
        chunks = [
            id_documentos[i : i + chunk_size]
            for i in range(0, len(id_documentos), chunk_size)
        ]

        if len(chunks) == 1:
            id_docs_str = ",".join(str(id_doc) for id_doc in chunks[0])
            return await SEIDBHandler.md_ia_consulta_documento_async(
                id_docs_str,
                sin_filtra_documentos_relevantes,
                sin_filtra_bloqueados,
                sin_filtra_ativos,
            )

        async def fetch_chunk(chunk):
            id_docs_str = ",".join(str(id_doc) for id_doc in chunk)
            return await SEIDBHandler.md_ia_consulta_documento_async(
                id_docs_str,
                sin_filtra_documentos_relevantes,
                sin_filtra_bloqueados,
                sin_filtra_ativos,
            )

        tasks = [fetch_chunk(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        dfs = [df for df in results if isinstance(df, pd.DataFrame) and not df.empty]
        if not dfs:
            return pd.DataFrame()

        return pd.concat(dfs, ignore_index=True)

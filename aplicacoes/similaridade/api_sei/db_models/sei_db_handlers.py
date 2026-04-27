import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import httpx
import pandas as pd
import requests
import urllib3
from requests.exceptions import JSONDecodeError, RequestException

from api_sei.envs import (
    SEI_API_DB_ADDRESS,
    SEI_API_DB_CHUNK_SIZE,
    SEI_API_DB_IDENTIFIER_SERVICE,
    SEI_API_DB_TIMEOUT,
    SEI_API_DB_USER,
    VERIFY_SSL,
)

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def run_async_if_needed(coro, timeout: float = None):
    """Executa a coroutine `coro` e retorna seu resultado. Seja:

    - em contexto SÍNCRONO (sem loop): via asyncio.run()
    - em contexto ASSÍNCRONO (loop já rodando): via ThreadPoolExecutor temporário
    """
    try:
        # Se já há um loop ativo (FastAPI), entra no except?
        asyncio.get_running_loop()
    except RuntimeError:
        # sem loop: Airflow, script standalone...
        return asyncio.run(coro)
    else:
        # loop ativo: executamos a coro num executor temporário
        with ThreadPoolExecutor(max_workers=1) as executor:
            # cada tarefa terá seu próprio executor que será fechado ao sair do with
            future = executor.submit(lambda: asyncio.run(coro))
            return future.result(timeout)


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
    # Substitua por sua lógica real de limpeza
    return str(value).strip()


def group_concat_distinct(series):
    return ", ".join(sorted({str(x) for x in series if x}))


class SEIDBHandler:
    @staticmethod
    def _build_api_url(service_endpoint: str) -> str:
        return f"{SEI_API_DB_ADDRESS}/{service_endpoint}"

    @staticmethod
    def _build_params(service_endpoint: str, extra_params: dict = None) -> dict:
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
            # Tenta fazer uma requisição simples para verificar conectividade
            url = SEIDBHandler._build_api_url("md_ia_lista_tipo_documento")
            params = SEIDBHandler._build_params("md_ia_lista_tipo_documento")
            response = requests.get(url, params=params, verify=VERIFY_SSL, timeout=10)
            # Aceita qualquer status que não seja erro de conexão
            return response.status_code in [
                200,
                404,
                500,
                503,
            ]  # API respondeu, mesmo com erro
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.SSLError,
        ) as e:
            logger.warning(f"API do SEI não está acessível: {e}")
            return False
        except Exception as e:
            # Para outros erros, assumimos que a API está disponível mas pode ter problemas temporários
            logger.info(f"API do SEI respondeu mas com erro: {e}")
            return True

    @staticmethod
    def _check_api_availability(func: callable) -> callable:
        """Decorador para verificar se a API está ativa antes de executar o método."""

        def wrapper(*args: tuple, **kwargs: dict):
            if not SEIDBHandler._check_api_health():
                logger.error("API do SEI está indisponível")
                raise SeiDBAPIUnavailableError("API do SEI está indisponível")
            return func(*args, **kwargs)

        return wrapper

    @staticmethod
    def _handle_api_errors(func: callable) -> callable:
        """Decorador para tratar erros comuns em chamadas de API."""

        def wrapper(*args: tuple, **kwargs: dict) -> pd.DataFrame:
            """Função wrapper para tratar exceções durante requisições à API.

            Esta função envolve a função decorada para tratar exceções que podem ocorrer
            durante as chamadas à API. Ela trata especificamente `RequestException` e
            `JSONDecodeError`, levantando um `SeiDBAPIError` customizado com códigos
            de status e mensagens de erro apropriados. Quaisquer outras exceções
            também são capturadas e levantadas como `SeiDBAPIError` com uma
            mensagem de erro genérica e código de status 500.

            Args:
                *args: Argumentos posicionais a serem passados para a função decorada.
                **kwargs: Argumentos nomeados a serem passados para a função decorada.

            Raises:
                SeiDBAPIError: Se ocorrer uma `RequestException`, `JSONDecodeError` ou
                qualquer outra exceção durante a execução da função decorada.
            """
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
                    detail=f"Falha na requisição à API do SEI ({req_exc.__class__.__name__}): {req_exc}",
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
            pd.DataFrame: DataFrame com as colunas id_protocolo_2 (subprocessos) e id_protocolo_1 (processo principal).
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
            else:
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
                "documento_especificacao": doc.get("EspecificacaoDocumento", ""),
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
        id_list = [i.strip() for i in str(id_documentos).split(",") if i.strip()]

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

            async def fetch_content_limited(ids, limit=25):
                """Busca o conteúdo dos documentos limitando a concorrência em *limit* chamadas."""
                sem = asyncio.Semaphore(limit)

                async def bound_fetch(_id):
                    async with sem:
                        try:
                            return await SEIDBHandler.md_ia_consulta_conteudo_documento_async(
                                id_documento=_id
                            )
                        except SeiDBAPIError:
                            return {"id_documento": _id, "content_doc": None}

                return await asyncio.gather(*(bound_fetch(_id) for _id in ids))

            res_conteudo = asyncio.run(
                fetch_content_limited(
                    df_metadata["id_protocolo_documento"].tolist(), limit=10
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
        if response.text:
            return SEIDBHandler._parse_api_response(response, columns, parse)

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
        quantidade_registros: int = None, id_ultimo_registro: int = None
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

        if response.status_code == 404 and "Nenhum" in response.text:
            logger.info("Nenhum novo processo a ser indexado.")
            return []
        elif response.status_code != 200:
            response.raise_for_status()

        response.encoding = "utf-8"
        if response.text:
            api_response = response.json()
            return parse(api_response.get("data", {}))
        return []

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_documentos_elegiveis_processos_similares(
        id_procedimento: str,
    ) -> list[int]:
        """Retorna lista de documentos elegíveis para processos similares.

        Args:
            id_procedimento (int): ID do procedimento para consulta.

        Returns:
            pd.DataFrame: DataFrame contendo a lista de documentos elegíveis.

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API.
        """
        service_endpoint = "md_ia_lista_documentos_elegiveis_processos_similares"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdProcedimento": str(id_procedimento)}
        )
        response = requests.get(
            url, params=params, verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
        )

        if response.text:
            api_response = response.json()
            return api_response.get("data", [])
        return []

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_processos_indexaveis_cancelados(
        quantidade_registros: int = None, id_ultimo_registro: int = None
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

        if response.status_code == 404 and "Nenhum" in response.text:
            logger.info("Nenhum novo processo a ser cancelado.")
            return [], 0

        response.raise_for_status()
        response.encoding = "utf-8"
        if response.text:
            api_response = response.json()
            return _parse(api_response.get("data", {}))
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
                elif response.status_code != 200:
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
            # Verifica se há processos relacionados
            records = []
            for api_dict in api_dicts:
                processos_anexados = api_dict.get("IdProcessosAnexados") or []

                # Concatena as especificações dos processos pai
                processos_pai = api_dict.get("ProcessosPaiRelacionado") or []
                descricao_pai_concatenada = "; ".join(
                    p.get("Especificacao", "") for p in processos_pai
                )

                # ID do interessado
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
    async def md_ia_consulta_conteudo_documento_async(id_documento: str) -> dict:
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
        service_endpoint = "md_ia_consulta_conteudo_documento"
        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdDocumento": id_documento}
        )

        try:
            async with httpx.AsyncClient(
                verify=VERIFY_SSL, timeout=int(SEI_API_DB_TIMEOUT)
            ) as client:
                response = await client.get(
                    url, params=params, headers={"accept": "application/json"}
                )

                if response.status_code not in [200, 404]:
                    response.raise_for_status()
                if response.text:
                    api_response = response.json()
                    data = api_response.get("data", {})
                    return {
                        "id_documento": id_documento,
                        "tipo_conteudo": data.get("TipoConteudo"),
                        "content_doc": data.get("ConteudoDocumento"),
                    }
                if response.status_code == 404:
                    logger.warning(
                        f"Conteúdo do documento {id_documento} não encontrado"
                    )
                return {"id_documento": id_documento, "content_doc": None}
        except httpx.HTTPError as e:
            status_code = getattr(getattr(e, "response", None), "status_code", 500)
            logger.error(
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
        quantidade_registros: int = None, id_ultimo_registro: int = None
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

        if response.status_code == 404 and "Nenhum" in response.text:
            logger.info("Nenhum novo documento a ser indexado.")
            return []
        elif response.status_code != 200:
            response.raise_for_status()

        response.encoding = "utf-8"
        if response.text:
            api_response = response.json()
            return parse(api_response.get("data", {}))
        return []

    @staticmethod
    @_handle_api_errors
    def md_ia_lista_documentos_indexaveis_cancelados(
        quantidade_registros: int = None, id_ultimo_registro: int = None
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

        if response.status_code == 404 and "Nenhum" in response.text:
            logger.info("Nenhum novo documento a ser cancelado.")
            return [], 0
        if response.status_code != 200:
            response.raise_for_status()

        response.encoding = "utf-8"
        if response.text:
            api_response = response.json()
            return _parse(api_response.get("data", {}))
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
                elif response.status_code != 200:
                    response.raise_for_status()

                api_response = response.json()
                return api_response.get("status", "") == "success"
        except httpx.HTTPError:
            return False

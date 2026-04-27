"""Modulo para lidar com a API do SEI."""

import asyncio
import html as html_lib
import logging
import re
import time
import uuid
import xml.etree.ElementTree as ET
from json.decoder import JSONDecodeError
from pathlib import Path

import fitz  # PyMuPDF
import httpx
import pandas as pd
import requests
from requests.exceptions import RequestException, Timeout

from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.services.counter import token_counter
from sei_ia.services.exceptions.http_exceptions import HTTPException412SeiApiTimeout

setup_logging()
logger = logging.getLogger(__name__)


def _extract_text_from_pdf(pdf_path: str) -> str:
    """Extrai texto de um arquivo PDF."""
    try:
        pdf = fitz.open(pdf_path)
        pages = []
        for page_num in range(pdf.page_count):
            page = pdf[page_num]
            text = page.get_text()
            pages.append(text)
        pdf.close()
        return "\n".join(pages)
    except Exception as e:
        logger.exception(f"Erro ao extrair texto do PDF: {e}")
        return ""


def _extract_text_from_spreadsheet(file_path: str) -> str:
    """Extrai texto de uma planilha Excel/ODS."""
    try:
        xls = pd.ExcelFile(file_path, engine="calamine")
        markdown_sheets = []
        for sheet_num, sheet_name in enumerate(xls.sheet_names):
            df_sheet = pd.read_excel(xls, sheet_name=sheet_num, engine="calamine")

            # Limitar número de colunas para evitar planilhas mal formatadas
            max_columns = 100  # Limite razoável para documentos corporativos
            if df_sheet.shape[1] > max_columns:
                logger.warning(
                    f"Sheet {sheet_name} has {df_sheet.shape[1]} columns. Limiting to {max_columns} columns."
                )
                df_sheet = df_sheet.iloc[:, :max_columns]

            markdown_text = df_sheet.to_markdown()
            markdown_sheets.append(
                f"\n\nAba número {sheet_num + 1}: {sheet_name}\n{markdown_text}"
            )
        return "\n\n".join(markdown_sheets)
    except Exception as e:
        logger.exception(f"Erro ao extrair texto da planilha: {e}")
        return ""


_CONTENT_ENDPOINT_EXCLUDE: frozenset[str] = frozenset(
    {"ConteudoDocumento", "IdAnexos", "TipoConteudo"}
)

# Campos do md_ia_consulta_documento que não devem ir para extra_metadata
# (IDs numéricos internos e flags de controle sem valor semântico).
_METADATA_ENDPOINT_EXCLUDE: frozenset[str] = frozenset(
    {
        "IdProcedimento",
        "IdTipoDocumento",
        "IdDocumento",
        "StaTipoDocumento",
        "SinArmazenarCache",
    }
)


def _sanitize_html_field(value: str) -> str:
    """Remove tags HTML e normaliza espaços em branco."""
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", text).strip()


def _parse_ids(id_documentos: str | int) -> set[int]:
    """Converte um único inteiro ou uma string CSV de inteiros em um conjunto de inteiros.

    Args:
        id_documentos (str | int): Um inteiro ou uma string CSV representando IDs de documentos.

    Returns:
        set[int]: Um conjunto de inteiros extraídos da entrada.
    """
    if isinstance(id_documentos, int):
        # single integer → one-element set
        return {id_documentos}
    # otherwise assume CSV string
    return {int(x.strip()) for x in str(id_documentos).split(",") if x.strip()}


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


class SEIDBHandler:
    """Classe para lidar com a API do SEI."""

    @staticmethod
    def _build_api_url(service_endpoint: str) -> str:
        """Constrói a URL completa para um endpoint da API."""
        return f"{settings.SEI_API_DB_ADDRESS}/{service_endpoint}"

    @staticmethod
    def _build_params(service_endpoint: str, extra_params: dict | None = None) -> dict:
        """Constrói o dicionário de parâmetros para a requisição à API."""
        params = {
            "servico": service_endpoint,
            "SiglaSistema": settings.SEI_API_DB_USER,
            "IdentificacaoServico": settings.SEI_API_DB_IDENTIFIER_SERVICE,
        }
        if extra_params:
            params.update(extra_params)
        return params

    @staticmethod
    def _handle_api_errors(func: callable) -> callable:
        """Decorador para tratar erros comuns em chamadas de API com retry para timeout."""

        def wrapper(*args: tuple, **kwargs: dict) -> pd.DataFrame:
            """Função wrapper para tratar exceções durante requisições à API com retry.

            Esta função envolve a função decorada para tratar exceções que podem ocorrer
            durante as chamadas à API. Ela trata especificamente `RequestException` e
            `JSONDecodeError`, levantando um `SeiDBAPIError` customizado com códigos
            de status e mensagens de erro apropriados. Para timeout, implementa retry
            com backoff exponencial.

            Args:
                *args: Argumentos posicionais a serem passados para a função decorada.
                **kwargs: Argumentos nomeados a serem passados para a função decorada.

            Raises:
                SeiDBAPIError: Se ocorrer uma `RequestException`, `JSONDecodeError` ou
                qualquer outra exceção durante a execução da função decorada.
                HTTPException412SeiApiTimeout: Se ocorrer timeout após todas as tentativas.
            """
            max_retries = 1
            retry_count = 0

            while retry_count < max_retries:
                try:
                    return func(*args, **kwargs)
                except Timeout as timeout_exc:
                    # Tentar extrair o id_documento dos argumentos da função
                    document_id = "unknown"
                    if args and len(args) > 0:
                        # O primeiro argumento geralmente é o id_documento
                        document_id = str(args[0])
                    elif "id_documento" in kwargs:
                        document_id = str(kwargs["id_documento"])
                    elif "id_documentos" in kwargs:
                        document_id = str(kwargs["id_documentos"])

                    retry_count += 1
                    if retry_count >= max_retries:
                        logger.exception(
                            f"Timeout da API SEI ao consultar documento {document_id} após {max_retries} tentativas: {timeout_exc}"
                        )
                        raise HTTPException412SeiApiTimeout(
                            document_id=document_id
                        ) from timeout_exc
                    else:
                        logger.warning(
                            f"Timeout da API SEI ao consultar documento {document_id} - tentativa {retry_count}/{max_retries}"
                        )
                        # Aguardar antes de tentar novamente
                        time.sleep(
                            settings.BACKOFF_INITIAL_WAIT
                            * (settings.RETRY_BACKOFF_FACTOR ** (retry_count - 1))
                        )
                except RequestException as req_exc:
                    msg = f"Falha na requisição à API SEI DB: {req_exc}"
                    logger.exception(msg)
                    raise SeiDBAPIError(
                        status_code=getattr(req_exc.response, "status_code", 500),
                        detail=msg,
                    ) from req_exc
                except JSONDecodeError as json_exc:
                    msg = f"Resposta inválida da API SEI DB (JSON mal formado): {json_exc}"
                    logger.exception(msg)
                    raise SeiDBAPIError(
                        status_code=requests.codes.bad_gateway,
                        detail=msg,
                    ) from json_exc
                except Exception as exc:
                    msg = f"Erro inesperado na API SEI DB: {exc}"
                    logger.exception(msg)
                    raise SeiDBAPIError(status_code=500, detail=msg) from exc

            # Não deveria chegar aqui, mas por segurança
            return func(*args, **kwargs)

        return wrapper

    @staticmethod
    def _handle_historico_topico_errors(func: callable) -> callable:
        """Decorador específico para tratar erros do endpoint md_ia_consulta_historico_topico.

        Similar ao _handle_api_errors, mas retorna DataFrame vazio para 404 ao invés de erro.
        """

        def wrapper(*args: tuple, **kwargs: dict) -> pd.DataFrame:
            """Função wrapper para tratar exceções durante requisições à API.

            Retorna DataFrame vazio para 404 e trata outros erros normalmente.
            """
            try:
                return func(*args, **kwargs)
            except RequestException as req_exc:
                # Se for 404, retorna DataFrame vazio
                if getattr(req_exc.response, "status_code", None) == 404:
                    logger.info("Histórico do tópico não encontrado (404)")
                    return pd.DataFrame(
                        columns=["pergunta", "resposta", "dth_cadastro", "total_tokens"]
                    )

                # Para outros erros, comportamento padrão
                msg = f"Falha na requisição à API SEI DB: {req_exc}"
                logger.exception(msg)
                raise SeiDBAPIError(
                    status_code=getattr(req_exc.response, "status_code", 500),
                    detail=msg,
                ) from req_exc
            except JSONDecodeError as json_exc:
                msg = f"Resposta inválida da API SEI DB (JSON mal formado): {json_exc}"
                logger.exception(msg)
                raise SeiDBAPIError(
                    status_code=requests.codes.bad_gateway,
                    detail=msg,
                ) from json_exc
            except Exception as exc:
                msg = f"Erro inesperado na API SEI DB: {exc}"
                logger.exception(msg)
                raise SeiDBAPIError(status_code=500, detail=msg) from exc

        return wrapper

    @staticmethod
    def _parse_api_response(
        response: requests.Response, columns: list, parse_single_doc: callable
    ) -> pd.DataFrame:
        """Processa a resposta da API e a transforma em um DataFrame.

        Args:
            response (requests.Response): O objeto de resposta da requisição.
            columns (list): Lista com os nomes das colunas esperadas no DataFrame final.
            parse_single_doc (callable): Função para processar um único item (documento) da resposta da API.

        Returns:
            pd.DataFrame: DataFrame com os dados processados. Retorna um DataFrame vazio se a API não retornar dados.

        Raises:
            requests.exceptions.HTTPError: Se a resposta da API indicar um erro HTTP (status code >= 400).
        """
        response.raise_for_status()  # Levanta exceção para códigos de erro HTTP
        response.encoding = "utf-8"  # Garante a codificação correta
        api_response = response.json()  # Tenta decodificar a resposta JSON
        api_docs = api_response.get(
            "data", []
        )  # Pega a lista de 'data', ou uma lista vazia se não existir
        if not api_docs:
            return pd.DataFrame(
                columns=columns
            )  # Retorna DataFrame vazio se não houver dados
        # Aplica a função de parse para cada documento e cria o DataFrame
        parsed_data = [parse_single_doc(doc) for doc in api_docs]
        return pd.DataFrame(parsed_data)

    @staticmethod
    def _sanitize_filename(raw_filename: str, doc_extension: str) -> str:
        """Sanitiza o nome do arquivo para evitar problemas de sistema operacional.

        Args:
            raw_filename (str): Nome do arquivo original extraído do header
            doc_extension (str): Extensão do documento

        Returns:
            str: Nome do arquivo sanitizado
        """
        # Remove caracteres inválidos para nomes de arquivos
        invalid_chars = r'[<>:"/\\|?*]'
        sanitized = re.sub(invalid_chars, "_", raw_filename)

        # Remove tags HTML se existirem
        sanitized = re.sub(r"<[^>]+>", "", sanitized)

        max_length = 100
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        # Remove espaços em branco excessivos
        sanitized = re.sub(r"\s+", " ", sanitized.strip())

        # Se o nome ficou vazio ou muito curto, usa um UUID
        if not sanitized or len(sanitized) < 3:
            return f"{uuid.uuid4()}.{doc_extension}"

        # Garante que tenha a extensão correta
        if not sanitized.endswith(f".{doc_extension}"):
            sanitized = f"{sanitized}.{doc_extension}"

        return sanitized

    @staticmethod
    @_handle_api_errors
    def md_ia_download_arquivo_documento_externo(
        id_documento: str, doc_extension: str, id_anexo: int | None = None
    ) -> str:
        """Faz o download do arquivo de um documento externo do SEI ou anexo.

        Retorna o caminho completo do arquivo salvo em /tmp/.

        Args:
            id_documento (str): ID do documento a ser baixado.
            doc_extension (str): Extensão esperada do arquivo (ex: "pdf").
            id_anexo (int | None): ID do anexo (opcional; se fornecido, baixa o anexo específico).

        Returns:
            str: Caminho completo do arquivo salvo (ex: "/tmp/SEI_Modulos_v5.0.pdf").

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
            verify=settings.VERIFY_SSL,
            timeout=int(settings.SEI_API_DB_TIMEOUT),
        )
        response.raise_for_status()

        content_disp = response.headers.get("content-disposition", "")
        logger.debug(f">> DEBUG: Headers: {response.headers}")

        filename_match = re.search(r'filename="(.+?)"', content_disp)
        raw_filename = (
            filename_match.group(1)
            if filename_match
            else f"{uuid.uuid4()}.{doc_extension}"
        )

        filename = SEIDBHandler._sanitize_filename(raw_filename, doc_extension)

        base_name = Path(filename).stem
        extension = Path(filename).suffix
        unique_filename = (
            f"{base_name}_doc{id_documento}_{uuid.uuid4().hex[:8]}{extension}"
        )

        save_path = Path("/tmp") / unique_filename
        with save_path.open("wb") as f:
            f.write(response.content)

        logger.debug(
            f">> Documento {id_documento} (anexo {id_anexo}) salvo em '{save_path}'"
        )
        return str(save_path)

    @staticmethod
    @_handle_api_errors
    def md_ia_download_arquivo_upload_assistente(
        id_upload: int, doc_extension: str
    ) -> str:
        """Faz o download de um arquivo enviado diretamente pelo usuário no Assistente IA.

        Retorna o caminho completo do arquivo salvo em /tmp/.

        Args:
            id_upload (int): ID do upload a ser baixado.
            doc_extension (str): Extensão esperada do arquivo (ex: "pdf", "docx", "png").

        Returns:
            str: Caminho completo do arquivo salvo (ex: "/tmp/relatorio_final_up123_a1b2c3d4.docx").

        Raises:
            SeiDBAPIError: Em caso de erro na requisição ou na resposta da API.
        """
        service_endpoint = "md_ia_download_arquivo_upload_assistente"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(service_endpoint, {"IdUpload": id_upload})

        response = requests.get(
            url,
            params=params,
            headers={"accept": "*/*"},
            verify=settings.VERIFY_SSL,
            timeout=int(settings.SEI_API_DB_TIMEOUT),
        )
        response.raise_for_status()

        content_disp = response.headers.get("content-disposition", "")
        logger.debug(f">> DEBUG: Headers: {response.headers}")

        filename_match = re.search(r'filename="(.+?)"', content_disp)
        raw_filename = (
            filename_match.group(1)
            if filename_match
            else f"{uuid.uuid4()}.{doc_extension}"
        )

        filename = SEIDBHandler._sanitize_filename(raw_filename, doc_extension)

        base_name = Path(filename).stem
        extension = Path(filename).suffix
        unique_filename = f"{base_name}_up{id_upload}_{uuid.uuid4().hex[:8]}{extension}"

        save_path = Path("/tmp") / unique_filename
        with save_path.open("wb") as f:
            f.write(response.content)

        logger.debug(f">> Upload {id_upload} salvo em '{save_path}'")
        return str(save_path)

    @staticmethod
    @_handle_api_errors
    def md_ia_consulta_conteudo_documento(id_documentos: str) -> pd.DataFrame:
        """Consulta a API do SEI para obter o conteúdo de um documento, com suporte a anexos.

        Retorna um DataFrame com as colunas:
        - tipo_conteudo: Tipo de conteúdo do documento
        - content_doc: Conteúdo do documento (augmentado com anexos se IdAnexos presente)

        Args:
            id_documentos (str): Identificador único do documento a ser consultado.

        Raises:
            SeiDBAPIError: Em caso de erro na requisição ou na resposta da API
        """
        service_endpoint = "md_ia_consulta_conteudo_documento"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdDocumento": id_documentos}
        )
        response = requests.get(
            url,
            params=params,
            verify=settings.VERIFY_SSL,
            timeout=int(settings.SEI_API_DB_TIMEOUT),
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        api_response = response.json()
        api_docs = api_response.get("data", {})

        logger.debug(
            f">> DEBUG: API response keys: {list(api_docs.keys()) if api_docs else 'None'}"
        )

        if not api_docs:
            return pd.DataFrame(
                [{"tipo_conteudo": None, "content_doc": None, "extra_metadata": {}}]
            )

        tipo_conteudo = api_docs.get("TipoConteudo")
        content_doc = api_docs.get("ConteudoDocumento")
        extra_metadata = {
            k: _sanitize_html_field(str(v)) if isinstance(v, str) else str(v)
            for k, v in api_docs.items()
            if k not in _CONTENT_ENDPOINT_EXCLUDE and v is not None
        }

        logger.debug(
            f">> DEBUG: Document {id_documentos} - TipoConteudo: {tipo_conteudo}"
        )
        logger.debug(
            f">> DEBUG: Document {id_documentos} - Content length: {len(content_doc) if content_doc else 0}"
        )

        if "IdAnexos" in api_docs and api_docs["IdAnexos"]:
            # Parsear XML para mapear IdAnexo a filename
            try:
                root = ET.fromstring(content_doc)
                anexos = root.findall(".//atributo[@nome='Anexos']/valores/valor")
                anexo_map = {
                    val.get("id"): val.text
                    for val in anexos
                    if val.get("id") and val.text
                }
            except ET.ParseError as e:
                logger.warning(f"Erro ao parsear XML para anexos: {e}")
                anexo_map = {}

            augmented_content = f"<conteudo_principal_do_email>\n{content_doc}\n</conteudo_principal_do_email>\n"
            for idx, id_anexo in enumerate(api_docs["IdAnexos"], start=1):
                filename = anexo_map.get(str(id_anexo), f"anexo_{id_anexo}.unknown")
                extension = Path(filename).suffix.lstrip(".").lower()

                # Download do anexo
                try:
                    save_path = SEIDBHandler.md_ia_download_arquivo_documento_externo(
                        id_documentos, extension, id_anexo
                    )

                    # Extrair texto usando métodos locais
                    try:
                        if extension == "pdf":
                            anexo_text = _extract_text_from_pdf(save_path)
                        elif extension in ["ods", "xls", "xlsb", "xlsm", "xlsx"]:
                            anexo_text = _extract_text_from_spreadsheet(save_path)
                        else:
                            # Fallback para texto simples (ou outros formatos)
                            with Path(save_path).open(
                                "r", encoding="utf-8", errors="ignore"
                            ) as f:
                                anexo_text = f.read()
                    except Exception as e:
                        logger.exception(
                            f"Erro ao extrair texto de anexo {id_anexo}: {e}"
                        )
                        anexo_text = ""

                    # Concatenar
                    augmented_content += f"<anexo_{idx} - {filename}>\n{anexo_text}\n</anexo_{idx} - {filename}>\n"

                    # Limpar arquivo temporário
                    Path(save_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.exception(f"Erro ao processar anexo {id_anexo}: {e}")
                    # Continua com o próximo anexo

            content_doc = augmented_content

        return pd.DataFrame(
            [
                {
                    "tipo_conteudo": tipo_conteudo,
                    "content_doc": content_doc,
                    "extra_metadata": extra_metadata,
                }
            ]
        )

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
            verify=settings.VERIFY_SSL, timeout=int(settings.SEI_API_DB_TIMEOUT)
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
                                "rp1p_descricao": pai.get("Especificacao", ""),
                                "rp2p_descricao": filho.get("Especificacao", ""),
                                "rp1u_sigla": pai.get(
                                    "SiglaUnidadeGeradoraProcesso", ""
                                ),
                                "rp2u_sigla": filho.get(
                                    "SiglaUnidadeGeradoraProcesso", ""
                                ),
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

        chunk_size = max(1, min(batch_size, settings.SEI_API_DB_CHUNK_SIZE))
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
    @_handle_api_errors
    def md_ia_consulta_processo(id_procedimentos: str) -> pd.DataFrame:
        """Consulta a API do SEI para obter os metadados de um processo.

        Retorna um DataFrame com as colunas:
        - id_procedimento
        - id_protocolo_formatado
        - processo_especificacao
        - nome_id_tipo_processo
        - rp1p_descricao
        - rp2p_descricao
        - rp1u_sigla
        - rp2u_sigla
        - sigla_unid
        - desc_unid
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

        response = requests.get(
            url,
            params=params,
            verify=settings.VERIFY_SSL,
            timeout=int(settings.SEI_API_DB_TIMEOUT),
        )
        response.raise_for_status()
        response.encoding = "utf-8"
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
                # Caso normal: existe pai e filho
                for pai in processos_pai:
                    for filho in processos_filho:
                        linhas.append(
                            {
                                "id_procedimento": data.get("IdProcedimento"),
                                "id_protocolo_formatado": protocolo_formatado,
                                "processo_especificacao": processo_especificacao,
                                "nome_id_tipo_processo": nome_id_tipo_processo,
                                "rp1p_descricao": pai.get("Especificacao", ""),
                                "rp2p_descricao": filho.get("Especificacao", ""),
                                "rp1u_sigla": pai.get(
                                    "SiglaUnidadeGeradoraProcesso", ""
                                ),
                                "rp2u_sigla": filho.get(
                                    "SiglaUnidadeGeradoraProcesso", ""
                                ),
                                "sigla_unid": sigla_unid,
                                "desc_unid": desc_unid,
                            }
                        )
            elif processos_pai:
                # Só tem processos_pai
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
                # Só tem processos_filho
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
                # Nem pai nem filho: monta apenas a linha básica
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
            "sin_armazena_cache",
            "extra_metadata",
        ]

        def parse(doc: dict) -> dict:
            extra_metadata = {
                k: html_lib.unescape(_sanitize_html_field(str(v)))
                if k == "Assinaturas"
                else (_sanitize_html_field(str(v)) if isinstance(v, str) else str(v))
                for k, v in doc.items()
                if k not in _METADATA_ENDPOINT_EXCLUDE and v is not None and v != ""
            }
            return {
                "id_protocolo": int(doc["IdProcedimento"]),
                "num_doc": doc["NumeroDocumento"],
                "documento_especificacao": doc.get("EspecificacaoDocumento", ""),
                "id_type_document": int(doc["IdTipoDocumento"]),
                "formato_arquivo": doc["NomeArquivo"],
                "dta_inclusao": pd.to_datetime(
                    doc["DataInclusao"], dayfirst=True
                ).strftime("%Y-%m-%d"),
                "name_id_type_doc": doc.get("NomeTipoDocumento", ""),
                "id_protocolo_documento": int(doc["IdDocumento"]),
                "type_doc": doc["StaTipoDocumento"],
                "num_proc": doc["NumeroProcesso"],
                "sin_armazena_cache": doc.get("SinArmazenarCache", "S"),
                "extra_metadata": extra_metadata,
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
            verify=settings.VERIFY_SSL, timeout=int(settings.SEI_API_DB_TIMEOUT)
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

        chunk_size = max(1, min(batch_size, settings.SEI_API_DB_CHUNK_SIZE))
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

    @staticmethod
    @_handle_api_errors
    def md_ia_consulta_documento(
        id_documentos: str,
        sin_filtra_documentos_relevantes: str = "N",
        sin_filtra_bloqueados: str = "N",
        sin_filtra_ativos: str = "N",
    ) -> pd.DataFrame:
        """Consulta a API do SEI para obter a lista de documentos.

        Args:
            id_documentos (str): Identificador único do documento.
            sin_filtra_documentos_relevantes (str, optional): Flag para filtrar documentos relevantes. Defaults to "N".
            sin_filtra_bloqueados (str, optional): Flag para filtrar documentos bloqueados. Defaults to "N".
            sin_filtra_ativos (str, optional): Flag para filtrar documentos ativos. Defaults to "N".

        Retorna um DataFrame com as colunas:
            - id_protocolo: Identificador único do procedimento
            - documento_especificacao: Especificação do documento
            - id_type_document: Identificador único do tipo de documento
            - content_doc: Conteúdo do documento (em branco, pois a API do SEI não retorna o conteúdo)
            - content_type: Tipo de conteúdo do documento (extensão do arquivo)
            - dta_inclusao: Data de inclusão do documento
            - name_id_type_doc: Nome do tipo de documento
            - id_protocolo_documento: Identificador único do documento
            - tipo: Tipo de documento (externo ou interno)
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
            "sin_armazena_cache",
            "extra_metadata",
        ]

        def parse(doc: dict) -> dict:
            extra_metadata = {
                k: html_lib.unescape(_sanitize_html_field(str(v)))
                if k == "Assinaturas"
                else (_sanitize_html_field(str(v)) if isinstance(v, str) else str(v))
                for k, v in doc.items()
                if k not in _METADATA_ENDPOINT_EXCLUDE and v is not None and v != ""
            }
            return {
                "id_protocolo": int(doc["IdProcedimento"]),
                "num_doc": doc["NumeroDocumento"],
                "documento_especificacao": doc.get("EspecificacaoDocumento", ""),
                "id_type_document": int(doc["IdTipoDocumento"]),
                "formato_arquivo": doc["NomeArquivo"],
                "dta_inclusao": pd.to_datetime(
                    doc["DataInclusao"], dayfirst=True
                ).strftime("%Y-%m-%d"),
                "name_id_type_doc": doc.get("NomeTipoDocumento", ""),
                "id_protocolo_documento": int(doc["IdDocumento"]),
                "type_doc": doc["StaTipoDocumento"],
                "num_proc": doc["NumeroProcesso"],
                "sin_armazena_cache": doc.get("SinArmazenarCache", "S"),
                "extra_metadata": extra_metadata,
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
        response = requests.get(
            url,
            params=params,
            verify=settings.VERIFY_SSL,
            timeout=int(settings.SEI_API_DB_TIMEOUT),
        )
        return SEIDBHandler._parse_api_response(response, columns, parse)

    @staticmethod
    def internal_docs_from_process_api(id_documentos: str) -> pd.DataFrame:
        """Consulta a API do SEI para obter os metadados de um documento interno.

        Args:
            id_documentos: string contendo ids de documentos separados por vírgula
        """
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
        try:
            df_documentos = SEIDBHandler.md_ia_consulta_documento(
                id_documentos=id_documentos
            )
        except SeiDBAPIError:
            logger.exception("documentos internos não encontrados")
            return pd.DataFrame(columns=columns)
        id_documentos_set = _parse_ids(id_documentos)
        df_id_documentos_set = set(
            df_documentos["id_protocolo_documento"].dropna().unique()
        )
        if len(id_documentos_set) > 0 and id_documentos_set != df_id_documentos_set:
            logger.exception(
                f"Documentos internos não encontrados: {id_documentos_set - df_id_documentos_set}"
            )
            raise SeiDBAPIError(
                status_code=requests.codes.not_found,
                detail=f"Documentos internos não encontrados: {id_documentos_set - df_id_documentos_set}",
            )
        return df_documentos

    @staticmethod
    async def get_internal_docs_from_process(id_documentos: str) -> pd.DataFrame:
        """Consulta a API do SEI para obter a lista de documentos internos de um processo.

        Retorna um DataFrame com as colunas:
        - id_protocolo: Identificador único do procedimento
        - nr_documento: Número do documento
        - documento_especificacao: Especificação do documento
        - id_type_document: Identificador único do tipo de documento
        - content_doc: Conteúdo do documento
        - content_type: Tipo de conteúdo do documento (html)
        - dta_inclusao: Data de inclusão do documento
        - name_id_type_doc: Nome do tipo de documento
        - id_protocolo_documento: Identificador único do documento
        - type_doc: Tipo do documento (interno ou externo)
        - num_proc: Número do processo

        Args:
            id_documentos: Identificador único do documento

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API
        """
        df_documento = SEIDBHandler.internal_docs_from_process_api(
            id_documentos=id_documentos
        )
        df_documento = df_documento.rename({"num_doc": "nr_documento"})
        if df_documento.empty:
            return df_documento

        try:
            logger.info(
                f"🚀 ASYNC: Usando busca assíncrona para {len(df_documento)} documento(s)"
            )
            (
                content_map,
                extra_meta_map,
            ) = await SEIDBHandler.fetch_documents_content_async(
                df_documento["id_protocolo_documento"].astype(str).tolist(),
                limit=settings.SEI_API_SEMAPHORE,
            )
            doc_ids = df_documento["id_protocolo_documento"].astype(str)
            df_documento["content_doc"] = doc_ids.map(content_map)
            df_documento["extra_metadata"] = doc_ids.map(
                lambda x: extra_meta_map.get(x, {})
            )
        except Exception as e:
            logger.exception(
                f"Erro ao buscar conteúdo dos documentos assincronamente: {e}"
            )
            df_documento["content_doc"] = ""
            df_documento["extra_metadata"] = [{}] * len(df_documento)

        df_documento["content_type"] = "html"
        return df_documento

    @staticmethod
    async def fetch_documents_content_async(
        document_ids: list[str], limit: int = 10
    ) -> tuple[dict, dict]:
        """Busca o conteúdo de múltiplos documentos de forma assíncrona com controle de concorrência.

        Args:
            document_ids: Lista de IDs de documentos
            limit: Limite de requisições simultâneas (padrão: 10)

        Returns:
            tuple: (content_map, extra_meta_map) onde cada um mapeia id_documento -> valor
        """
        import time

        start_time = time.time()
        sem = asyncio.Semaphore(limit)

        async def bound_fetch(_id):
            async with sem:
                try:
                    return await SEIDBHandler.md_ia_consulta_conteudo_documento_async(
                        id_documento=_id
                    )
                except SeiDBAPIError:
                    return {"id_documento": _id, "content_doc": None}

        results = await asyncio.gather(*(bound_fetch(_id) for _id in document_ids))

        elapsed_time = time.time() - start_time  # noqa: F841
        successful_results = [res for res in results if res and res.get("content_doc")]  # noqa: F841

        content_map = {
            str(res.get("id_documento")): res.get("content_doc")
            for res in results
            if res
        }
        extra_meta_map = {
            str(res.get("id_documento")): res.get("extra_metadata", {})
            for res in results
            if res
        }
        return content_map, extra_meta_map

    @staticmethod
    @_handle_historico_topico_errors  # Substitui o _handle_api_errors
    def md_ia_consulta_historico_topico(id_topico: str) -> pd.DataFrame:
        """Consulta a API do SEI para obter o histórico de um tópico.

        Retorna um DataFrame com as colunas:
        - pergunta: Pergunta do histórico
        - resposta: Resposta do histórico
        - pergunta_data: Data da pergunta
        - total_tokens: Número total de tokens

        Args:
            id_topico (str): Identificador único do tópico

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API
        """
        service_endpoint = "md_ia_consulta_historico_topico"
        columns = ["pergunta", "resposta", "dth_cadastro", "total_tokens"]

        def parse(doc: dict) -> dict:
            total_tokens = token_counter(doc["Pergunta"]) + token_counter(
                doc["Resposta"]
            )
            return {
                "pergunta": doc["Pergunta"],
                "resposta": doc["Resposta"],
                "dth_cadastro": pd.to_datetime(
                    doc.get("DthCadastro", ""), dayfirst=True
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "total_tokens": total_tokens,
            }

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(service_endpoint, {"IdTopico": id_topico})
        response = requests.get(
            url,
            params=params,
            verify=settings.VERIFY_SSL,
            timeout=int(settings.SEI_API_DB_TIMEOUT),
        )
        return SEIDBHandler._parse_api_response(response, columns, parse)

    @staticmethod
    @_handle_api_errors
    def md_ia_consulta_ultimo_id_message() -> int:
        """Consulta a API do SEI para obter o último ID de mensagem.

        Retorna o valor do último ID de mensagem se a requisição for bem-sucedida, None caso contrário.

        Raises:
            SeiDBAPIException: Em caso de erro na requisição ou na resposta da API
        """
        service_endpoint = "md_ia_consulta_ultimo_id_message"

        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(service_endpoint, {})
        response = requests.get(
            url,
            params=params,
            verify=settings.VERIFY_SSL,
            timeout=int(settings.SEI_API_DB_TIMEOUT),
        )

        response.raise_for_status()
        response.encoding = "utf-8"
        api_response = response.json()
        raw_value = api_response.get("data", None)

        return int(raw_value) if raw_value is not None else None

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
        import time

        start_time = time.time()

        service_endpoint = "md_ia_consulta_conteudo_documento"
        url = SEIDBHandler._build_api_url(service_endpoint)
        params = SEIDBHandler._build_params(
            service_endpoint, {"IdDocumento": id_documento}
        )

        # Configuração de retry
        max_retries = 3
        base_delay = 1.0  # segundos

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    verify=settings.VERIFY_SSL, timeout=int(settings.SEI_API_DB_TIMEOUT)
                ) as client:
                    if attempt > 0:
                        delay = base_delay * (2 ** (attempt - 1))  # backoff exponencial
                        logger.info(
                            f"🔄 RETRY #{attempt}: Aguardando {delay:.1f}s antes de tentar documento {id_documento}"
                        )
                        await asyncio.sleep(delay)

                    response = await client.get(
                        url, params=params, headers={"accept": "application/json"}
                    )

                    if response.status_code not in [200, 404]:
                        response.raise_for_status()

                    if response.text:
                        api_response = response.json()
                        data = api_response.get("data", {})

                        # Processar anexos se existirem (similar ao método síncrono)
                        content_doc = data.get("ConteudoDocumento")
                        extra_metadata = {
                            k: _sanitize_html_field(str(v))
                            if isinstance(v, str)
                            else str(v)
                            for k, v in data.items()
                            if k not in _CONTENT_ENDPOINT_EXCLUDE and v is not None
                        }
                        if "IdAnexos" in data and data["IdAnexos"]:
                            # Parsear XML para mapear IdAnexo a filename
                            try:
                                root = ET.fromstring(content_doc)
                                anexos = root.findall(
                                    ".//atributo[@nome='Anexos']/valores/valor"
                                )
                                anexo_map = {
                                    val.get("id"): val.text
                                    for val in anexos
                                    if val.get("id") and val.text
                                }
                            except ET.ParseError as e:
                                logger.warning(f"Erro ao parsear XML para anexos: {e}")
                                anexo_map = {}

                            augmented_content = f"<conteudo_principal_do_email>\n{content_doc}\n</conteudo_principal_do_email>\n"
                            for idx, id_anexo in enumerate(data["IdAnexos"], start=1):
                                filename = anexo_map.get(
                                    str(id_anexo), f"anexo_{id_anexo}.unknown"
                                )
                                extension = Path(filename).suffix.lstrip(".").lower()

                                # Download do anexo usando método síncrono (por questões de compatibilidade)
                                try:
                                    save_path = SEIDBHandler.md_ia_download_arquivo_documento_externo(
                                        id_documento, extension, id_anexo
                                    )

                                    # Extrair texto usando métodos locais
                                    try:
                                        if extension == "pdf":
                                            anexo_text = _extract_text_from_pdf(
                                                save_path
                                            )
                                        elif extension in [
                                            "ods",
                                            "xls",
                                            "xlsb",
                                            "xlsm",
                                            "xlsx",
                                        ]:
                                            anexo_text = _extract_text_from_spreadsheet(
                                                save_path
                                            )
                                        else:
                                            # Fallback para texto simples (ou outros formatos)
                                            with Path(save_path).open(
                                                "r", encoding="utf-8", errors="ignore"
                                            ) as f:
                                                anexo_text = f.read()
                                    except Exception as e:
                                        logger.exception(
                                            f"Erro ao extrair texto de anexo {id_anexo}: {e}"
                                        )
                                        anexo_text = ""

                                    # Concatenar
                                    augmented_content += f"<anexo_{idx} - {filename}>\n{anexo_text}\n</anexo_{idx} - {filename}>\n"

                                    # Limpar arquivo temporário
                                    Path(save_path).unlink(missing_ok=True)
                                except Exception as e:
                                    logger.exception(
                                        f"Erro ao processar anexo {id_anexo}: {e}"
                                    )
                                    # Continua com o próximo anexo

                            content_doc = augmented_content

                        elapsed_time = time.time() - start_time
                        return {
                            "id_documento": id_documento,
                            "tipo_conteudo": data.get("TipoConteudo"),
                            "content_doc": content_doc,
                            "extra_metadata": extra_metadata,
                        }

                    if response.status_code == 404:
                        elapsed_time = time.time() - start_time
                        logger.warning(
                            f"⚠️ ASYNC: Documento {id_documento} não encontrado (404) em {elapsed_time:.2f}s"
                        )
                        return {"id_documento": id_documento, "content_doc": None}

                    elapsed_time = time.time() - start_time
                    return {"id_documento": id_documento, "content_doc": None}

            except httpx.HTTPError as e:
                status_code = getattr(getattr(e, "response", None), "status_code", 500)

                # Determinar se devemos tentar novamente
                should_retry = attempt < max_retries and status_code in [
                    500,
                    502,
                    503,
                    504,
                    429,
                ]  # Erros temporários

                if should_retry:
                    logger.warning(
                        f"⚠️ RETRY: Erro temporário ao consultar documento {id_documento} (tentativa #{attempt + 1}): {e.__class__.__name__}: {e}"
                    )
                    continue  # Tenta novamente
                else:
                    # Última tentativa ou erro não recuperável
                    elapsed_time = time.time() - start_time
                    logger.error(
                        f"❌ ASYNC: Erro ao consultar documento {id_documento} em {elapsed_time:.2f}s após {attempt + 1} tentativas: {e.__class__.__name__}: {e}"
                    )
                    raise SeiDBAPIError(
                        status_code=status_code,
                        detail=f"Falha na requisição à API do SEI após {attempt + 1} tentativas ({e.__class__.__name__}): {e}",
                    ) from e

        # Se chegou aqui, esgotou todas as tentativas (não deveria acontecer)
        elapsed_time = time.time() - start_time
        logger.error(
            f"❌ ASYNC: Todas as tentativas esgotadas para documento {id_documento} em {elapsed_time:.2f}s"
        )
        return {"id_documento": id_documento, "content_doc": None}

"""Módulo de extração de metadados de documentos externos."""

import logging
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from sei_ia.data.database.sei_db_handlers import SEIDBHandler
from sei_ia.data.etl.extract.external import raise_http_exception
from sei_ia.data.etl.text_preprocess import get_file_extension
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException404,
    HTTPException409,
    HTTPException500,
)

logger = logging.getLogger(__name__)


class MetadataDocument(BaseModel):
    """Modelo de extração de metadados de documentos.

    Attributes:
        id_documento (str): ID do protocolo do documento.
        id_procedimento (str): ID do protocolo do procedimento.
        id_tipo_documento (str): ID do tipo de documento.
        id_protocolo_formatado (str): ID formatado do protocolo do protocolo.
        id_documento_formatado (str): ID formatado do protocolo do documento.
        documento_especificacao (str): Especificação do documento.
        formato_arquivo (str): Formato do arquivo do documento.
        dta_inclusao (Optional[datetime | str]): Data de inclusão do documento.
        nome_id_tipo_documento (str): Nome do tipo de documento.
    """

    id_documento: str
    id_procedimento: str
    id_tipo_documento: str
    id_protocolo_formatado: str
    id_documento_formatado: str
    documento_especificacao: str
    formato_arquivo: str
    dta_inclusao: datetime | str | None
    nome_id_tipo_documento: str
    type_doc: str | None = None

    model_config = ConfigDict(extra="allow")  # Substitui a antiga `class Config`

    @field_validator("dta_inclusao", mode="after")
    def parse_dta_inclusao(cls, value):
        """Validador para parsear a data de inclusão do documento.

        Converte `dta_inclusao` para string no formato "YYYY-MM-DD HH:MM:SS"
        se for uma instância de `datetime`.

        Args:
            value: O valor do campo `dta_inclusao`.

        Returns:
            O valor parseado como string ou o valor original.
        """
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value


class MetadataProc(BaseModel):
    """Modelo de extração de metadados de procedimentos.

    Attributes:
        id_procedimento (str): ID do procedimento.
        id_protocolo_formatado (str): ID formatado do protocolo do procedimento.
        processo_especificacao (str): Especificação do procedimento.
        nome_id_tipo_processo (str): Nome do tipo do procedimento.
        info_rel_procedimento (str): Informações de relacionamento do procedimento.
        unidade_geradora (str): Unidade geradora com sigla e descrição formatadas.
    """

    id_procedimento: str
    id_protocolo_formatado: str
    processo_especificacao: str
    nome_id_tipo_processo: str
    info_rel_procedimento: str
    unidade_geradora: str


async def get_proc_id_from_doc_id(id_documento: str) -> str:
    """Extrai o ID do procedimento a partir do ID do documento.

    Args:
        id_documento: ID do documento

    Returns:
        ID do procedimento ou string vazia se o documento não for encontrado
    """
    data_frame = SEIDBHandler.internal_docs_from_process_api(id_documentos=id_documento)
    return "" if data_frame.empty else data_frame["id_protocolo"][0]


def proc_metadata_with_description(metadata: MetadataProc) -> str:
    """Gera uma string formatada com a descrição dos metadados do processo/procedimento.

    Args:
        metadata (dict): Dicionário contendo os metadados do documento.

    Returns:
        str: String formatada com a descrição dos metadados.
    """
    metadados_formatados = [
        f"ID do Processo: {metadata.id_procedimento}",
        f"Número do Processo: {metadata.id_protocolo_formatado}",
        f"Descrição/Especificação do Processo: {metadata.processo_especificacao}",
        f"Tipo do Processo: {metadata.nome_id_tipo_processo}",
    ]

    return "\n".join(metadados_formatados)


def metadata_with_description(metadata: dict) -> str:
    """Gera uma string formatada com a descrição dos metadados dos documentos.

    Args:
        metadata (dict): Dicionário contendo os metadados do documento.

    Returns:
        str: String formatada com a descrição dos metadados.
    """
    metadados_formatados = [
        f"ID do Documento: {metadata.get('id_documento', 'N/A')}",
        f"Número do Documento: {metadata.get('id_documento_formatado', 'N/A')}",
        f"Descrição do Documento: {metadata.get('documento_especificacao', 'N/A')}",
        f"Formato do arquivo do Documento: {metadata.get('formato_arquivo', 'N/A')}",
        f"Data de Inclusão do Documento: {metadata.get('dta_inclusao', 'N/A')}",
        f"Descrição do tipo de Documento: {metadata.get('nome_id_tipo_documento', 'N/A')}",
    ]

    return "\n".join(metadados_formatados)


async def get_type_doc_from_id(id_documento: str) -> tuple[bool, str, str, str]:
    """Obtém o tipo e extensão dos documentos.

    Args:
        id_documento: ID do documento

    Returns:
        Tupla com (is_internal, extension, num_doc, num_proc)
    """
    df_types = SEIDBHandler.internal_docs_from_process_api(id_documentos=id_documento)
    l_df = len(df_types)
    if l_df == 0:
        msg = f"Documento {id_documento} nao encontrado!"
        raise HTTPException404(detail=msg)
    if l_df == 1 and isinstance(df_types["type_doc"][0], str):
        if df_types["type_doc"][0].lower() == "x":
            formato_arquivo = get_file_extension(df_types["formato_arquivo"][0])
            return (
                False,
                formato_arquivo,
                str(df_types["num_doc"][0]),
                str(df_types["num_proc"][0]),
            )
        return (True, "html", str(df_types["num_doc"][0]), str(df_types["num_proc"][0]))
    raise HTTPException409


async def get_doc_metadata_dict(id_documento: str) -> dict:
    """Extrai os metadados de um documento retornando um dict estruturado.

    Args:
        id_documento: ID do documento

    Returns:
        Dict com campos estruturados do metadata
    """
    try:
        data_frame = SEIDBHandler.internal_docs_from_process_api(
            id_documentos=id_documento
        )
        data_frame = data_frame.rename(
            columns={
                "num_proc": "id_protocolo_formatado",
                "id_protocolo": "id_procedimento",
                "num_doc": "id_documento_formatado",
                "id_type_document": "id_tipo_documento",
                "name_id_type_doc": "nome_id_tipo_documento",
            }
        )
        data_frame["id_documento"] = id_documento
        data_frame["formato_arquivo"] = (
            data_frame["formato_arquivo"]
            .str.strip()
            .replace(r"^\s*$", "html", regex=True)
            .fillna("html")
        )
        if data_frame.empty:
            msg = f"Nenhum documento encontrado com o ID {id_documento}."
            raise_http_exception(HTTPException404(detail=msg), msg)
        if data_frame.shape[0] > 1:
            msg = f"Mais de um documento encontrado com o ID {id_documento}."
            raise_http_exception(HTTPException409(detail=msg), msg)
        metadata = data_frame.iloc[0].to_dict()
        metadata["formato_arquivo"] = get_file_extension(metadata["formato_arquivo"])
        metadata = {k: str(v) for k, v in metadata.items()}
        return metadata
    except Exception as e:
        error_message = f"Erro ao buscar o documento com ID {id_documento}."
        logger.exception(error_message)
        raise HTTPException500(error_message) from e


async def get_doc_metadata_from_id(id_documento: str) -> str:
    """Extrai os metadados de um documento retornando string formatada.

    Args:
        id_documento: ID do documento

    Returns:
        String formatada com descrição dos metadados
    """
    metadata = await get_doc_metadata_dict(id_documento)
    return metadata_with_description(MetadataDocument(**metadata).model_dump())


async def fetch_procedimentos_metadata_batch(
    id_procedimentos: list[str],
) -> dict[str, str]:
    """Busca metadados de múltiplos procedimentos em lote.

    Args:
        id_procedimentos: Lista de IDs de procedimentos

    Returns:
        dict: Mapeamento de id_procedimento -> metadata_string
    """
    if not id_procedimentos:
        return {}

    logger.debug(
        f"🚀 BATCH: Buscando metadados de {len(id_procedimentos)} procedimentos"
    )

    try:
        # Buscar metadados em batch
        data_frame = await SEIDBHandler.md_ia_consulta_processo_batch(id_procedimentos)

        if data_frame.empty:
            logger.warning(
                f"Nenhum metadado encontrado para {len(id_procedimentos)} procedimentos"
            )
            return {}

        # Processar DataFrame
        data_frame["info_rel_procedimento"] = (
            data_frame["rp1u_sigla"]
            + " "
            + data_frame["rp1p_descricao"]
            + data_frame["rp2u_sigla"]
            + " "
            + data_frame["rp2p_descricao"]
        )
        data_frame = data_frame.drop(
            columns=["rp1u_sigla", "rp1p_descricao", "rp2u_sigla", "rp2p_descricao"]
        )
        data_frame = data_frame.groupby(
            [
                "id_procedimento",
                "id_protocolo_formatado",
                "processo_especificacao",
                "nome_id_tipo_processo",
                "sigla_unid",
                "desc_unid",
            ],
            as_index=False,
        ).agg(
            {
                "info_rel_procedimento": lambda x: " ".join(
                    v for v in x if isinstance(v, str) and v
                )
            }
        )

        data_frame["unidade_geradora"] = (
            data_frame["sigla_unid"] + " " + data_frame["desc_unid"]
        )
        data_frame = data_frame.drop(columns=["sigla_unid", "desc_unid"])

        # Converter para dict de metadados
        result = {}
        for _, row in data_frame.iterrows():
            row_dict = {
                key: str(value) if value is not None else ""
                for key, value in row.to_dict().items()
            }
            metadata = MetadataProc(**row_dict)
            metadata_str = proc_metadata_with_description(metadata)
            result[metadata.id_procedimento] = metadata_str

        logger.debug(f"✓ BATCH: {len(result)} metadados de procedimentos recuperados")
        return result

    except Exception as e:
        logger.exception(f"Erro ao buscar metadados em lote de procedimentos: {e}")
        return {}


async def fetch_documentos_metadata_batch(id_documentos: list[str]) -> dict[str, dict]:
    """Busca metadados de múltiplos documentos em lote.

    Args:
        id_documentos: Lista de IDs de documentos

    Returns:
        dict: Mapeamento de id_documento -> metadata_dict com campos estruturados (incluindo
            type_doc/is_internal) e a string "metadata_str" formatada.
    """
    if not id_documentos:
        return {}

    logger.debug(f"🚀 BATCH: Buscando metadados de {len(id_documentos)} documentos")

    try:
        # Buscar metadados em batch
        data_frame = await SEIDBHandler.md_ia_consulta_documento_batch(id_documentos)

        if data_frame.empty:
            logger.warning(
                f"Nenhum metadado encontrado para {len(id_documentos)} documentos"
            )
            return {}

        # Processar e converter para dict
        result = {}
        for _, row in data_frame.iterrows():
            raw_row = row.to_dict()
            extra_metadata = raw_row.pop("extra_metadata", None)
            if not isinstance(extra_metadata, dict):
                extra_metadata = {}
            row_dict = {
                key: (str(value) if value is not None else "")
                for key, value in raw_row.items()
            }
            doc_id = row_dict.get("id_protocolo_documento", "")

            # Preparar metadados básicos
            type_doc_value = row_dict.get("type_doc", "")
            metadata = {
                "id_documento": doc_id,
                "id_procedimento": row_dict.get("id_protocolo", ""),
                "id_tipo_documento": row_dict.get("id_type_document", ""),
                "id_protocolo_formatado": row_dict.get("num_proc", ""),
                "id_documento_formatado": row_dict.get("num_doc", ""),
                "documento_especificacao": row_dict.get("documento_especificacao", ""),
                "formato_arquivo": get_file_extension(
                    row_dict.get("formato_arquivo", "")
                ),
                "dta_inclusao": row_dict.get("dta_inclusao", ""),
                "nome_id_tipo_documento": row_dict.get("name_id_type_doc", ""),
                "type_doc": type_doc_value,
                "is_internal": bool(type_doc_value and type_doc_value.upper() != "X"),
                "sin_armazena_cache": row_dict.get("sin_armazena_cache", "S"),
            }

            # Criar objeto MetadataDocument e gerar string descritiva
            metadata_obj = MetadataDocument(**metadata)
            metadata_str = metadata_with_description(metadata_obj.model_dump())
            if extra_metadata:
                extra_lines = "\n".join(f"{k}: {v}" for k, v in extra_metadata.items())
                metadata_str = (
                    f"{metadata_str}\n{extra_lines}" if metadata_str else extra_lines
                )

            result[doc_id] = {
                "metadata": metadata,
                "metadata_str": metadata_str,
                "id_documento_formatado": metadata["id_documento_formatado"],
                "id_protocolo_formatado": metadata["id_protocolo_formatado"],
                "type_doc": type_doc_value,
                "is_internal": metadata["is_internal"],
                "sin_armazena_cache": metadata["sin_armazena_cache"],
            }

        logger.debug(f"✓ BATCH: {len(result)} metadados de documentos recuperados")
        return result

    except Exception as e:
        logger.exception(f"Erro ao buscar metadados em lote de documentos: {e}")
        return {}

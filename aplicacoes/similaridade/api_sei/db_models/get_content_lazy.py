"""Lida com solicitações de conteúdo preguiçosas para o banco de dados."""

import logging
import re

import pandas as pd
from bs4 import BeautifulSoup
from fastapi import HTTPException
from w3lib.html import replace_entities

from api_sei.db_models.sei_db_handlers import SEIDBHandler
from api_sei.resources.tokenizers_and_filters import solr_preprocessing

logger = logging.getLogger(__name__)
CONTENT_DOC_WARNING = 100_000_000


def process_html(doc: str) -> str:
    """Processa o conteúdo HTML, removendo tags e formatando o texto.

    Parameters:
        doc (str): O documento HTML a ser processado.

    Returns:
        str: O conteúdo processado do documento.
    """
    soup = BeautifulSoup(doc, "html.parser")
    if bool(soup.find()):
        text = soup.get_text()
        text = text.replace("\xa0", " ")
        text = text.encode("utf-8", "ignore").decode()
        text = text.lower()
        text = re.sub(r"[\n\t\r]", " ", text)
        text = re.sub(r" +", " ", text)
        text = text.replace("\u202f", " ")
    else:
        text = " ".join(doc.split())
    return text


def process_html_raw(text: str) -> str:
    """Processa o texto sem modificar o conteúdo HTML.

    Parameters:
        text (str): O texto HTML a ser processado.

    Returns:
        str: O conteúdo bruto do texto.
    """
    return replace_entities(text)


def get_doc_content_lazy(list_id_docs: list, *, raw: bool = False) -> dict:
    """Recupera o conteúdo de documentos internos e externos com base em uma lista de IDs de documentos.

    Args:
        list_id_docs (List[int]): Lista de IDs de documentos para os quais se deseja recuperar o conteúdo.
        raw (bool, opcional): Se True, retorna o conteúdo HTML bruto. Se False (padrão), processa o conteúdo.

    Returns:
        List[Dict[str, Union[int, str]]]: Uma lista de dicionários contendo o ID do documento e seu conteúdo.

    Raises:
        HTTPException: Se algum documento selecionado não for encontrado no banco de dados (BD) ou índice Solr do SEI.

    Exemplo:
        list_id_docs = [123, 456, 789]
        lista_conteudo = get_doc_content_lazy(list_id_docs)
        for doc in lista_conteudo:
            print(f"ID do Documento: {doc['id_document']}")
            print(f"Conteúdo: {doc['content']}")
    """
    try:
        # Usa o SEIDBHandler para buscar documentos com conteúdo
        ids_str = ",".join(map(str, list_id_docs))
        df_docs = SEIDBHandler.md_ia_consulta_documento(ids_str, conteudo=True)

        if df_docs.empty:
            msg = f"Nenhum documento encontrado para os IDs: {', '.join(map(str, list_id_docs))}"
            logger.error(msg=msg)
            raise HTTPException(status_code=404, detail=msg)

        # Verifica se algum documento não foi encontrado
        found_ids = df_docs["id_protocolo_documento"].tolist()
        missing_ids = [doc_id for doc_id in list_id_docs if doc_id not in found_ids]

        if missing_ids:
            s = "s" if len(missing_ids) > 1 else ""
            ids = ", ".join(map(str, missing_ids))
            msg = f"Documento{s} selecionado{s} para busca de similares não encontrado{s} (ID{s} {ids})"
            logger.error(msg=msg)
            raise HTTPException(status_code=404, detail=msg)

        # Processa o conteúdo dos documentos
        dict_ids_contents = []
        for _, row in df_docs.iterrows():
            content = row["content_doc"] or ""

            # Processa o conteúdo baseado no parâmetro raw
            if raw:
                processed_content = process_html_raw(content)
            else:
                processed_content = process_html(content)

            dict_ids_contents.append(
                {
                    "id_document": row["id_protocolo_documento"],
                    "content": processed_content,
                }
            )

        return dict_ids_contents

    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.error(f"Erro ao buscar conteúdo dos documentos: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erro interno ao buscar documentos: {str(e)}"
        ) from e


def get_proc_content_lazy(id_proc: int) -> dict[str, str | list[str]]:
    """Recupera o conteúdo de um processo com base no ID fornecido.

    Parameters:
        id_proc (int): O ID do processo.

    Returns:
        dict: Um dicionário contendo as informações e conteúdo do processo.

    Raises:
        HTTPException: Se o processo estiver vazio ou não for encontrado.
    """
    try:
        # Busca metadados do processo
        df_process_metadata = SEIDBHandler.md_ia_consulta_processo(str(id_proc))

        if df_process_metadata.empty:
            raise HTTPException(
                status_code=503, detail=f"Processo {id_proc} não encontrado"
            )

        # Busca documentos elegíveis do processo
        try:
            list_doc_ids = (
                SEIDBHandler.md_ia_lista_documentos_elegiveis_processos_similares(
                    str(id_proc)
                )
            )
            if not list_doc_ids:
                raise HTTPException(
                    status_code=503,
                    detail=f"Processo {id_proc} sem documentos elegíveis",
                )

            # Busca conteúdo dos documentos
            ids_str = ",".join(map(str, list_doc_ids))
            df_docs_processo = SEIDBHandler.md_ia_consulta_documento(
                id_documentos=ids_str,
                conteudo=True,
                sin_filtra_documentos_relevantes="S",
                sin_filtra_bloqueados="N",
                sin_filtra_ativos="S",
            )
        except Exception:
            # Fallback: tenta buscar documentos sem filtro específico
            df_docs_processo = pd.DataFrame()

        if df_docs_processo.empty:
            raise HTTPException(
                status_code=503, detail=f"Processo {id_proc} sem documentos"
            )

        # Monta metadados do processo
        proc_info = df_process_metadata.iloc[0]
        proc = {
            "metadata_name_id_type_process": proc_info["name_id_type_process"],
            "metadata_id_unit_process_generator": proc_info[
                "id_unit_process_generator"
            ],
            "metadata_process_specification": proc_info["processo_especificacao"],
            "metadata_id_contact_interested": " ".join(
                str(proc_info["interessado"]).split(",")
            ),
            "metadata_info_related_processes": "",  # Relacionamentos não disponíveis diretamente no SEIDBHandler
        }

        content_citations = []
        for id_type_doc in set(df_docs_processo["id_type_document"]):
            docs_by_type = df_docs_processo[
                df_docs_processo["id_type_document"] == id_type_doc
            ]
            name = docs_by_type["name_id_type_doc"].iloc[0]
            content = [process_html(doc or "") for doc in docs_by_type["content_doc"]]
            spec = docs_by_type["documento_especificacao"].to_numpy().tolist()

            for c in content:
                content_citations.extend(
                    re.findall(
                        r"[\d]{5}\.[\d]{6}\/[\d]{4}\-[\d]{2}|(?<=[^\d])[\d]{7}(?=[^\d])",
                        c,
                    )
                )

            proc[f"metadata_name_id_type_doc_{id_type_doc}"] = name
            proc[f"content_id_type_doc_{id_type_doc}"] = content
            proc[f"metadata_specification_id_type_doc_{id_type_doc}"] = spec

        proc["content_citations"] = re.sub(
            r"[^\d\s]", "", re.sub(r"[\s]+", " ", " ".join(set(content_citations)))
        ).strip()

        return proc

    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.error(f"Erro ao buscar conteúdo do processo {id_proc}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erro interno ao buscar processo: {str(e)}"
        ) from e


def get_tokenized_proc(
    id_protocolo: int, text_fields: list[str], string_fields: list[str]
) -> dict[str, list[str]]:
    """Tokeniza o conteúdo de um processo com base nos campos fornecidos.

    Parameters:
        id_protocolo (int): O ID do protocolo.
        text_fields (List[str]): Lista de campos de texto a serem tokenizados.
        string_fields (List[str]): Lista de campos de string a serem divididos em tokens.

    Returns:
        dict: Um dicionário com os campos tokenizados do processo.
    """
    raw_proc = get_proc_content_lazy(id_protocolo)
    proc = {}
    for k in raw_proc:
        if any(f in k for f in text_fields):
            proc[k] = solr_preprocessing(
                " ".join(raw_proc[k]) if isinstance(raw_proc[k], list) else raw_proc[k]
            )
        elif any(f in k for f in string_fields):
            proc[k] = raw_proc[k].split()
        else:
            continue
    return proc


def get_tokenized_docs(list_id_doc: list[int]) -> list[dict[str, int | str]]:
    """Tokeniza o conteúdo de documentos com base em seus IDs.

    Parameters:
        list_id_doc (List[int]): Lista de IDs dos documentos.

    Returns:
        List[Dict[str, Union[int, str]]]: Lista de documentos tokenizados.
    """
    docs = get_doc_content_lazy(list_id_doc)
    return [
        {
            "id_document": doc["id_document"],
            "content": solr_preprocessing(doc["content"]),
        }
        for doc in docs
    ]

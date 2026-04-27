"""process_transformed module."""

from datetime import datetime

import pandas as pd
from bs4 import BeautifulSoup
from pydantic import BaseModel, validator

from jobs.dags.inference.regex import apply_regex_model
from jobs.dags.preprocessing.sections_dictionary import SECTIONS_DICTIONARY
from jobs.dags.preprocessing.split_section2 import SplitSection
from jobs.dags.preprocessing.text_clean import (
    remove_encoding,
    remove_sep_token,
)
from jobs.db_models.repository import app_db
from jobs.utils.funcs import get_job_version_manager


def zero_pad(initial_list, total_len, zero):
    return [
        (initial_list[i] if i < len(initial_list) else zero) for i in range(total_len)
    ]


class ProcessTransformed(BaseModel):
    """Classe que representa um processo transformado."""

    id_protocolo: str
    df_process_documents: pd.DataFrame
    df_process_metadata: pd.DataFrame
    df_related_processes: pd.DataFrame
    interested_max: int
    related_processes_max: int
    solr_dict: dict | None = None
    content_id_type_docs_aggs: dict | None = None
    content_type_id_type_docs_aggs: dict | None = None
    metadata_name_id_type_doc_aggs: dict | None = None
    metadata_name_id_type_process: str | None = None
    metadata_specification_id_type_doc_aggs: list[str] | None = None
    dt_ref_insert: datetime | None = None

    class Config:
        arbitrary_types_allowed = True

    @validator("df_process_documents", pre=True)
    def dataframe_validator(cls, value):
        if not isinstance(value, pd.DataFrame):
            raise ValueError("dataframe must be a pandas DataFrame")
        return value

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.fabric_solr_dict()

    def fabric_solr_dict(self) -> None:
        """Retorna um dicionario com o schema para armazenar no solr."""
        metadata_process = self.extract_metadata_process()
        doc_information = self.__group_content_by_type_doc()

        self.metadata_name_id_type_process = metadata_process[
            "metadata_name_id_type_process"
        ]
        self.content_id_type_docs_aggs = doc_information["content_id_type_docs_aggs"]
        self.content_type_id_type_docs_aggs = doc_information[
            "content_type_id_type_docs_aggs"
        ]
        self.metadata_name_id_type_doc_aggs = doc_information[
            "metadata_name_id_type_doc_aggs"
        ]
        self.metadata_specification_id_type_doc_aggs = doc_information[
            "metadata_specification_id_type_doc_aggs"
        ]

        documents_content = self.__spread_documents_content()

        self.solr_dict = {
            **metadata_process,
            **documents_content,
            "version_manager_id": int(get_job_version_manager(app_db)),
            "list_documents": self.df_process_documents["id_protocolo_documento"]
            .to_numpy()
            .tolist(),
        }
        if self.dt_ref_insert:
            self.solr_dict["dt_ref_insert"] = self.dt_ref_insert.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        else:
            self.solr_dict["dt_ref_insert"] = datetime.now().strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

    def __spread_documents_content(self):
        """Expande o dicionario de conteudo por tipo de documento."""
        DOCS_WITH_SECTIONS = {
            "8": "acordao",
            "7": "analise",
            "4": "despacho",
            "16": "informe",
            "94": "voto",
        }

        content_spread = {}
        for id_type_doc, content in self.content_id_type_docs_aggs.items():
            content_spread[f"metadata_name_id_type_doc_{id_type_doc}"] = (
                self.metadata_name_id_type_doc_aggs[id_type_doc]
            )
            content_spread[f"metadata_specification_id_type_doc_{id_type_doc}"] = [
                s
                for s in self.metadata_specification_id_type_doc_aggs[id_type_doc]
                if s is not None and s.strip()
            ]

            if str(id_type_doc) in DOCS_WITH_SECTIONS:
                for ith_content in content:
                    if ith_content is not None:
                        sects_info = SECTIONS_DICTIONARY[
                            DOCS_WITH_SECTIONS[str(id_type_doc)]
                        ]

                        sects = SplitSection(
                            ith_content, html_sections=sects_info
                        ).create_sections()
                        for k in sects_info:
                            field_name = f"content_id_type_doc_{id_type_doc}_{k}"
                            if field_name not in content_spread:
                                content_spread[field_name] = [
                                    remove_sep_token(sects[k])
                                ]
                            else:
                                content_spread[field_name].append(
                                    remove_sep_token(sects[k])
                                )

            content_spread[f"content_id_type_doc_{id_type_doc}"] = (
                self.transform_html_to_text(
                    content, self.content_type_id_type_docs_aggs[id_type_doc]
                )
            )

        return content_spread

    def extract_info_related_processes(self):
        info_related_processes = ",".join(
            self.df_related_processes["processo_especificacao"]
            .fillna("")
            .to_numpy()
            .tolist()
            + self.df_related_processes["name_interested"]
            .fillna("")
            .to_numpy()
            .tolist()
            + self.df_related_processes["name_id_unit_process_generator"]
            .fillna("")
            .to_numpy()
            .tolist()
            + self.df_related_processes["name_id_type_process"]
            .fillna("")
            .to_numpy()
            .tolist()
            + self.df_related_processes["documento_especificacao"]
            .fillna("")
            .to_numpy()
            .tolist()
            + self.df_related_processes["name_id_type_doc"]
            .fillna("")
            .to_numpy()
            .tolist()
        )

        return " ".join(info_related_processes.split(","))

    def extract_metadata_process(self):
        """Extrai informações do processo."""
        id_protocolo = self.df_process_metadata["id_protocolo"].iloc[0]
        protocolo_formatado = self.df_process_metadata["protocolo_formatado"].iloc[0]
        id_type_process = self.df_process_metadata["id_type_process"].iloc[0]
        metadata_name_id_type_process = self.df_process_metadata[
            "name_id_type_process"
        ].iloc[0]
        metadata_id_unit_process_generator = self.df_process_metadata[
            "id_unit_process_generator"
        ].iloc[0]
        metadata_process_specification = self.df_process_metadata[
            "processo_especificacao"
        ].iloc[0]
        _interessado = self.df_process_metadata["interessado"].iloc[0]
        metadata_id_contact_interested = (
            str(_interessado).split(",") if _interessado is not None else [""]
        )
        metadata_info_related_processes = self.extract_info_related_processes()
        metadata_citations = " ".join(
            apply_regex_model(
                pd.Series(
                    self.transform_html_to_text(
                        self.df_process_documents["content_doc"],
                        self.df_process_documents["content_type"],
                    )
                )
            )
            .to_numpy()
            .tolist()
        )
        return {
            "id_protocolo": id_protocolo,
            "protocolo_formatado": protocolo_formatado,
            "id_type_process": id_type_process,
            "metadata_name_id_type_process": metadata_name_id_type_process,
            "metadata_id_unit_process_generator": metadata_id_unit_process_generator,
            "metadata_process_specification": metadata_process_specification,
            "metadata_id_contact_interested": " ".join(
                zero_pad(metadata_id_contact_interested, self.interested_max, "0")
            ),
            "metadata_info_related_processes": metadata_info_related_processes,
            "metadata_citations": " ".join(set(metadata_citations.split())),
        }

    def __group_content_by_type_doc(self):
        """Agrupa os textos por tipo de documento."""
        docs_process = self.df_process_documents
        docs_aggs_content = (
            docs_process.groupby("id_type_document")
            .agg(
                {
                    "content_doc": list,
                    "content_type": list,
                    "dta_inclusao": "last",
                    "name_id_type_doc": "last",
                    "documento_especificacao": list,
                }
            )
            .reset_index()
        )

        join_content_desc_id_type_docs = (
            docs_aggs_content[
                [
                    "id_type_document",
                    "content_doc",
                    "content_type",
                    "name_id_type_doc",
                    "documento_especificacao",
                ]
            ]
            .set_index("id_type_document")
            .to_dict()
        )

        dta_last_update = docs_aggs_content["dta_inclusao"].max()

        return {
            "content_id_type_docs_aggs": join_content_desc_id_type_docs["content_doc"],
            "content_type_id_type_docs_aggs": join_content_desc_id_type_docs[
                "content_type"
            ],
            "metadata_name_id_type_doc_aggs": join_content_desc_id_type_docs[
                "name_id_type_doc"
            ],
            "dta_last_update": dta_last_update,
            "metadata_specification_id_type_doc_aggs": join_content_desc_id_type_docs[
                "documento_especificacao"
            ],
        }

    @staticmethod
    def transform_html_to_text(docs_process, docs_types):
        """Transforma os htmls em textos."""
        text_docs = []
        for doc, _doc_type in zip(docs_process, docs_types, strict=False):
            if doc is not None:
                soup = BeautifulSoup(doc, "lxml")
                if bool(soup.find()):
                    if not soup.find("body"):
                        text_docs.append(
                            remove_encoding(soup.get_text()).replace("\u202f", " ")
                        )
                    else:
                        text_docs.append(
                            remove_encoding(soup.find("body").get_text()).replace(
                                "\u202f", " "
                            )
                        )
                else:
                    text_docs.append(" ".join(doc.split()))
            if doc is None:
                text_docs.append("")

        return text_docs

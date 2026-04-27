"""process_from_sei module."""

import logging
import re
from dataclasses import dataclass, field

import pandas as pd

from jobs.dags.preprocessing.process_transformed import ProcessTransformed
from jobs.db_models.sei_db_handlers import SEIDBHandler
from jobs.envs import FORMATS
from jobs.utils.funcs import group_concat_distinct, regexp_replace

logger = logging.getLogger(__name__)


@dataclass
class ProcessFromSEI:
    """Classe que busca no banco de dados os documentos de um processo
    e cria um objeto ProcessTransformed com os dados prontos para
    serem armazenados no banco de dados Solr.
    """

    id_protocolo: str
    id_type_process: int
    interested_max: int
    related_processes_max: int
    subprocesses: bool = True
    dt_ref_insert: str = None
    processes_str: str = field(init=False, default="")
    df_process_metadata: pd.DataFrame = field(init=False, default_factory=pd.DataFrame)
    related_processes_str: str = field(init=False, default="")
    df_related_processes: pd.DataFrame = field(init=False, default_factory=pd.DataFrame)
    df_process_documents: pd.DataFrame = field(init=False, default_factory=pd.DataFrame)
    docs_list: list = field(init=False, default_factory=list)
    process_transformed: any = field(init=False, default=None)

    def __post_init__(self):
        self.fabric_process_transformed()

    def fabric_process_transformed(self):
        """Retorna um objeto ProcessTransformed."""
        self.df_process_metadata = ProcessFromSEI.get_process_metadata(
            self.id_protocolo
        )

        if self.df_process_metadata.shape[0] == 0:
            return None

        self.df_process_documents = ProcessFromSEI.get_docs_from_process(
            self.id_protocolo
        )

        self.docs_list = ProcessFromSEI.list_documents(self.df_process_documents)

        if len(self.docs_list) == 0:
            return None

        self.processes_str = ProcessFromSEI.get_process_and_subprocesses_str(
            self.id_protocolo, self.subprocesses
        )

        self.related_processes_str = ProcessFromSEI.get_formatted_related_processes(
            self.df_process_metadata
        )

        self.df_related_processes = ProcessFromSEI.get_info_related_processes(
            self.related_processes_str
        )

        self.process_transformed = ProcessTransformed(
            id_protocolo=self.id_protocolo,
            df_process_documents=self.df_process_documents,
            df_process_metadata=self.df_process_metadata,
            df_related_processes=self.df_related_processes,
            interested_max=self.interested_max,
            related_processes_max=self.related_processes_max,
            dt_ref_insert=self.dt_ref_insert,
        )
        return self.process_transformed

    @staticmethod
    def get_formatted_related_processes(df):
        """Extrai e formata processos relacionados de um DataFrame.

        Args:
            df: DataFrame contendo colunas 'processos_relacionados_1'

        Returns:
            str: String com IDs de processos relacionados formatados e ordenados
        """
        # Verificação de segurança: DataFrame vazio
        if df.empty or len(df) == 0:
            return ""

        # Verificação de segurança: colunas não existem
        if "processos_relacionados_1" not in df.columns:
            return ""

        # Pega os valores (deve haver apenas uma linha após groupby)
        try:
            related_processes_1 = df["processos_relacionados_1"].iloc[0]
        except (IndexError, KeyError):
            return ""

        # Converte None para string vazia
        if related_processes_1 is None:
            related_processes_1 = ""

        # Converte para string se não for
        related_processes_1 = str(related_processes_1)

        # Extrai números das strings
        rel = re.findall(r"[\d]+", related_processes_1)

        # Remove duplicatas, ordena e junta
        return ",".join(sorted(set(rel)))

    @staticmethod
    def list_documents(df: pd.DataFrame) -> list:
        if df.empty:
            return []
        s = df["id_protocolo_documento"]
        return s[~s.isna()].to_numpy().tolist()

    @staticmethod
    def get_formats_str():
        return "'" + "','".join(FORMATS) + "'"

    @staticmethod
    def get_id_documents_allowed(processes_str: str) -> str:
        # Valida string vazia ANTES de chamar API
        if not processes_str or not processes_str.strip():
            return ""

        id_docs = SEIDBHandler.md_ia_lista_documentos_elegiveis_processos_similares(
            processes_str
        )
        return ",".join(map(str, id_docs))

    @staticmethod
    def get_process_and_subprocesses_str(id_protocolo, subprocesses=True):
        id_protocolos = str(id_protocolo)

        if subprocesses:
            subproc = SEIDBHandler.get_subprocessos_id_protocolo(id_protocolo)
            if subproc.shape[0] > 0:
                id_protocolos = ",".join(
                    map(str, [id_protocolo, *subproc["id_protocolo_2"].tolist()])
                )

        return id_protocolos

    @staticmethod
    def get_process_metadata(id_protocolo):
        df_metadata = SEIDBHandler.get_process_metadata(id_procedimento=id_protocolo)
        df_metadata.columns = map(str.lower, df_metadata.columns)
        if df_metadata.empty:
            return pd.DataFrame()
        return (
            df_metadata.groupby("id_protocolo")
            .agg(
                protocolo_formatado=("protocolo_formatado", "first"),
                processo_especificacao=("processo_especificacao", "first"),
                interessado=("interessado", lambda x: group_concat_distinct(x)),
                processos_relacionados_1=(
                    "processos_relacionados_1",
                    lambda x: group_concat_distinct(x),
                ),
                processos_relacionados_2=(
                    "processos_relacionados_2",
                    lambda x: group_concat_distinct(x),
                ),
                id_type_process=("id_type_process", "first"),
                id_unit_process_generator=("id_unit_process_generator", "first"),
                name_id_type_process=("name_id_type_process", "first"),
            )
            .reset_index()
        )

    @staticmethod
    def get_info_related_processes(related_processes_str):
        id_docs_str = ProcessFromSEI.get_id_documents_allowed(related_processes_str)

        if (related_processes_str.strip()) and (id_docs_str != ""):
            info_related_processes = ProcessFromSEI.agg_related_process_query(
                id_docs_str
            )
        else:
            info_related_processes = pd.DataFrame(
                columns=[
                    "id_protocolo",
                    "protocolo_formatado",
                    "processo_especificacao",
                    "interessado",
                    "name_interested",
                    "id_type_process",
                    "id_unit_process_generator",
                    "name_id_unit_process_generator",
                    "name_id_type_process",
                    "documento_especificacao",
                    "name_id_type_doc",
                ]
            )  # TODOS ESSES CAMPOS VÃO SER COLETADOS NA API DE consultar_processo EXCETO documento_especificacao
        return info_related_processes

    @staticmethod
    def get_docs_from_process(id_protocolo):
        """Retorna os documentos de um processo."""
        docs_process = pd.DataFrame()
        id_protocolo = str(id_protocolo)
        id_docs_str = ProcessFromSEI.get_id_documents_allowed(id_protocolo)
        docs_process = SEIDBHandler.md_ia_consulta_documento(id_docs_str)

        return docs_process.drop_duplicates(subset=["id_protocolo_documento"])

    @staticmethod
    def agg_related_process_query(id_docs_str: str) -> pd.DataFrame:
        """Agrega a query de processos relacionados.

        Args:
            related_processes_str: String contento os ids dos processos relacionados
            id_docs_str: String contendo ids de documentos separados por vírgula

        Returns:
            pd.DataFrame: Dataframe com colunas id_protocolo, protocolo_formatado, processo_especificacao,
            interessado, name_interested, id_type_process, id_unit_process_generator, name_id_unit_process_generator,
            name_id_type_process, documento_especificacao e name_id_type_doc.

        Raises:
            SeiDBAPIError: Em caso de erro na requisição ou na resposta da API
        """
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
            "documento_especificacao",
            "name_id_type_doc",
        ]

        def _post_process(df: pd.DataFrame) -> pd.DataFrame:
            fillna_cols = [
                "processo_especificacao",
                "interessado",
                "name_interested",
                "documento_especificacao",
                "id_unit_process_generator",
                "name_id_unit_process_generator",
                "name_id_type_doc",
            ]
            df[fillna_cols] = df[fillna_cols].fillna("")

            df["name_id_unit_process_generator"] = df[
                "name_id_unit_process_generator"
            ].apply(regexp_replace)
            df["name_interested"] = df["name_interested"].apply(regexp_replace)

            return (
                df.groupby("id_protocolo")
                .agg(
                    protocolo_formatado=("protocolo_formatado", "first"),
                    processo_especificacao=("processo_especificacao", "first"),
                    interessado=("interessado", lambda x: group_concat_distinct(x)),
                    name_interested=(
                        "name_interested",
                        lambda x: group_concat_distinct(x),
                    ),
                    id_type_process=("id_type_process", "first"),
                    id_unit_process_generator=("id_unit_process_generator", "first"),
                    name_id_unit_process_generator=(
                        "name_id_unit_process_generator",
                        "first",
                    ),
                    name_id_type_process=("name_id_type_process", "first"),
                    documento_especificacao=(
                        "documento_especificacao",
                        lambda x: group_concat_distinct(x),
                    ),
                    name_id_type_doc=(
                        "name_id_type_doc",
                        lambda x: group_concat_distinct(x),
                    ),
                )
                .reset_index()
            )

        df_docs = SEIDBHandler.md_ia_consulta_documento(id_docs_str, conteudo=False)
        records = []
        if df_docs.empty:
            return pd.DataFrame(columns=columns)
        for id_protocolo in df_docs["id_protocolo"].unique():
            processo = SEIDBHandler.md_ia_consulta_processo(id_protocolo)
            docs_protocolo = df_docs[df_docs["id_protocolo"] == id_protocolo]

            for _, row in docs_protocolo.iterrows():
                registros = {
                    "id_protocolo": id_protocolo,
                    "protocolo_formatado": processo.get("ProtocoloFormatado"),
                    "processo_especificacao": processo.get("EspecificacaoProcesso"),
                    "interessado": processo.get("Interessados", [{}])[0].get(
                        "IdInteressado"
                    ),
                    "name_interested": processo.get("Interessados", [{}])[0].get(
                        "NomeInteressado"
                    ),
                    "id_type_process": processo.get("IdTipoProcesso"),
                    "id_unit_process_generator": processo.get(
                        "IdUnidadeGeradoraProcesso"
                    ),
                    "name_id_unit_process_generator": processo.get(
                        "DescricaoUnidadeGeradoraProcesso"
                    ),
                    "name_id_type_process": processo.get("TipoProcesso"),
                    "documento_especificacao": row["documento_especificacao"],
                    "name_id_type_doc": row["name_id_type_doc"],
                }
                records.append(registros)

        df_related = pd.DataFrame(records)
        return _post_process(df_related)

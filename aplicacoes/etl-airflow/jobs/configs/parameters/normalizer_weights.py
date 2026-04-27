"""normalizer_weights module."""

import logging

import pandas as pd

from jobs.configs.parameters import utils
from jobs.dags.preprocessing.sections_dictionary import SECTIONS_DICTIONARY
from jobs.db_models.sei_db_handlers import SEIDBHandler

logger = logging.getLogger(__name__)


class DocumentSegmentNormalizer:
    """Classe para normalizar segmentos e subsegmentos de documentos."""

    def __init__(self, sections_dictionary) -> None:
        self.sections_dictionary = sections_dictionary

    def normalize_subsegments(self, df):
        df = df.copy()
        df["segmento"] = df["segmento"].str.split(".")
        df_level_0 = pd.DataFrame(df["segmento"].apply(lambda x: x[0]))
        sublevels = df["segmento"].apply(lambda x: x[1:])
        df_final_level_0 = df_level_0.join(
            self._normalize_subsegments_with_pipe(sublevels).explode(),
            how="right",
            rsuffix="_sub",
        ).fillna("")
        return df_final_level_0.join(df.drop("segmento", axis=1), how="left")

    def _normalize_subsegments_with_pipe(self, sublevels):
        return sublevels.apply(
            lambda row: (
                row[0].split("|") if len(row) == 1 else [""] if len(row) == 0 else []
            )
        )

    def normalize_segments_with_pipe(self, df):
        df = df.copy()
        df["segmento"] = df["segmento"].str.split("|")
        return df.explode("segmento").reset_index(drop=True)


def build_remapping_dictionary(df_subset, column_check, id_sections_dictionary):
    remapping_segmento = {}
    for seg in df_subset[column_check].str.lower().unique():
        for seg_dict, seg_options in id_sections_dictionary.get(
            df_subset["id_type_doc"].iloc[0], {}
        ).items():
            seg_options = [utils.clean_txt(seg) for seg in seg_options]
            if utils.clean_txt(seg) in seg_options:
                remapping_segmento[seg.lower()] = seg_dict.lower()
    return remapping_segmento


def apply_remapping_to_df(df, column_check, id_type_doc, id_sections_dictionary):
    df_subset = df[df["id_type_doc"] == id_type_doc]
    remapping_segmento = build_remapping_dictionary(
        df_subset, column_check, id_sections_dictionary
    )
    df.loc[df["id_type_doc"] == id_type_doc, column_check] = df.loc[
        df["id_type_doc"] == id_type_doc, column_check
    ].replace(remapping_segmento)
    return df


def standard_subsegments_relevance(df_norm_pipe: pd.DataFrame) -> pd.DataFrame:
    if df_norm_pipe.empty:
        return pd.DataFrame(
            {
                "segmento": ["default"],
                "segmento_sub": [""],
                "relevancia": [1.0],
                "relevancia_sub": [1.0],
                "id_type_doc": [0],
                "id_md_ia_adm_doc_relev": [0],
            }
        )

    # Existing logic for non-empty case
    df_norm_pipe.loc[:, "relevancia_sub"] = 1.0

    # Converter colunas relevantes explicitamente
    float_cols = ["relevancia", "relevancia_sub"]
    df_segment = df_norm_pipe[df_norm_pipe["segmento_sub"] == ""].copy()
    df_subsegment = df_norm_pipe[df_norm_pipe["segmento_sub"] != ""].copy()

    # Converter tipos antes das operações
    df_segment[float_cols] = df_segment[float_cols].astype("float64")
    df_subsegment[float_cols] = df_subsegment[float_cols].astype("float64")

    # Garantir que remaining_segment seja float
    remaining_segment = df_segment.groupby("id_type_doc").apply(
        lambda x: 100.0 - x["relevancia"].sum()
    )  # Adicionado .0

    # Cálculo final com conversão explícita
    df_subsegment.loc[:, "relevancia_sub"] = df_subsegment.apply(
        lambda x: x["relevancia"] / remaining_segment[x["id_type_doc"]], axis=1
    ).astype("float64")

    return pd.concat([df_segment, df_subsegment])


def fill_remanining_relevance(df_norm_pipe_standard: pd.DataFrame) -> pd.DataFrame:
    """Para as definições da relevancia dos documentos que não alcancarem 100% de relevância
    será feito um preenchimento com a relevância do preeambulo do documento.
    """
    if df_norm_pipe_standard.empty or (
        len(df_norm_pipe_standard) == 1
        and df_norm_pipe_standard["segmento"].iloc[0] == "default"
    ):
        return pd.DataFrame(
            {
                "segmento": ["default"],
                "segmento_sub": [""],
                "relevancia": [1.0],
                "relevancia_sub": [1.0],
                "id_type_doc": [0],
                "id_md_ia_adm_doc_relev": [0],
                "relevancia_final": [1.0],
            }
        )

    df_fill = df_norm_pipe_standard.copy()
    df_fill["relevancia_final"] = (
        df_norm_pipe_standard["relevancia"] * df_norm_pipe_standard["relevancia_sub"]
    )
    remaining_relevance = 100 - df_fill.groupby("id_type_doc")["relevancia_final"].sum()
    remaining_relevance = remaining_relevance[remaining_relevance > 0]
    for id_type_doc, rel in remaining_relevance.items():
        fill_row = {
            "segmento": "preambulo",
            "segmento_sub": "",
            "id_md_ia_adm_doc_relev": df_fill.query(f"id_type_doc == {id_type_doc}")[
                "id_md_ia_adm_doc_relev"
            ].iloc[0],
            "id_type_doc": id_type_doc,
            "relevancia": rel,
            "relevancia_sub": 1,
            "relevancia_final": rel,
        }
        df_fill = pd.concat([df_fill, pd.DataFrame([fill_row])], ignore_index=True)
    df_fill.loc[:, "relevancia_final"] = df_fill["relevancia_final"]
    df_fill.loc[:, "relevancia"] = df_fill["relevancia"]
    return df_fill


def run():
    normalizer = DocumentSegmentNormalizer(SECTIONS_DICTIONARY)
    df_docs_weights = SEIDBHandler.md_ia_lista_segmentos_documentos_relevantes()

    if df_docs_weights is None or df_docs_weights.empty:
        logger.warning(
            "Nenhum segmento de documento relevante disponível no SEI. "
            "Retornando configuração padrão. O sistema funcionará com pesos uniformes."
        )
        return pd.DataFrame(
            {
                "segmento": ["default"],
                "segmento_sub": [""],
                "relevancia": [100.0],
                "relevancia_sub": [1.0],
                "id_type_doc": [0],
                "id_md_ia_adm_doc_relev": [0],
                "relevancia_final": [100.0],
            }
        )

    df_normalized = normalizer.normalize_segments_with_pipe(
        normalizer.normalize_subsegments(df_docs_weights)
    )

    df_series = SEIDBHandler.md_ia_lista_tipo_documento()
    # Renomear id_serie para id_type_doc para manter consistência com df_normalized
    df_series = df_series.rename(columns={"id_serie": "id_type_doc"})
    df_series["nome"] = df_series["nome"].str.lower().apply(utils.clean_txt)
    type_doc_to_id_type_doc = dict(df_series[["nome", "id_type_doc"]].values)

    ID_SECTIONS_DICTIONARY = {}
    for raw_name, sections in SECTIONS_DICTIONARY.items():
        normalized_name = utils.clean_txt(raw_name)
        id_type_doc = type_doc_to_id_type_doc.get(normalized_name)
        if id_type_doc is None:
            continue
        ID_SECTIONS_DICTIONARY[id_type_doc] = sections

    ids_type_doc = df_normalized["id_type_doc"].unique()
    for id_type in ids_type_doc:
        df_normalized = apply_remapping_to_df(
            df_normalized, "segmento", id_type, ID_SECTIONS_DICTIONARY
        )
        df_normalized = apply_remapping_to_df(
            df_normalized, "segmento_sub", id_type, ID_SECTIONS_DICTIONARY
        )

    df_normalized = df_normalized.drop_duplicates()

    df_norm_pipe_standard = standard_subsegments_relevance(df_normalized).copy()
    df_conf_mlt_fields = fill_remanining_relevance(df_norm_pipe_standard)
    df_conf_mlt_fields["segmento"] = df_conf_mlt_fields["segmento"].apply(
        utils.clean_txt
    )
    df_conf_mlt_fields["segmento_sub"] = df_conf_mlt_fields["segmento_sub"].apply(
        utils.clean_txt
    )
    return df_conf_mlt_fields

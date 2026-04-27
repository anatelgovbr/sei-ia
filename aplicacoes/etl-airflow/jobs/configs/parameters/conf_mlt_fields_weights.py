"""Script para criar a estrutura de pesos do modelo de similaridade."""

import json
import logging

import pandas as pd
from sqlalchemy.exc import ArgumentError

from jobs.configs.parameters import normalizer_weights
from jobs.configs.parameters.default_conf_mlt_fields_weights import data
from jobs.configs.parameters.models import (
    AdmSimilarConfig,
    Content,
    FieldEntry,
    Metadata,
    MetadataModel,
    RootSchema,
)
from jobs.db_models.app_tables import ConfigMltFieldsWeights
from jobs.db_models.repository import app_db
from jobs.db_models.sei_db_handlers import SEIDBHandler

logger = logging.getLogger(__name__)


def add_default_config() -> None:
    """Caso não exista registro na tabela ConfigMLTFieldsWeights.

    Será adicionado os pesos padrões.
    """
    res = app_db.execute_query_one(
        f"SELECT * FROM {ConfigMltFieldsWeights.__tablename__} LIMIT 1"  # noqa: S608
    )
    if res is None:
        try:
            app_db.add(ConfigMltFieldsWeights(weights=data))
        except ArgumentError:
            # Incompatibilidade do airflow com o sqalchemy 2.0
            # Na segunda tentativa funciona
            app_db.add(ConfigMltFieldsWeights(weights=data))


def create_content_nested_structure(df: pd.DataFrame) -> dict:
    """Cria uma estrutura aninhada para campos de conteúdo.

    Args:
        df (pd.DataFrame): DataFrame com informações sobre tipos de documento,
            segmentos e relevância.

    Returns:
        dict: Dicionário aninhado com estrutura dos campos de conteúdo.
              Retorna estrutura vazia se df estiver vazio ou for default.
    """
    tmp_content_dict = {"fields": {}, "weight": 1.0}

    if df is None or df.empty:
        logger.info(
            "DataFrame de segmentos vazio. "
            "Usando estrutura de conteúdo padrão (sem segmentos específicos)."
        )
        return tmp_content_dict

    if len(df) == 1 and df["segmento"].iloc[0] == "default":
        logger.info(
            "Configuração default detectada. "
            "Usando estrutura de conteúdo padrão (pesos uniformes)."
        )
        return tmp_content_dict

    content_dict = tmp_content_dict["fields"]

    for _, row in df.iterrows():
        doc_type = f"content_id_type_doc_{row['id_type_doc']}"
        segment = row["segmento"]
        segment_sub = row["segmento_sub"]
        rel_final = row["relevancia_final"]
        rel_segment_sub = row["relevancia_sub"]
        rel_segment = row["relevancia"]

        if doc_type not in content_dict:
            content_dict[doc_type] = {"fields": {}, "weight": 1.0}

        name_field_segment = f"{doc_type}_{segment}"

        if segment_sub != "":
            name_field_subsegment = f"{name_field_segment}_{segment_sub}"

            if name_field_segment not in content_dict[doc_type]["fields"]:
                content_dict[doc_type]["fields"][name_field_segment] = {
                    "fields": {},
                    "weight": FieldEntry(weight=rel_segment).weight,
                }

            content_dict[doc_type]["fields"][name_field_segment]["fields"][
                name_field_subsegment
            ] = FieldEntry(weight=rel_segment_sub * 100)

        else:
            content_dict[doc_type]["fields"][name_field_segment] = FieldEntry(
                weight=rel_final
            )

    return tmp_content_dict


def create_metadata_structure() -> MetadataModel:
    """Cria a estrutura de pesos dos metadados.

    Args:
        adm_config_similar AdmSimilarConfig: Configuração geral do sistema SEI IA
    """
    df_metadados_weights = SEIDBHandler.md_ia_lista_percentual_relevancia_metadados()
    metadata_weights = (
        df_metadados_weights[["metadado", "relevancia"]]
        .set_index("metadado")
        .to_dict()["relevancia"]
    )
    metadata_weights = {k: FieldEntry(weight=v) for k, v in metadata_weights.items()}
    metadata_structure = MetadataModel(**metadata_weights)
    metadata_structure.update_variable_subfields()
    return metadata_structure


def main() -> str | None:
    """Função principal do script.

    Responsável por criar a estrutura de pesos do modelo de similaridade
    e salvar um registro na tabela ConfigMLTFieldsWeights.

    Caso não exista registro na tabela, será adicionado os pesos padrões.
    """
    add_default_config()
    adm_config_similar = AdmSimilarConfig()
    metadata_structure = None
    nested_structure = None

    try:
        metadata_structure = create_metadata_structure()
    except Exception:
        msg = "Erro ao criar a estrutura de pesos dos metadados:\n{e}"
        logger.exception(msg)
        raise

    try:
        nested_structure = create_content_nested_structure(normalizer_weights.run())
    except Exception:
        msg = "Erro ao criar a estrutura de pesos do conteúdo:\n{e}"
        logger.exception(msg)
        raise

    if metadata_structure and nested_structure:
        try:
            root_schema = RootSchema(
                metadata=Metadata(
                    fields=metadata_structure.dict(),
                    weight=FieldEntry(
                        weight=adm_config_similar.perc_relev_metadados
                    ).weight,
                ),
                content=Content(
                    fields={"content_id_type_doc_": nested_structure},
                    weight=FieldEntry(
                        weight=adm_config_similar.perc_relev_cont_doc
                    ).weight,
                ),
            )
        except Exception:
            msg = "Erro ao criar o objeto de pesos para configuração do MLT:\n"
            raise

        weights_json = json.dumps(root_schema.dict())
        escaped_weights = weights_json.replace("'", "''")

        sql = (
            f"INSERT INTO {ConfigMltFieldsWeights.__tablename__} (weights) "
            f"VALUES ('{escaped_weights}')"
        )  # noqa: S608
        app_db.execute(sql)
        logger.info("Pesos de configuração MLT criados com sucesso.")
        return "Sucesso"

    logger.warning(
        "Pesos podem estar vázios - "
        f"metadata_structure: {metadata_structure}, "
        f"nested_structure: {nested_structure}"
    )
    return None

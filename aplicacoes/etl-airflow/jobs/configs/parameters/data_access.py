"""data_access module."""

import pandas as pd

from jobs.db_models.sei_db_handlers import SEIDBHandler

# sql_adm_config_similar = f"""
# SELECT
#     *
# FROM {db_sei_schema}.md_ia_adm_config_similar
# ORDER BY dth_alteracao DESC
# """

# sql_docs_for_procs =f"""
# SELECT
#     *
# FROM {db_sei_schema}.md_ia_adm_doc_relev
# WHERE sin_ativo = 'S'
# """

# sql_docs_weights = f"""
# SELECT
#     sdr.id_md_ia_adm_doc_relev,
#     segmento_documento as segmento,
#     adr.id_serie as id_type_doc,
#     percentual_relevancia as relevancia
# FROM {db_sei_schema}.md_ia_adm_seg_doc_relev sdr
# INNER JOIN {db_sei_schema}.md_ia_adm_doc_relev adr
#     ON sdr.id_md_ia_adm_doc_relev = adr.id_md_ia_adm_doc_relev
# """

# sql_series = f"""
# SELECT
#     nome,
#     id_serie
# FROM {db_sei_schema}.serie
# """

# sql_metadados_weights = f"""
# SELECT
#     prm.id_md_ia_adm_config_similar,
#     prm.id_md_ia_adm_metadado as id_metadado,
#     m.metadado,
#     prm.percentual_relevancia as relevancia,
#     prm.dth_alteracao
# FROM {db_sei_schema}.md_ia_adm_perc_relev_met prm
# INNER JOIN {db_sei_schema}.md_ia_adm_metadado m
#     ON prm.id_md_ia_adm_metadado = m.id_md_ia_adm_metadado
# WHERE prm.id_md_ia_adm_config_similar = {{id_config}}
# """


class DataAccess:
    @staticmethod
    def fetch_docs_weights() -> pd.DataFrame:
        return SEIDBHandler.md_ia_lista_segmentos_documentos_relevantes()

    @staticmethod
    def fetch_series() -> pd.DataFrame:
        return SEIDBHandler.md_ia_lista_tipo_documento()

    @staticmethod
    def fetch_metadados_weights() -> pd.DataFrame:
        """Obs: o nome dos metadados na tabela do SEI IA é diferente do nome dos metadados
        utilizados no codigo. Por enquanto será alterado via dicionário, mas o ideal é
        alterar no codigo padronizando o nome dos campos.
        """
        return SEIDBHandler.md_ia_lista_percentual_relevancia_metadados()

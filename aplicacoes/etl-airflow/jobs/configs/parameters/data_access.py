"""data_access module."""

import pandas as pd

from jobs.db_models.sei_client import sei_client


class DataAccess:
    @staticmethod
    def fetch_docs_weights() -> pd.DataFrame:
        return sei_client.md_ia_lista_segmentos_documentos_relevantes()

    @staticmethod
    def fetch_series() -> pd.DataFrame:
        return sei_client.md_ia_lista_tipo_documento()

    @staticmethod
    def fetch_metadados_weights() -> pd.DataFrame:
        """Obs: o nome dos metadados na tabela do SEI IA é diferente do nome dos metadados
        utilizados no codigo. Por enquanto será alterado via dicionário, mas o ideal é
        alterar no codigo padronizando o nome dos campos.
        """
        return sei_client.md_ia_lista_percentual_relevancia_metadados()

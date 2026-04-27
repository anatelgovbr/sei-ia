"""Module containing code to help posting data to a solr core."""

import json

import numpy as np
import pandas as pd
import requests

from jobs.envs import VERIFY_SSL


def is_not_nan(value) -> bool:
    # Check if all values in the array are NaN

    if isinstance(value, float) and np.isnan(value):
        return False
    if isinstance(value, np.ndarray):
        return not np.isnan(value).all()
    return True


class GenericSender:
    """Base class for classes intended to help posting data to solr."""

    def __init__(self, df: pd.DataFrame, core_url) -> None:
        """Class initialization code.

        Args:
            df: data to be sent to solr. Type: pandas dataframe
            core_url: full url specifying the solr core
        """
        self.df = df
        self.core_url = core_url

    def send_all_docs_to_solr(self, auth=None) -> None:
        """Sends all docs to solr, with each row being one document,
        and each column being one document field.
        """
        for _i, row in self.df.iterrows():
            doc = row.to_dict()
            self.send_one_doc_to_solr(doc, self.core_url, auth=auth)

    def send_docs_in_bulk_to_solr(self, auth=None):
        """Envia um lote de documentos para o Solr.

        Args:
            docs: lista de documentos a serem enviados
        """
        df_dict_list = self.df.to_dict(orient="records")

        cleaned_dict_list = [
            {k: v for k, v in d.items() if is_not_nan(v)} for d in df_dict_list
        ]

        data = json.dumps(cleaned_dict_list)

        # https://solr.apache.org/guide/6_6/transforming-and-indexing-custom-json.html
        response = requests.post(
            f"{self.core_url.rstrip('/')}/update/json/docs?commit=true",
            headers={"Content-Type": "application/json; charset=utf-8"},
            data=data,
            timeout=5000,
            auth=auth,
            verify=VERIFY_SSL,
        )
        if response.status_code != requests.codes.ok:
            raise Exception(response.text)

        return response

    @staticmethod
    def send_one_doc_to_solr(doc, core_url, auth=None):
        """Sends a specific doc to the solr core.

        Args:
            doc: document to be sent to the specific solr core. Type: dict
            core_url: full url specifying the solr core

        """
        import json

        # https://cwiki.apache.org/confluence/display/solr/updatexmlmessages
        data = json.dumps({"add": {"doc": doc, "commitWithin": 1000}}).encode("utf-8")

        # https://stackoverflow.com/questions/34618149/post-unicode-string-to-web-service-using-python-requests-library
        response = requests.post(
            f"{core_url.rstrip('/')}/update?wt=json",
            headers={"Content-Type": "application/json; charset=utf-8"},
            data=data,
            timeout=5000,
            auth=auth,
            verify=VERIFY_SSL,
        )
        if response.status_code != requests.codes.ok:
            raise Exception(response.text)

        return response

    @staticmethod
    def update_bulk_fields(core_url, updates, auth=None):
        """Updates multiple fields in multiple documents in the solr core using bulk operation.

        Args:
            core_url: full url specifying the solr core.
            updates: list of updates, where each update is a list containing
                     id_field, id_field_value, new_field, new_field_value.
        """
        bulk_data = []
        for update in updates:
            id_field, id_field_value, new_field, new_field_value = update
            bulk_data.append(
                {id_field: id_field_value, new_field: {"set": new_field_value}}
            )

        data = json.dumps(bulk_data).encode("utf-8")
        response = requests.post(
            f"{core_url.rstrip('/')}/update?wt=json&commit=true",
            headers={"Content-Type": "application/json; charset=utf-8"},
            data=data,
            timeout=5000,
            auth=auth,
            verify=VERIFY_SSL,
        )
        if response.status_code != requests.codes.ok:
            raise Exception(response.text)

        return response

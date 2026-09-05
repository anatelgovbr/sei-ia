import unittest
from unittest import mock
from api_sei.db_models.get_content_lazy import get_proc_content_lazy, get_tokenized_proc
import pandas as pd
from api_sei.resources.bm25 import extract

df_process = pd.DataFrame(
    {
        "name_id_type_process": ["PADO: Home Passed"],
        "id_unit_process_generator": ["110000941"],
        "processo_especificacao": ["Editora Diário da Amazônia 3ª Meta"],
        "interessado": ["100323910"],
    }
)

df_docs = pd.DataFrame(
    {
        "id_type_document": [7],
        "name_id_type_doc": ["Análise"],
        "content_doc": [
            "de fato, a prestadora apresentou pedido de renúncia (petição sei nº 0244325), "
            "nos autos do processo nº 00000.000000/0000-00, tendo este conselho diretor "
            "declarado a extinção da outorga, por renúncia, a partir da mesma data, por meio "
            "do acórdão nº 166/2019 (sei nº 4013198), nos autos do processo nº 00000.000000/0000-00."
        ],
        "documento_especificacao": [""],
    }
)

text_fields = SEARCH_FIELDS_PREFIXES = [
    "metadata_name_id_type_process",
    "metadata_process_specification",
    "metadata_info_related_processes",
    "metadata_name_id_type_doc_7",
    "metadata_specification_id_type_doc_7",
    "content_id_type_doc_7",
]

string_fields = [
    "metadata_id_unit_process_generator",
    "metadata_id_contact_interested",
    "content_citations",
]


class TestGetContentLazy(unittest.TestCase):

    @mock.patch("api_sei.db_models.get_content_lazy.consulta_documentos_com_conteudo")
    @mock.patch("api_sei.db_models.get_content_lazy.sei_client")
    def test_get_proc_content_lazy(self, mock_sei_client, mock_consulta_docs):
        mock_sei_client.md_ia_consulta_processo_metadados.return_value = df_process
        mock_sei_client.md_ia_lista_documentos_elegiveis_processos_similares.return_value = [1]
        mock_consulta_docs.return_value = df_docs

        proc = get_proc_content_lazy(3619868)

        self.assertEqual(
            set(proc["content_citations"].split()),
            {"0244325", "53581000032201653", "4013198", "53500008851201278"},
        )

    @mock.patch("api_sei.resources.bm25.get_field_terms_statistics")
    @mock.patch("api_sei.db_models.get_content_lazy.consulta_documentos_com_conteudo")
    @mock.patch("api_sei.db_models.get_content_lazy.sei_client")
    def test_get_tokenized_proc(self, mock_sei_client, mock_consulta_docs, mock_field_terms_statistics):
        mock_sei_client.md_ia_consulta_processo_metadados.return_value = df_process
        mock_sei_client.md_ia_lista_documentos_elegiveis_processos_similares.return_value = [1]
        mock_consulta_docs.return_value = df_docs

        proc = get_tokenized_proc(3619868, text_fields, string_fields)

        mock_field_terms_statistics.return_value = (
            102,
            {"0244325": 0, "53581000032201653": 1, "4013198": 0, "53500008851201278": 1},
            4980 / 102,
        )

        tokens_scores = extract("", "content_citations", proc["content_citations"])

        self.assertEqual(len(tokens_scores), 4)

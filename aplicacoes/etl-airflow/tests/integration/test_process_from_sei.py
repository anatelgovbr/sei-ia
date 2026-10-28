import unittest

import random

import pandas as pd

from jobs.dags.preprocessing.process_from_sei import ProcessFromSEI


class TestProcessFromSEI(unittest.TestCase):
    """test ProcessFromSEI.get_formatted_related_processes"""

    def test_get_formatted_related_processes_usual(self):
        df = pd.DataFrame(
            {"processos_relacionados_1": ["122333,3334444"],
             "processos_relacionados_2": ["5555522,1224444"]}
        )
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "122333,1224444,3334444,5555522")

    def test_get_formatted_related_processes_two_empty(self):
        random.seed(1)
        for _ in range(100):
            df = pd.DataFrame(
                {"processos_relacionados_1": ",".join([str(random.randint(1, 10000000)) for _ in range(random.randint(1, 10))]),
                 "processos_relacionados_2": ['']}
            )
            rel = ProcessFromSEI.get_formatted_related_processes(df)
            self.assertNotIn(",,", rel, f"Bad str: {rel}")

    def test_get_formatted_related_processes_all_empty(self):
        df = pd.DataFrame(
            {"processos_relacionados_1": [""],
             "processos_relacionados_2": [""]}
        )
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "")

    def test_get_formatted_related_processes_empty_dataframe(self):
        """Testa comportamento com DataFrame vazio"""
        df = pd.DataFrame()
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "")

    def test_get_formatted_related_processes_missing_column(self):
        """Testa comportamento quando coluna processos_relacionados_1 não existe"""
        df = pd.DataFrame({"outra_coluna": ["valor"]})
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "")

    def test_get_formatted_related_processes_none_value(self):
        """Testa comportamento quando o valor é None"""
        df = pd.DataFrame({"processos_relacionados_1": [None]})
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "")

    def test_get_formatted_related_processes_non_string_value(self):
        """Testa comportamento quando o valor não é string"""
        df = pd.DataFrame({"processos_relacionados_1": [123]})
        rel = ProcessFromSEI.get_formatted_related_processes(df)
        self.assertEqual(rel, "")


if __name__ == "__main__":
    unittest.main()

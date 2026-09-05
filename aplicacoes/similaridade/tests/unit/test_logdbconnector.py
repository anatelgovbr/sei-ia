import unittest

from db_connection.db_connection import DBConnector


class TestDBConnector(unittest.TestCase):
    def test_invalid_connection_string(self):
        invalid_conn_string = "postgresql+psycopg2://localhost:1234/db"
        with self.assertRaises((ValueError, Exception)):
            DBConnector(invalid_conn_string, schema="test")


if __name__ == "__main__":
    unittest.main()

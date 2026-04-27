import unittest
from sqlalchemy.exc import SQLAlchemyError

# from api_sei.db_models.db_connect import DBConnector
from db_connection.db_connection import DBConnector

class TestDBConnector(unittest.TestCase):
    def test_invalid_connection_string(self):
        invalid_conn_string = "postgresql+psycopg2://user:pwd@localhost:1234/db"
        with self.assertRaises(SQLAlchemyError):
            DBConnector(invalid_conn_string)


if __name__ == "__main__":
    unittest.main()
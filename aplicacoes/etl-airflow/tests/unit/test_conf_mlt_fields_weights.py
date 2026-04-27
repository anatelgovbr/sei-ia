import unittest
from unittest.mock import patch
from jobs.db_models.async_db_connection import AsyncDbConnector
from jobs.db_models.app_tables import Base_pg

class TestBuildMltFieldsWeights(unittest.TestCase):
    """Test build config mlt fields weights with an in-memory database."""

    @patch('jobs.configs.parameters.conf_mlt_fields_weights.app_db')
    def test_conf_mlt_fields_weights(self, mock_app_db):
        from jobs.configs.parameters.conf_mlt_fields_weights import main
        app_db = AsyncDbConnector(r'sqlite:///:memory:', schema="", base=Base_pg)
        mock_app_db.return_value = app_db

        main()

        session = app_db.get_session()
        res = session.query(app_db.ConfigMltFieldsWeights).first()
        self.assertIsNotNone(res)
        session.close()

if __name__ == "__main__":
    unittest.main()
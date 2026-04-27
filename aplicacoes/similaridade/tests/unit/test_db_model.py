# from datetime import datetime
# import unittest
# import pytest
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker
# from unittest.mock import patch

# from api_sei.db_models.models import LogRecommendationDB, Base


# def db_session():
#     engine = create_engine("sqlite://")
#     with engine.connect() as connection:
#         connection.execute("attach ':memory:' as public")

#     Base.metadata.create_all(engine, tables=[LogRecommendationDB.__table__])
    
#     # Create the "public" schema


#     Session = sessionmaker(bind=engine)
#     return Session()


# class TestLogRecommendationDB(unittest.TestCase):

#     # Fixture to set up a test database session
#     @pytest.fixture(autouse=True)
#     def setup(self):
#         self.session = db_session()


#     def test_timestamp_format_validation(self):
#         log_entry = LogRecommendationDB(id_protocolo_search=1, id_protocolo_interest=2, email_user='valid_email@example.com', created_at='invalid_timestamp_format')
#         with self.assertRaises(Exception):
#             self.session.add(log_entry)
#             self.session.commit()

#     # Test case for successful insertion
#     def test_successful_insertion(self):
#         log_entry = LogRecommendationDB(id_protocolo_search=1, id_protocolo_interest=2, email_user='valid_email@example.com', created_at=datetime(2023, 1, 1))
#         self.session.add(log_entry)
#         self.session.commit()
#         retrieved_entry = self.session.query(LogRecommendationDB).filter_by(id=1).first()
#         self.assertIsNotNone(retrieved_entry)
#         self.assertEqual(retrieved_entry.email_user, 'valid_email@example.com')
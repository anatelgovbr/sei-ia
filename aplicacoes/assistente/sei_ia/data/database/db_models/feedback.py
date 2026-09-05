"""Modelo de tabelas de feedbacks."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, Column, Integer, Text

from sei_ia.data.database.db_instances import BasePgvector


class Feedback(BasePgvector):
    """Modelo de dados para feedback de mensagens.

    Attributes:
    - id (int): Identificador único do feedback.
    - id_mensagem (int): ID da mensagem associada ao feedback.
    - stars (int): Número de estrelas atribuído ao feedback.
    - comment (str): Comentário associado ao feedback.
    - created_on (TIMESTAMP): Data e hora de criação do feedback (padrão é a data e hora atual).
    """

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    id_mensagem = Column(Integer)
    stars = Column(Integer)
    comment = Column(Text)
    created_on = Column(TIMESTAMP, default=datetime.now)

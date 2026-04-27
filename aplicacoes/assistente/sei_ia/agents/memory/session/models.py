"""Modelo de tabelas de memoria."""

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class InteracaoChat(Base):
    """Classe de representação do modelo de tabela 'md_ia_interacao_chat'.

    Esta classe define o modelo de tabela 'md_ia_interacao_chat' no banco de dados.
    Ela possui os seguintes atributos:
    - id_md_ia_interacao_chat (int): Identificador único da interação de chat.
    - id_md_ia_topico_chat (int): Identificador do tópico de chat.
    - id_message (int): Identificador da mensagem.
    - dth_cadastro (DateTime): Data e hora de criação da interação.
    - input_prompt (Text): Entrada da interação.
    - pergunta (Text): Pergunta feita na interação.
    - resposta (Text): Resposta da interação.
    - procedimento_citado (String): Procedimento citado na interação.
    - link_acesso_procedimento (String): Link para acesso ao procedimento.
    - feedback (int): Feedback fornecido na interação.
    - status_requisicao (int): Status da requisição na interação.
    - tempo_execucao (int): Tempo de execução da interação.
    - total_tokens (int): Total de tokens utilizados na interação.
    """

    __tablename__ = "md_ia_interacao_chat"

    id_md_ia_interacao_chat = Column(Integer, primary_key=True)
    id_md_ia_topico_chat = Column(Integer)
    id_message = Column(Integer)
    dth_cadastro = Column(DateTime)
    input_prompt = Column(Text)
    pergunta = Column(Text)
    resposta = Column(Text)
    feedback = Column(Integer)
    status_requisicao = Column(Integer)
    tempo_execucao = Column(Integer)
    total_tokens = Column(Integer)


class TopicoChat(Base):
    """Classe de representação do modelo de tabela 'md_ia_topico_chat'.

    Esta classe define o modelo de tabela 'md_ia_topico_chat' no banco de dados.
    Ela possui os seguintes atributos:
    - id (int): Identificador único do tópico de chat.
    - dth_cadastro (DateTime): Data e hora de criação do tópico.
    - id_md_ia_topico_chat (int): Identificador do tópico de chat.
    - id_unidade (int): Identificador da unidade.
    - id_usuario (int): Identificador do usuário.
    - nome (str): Nome do tópico de chat.
    - sin_ativo (str): Indica se o tópico está ativo ou não.
    """

    __tablename__ = "md_ia_topico_chat"

    id = Column(Integer, primary_key=True)
    dth_cadastro = Column(DateTime)
    id_md_ia_topico_chat = Column(Integer)
    id_unidade = Column(Integer)
    id_usuario = Column(Integer)
    nome = Column(String)
    sin_ativo = Column(String)

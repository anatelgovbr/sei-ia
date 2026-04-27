"""Schemas para as tabelas da aplicação."""

from datetime import datetime

from pydantic import BaseModel


class MdIaInteracaoChatSchema(BaseModel):
    """Modelo de dados para representar uma interação de chat com a IA.

    Atributos:
    - id_md_ia_interacao_chat (int): Identificador único da interação.
    - id_md_ia_topico_chat (int | None): Identificador do tópico de chat. Defaults to None.
    - id_message (int | None): Identificador da mensagem. Defaults to None.
    - pergunta (str | None): Texto da pergunta. Defaults to None.
    - resposta (str | None): Texto da resposta. Defaults to None.
    - dth_cadastro (datetime | None): Data e hora de criação da interação. Defaults to None.
    """

    id_md_ia_interacao_chat: int
    id_md_ia_topico_chat: int | None = None
    id_message: int | None = None
    pergunta: str | None = None
    pergunta_data: str | None = None
    resposta: str | None = None
    dth_cadastro: datetime | None = None


class MemoryModel(BaseModel):
    """Modelo de dados para representar um lembrete de memória.

    Atributos:
    - id (int): Identificador único do lembrete.
    - prompt (str): Prompt do lembrete.
    - resposta (str): Resposta do lembrete.
    - created_at (datetime | None): Data e hora de criação do lembrete.
    """

    id: int
    prompt: str
    resposta: str
    created_at: datetime | None = None


class SessionModel(BaseModel):
    """Modelo de dados para representar uma sessão de chat.

    Atributos:
    - id (int): Identificador único da sessão.
    - session_id (str): ID da sessão.
    - user_id (int): ID do usuário associado à sessão.
    - memory (list[MemoryModel]): Lista de mensagens da sessão.
    - created_at (datetime | None): Data e hora de criação da sessão.
    """

    id: int
    session_id: str
    user_id: int
    memory: list[MemoryModel]
    created_at: datetime | None = None


class MdIaTopicoChatSchema(BaseModel):
    """Represents a row in the md_ia_topico_chat table.

    Attributes:
    - id_md_ia_topico_chat (int): The ID of the topic chat.
    - id_usuario (int): The ID of the user associated with the topic chat.
    - id_unidade (int | None): The ID of the unit associated with the topic chat. Defaults to None.
    - nome (str | None): The name of the topic chat. Defaults to None.
    - sin_ativo (str | None): The status of the topic chat. Defaults to None.
    - dth_cadastro (datetime | None): The date and time of creation of the topic chat. Defaults to None.
    """

    id_md_ia_topico_chat: int
    id_usuario: int
    id_unidade: int | None = None
    nome: str | None = None
    sin_ativo: str | None = None
    dth_cadastro: datetime | None = None

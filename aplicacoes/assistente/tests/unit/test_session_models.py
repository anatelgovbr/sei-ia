"""Testes unitários para os modelos SQLAlchemy de sessão.

Módulo testado: sei_ia/agents/memory/session/models.py
"""

from datetime import datetime

from sei_ia.agents.memory.session.models import Base, InteracaoChat, TopicoChat


class TestInteracaoChat:
    """Testes para o modelo InteracaoChat."""

    def test_tablename(self):
        assert InteracaoChat.__tablename__ == "md_ia_interacao_chat"

    def test_instanciacao_minima(self):
        obj = InteracaoChat()
        assert obj is not None

    def test_campos_none_por_padrao(self):
        obj = InteracaoChat()
        assert obj.pergunta is None
        assert obj.resposta is None
        assert obj.feedback is None

    def test_atribuicao_de_campos(self):
        obj = InteracaoChat()
        obj.pergunta = "Qual o prazo?"
        obj.resposta = "30 dias."
        obj.total_tokens = 150
        assert obj.pergunta == "Qual o prazo?"
        assert obj.resposta == "30 dias."
        assert obj.total_tokens == 150

    def test_coluna_primary_key(self):
        col = InteracaoChat.__table__.c["id_md_ia_interacao_chat"]
        assert col.primary_key

    def test_colunas_existem(self):
        cols = {c.name for c in InteracaoChat.__table__.c}
        esperadas = {
            "id_md_ia_interacao_chat",
            "id_md_ia_topico_chat",
            "id_message",
            "dth_cadastro",
            "pergunta",
            "resposta",
            "feedback",
            "status_requisicao",
            "tempo_execucao",
            "total_tokens",
        }
        assert esperadas.issubset(cols)

    def test_atribuicao_datetime(self):
        obj = InteracaoChat()
        dt = datetime(2024, 6, 1, 12, 0)
        obj.dth_cadastro = dt
        assert obj.dth_cadastro == dt


class TestTopicoChat:
    """Testes para o modelo TopicoChat."""

    def test_tablename(self):
        assert TopicoChat.__tablename__ == "md_ia_topico_chat"

    def test_instanciacao_minima(self):
        obj = TopicoChat()
        assert obj is not None

    def test_campos_none_por_padrao(self):
        obj = TopicoChat()
        assert obj.nome is None
        assert obj.sin_ativo is None
        assert obj.id_unidade is None

    def test_atribuicao_de_campos(self):
        obj = TopicoChat()
        obj.id_usuario = 42
        obj.nome = "Tópico de teste"
        obj.sin_ativo = "S"
        assert obj.id_usuario == 42
        assert obj.nome == "Tópico de teste"
        assert obj.sin_ativo == "S"

    def test_coluna_primary_key(self):
        col = TopicoChat.__table__.c["id"]
        assert col.primary_key

    def test_colunas_existem(self):
        cols = {c.name for c in TopicoChat.__table__.c}
        esperadas = {
            "id",
            "dth_cadastro",
            "id_md_ia_topico_chat",
            "id_unidade",
            "id_usuario",
            "nome",
            "sin_ativo",
        }
        assert esperadas.issubset(cols)


class TestBase:
    """Testes para a Base declarativa."""

    def test_base_contem_tabelas(self):
        tabelas = set(Base.metadata.tables.keys())
        assert "md_ia_interacao_chat" in tabelas
        assert "md_ia_topico_chat" in tabelas

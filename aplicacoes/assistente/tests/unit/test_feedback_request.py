"""Testes unitários para FeedbackRequest e Source de pydantic_models.

Módulo testado: sei_ia/data/pydantic_models.py
"""

import pytest
from pydantic import ValidationError

from sei_ia.data.pydantic_models import FeedbackRequest, Source


class TestFeedbackRequestValidacao:
    """Testes para o validator de stars em FeedbackRequest."""

    def test_stars_valido_minimo(self):
        req = FeedbackRequest(id_mensagem=1, stars=1)
        assert req.stars == 1

    def test_stars_valido_maximo(self):
        req = FeedbackRequest(id_mensagem=1, stars=5)
        assert req.stars == 5

    def test_stars_valido_meio(self):
        req = FeedbackRequest(id_mensagem=1, stars=3)
        assert req.stars == 3

    def test_stars_abaixo_do_minimo_levanta_erro(self):
        with pytest.raises(ValidationError):
            FeedbackRequest(id_mensagem=1, stars=0)

    def test_stars_acima_do_maximo_levanta_erro(self):
        with pytest.raises(ValidationError):
            FeedbackRequest(id_mensagem=1, stars=6)

    def test_stars_negativo_levanta_erro(self):
        with pytest.raises(ValidationError):
            FeedbackRequest(id_mensagem=1, stars=-1)

    def test_comment_opcional(self):
        req = FeedbackRequest(id_mensagem=1, stars=4)
        assert req.comment is None

    def test_comment_preenchido(self):
        req = FeedbackRequest(id_mensagem=1, stars=4, comment="Ótimo")
        assert req.comment == "Ótimo"

    def test_id_mensagem_preservado(self):
        req = FeedbackRequest(id_mensagem=42, stars=3)
        assert req.id_mensagem == 42


class TestSourceModel:
    """Testes para o modelo Source."""

    def test_criacao_basica(self):
        s = Source(index=1, id_documento_formatado="12345", conteudo_documento="texto")
        assert s.index == 1

    def test_str_contem_id_formatado(self):
        s = Source(index=1, id_documento_formatado="99999", conteudo_documento="trecho")
        assert "99999" in str(s)

    def test_str_contem_conteudo(self):
        s = Source(
            index=1, id_documento_formatado="123", conteudo_documento="texto do doc"
        )
        assert "texto do doc" in str(s)

    def test_str_retorna_string(self):
        s = Source(index=2, id_documento_formatado="555", conteudo_documento="x")
        assert isinstance(str(s), str)

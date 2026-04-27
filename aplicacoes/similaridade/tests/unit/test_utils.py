import pytest
import pandas as pd
from api_sei.utils import response_normalization, add_param_on_url_if_not_exists

class TestResponseNormalization:

    def test_normalizacao_com_recomendacoes(self):
        """Teste a normalização com recomendações."""
        recomendacoes = {
            'recommendation': [
                {'id': 1, 'score': 80},
                {'id': 2, 'score': 60},
            ]
        }
        max_score = 100
        resultado = response_normalization(recomendacoes, max_score)
        assert resultado == {
            'recommendation': [
                {'id': 1, 'score': 0.8},
                {'id': 2, 'score': 0.6},
            ]
        }

    def test_normalizacao_sem_recomendacoes(self):
        """Teste a normalização sem recomendações."""
        recomendacoes = {'recommendation': []}
        max_score = 100
        resultado = response_normalization(recomendacoes, max_score)
        assert resultado == recomendacoes

    def test_normalizacao_com_score_maior_que_max_score(self):
        """Teste a normalização com score maior que max_score."""
        recomendacoes = {
            'recommendation': [
                {'id': 1, 'score': 120},
            ]
        }
        max_score = 100
        resultado = response_normalization(recomendacoes, max_score)
        assert resultado == {
            'recommendation': [
                {'id': 1, 'score': 1.0},
            ]
        }

class TestAddParamOnUrlIfNotExists:

    @pytest.mark.parametrize(
        "url, param_name, param_value, expected_url",
        [
            ("https://exemplo.com", "utm_source", "newsletter", "https://exemplo.com?utm_source=newsletter"),
            ("https://exemplo.com?utm_medium=email", "utm_source", "newsletter", "https://exemplo.com?utm_medium=email&utm_source=newsletter"),
            ("https://exemplo.com?utm_source=blog", "utm_source", "newsletter", "https://exemplo.com?utm_source=newsletter"),
        ]
    )
    def test_add_param_on_url_if_not_exists(self, url, param_name, param_value, expected_url):
        """Teste a adição de parâmetros na URL."""
        result = add_param_on_url_if_not_exists(url, param_name, param_value)
        assert result == expected_url

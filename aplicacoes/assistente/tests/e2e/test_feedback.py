"""
Testes E2E do endpoint POST /feedback/feedback.

Complementa os testes básicos de test_p1_critical.py com:
1. Verificação de que os parâmetros chegam corretamente ao persist_feedback
2. Tipos e valores de fronteira (stars float, id_mensagem negativo, comment vazio)
3. Resposta retorna exatamente um inteiro (não dict, não string)
4. Formato do corpo de erro do banco de dados
"""

from unittest.mock import AsyncMock, patch

from sqlalchemy.exc import OperationalError, SQLAlchemyError

ENDPOINT = "/feedback/feedback"


# ---------------------------------------------------------------------------
# 1. Verificação de argumentos passados ao persist_feedback
# ---------------------------------------------------------------------------


def test_feedback_argumentos_passados_corretamente(client):
    """
    Verifica que os campos id_mensagem, stars e comment da requisição são
    repassados exatamente para persist_feedback sem transformação.
    """
    payload = {"id_mensagem": 123, "stars": 3, "comment": "Resposta razoável"}

    mock_persist = AsyncMock(return_value=55)

    with patch("sei_ia.routers.feedback.persist_feedback", new=mock_persist):
        response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 200
    mock_persist.assert_called_once_with(
        id_mensagem=123, stars=3, comment="Resposta razoável"
    )


def test_feedback_comment_none_passado_como_none(client):
    """
    Quando comment não é enviado, persist_feedback deve receber comment=None
    (não string vazia, não ausente).
    """
    payload = {"id_mensagem": 10, "stars": 5}

    mock_persist = AsyncMock(return_value=1)

    with patch("sei_ia.routers.feedback.persist_feedback", new=mock_persist):
        response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 200
    mock_persist.assert_called_once_with(id_mensagem=10, stars=5, comment=None)


def test_feedback_comment_explicito_null_passado_como_none(client):
    """
    Quando comment é enviado explicitamente como null/None, persist_feedback
    deve receber comment=None.
    """
    payload = {"id_mensagem": 10, "stars": 5, "comment": None}

    mock_persist = AsyncMock(return_value=2)

    with patch("sei_ia.routers.feedback.persist_feedback", new=mock_persist):
        response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 200
    mock_persist.assert_called_once_with(id_mensagem=10, stars=5, comment=None)


# ---------------------------------------------------------------------------
# 2. Formato da resposta de sucesso
# ---------------------------------------------------------------------------


def test_feedback_resposta_e_inteiro(client):
    """
    A resposta do endpoint deve ser exatamente o inteiro retornado por
    persist_feedback — não um dict, não uma string.
    """
    mock_persist = AsyncMock(return_value=42)

    with patch("sei_ia.routers.feedback.persist_feedback", new=mock_persist):
        response = client.post(ENDPOINT, json={"id_mensagem": 1, "stars": 3})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, int), f"Esperado int, recebido {type(body)}: {body}"
    assert body == 42


def test_feedback_id_retornado_reflete_valor_do_banco(client):
    """
    O ID retornado na resposta deve refletir exatamente o que o banco gerou,
    independente dos campos da requisição.
    """
    for expected_id in [1, 100, 99999]:
        mock_persist = AsyncMock(return_value=expected_id)
        with patch("sei_ia.routers.feedback.persist_feedback", new=mock_persist):
            response = client.post(ENDPOINT, json={"id_mensagem": 1, "stars": 3})

        assert response.status_code == 200
        assert response.json() == expected_id


# ---------------------------------------------------------------------------
# 3. Tipos e valores de fronteira
# ---------------------------------------------------------------------------


def test_feedback_stars_float_retorna_422(client):
    """
    stars como float não inteiro (ex: 3.5) deve retornar 422.
    Pydantic v2 rejeita float não inteiro para campo int.
    """
    response = client.post(ENDPOINT, json={"id_mensagem": 1, "stars": 3.5})

    assert response.status_code == 422


def test_feedback_stars_float_inteiro_aceito(client):
    """
    stars=3.0 (float que representa inteiro) deve ser aceito pelo Pydantic
    e resultar em 200 (coerção para int).
    """
    mock_persist = AsyncMock(return_value=1)

    with patch("sei_ia.routers.feedback.persist_feedback", new=mock_persist):
        response = client.post(ENDPOINT, json={"id_mensagem": 1, "stars": 3.0})

    # Pydantic v2 coerce int-compatible floats
    assert response.status_code == 200


def test_feedback_id_mensagem_negativo_aceito(client):
    """
    id_mensagem negativo não tem validação na model e deve ser aceito.
    O banco pode rejeitar, mas a validação do endpoint não deve bloquear.
    """
    mock_persist = AsyncMock(return_value=10)

    with patch("sei_ia.routers.feedback.persist_feedback", new=mock_persist):
        response = client.post(ENDPOINT, json={"id_mensagem": -1, "stars": 3})

    assert response.status_code == 200
    mock_persist.assert_called_once_with(id_mensagem=-1, stars=3, comment=None)


def test_feedback_id_mensagem_zero_aceito(client):
    """id_mensagem=0 não tem validação e deve ser aceito pelo endpoint."""
    mock_persist = AsyncMock(return_value=5)

    with patch("sei_ia.routers.feedback.persist_feedback", new=mock_persist):
        response = client.post(ENDPOINT, json={"id_mensagem": 0, "stars": 2})

    assert response.status_code == 200


def test_feedback_comment_vazio_aceito(client):
    """comment como string vazia é válido (campo é str | None, sem min_length)."""
    mock_persist = AsyncMock(return_value=3)

    with patch("sei_ia.routers.feedback.persist_feedback", new=mock_persist):
        response = client.post(
            ENDPOINT, json={"id_mensagem": 1, "stars": 2, "comment": ""}
        )

    assert response.status_code == 200
    mock_persist.assert_called_once_with(id_mensagem=1, stars=2, comment="")


def test_feedback_comment_longo_aceito(client):
    """comment longo (1000 chars) deve ser aceito sem truncamento."""
    long_comment = "A" * 1000
    mock_persist = AsyncMock(return_value=8)

    with patch("sei_ia.routers.feedback.persist_feedback", new=mock_persist):
        response = client.post(
            ENDPOINT, json={"id_mensagem": 1, "stars": 4, "comment": long_comment}
        )

    assert response.status_code == 200
    mock_persist.assert_called_once_with(id_mensagem=1, stars=4, comment=long_comment)


def test_feedback_id_mensagem_string_retorna_422(client):
    """id_mensagem como string não numérica deve retornar 422."""
    response = client.post(ENDPOINT, json={"id_mensagem": "abc", "stars": 3})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. Formato do corpo de erro
# ---------------------------------------------------------------------------


def test_feedback_erro_banco_corpo_tem_detail(client):
    """
    Em caso de SQLAlchemyError, o corpo da resposta 503 deve conter
    o campo 'detail' com mensagem descritiva do erro.
    """
    with patch(
        "sei_ia.routers.feedback.persist_feedback",
        new=AsyncMock(side_effect=SQLAlchemyError("timeout de conexão")),
    ):
        response = client.post(ENDPOINT, json={"id_mensagem": 1, "stars": 3})

    assert response.status_code == 503
    body = response.json()
    assert "detail" in body
    assert "timeout de conexão" in body["detail"]


def test_feedback_erro_operacional_banco_retorna_503(client):
    """
    OperationalError (subclasse de SQLAlchemyError) também deve retornar 503.
    """
    with patch(
        "sei_ia.routers.feedback.persist_feedback",
        new=AsyncMock(
            side_effect=OperationalError("stmt", {}, Exception("host unreachable"))
        ),
    ):
        response = client.post(ENDPOINT, json={"id_mensagem": 1, "stars": 5})

    assert response.status_code == 503

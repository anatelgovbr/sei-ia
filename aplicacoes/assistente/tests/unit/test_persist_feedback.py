"""
Testes unitários para sei_ia/services/persistance/feedback.py.

Cobre persist_feedback: criação do objeto Feedback e chamada a add_native_async.
O modelo Feedback (SQLAlchemy) é mockado para evitar dependência de banco.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_persist_feedback_chama_add_native_async():
    """
    persist_feedback deve criar um Feedback e chamar app_db_instance.add_native_async
    com returns_obj=True, retornando o .id do objeto persistido.
    """
    mock_result = MagicMock()
    mock_result.id = 42

    with (
        patch("sei_ia.services.persistance.feedback.app_db_instance") as mock_db,
        patch("sei_ia.services.persistance.feedback.Feedback") as mock_feedback_cls,
    ):
        mock_db.add_native_async = AsyncMock(return_value=mock_result)
        mock_feedback_cls.return_value = MagicMock()

        from sei_ia.services.persistance.feedback import persist_feedback

        result = await persist_feedback(id_mensagem=10, stars=4, comment="Ótimo!")

    assert result == 42
    mock_db.add_native_async.assert_called_once()
    call_kwargs = mock_db.add_native_async.call_args
    assert call_kwargs.kwargs.get("returns_obj") is True


@pytest.mark.asyncio
async def test_persist_feedback_sem_comment():
    """persist_feedback com comment=None deve funcionar normalmente."""
    mock_result = MagicMock()
    mock_result.id = 7

    with (
        patch("sei_ia.services.persistance.feedback.app_db_instance") as mock_db,
        patch("sei_ia.services.persistance.feedback.Feedback") as mock_feedback_cls,
    ):
        mock_db.add_native_async = AsyncMock(return_value=mock_result)
        mock_feedback_cls.return_value = MagicMock()

        from sei_ia.services.persistance.feedback import persist_feedback

        result = await persist_feedback(id_mensagem=5, stars=5, comment=None)

    assert result == 7


@pytest.mark.asyncio
async def test_persist_feedback_cria_feedback_com_argumentos_corretos():
    """Feedback deve ser instanciado com exatamente os argumentos recebidos."""
    mock_result = MagicMock()
    mock_result.id = 1

    with (
        patch("sei_ia.services.persistance.feedback.app_db_instance") as mock_db,
        patch("sei_ia.services.persistance.feedback.Feedback") as mock_feedback_cls,
    ):
        mock_db.add_native_async = AsyncMock(return_value=mock_result)
        mock_instance = MagicMock()
        mock_feedback_cls.return_value = mock_instance

        from sei_ia.services.persistance.feedback import persist_feedback

        await persist_feedback(id_mensagem=99, stars=3, comment="Comentário teste")

    mock_feedback_cls.assert_called_once_with(
        id_mensagem=99, stars=3, comment="Comentário teste"
    )


@pytest.mark.asyncio
async def test_persist_feedback_retorna_id_do_banco():
    """O ID retornado deve ser exatamente o .id do objeto persistido pelo banco."""
    for expected_id in [1, 100, 99999]:
        mock_result = MagicMock()
        mock_result.id = expected_id

        with (
            patch("sei_ia.services.persistance.feedback.app_db_instance") as mock_db,
            patch("sei_ia.services.persistance.feedback.Feedback"),
        ):
            mock_db.add_native_async = AsyncMock(return_value=mock_result)

            from sei_ia.services.persistance.feedback import persist_feedback

            result = await persist_feedback(id_mensagem=1, stars=3, comment=None)

        assert result == expected_id, f"Esperado {expected_id}, recebido {result}"

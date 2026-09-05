"""Testes da integração do router de chat com `persist_topic_attachments`.

Cobre o caminho `_apply_arquivos_avulsos_to_state` do router:
- Persistência é chamada quando há `id_topico` e anexos textuais.
- Falha do Redis não derruba a resposta (fail-open).
- Sem `id_topico` no `user_state`, persistência NÃO é chamada.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sei_ia.data.etl.extract.uploads import (
    ArquivoAvulsoProcessingError,
    ProcessedAttachment,
    UploadOutcome,
)


def _outcome_com_anexos(attachments: list[ProcessedAttachment]) -> UploadOutcome:
    return UploadOutcome(
        text_block="<arquivos_avulsos>...</arquivos_avulsos>",
        image_attachments=[],
        attachments=attachments,
        temp_files=set(),
    )


@pytest.mark.asyncio
async def test_persiste_anexos_quando_ha_topico():
    from sei_ia.routers.chat import _apply_arquivos_avulsos_to_state

    request = MagicMock()
    request.arquivos_avulsos = [
        MagicMock(
            id_arquivo_avulso=1,
            extensao_arquivo_avulso="pdf",
            nome_arquivo_avulso="doc.pdf",
        )
    ]

    user_state: dict = {
        "user_request": "",
        "all_tokens_counter": 0,
        "system_prompt": "",
        "id_topico": 19671,
    }

    outcome = _outcome_com_anexos(
        [
            ProcessedAttachment(
                id_arquivo_avulso=1,
                nome_arquivo="doc.pdf",
                extensao="pdf",
                tipo="text",
                conteudo="conteúdo extraído",
            )
        ]
    )

    with (
        patch(
            "sei_ia.routers.chat.process_arquivos_avulsos",
            new_callable=AsyncMock,
            return_value=outcome,
        ),
        patch(
            "sei_ia.routers.chat.persist_topic_attachments",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_persist,
        patch(
            "sei_ia.routers.chat._remove_arquivos_avulsos_no_sei",
            new_callable=AsyncMock,
        ),
    ):
        await _apply_arquivos_avulsos_to_state(request, user_state)

    mock_persist.assert_awaited_once()
    kwargs = mock_persist.await_args.kwargs
    assert kwargs["id_topico"] == 19671
    assert len(kwargs["attachments"]) == 1
    assert kwargs["attachments"][0].id_arquivo_avulso == 1


@pytest.mark.asyncio
async def test_nao_persiste_sem_id_topico():
    from sei_ia.routers.chat import _apply_arquivos_avulsos_to_state

    request = MagicMock()
    request.arquivos_avulsos = [
        MagicMock(
            id_arquivo_avulso=1,
            extensao_arquivo_avulso="pdf",
            nome_arquivo_avulso="doc.pdf",
        )
    ]

    user_state: dict = {
        "user_request": "",
        "all_tokens_counter": 0,
        "system_prompt": "",
        "id_topico": None,
    }

    outcome = _outcome_com_anexos(
        [
            ProcessedAttachment(
                id_arquivo_avulso=1,
                nome_arquivo="doc.pdf",
                extensao="pdf",
                tipo="text",
                conteudo="x",
            )
        ]
    )

    with (
        patch(
            "sei_ia.routers.chat.process_arquivos_avulsos",
            new_callable=AsyncMock,
            return_value=outcome,
        ),
        patch(
            "sei_ia.routers.chat.persist_topic_attachments",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_persist,
        patch(
            "sei_ia.routers.chat._remove_arquivos_avulsos_no_sei",
            new_callable=AsyncMock,
        ),
    ):
        await _apply_arquivos_avulsos_to_state(request, user_state)

    mock_persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_falha_no_redis_nao_derruba_request():
    from sei_ia.routers.chat import _apply_arquivos_avulsos_to_state

    request = MagicMock()
    request.arquivos_avulsos = [
        MagicMock(
            id_arquivo_avulso=1,
            extensao_arquivo_avulso="pdf",
            nome_arquivo_avulso="doc.pdf",
        )
    ]
    user_state: dict = {
        "user_request": "",
        "all_tokens_counter": 0,
        "system_prompt": "",
        "id_topico": 42,
    }
    outcome = _outcome_com_anexos(
        [
            ProcessedAttachment(
                id_arquivo_avulso=1,
                nome_arquivo="doc.pdf",
                extensao="pdf",
                tipo="text",
                conteudo="x",
            )
        ]
    )

    with (
        patch(
            "sei_ia.routers.chat.process_arquivos_avulsos",
            new_callable=AsyncMock,
            return_value=outcome,
        ),
        patch(
            "sei_ia.routers.chat.persist_topic_attachments",
            new_callable=AsyncMock,
            side_effect=RuntimeError("redis down"),
        ),
        patch(
            "sei_ia.routers.chat._remove_arquivos_avulsos_no_sei",
            new_callable=AsyncMock,
        ) as mock_remove,
    ):
        # Não deve propagar a exceção do Redis.
        result = await _apply_arquivos_avulsos_to_state(request, user_state)

    assert result == set()
    # Remoção do SEI ainda deve ocorrer após falha do Redis.
    mock_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_falha_em_um_upload_nao_sinaliza_remocao_de_nenhum_upload():
    """A remoção só começa depois que o lote inteiro foi processado."""
    from fastapi import HTTPException

    from sei_ia.routers.chat import _apply_arquivos_avulsos_to_state

    request = MagicMock()
    request.arquivos_avulsos = [
        MagicMock(
            id_arquivo_avulso=1,
            extensao_arquivo_avulso="pdf",
            nome_arquivo_avulso="primeiro.pdf",
        ),
        MagicMock(
            id_arquivo_avulso=2,
            extensao_arquivo_avulso="png",
            nome_arquivo_avulso="segundo.png",
        ),
    ]
    user_state: dict = {
        "user_request": "",
        "all_tokens_counter": 0,
        "system_prompt": "",
        "id_topico": 42,
    }

    with (
        patch(
            "sei_ia.routers.chat.process_arquivos_avulsos",
            new_callable=AsyncMock,
            side_effect=ArquivoAvulsoProcessingError(
                "segundo.png", "png", "falha simulada"
            ),
        ),
        patch(
            "sei_ia.routers.chat._remove_arquivos_avulsos_no_sei",
            new_callable=AsyncMock,
        ) as mock_remove,
        pytest.raises(HTTPException) as exc_info,
    ):
        await _apply_arquivos_avulsos_to_state(request, user_state)

    assert exc_info.value.status_code == 422
    mock_remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_falha_na_remocao_e_best_effort_e_respeita_ids_elegiveis():
    from sei_ia.routers.chat import _remove_arquivos_avulsos_no_sei

    uploads = [
        MagicMock(id_arquivo_avulso=1),
        MagicMock(id_arquivo_avulso=2),
    ]
    loop = MagicMock()
    loop.run_in_executor = AsyncMock(side_effect=RuntimeError("SEI indisponível"))

    with patch("sei_ia.routers.chat.asyncio.get_running_loop", return_value=loop):
        await _remove_arquivos_avulsos_no_sei(uploads, eligible_ids={1})

    loop.run_in_executor.assert_awaited_once()
    assert loop.run_in_executor.await_args.args[2] == [1]

"""Testes unitários para sei_ia/routers/chat/stream.py."""

from datetime import datetime

import pytest
from fastapi import Request


def test_json_serializer_converte_datetime_para_isoformat():
    from sei_ia.routers.chat.stream import json_serializer

    valor = datetime(2026, 5, 18, 12, 34, 56)

    assert json_serializer(valor) == "2026-05-18T12:34:56"


def test_json_serializer_rejeita_tipo_nao_suportado():
    from sei_ia.routers.chat.stream import json_serializer

    with pytest.raises(TypeError, match="not JSON serializable"):
        json_serializer(object())


def test_endpoint_stream_registrado_com_nome_esperado():
    from sei_ia.routers.chat.stream import ENDPOINT_NAME, router

    rotas = [getattr(route, "path", None) for route in router.routes]

    assert ENDPOINT_NAME == "/llm_lang/stream"
    assert ENDPOINT_NAME in rotas


def test_trace_header_do_harness_tem_precedencia(monkeypatch):
    from sei_ia.routers.chat import stream

    monkeypatch.setattr(stream, "_new_trace_id", lambda: "generated")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/llm_lang/stream",
            "headers": [(b"x-langfuse-trace-id", b"linked-trace")],
        }
    )

    assert stream._trace_id_for_request(request) == "linked-trace"

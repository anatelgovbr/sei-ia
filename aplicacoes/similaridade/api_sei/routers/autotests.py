"""Rota para testes de autoteste da API."""

import logging

from fastapi import APIRouter, Request

from api_sei.services.autoteste import TestesAutoteste

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/teste")
async def autotests(request: Request) -> list:
    """Endpoint para testes de autoteste da API.

    Retorna um dicionário com URLs como chave e status_code como valor.
    """
    autoteste_inst = TestesAutoteste(app=request.app)
    return autoteste_inst.autoteste()

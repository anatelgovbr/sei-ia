"""
Testes de concorrência — isolamento de estado entre requisições paralelas.

Verifica que:
1. N requisições simultâneas ao /feedback/feedback cada uma recebe
   de volta seu próprio dado (sem mistura de respostas).
2. N requisições simultâneas ao /health retornam 200 corretamente.
3. N requisições simultâneas ao endpoint de chat produzem respostas
   independentes — o conteúdo de uma não aparece na resposta de outra.
4. Falhas em uma requisição não afetam as demais.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, wait
from unittest.mock import patch

FEEDBACK_ENDPOINT = "/feedback/feedback"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coletar_paralelo(fn, args_list, max_workers=None):
    """
    Executa fn(arg) para cada arg em args_list em paralelo.
    Retorna lista de resultados na ordem de chegada (não necessariamente a de envio).
    """
    resultados = {}
    lock = threading.Lock()
    workers = max_workers or len(args_list)

    def tarefa(idx, arg):
        resultado = fn(arg)
        with lock:
            resultados[idx] = resultado

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(tarefa, i, arg) for i, arg in enumerate(args_list)]
        wait(futures)

    return [resultados[i] for i in range(len(args_list))]


# ---------------------------------------------------------------------------
# 1. Feedback — N requisições paralelas, cada uma recebe seu próprio ID
# ---------------------------------------------------------------------------


def test_feedback_concorrente_sem_mistura_de_ids(client):
    """
    5 requisições simultâneas de feedback: cada uma deve receber de volta
    exatamente o seu próprio id_mensagem — sem mistura entre threads.
    """
    N = 5

    async def persist_echo(id_mensagem, stars, comment):  # noqa: ARG001
        """Devolve o id_mensagem recebido como confirmação."""
        return id_mensagem

    def enviar(id_mensagem):
        return client.post(
            FEEDBACK_ENDPOINT,
            json={"id_mensagem": id_mensagem, "stars": 3},
        )

    with patch("sei_ia.routers.feedback.persist_feedback", side_effect=persist_echo):
        respostas = _coletar_paralelo(enviar, list(range(1, N + 1)))

    for i, resp in enumerate(respostas):
        id_esperado = i + 1
        assert resp.status_code == 200, (
            f"Request {id_esperado} falhou: {resp.status_code}"
        )
        assert resp.json() == id_esperado, (
            f"Request {id_esperado} recebeu resposta de outra requisição: {resp.json()}"
        )


def test_feedback_concorrente_todas_retornam_200(client):
    """
    10 requisições simultâneas de feedback devem todas retornar 200.
    Verifica que não há race condition que cause falha silenciosa.
    """
    N = 10

    async def persist_ok(id_mensagem, stars, comment):  # noqa: ARG001
        return id_mensagem

    def enviar(i):
        return client.post(
            FEEDBACK_ENDPOINT,
            json={"id_mensagem": i, "stars": 5, "comment": f"Comentário {i}"},
        )

    with patch("sei_ia.routers.feedback.persist_feedback", side_effect=persist_ok):
        respostas = _coletar_paralelo(enviar, list(range(1, N + 1)))

    statuses = [r.status_code for r in respostas]
    assert all(s == 200 for s in statuses), f"Nem todas retornaram 200: {statuses}"


def test_feedback_concorrente_falha_em_uma_nao_afeta_outras(client):
    """
    Quando uma das requisições simultâneas falha (422 por dados inválidos),
    as outras devem continuar retornando 200 normalmente.
    """
    N = 5

    async def persist_ok(id_mensagem, stars, comment):  # noqa: ARG001
        return id_mensagem

    payloads = [
        {"id_mensagem": 1, "stars": 3},  # válido
        {"id_mensagem": 2, "stars": 99},  # inválido → 422
        {"id_mensagem": 3, "stars": 2},  # válido
        {"id_mensagem": 4, "stars": 0},  # inválido → 422
        {"id_mensagem": 5, "stars": 5},  # válido
    ]

    def enviar(payload):
        return client.post(FEEDBACK_ENDPOINT, json=payload)

    with patch("sei_ia.routers.feedback.persist_feedback", side_effect=persist_ok):
        respostas = _coletar_paralelo(enviar, payloads)

    # Requisições válidas (índices 0, 2, 4) devem retornar 200
    assert respostas[0].status_code == 200
    assert respostas[2].status_code == 200
    assert respostas[4].status_code == 200

    # Requisições inválidas devem retornar 422
    assert respostas[1].status_code == 422
    assert respostas[3].status_code == 422


# ---------------------------------------------------------------------------
# 2. Health check — endpoint leve para verificar concorrência básica
# ---------------------------------------------------------------------------


def test_health_check_concorrente(client):
    """
    20 requisições simultâneas a GET /health devem todas retornar 200
    com o body correto — sem nenhuma falha ou mistura de respostas.
    """
    N = 20

    def consultar(_):
        return client.get("/health")

    respostas = _coletar_paralelo(consultar, list(range(N)))

    assert len(respostas) == N
    for resp in respostas:
        assert resp.status_code == 200
        assert resp.json() == {"status": "OK"}


# ---------------------------------------------------------------------------
# 3. Chat — isolamento de UserState entre requisições paralelas
# ---------------------------------------------------------------------------

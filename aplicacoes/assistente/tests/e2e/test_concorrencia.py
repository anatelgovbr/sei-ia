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
from unittest.mock import MagicMock, patch

FEEDBACK_ENDPOINT = "/feedback/feedback"
CHAT_ENDPOINT = "/llm_lang/chat_gpt_4o_mini_128k"
CHAT_HEADERS = {"Content-Type": "application/json", "X-Internal-Test-Call": "true"}


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


def _make_fake_ainvoke(resposta_fn):
    """
    Cria um AsyncMock para graph.ainvoke que:
    - Preserva o user_state recebido como entrada.
    - Adiciona o campo 'response' usando resposta_fn(user_state).
    """

    async def fake_ainvoke(user_state, config=None):
        final_state = dict(user_state)
        final_state["response"] = {
            "response": resposta_fn(user_state),
            "n_tokens": [10, 5],
            "finish_reason": "stop",
            "type_choiced_summary": "Not found",
            "reasoning": None,
        }
        return final_state

    mock_graph = MagicMock()
    mock_graph.ainvoke = fake_ainvoke
    return mock_graph


# ---------------------------------------------------------------------------
# 1. Feedback — N requisições paralelas, cada uma recebe seu próprio ID
# ---------------------------------------------------------------------------


def test_feedback_concorrente_sem_mistura_de_ids(client):
    """
    5 requisições simultâneas de feedback: cada uma deve receber de volta
    exatamente o seu próprio id_mensagem — sem mistura entre threads.
    """
    N = 5

    async def persist_echo(id_mensagem, stars, comment):
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

    async def persist_ok(id_mensagem, stars, comment):
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

    async def persist_ok(id_mensagem, stars, comment):
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


def test_chat_concorrente_respostas_independentes(client):
    """
    5 requisições simultâneas ao endpoint de chat, cada uma com id_usuario
    diferente. A resposta de cada requisição deve conter o texto referente
    ao seu próprio usuário — nenhuma resposta mistura dados de outra.
    """
    N = 5

    def resposta_por_usuario(user_state):
        return f"Olá, usuário {user_state['id_usuario']}!"

    mock_graph = _make_fake_ainvoke(resposta_por_usuario)

    def enviar(id_usuario):
        return client.post(
            CHAT_ENDPOINT,
            headers=CHAT_HEADERS,
            json={"id_usuario": id_usuario, "id_topico": 0, "text": "Olá!"},
        )

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        respostas = _coletar_paralelo(enviar, list(range(1, N + 1)))

    for i, resp in enumerate(respostas):
        id_usuario = i + 1
        assert resp.status_code == 200, (
            f"Usuário {id_usuario} recebeu status {resp.status_code}"
        )
        body = resp.json()
        conteudo = body["choices"][0]["message"]["content"]
        assert f"usuário {id_usuario}" in conteudo, (
            f"Resposta do usuário {id_usuario} contém conteúdo errado: '{conteudo}'"
        )


def test_chat_concorrente_nenhum_usuario_recebe_resposta_de_outro(client):
    """
    Verifica a ausência de cross-contamination: a resposta do usuário X
    não deve conter menção ao usuário Y.
    """
    usuarios = [10, 20, 30]

    def resposta_exclusiva(user_state):
        return f"Resposta exclusiva para id={user_state['id_usuario']}"

    mock_graph = _make_fake_ainvoke(resposta_exclusiva)

    def enviar(id_usuario):
        return client.post(
            CHAT_ENDPOINT,
            headers=CHAT_HEADERS,
            json={"id_usuario": id_usuario, "id_topico": 0, "text": "Teste!"},
        )

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        respostas = _coletar_paralelo(enviar, usuarios)

    for i, resp in enumerate(respostas):
        id_proprio = usuarios[i]
        ids_outros = [u for u in usuarios if u != id_proprio]

        assert resp.status_code == 200
        conteudo = resp.json()["choices"][0]["message"]["content"]

        # Deve conter o próprio ID
        assert str(id_proprio) in conteudo, (
            f"Resposta de {id_proprio} não menciona o próprio ID: '{conteudo}'"
        )
        # Não deve conter ID de outro usuário
        for id_outro in ids_outros:
            assert str(id_outro) not in conteudo, (
                f"Resposta de {id_proprio} contém dados do usuário {id_outro}: '{conteudo}'"
            )


def test_chat_concorrente_todas_retornam_200(client):
    """
    8 requisições simultâneas de chat devem todas completar com 200.
    """
    N = 8

    mock_graph = _make_fake_ainvoke(lambda state: "Resposta padrão.")

    def enviar(i):
        return client.post(
            CHAT_ENDPOINT,
            headers=CHAT_HEADERS,
            json={"id_usuario": i, "id_topico": i, "text": f"Pergunta {i}"},
        )

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        respostas = _coletar_paralelo(enviar, list(range(N)))

    statuses = [r.status_code for r in respostas]
    assert all(s == 200 for s in statuses), f"Nem todas retornaram 200: {statuses}"


# ---------------------------------------------------------------------------
# 4. Isolamento de erro — falha em uma thread não contamina as outras
# ---------------------------------------------------------------------------


def test_chat_concorrente_erro_em_uma_nao_afeta_outras(client):
    """
    Se uma requisição falha (500) por exceção interna, as outras requisições
    simultâneas devem retornar 200 com conteúdo correto.

    A falha é determinística: o usuário com id_usuario=99 sempre falha.
    Os demais (1..4) sempre têm sucesso com resposta identificável.
    """
    ID_QUE_FALHA = 99
    ids_sucesso = [1, 2, 3, 4]

    async def ainvoke_por_usuario(user_state, config=None):
        if int(user_state["id_usuario"]) == ID_QUE_FALHA:
            raise RuntimeError("Erro simulado para o usuário especial")

        final_state = dict(user_state)
        final_state["response"] = {
            "response": f"Resposta para usuário {user_state['id_usuario']}",
            "n_tokens": [10, 5],
            "finish_reason": "stop",
            "type_choiced_summary": "Not found",
            "reasoning": None,
        }
        return final_state

    mock_graph = MagicMock()
    mock_graph.ainvoke = ainvoke_por_usuario

    todos_os_ids = ids_sucesso + [ID_QUE_FALHA]

    def enviar(id_usuario):
        return client.post(
            CHAT_ENDPOINT,
            headers=CHAT_HEADERS,
            json={"id_usuario": id_usuario, "id_topico": 0, "text": "Olá!"},
        )

    with patch(
        "sei_ia.routers.chat.build_chat_completion_graph",
        return_value=mock_graph,
    ):
        respostas = _coletar_paralelo(enviar, todos_os_ids)

    # respostas[i] corresponde a todos_os_ids[i]
    for i, id_usuario in enumerate(todos_os_ids):
        resp = respostas[i]
        if id_usuario == ID_QUE_FALHA:
            assert resp.status_code == 500, (
                f"Usuário {id_usuario} deveria ter falhado com 500, recebeu {resp.status_code}"
            )
        else:
            assert resp.status_code == 200, (
                f"Usuário {id_usuario} não deveria ter falhado, recebeu {resp.status_code}"
            )
            conteudo = resp.json()["choices"][0]["message"]["content"]
            assert str(id_usuario) in conteudo, (
                f"Resposta do usuário {id_usuario} não contém o próprio ID: '{conteudo}'"
            )

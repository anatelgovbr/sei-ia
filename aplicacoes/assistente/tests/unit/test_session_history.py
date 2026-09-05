"""Testes offline (sem DB/LLM) para seed de histórico e middleware de janela."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pandas as pd
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from sei_ia.agents.session_agent.window import ConversationWindowMiddleware
from sei_ia.services.session_fs.history import seed_messages_from_jsonl

# ---------------------------------------------------------------------------
# seed_messages_from_jsonl
# ---------------------------------------------------------------------------


def _escreve_jsonl(path: Path, turnos: list[dict]) -> None:
    linhas = [json.dumps(t, ensure_ascii=False) for t in turnos]
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _turno(i: int, resposta: str = "resp") -> dict:
    return {
        "pergunta": f"pergunta {i}",
        "resposta": resposta,
        "dth_cadastro": f"2024-01-{i:02d}T10:00:00",
        "total_tokens": 100 + i,
    }


def test_seed_retorna_ultimos_n_pares(tmp_path):
    jsonl = tmp_path / "historico_conversa.jsonl"
    M, N = 7, 3
    turnos = [_turno(i) for i in range(1, M + 1)]
    _escreve_jsonl(jsonl, turnos)

    msgs = seed_messages_from_jsonl(jsonl, "u1_t1", max_turns=N)

    assert len(msgs) == 2 * N
    # Primeiro par deve ser do turno M-N+1 = 5
    assert isinstance(msgs[0], HumanMessage)
    assert "pergunta 5" in msgs[0].content
    assert isinstance(msgs[1], AIMessage)
    assert msgs[1].content == "resp"


def test_seed_human_tem_prefixo_timestamp(tmp_path):
    jsonl = tmp_path / "historico_conversa.jsonl"
    _escreve_jsonl(jsonl, [_turno(1)])

    msgs = seed_messages_from_jsonl(jsonl, "u1_t1", max_turns=5)

    human = msgs[0]
    assert "2024-01-01T10:00:00" in human.content
    assert "pergunta 1" in human.content


def test_seed_ids_deterministicos(tmp_path):
    jsonl = tmp_path / "historico_conversa.jsonl"
    _escreve_jsonl(jsonl, [_turno(1), _turno(2)])

    msgs1 = seed_messages_from_jsonl(jsonl, "u1_t1", max_turns=5)
    msgs2 = seed_messages_from_jsonl(jsonl, "u1_t1", max_turns=5)

    ids1 = [m.id for m in msgs1]
    ids2 = [m.id for m in msgs2]
    assert ids1 == ids2
    assert len(set(ids1)) == len(ids1)  # todos distintos


def test_seed_ordem_cronologica(tmp_path):
    jsonl = tmp_path / "historico_conversa.jsonl"
    _escreve_jsonl(jsonl, [_turno(1), _turno(2), _turno(3)])

    msgs = seed_messages_from_jsonl(jsonl, "u1_t1", max_turns=5)

    humans = [m for m in msgs if isinstance(m, HumanMessage)]
    conteudos = [m.content for m in humans]
    # Deve estar em ordem ascendente
    assert conteudos == sorted(conteudos)


def test_seed_arquivo_ausente(tmp_path):
    jsonl = tmp_path / "historico_conversa.jsonl"
    assert seed_messages_from_jsonl(jsonl, "u1_t1", max_turns=5) == []


def test_seed_pula_resposta_vazia(tmp_path):
    jsonl = tmp_path / "historico_conversa.jsonl"
    turnos = [_turno(1), _turno(2, resposta=""), _turno(3)]
    _escreve_jsonl(jsonl, turnos)

    msgs = seed_messages_from_jsonl(jsonl, "u1_t1", max_turns=5)

    # Turno 2 (resposta vazia) é ignorado → 2 pares = 4 msgs
    assert len(msgs) == 4
    humans = [m.content for m in msgs if isinstance(m, HumanMessage)]
    assert not any("pergunta 2" in c for c in humans)


# ---------------------------------------------------------------------------
# ConversationWindowMiddleware._removidos
# ---------------------------------------------------------------------------


def _make_id(s: str) -> str:
    return f"id-{s}"


def test_janela_remove_turnos_antigos():
    """Com max_turns=2 e 4 Humans, remove tudo antes do 3º Human."""
    h1 = HumanMessage(content="h1", id=_make_id("h1"))
    a1 = AIMessage(content="a1", id=_make_id("a1"))
    # Simula tool-call sequence entre a1 e h2
    tool_ai = AIMessage(
        content="",
        id=_make_id("tool_ai"),
        tool_calls=[{"name": "ls", "args": {}, "id": "tc1", "type": "tool_call"}],
    )
    tool_msg = ToolMessage(content="ok", id=_make_id("tool_msg"), tool_call_id="tc1")
    a2 = AIMessage(content="a2", id=_make_id("a2"))
    h2 = HumanMessage(content="h2", id=_make_id("h2"))
    a3 = AIMessage(content="a3", id=_make_id("a3"))
    h3 = HumanMessage(content="h3", id=_make_id("h3"))
    a4 = AIMessage(content="a4", id=_make_id("a4"))

    messages = [h1, a1, tool_ai, tool_msg, a2, h2, a3, h3, a4]
    mw = ConversationWindowMiddleware(max_turns=2)
    removidos = mw._removidos(messages)

    ids_removidos = {r.id for r in removidos}
    # Deve remover h1, a1, tool_ai, tool_msg, a2 (tudo antes do h2, que é o (N-1)º último Human)
    assert _make_id("h1") in ids_removidos
    assert _make_id("a1") in ids_removidos
    assert _make_id("tool_ai") in ids_removidos
    assert _make_id("tool_msg") in ids_removidos
    assert _make_id("a2") in ids_removidos
    # h2, a3, h3, a4 devem sobrar
    assert _make_id("h2") not in ids_removidos
    assert _make_id("h3") not in ids_removidos
    assert _make_id("a3") not in ids_removidos
    assert _make_id("a4") not in ids_removidos


def test_janela_sem_remocao_quando_poucos_turnos():
    """Com ≤N Humans não remove nada."""
    messages = [
        HumanMessage(content="h1", id="i1"),
        AIMessage(content="a1", id="i2"),
    ]
    mw = ConversationWindowMiddleware(max_turns=2)
    assert mw._removidos(messages) == []


def test_janela_nao_remove_system():
    """SystemMessage nunca entra na lista de removidos, mesmo estando antes do cutoff."""
    sys = SystemMessage(content="sys", id="sys-id")
    h1 = HumanMessage(content="h1", id="h1-id")
    a1 = AIMessage(content="a1", id="a1-id")
    h2 = HumanMessage(content="h2", id="h2-id")
    a2 = AIMessage(content="a2", id="a2-id")
    h3 = HumanMessage(content="h3", id="h3-id")
    a3 = AIMessage(content="a3", id="a3-id")

    messages = [sys, h1, a1, h2, a2, h3, a3]
    mw = ConversationWindowMiddleware(max_turns=2)
    removidos = mw._removidos(messages)

    ids = {r.id for r in removidos}
    assert "sys-id" not in ids
    assert "h1-id" in ids
    assert "a1-id" in ids


# ---------------------------------------------------------------------------
# _ensure_history (testa o método do manager diretamente)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_history_grava_jsonl(tmp_path):
    from sei_ia.services.session_fs.manager import SessionManager
    from sei_ia.services.session_fs.types import SessionPaths

    paths = SessionPaths.for_session(tmp_path, "u1_t1")
    paths.workspace.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        [
            {
                "pergunta": "p1",
                "resposta": "r1",
                "dth_cadastro": pd.Timestamp("2024-01-01"),
                "total_tokens": 10,
            },
            {
                "pergunta": "p2",
                "resposta": "r2",
                "dth_cadastro": pd.Timestamp("2024-01-02"),
                "total_tokens": 20,
            },
        ]
    )

    async def fetch_history():
        return df

    # Usa checkpointer fake — adelete_thread nunca é chamado neste teste
    fake_checkpointer = unittest.mock.MagicMock()
    manager = SessionManager(
        sessions_root=tmp_path,
        ttl_seconds=3600,
        checkpointer=fake_checkpointer,
    )

    count = await manager._ensure_history(paths, fetch_history)

    jsonl = paths.root / "historico_conversa.jsonl"
    assert jsonl.exists()
    assert count == 2
    linhas = [
        json.loads(linha) for linha in jsonl.read_text().splitlines() if linha.strip()
    ]
    assert linhas[0]["pergunta"] == "p1"
    assert linhas[1]["pergunta"] == "p2"


@pytest.mark.asyncio
async def test_ensure_history_sempre_reescreve(tmp_path):
    """Rebusca do SEI a cada chamada e reescreve, refletindo turnos novos do frontend."""
    from sei_ia.services.session_fs.manager import SessionManager
    from sei_ia.services.session_fs.types import SessionPaths

    paths = SessionPaths.for_session(tmp_path, "u1_t1")
    paths.workspace.mkdir(parents=True, exist_ok=True)

    chamadas = 0

    async def fetch_history():
        nonlocal chamadas
        chamadas += 1
        n = 1 if chamadas == 1 else 2  # 2a chamada: o frontend gravou um turno novo
        return pd.DataFrame(
            [
                {
                    "pergunta": f"p{i}",
                    "resposta": f"r{i}",
                    "dth_cadastro": pd.Timestamp(f"2024-01-0{i}"),
                    "total_tokens": 5,
                }
                for i in range(1, n + 1)
            ]
        )

    manager = SessionManager(
        sessions_root=tmp_path,
        ttl_seconds=3600,
        checkpointer=unittest.mock.MagicMock(),
    )

    count1 = await manager._ensure_history(paths, fetch_history)
    count2 = await manager._ensure_history(paths, fetch_history)

    assert count1 == 1
    assert count2 == 2  # reescreveu refletindo o turno novo
    assert chamadas == 2  # rebuscou o SEI na 2a vez
    linhas = [
        json.loads(linha)
        for linha in (paths.root / "historico_conversa.jsonl").read_text().splitlines()
        if linha.strip()
    ]
    assert [item["pergunta"] for item in linhas] == ["p1", "p2"]


@pytest.mark.asyncio
async def test_ensure_history_preserva_em_falha(tmp_path):
    """Se a busca ao SEI falha, mantem o JSONL anterior em vez de apaga-lo."""
    from sei_ia.services.session_fs.manager import SessionManager
    from sei_ia.services.session_fs.types import SessionPaths

    paths = SessionPaths.for_session(tmp_path, "u1_t1")
    paths.workspace.mkdir(parents=True, exist_ok=True)

    falha = False

    async def fetch_history():
        if falha:
            raise RuntimeError("SEI indisponível")
        return pd.DataFrame(
            [
                {
                    "pergunta": "p1",
                    "resposta": "r1",
                    "dth_cadastro": pd.Timestamp("2024-01-01"),
                    "total_tokens": 5,
                }
            ]
        )

    manager = SessionManager(
        sessions_root=tmp_path,
        ttl_seconds=3600,
        checkpointer=unittest.mock.MagicMock(),
    )

    count1 = await manager._ensure_history(paths, fetch_history)
    falha = True
    count2 = await manager._ensure_history(paths, fetch_history)

    assert count1 == 1
    assert count2 == 1  # preservou o JSONL anterior
    assert (paths.root / "historico_conversa.jsonl").exists()


@pytest.mark.asyncio
async def test_ensure_history_dataframe_vazio(tmp_path):
    from sei_ia.services.session_fs.manager import SessionManager
    from sei_ia.services.session_fs.types import SessionPaths

    paths = SessionPaths.for_session(tmp_path, "u1_t1")
    paths.workspace.mkdir(parents=True, exist_ok=True)

    async def fetch_history():
        return pd.DataFrame()

    manager = SessionManager(
        sessions_root=tmp_path,
        ttl_seconds=3600,
        checkpointer=unittest.mock.MagicMock(),
    )

    count = await manager._ensure_history(paths, fetch_history)

    assert count == 0
    assert not (paths.root / "historico_conversa.jsonl").exists()


# ---------------------------------------------------------------------------
# _apply_history_policy (skip_memory vs sincronização)
# ---------------------------------------------------------------------------


def _fake_resolved(tmp_path):
    from types import SimpleNamespace

    from sei_ia.services.session_fs.types import SessionPaths

    paths = SessionPaths.for_session(tmp_path, "u1_t1")
    paths.workspace.mkdir(parents=True, exist_ok=True)
    (paths.root / "historico_conversa.jsonl").write_text(
        '{"pergunta":"p","resposta":"r","dth_cadastro":"x","total_tokens":1}\n',
        encoding="utf-8",
    )
    return SimpleNamespace(paths=paths)


@pytest.mark.asyncio
async def test_apply_history_policy_skip_memory_remove_jsonl_e_zera(tmp_path):
    """skip_memory: remove o JSONL e zera a janela (só o turno atual)."""
    from sei_ia.routers.session.stream import _apply_history_policy

    resolved = _fake_resolved(tmp_path)
    jsonl = resolved.paths.root / "historico_conversa.jsonl"
    agent = unittest.mock.MagicMock()
    agent.aupdate_state = unittest.mock.AsyncMock()

    await _apply_history_policy(
        agent,
        {"configurable": {"thread_id": "u1_t1"}},
        resolved,
        skip_memory=True,
        traced=False,
    )

    assert not jsonl.exists()  # JSONL removido
    agent.aupdate_state.assert_awaited_once()
    msgs = agent.aupdate_state.await_args.args[1]["messages"]
    assert len(msgs) == 1  # só o RemoveMessage(REMOVE_ALL_MESSAGES)


@pytest.mark.asyncio
async def test_apply_history_policy_sincroniza_quando_nao_skip(tmp_path, monkeypatch):
    """Sem skip_memory e com SESSION_SEED_HISTORY, sincroniza a janela do JSONL."""
    from sei_ia.configs.settings_config import settings
    from sei_ia.routers.session.stream import _apply_history_policy

    monkeypatch.setattr(settings, "SESSION_SEED_HISTORY", True)
    monkeypatch.setattr(settings, "SESSION_MAX_TURNS", 20)
    resolved = _fake_resolved(tmp_path)
    jsonl = resolved.paths.root / "historico_conversa.jsonl"
    agent = unittest.mock.MagicMock()
    agent.aupdate_state = unittest.mock.AsyncMock()

    await _apply_history_policy(
        agent,
        {"configurable": {"thread_id": "u1_t1"}},
        resolved,
        skip_memory=False,
        traced=False,
    )

    assert jsonl.exists()  # JSONL preservado
    agent.aupdate_state.assert_awaited_once()
    msgs = agent.aupdate_state.await_args.args[1]["messages"]
    assert len(msgs) == 3  # REMOVE_ALL_MESSAGES + 1 par (Human + AI)

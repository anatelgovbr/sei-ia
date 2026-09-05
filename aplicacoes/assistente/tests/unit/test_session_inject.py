"""Unit tests do modo injetado (fase 6): bloco de documentos + prompt por modo.

Sem rede: `build_injected_context` roda sobre uma sessão sintética em tmp_path;
`compose_system_prompt` é função pura. O gate de citação idêntica entre modos é
verificado pelo marcador `<doc_{id}>` no bloco (mesmo formatador do clássico).
"""

from __future__ import annotations

import pytest

from sei_ia.agents.session_agent.agent import build_session_agent, compose_system_prompt
from sei_ia.agents.session_agent.inject import build_injected_context
from sei_ia.agents.session_agent.prompts import (
    INJECTED_SYSTEM_PROMPT,
    SESSION_SYSTEM_PROMPT,
    WEBSEARCH_DIRECTIVE,
)
from sei_ia.services.session_fs.manager import ResolvedSession
from sei_ia.services.session_fs.types import SessionMeta, SessionPaths


def _resolved(tmp_path, processos, documentos, files: dict[str, str]):
    """Monta uma ResolvedSession sintética com os arquivos no disco."""
    paths = SessionPaths.for_session(tmp_path, "1_1")
    for rel, content in files.items():
        target = paths.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    meta = SessionMeta(
        created_at=0.0,
        last_access=0.0,
        ttl_seconds=3600,
        processos=processos,
        documentos=documentos,
    )
    return ResolvedSession(paths=paths, meta=meta, is_new=True)


def test_injected_context_contem_docs_e_marcadores(tmp_path):
    r = _resolved(
        tmp_path,
        processos={
            "77": {
                "id_procedimento": "77",
                "documentos": ["10", "2"],
                "metadata": {"id_protocolo_formatado": "PROC-77"},
            }
        },
        documentos={
            "10": {
                "id_documento": "10",
                "id_documento_formatado": "DOC-10",
                "arquivo": "proc_77/10.txt",
            },
            "2": {
                "id_documento": "2",
                "id_documento_formatado": "DOC-2",
                "arquivo": "proc_77/2.txt",
            },
        },
        files={"proc_77/10.txt": "CONTEUDO DEZ", "proc_77/2.txt": "CONTEUDO DOIS"},
    )
    bloco = build_injected_context(r)
    assert bloco.startswith("<documentos_da_sessao>")
    assert bloco.endswith("</documentos_da_sessao>")
    # mesmos marcadores <doc_{id}> do clássico -> contrato de citação idêntico
    assert "<doc_2>" in bloco and "<doc_10>" in bloco
    assert "CONTEUDO DEZ" in bloco and "CONTEUDO DOIS" in bloco
    # A ordem do manifesto é preservada para manter processo/documento alinhados.
    assert bloco.index("<doc_10>") < bloco.index("<doc_2>")


def test_injected_context_preserva_metadata_de_documento_e_ordem_v3(tmp_path):
    paths = SessionPaths.for_session(tmp_path, "1_1")
    for rel, content in {
        "proc_77/10.txt": "PRIMEIRO",
        "proc_77/2.txt": "SEGUNDO",
    }.items():
        target = paths.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    meta = SessionMeta(
        created_at=0.0,
        last_access=0.0,
        ttl_seconds=3600,
        processos={
            "77": {
                "id_procedimento": "77",
                "metadata": {"numero": "53500.77"},
                "documentos": ["10", "2"],
            }
        },
        documentos={
            "10": {
                "id_documento": "10",
                "arquivo": "proc_77/10.txt",
                "metadata": {"tipo": "primeiro"},
            },
            "2": {
                "id_documento": "2",
                "arquivo": "proc_77/2.txt",
                "metadata": {"tipo": "segundo"},
            },
        },
    )
    r = ResolvedSession(paths=paths, meta=meta, is_new=True)

    bloco = build_injected_context(r)

    assert bloco.index("<doc_10>") < bloco.index("<doc_2>")
    assert "tipo: primeiro" in bloco
    assert "tipo: segundo" in bloco


def test_injected_context_exibe_ids_interno_e_formatado(tmp_path):
    r = _resolved(
        tmp_path,
        processos={
            "17918415": {
                "id_procedimento": "17918415",
                "documentos": ["17930920"],
                "metadata": {"id_protocolo_formatado": "00000.000000/0000-00"},
            }
        },
        documentos={
            "17930920": {
                "id_documento": "17930920",
                "id_documento_formatado": "16016297",
                "arquivo": "proc_17918415/17930920.txt",
            }
        },
        files={"proc_17918415/17930920.txt": "CONTEUDO"},
    )

    bloco = build_injected_context(r)

    assert (
        "Referências internas (somente para navegação; não repetir ao usuário):"
        in bloco
    )
    assert "id_documento: 17930920" in bloco
    assert "Documento SEI nº: 16016297" in bloco
    assert "id_procedimento: 17918415" in bloco
    assert "<doc_17930920>" in bloco


def test_injected_context_pula_arquivo_ausente(tmp_path):
    r = _resolved(
        tmp_path,
        processos={
            "77": {
                "id_procedimento": "77",
                "documentos": ["1", "9"],
                "metadata": {"id_protocolo_formatado": "PROC-77"},
            }
        },
        documentos={
            "1": {
                "id_documento": "1",
                "id_documento_formatado": "DOC-1",
                "arquivo": "proc_77/1.txt",
            },
            "9": {
                "id_documento": "9",
                "id_documento_formatado": "DOC-9",
                "arquivo": "proc_77/9.txt",
            },  # não existe
        },
        files={"proc_77/1.txt": "SOZINHO"},
    )
    bloco = build_injected_context(r)
    assert "SOZINHO" in bloco
    assert "<doc_9>" not in bloco  # ausente é pulado, nunca inventado


def test_injected_context_aceita_id_documento_formatado_ausente(tmp_path):
    r = _resolved(
        tmp_path,
        processos={
            "77": {
                "id_procedimento": "77",
                "documentos": ["1"],
                "metadata": {"id_protocolo_formatado": "PROC-77"},
            }
        },
        documentos={
            "1": {"id_documento": "1", "arquivo": "proc_77/1.txt"},
        },
        files={"proc_77/1.txt": "CONTEUDO"},
    )

    bloco = build_injected_context(r)

    assert "Documento SEI nº: não disponível" in bloco


def test_injected_context_indica_documento_vazio(tmp_path):
    resolved = _resolved(
        tmp_path,
        processos={
            "77": {
                "documentos": ["1"],
                "metadata": {"id_protocolo_formatado": "00000.000000/0000-00"},
            }
        },
        documentos={
            "1": {
                "id_documento": "1",
                "id_documento_formatado": "DOC-1",
                "arquivo": "proc_77/1.txt",
                "content_state": "empty",
            }
        },
        files={"proc_77/1.txt": ""},
    )

    bloco = build_injected_context(resolved)

    assert "<doc_1>" in bloco
    assert "Estado do conteúdo: documento existente, sem conteúdo textual." in bloco
    assert "[Documento existente, mas sem conteúdo textual no SEI.]" in bloco


def test_injected_context_indica_documento_indisponivel_sem_ler_arquivo(tmp_path):
    resolved = _resolved(
        tmp_path,
        processos={"77": {"documentos": ["1"], "metadata": {}}},
        documentos={
            "1": {
                "id_documento": "1",
                "id_documento_formatado": None,
                "arquivo": None,
                "content_state": "unavailable",
                "content_reason": "binary_not_found",
            }
        },
        files={},
    )

    bloco = build_injected_context(resolved)

    assert "Processo/protocolo: não disponível" in bloco
    assert (
        "[Conteúdo do documento indisponível nesta solicitação. Não infira fatos.]"
        in bloco
    )


def test_compose_prompt_injetado_tem_bloco_no_fim_e_sem_exploracao():
    bloco = "<documentos_da_sessao>X</documentos_da_sessao>"
    p = compose_system_prompt(mode="injected", injected_context=bloco)
    assert p.startswith(INJECTED_SYSTEM_PROMPT)
    assert p.endswith(bloco)  # bloco por último: prefixo estável p/ cache
    assert "## Esforço" not in p  # diretiva de complexidade (exploração) não entra
    assert "task(name=" not in p  # sem instrução de subagente


def test_compose_prompt_injetado_exige_contexto():
    with pytest.raises(ValueError):
        compose_system_prompt(mode="injected", injected_context=None)


def test_compose_prompt_injetado_com_websearch():
    p = compose_system_prompt(
        mode="injected", use_websearch=True, injected_context="<documentos_da_sessao/>"
    )
    assert WEBSEARCH_DIRECTIVE in p


def test_compose_prompt_filesystem_inalterado():
    p = compose_system_prompt(mode="filesystem", complexity="medium")
    assert p.startswith(SESSION_SYSTEM_PROMPT)
    assert "## Esforço: MÉDIO" in p
    assert "<documentos_da_sessao>" not in p


def test_prompts_separam_marcadores_de_documento_e_upload():
    """Os dois modos instruem o agente a citar uploads em namespace próprio."""
    for prompt in (SESSION_SYSTEM_PROMPT, INJECTED_SYSTEM_PROMPT):
        assert "<doc_ID></doc_ID>" in prompt
        assert "<upload_ID></upload_ID>" in prompt


def test_build_session_agent_injetado_constroi_grafo(tmp_path):
    agent = build_session_agent(
        tmp_path / "1_1",
        checkpointer=None,
        mode="injected",
        injected_context="<documentos_da_sessao>doc</documentos_da_sessao>",
    )
    assert agent is not None
    assert hasattr(agent, "astream")

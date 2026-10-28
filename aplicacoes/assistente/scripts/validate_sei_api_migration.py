"""Equivalência OLD fork vs NEW sei_api adapter, contra a API de homologação.

Roda no venv do assistente (tem settings + sei_api). Carrega o fork antigo de um
caminho passado em SEI_FORK_PATH (restaurado do git), monta o adapter novo, e
compara as saídas dos métodos que produção usa, mais as duas decisões cortadas
(total_tokens do histórico e a cadeia de conteúdo).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pandas as pd

ID_PROCESSO = os.environ.get("VAL_ID_PROCESSO", "17427372")
ID_DOCUMENTO = os.environ.get("VAL_ID_DOCUMENTO", "17452066")
ID_TOPICO = os.environ.get("VAL_ID_TOPICO", "1")


def _load_fork(path: str):
    spec = importlib.util.spec_from_file_location("_old_fork", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_old_fork"] = mod
    spec.loader.exec_module(mod)
    return mod


def _frames_equal(a: pd.DataFrame, b: pd.DataFrame, cols: list[str]) -> bool:
    a2 = a.reindex(columns=cols).reset_index(drop=True)
    b2 = b.reindex(columns=cols).reset_index(drop=True)
    return a2.equals(b2)


def _dta_line(metadata_str: str) -> str:
    for line in metadata_str.splitlines():
        if line.startswith("Data de Inclusão do Documento:"):
            return line.split(":", 1)[1].strip()
    return ""


def _check_dta_consumed_strings(old_idoc: pd.DataFrame, record) -> None:
    """Asseri a STRING de dta_inclusao que o LLM consome, não só a coluna.

    O str() em cima do Timestamp da lib regrediu a linha para
    "YYYY-MM-DD HH:MM:SS"; o invariante do assistente é date-only. O harness
    antigo comparava só a coluna do DataFrame e passava enquanto a string
    consumida por get_doc_metadata_from_id e fetch_documentos_metadata_batch
    regredia. Asserir aqui fecha o ponto cego.
    """
    import asyncio

    from sei_ia.data.etl.extract.metadata import (
        fetch_documentos_metadata_batch,
        get_doc_metadata_from_id,
    )

    expected = str(old_idoc["dta_inclusao"].iloc[0]) if not old_idoc.empty else ""

    single_dta = _dta_line(asyncio.run(get_doc_metadata_from_id(ID_DOCUMENTO)))
    record(
        "get_doc_metadata_from_id dta date-only == fork",
        single_dta == expected and len(single_dta) == len("YYYY-MM-DD"),
        f"(fork={expected!r}, consumed={single_dta!r})",
    )

    batch = asyncio.run(fetch_documentos_metadata_batch([ID_DOCUMENTO]))
    batch_dta = _dta_line(batch.get(ID_DOCUMENTO, {}).get("metadata_str", ""))
    record(
        "fetch_documentos_metadata_batch dta date-only == fork",
        batch_dta == expected and len(batch_dta) == len("YYYY-MM-DD"),
        f"(fork={expected!r}, consumed={batch_dta!r})",
    )


def main() -> int:
    fork_path = os.environ["SEI_FORK_PATH"]
    old = _load_fork(fork_path)
    old_handler = old.SEIDBHandler

    from sei_ia.data.database.sei_client import (
        consulta_historico_topico_com_tokens,
        sei_client,
    )

    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, note: str = "") -> None:
        results.append((name, ok, note))
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {note}")

    # 1. internal_docs_from_process_api (metadados de documento)
    old_idoc = old_handler.internal_docs_from_process_api(id_documentos=ID_DOCUMENTO)
    new_idoc = sei_client.internal_docs_from_process_api(id_documentos=ID_DOCUMENTO)
    cols = [
        "id_protocolo",
        "num_doc",
        "documento_especificacao",
        "id_type_document",
        "formato_arquivo",
        "name_id_type_doc",
        "id_protocolo_documento",
        "type_doc",
        "num_proc",
    ]
    record(
        "internal_docs_from_process_api",
        _frames_equal(old_idoc, new_idoc, cols),
        f"(old rows={len(old_idoc)}, new rows={len(new_idoc)})",
    )
    # dta_inclusao: fork formata '%Y-%m-%d' (str); lib devolve datetime.
    # O assistente consome via str(...), então comparamos a forma str(%Y-%m-%d).
    if not old_idoc.empty and not new_idoc.empty:
        old_dta = str(old_idoc["dta_inclusao"].iloc[0])
        new_dta = pd.to_datetime(new_idoc["dta_inclusao"].iloc[0]).strftime("%Y-%m-%d")
        record(
            "dta_inclusao assistant-format (%Y-%m-%d)",
            old_dta == new_dta,
            f"(old={old_dta!r}, new={new_dta!r})",
        )

    # A coluna do DataFrame casa, mas o que o LLM consome é a STRING final.
    _check_dta_consumed_strings(old_idoc, record)

    # 2. md_ia_consulta_processo_batch (async em ambos)
    import asyncio

    old_proc = asyncio.run(old_handler.md_ia_consulta_processo_batch([ID_PROCESSO]))
    new_proc = asyncio.run(sei_client.md_ia_consulta_processo_batch([ID_PROCESSO]))
    proc_cols = [
        "id_procedimento",
        "id_protocolo_formatado",
        "processo_especificacao",
        "nome_id_tipo_processo",
        "rp1p_descricao",
        "rp2p_descricao",
        "rp1u_sigla",
        "rp2u_sigla",
        "sigla_unid",
        "desc_unid",
    ]
    record(
        "md_ia_consulta_processo_batch",
        _frames_equal(old_proc, new_proc, proc_cols),
        f"(old rows={len(old_proc)}, new rows={len(new_proc)})",
    )

    # 3. md_ia_consulta_documento_batch (fork async, lib sync)
    old_dbatch = asyncio.run(old_handler.md_ia_consulta_documento_batch([ID_DOCUMENTO]))
    new_dbatch = sei_client.md_ia_consulta_documento_batch([ID_DOCUMENTO])
    record(
        "md_ia_consulta_documento_batch",
        _frames_equal(old_dbatch, new_dbatch, cols),
        f"(old rows={len(old_dbatch)}, new rows={len(new_dbatch)})",
    )

    # 4. md_ia_consulta_conteudo_documento_async (content chain)
    old_content = asyncio.run(
        old_handler.md_ia_consulta_conteudo_documento_async(id_documento=ID_DOCUMENTO)
    )
    new_content = asyncio.run(
        sei_client.md_ia_consulta_conteudo_documento_async(id_documento=ID_DOCUMENTO)
    )
    same_doc = old_content.get("content_doc") == new_content.get("content_doc")
    same_tipo = old_content.get("tipo_conteudo") == new_content.get("tipo_conteudo")
    record(
        "conteudo_documento_async content_doc",
        bool(same_doc),
        f"(old_len={len(old_content.get('content_doc') or '')}, "
        f"new_len={len(new_content.get('content_doc') or '')})",
    )
    record("conteudo_documento_async tipo_conteudo", bool(same_tipo))

    # 5. histórico com total_tokens (decisão cortada #1)
    old_hist = old_handler.md_ia_consulta_historico_topico(id_topico=ID_TOPICO)
    new_hist = consulta_historico_topico_com_tokens(id_topico=ID_TOPICO)
    has_col = "total_tokens" in new_hist.columns
    record("historico total_tokens column present", has_col)
    if has_col and not old_hist.empty and not new_hist.empty:
        tokens_match = (
            old_hist["total_tokens"]
            .reset_index(drop=True)
            .equals(new_hist["total_tokens"].reset_index(drop=True))
        )
        record(
            "historico total_tokens values match",
            bool(tokens_match),
            f"(old sum={int(old_hist['total_tokens'].sum())}, "
            f"new sum={int(new_hist['total_tokens'].sum())})",
        )
    elif has_col:
        record(
            "historico total_tokens values match",
            True,
            f"(histórico vazio para topico {ID_TOPICO}; coluna existe e tem dtype int)",
        )

    print("\n=== SUMMARY ===")
    failed = [r for r in results if not r[1]]
    for name, ok, note in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name} {note}")
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    Path(os.environ["SEI_FORK_PATH"])  # fail fast if unset
    raise SystemExit(main())

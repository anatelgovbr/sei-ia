"""Upsert idempotente dos casos do experimento no dataset Langfuse.

Fonte base: `dataset/session-classico/cases.json`. Suites versionadas, como
`benchmark-decision-v2.json`,
selecionam os casos e aplicam ajustes sem reescrever a fotografia historica. Cada item
vira um dataset item com id deterministico por qid (`<dataset>:<qid>`), entao rodar duas
vezes atualiza o mesmo item em vez de duplicar.

Credenciais: usa LF_PUBLIC/LF_SECRET/LF_HOST se setados, senao cai nos LANGFUSE_* do .env.
O dataset `comparativo-deepagents-classico` vive num projeto Langfuse cujas chaves precisam
estar no ambiente (o run_experiment.py aponta para o MESMO dataset).

Uso:
    uv run python experimentos/latencia-session-vs-classico/scripts/session-classico/upsert_dataset.py --dry-run
    uv run python experimentos/latencia-session-vs-classico/scripts/session-classico/upsert_dataset.py
    uv run python experimentos/latencia-session-vs-classico/scripts/session-classico/upsert_dataset.py --create-dataset

Suite decisoria atual:
    uv run python .../upsert_dataset.py --create-dataset --decision-suite

Suite explicita:
    uv run python .../upsert_dataset.py --suite benchmark-decision-v2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zlib
from pathlib import Path

from dataset_manifest import DEFAULT_SUITE, load_suite
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
HERE = SCRIPT_DIR.parents[1]
CASES_PATH = HERE / "dataset" / "session-classico" / "cases.json"
DOCS_DIR = HERE / "dataset" / "docs" / "candidatos"
EXP_ID_USUARIO = 999999


def _build_input(case: dict) -> dict:
    """Monta o SessionStreamRequest completo do caso a partir do index.json do processo.

    A lista de documentos (id_procedimentos) e derivada de dataset/docs/candidatos/
    <processo>/index.json, a fonte da verdade da extracao — nao ha lista de docs
    escrita a mao no manifesto.
    """
    text = case["input"]["text"]
    md = case["metadata"]
    inp = case["input"]
    topico = inp.get("id_topico") or (900000 + zlib.crc32(case["qid"].encode()) % 90000)
    # Caso web-puro (sem processo): sem documentos, só a ferramenta de busca. O router
    # do session tolera id_procedimentos vazio (`or []`); o clássico aceita null (é o
    # payload do guia manual da busca web). Compara os dois endpoints em web pura.
    if md.get("processo") is None:
        assert md.get("requires_web"), (
            f"{case['qid']}: caso sem processo exige requires_web=true"
        )
        return {
            "id_usuario": inp.get("id_usuario", EXP_ID_USUARIO),
            "id_topico": topico,
            "text": text,
            "id_procedimentos": None,
            "use_websearch": True,
            "skip_memory": True,
        }
    processo = str(md["processo"])
    index_path = DOCS_DIR / processo / "index.json"
    assert index_path.exists(), f"{case['qid']}: index.json ausente em {index_path}"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    # Subconjunto de docs (casos que reduzem o payload de um processo): `doc_ids`
    # inclui SO esses; `exclude_doc_ids` remove esses. Default: todos os docs ok.
    only = {str(x) for x in inp.get("doc_ids", [])} or None
    excl = {str(x) for x in inp.get("exclude_doc_ids", [])}
    docs = [
        {
            "id_documento": d["id_documento"],
            "download_ext": d["download_ext"],
            "id_documento_formatado": d["num_doc_formatado"],
        }
        for d in index["docs"]
        if d.get("status") == "ok"
        and str(d["id_documento"]) not in excl
        and (only is None or str(d["id_documento"]) in only)
    ]
    assert docs, f"{case['qid']}: nenhum documento ok no index de {processo}"
    return {
        "id_usuario": inp.get("id_usuario", EXP_ID_USUARIO),
        "id_topico": topico,
        "text": text,
        "id_procedimentos": [
            {"id_procedimento": processo, "id_documentos": docs, "metadata": {}}
        ],
        "use_websearch": bool(md["requires_web"]),
        "skip_memory": True,
    }


def _load_env() -> None:
    app = HERE.parents[1]  # .../aplicacoes/assistente
    worktree = HERE.parents[3]  # raiz do worktree
    for f in (worktree / "security.env", worktree / ".env", app / ".env"):
        if f.exists():
            load_dotenv(f)
    os.environ.setdefault("LF_SECRET", os.environ.get("LANGFUSE_SECRET_KEY", ""))
    os.environ.setdefault("LF_PUBLIC", os.environ.get("LANGFUSE_PUBLIC_KEY", ""))
    os.environ.setdefault(
        "LF_HOST", os.environ.get("LANGFUSE_URL") or os.environ.get("LANGFUSE_HOST", "")
    )


def _item_id(dataset_name: str, qid: str) -> str:
    return f"{dataset_name}:{qid}"


def _validate_cases(cases: list[dict]) -> list[dict]:
    seen: set[str] = set()
    for c in cases:
        qid = c["qid"]
        assert qid not in seen, f"qid duplicado no manifesto: {qid}"
        seen.add(qid)
        assert c["input"].get("text"), f"{qid}: input.text vazio"
        eo = c["expected_output"]
        assert eo.get("categoria"), f"{qid}: categoria vazia"
        assert eo.get("gold_answer_exemplo"), f"{qid}: gold_answer_exemplo vazio"
        md = c["metadata"]
        assert md.get("size_class") in {
            "small",
            "medium",
            "medium-larger",
            "large",
            "web",
        }, f"{qid}: size_class invalido {md.get('size_class')!r}"
        assert isinstance(md.get("requires_web"), bool), (
            f"{qid}: requires_web precisa ser bool"
        )
        # Caso web-puro (size_class=web): processo null e requires_web=true.
        if md.get("size_class") == "web":
            assert md.get("processo") is None and md.get("requires_web"), (
                f"{qid}: size_class=web exige processo=null e requires_web=true"
            )
    return cases


def _load_cases() -> list[dict]:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return _validate_cases(data["cases"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="valida e mostra, nao grava")
    ap.add_argument(
        "--create-dataset", action="store_true", help="cria o dataset se nao existir"
    )
    ap.add_argument(
        "--qids",
        default=None,
        help="subconjunto de qids separados por virgula (dataset reduzido/curado); "
        "default: todos os casos de cases.json",
    )
    ap.add_argument(
        "--decision-suite",
        action="store_true",
        help=f"usa os 10 casos da suite decisoria atual ({DEFAULT_SUITE})",
    )
    ap.add_argument(
        "--suite",
        default=None,
        help="nome ou caminho do manifesto versionado (ex.: benchmark-decision-v2)",
    )
    args = ap.parse_args()

    _load_env()
    suite_selector = args.suite or (DEFAULT_SUITE if args.decision_suite else None)
    manifest = None
    if suite_selector:
        manifest, cases = load_suite(suite_selector)
        cases = _validate_cases(cases)
    else:
        cases = _load_cases()
    dataset_name = (
        os.environ.get("EXP_DATASET_NAME")
        or (manifest or {}).get("dataset_name")
        or "benchmark-cases"
    )
    wanted = (
        {q.strip() for q in args.qids.split(",") if q.strip()} if args.qids else None
    )
    if wanted:
        missing = wanted - {c["qid"] for c in cases}
        assert not missing, f"qids ausentes na fonte selecionada: {sorted(missing)}"
        cases = [c for c in cases if c["qid"] in wanted]
    print(
        f"[upsert] dataset={dataset_name} suite={suite_selector or 'cases.json'} "
        f"casos={len(cases)} "
        f"qids={[c['qid'] for c in cases]}",
        file=sys.stderr,
    )
    if args.dry_run:
        for c in cases:
            md = c["metadata"]
            built = _build_input(c)
            procs = built["id_procedimentos"] or []
            ndocs = len(procs[0]["id_documentos"]) if procs else 0
            print(
                f"  DRY id={_item_id(dataset_name, c['qid'])} "
                f"cat={c['expected_output']['categoria']} "
                f"size={md['size_class']} web={md['requires_web']} proc={md['processo']} "
                f"id_usuario={built['id_usuario']} docs={ndocs} use_websearch={built['use_websearch']}"
            )
        return 0

    from langfuse import Langfuse

    lf = Langfuse(
        secret_key=os.environ["LF_SECRET"],
        public_key=os.environ["LF_PUBLIC"],
        host=os.environ["LF_HOST"],
    )
    assert lf.auth_check(), "Langfuse auth_check falhou"

    if args.create_dataset:
        lf.create_dataset(
            name=dataset_name,
            description=(manifest or {}).get(
                "description", "Casos session vs classico"
            ),
        )

    try:
        ds = lf.get_dataset(dataset_name)
    except Exception as exc:
        # A primeira publicação da suíte deve ser idempotente também quando o
        # dataset ainda não existe no projeto Langfuse configurado.
        if exc.__class__.__name__ != "NotFoundError":
            raise
        lf.create_dataset(
            name=dataset_name,
            description=(manifest or {}).get(
                "description", "Casos session vs classico"
            ),
        )
        ds = lf.get_dataset(dataset_name)
    before = {(it.metadata or {}).get("qid") for it in ds.items}

    for c in cases:
        qid = c["qid"]
        md = dict(c["metadata"], qid=qid)
        lf.create_dataset_item(
            dataset_name=dataset_name,
            id=_item_id(dataset_name, qid),
            input=_build_input(c),
            expected_output=c["expected_output"],
            metadata=md,
        )
        state = "update" if qid in before else "create"
        print(
            f"  {state}: {qid} (id={_item_id(dataset_name, qid)})",
            file=sys.stderr,
        )

    lf.flush()
    after = lf.get_dataset(dataset_name).items
    our = [
        it
        for it in after
        if (it.metadata or {}).get("qid") in {c["qid"] for c in cases}
    ]
    print(
        json.dumps(
            {
                "dataset": dataset_name,
                "suite": suite_selector,
                "upserted": len(cases),
                "total_items_after": len(after),
                "our_items_after": len(our),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

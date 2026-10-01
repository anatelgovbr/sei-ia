"""Mede o tamanho real (chars + tokens len/3.5) de um procedimento SEI.

Reusa o setup de ambiente PD do smoke_endpoint_host.py (load_worktree_envs + LiteLLM via glab) e a
MESMA funcao de extracao da pipeline (get_doc_from_id_async -> sei_extraction.fetch_document_text).
Grava os .txt extraidos e um index.json no formato do 8116731, numa subpasta candidatos/
separada para nao poluir o dataset atual.

Read-only contra a PD. Nao toca codigo de producao. Uso:
    uv run python experimentos/latencia-session-vs-classico/scripts/session-classico/medir_processo.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = EXPERIMENT_ROOT.parents[1]  # aplicacoes/assistente
sys.path.insert(0, str(APP_DIR))

# 1) Ambiente: reusa o loader do smoke_endpoint_host
# (default.env/security.env/.env + LiteLLM do GitLab).
from scripts.smoke_helpers import load_worktree_envs  # noqa: E402

load_worktree_envs(APP_DIR)

# 2) Override PD DEPOIS do loader (que usa load_dotenv override=True). No .env, SEI_ADDRESS
#    resolve para staging; forcamos os dois enderecos para a PD, igual ao run_experiment.py.
os.environ["SEI_ADDRESS"] = "https://sei.anatel.gov.br"
os.environ["SEI_API_DB_ADDRESS"] = "https://sei.anatel.gov.br/sei/controlador_ws.php"
os.environ.setdefault("REDIS_URI", "redis://localhost:8091/0")

# 2b) Override do OCR/visao. O OpenAIVisionOCRClient le settings.LITELLM_PROXY_URL (alias
#     ASSISTENTE_LITELLM_PROXY_URL), que no .env aponta para o Docker interno infra-litellm:4000
#     (nao resolve do host local). Sem este override, um PDF 100% escaneado falha com
#     "Name or service not known" (paginas com texto nativo pulam o OCR e passam sem isto).
#     Aponta para o proxy PD alcancavel (o mesmo que o smoke importa do GitLab) e usa o alias
#     de visao (nano) que ESSE proxy publica. So mexe no ambiente deste script.
_proxy = os.environ.get("LITELLM_PROXY_URL")
if _proxy:
    os.environ["ASSISTENTE_LITELLM_PROXY_URL"] = _proxy
    if os.environ.get("LITELLM_PROXY_API_KEY"):
        os.environ["ASSISTENTE_LITELLM_PROXY_API_KEY"] = os.environ[
            "LITELLM_PROXY_API_KEY"
        ]
    os.environ["ASSISTENTE_OCR_MODEL"] = os.environ.get(
        "LITELLM_NANO_MODEL_NAME", "seiia-ds-nano"
    )

# 3) Cadeia de extracao (le settings de os.environ no import) — depois dos overrides.
from sei_ia.data.etl.extract.doc_content import get_doc_from_id_async  # noqa: E402
from sei_ia.services.counter import token_counter  # noqa: E402

ID_PROCEDIMENTO = "14564832"

# (id_documento, precisa_ocr). download_ext = precisa_ocr (o payload real manda download_ext
# nos que exigem OCR); a rota de extracao em si fica com fetch_document_text.
DOCS: list[tuple[str, bool]] = [
    ("14564839", False),
    ("14564861", False),
    ("14564959", True),
    ("14596903", False),
    ("14663256", True),
    ("14663258", False),
    ("14687537", False),
    ("14688918", True),
    ("14719501", False),
    ("14729684", True),
    ("14729688", False),
    ("15066592", True),
    ("15066639", True),
    ("15066651", True),
    ("15398592", False),
    ("15460005", False),
    ("15570430", True),
    ("15570431", True),
    ("15570432", False),
    ("15584187", False),
    ("15654157", False),
    ("15705617", True),
    ("15705619", False),
    ("16032954", False),
    ("16033354", True),
    ("16102776", False),
    ("16165997", True),
    ("16165999", False),
    ("16245195", False),
    ("16274693", True),
    ("16274695", True),
    ("16343582", False),
    ("16362647", False),
    ("16457602", True),
    ("16457605", False),
    ("16474966", False),
    ("16515478", False),
    ("16548740", False),
    ("16555050", True),
    ("16555053", False),
    ("16570775", False),
    ("16601982", False),
    ("16702419", True),
    ("16702422", True),
    ("16702423", False),
    ("16768876", False),
    ("16844187", True),
    ("16844190", False),
    ("17468022", True),
    ("17468025", False),
    ("17492116", False),
    ("17538725", True),
    ("17561724", True),
    ("17565064", True),
    ("17569410", True),
    ("17569417", True),
    ("17569715", True),
    ("17571849", False),
    ("17707505", False),
]

OUT_DIR = EXPERIMENT_ROOT / "dataset" / "docs" / "candidatos" / ID_PROCEDIMENTO
CUTS = {"25k": 25_000, "50k": 50_000, "100k": 100_000}


def classify(tokens: int) -> str:
    if tokens < CUTS["25k"]:
        return "small (< 25k)"
    if tokens < CUTS["100k"]:
        return "medium (25k-100k)"
    return "large (> 100k)"


async def extract_one(idx: int, id_doc: str, precisa_ocr: bool) -> dict:
    entry: dict = {
        "idx": idx,
        "id_documento": id_doc,
        "download_ext": precisa_ocr,
        "precisa_ocr": precisa_ocr,
        "num_doc_formatado": None,
        "content_len": 0,
        "file": None,
        "extra_metadata": {},
        "status": "ok",
    }
    try:
        content, num_fmt, extra = await get_doc_from_id_async(
            id_documento=id_doc, download_ext=precisa_ocr
        )
        content = content or ""
        entry["num_doc_formatado"] = num_fmt
        entry["content_len"] = len(content)
        entry["extra_metadata"] = extra or {}
        if not content.strip():
            entry["status"] = "empty"
        else:
            fname = f"{idx:02d}_{id_doc}_{num_fmt or 'sn'}.txt"
            (OUT_DIR / fname).write_text(content, encoding="utf-8")
            entry["file"] = fname
    except Exception as exc:  # NOSONAR — registra e segue, nao inventa tamanho
        entry["status"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    return entry


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    for i, (id_doc, ocr) in enumerate(DOCS, start=1):
        entry = await extract_one(i, id_doc, ocr)
        entries.append(entry)
        mark = "ocr" if ocr else "nat"
        print(
            f"[{i:02d}/{len(DOCS)}] {id_doc} ({mark}) "
            f"num={entry['num_doc_formatado']} len={entry['content_len']} "
            f"status={entry['status']}",
            flush=True,
        )

    ok = [e for e in entries if e["status"] == "ok"]
    failed = [e for e in entries if e["status"] not in ("ok",)]
    total_chars = sum(e["content_len"] for e in ok)
    total_tokens = sum(token_counter_of(e) for e in ok)

    index = {
        "processo": ID_PROCEDIMENTO,
        "n_docs": len(DOCS),
        "n_ok": len(ok),
        "n_failed": len(failed),
        "total_chars": total_chars,
        "total_tokens": total_tokens,
        "token_rule": "len/3.5 (sei_ia.services.counter.token_counter), somado por doc",
        "cuts": CUTS,
        "classification": classify(total_tokens),
        "docs": entries,
    }
    (OUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n===== RESUMO =====")
    print(f"processo:      {ID_PROCEDIMENTO}")
    print(f"docs OK:       {len(ok)}/{len(DOCS)}   falharam: {len(failed)}")
    print(f"total chars:   {total_chars}")
    print(f"total tokens:  {total_tokens}  (len/3.5, somado por doc)")
    for name, cut in CUTS.items():
        side = "ACIMA" if total_tokens > cut else "abaixo"
        print(f"  corte {name} ({cut}): {side}")
    print(f"classificacao: {classify(total_tokens)}")
    if failed:
        print("\nfalhas:")
        for e in failed:
            print(f"  {e['id_documento']} -> {e['status']}")
    print(f"\ngravado em: {OUT_DIR}")


def token_counter_of(entry: dict) -> int:
    """Tokens do doc pela regua do projeto, a partir do arquivo salvo (fonte da verdade)."""
    if not entry.get("file"):
        return token_counter("x" * entry["content_len"]) if entry["content_len"] else 0
    text = (OUT_DIR / entry["file"]).read_text(encoding="utf-8")
    return token_counter(text)


def _parse_docs(spec: str) -> list[tuple[str, bool]]:
    """Parseia "id:ocr,id:ocr" (ocr = 0/1) numa lista (id_documento, precisa_ocr)."""
    out: list[tuple[str, bool]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            doc_id, ocr = part.split(":", 1)
            out.append((doc_id.strip(), ocr.strip() in ("1", "true", "True", "ocr")))
        else:
            out.append((part, False))
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Mede tamanho real de um procedimento SEI."
    )
    parser.add_argument("--processo", default=ID_PROCEDIMENTO, help="id_procedimento")
    parser.add_argument(
        "--docs",
        default=None,
        help='lista "id:ocr,id:ocr" (ocr=0/1); vazio usa o default 14564832',
    )
    args = parser.parse_args()

    ID_PROCEDIMENTO = args.processo
    if args.docs:
        DOCS = _parse_docs(args.docs)
    OUT_DIR = EXPERIMENT_ROOT / "dataset" / "docs" / "candidatos" / ID_PROCEDIMENTO

    asyncio.run(main())

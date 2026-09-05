#!/usr/bin/env python
"""Compara latência (TTFC + total) entre /session_stream (novo) e /llm_lang/stream (clássico).

Mata qualquer server na porta, sobe um fresco (herda o env atual → permite testar
variantes de config via ASSISTENTE_*), dispara os DOIS endpoints no mesmo payload,
mede e imprime JSON. Sempre derruba o server no fim.

Uso:
    uv run python scripts/compare_endpoints.py --label baseline
    ASSISTENTE_REASONING_EFFORT=low uv run python scripts/compare_endpoints.py --label reasoning-low
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent


def _reexec_in_venv() -> None:
    venv_py = _APP_DIR / ".venv" / "bin" / "python"
    if not venv_py.exists():
        return
    try:
        if venv_py.resolve() == Path(sys.executable).resolve():
            return
    except OSError:
        return
    os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


_reexec_in_venv()

import httpx  # noqa: E402


def _app_up(health: str) -> bool:
    try:
        return httpx.get(health, timeout=2.0).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _kill_port(port: int) -> None:
    subprocess.run(
        ["pkill", "-f", f"uvicorn sei_ia.main:app --host 127.0.0.1 --port {port}"],
        check=False,
    )
    time.sleep(1.5)


def _start_server(port: int, health: str) -> subprocess.Popen | None:
    log_path = _APP_DIR / "logs" / "compare_server.log"
    log_path.parent.mkdir(exist_ok=True)
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "sei_ia.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(_APP_DIR),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 180
    while time.time() < deadline:
        if proc.poll() is not None:
            return None
        if _app_up(health):
            return proc
        time.sleep(1)
    return proc


def stream_endpoint(url: str, payload: dict, timeout: float) -> dict:
    t0 = time.perf_counter()
    ttfc = None
    chars = 0
    n_status = 0
    n_reasoning = 0
    err = None
    try:
        with httpx.stream("POST", url, json=payload, timeout=timeout) as resp:
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                frame = json.loads(line[6:])
                ft = frame.get("type")
                if ft == "status":
                    n_status += 1
                elif ft == "reasoning":
                    n_reasoning += 1
                elif ft == "content":
                    if ttfc is None:
                        ttfc = round(time.perf_counter() - t0, 2)
                    chars += len(frame.get("data", ""))
                elif ft == "error":
                    err = f"{frame.get('status_code')}: {frame.get('detail')}"
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    return {
        "ttfc_s": ttfc,
        "total_s": round(time.perf_counter() - t0, 2),
        "content_chars": chars,
        "status_frames": n_status,
        "reasoning_frames": n_reasoning,
        "error": err,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", default="scripts/request_example.json")
    ap.add_argument(
        "--text",
        default="Faça um resumo objetivo dos pontos principais deste processo e cite o documento-fonte de cada ponto.",
    )
    ap.add_argument("--port", type=int, default=8190)
    ap.add_argument("--timeout", type=float, default=480)
    ap.add_argument("--label", default="run")
    ap.add_argument("--websearch", action="store_true")
    args = ap.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    health = base + "/health"

    _kill_port(args.port)
    server = _start_server(args.port, health)
    if not _app_up(health):
        print(json.dumps({"label": args.label, "error": "app nao subiu"}))
        return 1

    with open(args.payload, encoding="utf-8") as fh:
        payload = json.load(fh)
    payload["text"] = args.text
    payload["use_websearch"] = args.websearch

    out = {"label": args.label, "text": args.text[:80], "websearch": args.websearch}
    print(f"[{args.label}] disparando /session_stream ...", file=sys.stderr, flush=True)
    out["session"] = stream_endpoint(
        base + "/llm_lang/session_stream", dict(payload), args.timeout
    )
    print(
        f"[{args.label}] disparando /llm_lang/stream ...", file=sys.stderr, flush=True
    )
    out["classic"] = stream_endpoint(
        base + "/llm_lang/stream", dict(payload), args.timeout
    )

    print("RESULT " + json.dumps(out, ensure_ascii=False))
    if server is not None:
        try:
            os.killpg(os.getpgid(server.pid), signal.SIGTERM)
        except Exception:  # noqa: BLE001
            server.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())

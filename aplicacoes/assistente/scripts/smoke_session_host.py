#!/usr/bin/env python
"""Dispara o /llm_lang/session_stream contra uma app e mostra tudo ao vivo.

Este é o modo host: sobe um uvicorn local quando necessário e depende de
endpoints acessíveis a partir do host. Para usar ``infra-litellm:4000`` e os
demais nomes internos do Compose, deixe a stack de pé e chame
``smoke_session_stack.sh``.

Para debug do comportamento. Se a app não estiver no ar, SOBE uma cópia local
(uvicorn), monta o .env a partir dos env files do monorepo se faltar, espera o
health e roda. Imprime a cronologia: cada frame SSE com timestamp relativo, o
conteúdo streamando como o usuário veria, a metadata, e o tempo total
call→return. No fim roda a verificação padrão via blob do checkpoint.

Exemplos (default --payload = scripts/request_example.json):
    uv run python scripts/smoke_session_host.py
    uv run python scripts/smoke_session_host.py --text "..." --no-cache --trace
    uv run python scripts/smoke_session_host.py --websearch --payload outro_req.json
    uv run python scripts/smoke_session_host.py --no-serve   # não sobe a app
    scripts/smoke_session_stack.sh --payload scripts/request_example.json

No ipython, os argumentos do script vêm DEPOIS de `--` (senão o ipython os captura):
    uv run ipython scripts/smoke_session_host.py -- --text "..." --no-cache --trace
O runner se re-executa no Python do .venv (py3.12) mesmo que o ipython do sistema
(py3.9) o tenha iniciado — não precisa instalar nada extra no ambiente do launcher.

Flags: --no-cache (força fresh + limpa Redis), --trace (loga tool calls no
terminal DA APP), --websearch (Bing), --no-serve (não sobe a app), --stop-server
(derruba no fim a app que o script subiu).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

_APP_DIR = Path(__file__).resolve().parent.parent
_NEEDLES = ["read_file", "grep", "task", "write_todos", "deep_research_search"]
_TRACE_FILE = _APP_DIR / "logs" / "session_trace.log"


def _reexec_in_venv() -> None:
    """Re-exec no Python do .venv (py3.12) se o launcher trouxe outro interpretador.

    `uv run ipython` pode cair no ipython do SISTEMA (py3.9) — e aí o subprocess do
    uvicorn (`No module named uvicorn`) e o blob-check (`No module named psycopg`)
    quebram, pois as deps vivem no .venv. Re-exec garante o interpretador certo
    para qualquer launcher (uv, python ou ipython do sistema).
    """
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

import httpx  # noqa: E402  (após o re-exec, garantidamente no .venv)


def _tail_trace(offset: int, stop: threading.Event) -> None:
    """Imprime ao vivo as novas linhas do log de trace da app (server-side)."""
    while not stop.is_set():
        try:
            if _TRACE_FILE.exists() and _TRACE_FILE.stat().st_size > offset:
                with open(_TRACE_FILE, encoding="utf-8") as fh:
                    fh.seek(offset)
                    chunk = fh.read()
                    offset = fh.tell()
                sys.stdout.write(chunk)
                sys.stdout.flush()
        except OSError:
            pass
        stop.wait(0.25)


def _render_markdown(text: str) -> None:
    """Re-exibe a resposta final consolidada, renderizada como Markdown no terminal.

    Abaixo do streaming bruto (chunk a chunk), mostra a resposta inteira já montada
    e FORMATADA (títulos, negrito, listas) via ``rich``. Funciona tanto sob IPython
    quanto sob python puro; se ``rich`` faltar, cai para texto puro.
    """
    text = text.strip()
    if not text:
        return
    print("\n" + "═" * 70 + "\n📄 resposta final (Markdown):\n", flush=True)
    try:
        from rich.console import Console
        from rich.markdown import Markdown

        Console().print(Markdown(text))
    except Exception:  # noqa: BLE001
        print(text, flush=True)


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--payload",
        default="scripts/request_example.json",
        help="JSON do request. Default: scripts/request_example.json",
    )
    ap.add_argument("--port", type=int, default=8190)
    ap.add_argument("--url", help="URL completa (sobrescreve --port)")
    ap.add_argument("--text", help="sobrescreve o texto da pergunta")
    ap.add_argument(
        "--no-cache", action="store_true", help="pula e limpa o cache Redis"
    )
    ap.add_argument(
        "--trace", action="store_true", help="loga tool calls no terminal da app"
    )
    ap.add_argument("--websearch", action="store_true", help="liga a busca web (Bing)")
    ap.add_argument(
        "--no-serve", action="store_true", help="não sobe a app se estiver fora"
    )
    ap.add_argument(
        "--stop-server", action="store_true", help="derruba no fim a app que subiu"
    )
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument(
        "--no-blob-check", action="store_true", help="pula a verificação via blob"
    )
    ap.add_argument(
        "--langfuse-trace-id",
        help="trace id explícito para correlacionar a chamada no Langfuse",
    )
    return ap.parse_args()


def _app_up(health_url: str) -> bool:
    try:
        return httpx.get(health_url, timeout=2.0).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _host_server_env() -> dict[str, str]:
    """Troca aliases exclusivos do Compose pelos equivalentes acessíveis no host."""
    env = os.environ.copy()
    assistant_url = env.get("ASSISTENTE_LITELLM_PROXY_URL", "")
    assistant_host = urlparse(assistant_url).hostname
    if assistant_host not in {None, "", "infra-litellm"}:
        return env

    host_url = env.get("LITELLM_PROXY_URL", "")
    host_name = urlparse(host_url).hostname
    if host_name in {None, "", "infra-litellm"}:
        return env

    # LITELLM_{STANDARD,MINI,NANO}_MODEL já são lidos direto pelo app (sem
    # prefixo ASSISTENTE_, sem indireção de rótulo — ver settings_config.py);
    # só o proxy URL/key precisam do alias ASSISTENTE_ pra virar acessível do
    # host.
    aliases = {
        "ASSISTENTE_LITELLM_PROXY_URL": "LITELLM_PROXY_URL",
        "ASSISTENTE_LITELLM_PROXY_API_KEY": "LITELLM_PROXY_API_KEY",
    }
    for assistant_name, host_name in aliases.items():
        if value := env.get(host_name):
            env[assistant_name] = value
    return env


def _ensure_env() -> None:
    """Monta o .env da app combinando os env files do monorepo, se faltar."""
    env_path = _APP_DIR / ".env"
    if env_path.exists():
        return
    monorepo = _APP_DIR.parent.parent
    chunks = []
    for name in ("default.env", "security.env", ".env"):
        src = monorepo / name
        if src.exists():
            chunks.append(src.read_text(encoding="utf-8"))
    sessions = _APP_DIR / "tmp_session"
    chunks.append(f"\nASSISTENTE_SESSIONS_ROOT={sessions}\n")
    env_fd = os.open(
        env_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(env_fd, "w", encoding="utf-8") as env_file:
        env_file.write("\n".join(chunks))
    env_path.chmod(0o600)
    print(f"… .env montado a partir do monorepo em {env_path}", flush=True)


def _start_server(port: int, health_url: str) -> subprocess.Popen | None:
    """Sobe a app (uvicorn, detached) e espera o health. Devolve o processo."""
    _ensure_env()
    log_path = _APP_DIR / "logs" / "runner_server.log"
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
        env=_host_server_env(),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print(f"… subindo a app (pid {proc.pid}, log {log_path}) …", end="", flush=True)
    deadline = time.time() + 180
    while time.time() < deadline:
        if proc.poll() is not None:
            print(
                f"\n❌ a app encerrou (exit {proc.returncode}). Veja {log_path}",
                flush=True,
            )
            return None
        if _app_up(health_url):
            print(" no ar ✅", flush=True)
            return proc
        print(".", end="", flush=True)
        time.sleep(1)
    print(f"\n❌ timeout subindo a app. Veja {log_path}", flush=True)
    return proc


def _missing_terminal_frames(meta: dict | None, saw_end: bool) -> list[str]:
    terminal_frames = {"metadata": meta is not None, "end": saw_end}
    return [name for name, present in terminal_frames.items() if not present]


def _stream(
    url: str,
    payload: dict,
    timeout: float,
    t0: float,
    langfuse_trace_id: str | None,
) -> tuple[list[str], dict | None, bool]:
    def rel() -> str:
        return f"+{time.perf_counter() - t0:6.2f}s"

    answer: list[str] = []
    meta: dict | None = None
    first_content: float | None = None
    stream_failed = False
    saw_end = False
    headers = {"X-Langfuse-Trace-Id": langfuse_trace_id} if langfuse_trace_id else None
    with httpx.stream(
        "POST", url, json=payload, headers=headers, timeout=timeout
    ) as resp:
        stream_failed = resp.status_code != 200
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            frame = json.loads(line[6:])
            ftype = frame.get("type")
            if ftype == "status":
                print(f"\n[{rel()}] ⚙  status:{frame['data']}", flush=True)
            elif ftype == "reasoning":
                print(f"\n[{rel()}] 🧠 {frame['data']}", flush=True)
            elif ftype == "content":
                if first_content is None:
                    first_content = time.perf_counter() - t0
                    print(f"\n[{rel()}] 💬 resposta (streaming):\n", flush=True)
                sys.stdout.write(frame["data"])
                sys.stdout.flush()
                answer.append(frame["data"])
            elif ftype == "metadata":
                meta = frame["data"]
                print(
                    f"\n\n[{rel()}] 📊 metadata: {json.dumps(meta, ensure_ascii=False)}",
                    flush=True,
                )
            elif ftype == "end":
                saw_end = True
                print(f"[{rel()}] ✅ end", flush=True)
            elif ftype == "error":
                stream_failed = True
                print(
                    f"\n[{rel()}] ❌ error {frame.get('status_code')}: {frame.get('detail')}",
                    flush=True,
                )
    missing_terminal_frames = _missing_terminal_frames(meta, saw_end)
    if missing_terminal_frames:
        stream_failed = True
        print(
            f"\n[{rel()}] ❌ SSE incompleto: ausente "
            f"{', '.join(missing_terminal_frames)}",
            flush=True,
        )
    if first_content is not None:
        print(f"[ttfc] time-to-first-content: {first_content:.2f}s", flush=True)
    return answer, meta, stream_failed


def main() -> int:
    args = _parse_args()
    url = args.url or f"http://127.0.0.1:{args.port}/llm_lang/session_stream"
    health = url.rsplit("/llm_lang", 1)[0] + "/health"

    with open(args.payload, encoding="utf-8") as fh:
        payload = json.load(fh)
    if args.text:
        payload["text"] = args.text
    payload["no_cache"] = args.no_cache or payload.get("no_cache", False)
    payload["trace"] = args.trace or payload.get("trace", False)
    payload["use_websearch"] = args.websearch or payload.get("use_websearch", False)

    server: subprocess.Popen | None = None
    if not _app_up(health):
        if args.no_serve:
            print(
                f"App não está no ar em {url}.\n"
                f"Rode sem --no-serve para subir automaticamente, ou:\n"
                f"  cd {_APP_DIR} && uv run uvicorn sei_ia.main:app "
                f"--host 127.0.0.1 --port {args.port}",
                file=sys.stderr,
            )
            return 1
        server = _start_server(args.port, health)
        if not _app_up(health):
            return 1

    n_docs = sum(
        len(p.get("id_documentos", [])) for p in payload.get("id_procedimentos", [])
    )
    t0 = time.perf_counter()
    print(
        f"[+  0.00s] POST {url}\n"
        f"          docs={n_docs} no_cache={payload['no_cache']} "
        f"trace={payload['trace']} websearch={payload['use_websearch']}\n"
        f"          langfuse_trace_id={args.langfuse_trace_id or 'auto'}\n"
        f"          pergunta: {payload.get('text', '')[:160]}\n" + "-" * 70,
        flush=True,
    )

    # Tailha o log de trace da app (server-side) ao vivo, interleaved.
    trace_stop: threading.Event | None = None
    if payload["trace"]:
        offset = _TRACE_FILE.stat().st_size if _TRACE_FILE.exists() else 0
        trace_stop = threading.Event()
        threading.Thread(
            target=_tail_trace, args=(offset, trace_stop), daemon=True
        ).start()

    answer, meta, stream_failed = _stream(
        url, payload, args.timeout, t0, args.langfuse_trace_id
    )

    if trace_stop is not None:
        time.sleep(0.6)  # deixa o tail drenar as últimas linhas
        trace_stop.set()

    total = time.perf_counter() - t0
    print(
        "-" * 70 + f"\n[+{total:6.2f}s] TOTAL call→return: {total:.2f}s | "
        f"resposta: {len(''.join(answer))} chars",
        flush=True,
    )

    # Abaixo do streaming: a resposta final inteira, formatada como Markdown.
    _render_markdown("".join(answer))

    if not args.no_blob_check and meta and meta.get("session_key"):
        try:
            from sei_ia.services.session_fs.debug import checkpoint_blob_counts

            counts = checkpoint_blob_counts(meta["session_key"], _NEEDLES)
            linha = " ".join(f"{k}={v}" for k, v in counts.items())
            print(f"[blob-check] thread={meta['session_key']} | {linha}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[blob-check] indisponível: {type(exc).__name__}: {exc}", flush=True)

    if server is not None:
        if args.stop_server:
            server.terminate()
            print(f"[server] app (pid {server.pid}) derrubada.", flush=True)
        else:
            print(
                f"[server] app continua rodando (pid {server.pid}); "
                f"pare com: kill {server.pid}",
                flush=True,
            )
    return 1 if stream_failed else 0


if __name__ == "__main__":
    sys.exit(main())

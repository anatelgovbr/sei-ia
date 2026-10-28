import json
import time

import pytest

from scripts.smoke_session_host import _ensure_env, _host_server_env, _stream


def _set_physical_litellm_models(monkeypatch):
    monkeypatch.setenv("LITELLM_STANDARD_MODEL", "provider/standard-physical")
    monkeypatch.setenv("LITELLM_MINI_MODEL", "provider/mini-physical")
    monkeypatch.setenv("LITELLM_NANO_MODEL", "provider/nano-physical")


def _clear_proxy_environment(monkeypatch):
    for variable in (
        "ASSISTENTE_LITELLM_PROXY_URL",
        "ASSISTENTE_LITELLM_PROXY_API_KEY",
        "LITELLM_PROXY_URL",
        "LITELLM_PROXY_API_KEY",
        "LITELLM_STANDARD_API_BASE",
        "LITELLM_STANDARD_API_KEY",
    ):
        monkeypatch.delenv(variable, raising=False)


def test_session_local_e2e_usa_proxy_em_vez_de_credenciais_do_provider(monkeypatch):
    """A readiness não pode enviar a chave do proxy ao upstream físico."""
    import scripts.session_local_e2e as session_module

    _clear_proxy_environment(monkeypatch)
    _set_physical_litellm_models(monkeypatch)
    monkeypatch.setenv("LITELLM_STANDARD_API_BASE", "https://provider.invalid")
    monkeypatch.setenv("LITELLM_STANDARD_API_KEY", "provider-key")
    monkeypatch.setenv("LITELLM_PROXY_URL", "https://proxy.invalid")
    monkeypatch.setenv("LITELLM_PROXY_API_KEY", "proxy-key")
    requests = []

    class ReadyResponse:
        def raise_for_status(self):
            return None

    def fake_get(url, *, headers, timeout):
        requests.append((url, headers, timeout))
        return ReadyResponse()

    monkeypatch.setattr(session_module.httpx, "get", fake_get)

    result = session_module.configure_real_llm_environment()

    assert requests == [
        (
            "https://proxy.invalid/health/readiness",
            {"Authorization": "Bearer proxy-key"},
            10,
        )
    ]
    assert result["source"] == "LITELLM_PROXY_URL"
    assert result["model_aliases"] == {
        "STANDARD_MODEL": "provider/standard-physical",
        "MINI_MODEL": "provider/mini-physical",
        "NANO_MODEL": "provider/nano-physical",
    }
    assert session_module.os.environ["ASSISTENTE_LITELLM_PROXY_URL"] == (
        "https://proxy.invalid"
    )
    assert session_module.os.environ["ASSISTENTE_LITELLM_PROXY_API_KEY"] == "proxy-key"


def test_session_local_e2e_aceita_par_assistente_do_proxy(monkeypatch):
    import scripts.session_local_e2e as session_module

    _clear_proxy_environment(monkeypatch)
    _set_physical_litellm_models(monkeypatch)
    monkeypatch.setenv(
        "ASSISTENTE_LITELLM_PROXY_URL", "https://assistente-proxy.invalid"
    )
    monkeypatch.setenv("ASSISTENTE_LITELLM_PROXY_API_KEY", "assistente-proxy-key")
    requests = []

    class ReadyResponse:
        def raise_for_status(self):
            return None

    def fake_get(url, *, headers, timeout):
        requests.append((url, headers, timeout))
        return ReadyResponse()

    monkeypatch.setattr(session_module.httpx, "get", fake_get)

    result = session_module.configure_real_llm_environment()

    assert requests == [
        (
            "https://assistente-proxy.invalid/health/readiness",
            {"Authorization": "Bearer assistente-proxy-key"},
            10,
        )
    ]
    assert result["source"] == "ASSISTENTE_LITELLM_PROXY_URL"


def test_session_local_e2e_rejeita_credenciais_somente_do_provider(monkeypatch):
    import scripts.session_local_e2e as session_module

    _clear_proxy_environment(monkeypatch)
    _set_physical_litellm_models(monkeypatch)
    monkeypatch.setenv("LITELLM_STANDARD_API_BASE", "https://provider.invalid")
    monkeypatch.setenv("LITELLM_STANDARD_API_KEY", "provider-key")

    def unexpected_request(*_args, **_kwargs):
        pytest.fail("não deve consultar o upstream do provider")

    monkeypatch.setattr(session_module.httpx, "get", unexpected_request)

    with pytest.raises(RuntimeError, match="ASSISTENTE_LITELLM_PROXY_URL") as exc_info:
        session_module.configure_real_llm_environment()

    assert "provider.invalid" not in str(exc_info.value)
    assert "LITELLM_STANDARD_API" not in str(exc_info.value)


def test_ensure_env_materializa_arquivo_com_permissao_privada(
    tmp_path, monkeypatch, capsys
):
    import scripts.smoke_session_host as smoke_module

    app_dir = tmp_path / "aplicacoes" / "assistente"
    app_dir.mkdir(parents=True)
    (tmp_path / "security.env").write_text(
        "LITELLM_PROXY_API_KEY=nao-imprimir\n", encoding="utf-8"
    )
    monkeypatch.setattr(smoke_module, "_APP_DIR", app_dir)

    _ensure_env()

    env_path = app_dir / ".env"
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert "nao-imprimir" in env_path.read_text(encoding="utf-8")
    assert "nao-imprimir" not in capsys.readouterr().out


def test_host_server_env_substitui_configuracao_exclusiva_do_compose(monkeypatch):
    monkeypatch.setenv("ASSISTENTE_LITELLM_PROXY_URL", "http://infra-litellm:4000")
    monkeypatch.setenv("ASSISTENTE_LITELLM_PROXY_API_KEY", "container-key")
    monkeypatch.setenv("LITELLM_PROXY_URL", "https://proxy-host.example.test")
    monkeypatch.setenv("LITELLM_PROXY_API_KEY", "host-key")
    # LITELLM_{STANDARD,MINI,NANO}_MODEL já são lidos direto pelo app (sem
    # indireção ASSISTENTE_*_MODEL_NAME) — só precisam sobreviver ao
    # os.environ.copy(), não passar pelo dict `aliases`.
    monkeypatch.setenv("LITELLM_STANDARD_MODEL", "host-standard")
    monkeypatch.setenv("LITELLM_MINI_MODEL", "host-mini")
    monkeypatch.setenv("LITELLM_NANO_MODEL", "host-nano")

    env = _host_server_env()

    assert env["ASSISTENTE_LITELLM_PROXY_URL"] == "https://proxy-host.example.test"
    assert env["ASSISTENTE_LITELLM_PROXY_API_KEY"] == "host-key"
    assert env["LITELLM_STANDARD_MODEL"] == "host-standard"
    assert env["LITELLM_MINI_MODEL"] == "host-mini"
    assert env["LITELLM_NANO_MODEL"] == "host-nano"


def test_host_server_env_preserva_proxy_host_explicito(monkeypatch):
    monkeypatch.setenv(
        "ASSISTENTE_LITELLM_PROXY_URL", "https://explicit-host.example.test"
    )
    monkeypatch.setenv("LITELLM_STANDARD_MODEL", "explicit-standard")
    monkeypatch.setenv("LITELLM_PROXY_URL", "https://fallback-host.example.test")

    env = _host_server_env()

    assert env["ASSISTENTE_LITELLM_PROXY_URL"] == "https://explicit-host.example.test"
    assert env["LITELLM_STANDARD_MODEL"] == "explicit-standard"


def test_session_local_e2e_importa_helpers_do_smoke_atual():
    import importlib

    module = importlib.import_module("scripts.session_local_e2e")

    assert callable(module.load_worktree_envs)
    assert callable(module.install_local_smoke_stubs)
    assert callable(module.make_app)


def test_stream_sinaliza_erro_sse(monkeypatch, capsys):
    import scripts.smoke_session_host as smoke_module

    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_lines(self):
            yield "data: " + json.dumps(
                {"type": "error", "status_code": 500, "detail": "falha"}
            )

    monkeypatch.setattr(
        smoke_module.httpx,
        "stream",
        lambda *args, **kwargs: FakeResponse(),
    )

    answer, meta, failed = _stream(
        "http://example.test/llm_lang/session_stream",
        {},
        1.0,
        time.perf_counter(),
        None,
    )

    assert answer == []
    assert meta is None
    assert failed is True
    assert "error 500" in capsys.readouterr().out


def test_stream_sucesso_exige_metadata_e_end(monkeypatch):
    import scripts.smoke_session_host as smoke_module

    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_lines(self):
            yield "data: " + json.dumps({"type": "content", "data": "ok"})
            yield "data: " + json.dumps(
                {"type": "metadata", "data": {"session_key": "session-1"}}
            )
            yield "data: " + json.dumps({"type": "end"})

    monkeypatch.setattr(
        smoke_module.httpx,
        "stream",
        lambda *args, **kwargs: FakeResponse(),
    )

    answer, meta, failed = _stream(
        "http://example.test/llm_lang/session_stream",
        {},
        1.0,
        time.perf_counter(),
        None,
    )

    assert answer == ["ok"]
    assert meta == {"session_key": "session-1"}
    assert failed is False


def test_stream_terminal_com_error_falha_mesmo_completo(monkeypatch):
    import scripts.smoke_session_host as smoke_module

    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_lines(self):
            yield "data: " + json.dumps(
                {"type": "metadata", "data": {"session_key": "session-1"}}
            )
            yield "data: " + json.dumps({"type": "end"})
            yield "data: " + json.dumps(
                {"type": "error", "status_code": 500, "detail": "falha"}
            )

    monkeypatch.setattr(
        smoke_module.httpx,
        "stream",
        lambda *args, **kwargs: FakeResponse(),
    )

    answer, meta, failed = _stream(
        "http://example.test/llm_lang/session_stream",
        {},
        1.0,
        time.perf_counter(),
        None,
    )

    assert answer == []
    assert meta == {"session_key": "session-1"}
    assert failed is True


def test_stream_incompleto_sem_metadata_ou_end_falha(monkeypatch, capsys):
    import scripts.smoke_session_host as smoke_module

    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_lines(self):
            yield "data: " + json.dumps({"type": "content", "data": "parcial"})

    monkeypatch.setattr(
        smoke_module.httpx,
        "stream",
        lambda *args, **kwargs: FakeResponse(),
    )

    answer, meta, failed = _stream(
        "http://example.test/llm_lang/session_stream",
        {},
        1.0,
        time.perf_counter(),
        None,
    )

    assert answer == ["parcial"]
    assert meta is None
    assert failed is True
    output = capsys.readouterr().out
    assert "ausente metadata, end" in output

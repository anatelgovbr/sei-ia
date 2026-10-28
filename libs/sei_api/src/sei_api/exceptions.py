from __future__ import annotations

import contextlib
import re


class SeiApiError(Exception):
    """Erro ao falar com a API do SEI.

    Sanitiza o ``IdentificacaoServico`` (token) de qualquer mensagem antes de
    expô-la, para que ele não vaze em traceback ou log.
    """

    _SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"([?&]IdentificacaoServico=)[^&\s]+"), r"\1<anonimizado>"),
    )

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")

    @classmethod
    def _sanitize(cls, value: object) -> str:
        text = str(value)
        for pattern, repl in cls._SENSITIVE_PATTERNS:
            text = pattern.sub(repl, text)
        return text

    @classmethod
    def from_source_exc(
        cls,
        src_exc: BaseException,
        status_code: int,
        prefix: str = "",
    ) -> SeiApiError:
        """Constrói o erro mutando a exceção de origem para anonimizar o token.

        Sanitiza ``src_exc.args`` in-place e tenta sanitizar ``.url`` em
        ``request``/``response`` quando existem. Em objetos imutáveis (e.g.
        ``httpx.Request.url``) cai fora silenciosamente; o filtro global de
        logging cobre como rede de proteção.
        """
        if src_exc.args:
            src_exc.args = tuple(
                cls._sanitize(a) if isinstance(a, str) else a for a in src_exc.args
            )
        for attr in ("request", "response"):
            owner = None
            with contextlib.suppress(AttributeError, RuntimeError):
                owner = getattr(src_exc, attr, None)
            if owner is None:
                continue
            url = getattr(owner, "url", None)
            if url is None:
                continue
            with contextlib.suppress(AttributeError, TypeError):
                owner.url = cls._sanitize(url)
        detail = f"{prefix}{cls._sanitize(src_exc)}"
        return cls(status_code=status_code, detail=detail)


class SeiApiUnavailableError(Exception):
    """A API do SEI respondeu como indisponível no healthcheck."""

    def __init__(self, detail: str = "API do SEI indisponível"):
        self.detail = detail
        super().__init__(detail)


class SeiApiTimeoutError(SeiApiError):
    """Timeout esgotando o limite de tentativas. Default quando o app não injeta um próprio."""

    def __init__(self, document_id: str = "unknown"):
        super().__init__(
            status_code=412,
            detail=f"Timeout da API SEI ao consultar documento {document_id}",
        )

"""Modulo de configuracao do logger."""

import logging
import re
import sys
import traceback
from logging.config import dictConfig
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from sei_ia.configs.settings_config import settings

LOG_DIRECTORY = Path("logs")
LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)

# Configuração para rotação de logs
LOG_FILENAME = str(LOG_DIRECTORY / "app.log")
BACKUP_COUNT = 7  # Mantém logs por 7 dias


# Padrões sensíveis aplicados globalmente em qualquer record que passe pelo
# logging. Pré-compilados na importação para amortizar o custo em logs de
# alto volume (urllib3 DEBUG, por exemplo).
_SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"([?&]IdentificacaoServico=)[^&\s]+"), r"\1<anonimizado>"),
)


def _scrub(text: str) -> str:
    for pattern, repl in _SENSITIVE_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def _scrub_args(args: object) -> object:
    if isinstance(args, tuple):
        return tuple(_scrub(a) if isinstance(a, str) else a for a in args)
    if isinstance(args, dict):
        return {k: _scrub(v) if isinstance(v, str) else v for k, v in args.items()}
    return args


def _scrub_exc_text(record: logging.LogRecord) -> None:
    """Pre-popula e sanitiza `record.exc_text`.

    `exc_text` é cache populado por `Formatter.format()` na primeira renderização.
    Se rodarmos depois do 1º handler formatar, perdemos o stdout cru. Renderizando
    o traceback aqui mesmo (antes do dispatch), todo handler vê a versão já limpa
    via cache. Pré-renderizar tem custo só em records com `exc_info`, que são raros.
    """
    if record.exc_info and not record.exc_text:
        record.exc_text = "".join(traceback.format_exception(*record.exc_info))
    if record.exc_text:
        record.exc_text = _scrub(record.exc_text)


class SensitiveDataFilter(logging.Filter):
    """Sanitiza dados sensíveis em records que passam pelos handlers.

    Roda em todo record visto por um handler que tenha esse filtro instalado.
    Defesa de cinto-e-suspensórios: mesmo trabalho que o LogRecordFactory faz
    na origem, repetido aqui para cobrir paths que criem `LogRecord` diretamente
    (sem passar pelo factory).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)
        if record.args:
            record.args = _scrub_args(record.args)
        _scrub_exc_text(record)
        return True


_FACTORY_INSTALLED = False


def _install_sanitizing_record_factory() -> None:
    """Instala um LogRecordFactory global que sanitiza msg/args na criação.

    Filtros em loggers pai não rodam para records propagados, e o handler do
    pytest `caplog` não compartilha nossos filtros. O factory roda em todo
    record criado em qualquer logger do processo — captura urllib3 DEBUG,
    httpx, langfuse e qualquer logger futuro sem precisar tocar no config.
    """
    global _FACTORY_INSTALLED
    if _FACTORY_INSTALLED:
        return
    base_factory = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = base_factory(*args, **kwargs)
        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)
        if record.args:
            record.args = _scrub_args(record.args)
        # Pré-renderiza exc_text aqui (antes de qualquer handler/formatter),
        # senão o 1º handler vê exc_text=None, o filter não scrubba, e o
        # Formatter popula raw no record (vazando no stdout). Os handlers
        # seguintes leem o cache já limpo, mas o 1º já saiu sujo.
        if record.exc_info and not record.exc_text:
            record.exc_text = _scrub(
                "".join(traceback.format_exception(*record.exc_info))
            )
        return record

    logging.setLogRecordFactory(factory)
    _FACTORY_INSTALLED = True


class TimedRotatingFileHandlerWithHeader(TimedRotatingFileHandler):
    """Handler personalizado para adicionar cabeçalho em novos arquivos de log."""

    def do_rollover(self) -> None:
        """Executado quando ocorre a rotação do arquivo."""
        super().doRollover()


logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "sensitive_data": {
            "()": "sei_ia.configs.logging_config.SensitiveDataFilter",
        },
    },
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(asctime)s.%(msecs)03d %(levelprefix)s [%(filename)s:%(lineno)d] - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "gunicorn": {
            "format": "%(asctime)s.%(msecs)03d %(levelname)s [%(filename)s:%(lineno)d] - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "filters": ["sensitive_data"],
        },
        "file": {
            "formatter": "default",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": LOG_FILENAME,
            "when": "midnight",  # Rotação diária à meia-noite
            "interval": 1,  # Intervalo de 1 dia
            "backupCount": BACKUP_COUNT,  # Mantém logs por X dias
            "encoding": "utf-8",
            "filters": ["sensitive_data"],
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default", "file"], "level": f"{settings.LOG_LEVEL}"},
        "uvicorn.access": {
            "handlers": ["default", "file"],
            "level": f"{settings.LOG_LEVEL}",
            "propagate": False,
        },
        "gunicorn.access": {
            "handlers": ["default", "file"],
            "level": f"{settings.LOG_LEVEL}",
            "formatter": "gunicorn",
            "propagate": False,
        },
        "": {"handlers": ["default", "file"], "level": f"{settings.LOG_LEVEL}"},
        "langfuse": {
            "handlers": ["default", "file"],
            "level": "ERROR",
            "propagate": False,
        },
        "opentelemetry": {
            "handlers": ["default", "file"],
            "level": "ERROR",
            "propagate": False,
        },
        "httpcore": {
            "handlers": ["default", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "httpx": {
            "handlers": ["default", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "openai": {
            "handlers": ["default", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "LiteLLM": {
            "handlers": ["default", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "litellm": {
            "handlers": ["default", "file"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}


def setup_logging() -> None:
    """Logger configs."""
    _install_sanitizing_record_factory()
    dictConfig(logging_config)

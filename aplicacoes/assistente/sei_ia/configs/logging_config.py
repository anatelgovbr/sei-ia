"""Modulo de configuracao do logger."""

import sys
from logging.config import dictConfig
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from sei_ia.configs.settings_config import settings

LOG_DIRECTORY = Path("logs")
if not LOG_DIRECTORY.exists():
    LOG_DIRECTORY.mkdir(parents=True)

# Configuração para rotação de logs
LOG_FILENAME = str(LOG_DIRECTORY / "app.log")
BACKUP_COUNT = 7  # Mantém logs por 7 dias


class TimedRotatingFileHandlerWithHeader(TimedRotatingFileHandler):
    """Handler personalizado para adicionar cabeçalho em novos arquivos de log."""

    def do_rollover(self) -> None:
        """Executado quando ocorre a rotação do arquivo."""
        super().doRollover()


logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
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
        },
        "file": {
            "formatter": "default",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": LOG_FILENAME,
            "when": "midnight",  # Rotação diária à meia-noite
            "interval": 1,  # Intervalo de 1 dia
            "backupCount": BACKUP_COUNT,  # Mantém logs por X dias
            "encoding": "utf-8",
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
    dictConfig(logging_config)

"""Modulo de configuracoes do gunicorn."""

from sei_ia.configs.settings_config import settings

bind = f"0.0.0.0:{settings.PORT}"
workers = settings.WORKERS
worker_class = "uvicorn.workers.UvicornWorker"

loglevel = settings.LOG_LEVEL
accesslog = "-"
errorlog = "-"

logger_class = "gunicorn.glogging.Logger"

timeout = settings.TIMEOUT_API
graceful_timeout = settings.TIMEOUT_API
keepalive = settings.KEEPALIVE
max_requests = settings.MAX_REQUESTS
max_requests_jitter = settings.MAX_REQUESTS_JITTER

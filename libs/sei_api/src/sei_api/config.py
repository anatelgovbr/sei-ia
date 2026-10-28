from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeiApiConfig:
    """Configuração de uma conexão com a API do SEI.

    Substitui os env globais que cada app lia direto (``settings.SEI_API_DB_*``,
    ``VERIFY_SSL``). Cada app constrói uma instância a partir do seu próprio
    ambiente e injeta no cliente.
    """

    base_url: str
    sigla_sistema: str
    identificacao_servico: str
    verify_ssl: bool = True
    timeout_s: int = 30
    max_retries: int = 5
    backoff_initial_wait: float = 1.0
    retry_backoff_factor: float = 2.0
    max_concurrency: int = 10
    chunk_size: int = 50

"""Async LLM Pool module for managing asynchronous requests to LLMs using OpenAI API."""

from __future__ import annotations

import logging
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    import types

    from openai import AsyncOpenAI

from sei_ia.data.database.db_instances import app_db_instance
from sei_ia.services.async_llm_requests.async_requests import process_requests

logger = logging.getLogger(__name__)


class AsyncLLMPool(ABC):
    """Pool de requisições assíncronas para o LLM usando OpenAI API."""

    def __init__(self, llm_params: dict[str, Any], async_client: AsyncOpenAI) -> None:
        """Inicializa o pool de LLM com parâmetros e cliente assíncrono."""
        self.llm_params: dict[str, Any] = llm_params
        self.async_client: AsyncOpenAI = async_client
        self.request_file: tempfile.NamedTemporaryFile | None = None
        self.result_file: tempfile.NamedTemporaryFile | None = None

    def __enter__(self) -> Self:
        """Context manager initialization for temp files."""
        self.request_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=".jsonl", prefix="llm_requests_"
        )
        self.result_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=".jsonl", prefix="llm_results_"
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Cleanup resources on context exit."""
        for path in (self.request_file, self.result_file):
            if path:
                try:
                    Path(path.name).unlink(missing_ok=True)
                except OSError as e:
                    logger.warning(f"Error cleaning temp file: {e!s}")

    async def run_requests(self) -> tuple[dict[str, Any], int, int]:
        """Execute all queued requests assincronamente e retorna resultados."""
        await process_requests(
            requests_filepath=self.request_file.name,
            save_filepath=self.result_file.name,
            api_endpoint="chat/completions",
            llm_client=self.async_client,
            db=app_db_instance,
        )
        return self.process_results()

    @abstractmethod
    def prepare_request(
        self, prompt: str, system_prompt: str, metadata: dict[str, Any]
    ) -> None:
        """Prepare uma requisição para ser adicionada ao pool."""

    @abstractmethod
    def process_results(self) -> tuple[dict[str, Any], int, int]:
        """Parse e organiza resultados do batch (implementado pelas subclasses)."""

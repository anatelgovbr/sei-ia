"""Configura o worker."""  # noqa: INP001

from typing import Any, ClassVar

from uvicorn.workers import UvicornWorker


class CustomUvicornWorker(UvicornWorker):
    """Classe que configura o worker."""

    CONFIG_KWARGS: ClassVar[dict[str, Any]] = {"loop": "asyncio"}

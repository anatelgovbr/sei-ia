"""Wrapper para StreamWriter que processa tags durante o streaming."""

import logging
from typing import Any

from langgraph.types import StreamWriter

from sei_ia.agents.rag.stream_processor_v2 import StreamTagProcessorV2
from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState

setup_logging()
logger = logging.getLogger(__name__)


class StreamWriterWithTagProcessor:
    """Wrapper para StreamWriter que processa tags antes de escrever."""

    def __init__(
        self, original_writer: StreamWriter, user_state: UserState | None = None
    ):
        """Inicializa o wrapper.

        Args:
            original_writer: Writer original do LangGraph
            user_state: Estado do usuário para processar tags (opcional)
        """
        self.original_writer = original_writer
        self.processor = None

        # Cria processador se tivermos user_state e RAG ativo
        if user_state and user_state.get("doc_rag"):
            self.processor = StreamTagProcessorV2(user_state)
            logger.debug("StreamWriterWrapper: Processador de tags ativado para RAG")

    def __call__(self, content: Any) -> None:
        """Processa e escreve conteúdo.

        Args:
            content: Conteúdo a escrever
        """
        if self.processor and isinstance(content, str):
            # Processa token por token através do processador
            output = self.processor.process_token(content)
            if output:
                self.original_writer(output)
        else:
            # Sem processador ou conteúdo não é string, escreve direto
            self.original_writer(content)

    def flush(self) -> None:
        """Flush de conteúdo pendente."""
        if self.processor:
            remaining = self.processor.flush()
            if remaining:
                self.original_writer(remaining)

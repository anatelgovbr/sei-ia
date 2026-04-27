"""Modulo da classe embedding generator."""

import json
import logging
import tempfile
from pathlib import Path

from pydantic import BaseModel

from sei_ia.configs.settings_config import settings
from sei_ia.data.database.db_instances import app_db_instance
from sei_ia.services.async_llm_requests.api_requests_from_file import (
    append_to_jsonl,
    get_last_jsonl_line,
)
from sei_ia.services.async_llm_requests.async_requests import process_requests
from sei_ia.services.embedder.providers.azure import AzureOpenAIEmbeddingProvider

logger = logging.getLogger(__name__)

SEPARATORS = [
    "\n\n",
    "\n",
    ".",
    ",",
    "\u200b",
    "\uff0c",
    "\u3001",
    "\uff0e",
    "\u3002",
    "",
]


class InputPoolEmbd(BaseModel):
    """Classe para representar a entrada de um input na pool."""

    input_texts: list[str]
    doc_id: str
    chunk_ids: list[int]
    positions: list[tuple[int, int]]


class EmbeddingGenerator:
    """Classe para gerar embeddings de textos via LiteLLM Proxy."""

    def __init__(self) -> None:
        """Inicializa a classe.

        Sempre usa o LiteLLM Proxy para embeddings. O proxy gerencia
        a conexão com Azure OpenAI automaticamente.
        """
        # Sempre usa proxy LiteLLM
        # O AzureOpenAIEmbeddingProvider detecta automaticamente que é proxy
        # pela URL (não contém "openai.azure.com")
        self.provider = AzureOpenAIEmbeddingProvider(
            api_key=settings.LITELLM_PROXY_API_KEY or "dummy-key",
            endpoint=settings.LITELLM_PROXY_URL,
            model=settings.LITELLM_EMBEDDING_MODEL_NAME,
            encoding_name=settings.EMBEDDING_ENCODING_NAME,  # Encoding configurável
        )

    def generate(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings para uma lista de textos."""
        return self.provider.generate_embeddings(texts)

    def apply_tokenizer(self, texts: list[str]) -> list[list[int]]:
        """Aplica o tokenizador para uma lista de textos."""
        return self.provider.apply_tokenizer(texts)

    def create_temp_files(self) -> tuple[Path, Path]:
        """Cria e retorna arquivos temporários únicos para uma operação."""
        with (
            tempfile.NamedTemporaryFile(
                delete=False, suffix=".jsonl", prefix="pool_"
            ) as tmp_req,
            tempfile.NamedTemporaryFile(
                delete=False, suffix=".jsonl", prefix="pool_result_"
            ) as tmp_save,
        ):
            return Path(tmp_req.name), Path(tmp_save.name)

    async def async_generate_from_pool(
        self, req_filepath: str, save_filepath: str
    ) -> None:
        """Versão assíncrona para executar requisições a partir de um arquivo de pool jsonl.

        Args:
            req_filepath (str): Caminho para o arquivo de requisições.
            save_filepath (str): Caminho para o arquivo de resultados.
        """
        await process_requests(
            requests_filepath=req_filepath,
            save_filepath=save_filepath,
            api_endpoint="embeddings",
            llm_client=self.provider.async_client,
            db=app_db_instance,
        )

        logger.info("Requisições finalizadas com sucesso.")

    def append_pool_file(self, pool_input: InputPoolEmbd, req_filepath: Path) -> None:
        """Adiciona um item ao arquivo de pool de requisições.

        Args:
            pool_input (InputPoolEmbd): Entrada para adicionar ao pool.
            req_filepath (str): Caminho para o arquivo de pool de requisições

        """
        count_context_size = 0
        doc_ids, chunk_ids, positions, input_texts = [], [], [], []
        tokenizer = self.provider.get_tokenizer()
        max_context_size = self.provider.max_context_size

        last_line = get_last_jsonl_line(req_filepath)
        if last_line:
            entry = json.loads(last_line)
            doc_ids = entry["doc_ids"]
            chunk_ids = entry["chunk_ids"]
            positions = entry["positions"]
            input_texts = entry["input_texts"]
            count_context_size = entry["count_context_size"]

        for idx, text in enumerate(pool_input.input_texts):
            context_size = len(tokenizer.encode(text))
            if context_size + count_context_size <= max_context_size:
                doc_ids.append(pool_input.doc_id)
                input_texts.append(text)
                chunk_ids.append(pool_input.chunk_ids[idx])
                positions.append(pool_input.positions[idx])
                count_context_size += context_size
            else:
                item = {
                    "doc_ids": doc_ids,
                    "chunk_ids": chunk_ids,
                    "positions": positions,
                    "input_texts": input_texts,
                    "count_context_size": count_context_size,
                }
                append_to_jsonl(item, req_filepath)
                count_context_size = context_size
                doc_ids = [pool_input.doc_id]
                input_texts = [text]
                chunk_ids = [pool_input.chunk_ids[idx]]
                positions = [pool_input.positions[idx]]

        item = {
            "doc_ids": doc_ids,
            "chunk_ids": chunk_ids,
            "positions": positions,
            "input_texts": input_texts,
            "count_context_size": count_context_size,
        }
        append_to_jsonl(item, req_filepath)

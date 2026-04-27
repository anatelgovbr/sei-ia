"""Modulo da classe embedding generator."""

import json
import logging
import tempfile
from pathlib import Path

from pydantic import BaseModel

from jobs.envs import (
    EMBEDDING_BASE_MODEL,
    LITELLM_MODEL_NAME,
    LITELLM_PROXY_URL,
)
from jobs.services.embedder.providers.litellm import LiteLLMEmbeddingProvider

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
    """Classe para gerar embeddings de textos."""

    def __init__(self) -> None:
        """Inicializa a classe."""
        self.provider = LiteLLMEmbeddingProvider(
            base_url=LITELLM_PROXY_URL,
            model=LITELLM_MODEL_NAME,
            base_model=EMBEDDING_BASE_MODEL,
            api_key=None,
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


def append_to_jsonl(data: dict, filepath: Path) -> None:
    """Adiciona uma linha JSON a um arquivo JSONL."""
    with filepath.open("a") as f:
        f.write(json.dumps(data) + "\n")


def get_last_jsonl_line(filepath: Path) -> str | None:
    """Retorna a última linha de um arquivo JSONL."""
    if not filepath.exists() or filepath.stat().st_size == 0:
        return None
    with filepath.open("r") as f:
        lines = f.readlines()
        return lines[-1].strip() if lines else None

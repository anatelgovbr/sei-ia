"""Testes comportamentais do contrato de roteamento de embeddings do ETL."""

import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_embedding_request_alias_is_separate_from_physical_table_identity():
    """Roteia por ``embedding`` e preserva o pin físico da tabela."""
    child_code = dedent(
        """
        import json
        from types import SimpleNamespace

        import jobs.services.embedder.providers.litellm as provider_module


        class FakeEmbeddings:
            def __init__(self):
                self.request = None

            def create(self, **kwargs):
                self.request = kwargs
                return SimpleNamespace(
                    data=[SimpleNamespace(embedding=[0.0] * 1536)]
                )


        class FakeOpenAI:
            last_embeddings = None

            def __init__(self, **kwargs):
                if type(self).last_embeddings is None:
                    type(self).last_embeddings = FakeEmbeddings()
                self.embeddings = type(self).last_embeddings


        provider_module.OpenAI = FakeOpenAI
        provider_module.AsyncOpenAI = FakeOpenAI

        from jobs.db_models.embedding import EmbeddingsTable
        from jobs.services.embedder.embedding_generator import EmbeddingGenerator

        generator = EmbeddingGenerator()
        result = generator.generate(["texto"])
        request = FakeOpenAI.last_embeddings.request
        table = EmbeddingsTable.__table__
        print(
            json.dumps(
                {
                    "model": request["model"],
                    "table": table.name,
                    "dimension": table.c.embedding.type.dim,
                    "result_dimension": len(result[0]),
                }
            )
        )
        """
    )
    child_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "ENVIRONMENT": "test",
        "EMBEDDING_MODEL": "provider/embedding-physical",
        "EMBEDDING_BASE_MODEL": "provider/embedding-physical",
        "EMBEDDING_DIM": "1536",
        "MAX_LENGTH_CHUNK_SIZE": "1512",
        "CHUNK_OVERLAP": "50",
        "LITELLM_PROXY_URL": "http://litellm.invalid",
    }

    completed = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=Path(__file__).resolve().parents[2],
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "model": "embedding",
        "table": "provider_embedding_physical_1512_50",
        "dimension": 1536,
        "result_dimension": 1536,
    }

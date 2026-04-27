"""Modelos de resposta."""

import logging
from dataclasses import dataclass
from datetime import datetime

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState
from sei_ia.services.llm_models.get_model import get_model_config

setup_logging()
logger = logging.getLogger(__name__)


@dataclass
class ModelResponse:
    """Classe para representar o modelo de resposta."""

    user_state: UserState
    response: dict
    model_output: str
    created: datetime
    n_tokens: dict

    def __init__(
        self,
        user_state: UserState,
    ) -> None:
        """Inicializa a instância da classe ModelResponse.

        Args:
            user_state (UserState): UserState
            response (dict): Resposta gerada pelo modelo
        """
        self.user_state = user_state
        self.response = user_state["response"]
        self.model_output = self.response["response"]
        self.created = datetime.now()  # noqa: DTZ005
        self.n_tokens = {
            "prompt_tokens": self.response["n_tokens"][0],
            "completion_tokens": self.response["n_tokens"][1],
            "total_tokens": self.response["n_tokens"][0] + self.response["n_tokens"][1],
        }
        self.id_message = self.user_state["id_request"]

    def to_dict(self) -> dict:
        """Converte a instância da classe em um dicionário.

        Returns:
            dict: Dicionário representando a instância da classe
        """
        # logger.debug(f"last_prompt: {self.user_state.get('last_prompt')}")
        configs_model_used = get_model_config(model_type=self.user_state["model_type"])
        return {
            "id": f"chatcmpl-{configs_model_used['model_name']}",
            "id_message": self.user_state["id_request"],
            "object": "chat.completion",
            "created": self.created,
            "model": configs_model_used["model_name"],
            "usage": self.n_tokens,
            "initial_config": {
                "messages": self.user_state["user_request"],
                "temperature": self.user_state["temperature"],
            },
            "choices": [
                {
                    "message": {"role": "assistant", "content": self.model_output},
                    "finish_reason": self.response.get("finish_reason", "stop"),
                    "index": 0,
                }
            ],
            "use_websearch": self.user_state["use_websearch"],
            "use_thinking": self.user_state["use_thinking"],
            "doc_paged": self.user_state["doc_paged"],
            "doc_summarized": self.user_state["doc_summarized"],
            "doc_rag": self.user_state["doc_rag"],
            "doc_false_rag": self.user_state["doc_false_rag"],
            "all_tokens_counter": self.user_state["all_tokens_counter"],
            "intent": self.user_state["intent"],
            "type_choiced_summary": self.response.get(
                "type_choiced_summary", "Not found"
            ),
            # Campos para RAG Enhanced
            "rag_method": self.user_state.get("rag_method"),
            "rag_documents_count": self.user_state.get("rag_documents_count"),
            "rag_chunks_count": self.user_state.get("rag_chunks_count"),
        }

    def persist_log_api(self) -> int:
        """Persiste o log da API e a ultima interacao. REMOVIDO - Logging para Solr desabilitado."""
        # Log para Solr removido - apenas retorna o id_request para compatibilidade
        return self.user_state["id_request"]


@dataclass
class ModelResponseWithMetadata:
    """Classe para representar o modelo de resposta."""

    user_state: UserState
    response: dict
    model_output: str
    created: datetime
    n_tokens: dict

    def __init__(
        self,
        user_state: UserState,
    ) -> None:
        """Inicializa a instância da classe ModelResponse.

        Args:
            user_state (UserState): UserState
            response (dict): Resposta gerada pelo modelo
        """
        self.user_state = user_state
        self.response = user_state["response"]
        self.model_output = self.response["response"]
        self.created = datetime.now()  # noqa: DTZ005
        self.n_tokens = {
            "prompt_tokens": self.response["n_tokens"][0],
            "completion_tokens": self.response["n_tokens"][1],
            "total_tokens": self.response["n_tokens"][0] + self.response["n_tokens"][1],
        }
        self.id_message = self.user_state["id_request"]

    def to_dict(self) -> dict:
        """Converte a instância da classe em um dicionário.

        Returns:
            dict: Dicionário representando a instância da classe
        """
        configs_model_used = get_model_config(model_type=self.user_state["model_type"])
        result = {
            "id": f"chatcmpl-{configs_model_used['model_name']}",
            "id_message": self.user_state["id_request"],
            # "object": "chat.completion",
            "created": self.created,
            # "model": configs_model_used["model_name"],
            "usage": self.n_tokens,
            "use_websearch": self.user_state["use_websearch"],
            "use_thinking": self.user_state["use_thinking"],
            "doc_paged": self.user_state["doc_paged"],
            "doc_summarized": self.user_state["doc_summarized"],
            "doc_rag": self.user_state["doc_rag"],
            "doc_false_rag": self.user_state["doc_false_rag"],
            "all_tokens_counter": self.user_state["all_tokens_counter"],
            "intent": self.user_state["intent"],
            # Campos para RAG Enhanced
            "rag_method": self.user_state.get("rag_method"),
            "rag_documents_count": self.user_state.get("rag_documents_count"),
            "rag_chunks_count": self.user_state.get("rag_chunks_count"),
        }

        # Adiciona reasoning se disponível (para modelos de thinking)
        if self.response.get("reasoning"):
            result["reasoning"] = self.response["reasoning"]

        return result

    def persist_log_api(self) -> int:
        """Persiste o log da API e a ultima interacao. REMOVIDO - Logging para Solr desabilitado."""
        # Log para Solr removido - apenas retorna o id_request para compatibilidade
        return self.user_state["id_request"]

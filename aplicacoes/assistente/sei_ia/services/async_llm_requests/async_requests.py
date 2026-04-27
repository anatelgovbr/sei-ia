"""Módulo de requisições assíncronas para API com tratamento de rate limit e backoff.

Este módulo processa requisições a endpoints de API (embeddings e chat/completions)
utilizando retry com backoff exponencial e respeitando limites de requisições.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import backoff
import httpx
import openai
import tiktoken
from openai import AsyncOpenAI

from sei_ia.configs.settings_config import settings
from sei_ia.data.database.async_db_connection import AsyncDbConnector

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Exceção levantada quando o limite de requisições da API é atingido."""

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
        response: dict[str, Any] | None = None,
    ) -> None:
        """Inicializa a exceção.

        Args:
            message: Mensagem de erro.
            retry_after: Tempo (em segundos) para retry, se fornecido.
            response: Resposta completa da API.
        """
        super().__init__(message)
        self.retry_after: float | None = retry_after
        self.response: dict[str, Any] | None = response

    @classmethod
    def from_response(
        cls: type["RateLimitError"], response: dict[str, Any]
    ) -> "RateLimitError":
        """Cria uma RateLimitError a partir de uma resposta da API.

        Args:
            response: Resposta da API.

        Returns:
            Instância de RateLimitError.
        """
        retry_after = response.get("retry_after") or response.get("headers", {}).get(
            "retry-after"
        )
        if isinstance(retry_after, str):
            try:
                retry_after = float(retry_after)
            except ValueError:
                retry_after = None
        return cls(
            str(response.get("message", "Rate limit exceeded")), retry_after, response
        )


_endpoint_gate_state: dict[str, float] = {}


async def on_backoff(details: dict[str, Any]) -> None:
    """Callback para eventos de backoff.

    Atualiza o status do gateway no banco de dados e espera o tempo necessário.

    Args:
        details: Informações do evento de backoff.
    """
    api_instance: APIRequest = details["args"][0]
    db: AsyncDbConnector = api_instance.db
    llm_client = api_instance.llm_client
    endpoint_key = f"{llm_client.base_url}{api_instance.api_endpoint}"

    await db.update_gateway_status(endpoint=endpoint_key, is_open=False)

    exc = details.get("exception")
    wait_time = details.get("wait", 0.0)
    tries = details.get("tries", 1)

    # Caso seja RateLimitError com retry_after especificado
    if isinstance(exc, RateLimitError) and exc.retry_after:
        wait_time = float(exc.retry_after)
        logger.info(
            f"Aguardando {wait_time}s conforme especificado pela API (rate limit)"
        )
    # Caso seja timeout, usa backoff exponencial
    elif isinstance(
        exc,
        openai.APITimeoutError
        | httpx.TimeoutException
        | httpx.ConnectTimeout
        | httpx.ReadTimeout,
    ):
        logger.warning(f"Timeout detectado (tentativa {tries}): {exc!s}")
        # wait_time já vem calculado pelo backoff.expo

    blocked_until = time.time() + wait_time if wait_time else time.time()
    _endpoint_gate_state[endpoint_key] = blocked_until

    if wait_time:
        await asyncio.sleep(wait_time)

    await db.update_gateway_status(endpoint=endpoint_key, is_open=True)
    logger.info(
        f"Gateway reaberto para {endpoint_key} após período de backoff ({wait_time:.2f}s)"
    )


@dataclass
class StatusTracker:
    """Acompanha o status das requisições."""

    num_tasks_started: int = 0
    num_tasks_in_progress: int = 0
    num_tasks_succeeded: int = 0
    num_tasks_failed: int = 0
    time_of_last_request: float = 0.0


@dataclass
class APIRequest:
    """Representa uma requisição à API com suporte a retry e controle de rate limit."""

    task_id: int
    request_json: dict[str, Any]
    token_consumption: int
    attempts_left: int
    llm_client: AsyncOpenAI
    api_endpoint: str
    metadata: dict[str, Any] | None = None
    result: list[Any] = field(default_factory=list)
    db: AsyncDbConnector | None = None

    async def _check_rate_limit(self, status: StatusTracker) -> None:
        """Verifica e impõe o rate limit.

        Args:
            status: O objeto que rastreia o status das requisições.
        """
        now = time.time()
        if status.time_of_last_request > 0:
            time_since_last = now - status.time_of_last_request
            if time_since_last < (1.0 / settings.REQUESTS_PER_SECOND):
                sleep_time = (1.0 / settings.REQUESTS_PER_SECOND) - time_since_last
                await asyncio.sleep(sleep_time)
        status.time_of_last_request = time.time()

    @backoff.on_exception(
        backoff.expo,
        (
            RateLimitError,
            openai.APITimeoutError,
            httpx.TimeoutException,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
        ),
        max_tries=settings.BACKOFF_MAX_TRIES,
        max_time=settings.BACKOFF_MAX_TIME,
        base=settings.BACKOFF_INITIAL_WAIT,
        on_backoff=on_backoff,
        raise_on_giveup=True,
        logger=logger,
    )
    async def call_api(  # noqa: C901
        self,
        session: httpx.AsyncClient,
        llm_client: AsyncOpenAI,
        api_endpoint: str,
        db: AsyncDbConnector,
        save_path: Path,
        status: StatusTracker,
    ) -> tuple[bool, float | None]:
        """Executa a requisição à API com retries automáticos e controle de rate limit.

        Args:
            session: Sessão HTTP assíncrona.
            llm_client: Cliente da API assíncrona.
            api_endpoint: Endpoint da API a ser chamado.
            db: Conexão assíncrona com o banco de dados.
            save_path: Caminho para salvar os resultados.
            status: StatusTracker para controle de requisições.

        Returns:
            Uma tupla contendo (True, None) em caso de sucesso.
        """

        def _raise_rate_limit_error(
            err: Exception,
            retry_after: float | None,
            headers: dict[str, str] | None,
            response_data: str | None,
        ) -> None:
            """Função interna para levantar RateLimitError evitando mensagens longas em f-string."""
            msg = str(err)
            raise RateLimitError(
                msg, retry_after, {"headers": headers, "data": response_data}
            ) from None

        try:
            endpoint_key = f"{llm_client.base_url}{api_endpoint}"

            # VERIFICAÇÃO DO GATEWAY DESATIVADA
            # blocked_until = _endpoint_gate_state.get(endpoint_key, 0.0)
            # now = time.time()
            # if blocked_until > now:
            #     sleep_time = blocked_until - now
            #     logger.debug(
            #         "Aguardando %ss para reabrir gateway local do endpoint %s",
            #         round(sleep_time, 2),
            #         endpoint_key,
            #     )
            #     await asyncio.sleep(sleep_time)

            await self._check_rate_limit(status)
            llm_client.http_client = session

            if "embeddings" in api_endpoint:
                response = await llm_client.embeddings.create(
                    input=self.request_json["input_texts"],
                    model=self.request_json.get(
                        "model", settings.LITELLM_EMBEDDING_MODEL_NAME
                    ),
                )
                response_data = [item.embedding for item in response.data]
            elif "chat/completions" in api_endpoint:
                response = await llm_client.chat.completions.create(
                    messages=self.request_json["messages"],
                    model=self.request_json["model"],
                    temperature=self.request_json.get("temperature", 0),
                    max_tokens=self.request_json.get("max_tokens", 4096),
                )
                response_data = response.choices[0].message.content
            else:
                raise ValueError("Endpoint não suportado: " + api_endpoint)  # noqa: TRY301

            result = {
                "request": self.request_json,
                "response": response_data,
                "metadata": self.metadata,
            }
            append_to_jsonl(result, save_path)
            status.num_tasks_succeeded += 1
            status.num_tasks_in_progress -= 1

            logger.debug(f"Requisição {self.task_id} concluída com sucesso")
            await db.update_gateway_status(endpoint=endpoint_key, is_open=True)
            return True, None  # noqa: TRY300

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Requisição {self.task_id} falhou: {error_msg}")

            # Tratamento de timeouts - relança a exceção para o decorador backoff
            if isinstance(
                e,
                openai.APITimeoutError
                | httpx.TimeoutException
                | httpx.ConnectTimeout
                | httpx.ReadTimeout,
            ):
                logger.warning(f"Timeout na requisição {self.task_id}: {error_msg}")
                status.num_tasks_in_progress -= 1
                raise  # Relança para o backoff decorator fazer retry

            # Tratamento de rate limit
            if "rate limit" in error_msg.lower() or "429" in error_msg:
                retry_after: int | float | None = None
                response_data = None
                headers: dict[str, Any] = {}

                if (
                    isinstance(e, (httpx.HTTPStatusError) | (openai.RateLimitError))
                    and getattr(e, "response", None) is not None
                ):
                    headers = dict(e.response.headers)
                    retry_after = headers.get("retry-after")

                    if retry_after:
                        try:
                            retry_after_int = int(retry_after)
                        except ValueError:
                            retry_after_int = None
                        else:
                            retry_after = retry_after_int
                            logger.info(
                                f"A API solicitou espera de {retry_after}s devido ao rate limit"
                            )
                            await asyncio.sleep(retry_after)

                _raise_rate_limit_error(e, retry_after, headers, response_data)

            # Outros erros não recuperáveis
            status.num_tasks_failed += 1
            status.num_tasks_in_progress -= 1
            logger.exception(
                f"Requisição {self.task_id} falhou com erro: {error_msg}",
                extra={
                    "error": e,
                    "retry_after": retry_after if "retry_after" in locals() else None,
                },
            )
            raise e from None


async def process_requests(
    requests_filepath: Path,
    save_filepath: Path,
    api_endpoint: str,
    llm_client: AsyncOpenAI,
    db: AsyncDbConnector,
    token_encoding_name: str = "o200k_base",  # noqa: S107
) -> None:
    """Processa as requisições a partir de um arquivo jsonl e salva os resultados.

    Args:
        requests_filepath: Caminho do arquivo com as requisições (jsonl).
        save_filepath: Caminho para salvar as respostas (jsonl).
        api_endpoint: Endpoint da API a ser chamado.
        llm_client: Cliente assíncrono da API.
        db: Conexão com o banco de dados.
        token_encoding_name: Nome da codificação de tokens a ser utilizada.
    """
    token_encoding = tiktoken.get_encoding(token_encoding_name)
    status = StatusTracker()
    await db.connect()
    await db.initialize_gateway_table()

    # Configura timeout para o cliente HTTP
    http_timeout = httpx.Timeout(
        connect=30.0, read=settings.TIMEOUT_API, write=30.0, pool=10.0
    )

    async with httpx.AsyncClient(timeout=http_timeout) as session:
        store_req: list[APIRequest] = []
        with Path(requests_filepath).open("r") as file:
            for task_id, line in enumerate(file, 1):
                try:
                    request_json = json.loads(line)
                    req = APIRequest(
                        task_id=task_id,
                        request_json=request_json,
                        token_consumption=calculate_token_usage(
                            request_json, api_endpoint, token_encoding
                        ),
                        attempts_left=settings.MAX_RETRIES,
                        metadata=request_json.pop("metadata", None),
                        db=db,
                        llm_client=llm_client,
                        api_endpoint=api_endpoint,
                    )
                    store_req.append(req)
                    status.num_tasks_started += 1
                    status.num_tasks_in_progress += 1
                except json.JSONDecodeError as e:
                    logger.exception(f"JSON inválido na linha {task_id}: {e}")  # noqa: TRY401
                    status.num_tasks_failed += 1

        semaphore = asyncio.Semaphore(settings.EMBEDDINGS_MAX_CONCURRENCY)

        async def bounded_call(
            request: APIRequest,
        ) -> tuple[bool, float | None] | Exception:
            async with semaphore:
                return await request.call_api(
                    session=session,
                    llm_client=llm_client,
                    api_endpoint=api_endpoint,
                    db=db,
                    save_path=save_filepath,
                    status=status,
                )

        tasks = [bounded_call(r) for r in store_req]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                status.num_tasks_failed += 1
                logger.error(f"Task failed with error: {result!s}")

    logger.info(f"Processamento concluído. Resultados salvos em {save_filepath}")
    logger.info(
        f"Tarefas: {status.num_tasks_succeeded} concluídas, {status.num_tasks_failed} falharam"
    )

    await db.close()


def append_to_jsonl(data: dict[str, Any], filepath: str) -> None:
    """Anexa os dados no formato JSON a um arquivo jsonl.

    Args:
        data: Dicionário com os dados a serem salvos.
        filepath: Caminho do arquivo onde os dados serão anexados.
    """
    with Path(filepath).open("a") as f:
        f.write(json.dumps(data) + "\n")


def calculate_token_usage(
    request_json: dict[str, Any], endpoint: str, encoding: tiktoken.Encoding
) -> int:
    """Calcula o consumo de tokens para diferentes endpoints da API.

    Args:
        request_json: Dicionário com a requisição.
        endpoint: Endpoint utilizado na requisição.
        encoding: Codificação de tokens a ser utilizada.

    Returns:
        Número de tokens consumidos.

    Raises:
        ValueError: Se o endpoint não for suportado para contagem de tokens.
    """
    if "embeddings" in endpoint:
        inputs = request_json.get("input_texts", [])
        if isinstance(inputs, str):
            return len(encoding.encode(inputs))
        return sum(len(encoding.encode(text)) for text in inputs)

    if "chat" in endpoint:
        messages = request_json.get("messages", [])
        tokens = 0
        for msg in messages:
            tokens += len(encoding.encode(msg.get("content", ""))) + 4
        return tokens + 2

    msg = "Endpoint não suportado para contagem de tokens: " + endpoint
    raise ValueError(msg)

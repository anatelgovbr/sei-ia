"""API REQUEST PARALLEL PROCESSOR - OpenAI CookBook.

Using the OpenAI API to process lots of text quickly takes some care.
If you trickle in a million API requests one by one, they'll take days to complete.
If you flood a million API requests in parallel, they'll exceed the rate limits and fail with errors.
To maximize throughput, parallel requests need to be throttled to stay under rate limits.

This script parallelizes requests to the OpenAI API while throttling to stay under rate limits.

Features:
- Streams requests from file, to avoid running out of memory for giant jobs
- Makes requests concurrently, to maximize throughput
- Throttles request and token usage, to stay under rate limits
- Retries failed requests up to {max_attempts} times, to avoid missing data
- Logs errors, to diagnose problems with requests


Inputs:
- requests_filepath : str
    - path to the file containing the requests to be processed
    - file should be a jsonl file, where each line is a json object with API parameters and an optional metadata field
    - e.g., {"model": "text-embedding-3-small", "input": "embed me", "metadata": {"row_id": 1}}
    - as with all jsonl files, take care that newlines in the content are properly escaped
      (json.dumps does this automatically)
    - an example file is provided at examples/data/example_requests_to_parallel_process.jsonl
    - the code to generate the example file is appended to the bottom of this script
- save_filepath : str, optional
    - path to the file where the results will be saved
    - file will be a jsonl file, where each line is an array with the original request plus the API response
    - e.g., [{"model": "text-embedding-3-small", "input": "embed me"}, {...}]
    - if omitted, results will be saved to {requests_filename}_results.jsonl
- api_endpoint: str, optional
    - Type of API endpoint to call
    - if omitted, will default to embeddings
- max_requests_per_minute : float, optional
    - target number of requests to make per minute (will make less if limited by tokens)
    - leave headroom by setting this to 50% or 75% of your limit
    - if requests are limiting you, try batching multiple embeddings or completions into one request
    - if omitted, will default to 1,500
- max_tokens_per_minute : float, optional
    - target number of tokens to use per minute (will use less if limited by requests)
    - leave headroom by setting this to 50% or 75% of your limit
    - if omitted, will default to 125,000
- token_encoding_name : str, optional
    - name of the token encoding used, as defined in the `tiktoken` package
    - if omitted, will default to "o200k_base" (used by `text-embedding-3-small`)
- max_attempts : int, optional
    - number of times to retry a failed request before giving up
    - if omitted, will default to 5
- logging_level : int, optional
    - level of logging to use; higher numbers will log fewer messages
    - 40 = ERROR; will log only when requests fail after all retries
    - 30 = WARNING; will log when requests his rate limits or other errors
    - 20 = INFO; will log when requests start and the status at finish
    - 10 = DEBUG; will log various things as the loop runs to see when they occur
    - if omitted, will default to 20 (INFO).

The script is structured as follows:
    - Imports
    - Define main()
        - Initialize things
        - In main loop:
            - Get next request if one is not already waiting for capacity
            - Update available token & request capacity
            - If enough capacity available, call API
            - The loop pauses if a rate limit error is hit
            - The loop breaks when no tasks remain
    - Define dataclasses
        - StatusTracker (stores script metadata counters; only one instance is created)
        - APIRequest (stores API inputs, outputs, metadata; one method to call API)
    - Define functions
        - append_to_jsonl (writes to results file)
        - num_tokens_consumed_from_request (bigger function to infer token usage from request)
        - task_id_generator_function (yields 0, 1, 2, ...)
    - Run main()
"""

import asyncio
import json
import logging
import time
from dataclasses import (
    dataclass,
    field,
)
from pathlib import Path
from typing import NoReturn

import httpx
import tiktoken
from openai import AsyncOpenAI

from sei_ia.configs.settings_config import settings
from sei_ia.services.exceptions.http_exceptions import HTTPException500

logger = logging.getLogger(__name__)


def _raise_not_implemented(api_endpoint: str) -> NoReturn:
    msg = f"API endpoint '{api_endpoint}' not supported for this request."
    raise NotImplementedError(msg)


async def api_requests_from_file(  # noqa: C901, PLR0915
    requests_filepath: str,
    save_filepath: str,
    api_endpoint: str,
    max_requests_per_minute: float,
    max_tokens_per_minute: float,
    max_attempts: int,
    llm_async_client: AsyncOpenAI,
    token_encoding: tiktoken.core.Encoding,
) -> None:
    """Processes API requests from a file asynchronously, managing rate limits and retries.

    Args:
        requests_filepath (str): Path to the file containing API requests, one per line in JSON format.
        save_filepath (str): Path to the file where API responses and statuses will be saved.
        api_endpoint (str): The API endpoint to which requests will be sent.
        max_requests_per_minute (float): Maximum number of requests allowed per minute.
        max_tokens_per_minute (float): Maximum number of tokens allowed per minute.
        max_attempts (int): Maximum number of retry attempts for each request in case of failure.
        llm_async_client (AsyncOpenAI): Asynchronous client for making API requests.
        token_encoding (tiktoken.core.Encoding): Token encoding used to count tokens per request.

    Returns:
        None

    Raises:
        None directly, but logs errors and warnings for failed requests and rate limit issues.

    Notes:
        - Requests are processed in parallel, with throttling to stay under specified rate limits.
        - Retries are managed for failed requests up to `max_attempts`.
        - Status and errors are logged, and summary information is provided at the end of processing.
    """
    seconds_to_pause_after_rate_limit_error = 3
    seconds_to_sleep_each_loop = (
        0.01  # 1 ms limits max throughput to 1,000 requests per second
    )
    seconds_to_recover_after_rate_limit = 1

    # initialize trackers
    queue_of_requests_to_retry = asyncio.Queue()
    task_id_generator = (
        task_id_generator_function()
    )  # generates integer IDs of 0, 1, 2, ...
    status_tracker = (
        StatusTracker()
    )  # single instance to track a collection of variables
    next_request = None  # variable to hold the next request to call

    # initialize available capacity counts
    available_request_capacity = max_requests_per_minute
    available_token_capacity = max_tokens_per_minute
    last_update_time = time.time()

    # initialize flags
    file_not_finished = True  # after file is empty, we'll skip reading it
    logger.debug("Initialization complete.")

    # initialize file reading
    with Path(requests_filepath).open() as file:
        # `requests` will provide requests one at a time
        requests = file.__iter__()
        logger.debug("File opened. Entering main loop")
        async with httpx.AsyncClient() as session:  # Initialize ClientSession here
            while True:
                # get next request (if one is not already waiting for capacity)
                if next_request is None:
                    if not queue_of_requests_to_retry.empty():
                        next_request = queue_of_requests_to_retry.get_nowait()
                        logger.debug(
                            f"Retrying request {next_request.task_id}: {next_request}"
                        )
                    elif file_not_finished:
                        try:
                            # get new request
                            request_json = json.loads(next(requests))
                            next_request = APIRequest(
                                task_id=next(task_id_generator),
                                request_json=request_json,
                                token_consumption=num_tokens_consumed_from_request(
                                    request_json, api_endpoint, token_encoding
                                ),
                                attempts_left=max_attempts,
                                metadata=request_json.pop("metadata", None),
                            )
                            status_tracker.num_tasks_started += 1
                            status_tracker.num_tasks_in_progress += 1
                            logger.debug(
                                f"Reading request {next_request.task_id}: {next_request}"
                            )
                        except StopIteration:
                            # if file runs out, set flag to stop reading it
                            logger.debug("Read file exhausted")
                            file_not_finished = False

                # update available capacity
                current_time = time.time()
                seconds_since_update = current_time - last_update_time
                available_request_capacity = min(
                    available_request_capacity
                    + max_requests_per_minute
                    * seconds_since_update
                    / (seconds_to_recover_after_rate_limit * 60.0),
                    max_requests_per_minute,
                )
                available_token_capacity = min(
                    available_token_capacity
                    + max_tokens_per_minute
                    * seconds_since_update
                    / (seconds_to_recover_after_rate_limit * 60.0),
                    max_tokens_per_minute,
                )
                last_update_time = current_time

                # if enough capacity available, call API
                if next_request:
                    next_request_tokens = next_request.token_consumption
                    if (
                        available_request_capacity >= 1
                        and available_token_capacity >= next_request_tokens
                    ):
                        # update counters
                        available_request_capacity -= 1
                        available_token_capacity -= next_request_tokens
                        next_request.attempts_left -= 1

                        # call API
                        asyncio.create_task(  # noqa: RUF006
                            next_request.call_api(
                                session=session,
                                llm_async_client=llm_async_client,
                                api_endpoint=api_endpoint,
                                retry_queue=queue_of_requests_to_retry,
                                save_filepath=save_filepath,
                                status_tracker=status_tracker,
                            )
                        )
                        next_request = None  # reset next_request to empty

                # if all tasks are finished, break
                if status_tracker.num_tasks_in_progress == 0:
                    break

                # main loop sleeps briefly so concurrent tasks can run
                await asyncio.sleep(seconds_to_sleep_each_loop)

                # if a rate limit error was hit recently, pause to cool down
                seconds_since_rate_limit_error = (
                    time.time() - status_tracker.time_of_last_rate_limit_error
                )
                if (
                    seconds_since_rate_limit_error
                    < seconds_to_pause_after_rate_limit_error
                ):
                    remaining_seconds_to_pause = (
                        seconds_to_pause_after_rate_limit_error
                        - seconds_since_rate_limit_error
                    )
                    await asyncio.sleep(remaining_seconds_to_pause)
                    # ^e.g., if pause is 15 seconds and final limit was hit 5 seconds ago
                    ctime_value = (
                        status_tracker.time_of_last_rate_limit_error
                        + seconds_to_pause_after_rate_limit_error
                    )
                    msg = f"Pausing to cool down until {time.ctime(ctime_value)}"
                    logger.warning(msg)

        # after finishing, log final status
        logger.info(
            f"""Parallel processing complete. Results saved to {save_filepath}"""
        )
        msg = (
            f"{status_tracker.num_tasks_failed} / {status_tracker.num_tasks_started} requests failed. "
            f"Errors logged to {save_filepath}."
        )
        if status_tracker.num_tasks_failed > 0:
            logger.warning(msg)
        if status_tracker.num_rate_limit_errors > 0:
            logger.warning(
                f"{status_tracker.num_rate_limit_errors} rate limit errors received. Consider running at a lower rate."
            )


# dataclasses


@dataclass
class StatusTracker:
    """Stores metadata about the script's progress. Only one instance is created."""

    num_tasks_started: int = 0
    num_tasks_in_progress: int = 0  # script ends when this reaches 0
    num_tasks_succeeded: int = 0
    num_tasks_failed: int = 0
    num_rate_limit_errors: int = 0
    num_api_errors: int = 0  # excluding rate limit errors, counted above
    num_other_errors: int = 0
    time_of_last_rate_limit_error: int = 0  # used to cool off after hitting rate limits


@dataclass
class APIRequest:
    """Stores an API request's inputs, outputs, and other metadata. Contains a method to make an API call."""

    task_id: int
    request_json: dict
    token_consumption: int
    attempts_left: int
    metadata: dict
    result: list = field(default_factory=list)

    async def call_api(
        self,
        session: httpx.AsyncClient,
        api_endpoint: str,
        retry_queue: asyncio.Queue,
        save_filepath: str,
        status_tracker: StatusTracker,
        llm_async_client: AsyncOpenAI,
    ) -> None:
        """Calls the OpenAI API and saves results."""
        logger.info(f"Starting request #{self.task_id}")
        error = None
        llm_async_client.http_client = session
        try:
            if "embeddings" in api_endpoint:
                response = await llm_async_client.embeddings.create(
                    input=self.request_json["input_texts"],
                    model=settings.EMBEDDING_MODEL,
                )
                response_data = [item.embedding for item in response.data]

            elif "completions" in api_endpoint:
                # Handle chat completions
                if "chat" in api_endpoint:
                    response = await llm_async_client.chat.completions.create(
                        messages=self.request_json["messages"],
                        model=self.request_json["model"],
                        temperature=self.request_json.get("temperature", 0),
                        max_tokens=self.request_json.get("max_tokens", 4096),
                        top_p=self.request_json.get("top_p", 1),
                        frequency_penalty=self.request_json.get("frequency_penalty", 0),
                        presence_penalty=self.request_json.get("presence_penalty", 0),
                    )
                    response_data = response.choices[0].message.content

                # Handle regular completions
                else:
                    response = await llm_async_client.completions.create(
                        prompt=self.request_json["prompt"],
                        model=self.request_json["model"],
                        temperature=self.request_json.get("temperature", 0),
                        max_tokens=self.request_json.get("max_tokens", 4096),
                        top_p=self.request_json.get("top_p", 1),
                        frequency_penalty=self.request_json.get("frequency_penalty", 0),
                        presence_penalty=self.request_json.get("presence_penalty", 0),
                    )
                    response_data = response.choices[0].text

            else:
                _raise_not_implemented(api_endpoint)

        except httpx.HTTPError as e:
            logger.warning(f"Request {self.task_id} failed with HTTPError {e}")
            status_tracker.num_other_errors += 1
            error = e
        except NotImplementedError as e:
            logger.warning(
                f"Request {self.task_id} failed with NotImplementedError {e}"
            )
            status_tracker.num_other_errors += 1
            error = e
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(
                f"Request {self.task_id} failed with {type(e).__name__}: {e}"
            )
            status_tracker.num_other_errors += 1
            error = e

        if error:
            self.result.append(error)
            if self.attempts_left:
                retry_queue.put_nowait(self)
            else:
                logger.error(
                    f"Request {self.request_json} failed after all attempts. Saving errors: {self.result}"
                )
                status_tracker.num_tasks_in_progress -= 1
                status_tracker.num_tasks_failed += 1
                raise HTTPException500(detail=f"Error during API request: {error}")
        else:
            data = (
                [self.request_json, response_data, self.metadata]
                if self.metadata
                else [self.request_json, response_data]
            )
            append_to_jsonl(data, save_filepath)
            status_tracker.num_tasks_in_progress -= 1
            status_tracker.num_tasks_succeeded += 1
            logger.debug(f"Request {self.task_id} saved to {save_filepath}")


def append_to_jsonl(data: dict, filename: str) -> None:
    """Append a json payload to the end of a jsonl file."""
    json_string = json.dumps(data)
    with Path(filename).open("a") as f:
        f.write(json_string + "\n")


def num_tokens_consumed_from_request(  # noqa: C901
    request_json: dict,
    api_endpoint: str,
    token_encoding: tiktoken.core.Encoding,
) -> int:
    """Estimate the number of tokens consumed by an API request.

    Args:
        request_json (dict): The request parameters for the API.
        api_endpoint (str): The API endpoint being called.
        token_encoding (tiktoken.core.Encoding): The encoding used for token counting.

    Returns:
        int: Estimated number of tokens consumed by the request.

    Raises:
        TypeError: If the input type is not as expected.
        NotImplementedError: If the endpoint is not supported for token counting.
    """
    if api_endpoint.endswith("completions"):
        max_tokens = request_json.get("max_tokens", 15)
        n = request_json.get("n", 1)
        completion_tokens = n * max_tokens

        # chat completions
        if api_endpoint.startswith("chat/"):
            num_tokens = 0
            for message in request_json["messages"]:
                num_tokens += 4  # every message follows <im_start>{role/name}\n{content}<im_end>\n
                for key, value in message.items():
                    num_tokens += len(token_encoding.encode(value))
                    if key == "name":  # if there's a name, the role is omitted
                        num_tokens -= 1  # role is always required and always 1 token
            num_tokens += 2  # every reply is primed with <im_start>assistant
            return num_tokens + completion_tokens
        # normal completions
        prompt = request_json["prompt"]
        if isinstance(prompt, str):  # single prompt
            prompt_tokens = len(token_encoding.encode(prompt))
            return prompt_tokens + completion_tokens

        if isinstance(prompt, list):  # multiple prompts
            prompt_tokens = sum([len(token_encoding.encode(p)) for p in prompt])
            return prompt_tokens + completion_tokens * len(prompt)
        msg = 'Expecting either string or list of strings for "prompt" field in completion request'
        raise TypeError(msg)
    # if embeddings request, tokens = input tokens
    if api_endpoint == "embeddings":
        if isinstance(request_json["input_texts"], str):  # single input
            return len(token_encoding.encode(request_json["input_texts"]))
        if isinstance(request_json["input_texts"], list):  # multiple inputs
            return sum(
                [len(token_encoding.encode(i)) for i in request_json["input_texts"]]
            )
        msg = 'Expecting either string or list of strings for "inputs" field in embedding request'
        raise TypeError(msg)
    # more logic needed to support other API calls (e.g., edits, inserts, DALL-E)
    msg = f'API endpoint "{api_endpoint}" not supported for token counting'

    def _raise_not_implemented() -> NoReturn:
        raise NotImplementedError(msg)

    _raise_not_implemented()
    return None


def task_id_generator_function() -> int:
    """Generate an infinite sequence of integer task IDs starting from 0.

    Yields:
        int: The next integer in the sequence, starting from 0 and incrementing by 1 each time.
    """
    task_id = 0
    while True:
        yield task_id
        task_id += 1


def get_last_jsonl_line(filepath: Path) -> str:
    """Return the last non-empty line from a .jsonl file, ignoring any trailing newlines.

    Args:
        filepath (Path): Path to the .jsonl file.

    Returns:
        str: The last non-empty line as a string, or an empty string if the file is empty or contains only newlines.
    """
    with filepath.open("rb") as f:
        # 1) Vai para o final do arquivo
        f.seek(0, 2)  # 2 -> os.SEEK_END
        file_length = f.tell()

        # Se o arquivo está totalmente vazio, não há nada a ler
        if file_length == 0:
            return ""

        # 2) Mover para trás, pulando todos os '\n' do fim do arquivo
        pos = file_length - 1
        while pos >= 0:
            f.seek(pos, 0)  # 0 -> os.SEEK_SET
            if f.read(1) != b"\n":
                # Achamos um caractere que não é newline
                break
            pos -= 1

        # Se pos < 0 depois de pular newlines, significa que só havia quebras de linha
        if pos < 0:
            return ""

        # 3) A partir desse ponto, recuar até achar o início da linha (ou início do arquivo)
        while pos >= 0:
            f.seek(pos, 0)
            if f.read(1) == b"\n":
                # Assim que encontrar um newline, avançamos 1 byte para chegar no
                # primeiro char da última linha
                f.seek(pos + 1, 0)
                break
            pos -= 1

        # Se pos < 0, significa que não encontramos newline; então a linha começa no início
        if pos < 0:
            f.seek(0, 0)

        # Agora lemos a linha final
        return f.readline().decode("utf-8").rstrip("\n")

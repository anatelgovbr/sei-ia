"""funcs module."""

import logging
import re
import time
from urllib.parse import parse_qs, urlencode, urlparse

import numpy as np
import pandas as pd

from jobs.db_models.async_db_connection import AsyncDbConnector

logger = logging.getLogger(__name__)


def timing_decorator(func):
    """Decorator to measure the execution time of a function."""

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        logger.debug(f"{func.__name__} took {elapsed:.3f}s")
        return result

    return wrapper


def check_permitted_documents(row: pd.Series, permitted_dict: dict) -> bool:
    """Check if a document is allowed for a given process type."""
    id_type_process, id_type_document = (
        row["id_tipo_procedimento"],
        row["id_type_document"],
    )

    if str(id_type_document) in permitted_dict["default"]:
        return True

    permitted = permitted_dict.get(str(id_type_process), [])
    return str(id_type_document) in permitted


def chunker(seq: list, chunk_size: int) -> list:
    """Breaks a list into chunks of a specified size."""
    return [seq[pos : pos + chunk_size] for pos in range(0, len(seq), chunk_size)]


def is_not_nan(value) -> bool:
    # Check if all values in the array are NaN

    if isinstance(value, float) and np.isnan(value):
        return False
    if isinstance(value, np.ndarray):
        return not np.isnan(value).all()
    return True


def add_param_on_url_if_not_exists(url: str, param_name: str, param_value: str) -> str:
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    query_params[param_name] = [param_value]
    parsed_url = parsed_url._replace(query=urlencode(query_params, doseq=True))
    return parsed_url.geturl()


def regexp_replace(value: str):
    alphanumeric_and_accented_chars_pattern = r"[^0-9a-záéíóúàèìòùâêîôûãõç]+"
    return re.sub(alphanumeric_and_accented_chars_pattern, "", str(value.lower()))


def group_concat_distinct(series: pd.Series):
    """Concatena os elementos únicos de uma série de dados separando por vírgula."""
    unique_elements = set(series.astype(str))
    return ",".join(sorted(unique_elements, reverse=True))


def get_job_version_manager(db_connector: AsyncDbConnector) -> int:
    """Retorna o id da tabela version_manager referente ao repo Jobs.

    Returns:
        int: id da tabela version_manager
    """
    sql = """
        SELECT
            max(id) as id
        FROM version_register
        WHERE url LIKE '%/jobs.git%'
    """
    result = db_connector.execute_query_one(sql)
    return result["id"] if result else None

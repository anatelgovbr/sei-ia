"""Testes de containers Docker do healthchecker."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta

import docker
import pandas as pd

containers_names = [
    "etl-airflow-worker",
    "etl-airflow-scheduler",
    "etl-airflow-webserver",
    "etl-airflow-triggerer",
    "etl-airflow-api",
    "assistente",
    "gateway-nginx",
    "similaridade",
    "similaridade-feedback",
    "infra-solr",
    "infra-postgres",
    "infra-postgres-airflow",
    "infra-rabbitmq",
    "infra-redis",
    "infra-litellm",
    "infra-searxng",
    "infra-lightpanda",
    "infra-chrome",
    "infra-fastcrw",
    "infra-byparr",
    "infra-marker",
]

allowed_no_healthcheck: set[str] = set()
error_pattern = re.compile(
    r"\b(error|exception|traceback|fatal|failed|timeout)\b", re.I
)
bootstrap_grace_period = timedelta(seconds=120)
recent_log_window = timedelta(minutes=5)
monitored_log_services = set(containers_names) | {"etl-airflow-init"}


def _parse_container_started_at(container) -> datetime | None:
    started_at = container.attrs["State"]["StartedAt"]
    if started_at == "0001-01-01T00:00:00Z":
        return None
    normalized = started_at.replace("Z", "+00:00")
    if "." in normalized:
        timestamp_part, timezone_part = normalized.split("+", 1)
        head, fraction = timestamp_part.split(".", 1)
        normalized = f"{head}.{fraction[:6]}+{timezone_part}"
    return datetime.fromisoformat(normalized)


def _container_log_since(container) -> int:
    now = datetime.now().astimezone()
    started_at = _parse_container_started_at(container)
    if started_at is None:
        return int((now - recent_log_window).timestamp())

    window_start = max(started_at + bootstrap_grace_period, now - recent_log_window)
    return int(window_start.timestamp())


def _filter_known_benign_lines(container_name: str, log_lines: list[str]) -> list[str]:
    normalized_name = container_name.removeprefix("sei-ia-").removesuffix("-1")
    ignore_patterns: dict[str, list[re.Pattern[str]]] = {
        "assistente": [
            re.compile(r"UserWarning: Valid config keys have changed in V2", re.I),
            re.compile(r"'fields' has been removed", re.I),
        ],
        "infra-postgres": [
            re.compile(r"database system is ready to accept connections", re.I),
        ],
        "infra-postgres-airflow": [
            re.compile(r"database system is ready to accept connections", re.I),
        ],
        "infra-searxng": [
            re.compile(
                r"WARNING:searx\.(?:network|engines)\..*"
                r"(?:HTTP Request failed|ErrorContext)",
                re.I,
            ),
        ],
    }

    patterns = ignore_patterns.get(normalized_name, [])
    if not patterns:
        return log_lines

    return [
        line
        for line in log_lines
        if line and not any(pattern.search(line) for pattern in patterns)
    ]


def get_docker_logs(
    container_name: str, tail: int | None = None, verbose: bool = False
) -> list[str]:
    client = docker.from_env()
    container = client.containers.get(container_name)
    since = _container_log_since(container)
    raw_logs = (
        container.logs(tail=tail, since=since).decode("utf-8")
        if tail
        else container.logs(since=since).decode("utf-8")
    )
    log_lines = [line for line in raw_logs.split("\n") if line.strip()]
    log_lines = _filter_known_benign_lines(container_name, log_lines)
    if verbose:
        logging.info(
            "Container %s gerou %s linhas de log.", container_name, len(log_lines)
        )
    return log_lines


def get_all_docker_logs(
    container_status: dict, tail: int = 300, verbose: bool = False
) -> dict:
    logs_lines = {}
    for container_name, status in container_status.items():
        if status.get("Service") not in monitored_log_services:
            continue
        log_line = get_docker_logs(container_name, tail, verbose)
        logs_lines[container_name] = {
            "Linhas": len(log_line),
            "log_text": "\n".join(log_line),
        }
    return logs_lines


def report_docker_logs(logs_lines: dict, show_logs: bool = False) -> int:
    results_df = pd.DataFrame.from_dict(logs_lines, orient="index")
    results_df["contem_erro"] = results_df["log_text"].apply(
        lambda text: len(error_pattern.findall(text))
    )
    notcontainslog = results_df[results_df["Linhas"] < 3]
    containserror = results_df[results_df["contem_erro"] != 0]
    errors = 0

    if len(notcontainslog) > 0:
        logging.info(
            "\nExistem containers sem logs recentes apos a janela de bootstrap.\n"
        )
        logging.info(notcontainslog[["Linhas", "contem_erro"]].to_markdown())
    else:
        logging.info("\nTodos os containers possuem logs recentes suficientes.\n")

    if len(containserror) > 0:
        errors += int(containserror["contem_erro"].sum())
        logging.warning("\nExistem eventos recentes com palavras de erro nos logs.\n")
        logging.warning(containserror[["Linhas", "contem_erro"]].to_markdown())
        if show_logs:
            for row, line in containserror.iterrows():
                logging.info(
                    "\n##### LOG do container %s #####\n%s", row, line["log_text"]
                )
    else:
        logging.info("Nao foram encontrados erros nos logs monitorados.")
    return errors


def get_docker_containers(verbose: bool = False) -> dict:
    client = docker.from_env()
    containers = client.containers.list(all=True)
    container_status = {}

    for container in containers:
        name = str(container.name)
        labels = container.labels or {}
        if labels.get("com.docker.compose.project") != "sei-ia":
            continue

        start_time = container.attrs["State"]["StartedAt"]
        if start_time != "0001-01-01T00:00:00Z":
            start_time = datetime.fromisoformat(start_time[:23])
            if container.status == "running":
                uptime = datetime.now() - start_time
            else:
                finished_time = container.attrs["State"]["FinishedAt"]
                if finished_time != "0001-01-01T00:00:00Z":
                    finished_time = datetime.fromisoformat(finished_time[:23])
                    uptime = finished_time - start_time
                else:
                    uptime = "Indisponivel"
        else:
            uptime = "Indisponivel"

        container_status[name] = {
            "ID": container.short_id,
            "Service": labels.get("com.docker.compose.service", ""),
            "Status": container.status,
            "uptime": uptime,
            "RestartCount": int(container.attrs.get("RestartCount", 0)),
            "network": str(list(container.attrs["NetworkSettings"]["Networks"].keys()))[
                1:-1
            ],
        }
        container_status[name].update(container.attrs["State"])
        if verbose:
            logging.debug("Container %s status=%s", container.name, container.status)

    return container_status


def verify_status_docker(
    container_status: dict, containers_names: list[str], verbose: bool = False
) -> pd.DataFrame:
    data_df = pd.DataFrame.from_dict(container_status, orient="index")
    dfs = []
    if len(data_df) == 0:
        for container_name in containers_names:
            dfs.append(
                pd.DataFrame(
                    data={
                        "Nome": container_name,
                        "Service": container_name,
                        "Status": "Indisponivel",
                        "Health": "Indisponivel",
                        "Restarting": False,
                        "OOMKilled": False,
                        "RestartCount": 0,
                    },
                    index=[0],
                )
            )
    else:
        data_df["Health"] = data_df["Health"].apply(
            lambda x: x.get("Status") if isinstance(x, dict) else "Indisponivel"
        )
        data_df.reset_index(inplace=True)
        data_df.rename(columns={"index": "Nome"}, inplace=True)

        for container_name in containers_names:
            matched = data_df[data_df["Service"] == container_name]
            if not matched.empty:
                dfs.append(matched)
            else:
                if verbose:
                    logging.debug("Container %s nao encontrado.", container_name)
                dfs.append(
                    pd.DataFrame(
                        data={
                            "Nome": container_name,
                            "Service": container_name,
                            "Status": "Indisponivel",
                            "Health": "Indisponivel",
                            "Restarting": False,
                            "OOMKilled": False,
                            "RestartCount": 0,
                        },
                        index=[0],
                    )
                )
    return pd.concat(dfs, ignore_index=True).fillna(False)


def report_container_status(
    container_status_df: pd.DataFrame,
    return_dfs: bool = False,
    verbose: bool = False,
    path: str | None = None,
) -> tuple[int, dict]:
    if path:
        container_status_df.to_csv(path, index=False)

    not_running = container_status_df[container_status_df["Status"] != "running"]
    restarting = container_status_df[container_status_df["Restarting"]]
    unhealth = container_status_df[container_status_df["Health"] == "unhealthy"]
    health_unavailable = container_status_df[
        (container_status_df["Health"] == "Indisponivel")
        & (
            ~container_status_df["Nome"].apply(
                lambda name: any(token in name for token in allowed_no_healthcheck)
            )
        )
    ]
    oom_killed = container_status_df[container_status_df["OOMKilled"]]
    restarted = container_status_df[container_status_df["RestartCount"] > 0]

    errors = 0
    if len(not_running) > 0:
        errors += len(not_running)
        logging.error("\nExistem containers fora de running.\n")
        logging.error(not_running.to_markdown())
    else:
        logging.info("\nTodos os containers monitorados estao running.\n")

    if len(restarting) > 0:
        errors += len(restarting)
        logging.error("\nExistem containers reiniciando.\n")
        logging.error(restarting.to_markdown())
    else:
        logging.info("\nNenhum container esta reiniciando.\n")

    if len(unhealth) > 0:
        errors += len(unhealth)
        logging.error("\nExistem containers unhealthy.\n")
        logging.error(unhealth.to_markdown())
    else:
        logging.info("\nNenhum container esta unhealthy.\n")

    if len(health_unavailable) > 0:
        errors += len(health_unavailable)
        logging.error("\nExistem containers sem healthcheck onde isso era esperado.\n")
        logging.error(health_unavailable.to_markdown())
    else:
        logging.info("\nTodos os containers esperados possuem healthcheck.\n")

    if len(oom_killed) > 0:
        errors += len(oom_killed)
        logging.error("\nExistem containers finalizados pelo OOM killer.\n")
        logging.error(oom_killed.to_markdown())
    else:
        logging.info("\nNenhum container foi finalizado pelo OOM killer.\n")

    if len(restarted) > 0:
        errors += len(restarted)
        logging.error("\nExistem containers com reinicios desde a criacao.\n")
        logging.error(restarted.to_markdown())
    else:
        logging.info("\nNenhum container reiniciou desde a criacao.\n")

    expected_workers = int(os.getenv("AIRFLOW_WORKERS_REPLICAS", "1"))
    actual_workers = len(
        container_status_df[
            (container_status_df["Service"] == "etl-airflow-worker")
            & (container_status_df["Status"] == "running")
        ]
    )
    if actual_workers != expected_workers:
        errors += abs(expected_workers - actual_workers) or 1
        logging.error(
            "Quantidade de workers do Airflow incorreta: esperado=%s atual=%s",
            expected_workers,
            actual_workers,
        )
    else:
        logging.info(
            "Quantidade de workers do Airflow confere com AIRFLOW_WORKERS_REPLICAS=%s.",
            expected_workers,
        )
    if return_dfs:
        return errors, {
            "not_running": not_running,
            "restarting": restarting,
            "unhealth": unhealth,
            "health_unavailable": health_unavailable,
        }
    return errors, {}


def save_logs_into_file(logs_lines: dict, path: str) -> None:
    for container_name, log_data in logs_lines.items():
        log_file_path = os.path.join(path, f"{container_name}.log")
        with open(log_file_path, "w", encoding="utf-8") as log_file:
            log_file.write(log_data.get("log_text", ""))
        logging.info("Logs do container %s salvos em %s", container_name, log_file_path)

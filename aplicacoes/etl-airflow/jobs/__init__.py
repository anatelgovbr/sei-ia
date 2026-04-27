#!/usr/bin/env python3
"""Módulo principal da API."""

import logging

from jobs.envs import LOG_LEVEL

log_levels = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

log_level = log_levels.get(LOG_LEVEL.upper())

if log_level is None:
    log_level = logging.INFO


logging.basicConfig(
    level=log_level,
    format="[%(asctime)s] [%(process)d] [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S %z",
)

#!/usr/bin/env python3
"""Module is responsible for checking for new merge requests from an RSS feed.

Checking If there has been a new merge since the last recorded merge.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
import xmltodict
from utils import root_path

logging.basicConfig(level=logging.INFO)


def get_last_merge_requests_merged_from_rss(url_rss: str) -> Optional[dict]:
    """Recuperar o último merge usando RSS do repositorio.

    :param url_rss: URL rss feed.
    :return: Dicionário representando o último merge requests merged, se disponível; caso contrário, None.
    """
    try:
        response = requests.get(url_rss, timeout=10)
        rss_feed = xmltodict.parse(response.text).get("feed")
        last_merged_rss = rss_feed.get("entry") if rss_feed else None

    except KeyError as e:  # pragma: no cover
        logging.info("Last merge not found", exc_info=e)
        last_merged_rss = None

    return last_merged_rss


def check_new_merge_from_rss(url_rss: str, url_last_merge: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Checa se existe um novo merge comparando com o último rodando.

    :param url_rss: URL rss feed.
    :param url_last_merge: URL rss feed do último merge registrado.
    :return: Uma tupla contendo um booleano indicando se há um novo merge e a URL do merge atual.
    """
    last_merge_requests = get_last_merge_requests_merged_from_rss(url_rss)
    url_current_merge = None
    if last_merge_requests:
        url_current_merge = last_merge_requests[0]["link"]["@href"]
    new_merge = url_last_merge != url_current_merge

    if url_last_merge is None:
        logging.info(f"url_last_merge is None. Unable to compare merges this time. Check RSS: {url_rss}")
        logging.info("Assuming as initial merge state: %s", url_current_merge)

    elif url_current_merge is None:
        logging.info("url_current_merge is None. Unable to compare merges this time.")  # pragma: no cover

    elif new_merge:
        logging.info("New merge detected: %s", url_current_merge)

    return new_merge, url_current_merge


def handle_merge_check(service: str, env_alias: str, url_rss: str) -> Tuple[bool, Dict[str, Any]]:
    """Manipula o processo de verificação de novos merges e atualiza os arquivos.

    :param service: Serviço checka por um novo merge.
    :param env_alias: Alias do ambiente.
    :param url_rss: URL RSS para verificar novos merges..
    :return: A tupla indicando se um novo merge foi encontrado e o dicionário de detalhes atualizado.
    """
    json_details = root_path / Path(f"shared/{service}-{env_alias}-details.json")
    dict_details = {}
    if Path(json_details).exists():
        with Path(json_details).open() as file:
            dict_details = json.load(file)
            url_last_merge = dict_details.get("url_last_merge")
    else:
        logging.info(f"No merge current state set. {json_details} not found.", exc_info=True)
        url_last_merge = None

    new_merge, url_current_merge = check_new_merge_from_rss(url_rss, url_last_merge)
    if url_current_merge:
        dict_details["url_last_merge"] = url_current_merge
        Path(json_details).write_text(json.dumps(dict_details))

    return new_merge, dict_details

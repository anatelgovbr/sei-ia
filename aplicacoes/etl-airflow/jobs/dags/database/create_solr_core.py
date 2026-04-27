"""Module containing helper functions for the management of solr cores."""

import requests

from jobs.envs import DEFAULT_REQUEST_TIMEOUT, VERIFY_SSL


def create_solr_core(address, name, conf, auth=None) -> None:
    """Creates a new solr core named name with configset conf.

    Args:
        address: solr address
        name: core name
        conf: path to configset

    https://stackoverflow.com/questions/40604705/check-if-solr-core-already-exists-from-command-line
    """
    # Query core status explicitly to avoid noisy reload errors on first bootstrap.
    status_req = requests.get(
        f"{address}/solr/admin/cores?action=STATUS&core={name}&indexInfo=false&wt=json",
        timeout=DEFAULT_REQUEST_TIMEOUT,
        auth=auth,
        verify=VERIFY_SSL,
    )

    if status_req.status_code == requests.codes.ok:
        try:
            if status_req.json().get("status", {}).get(name):
                return
        except ValueError:
            pass

    create_req = requests.get(
        f"{address}/solr/admin/cores?action=CREATE&name={name}&configSet={conf}",
        timeout=DEFAULT_REQUEST_TIMEOUT,
        auth=auth,
        verify=VERIFY_SSL,
    )

    if create_req.status_code != requests.codes.ok:
        msg = f"Failed to create core:{create_req.text}"
        raise Exception(msg)

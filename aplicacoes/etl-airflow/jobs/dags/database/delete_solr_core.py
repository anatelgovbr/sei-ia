"""Module containing helper functions for the management of solr cores."""

import requests

from jobs.envs import DEFAULT_REQUEST_TIMEOUT, VERIFY_SSL


def delete_solr_core(
    address,
    name,
    deleteIndex=True,
    deleteDataDir=True,
    deleteInstanceDir=False,
    auth=None,
) -> None:
    """Delete a solr core .

    Args:
        address: solr address
        name: core name
        conf: path to configset

    https://stackoverflow.com/questions/40604705/check-if-solr-core-already-exists-from-command-line
    """
    deleteIndex = "true" if deleteIndex else "false"
    deleteDataDir = "true" if deleteDataDir else "false"
    deleteInstanceDir = "true" if deleteInstanceDir else "false"

    # check if core exists
    req0 = requests.get(
        f"{address}/solr/admin/cores?action=reload&core={name}",
        timeout=DEFAULT_REQUEST_TIMEOUT,
        auth=auth,
        verify=VERIFY_SSL,
    )

    if req0.status_code == requests.codes.ok:
        req1 = requests.get(
            f"{address}/solr/admin/cores?action=UNLOAD&core={name}&deleteIndex={deleteIndex}&deleteDataDir={deleteDataDir}&deleteInstanceDir={deleteInstanceDir}",
            timeout=DEFAULT_REQUEST_TIMEOUT,
            auth=auth,
            verify=VERIFY_SSL,
        )

        if req1.status_code != requests.codes.ok:
            raise Exception("Failed to delete core")

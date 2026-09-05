"""Module containing helper functions for the management of solr cores."""

import requests

from jobs.envs import DEFAULT_REQUEST_TIMEOUT, VERIFY_SSL


def delete_solr_core(
    address,
    name,
    delete_index=True,
    delete_data_dir=True,
    delete_instance_dir=False,
    auth=None,
) -> None:
    """Delete a solr core .

    Args:
        address: solr address
        name: core name
        conf: path to configset

    https://stackoverflow.com/questions/40604705/check-if-solr-core-already-exists-from-command-line
    """
    delete_index_str = "true" if delete_index else "false"
    delete_data_dir_str = "true" if delete_data_dir else "false"
    delete_instance_dir_str = "true" if delete_instance_dir else "false"

    # check if core exists
    req0 = requests.get(
        f"{address}/solr/admin/cores?action=reload&core={name}",
        timeout=DEFAULT_REQUEST_TIMEOUT,
        auth=auth,
        verify=VERIFY_SSL,
    )

    if req0.status_code == requests.codes.ok:
        req1 = requests.get(
            f"{address}/solr/admin/cores?action=UNLOAD&core={name}&deleteIndex={delete_index_str}&deleteDataDir={delete_data_dir_str}&deleteInstanceDir={delete_instance_dir_str}",
            timeout=DEFAULT_REQUEST_TIMEOUT,
            auth=auth,
            verify=VERIFY_SSL,
        )

        if req1.status_code != requests.codes.ok:
            raise RuntimeError("Failed to delete core")

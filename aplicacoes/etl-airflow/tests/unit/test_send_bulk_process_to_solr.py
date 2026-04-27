import unittest
from collections import namedtuple
from unittest import mock

import pandas as pd
from jobs.dags.dag_objects.mlt_etl_process.dag_mlt_etl_process import bulk_task_send_process
from jobs.dags.dag_objects.mlt_etl_process.funcs import ProcessToIndex
from jobs.envs import SOLR_MLT_PROCESS_CORE
import json
# from jobs.dags.dag_objects.old_mlt_process_dag import (
#     generic_task_send_bulk_process_to_solr,
#     send_process_to_solr,
# )


class TestDagSendProcessToSolr(unittest.TestCase):
    """test dag send process to solr"""

    def setUp(self):
        self.dummy_batch_process_info = "[[\"1\", 1, \"2024-02-27T19:55:36Z\", \"2024-02-27T19:55:36Z\"]]"
        

    @mock.patch("jobs.dags.dag_objects.mlt_etl_process.funcs.send_bulk_process_to_solr")
    def test_send_bulk_process_to_solr(self, mock_send_bulk_process_to_solr):
        """
        Tests if bulk_task_send_process passes the arguments
        to send_bulk_process_to_solr properly
        """
        DagRun = namedtuple("DagRun", ["conf"])
        kwargs = {
            "dag_run": DagRun(
                {
                    "batch_process_info": self.dummy_batch_process_info,
                    "interested_max": 1,
                    "related_processes_max": 1,
                }
            ),
            "ti": mock.MagicMock(),
        }

        batch_process_info = json.loads(self.dummy_batch_process_info)
        l_batch = [ProcessToIndex(id_protocolo=item[0],
                                id_type_process=item[1],
                                dt_update=item[2],
                                created_at=item[3]) for item in batch_process_info]
        bulk_task_send_process.function(**kwargs)

        mock_send_bulk_process_to_solr.assert_called_with(l_batch, 1,1, 
                                                          SOLR_MLT_PROCESS_CORE,external=True, subprocesses=True)


# if __name__ == "__main__":
#     unittest.main()
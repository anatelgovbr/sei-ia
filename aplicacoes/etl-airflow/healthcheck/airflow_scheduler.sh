#!/bin/bash
set -euo pipefail

airflow jobs check --job-type SchedulerJob --hostname "${HOSTNAME}"

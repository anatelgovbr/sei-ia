#!/bin/bash
airflow jobs check --job-type TriggererJob --hostname "${HOSTNAME}"
  

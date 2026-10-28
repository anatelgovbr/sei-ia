#!/bin/bash
celery --app airflow.providers.celery.executors.celery_executor.app inspect ping

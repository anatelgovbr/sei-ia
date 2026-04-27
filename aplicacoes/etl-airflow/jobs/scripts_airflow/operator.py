"""operator module."""

import time

from airflow.exceptions import AirflowException
from airflow.operators.python_operator import PythonOperator, PythonVirtualenvOperator
from airflow.utils.decorators import apply_defaults

from jobs.envs import LIST_RETRY_DELAYS_4t


class CustomPythonRetryOperator(PythonOperator):
    """Implementa a lista de retry_delay baseada no current_retry."""

    @apply_defaults
    def __init__(self, *args, retry_delays=LIST_RETRY_DELAYS_4t, **kwargs) -> None:
        """Constructor da classe."""
        super().__init__(*args, **kwargs)
        self.retry_delays = retry_delays

    def execute(self, context) -> None:
        """Executa a DAG atualizando o delay do retry em caso de exception."""
        try:
            super().execute(context)
        except Exception as e:
            # PythonOperator não capturava AirflowException corretamente
            # Workaround necessário
            current_retry = context["ti"].try_number - 1
            if current_retry < len(self.retry_delays):
                delay = self.retry_delays[current_retry]
                self.log.exception(f"Erro capturado: {e!s}")
                self.log.info(
                    f"Tentativa de retry em {delay.total_seconds()}s "
                    f"(tentativa {current_retry + 1})."
                )
                time.sleep(delay.total_seconds())
                msg = (
                    f"Retrying delayed for {delay.total_seconds()}s after error: {e!s}"
                )
                raise AirflowException(msg) from e
            raise


class CustomPythonVirtualRetryOperator(PythonVirtualenvOperator):
    """Implementa a lista de retry_delay baseada no current_retry."""

    @apply_defaults
    def __init__(self, *args, retry_delays=LIST_RETRY_DELAYS_4t, **kwargs) -> None:
        """Constructor da classe."""
        super().__init__(*args, **kwargs)
        self.retry_delays = retry_delays

    def execute(self, context) -> None:
        """Executa a DAG atualizando o delay do retry em caso de exception."""
        try:
            super().execute(context)
        except AirflowException as e:
            current_retry = context["ti"].try_number - 1
            if current_retry < len(self.retry_delays):
                delay = self.retry_delays[current_retry]
                self.log.info(
                    f"Retrying in {delay.total_seconds()}s "
                    f"(attempt {current_retry + 1})."
                )
                time.sleep(delay.total_seconds())
                msg = f"Retrying delayed for {delay.total_seconds()}s."
                raise AirflowException(msg) from e
            raise

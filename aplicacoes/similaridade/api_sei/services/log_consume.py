from api_sei.pydantic_models.log_consume import LogConsumeCreate
from api_sei.repository.log_consume import insert_log_consume


def create_log(
    status_code: int, id_protocol: list[int], id_user: int, api_recomend_url: str
):
    log_consume = LogConsumeCreate(
        id_protocol=id_protocol,
        id_user=id_user,
        api_recomend_url=api_recomend_url,
        status_code=status_code,
    )

    insert_log_consume(log_consume=log_consume)

from urllib.parse import parse_qs, urlencode, urlparse

import numpy as np
import pandas as pd


def response_normalization(recomendations: dict, max_score: float):
    """
    Descrição:
    - Função de normalização da saída dos scores dos recommenders. Os valores são normalizados
    baseados nos valores máximos de cada recommender.

    Parâmetros:
    - recomentations (Dict): Dicionário com as recomedações finais de um método de recomendação.
    - max_score (float): similaridade máxima

    Retorno:
    - response (dict): Dicionário com o scores de recomendação já normalizados.
    """

    if len(recomendations["recommendation"]) == 0:
        return recomendations

    recomendations_df = pd.DataFrame(recomendations["recommendation"])

    recomendations_df["score"] = (recomendations_df["score"] / (max_score)).clip(0, 1)

    # Contrução da resposta
    response = {"recommendation": recomendations_df.to_dict("records")}

    return response


def add_param_on_url_if_not_exists(url: str, param_name: str, param_value: str) -> str:
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    query_params[param_name] = [param_value]
    parsed_url = parsed_url._replace(query=urlencode(query_params, doseq=True))
    updated_url = parsed_url.geturl()

    return updated_url


def replace_nan(data):
    "Funcao para corrigir erro de parsed do json com valores NaN"
    if isinstance(data, dict):
        return {k: replace_nan(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_nan(item) for item in data]
    elif isinstance(data, float) and np.isnan(data):
        return ""
    else:
        return data

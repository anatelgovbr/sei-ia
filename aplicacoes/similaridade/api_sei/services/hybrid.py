"""Estratégia de recomendação de documentos ou processos baseada na combinação de outras estratégias (Ensemble).

Parâmetros:
- identifier (Int) : Número do documento ou processo que deseja encontrar similares
- recommenders (List) : Lista de recommenders para serem utilizados na recomendação hibrida:
    - mlt: More like this recommender
    - ner: Entity Recognition recommender
    - rerank: MLT+BERT recommender
- join_method (Str) : Método a ser utilizado para calcular as recomendações finais. Métodos possíveis:
    - outer : Realiza um "outer join" analisando as recomendações de cada método.
    - inner : Devolve somente os documentos que foram recomendados em todos os métodos escolhidos
- mean_weights (List) : Lista de pesos para uma média ponderada entre os scores de cada método. Valor default: [1,1,1]

Retorno:
- JSON - {document_id:,score:}

assert len(recommenders) <= 3

assert join_method in ['inner','outer']

assert isinstance(mean_weights, list) and len(mean_weights)==len(recommenders)

"""

from functools import partial

import numpy as np
import pandas as pd

from api_sei.services.mlt import (
    mlt_process_recommendations_service,
    wmlt_process_recommendations_service,
)

process_recommenders = {
    "wmlt": mlt_process_recommendations_service,
    "mlt": mlt_process_recommendations_service,
}


def skipna_average(data, weights, axis):
    # https://stackoverflow.com/questions/35758147/taking-np-average-while-ignoring-nans
    masked_data = np.ma.masked_array(data, np.isnan(data))
    average = np.ma.average(masked_data, axis=axis, weights=weights)
    result = average.filled(np.nan)
    return result


def hwmlt_process_recommendations_service(
    id_value, rows, fq, depth=200, id_field="id_protocolo"
):
    recommenders = [
        partial(
            wmlt_process_recommendations_service,
            parsedquery_field="fulltext_parsedquery_t",
            id_field=id_field,
        ),
        partial(
            wmlt_process_recommendations_service,
            parsedquery_field="sections_parsedquery_t",
            id_field=id_field,
        ),
    ]
    return merge_recommenders(
        id_value, "outer", rows, recommenders, [1, 1], fq, depth, agg_func="max"
    )


def merge_recommenders(
    identifier,
    join_method,
    rows,
    recommenders,
    mean_weights,
    fq,
    depth,
    agg_func="mean",
):
    # Exemplo:
    # >>> import pandas as pd
    # >>> a = pd.DataFrame([{"id":1,"score":1},{"id":2,"score":3}]).set_index(keys='id')
    # >>> a
    #     score
    # id
    # 1       1
    # 2       3
    # >>> b = pd.DataFrame([{"id":1,"score":5},{"id":3,"score":1}]).set_index(keys='id')
    # >>> b
    #     score
    # id
    # 1       5
    # 3       1
    # >>> pd.concat([a,b],axis=1).fillna(0)
    #     score  score
    # id
    # 1     1.0    5.0
    # 2     3.0    0.0
    # 3     0.0    1.0
    # >>> pd.concat([a,b],join="inner",axis=1).fillna(0)
    #     score  score
    # id
    # 1       1      5
    # >>> merged_df = pd.concat([a,b],axis=1).fillna(0)
    # >>> merged_df.mean()
    # score    1.333333
    # score    2.000000
    # dtype: float64

    # Etapa de recomendação
    df_recommentations = []
    col_weights = []
    for i, recommender_function in enumerate(recommenders):
        response = recommender_function(
            id_value=identifier, fq=None, rows=depth, normalized=True
        )["recommendation"]
        if len(response) != 0:
            df_recommentations.append(pd.DataFrame(response).set_index(keys="id"))
            col_weights.append(mean_weights[i])

    # Etapa de join
    merged_df = pd.concat(df_recommentations, join=join_method, axis=1)  # .fillna(0)
    merged_df.drop(columns=["vector"], inplace=True, errors="ignore")

    if merged_df.size == 0:
        print(
            "Não há interseção entre as recomendações.\nExecutando o método default..."
        )
        merged_df = pd.concat(df_recommentations, axis=1)  # .fillna(0)

    if fq is not None:
        reduced_fq = list(set(merged_df.index.tolist()).intersection(set(fq)))
        merged_df = merged_df.loc[reduced_fq]

    # Etapa de ranqueamento
    merged_df.reset_index(inplace=True)
    response_df = pd.DataFrame()
    response_df["id"] = merged_df["id"]
    if agg_func == "mean":
        response_df["score"] = skipna_average(
            merged_df.drop(columns="id"), col_weights, 1
        )
    elif agg_func == "max":
        response_df["score"] = merged_df.drop(columns="id").max(axis=1)
    else:
        raise ValueError(f"Unknown agg_func {agg_func}")
    response_df = response_df.sort_values(by=["score"], ascending=False)

    response_df = response_df.head(rows)

    # Contrução da resposta
    response = {"recommendation": response_df.to_dict("records")}

    return response

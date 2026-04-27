import json
import logging
from jobs.db_models.app_tables import ConfigMltFieldsWeights
from jobs.db_models.repository import app_db
# - Conteúdo dos Documentos:
#     - sugiro considerar os principais tipos de documentos destacados pela análise do rafael, considerando um limiar
# - Metadados:
#     - Processos Relacionados: (sugiro avaliar como implementar isso, pois vejo como uma recursividade de comparação entre processos, mas antes avaliando se tem ou não processo relacionado)



logger = logging.getLogger(__name__)



def init_weights_dict(mlt_fields,weights_dict,d,level):

    for in_key in d.keys():

        for out_key in mlt_fields:

            if in_key in out_key:

                weights_dict[out_key] = {"level":level+(0 if in_key == out_key else 1),"weight":1}

        if d[in_key].get("fields"):

            weights_dict = init_weights_dict(mlt_fields,weights_dict,d[in_key]["fields"],level+1)
    
    return weights_dict


def read_weight(weights_dict,d,level):

    for in_key in d.keys():

        for out_key in weights_dict.keys():

            if in_key in out_key:

                # print(f"{in_key} is in {out_key} then {weights_dict[out_key]['weight']}*{d[in_key]['weight']}->{weights_dict[out_key]['weight']*d[in_key]['weight']}")

                weights_dict[out_key]["weight"] *= d[in_key]["weight"]

        if d[in_key].get("variable_subfields"):

            subfields = []
            for out_key in weights_dict.keys():
                if (in_key in out_key) and (weights_dict[out_key]["level"] == level+1):
                    subfields.append(out_key)
            
                if d[in_key].get("fields"):
                    for subfield in d[in_key]["fields"].keys():
                        if (subfield in out_key):
                            subfields.append(subfield)

            c = len(set(subfields))

            for out_key in weights_dict.keys():

                if in_key in out_key:

                    # print(f"{in_key} has variable subfields and {in_key} is in {out_key} then {weights_dict[out_key]['weight']} / {c} ->{weights_dict[out_key]['weight']/c}")

                    weights_dict[out_key]["weight"] /= c

        if d[in_key].get("fields"):

            weights_dict = read_weight(weights_dict,d[in_key]["fields"],level+1)

    return weights_dict




def read_mlt_fields_weights(mlt_fields):

    conf_mlt_fields_weights = app_db.execute_query_one(f"SELECT * FROM {ConfigMltFieldsWeights.__tablename__} ORDER BY id DESC")[1]
    
    weights_dict = init_weights_dict(mlt_fields,dict(),conf_mlt_fields_weights,0)

    weights_dict = read_weight(weights_dict,conf_mlt_fields_weights,0)

    return weights_dict


def recursive_keys(d,ks):
    for k, v in d.items():
        ks.append(k)
        if isinstance(v,dict):
            ks = recursive_keys(v,ks)
    return ks


def read_fulltext_sections_fields():
    
    conf_mlt_fields_weights = app_db.execute_query_one(f"SELECT * FROM {ConfigMltFieldsWeights.__tablename__} ORDER BY id DESC")[1]

    fulltext_fields = set(conf_mlt_fields_weights["content"]["fields"]["content_id_type_doc_"]["fields"].keys())

    reserved_words = {'fields','weight','variable_subfields'}

    sections_fields = set(recursive_keys(conf_mlt_fields_weights["content"]["fields"]["content_id_type_doc_"],[]))
    
    sections_fields = sections_fields - set(fulltext_fields)

    sections_fields = sections_fields - reserved_words

    return fulltext_fields,sections_fields
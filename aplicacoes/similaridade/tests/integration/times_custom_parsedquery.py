
import time
from unittest import mock
from api_sei.resources.custom_parsedquery import FasterCustomParsedQuery
from api_sei.resources.custom_parsedquery import (
    read_fulltext_sections_fields, read_mlt_fields_weights)
from api_sei.resources.custom_parsedquery import get_all_str_search_fields


@mock.patch(
    'api_sei.resources.custom_parsedquery.SOLR_ADDRESS',
    'http://localhost:8997'
)
@mock.patch(
    'api_sei.resources.custom_parsedquery.SOLR_MLT_PROCESS_CORE',
    'process'
)
def times_custom_parsedquery(id_protocolo = "243264",speed_level = 2,parallel=False,n_repetitions = 10):

    fulltext_fields,sections_fields = read_fulltext_sections_fields()

    fulltext_time = 0
    for i in range(n_repetitions):
        fulltext_start = time.time()
        customParsedQuery = FasterCustomParsedQuery(
            id_protocolo,ignore_fields = sections_fields, speed_level=speed_level, parallel=parallel)
        fulltext_parsedquery = customParsedQuery.get_parsedquery(ignore_fields = sections_fields)
        fulltext_end = time.time()
        fulltext_time += (fulltext_end-fulltext_start)
    fulltext_time = fulltext_time / n_repetitions

    sections_time = 0
    for i in range(n_repetitions):
        sections_start = time.time()
        customParsedQuery = FasterCustomParsedQuery(
            id_protocolo,ignore_fields = fulltext_fields, speed_level=speed_level, parallel=parallel)
        sections_parsedquery = customParsedQuery.get_parsedquery(ignore_fields = fulltext_fields)
        sections_end = time.time()
        sections_time += (sections_end-sections_start)
    sections_time = sections_time / n_repetitions

    hybrid_time = 0
    for i in range(n_repetitions):
        hybrid_start = time.time()
        customParsedQuery = FasterCustomParsedQuery(
            id_protocolo, speed_level=speed_level, parallel=parallel)
        fulltext_parsedquery = customParsedQuery.get_parsedquery(ignore_fields = sections_fields)
        sections_parsedquery = customParsedQuery.get_parsedquery(ignore_fields = fulltext_fields)
        hybrid_end = time.time()
        hybrid_time += (hybrid_end-hybrid_start)
    hybrid_time = hybrid_time / n_repetitions

    fulltext_mlt_fields = read_mlt_fields_weights([f for f in get_all_str_search_fields(
        id_protocolo, customParsedQuery.base_url, id_field="id_protocolo") if f not in sections_fields])

    sections_mlt_fields = read_mlt_fields_weights([f for f in get_all_str_search_fields(
        id_protocolo, customParsedQuery.base_url, id_field="id_protocolo") if f not in fulltext_fields])
    
    print("process: ", id_protocolo)
    print("custom parsedquery speed level: ", speed_level)
    print("fulltext fields: ",len(fulltext_mlt_fields))
    print("sections fields: ",len(sections_mlt_fields))

    print("fulltext elapsed time in seconds: ", fulltext_time)
    print("sections elapsed time in seconds: ", sections_time)
    print("hybrid elapsed time in seconds: ", hybrid_time)
    print("number of repetitions: ", n_repetitions)


if __name__ == '__main__':

    # times_custom_parsedquery(id_protocolo = "243264",speed_level = 1,parallel=False,n_repetitions = 10)
    times_custom_parsedquery(id_protocolo = "243264",speed_level = 2,parallel=False,n_repetitions = 10)
    # times_custom_parsedquery(id_protocolo = "243264",speed_level = 3,parallel=False,n_repetitions = 10)
    # times_custom_parsedquery(id_protocolo = "243264",speed_level = 4,parallel=False,n_repetitions = 10)

    # times_custom_parsedquery(id_protocolo = "243264",speed_level = 1,parallel=True,n_repetitions = 10)
    times_custom_parsedquery(id_protocolo = "243264",speed_level = 2,parallel=True,n_repetitions = 10)
    # times_custom_parsedquery(id_protocolo = "243264",speed_level = 3,parallel=True,n_repetitions = 10)
    # times_custom_parsedquery(id_protocolo = "243264",speed_level = 4,parallel=True,n_repetitions = 10)
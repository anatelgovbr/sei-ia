"""Funções utilitárias compartilhadas entre as DAGs de ETL."""


def split_set(set_id_process_with_type_id_process, slots):
    """Divide um conjunto de IDs em múltiplos slots para processamento paralelo.

    Args:
        set_id_process_with_type_id_process: Conjunto de IDs a serem divididos
        slots: Número de slots para distribuição

    Returns:
        Lista de listas, onde cada sublista contém os IDs para um slot específico
    """
    list_process = list(set_id_process_with_type_id_process)
    result = []
    for i in range(slots):
        result.append(list_process[i::slots])
    return result

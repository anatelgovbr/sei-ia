"""Arquivo que contem as funcoes para a concatenacao de documentos."""

import asyncio
import contextlib
import logging
import time

from langgraph.config import get_stream_writer

from sei_ia.agents.prompts.completation import INTERMEDIATE_COMPLETATION_WITH_DOC
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.data.database.db_instances import app_db_instance
from sei_ia.data.etl.extract.doc_content import EXT_PERMITIDAS
from sei_ia.data.etl.extract.external import get_doc_ext_from_id
from sei_ia.data.etl.extract.internal import get_doc_int_from_id
from sei_ia.data.etl.extract.metadata import (
    fetch_documentos_metadata_batch,
    fetch_procedimentos_metadata_batch,
    get_doc_metadata_dict,
    get_doc_metadata_from_id,
    get_proc_id_from_doc_id,
    get_type_doc_from_id,
)
from sei_ia.data.pydantic_models import ItemDocument, UserState
from sei_ia.services.cache import get_cache
from sei_ia.services.cache.cache_cleanup_service import cleanup_non_cacheable_documents
from sei_ia.services.counter import token_counter
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException406,
    HTTPException411DocumentTimeout,
    HTTPException412SeiApiTimeout,
    HTTPException415,
    HTTPException422,
)

setup_logging()
logger = logging.getLogger(__name__)


def is_document_paginated(id_documento_obj) -> bool:
    """Verifica se um documento é paginado e não deve ser cacheado.

    Args:
        id_documento_obj: Objeto ItemDocumentRequest do documento

    Returns:
        bool: True se o documento é paginado (tem paginação ou download_ext)
    """
    return bool(
        id_documento_obj.pag_doc_init
        or id_documento_obj.pag_doc_end
        or id_documento_obj.download_ext
    )


def register_payload_pagination(
    doc_paged: list[tuple[str, int | None, int | None]],
    id_docs_paged: list[str],
    doc_obj,
    metadata_info: dict | None,
) -> None:
    """Registra paginação vinda do payload usando o número formatado do documento."""

    if not (doc_obj.pag_doc_init or doc_obj.pag_doc_end):
        return

    metadata_info = metadata_info or {}
    num_doc_temp = str(metadata_info.get("id_documento_formatado", "")).strip()
    if not num_doc_temp or num_doc_temp in id_docs_paged:
        return

    pag_ini = doc_obj.pag_doc_init
    pag_fim = doc_obj.pag_doc_end
    if pag_ini is not None and pag_fim is None:
        pag_fim = pag_ini

    doc_paged.append((num_doc_temp, pag_ini, pag_fim))
    id_docs_paged.append(num_doc_temp)


def build_docs_paged_from_payload(
    user_state: UserState, doc_metadata_map: dict[str, dict]
) -> tuple[list[tuple[str, int | None, int | None]], list[str]]:
    """Monta a paginação exclusivamente a partir dos campos enviados no payload."""

    doc_paged: list[tuple[str, int | None, int | None]] = []
    id_docs_paged: list[str] = []

    for proc_item in user_state["id_procedimentos"] or []:
        for doc_obj in proc_item.id_documentos:
            register_payload_pagination(
                doc_paged=doc_paged,
                id_docs_paged=id_docs_paged,
                doc_obj=doc_obj,
                metadata_info=doc_metadata_map.get(doc_obj.id_documento),
            )

    return doc_paged, id_docs_paged


async def get_doc_from_id_async(
    id_documento: str,
    docs_paged: list | None = None,
    download_ext: bool | None = None,
    cached_metadata: dict | None = None,
) -> tuple[str, str, dict]:
    """Versão assíncrona de get_doc_from_id.

    Recupera o conteúdo de um documento com base em seu identificador usando operações assíncronas.

    Args:
        id_documento: O identificador único do documento a ser recuperado
        docs_paged: Lista de documentos paginados
        download_ext: Flag para forçar download de documento externo

    Returns:
        Tuple[str, str, dict]: Conteúdo do documento, ID formatado e metadados extras da API
    """
    try:
        # Usar loop para executar operações síncronas de forma não bloqueante
        loop = asyncio.get_running_loop()

        internal = None
        doc_extension = None
        num_doc_formatado = None
        metadata = None

        if cached_metadata is not None:
            metadata = (
                cached_metadata.get("metadata")
                if cached_metadata.get("metadata")
                else cached_metadata
            )

        if metadata and metadata.get("type_doc"):
            type_doc_value = metadata["type_doc"]
            internal = type_doc_value.upper() != "X"
            doc_extension = metadata.get("formato_arquivo")
            num_doc_formatado = metadata.get("id_documento_formatado")

        if internal is None:
            (
                internal,
                doc_extension,
                num_doc_formatado,
                protocolo_formatado,
            ) = await get_type_doc_from_id(id_documento)

        if not internal and doc_extension not in EXT_PERMITIDAS:
            msg = f"ID DOC: {id_documento} (nº: {num_doc_formatado}). Tipo de midia nao suportado."
            logger.warning(msg)
            raise HTTPException415(detail=msg)

        pag_ini = None
        pag_fim = None
        if docs_paged:
            for doc in docs_paged:
                if doc[0] == num_doc_formatado:
                    pag_ini = doc[1]
                    pag_fim = doc[2]
                    break

        # Cenário 1: Documentos Externos sigilosos com download_ext=true
        # Cenário 3: Documentos com intervalo de página com download_ext=true
        if download_ext is True and not internal:
            logger.debug(
                f"Flag download_ext=True para documento {id_documento} (nº {num_doc_formatado})"
            )
            doc_content = await loop.run_in_executor(
                None,
                get_doc_ext_from_id,
                id_documento,
                pag_ini,
                pag_fim,
                doc_extension,
                True,  # force_download
            )
            return (doc_content, num_doc_formatado, {})

        if internal:
            if pag_ini or pag_fim:
                logger.warning(
                    f"O documento id {id_documento} (nº {num_doc_formatado}) é interno!"
                )
                msg = f"Não posso definir um intervalo de páginas para o documento nº {num_doc_formatado}!"
                raise HTTPException406(detail=msg)
            try:
                doc_content, extra_metadata = await get_doc_int_from_id(id_documento)
                return (doc_content, num_doc_formatado, extra_metadata)
            except HTTPException204:
                doc_content = await loop.run_in_executor(
                    None, get_doc_ext_from_id, id_documento
                )
                return (doc_content, num_doc_formatado, {})

        # Cenário padrão: consulta conteúdo do documento
        doc_content = await loop.run_in_executor(
            None, get_doc_ext_from_id, id_documento, pag_ini, pag_fim, doc_extension
        )
        return (doc_content, num_doc_formatado, {})

    except Exception as exc:
        logger.exception(f"Erro ao recuperar documento {id_documento}: {exc}")
        raise


async def process_document_async(
    id_documento_obj,
    doc_paged: list,
    id_docs_paged: list,
    token_len_metadata,
    semaphore: asyncio.Semaphore,
) -> ItemDocument:
    """Processa um documento individual de forma assíncrona com cache e controle de concorrência.

    Args:
        id_documento_obj: Objeto ItemDocumentRequest do documento
        doc_paged: Lista de documentos paginados
        id_docs_paged: Lista de IDs de documentos paginados
        token_len_metadata: tamanho do metadata de procedimento em tokens
        semaphore: Semáforo para controlar concorrência

    Returns:
        ItemDocument: Documento processado
    """
    async with semaphore:  # Limitar concorrência
        logger.debug(
            f">> Processando documento {id_documento_obj.id_documento} assincronamente"
        )

        # Verificar cache apenas se não for documento paginado
        is_paginated = is_document_paginated(id_documento_obj)

        if not is_paginated:
            cache = get_cache()
            cached_document = await cache.get_document(
                id_documento_obj.id_documento,
                pag_ini=id_documento_obj.pag_doc_init,
                pag_fim=id_documento_obj.pag_doc_end,
                download_ext=id_documento_obj.download_ext,
                id_anexos=id_documento_obj.id_anexos,
            )

            if cached_document is not None:
                logger.debug(
                    f"✓ Cache hit: documento {id_documento_obj.id_documento} recuperado do cache"
                )

                # Atualizar tokens com metadados do procedimento (que podem ter mudado)
                metadata_str = (
                    cached_document["metadata"]
                    if isinstance(cached_document["metadata"], str)
                    else str(cached_document["metadata"])
                )
                cached_document["doc_tokens"] = (
                    token_counter(cached_document["content"])
                    + token_counter(metadata_str)
                    + 4
                    + token_len_metadata
                )

                return cached_document
        else:
            logger.debug(
                f"⚠ Documento {id_documento_obj.id_documento} é paginado, pulando cache"
            )

        logger.debug(
            f"⚠ Cache miss: processando documento {id_documento_obj.id_documento}"
        )

        # Cenário 3: Documentos com intervalo de página definido no request
        if id_documento_obj.pag_doc_init or id_documento_obj.pag_doc_end:
            doc_metadata_temp = await get_doc_metadata_dict(
                id_documento_obj.id_documento
            )
            num_doc_temp = str(doc_metadata_temp["id_documento_formatado"])
            if num_doc_temp not in id_docs_paged:
                doc_paged.append(
                    (
                        num_doc_temp,
                        id_documento_obj.pag_doc_init,
                        id_documento_obj.pag_doc_end,
                    )
                )
                id_docs_paged.append(num_doc_temp)

        # Processar documento principal
        doc, id_documento_formatado, _ = await get_doc_from_id_async(
            id_documento_obj.id_documento,
            doc_paged,
            id_documento_obj.download_ext,
        )

        # Cenário 2: Anexos de correspondência eletrônica (processamento paralelo)
        if id_documento_obj.id_anexos:
            logger.debug(
                f"Processando anexos para documento {id_documento_obj.id_documento}: {id_documento_obj.id_anexos}"
            )

            # Processar anexos em paralelo
            anexo_tasks = [
                get_doc_from_id_async(id_anexo, doc_paged, True)
                for id_anexo in id_documento_obj.id_anexos
            ]

            anexo_results = []
            if anexo_tasks:
                anexo_results = await asyncio.gather(
                    *anexo_tasks, return_exceptions=True
                )

            # Processar resultados dos anexos
            if anexo_results:
                for i, result in enumerate(anexo_results):
                    id_anexo = id_documento_obj.id_anexos[i]
                    if isinstance(result, Exception):
                        if isinstance(
                            result,
                            HTTPException411DocumentTimeout
                            | HTTPException412SeiApiTimeout,
                        ):
                            logger.exception(
                                f"Timeout no anexo {id_anexo} do documento {id_documento_obj.id_documento}: {result}"
                            )
                            raise result
                        else:
                            logger.warning(
                                f"Erro ao processar anexo {id_anexo}: {result}"
                            )
                            continue
                    else:
                        doc_anexo, id_anexo_formatado, _ = result
                        doc += f"\n\n--- Anexo {id_anexo_formatado} ---\n{doc_anexo}"
                        logger.debug(
                            f"Anexo {id_anexo_formatado} processado com sucesso"
                        )

        # Obter metadados
        doc_metadata_dict = await get_doc_metadata_dict(id_documento_obj.id_documento)
        doc_metadata = await get_doc_metadata_from_id(id_documento_obj.id_documento)

        # Formatar documento
        doc = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
            id_documento_formatado=id_documento_formatado,
            protocolo_processo=doc_metadata_dict.get("id_protocolo_formatado", ""),
            doc=doc,
        )

        # Criar objeto de documento
        doc_object = ItemDocument(  # type: ignore
            id_documento=id_documento_obj.id_documento,
            id_documento_formatado=id_documento_formatado,
            content=doc,
            doc_tokens=token_counter(doc)
            + token_counter(doc_metadata)
            + 4
            + token_len_metadata,
            metadata=doc_metadata,
            download_ext=id_documento_obj.download_ext,
            id_anexos=id_documento_obj.id_anexos,
        )

        # Verificar se é documento paginado
        num_documento = str(doc_metadata_dict["id_documento_formatado"])
        if num_documento in id_docs_paged:
            idx_doc_paged = id_docs_paged.index(num_documento)
            doc_object["pag_doc_init"] = doc_paged[idx_doc_paged][1]
            doc_object["pag_doc_end"] = doc_paged[idx_doc_paged][2]
            if doc_object["pag_doc_init"]:
                doc_object["doc_paged"] = True

        # Armazenar no cache apenas se não for documento paginado
        if not is_paginated:
            cache = get_cache()
            try:
                cache_success = await cache.set_document(
                    doc_object,
                    pag_ini=id_documento_obj.pag_doc_init,
                    pag_fim=id_documento_obj.pag_doc_end,
                    download_ext=id_documento_obj.download_ext,
                    id_anexos=id_documento_obj.id_anexos,
                )
                if cache_success:
                    logger.debug(
                        f"✓ Documento {id_documento_obj.id_documento} armazenado no cache"
                    )
                else:
                    logger.warning(
                        f"⚠️  Cache indisponível - documento {id_documento_obj.id_documento} não foi armazenado no cache"
                    )
            except Exception as e:
                # Log erro mas não falha o processamento se o cache falhar
                logger.warning(
                    f"Erro ao armazenar documento {id_documento_obj.id_documento} no cache: {e}"
                )
        else:
            logger.debug(
                f"✓ Documento {id_documento_obj.id_documento} é paginado, não armazenado no cache"
            )

        return doc_object


async def process_procedimento_async(user_state: UserState) -> UserState:
    """Processa metadados dos procedimentos de forma assíncrona usando batch fetch.

    Args:
        user_state: Estado do usuário

    Returns:
        UserState: Estado do usuário atualizado
    """
    # Obter ID do procedimento se necessário #TODO: Excluir quando remover auto teste porque sempre recebe o id_procedimento.
    for item_id_procedimento in user_state["id_procedimentos"]:
        if (
            item_id_procedimento.id_procedimento == ""
            or item_id_procedimento.id_procedimento is None
            or item_id_procedimento.id_procedimento == "N/A"
        ):
            primeiro_doc = item_id_procedimento.id_documentos[0]
            primeiro_doc_id = (
                primeiro_doc.id_documento
                if hasattr(primeiro_doc, "id_documento")
                else primeiro_doc
            )
            item_id_procedimento.id_procedimento = str(
                await get_proc_id_from_doc_id(primeiro_doc_id)
            )

        # Validação: se id_procedimento continuar vazio/None, interrompe com 204
        if (
            not item_id_procedimento.id_procedimento
            or item_id_procedimento.id_procedimento.strip() == ""
        ):
            logger.warning(
                "Nenhum id_procedimento foi encontrado a partir do(s) documento(s). Retornando 204."
            )
            raise HTTPException204(
                detail="Documento sem conteúdo ou procedimento não encontrado"
            )

    # Buscar metadados de todos os procedimentos em batch
    all_proc_ids = [
        item.id_procedimento
        for item in user_state["id_procedimentos"]
        if item.id_procedimento and item.id_procedimento.strip()
    ]

    if all_proc_ids:
        logger.info(
            f"🚀 BATCH: Buscando metadados de {len(all_proc_ids)} procedimentos"
        )
        proc_metadata_map = await fetch_procedimentos_metadata_batch(all_proc_ids)

        # Distribuir metadados para cada procedimento
        for item_id_procedimento in user_state["id_procedimentos"]:
            if item_id_procedimento.id_procedimento in proc_metadata_map:
                item_id_procedimento.metadata = proc_metadata_map[
                    item_id_procedimento.id_procedimento
                ]
            else:
                logger.warning(
                    f"Metadado não encontrado para procedimento {item_id_procedimento.id_procedimento}"
                )
                item_id_procedimento.metadata = ""

    return user_state


async def concatenate_procedimento_documents_async(
    document_semaphore: asyncio.Semaphore, user_state: UserState
) -> UserState:
    """Processa todos os documentos usando novo fluxo: cache → batch metadata → parallel content.

    Args:
        document_semaphore: Semáforo para controlar concorrência
        user_state: Estado do usuário

    Returns:
        UserState: Estado do usuário atualizado com documentos processados
    """
    start_time = time.time()
    user_state["doc_paged"] = False

    # Coletar todos os documentos com seus metadados de procedimento
    all_docs_with_proc_metadata = [
        (token_counter(item.metadata), doc, item.metadata)
        for item in user_state["id_procedimentos"]
        for doc in item.id_documentos
    ]

    logger.info(
        f"🚀 BATCH V3: Processando {len(all_docs_with_proc_metadata)} documentos com novo fluxo"
    )

    # === FASE 1: Batch Fetch de Metadados de TODOS os Documentos ===
    # Precisamos buscar metadados de todos os documentos (não apenas os que faltam)
    # para saber quais têm sin_armazena_cache="N" e devem ser limpos
    all_doc_ids = [
        doc_obj.id_documento for _, doc_obj, _ in all_docs_with_proc_metadata
    ]
    logger.info(f"🚀 BATCH: Buscando metadados de {len(all_doc_ids)} documentos")
    doc_metadata_map = await fetch_documentos_metadata_batch(all_doc_ids)

    for proc_item in user_state["id_procedimentos"]:
        for doc_obj in proc_item.id_documentos:
            if doc_obj.id_documento in doc_metadata_map:
                metadata_info = doc_metadata_map[doc_obj.id_documento]
                sin_cache = metadata_info.get("sin_armazena_cache", "S")
                doc_obj.sin_armazena_cache = sin_cache

    doc_paged, id_docs_paged = build_docs_paged_from_payload(
        user_state=user_state,
        doc_metadata_map=doc_metadata_map,
    )

    # === LIMPEZA: Deletar cache/embeddings de documentos não cacheáveis ===
    # Agora que temos os metadados (incluindo sin_armazena_cache), podemos fazer a limpeza
    try:
        cache = get_cache()
        db_engine = app_db_instance.async_engine

        cleanup_result = await cleanup_non_cacheable_documents(
            user_state=user_state,
            redis_client=cache,
            db_pool=db_engine,
        )

        if (
            cleanup_result["deleted_from_redis"]
            or cleanup_result["deleted_from_postgres"]
        ):
            logger.info(
                f"🧹 Limpeza após metadata: Redis={len(cleanup_result['deleted_from_redis'])}, "
                f"Postgres={len(cleanup_result['deleted_from_postgres'])}, "
                f"Erros={len(cleanup_result['errors'])}"
            )
    except Exception as e:
        # Não bloquear o fluxo se houver erro na limpeza
        logger.warning(f"Erro na limpeza após metadata fetch: {e}", exc_info=True)

    # === FASE 2: Verificação de Cache em Paralelo ===
    cached_docs = {}
    missing_docs = []

    cache_tasks = []
    cache_indices = []

    for i, (token_len_metadata, doc_obj, proc_metadata) in enumerate(
        all_docs_with_proc_metadata
    ):
        if not is_document_paginated(doc_obj):
            cache_tasks.append(
                cache.get_document(
                    doc_obj.id_documento,
                    pag_ini=doc_obj.pag_doc_init,
                    pag_fim=doc_obj.pag_doc_end,
                    download_ext=doc_obj.download_ext,
                    id_anexos=doc_obj.id_anexos,
                )
            )
            cache_indices.append(i)
        else:
            missing_docs.append((i, token_len_metadata, doc_obj, proc_metadata))

    if cache_tasks:
        logger.debug(f"🔍 Verificando cache para {len(cache_tasks)} documentos")
        cache_results = await asyncio.gather(*cache_tasks, return_exceptions=True)

        for idx, result in zip(cache_indices, cache_results, strict=False):
            token_len_metadata, doc_obj, proc_metadata = all_docs_with_proc_metadata[
                idx
            ]
            if result and not isinstance(result, Exception):
                # Atualizar tokens com metadados do procedimento
                metadata_str = (
                    result["metadata"]
                    if isinstance(result["metadata"], str)
                    else str(result["metadata"])
                )
                result["doc_tokens"] = (
                    token_counter(result["content"])
                    + token_counter(metadata_str)
                    + 4
                    + token_len_metadata
                )
                cached_docs[idx] = result
                logger.debug(f"✓ Cache hit: {doc_obj.id_documento}")
            else:
                missing_docs.append((idx, token_len_metadata, doc_obj, proc_metadata))

    logger.info(f"✓ Cache: {len(cached_docs)} hits, {len(missing_docs)} misses")

    # === FASE 3: Fetch de Conteúdo em Paralelo ===
    async def process_missing_document(idx, token_len_metadata, doc_obj, proc_metadata):
        """Processa um documento que não está em cache."""
        async with document_semaphore:
            try:
                # Buscar conteúdo
                (
                    doc,
                    id_documento_formatado,
                    extra_metadata,
                ) = await get_doc_from_id_async(
                    doc_obj.id_documento,
                    doc_paged,
                    doc_obj.download_ext,
                    doc_metadata_map.get(doc_obj.id_documento),
                )

                # Processar anexos se houver
                if doc_obj.id_anexos:
                    logger.debug(
                        f"Processando anexos para documento {doc_obj.id_documento}: {doc_obj.id_anexos}"
                    )
                    anexo_tasks = [
                        get_doc_from_id_async(id_anexo, doc_paged, True)
                        for id_anexo in doc_obj.id_anexos
                    ]
                    anexo_results = await asyncio.gather(
                        *anexo_tasks, return_exceptions=True
                    )

                    for i, result in enumerate(anexo_results):
                        id_anexo = doc_obj.id_anexos[i]
                        if isinstance(result, Exception):
                            if isinstance(
                                result,
                                HTTPException411DocumentTimeout
                                | HTTPException412SeiApiTimeout,
                            ):
                                raise result
                            logger.warning(
                                f"Erro ao processar anexo {id_anexo}: {result}"
                            )
                        else:
                            doc_anexo, id_anexo_formatado, _ = result
                            doc += (
                                f"\n\n--- Anexo {id_anexo_formatado} ---\n{doc_anexo}"
                            )

                # Obter metadados (já buscados em batch)
                metadata_info = doc_metadata_map.get(doc_obj.id_documento, {})

                # Formatar documento
                doc = INTERMEDIATE_COMPLETATION_WITH_DOC.format(
                    id_documento_formatado=id_documento_formatado,
                    protocolo_processo=metadata_info.get("id_protocolo_formatado", ""),
                    doc=doc,
                )
                metadata_str = metadata_info.get("metadata_str", "")
                if extra_metadata:
                    extra_lines = "\n".join(
                        f"{k}: {v}" for k, v in extra_metadata.items()
                    )
                    metadata_str = (
                        f"{metadata_str}\n{extra_lines}"
                        if metadata_str
                        else extra_lines
                    )

                # Criar objeto de documento
                doc_object = ItemDocument(
                    id_documento=doc_obj.id_documento,
                    id_documento_formatado=id_documento_formatado,
                    content=doc,
                    doc_tokens=token_counter(doc)
                    + token_counter(metadata_str)
                    + 4
                    + token_len_metadata,
                    metadata=metadata_str,
                    download_ext=doc_obj.download_ext,
                    id_anexos=doc_obj.id_anexos,
                    sin_armazena_cache=metadata_info.get("sin_armazena_cache", "S"),
                )

                # Verificar se é documento paginado
                num_documento = id_documento_formatado
                if num_documento in id_docs_paged:
                    idx_doc_paged = id_docs_paged.index(num_documento)
                    doc_object["pag_doc_init"] = doc_paged[idx_doc_paged][1]
                    doc_object["pag_doc_end"] = doc_paged[idx_doc_paged][2]
                    if doc_object["pag_doc_init"]:
                        doc_object["doc_paged"] = True

                # Salvar no cache apenas se não for paginado
                if not is_document_paginated(doc_obj):
                    try:
                        await cache.set_document(
                            doc_object,
                            pag_ini=doc_obj.pag_doc_init,
                            pag_fim=doc_obj.pag_doc_end,
                            download_ext=doc_obj.download_ext,
                            id_anexos=doc_obj.id_anexos,
                        )
                        logger.debug(
                            f"✓ Documento {doc_obj.id_documento} armazenado no cache"
                        )
                    except Exception as e:
                        logger.warning(f"Erro ao armazenar documento no cache: {e}")

                return (idx, doc_object, None)

            except Exception as e:
                return (idx, None, e)

    # Executar processamento em paralelo
    if missing_docs:
        missing_tasks = [
            process_missing_document(idx, token_len, doc_obj, proc_meta)
            for idx, token_len, doc_obj, proc_meta in missing_docs
        ]
        missing_results = await asyncio.gather(*missing_tasks)
    else:
        missing_results = []

    # === FASE 4: Consolidação de Resultados ===
    all_results = {}
    for idx, doc in cached_docs.items():
        all_results[idx] = (doc, None)

    for idx, doc, error in missing_results:
        all_results[idx] = (doc, error)

    # Processar resultados finais
    documentos_processados = 0
    set_documentos_validos = set()

    for i, (_token_len_metadata, doc_obj, _proc_metadata) in enumerate(
        all_docs_with_proc_metadata
    ):
        doc_object, error = all_results.get(i, (None, None))
        documentos_processados += 1

        if error:
            # Tratar exceções
            if isinstance(
                error, HTTPException411DocumentTimeout | HTTPException412SeiApiTimeout
            ):
                logger.exception(
                    f"Timeout no documento {doc_obj.id_documento}: {error}"
                )
                user_state["last_status_code"] = error.status_code
                user_state["last_detail"] = error.detail
            elif isinstance(error, HTTPException204):
                logger.exception(f"Documento {doc_obj.id_documento} sem conteúdo")
            elif isinstance(
                error, HTTPException406 | HTTPException415 | HTTPException422
            ):
                user_state["last_status_code"] = error.status_code
                user_state["last_detail"] = error.detail
                logger.exception(
                    f"Erro ao processar documento {doc_obj.id_documento}: {error}"
                )
            else:
                logger.exception(
                    f"Erro inesperado ao processar documento {doc_obj.id_documento}: {error}"
                )

            # Definir valores seguros
            doc_obj.content = ""
            doc_obj.metadata = ""
            doc_obj.doc_tokens = 0
            doc_obj.id_documento_formatado = ""
            doc_obj.doc_paged = False

        elif doc_object:
            # Sucesso
            set_documentos_validos.add(doc_object["id_documento_formatado"])
            user_state["has_content"] = True
            user_state["all_tokens_counter"] += doc_object["doc_tokens"]

            # Atualizar objeto original
            doc_obj.id_documento_formatado = doc_object["id_documento_formatado"]
            doc_obj.content = doc_object["content"]
            doc_obj.metadata = doc_object["metadata"]
            doc_obj.doc_tokens = doc_object["doc_tokens"]
            doc_obj.doc_paged = doc_object.get("doc_paged", False)

            if doc_object.get("doc_paged", False):
                user_state["doc_paged"] = True

    # Verificar se todos falharam
    if documentos_processados > 0 and len(set_documentos_validos) == 0:
        logger.error(f"Todos os {documentos_processados} documentos estão sem conteúdo")
        raise HTTPException204(detail="Todos os documentos estão sem conteúdo")

    elapsed_time = time.time() - start_time
    logger.info(
        f"🚀 BATCH V3: Processados {len(set_documentos_validos)}/{documentos_processados} documentos "
        f"em {elapsed_time:.2f}s (média: {elapsed_time / documentos_processados:.2f}s/doc)"
    )

    return user_state


async def concatenate_documents(user_state: UserState) -> UserState:
    """Versão 2 da concatenação assíncrona de documentos com separação de processamento de procedimentos e documentos.

    Args:
        user_state: Estado do usuário contendo informações da sessão e documento.

    Returns:
        UserState: Estado do usuário com todos os documentos concatenados
    """
    logger.info("🚀 ASYNC V2: Iniciando concatenação assíncrona de documentos")

    _stream_writer = None
    with contextlib.suppress(Exception):
        _stream_writer = get_stream_writer()
        _stream_writer({"_status": "Processando documentos"})

    # Etapa 1: Processar procedimento (metadados e validações)
    user_state = await process_procedimento_async(user_state)

    # Etapa 2: Processar documentos do procedimento
    user_state = await concatenate_procedimento_documents_async(
        document_semaphore=asyncio.Semaphore(settings.SEI_API_SEMAPHORE),
        user_state=user_state,
    )

    if _stream_writer is not None:
        with contextlib.suppress(Exception):
            _stream_writer({"_status": "Documentos processados"})

    logger.info("🚀 ASYNC V2: Finalizada a concatenação assíncrona dos documentos")
    return user_state


async def initialize_document_processing_state(_: UserState) -> dict:
    """Inicializa o estado de documentos sem inferir paginação a partir do prompt."""

    return {"doc_paged": []}

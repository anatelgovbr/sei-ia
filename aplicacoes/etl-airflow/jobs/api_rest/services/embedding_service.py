"""Serviço para geração de embeddings de documentos."""

import logging
from pathlib import Path

from langchain.text_splitter import RecursiveCharacterTextSplitter as RecursiveSplitter
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from jobs.db_models.embedding import EmbeddingsTable, get_embeddings_db_connector
from jobs.envs import (
    CHUNK_OVERLAP,
    DB_SEIIA_ASSISTENTE_SCHEMA,
    EMBEDDINGS_TABLE_NAME,
    MAX_LENGTH_CHUNK_SIZE,
)
from jobs.services.embedder.embedding_generator import EmbeddingGenerator, InputPoolEmbd

logger = logging.getLogger(__name__)

SEPARATORS = [
    "\n\n",
    "\n",
    ".",
    ",",
    "\u200b",
    "\uff0c",
    "\u3001",
    "\uff0e",
    "\u3002",
    "",
]

embedding_generator = EmbeddingGenerator()


def split_chunks(
    doc: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: list[str] = SEPARATORS,
    *,
    return_positions: bool = False,
) -> tuple[list[str], list[tuple[int, int]]]:
    """Funcao para dividir o texto em chunks.

    Args:
        doc: Texto a ser dividido.
        chunk_size (int): Tamanho do chunk (padrão é 400).
        chunk_overlap (int): Sobreposição entre chunks (padrão é 50).
        separators (list): Lista de separadores (padrão é lista especificada)
        return_positions (bool): Se deve retornar as posicoes dos chunks
            (padrão é False).

    Returns:
        tuple: (lista de chunks, lista de posições)
    """
    logger.debug("entrou no split_chunks")
    if embedding_generator.provider.tokenizer_type == "huggingface":
        text_splitter = RecursiveSplitter.from_huggingface_tokenizer(
            tokenizer=embedding_generator.provider.get_tokenizer(),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
        )
    if embedding_generator.provider.tokenizer_type == "tiktoken":
        text_splitter = RecursiveSplitter.from_tiktoken_encoder(
            model_name=embedding_generator.provider.base_model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
        )

    chunks = text_splitter.split_text(doc)
    positions = []

    if return_positions:
        for chunk in chunks:
            start = doc.find(chunk)
            if start != -1:
                end = start + len(chunk)
                positions.append((start, end))
        return chunks, positions

    return chunks, positions


async def check_embeddings_exist(id_documentos: list[str]) -> dict[str, bool]:
    """Verifica quais documentos já possuem embeddings no banco.

    Args:
        id_documentos: Lista de IDs de documentos

    Returns:
        dict: Mapeamento id_documento -> bool (True se existe)
    """
    connector = get_embeddings_db_connector()

    # Converter IDs para inteiros
    doc_ids_int = [int(doc_id) for doc_id in id_documentos]

    # Query SQL direta para buscar documentos existentes

    sql = f"""
        SELECT DISTINCT id_documento
        FROM {DB_SEIIA_ASSISTENTE_SCHEMA}.{EMBEDDINGS_TABLE_NAME}
        WHERE id_documento IN ({",".join(map(str, doc_ids_int))})
    """  # noqa: S608

    # Usar método async
    df = await connector.select_async(sql)
    existing_ids = {str(int(row["id_documento"])) for _, row in df.iterrows()}

    # Criar dicionário com todos os IDs solicitados
    return {doc_id: doc_id in existing_ids for doc_id in id_documentos}


async def process_document_for_embedding(
    id_documento: str, content: str, req_filepath: Path
) -> None:
    """Processa um documento, gerando chunks e adicionando ao pool de embedding.

    Args:
        id_documento: ID do documento a ser processado.
        content: Conteúdo do documento.
        req_filepath: Caminho do arquivo temporário para o pool.
    """
    logger.info(f"Processando documento {id_documento} para embedding")

    # Gerar chunks
    content_splitted, positions = split_chunks(
        content,
        chunk_size=MAX_LENGTH_CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        return_positions=True,
    )

    logger.debug(f"Documento {id_documento}: {len(content_splitted)} chunks gerados")

    # Adicionar ao pool
    pool_input = InputPoolEmbd(
        input_texts=content_splitted,
        doc_id=id_documento,
        chunk_ids=list(range(len(content_splitted))),
        positions=positions,
    )
    embedding_generator.append_pool_file(pool_input, req_filepath)


async def save_embeddings_to_db(result_file: list) -> None:
    """Salva os embeddings no banco de dados.

    Args:
        result_file: Lista de resultados de embedding.
    """
    # Coleta todos os registros para inserção em lote
    unique_rows: dict[tuple[int, int], dict] = {}

    for line in result_file:
        data = line["request"]
        embeddings = line["response"]
        for idx in range(len(embeddings)):
            doc_id = int(data["doc_ids"][idx])
            chunk_id = data["chunk_ids"][idx]
            row_key = (doc_id, chunk_id)

            unique_rows[row_key] = {
                "chunk_id": chunk_id,
                "id_documento": doc_id,
                "embedding": embeddings[idx],
                "start_position": data["positions"][idx][0],
                "finished_position": data["positions"][idx][1],
            }

    rows = list(unique_rows.values())

    if not rows:
        logger.info("Nenhum embedding para salvar no banco de dados")
        return

    logger.debug(
        f"Inserindo {len(rows)} embeddings em lote no banco de dados via upsert"
    )

    table = EmbeddingsTable.__table__
    stmt = insert(table).values(rows)
    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.id_documento, table.c.chunk_id],
        set_={
            "embedding": stmt.excluded.embedding,
            "start_position": stmt.excluded.start_position,
            "finished_position": stmt.excluded.finished_position,
        },
    )

    # Usar AsyncDbConnector
    connector = get_embeddings_db_connector()
    session = connector.get_session()
    try:
        session.execute(upsert_stmt)
        session.commit()
        logger.info(f"✓ {len(rows)} embeddings salvos no banco de dados")
    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("Falha ao inserir embeddings em lote", exc_info=True)
        msg = f"Erro ao salvar embeddings: {exc}"
        raise RuntimeError(msg) from exc
    finally:
        session.close()


async def generate_embeddings_for_documents(id_documentos: list[str]) -> dict:
    """Gera embeddings para uma lista de documentos.

    Args:
        id_documentos: Lista de IDs de documentos

    Returns:
        dict: Resultado do processamento
    """
    logger.info(f"Iniciando geração de embeddings para {len(id_documentos)} documentos")

    # Verificar quais documentos já têm embeddings
    existing_embeddings = await check_embeddings_exist(id_documentos)
    docs_to_process = [
        doc_id for doc_id, exists in existing_embeddings.items() if not exists
    ]
    docs_skipped = [doc_id for doc_id, exists in existing_embeddings.items() if exists]

    logger.info(
        f"Documentos a processar: {len(docs_to_process)}, "
        f"já existentes: {len(docs_skipped)}"
    )

    if not docs_to_process:
        return {
            "status": "already_exists",
            "processed_count": 0,
            "skipped_count": len(docs_skipped),
            "skipped_ids": docs_skipped,
            "embeddings": [],
        }

    # Criar arquivos temporários
    req_filepath, save_filepath = embedding_generator.create_temp_files()

    try:
        # Buscar conteúdo dos documentos via SEI API usando o novo sistema de leitura
        logger.info(
            f"Buscando conteúdo de {len(docs_to_process)} documentos via SEI API"
        )

        # Importar o novo módulo de leitura de documentos
        from jobs.document_extraction.document_reader import get_document_content

        # Usar método assíncrono para buscar conteúdo de múltiplos documentos
        contents_map = {}
        for doc_id in docs_to_process:
            try:
                # Usar o novo sistema de leitura que suporta documentos
                # internos e externos
                content = await get_document_content(doc_id)
                if content:
                    contents_map[doc_id] = content
                else:
                    logger.warning(f"Documento {doc_id} sem conteúdo")
            except Exception as e:
                logger.exception(f"Erro ao buscar documento {doc_id}: {e}")

        logger.info(f"Conteúdo obtido para {len(contents_map)} documentos")

        # Processar cada documento
        for doc_id, content in contents_map.items():
            await process_document_for_embedding(doc_id, content, req_filepath)

        # Gerar embeddings (implementação simplificada - na prática usaria async pool)
        logger.info("Gerando embeddings...")
        result_file = await generate_embeddings_from_pool(req_filepath, save_filepath)

        # Salvar no banco
        await save_embeddings_to_db(result_file)

        # Preparar resposta
        embeddings_info = []
        for doc_id in contents_map:
            # Contar chunks do documento
            chunks_count = sum(
                1
                for line in result_file
                for data_doc_id in line["request"]["doc_ids"]
                if data_doc_id == doc_id
            )
            embeddings_info.append(
                {"id_documento": doc_id, "chunks_count": chunks_count}
            )

        return {
            "status": "processed",
            "processed_count": len(contents_map),
            "skipped_count": len(docs_skipped),
            "skipped_ids": docs_skipped,
            "embeddings": embeddings_info,
        }

    finally:
        # Limpar arquivos temporários
        try:
            Path.unlink(req_filepath)
            Path.unlink(save_filepath)
        except FileNotFoundError:
            pass


async def generate_embeddings_from_pool(
    req_filepath: Path, save_filepath: Path
) -> list:
    """Gera embeddings a partir de um arquivo de pool.

    Args:
        req_filepath: Caminho do arquivo de requisições
        save_filepath: Caminho do arquivo de resultados

    Returns:
        list: Lista de resultados com embeddings
    """
    import json

    result_file = []

    # Ler arquivo de requisições
    with req_filepath.open("r") as f:
        for line in f:
            request_data = json.loads(line.strip())

            # Gerar embeddings para este batch
            embeddings = embedding_generator.generate(request_data["input_texts"])

            result = {"request": request_data, "response": embeddings}
            result_file.append(result)

            # Salvar resultado no arquivo
            with save_filepath.open("a") as save_f:
                save_f.write(json.dumps(result) + "\n")

    return result_file


async def delete_embeddings_by_document_ids(id_documentos: list[int]) -> int:
    """Remove embeddings de documentos do banco de dados PostgreSQL.

    Args:
        id_documentos: Lista de IDs de documentos cujos embeddings devem ser removidos

    Returns:
        int: Quantidade de registros removidos

    Raises:
        RuntimeError: Em caso de erro na execução da query
    """
    if not id_documentos:
        logger.info("Nenhum documento para remover embeddings")
        return 0

    doc_ids_int = [int(doc_id) for doc_id in id_documentos]

    ids_str = ",".join(map(str, doc_ids_int))

    sql = f"""
        DELETE FROM {DB_SEIIA_ASSISTENTE_SCHEMA}.{EMBEDDINGS_TABLE_NAME}
        WHERE id_documento IN ({ids_str})
    """  # noqa: S608

    logger.info(f"Removendo embeddings de {len(doc_ids_int)} documentos")

    connector = get_embeddings_db_connector()

    try:
        if not connector.pool:
            await connector.connect()

        async with connector.pool.acquire() as conn:
            status = await conn.execute(sql)
            rows_deleted = int(status.split()[-1]) if status and " " in status else 0

        logger.info(f"✓ {rows_deleted} embeddings removidos do banco de dados")
        return rows_deleted

    except Exception as exc:
        logger.error(f"Erro ao remover embeddings: {exc}", exc_info=True)
        msg = f"Falha ao remover embeddings: {exc}"
        raise RuntimeError(msg) from exc

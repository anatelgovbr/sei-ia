"""Modulo de Embedding para RAG."""

import json
import logging
from pathlib import Path

from langchain.text_splitter import RecursiveCharacterTextSplitter as RecursiveSplitter
from sqlalchemy.dialects.postgresql import insert

from sei_ia.configs.settings_config import settings
from sei_ia.data.database.db_instances import app_db_instance
from sei_ia.data.database.db_models.embedding import EmbeddingsTable
from sei_ia.data.database.query_templates.rag import SQL_HAS_DOCUMENT_EMBEDDING
from sei_ia.data.etl.text_preprocess import html_to_markdown
from sei_ia.data.pydantic_models import ItemDocumentRequest, UserState
from sei_ia.services.embedder.content_cleaner import clean_document_content
from sei_ia.services.embedder.embedding_generator import (
    EmbeddingGenerator,
    InputPoolEmbd,
)
from sei_ia.services.exceptions.http_exceptions import (
    HTTPException204,
    HTTPException404,
    HTTPException409,
    HTTPException415,
    HTTPException500,
)

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
) -> list:
    """Funcao para dividir o texto em chunks.

    Args:
        doc: Texto a ser dividido.
        chunk_size (int): Tamanho do chunk (padrão é 400).
        chunk_overlap (int): Sobreposição entre chunks (padrão é 50).
        separators (list): Lista de separadores (padrão é a lista especificada)
        return_positions (bool): Se deve retornar as posicoes dos chunks (padrão é False).

    Returns:
        list: Lista de chunks do texto.
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
            model_name=embedding_generator.provider.tokenizer_model,
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


async def get_document_state_by_id(
    item_doc_trigger: str, user_state: UserState
) -> ItemDocumentRequest | None:
    """Localiza um documento pelo seu ID nos procedimentos do usuário.

    Args:
        item_doc_trigger (str): ID do documento a ser localizado.
        user_state (UserState): Estado do usuário contendo informações de contexto e documentos.

    Returns:
        ItemDocumentRequest | None: Documento encontrado ou None se não for encontrado.
    """
    for item_proc in user_state["id_procedimentos"]:
        for doc in item_proc.id_documentos:
            if doc.id_documento == item_doc_trigger:
                return doc
    return None


async def process_document(item_doc: ItemDocumentRequest, req_filepath: Path) -> None:
    """Processa um documento, gerando chunks e adicionando ao pool de embedding.

    Args:
        item_doc (ItemDocumentRequest): Documento a ser processado.
        req_filepath (Path): Caminho do arquivo temporário para o pool.
    """
    try:
        cleaned_content = clean_document_content(item_doc.content)
        content_markdown = html_to_markdown(cleaned_content)
    except ValueError as e:
        # Se limpeza falhar, lançar erro crítico - não pular silenciosamente
        error_msg = f"Documento {item_doc.id_documento} tem conteúdo inválido que não pode ser processado: {e}"
        logger.error(error_msg)
        raise HTTPException500(detail=error_msg) from e
    content_splitted, positions = split_chunks(
        content_markdown,
        chunk_size=settings.MAX_LENGTH_CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        return_positions=True,
    )
    pool_input = InputPoolEmbd(
        input_texts=content_splitted,
        doc_id=item_doc.id_documento,
        chunk_ids=list(range(len(content_splitted))),
        positions=positions,
    )
    embedding_generator.append_pool_file(pool_input, req_filepath)


async def read_embedding_results(save_filepath: Path) -> list:
    """Lê os resultados do arquivo de embeddings.

    Args:
        save_filepath (Path): Caminho do arquivo com os embeddings.

    Returns:
        list: Lista de resultados de embedding.
    """
    result_file = []
    try:
        with save_filepath.open("r") as file:
            for line_number, line in enumerate(file, start=1):
                try:
                    result_file.append(json.loads(line.strip()))
                except json.JSONDecodeError as e:
                    raise HTTPException500(
                        detail=f"Erro ao decodificar JSON na linha {line_number}: {e.msg}. Linha: {line.strip()}"
                    ) from e
    except FileNotFoundError as e:
        raise HTTPException500(detail=f"Arquivo {save_filepath} não encontrado.") from e
    return result_file


async def save_embeddings_to_db(result_file: list) -> None:
    """Salva os embeddings no banco de dados.

    Args:
        result_file (list): Lista de resultados de embedding.
    """
    # Coleta todos os doc_ids únicos primeiro para otimizar chamadas HTTP
    all_doc_ids = set()
    for line in result_file:
        data = line["request"]
        all_doc_ids.update(data["doc_ids"])

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

    if not app_db_instance.async_engine:
        error_msg = "AsyncEngine não está inicializado. Verifique a configuração do banco de dados."
        logger.error(error_msg)
        raise HTTPException500(detail=error_msg)

    try:
        async with app_db_instance.async_engine.connect() as conn:
            async with conn.begin():
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
                await conn.execute(upsert_stmt)
            logger.debug("✓ Embeddings salvos com sucesso usando AsyncEngine")
    except Exception as exc:
        logger.error("Falha ao inserir embeddings em lote (async)", exc_info=True)
        raise HTTPException500(detail=f"Erro ao salvar embeddings: {exc}") from exc


async def indexing_embeddings(
    list_to_trigger: list[str], user_state: UserState
) -> None:
    """Executa de fato a indexação dos embeddings V2.

    Args:
        list_to_trigger (list[str]): Lista de ids para trigger do indexing_embeddings.
        user_state (UserState): Estado do usuário contendo informações de contexto e documentos.
    """
    logger.debug(f"Entrou no indexing_embeddings: {list_to_trigger}")
    req_filepath, save_filepath = embedding_generator.create_temp_files()

    for item_doc_trigger in list_to_trigger:
        item_doc_selected = await get_document_state_by_id(item_doc_trigger, user_state)
        if item_doc_selected:
            try:
                await process_document(item_doc_selected, req_filepath)
            except (
                HTTPException204,
                HTTPException404,
                HTTPException409,
                HTTPException415,
            ) as e:
                logger.warning(
                    f"Documento {item_doc_selected.id_documento} \n Exception: {e}"
                )

    await embedding_generator.async_generate_from_pool(req_filepath, save_filepath)
    result_file = await read_embedding_results(save_filepath)
    await save_embeddings_to_db(result_file)

    try:
        Path.unlink(req_filepath)
        Path.unlink(save_filepath)
    except FileNotFoundError:
        pass


async def check_reindex_embedding(id_documentos: list[str]) -> dict:
    """Checa documentos precisam ser reindexados.

    Args:
        id_documentos (list[str]): IDs dos documentos liberados.

    Returns:
        dict: Dict com ids dos documentos que precisam ser reindexados.
    """
    logger.debug("Entrou no check_reindex_embedding")

    where_id_documento = "AND id_documento IN ({})".format(",".join(id_documentos))
    sql = SQL_HAS_DOCUMENT_EMBEDDING.format(where_id_documento=where_id_documento)

    # Validação obrigatória: AsyncEngine DEVE estar disponível
    if not app_db_instance.async_engine:
        error_msg = "AsyncEngine não está inicializado. Verifique a configuração do banco de dados."
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    documents_df = await app_db_instance.select_native_async(sql)
    documents = documents_df.to_dict(orient="records")

    # Verificar quais documentos já existem no banco
    existing_docs = {str(d["id_documento"]) for d in documents}

    reindex_ids = {}

    for id_doc in id_documentos:
        if id_doc not in existing_docs:
            # Documento não existe no banco de dados, precisa ser reindexado
            logger.debug(
                f"Documento {id_doc} não existe no banco de dados, precisa ser reindexado"
            )
            reindex_ids[id_doc] = None
        else:
            # Documento existe no banco, será reindexado (sem verificação de hash)
            logger.debug(f"Documento {id_doc} encontrado no BD")

    return reindex_ids

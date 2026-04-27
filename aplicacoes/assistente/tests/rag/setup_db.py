"""
Helper module para inicializar tabelas de banco de dados nos testes RAG.
"""

import logging

from sei_ia.data.database.db_instances import app_db_instance
from sei_ia.data.database.table_manager import TableManager

logger = logging.getLogger(__name__)


def initialize_test_database():
    """
    Inicializa as tabelas necessárias para os testes RAG.

    Esta função deve ser chamada no início de cada script de teste RAG
    para garantir que as tabelas de embeddings existam antes dos testes.
    """
    try:
        logger.info("=" * 80)
        logger.info("🔧 Inicializando tabelas de banco de dados para testes RAG")
        logger.info("=" * 80)

        # Criar TableManager
        table_manager = TableManager(app_db_instance)

        logger.info(f"📋 Schema: {table_manager.schema}")
        logger.info(f"📋 Table name: {table_manager.embeddings_table_name}")
        logger.info(f"📋 Full table name: {table_manager.full_table_name}")

        # Verificar se a tabela já existe
        exists = table_manager.check_table_exists()

        if exists:
            logger.info(f"✅ Tabela {table_manager.full_table_name} já existe")
        else:
            logger.info(
                f"⚠️  Tabela {table_manager.full_table_name} não existe, criando..."
            )

            # Criar a tabela
            success = table_manager.create_embeddings_table()

            if success:
                logger.info(
                    f"✅ Tabela {table_manager.full_table_name} criada com sucesso!"
                )

                # Verificar novamente
                exists = table_manager.check_table_exists()
                if not exists:
                    logger.error("❌ ERRO: Tabela não foi encontrada após criação!")
                    return False
            else:
                logger.error(
                    f"❌ Falha ao criar tabela {table_manager.full_table_name}"
                )
                return False

        logger.info("=" * 80)
        logger.info("✅ Banco de dados pronto para testes RAG")
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error(f"❌ Erro ao inicializar banco de dados: {e}", exc_info=True)
        return False


# Executar automaticamente quando o módulo for importado
# Isso garante que as tabelas sejam criadas ao importar este módulo
if __name__ != "__main__":
    initialize_test_database()

#!/usr/bin/env python3
"""
Script de exemplo e validação do sistema de cache Redis.

Este script demonstra como usar o sistema de cache e valida sua funcionalidade.
"""

import asyncio
import logging
import time

from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import ItemDocument
from sei_ia.services.cache import get_cache

setup_logging()
logger = logging.getLogger(__name__)


def create_sample_document(doc_id: str, content_size: int = 1000) -> ItemDocument:
    """Cria um documento de exemplo para teste."""
    content = f"Conteúdo de exemplo para documento {doc_id}. " * content_size

    return ItemDocument(
        {
            "id_documento": doc_id,
            "id_documento_formatado": f"{doc_id}_formatado",
            "content": content,
            "metadata": {
                "tipo": "exemplo",
                "tamanho": len(content),
                "timestamp": time.time(),
            },
            "doc_tokens": len(content.split()),
            "doc_paged": False,
            "pag_doc_init": None,
            "pag_doc_end": None,
            "download_ext": False,
            "id_anexos": None,
        }
    )


async def test_cache_operations():
    """Testa operações básicas do cache."""
    print("\n🧪 Testando operações básicas do cache...")

    cache = get_cache()

    # Criar documento de exemplo
    doc_id = "12345"
    sample_doc = create_sample_document(doc_id)

    # Limpar cache do documento de teste antes de começar
    await cache.delete_document(doc_id)

    print(f"📄 Documento criado: {doc_id}")

    # Testar cache miss
    print("🔍 Testando cache miss...")
    start_time = time.time()
    cached_doc = await cache.get_document(doc_id)
    miss_time = time.time() - start_time

    if cached_doc is None:
        print(f"✅ Cache miss confirmado em {miss_time:.4f}s")
    else:
        print("❌ Esperava cache miss, mas encontrou documento")
        return False

    # Armazenar no cache
    print("💾 Armazenando documento no cache...")
    start_time = time.time()
    success = await cache.set_document(sample_doc)
    set_time = time.time() - start_time

    if success:
        print(f"✅ Documento armazenado em {set_time:.4f}s")
    else:
        print("❌ Falha ao armazenar documento")
        return False

    # Testar cache hit
    print("🎯 Testando cache hit...")
    start_time = time.time()
    cached_doc = await cache.get_document(doc_id)
    hit_time = time.time() - start_time

    if cached_doc is not None:
        print(f"✅ Cache hit confirmado em {hit_time:.4f}s")
        print(f"📊 Speedup: {miss_time / hit_time:.2f}x mais rápido")

        # Validar conteúdo
        if cached_doc["id_documento"] == sample_doc["id_documento"]:
            print("✅ Conteúdo do cache válido")
        else:
            print("❌ Conteúdo do cache inválido")
            return False
    else:
        print("❌ Esperava cache hit, mas não encontrou documento")
        return False

    return True


async def test_cache_with_parameters():
    """Testa cache com diferentes parâmetros."""
    print("\n🧪 Testando cache com parâmetros...")

    cache = get_cache()
    doc_id = "67890"

    # Criar documento base
    base_doc = create_sample_document(doc_id)

    # Testar com diferentes parâmetros
    test_cases = [
        {"pag_ini": None, "pag_fim": None, "download_ext": None, "id_anexos": None},
        {"pag_ini": 1, "pag_fim": 5, "download_ext": None, "id_anexos": None},
        {"pag_ini": None, "pag_fim": None, "download_ext": True, "id_anexos": None},
        {
            "pag_ini": None,
            "pag_fim": None,
            "download_ext": None,
            "id_anexos": ["111", "222"],
        },
    ]

    for i, params in enumerate(test_cases):
        print(f"📋 Caso de teste {i + 1}: {params}")

        # Armazenar
        success = await cache.set_document(base_doc, **params)
        if not success:
            print(f"❌ Falha ao armazenar caso {i + 1}")
            continue

        # Recuperar
        cached_doc = await cache.get_document(doc_id, **params)
        if cached_doc:
            print(f"✅ Caso {i + 1} armazenado e recuperado com sucesso")
        else:
            print(f"❌ Caso {i + 1} falhou na recuperação")
            return False

    return True


async def test_cache_performance():
    """Testa performance do cache com múltiplos documentos."""
    print("\n🧪 Testando performance do cache...")

    cache = get_cache()
    num_docs = 50
    batch_size = 5  # Processar em lotes menores para evitar "too many connections"

    # Criar documentos
    documents = [create_sample_document(f"perf_{i}", 100) for i in range(num_docs)]

    # Testar armazenamento em lotes
    print(f"💾 Armazenando {num_docs} documentos em lotes de {batch_size}...")
    start_time = time.time()

    store_results = []
    for i in range(0, num_docs, batch_size):
        batch = documents[i : i + batch_size]
        batch_tasks = [cache.set_document(doc) for doc in batch]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        store_results.extend(batch_results)
        # Pequena pausa entre lotes para evitar sobrecarga
        await asyncio.sleep(0.01)

    store_time = time.time() - start_time
    successful_stores = sum(1 for r in store_results if r is True)

    print(
        f"✅ {successful_stores}/{num_docs} documentos armazenados em {store_time:.2f}s"
    )
    print(f"📊 Taxa: {successful_stores / store_time:.1f} docs/segundo")

    # Testar recuperação em lotes
    print(f"🎯 Recuperando {num_docs} documentos em lotes de {batch_size}...")
    start_time = time.time()

    fetch_results = []
    for i in range(0, num_docs, batch_size):
        batch_tasks = [
            cache.get_document(f"perf_{j}")
            for j in range(i, min(i + batch_size, num_docs))
        ]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        fetch_results.extend(batch_results)
        # Pequena pausa entre lotes
        await asyncio.sleep(0.01)

    fetch_time = time.time() - start_time
    successful_fetches = sum(
        1 for r in fetch_results if r is not None and not isinstance(r, Exception)
    )

    print(
        f"✅ {successful_fetches}/{num_docs} documentos recuperados em {fetch_time:.2f}s"
    )
    print(f"📊 Taxa: {successful_fetches / fetch_time:.1f} docs/segundo")

    return successful_stores == num_docs and successful_fetches == num_docs


async def test_cache_stats():
    """Testa estatísticas do cache."""
    print("\n🧪 Testando estatísticas do cache...")

    cache = get_cache()
    stats = await cache.get_stats()

    print("📊 Estatísticas do cache:")
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print(f"✅ Hit ratio: {stats.get('hit_ratio', 0):.2%}")

    return True


async def run_validation():
    """Executa validação completa do sistema de cache."""
    print("🚀 Iniciando validação do sistema de cache Redis...")

    try:
        # Executar testes
        tests = [
            ("Operações básicas", test_cache_operations),
            ("Parâmetros diferentes", test_cache_with_parameters),
            ("Performance", test_cache_performance),
            ("Estatísticas", test_cache_stats),
        ]

        results = []
        for test_name, test_func in tests:
            try:
                print(f"\n{'=' * 50}")
                print(f"🧪 TESTE: {test_name}")
                print(f"{'=' * 50}")

                result = await test_func()
                results.append((test_name, result))

                if result:
                    print(f"✅ {test_name}: PASSOU")
                else:
                    print(f"❌ {test_name}: FALHOU")

            except Exception as e:
                print(f"❌ {test_name}: ERRO - {e}")
                results.append((test_name, False))

        # Resumo final
        print(f"\n{'=' * 50}")
        print("📋 RESUMO DOS TESTES")
        print(f"{'=' * 50}")

        passed = sum(1 for _, result in results if result)
        total = len(results)

        for test_name, result in results:
            status = "✅ PASSOU" if result else "❌ FALHOU"
            print(f"{test_name}: {status}")

        print(f"\n🎯 Resultado: {passed}/{total} testes passaram")

        if passed == total:
            print(
                "🎉 Todos os testes passaram! Sistema de cache funcionando corretamente."
            )
            return True
        else:
            print("⚠️ Alguns testes falharam. Verificar logs para detalhes.")
            return False

    except Exception as e:
        print(f"❌ Erro durante validação: {e}")
        return False
    finally:
        # Limpeza
        try:
            cache = get_cache()
            await cache.close()
        except Exception:
            pass


if __name__ == "__main__":
    # Executar validação
    success = asyncio.run(run_validation())
    exit(0 if success else 1)

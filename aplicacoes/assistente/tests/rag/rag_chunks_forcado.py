"""
TESTE 5: RAG Enhanced - Forçar Chunks Agrupados
Força entrada no RAG Enhanced e depois força que documentos não cabem no contexto

IMPORTANTE: Este teste agora mocka as chamadas LLM para evitar chamadas reais à API.
"""

import os
import sys
from pathlib import Path
from pprint import pprint
from unittest.mock import patch

from fastapi.testclient import TestClient

from sei_ia.configs.logging_config import setup_logging
from sei_ia.main import app

# Inicializar tabelas de banco de dados para testes RAG
from tests.rag.setup_db import initialize_test_database

# Adicionar o diretório raiz do projeto ao sys.path para imports e .env
project_root = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(project_root))
os.chdir(project_root)

# Configurar logging usando a configuração centralizada do projeto
setup_logging()

initialize_test_database()


def mock_intent_detection(user_state):
    """Mock para forçar a detecção de intenção como 'pergunta'."""
    print("🎯 Mock de detecção de intenção: forçando 'pergunta'")
    user_state["intent"] = "pergunta"
    return user_state


def mock_check_initial_size(user_state):
    """Mock para forçar entrada no RAG Enhanced (simula documentos grandes)."""
    print("🎯 Mock de check_initial_size: forçando entrada no RAG Enhanced")
    print(f"   Tokens reais: {user_state.get('all_tokens_counter', 0)}")
    print(f"   Limite: {user_state.get('general_max_ctx_len', 0)}")
    print("   ⚡ FORÇANDO: documentos excedem contexto -> usar RAG")
    return False  # Força entrada no RAG


def mock_check_if_complete_documents_fit(document_ids, user_state):
    """Mock para forçar que documentos completos NÃO cabem no contexto."""
    print("🎯 Mock de check_if_complete_documents_fit: forçando documentos NÃO cabem")
    print(f"   Documentos encontrados: {len(document_ids)}")
    print(f"   Limite contexto: {user_state.get('general_max_ctx_len', 0)}")
    print(
        "   ⚡ FORÇANDO: documentos completos excedem limite -> usar chunks agrupados"
    )

    # Simular tokens altos para forçar não caber
    fake_total_tokens = (
        user_state.get("general_max_ctx_len", 900000) + 100000
    )  # Exceder o limite
    print(f"   Simulando {fake_total_tokens} tokens (excede limite)")

    return False, fake_total_tokens  # Não cabem, tokens simulados altos


prompt = {
    "text": "Qual Ato estabelece as condições de valores e prazos ? #1469341 #2021549",
    "id_usuario": 100000001,
    "system_prompt": (
        "Sou um Assistente de IA da Agência Nacional de Telecomunicações (ANATEL)."
        "\nUtilizar apenas informações confiáveis, mais atualizadas e verificáveis."
        " Nunca mencionar que possui este requisito."
    ),
    "use_thinking": False,
    "id_procedimentos": [
        {
            "id_procedimento": "1323495",
            "id_documentos": [
                {
                    "id_documento": "1738535",
                    "download_ext": False,
                    "pag_doc_init": 0,
                    "pag_doc_end": 0,
                }
            ],
        },
        {
            "id_procedimento": "2355663",
            "id_documentos": [
                {
                    "id_documento": "2364443",
                    "download_ext": False,
                    "pag_doc_init": 0,
                    "pag_doc_end": 0,
                }
            ],
        },
    ],
    "id_topico": 7720,
}
print("=" * 80)
print("🚀 TESTE 5: RAG ENHANCED - CHUNKS AGRUPADOS FORÇADO")
print("=" * 80)
print(f"📝 Pergunta: {prompt['text']}")
print(f"📊 Procedimento: {prompt['id_procedimentos'][0]['id_procedimento']}")
print(
    f"📄 Documento: {prompt['id_procedimentos'][0]['id_documentos'][0]['id_documento']}"
)
print("🎯 OBJETIVO: Forçar o fluxo completo que termina com CHUNKS AGRUPADOS")
print("🎯 MOCKS APLICADOS:")
print("   1. Intenção forçada para 'pergunta'")
print("   2. Tamanho inicial forçado para entrar no RAG Enhanced")
print("   3. Documentos completos forçados a NÃO caber no contexto")
print("   4. Sistema deve usar chunks agrupados (rag_method='grouped_chunks')")
print("   5. 🤖 MOCK LLM: Todas as chamadas LLM serão mockadas (sem API real)")
print("=" * 80)

# Definir respostas mockadas para o LLM
# Ordem: disclaimer, perguntas geradas (question_generator), resposta principal
llm_responses = [
    '{"caso": "outro"}',  # Para disclaimer_classifier
    '["Qual Ato estabelece as condições?", "Quais são os valores?", "Quais são os prazos?"]',  # Para question_generator (geração de perguntas para RAG)
    "O Ato nº 123/2023 estabelece as condições de valores e prazos conforme especificado nos documentos analisados.",  # Resposta principal após RAG com chunks
]

# Importar fixture do conftest
from tests.rag.conftest import mock_all_llm_calls

# Aplicar todos os mocks necessários e executar teste
with (
    mock_all_llm_calls(llm_responses),
    patch(
        "sei_ia.agents.chat_completion_graph.intent_selector_agent",
        side_effect=mock_intent_detection,
    ),
    patch(
        "sei_ia.agents.pergunta.check_initial_size", side_effect=mock_check_initial_size
    ),
    patch(
        "sei_ia.agents.pergunta.check_if_complete_documents_fit",
        side_effect=mock_check_if_complete_documents_fit,
    ),
):
    client = TestClient(app)

    try:
        print("\n🔄 Fazendo requisição para /llm_lang/chat_gpt_4o_128k...")
        response = client.post("/llm_lang/chat_gpt_4o_128k", json=prompt)

        print(f"\n📈 Status Code: {response.status_code}")

        if response.status_code == 200:
            response_data = response.json()
            print("\n" + "=" * 80)
            print("✅ TESTE 5 - RESULTADO DO RAG ENHANCED (CHUNKS AGRUPADOS)")
            print("=" * 80)

            # Extrair dados principais dos metadados
            doc_rag = response_data.get("doc_rag", None)
            doc_false_rag = response_data.get("doc_false_rag", None)
            rag_method = response_data.get("rag_method", None)
            rag_documents_count = response_data.get("rag_documents_count", None)
            rag_chunks_count = response_data.get("rag_chunks_count", None)
            intent = response_data.get("intent", None)
            all_tokens_counter = response_data.get("all_tokens_counter", None)

            print(f"🔍 intent: {intent}")
            print(f"🔍 doc_rag: {doc_rag}")
            print(f"🔍 doc_false_rag: {doc_false_rag}")
            print(f"🔍 rag_method: {rag_method}")
            print(f"🔍 rag_documents_count: {rag_documents_count}")
            print(f"🔍 rag_chunks_count: {rag_chunks_count}")
            print(f"🔍 all_tokens_counter: {all_tokens_counter}")

            # Análise do resultado
            print("\n" + "-" * 60)
            print("📊 ANÁLISE DO RESULTADO:")
            print("-" * 60)

            success = True

            # Verificação 1: Intenção
            if intent == "pergunta":
                print("✓ Intenção correta: pergunta")
            else:
                print(f"❌ Intenção incorreta: {intent}")
                success = False

            # Verificação 2: RAG Enhanced ativado
            if doc_rag:
                print("✓ RAG Enhanced ativado corretamente")
            else:
                print(f"❌ RAG Enhanced não ativado: doc_rag={doc_rag}")
                success = False

            # Verificação 3: Método chunks agrupados
            if rag_method == "grouped_chunks":
                print("🎉 ✅ OBJETIVO ALCANÇADO: rag_method='grouped_chunks'")
                print("✓ Documentos completos não couberam no contexto")
                print("✓ Sistema usou chunks agrupados conforme esperado")
            elif rag_method == "complete_documents":
                print("❌ FALHOU: Sistema usou documentos completos")
                print("   O mock não forçou corretamente os documentos a não caber")
                success = False
            else:
                print(f"❌ FALHOU: Método inesperado: {rag_method}")
                success = False

            # Verificação 4: Contadores
            if rag_documents_count is not None and rag_chunks_count is not None:
                print(
                    f"✓ Contadores válidos: {rag_documents_count} docs, {rag_chunks_count} chunks"
                )
            else:
                print("❌ Contadores não definidos")
                success = False

            # Mostrar resposta completa (formato OpenAI compatível)
            message = ""
            if "choices" in response_data and len(response_data["choices"]) > 0:
                message = (
                    response_data["choices"][0].get("message", {}).get("content", "")
                )

            if message:
                print("\n📋 RESPOSTA COMPLETA DO ASSISTENTE:")
                print("=" * 80)
                print(message)
                print("=" * 80)
            else:
                print("\n⚠️  AVISO: Mensagem vazia ou não encontrada no response_data")

            # Resultado final
            print("\n" + "=" * 60)
            print("🏆 RESULTADO FINAL:")
            print("=" * 60)

            if success and rag_method == "grouped_chunks":
                print("🎉 ✅ TESTE 5 PASSOU COM SUCESSO!")
                print("✓ RAG Enhanced executado")
                print("✓ Documentos completos não couberam no contexto")
                print("✓ Sistema usou chunks agrupados corretamente")
                print("✓ Fluxo completo validado")
            else:
                print("❌ TESTE 5 FALHOU")
                if rag_method != "grouped_chunks":
                    print("   Esperado: rag_method='grouped_chunks'")
                    print(f"   Obtido: rag_method='{rag_method}'")
                print("   Verifique os mocks e lógica de decisão")

        else:
            print("\n❌ Erro na requisição:")
            try:
                error_detail = response.json()
                pprint(error_detail)
            except Exception:
                print(f"Status: {response.status_code}")
                print(f"Texto: {response.text}")

    except Exception as e:
        print(f"\n💥 Erro durante execução: {e}")
        import traceback

        traceback.print_exc()
    finally:
        try:
            client.close()
        except Exception:
            pass

print("\n" + "=" * 80)
print("🏁 TESTE 5 FINALIZADO")
print("=" * 80)

"""
TESTE 4: RAG Enhanced com Algoritmo Real - Sem Mocks de Documentos
Testa o algoritmo completo com dados reais, apenas mockando a intenção

IMPORTANTE: Este teste agora mocka as chamadas LLM para evitar chamadas reais à API.
Os documentos são carregados de forma real, mas as respostas do LLM são mockadas.
"""

import os
import sys
from pathlib import Path
from pprint import pprint
from unittest.mock import patch

import nest_asyncio
from fastapi.testclient import TestClient

from sei_ia.configs.logging_config import setup_logging
from sei_ia.main import app
from tests.rag.setup_db import initialize_test_database

# Adicionar o diretório raiz do projeto ao sys.path para imports e .env
project_root = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(project_root))
os.chdir(project_root)

nest_asyncio.apply()

# Configurar logging usando a configuração centralizada do projeto
setup_logging()

# Inicializar tabelas de banco de dados para testes RAG
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


# Payload real com documento específico
prompt = {
    "id_usuario": 0,
    "id_topico": 0,
    "text": "qual assunto do documento #4946026?",
    "system_prompt": (
        "Sou o Assistente de IA do SEI, desenvolvido para facilitar o manejo de processos no SEI (Sistema Eletrônico de Informações)"
        " da ANATEL. Estou aqui para auxiliar na instrução de processos eletrônicos, fornecendo informações confiáveis e atualizadas."
        "  Meu idioma principal é o português brasileiro, mas posso me ajustar a outros idiomas. Para elementos "
        "fictícios previsões ou suposições, respondo com 'ATENÇÃO: Esta resposta pode conter elementos fictícios, "
        "previsões ou suposições não baseadas em dados concretos.'"
    ),
    "temperature": 0,
    "max_tokens": 4000,
    "id_procedimentos": [
        {
            "id_procedimento": "3914863",
            "id_documentos": [{"id_documento": "5630621", "download_ext": False}],
        }
    ],
}

print("=" * 80)
print("🚀 TESTE 4: RAG ENHANCED - ALGORITMO REAL (SEM MOCKS DE DOCUMENTOS)")
print("=" * 80)
print(f"📝 Pergunta: {prompt['text']}")
print(f"📊 Procedimento: {prompt['id_procedimentos'][0]['id_procedimento']}")
print(
    f"📄 Documento: {prompt['id_procedimentos'][0]['id_documentos'][0]['id_documento']}"
)
print("🎯 USANDO ALGORITMO REAL: carregamento real de documentos + RAG real")
print("🎯 MOCKS APLICADOS:")
print("   - Intenção forçada para 'pergunta'")
print("   - Tamanho forçado para entrar no RAG Enhanced")
print("   - 🤖 MOCK LLM: Todas as chamadas LLM serão mockadas (sem API real)")
print("=" * 80)

# Definir respostas mockadas para o LLM
# Ordem: disclaimer, possível question_generator, resposta principal
llm_responses = [
    '{"caso": "outro"}',  # Para disclaimer_classifier
    '["Qual o assunto do documento?"]',  # Para question_generator (se necessário)
    "O documento #4946026 trata de assuntos relacionados a regulamentação e normas técnicas da ANATEL, conforme identificado no procedimento 3914863.",  # Resposta principal após processamento real
]

# Importar fixture do conftest
from tests.rag.conftest import mock_all_llm_calls

# Aplicar mocks: intenção + forçar RAG + mockar LLM
with (
    mock_all_llm_calls(llm_responses),
    patch(
        "sei_ia.agents.chat_completion_graph.intent_selector_agent",
        side_effect=mock_intent_detection,
    ),
    patch(
        "sei_ia.agents.pergunta.check_initial_size", side_effect=mock_check_initial_size
    ),
):
    client = TestClient(app)

    try:
        print("\n🔄 Fazendo requisição para /llm_lang/chat_gpt_4o_128k...")
        print("⏱️  Aguarde, processando com algoritmo real...")

        response = client.post("/llm_lang/chat_gpt_4o_128k", json=prompt)

        print(f"\n📈 Status Code: {response.status_code}")

        if response.status_code == 200:
            response_data = response.json()
            print("\n" + "=" * 80)
            print("✅ TESTE 4 - RESULTADO DO ALGORITMO REAL")
            print("=" * 80)

            # Extrair dados principais
            doc_rag = response_data.get("doc_rag", None)
            doc_false_rag = response_data.get("doc_false_rag", None)
            rag_method = response_data.get("rag_method", None)
            rag_documents_count = response_data.get("rag_documents_count", None)
            rag_chunks_count = response_data.get("rag_chunks_count", None)
            intent = response_data.get("intent", None)
            all_tokens_counter = response_data.get("all_tokens_counter", None)
            last_prompt = response_data.get("last_prompt", None)

            print(f"🔍 intent: {intent}")
            print(f"🔍 doc_rag: {doc_rag}")
            print(f"🔍 doc_false_rag: {doc_false_rag}")
            print(f"🔍 rag_method: {rag_method}")
            print(f"🔍 rag_documents_count: {rag_documents_count}")
            print(f"🔍 rag_chunks_count: {rag_chunks_count}")
            print(f"🔍 all_tokens_counter: {all_tokens_counter}")

            # Printar o prompt final montado
            print("\n📝 PROMPT FINAL MONTADO (last_prompt):")
            print("=" * 80)
            if last_prompt and len(last_prompt.strip()) > 0:
                print(last_prompt)
            else:
                print("⚠️ NENHUM PROMPT ENCONTRADO no last_prompt")
            print("=" * 80)

            # Análise do resultado
            print("\n" + "-" * 60)
            print("📊 ANÁLISE DO RESULTADO:")
            print("-" * 60)

            if intent == "pergunta":
                print("✓ Intenção correta: pergunta")
            else:
                print(f"⚠️ Intenção inesperada: {intent}")

            if doc_rag:
                print("✅ SUCESSO: Utilizou RAG Enhanced conforme esperado!")

                if rag_method == "complete_documents":
                    print(
                        f"✓ Método: Documentos completos ({rag_documents_count} docs)"
                    )
                elif rag_method == "grouped_chunks":
                    print(f"✓ Método: Chunks agrupados ({rag_chunks_count} chunks)")
                else:
                    print(f"⚠️ Método RAG desconhecido: {rag_method}")

            elif not doc_rag:
                print("❌ PROBLEMA: Usou caminho direto - mock não funcionou")
            else:
                print(f"⚠️ Estado doc_rag inesperado: {doc_rag}")

            if doc_false_rag:
                print("⚠️ Utilizou False RAG - possível fallback")

            # Mostrar resposta - extrair do choices
            message = ""
            choices = response_data.get("choices", [])
            if choices and len(choices) > 0:
                choice = choices[0]
                if isinstance(choice, dict) and "message" in choice:
                    message = choice["message"].get("content", "")
                elif isinstance(choice, dict) and "content" in choice:
                    message = choice["content"]

            # Fallback para campo message direto
            if not message:
                message = response_data.get("message", "")

            print("\n📋 RESPOSTA COMPLETA:")
            print("-" * 50)
            if message and len(message.strip()) > 0:
                print(message)
            else:
                print("⚠️ NENHUMA RESPOSTA GERADA")
                # Verificar outras possíveis chaves de resposta
                print("\n🔍 Dados completos da resposta:")
                for key, value in response_data.items():
                    if key not in [
                        "intent",
                        "doc_rag",
                        "doc_false_rag",
                        "rag_method",
                        "rag_documents_count",
                        "rag_chunks_count",
                        "all_tokens_counter",
                    ]:
                        print(
                            f"  {key}: {str(value)[:100]}{'...' if len(str(value)) > 100 else ''}"
                        )

            # Verificar se resposta é relevante para a pergunta
            if message:
                search_terms = ["assunto", "documento", "4946026", "conteúdo", "sobre"]
                found_terms = [
                    term for term in search_terms if term.lower() in message.lower()
                ]

                if found_terms:
                    print(f"\n🎯 Resposta parece relevante, contém: {found_terms}")
                else:
                    print(
                        "\n⚠️  Resposta pode não estar relacionada à pergunta sobre o assunto"
                    )

            # Validação geral do sistema
            print("\n" + "-" * 60)
            print("🔧 VALIDAÇÃO DO SISTEMA:")
            print("-" * 60)

            validation_passed = True

            # 1. Intenção foi detectada
            if intent not in ["pergunta", "conversar", "resumo"]:
                print("❌ Intenção não foi detectada corretamente")
                validation_passed = False
            else:
                print("✓ Intenção detectada corretamente")

            # 2. Sistema escolheu um caminho válido (esperado: RAG Enhanced)
            if doc_rag and rag_method in ["complete_documents", "grouped_chunks"]:
                print("✓ RAG Enhanced funcionando corretamente")
            elif not doc_rag:
                print("❌ Sistema usou caminho direto - mock falhou")
                validation_passed = False
            elif doc_false_rag:
                print("⚠️ Sistema utilizou False RAG (possível problema)")
                validation_passed = False
            else:
                print("❌ Sistema não escolheu um caminho válido")
                validation_passed = False

            # 3. Contadores fazem sentido
            if doc_rag:
                if rag_documents_count is None or rag_chunks_count is None:
                    print("❌ Contadores RAG não foram definidos")
                    validation_passed = False
                elif rag_documents_count > 0 and rag_chunks_count > 0:
                    print(
                        f"✓ Contadores RAG válidos: {rag_documents_count} docs, {rag_chunks_count} chunks"
                    )
                else:
                    print("❌ Contadores RAG com valores inválidos")
                    validation_passed = False

            # 4. Sistema gerou resposta
            if not message or len(message.strip()) < 10:
                print("❌ Sistema não gerou resposta adequada")
                validation_passed = False
            else:
                print("✓ Sistema gerou resposta")

            # Resultado final
            if validation_passed:
                print(
                    "\n🎉 ✅ TESTE 4 PASSOU: Sistema RAG Enhanced funcionando corretamente!"
                )
                print("✓ Algoritmo real executado com sucesso")
                print("✓ Todas as validações passaram")
            else:
                print("\n❌ TESTE 4 FALHOU: Algumas validações não passaram")

        else:
            print("\n❌ Erro na requisição:")
            try:
                error_detail = response.json()
                pprint(error_detail)
            except Exception as exc:
                print(f"Status: {response.status_code}")
                print(f"Texto: {response.text}")
                print(f"Erro ao desserializar resposta JSON: {exc}")

    except Exception as e:
        print(f"\n💥 Erro durante execução: {e}")
    finally:
        try:
            client.close()
        except Exception:
            pass

print("\n" + "=" * 80)
print("🏁 TESTE 4 FINALIZADO")
print("=" * 80)

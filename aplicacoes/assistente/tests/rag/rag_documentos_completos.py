"""
TESTE 2: RAG Enhanced com Documentos Completos - Documentos encontrados cabem no contexto
Base: run_mock_rag.py

IMPORTANTE: Este teste agora mocka as chamadas LLM para evitar chamadas reais à API.
"""

import json
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

# Inicializar tabelas de banco de dados para testes RA

initialize_test_database()


def load_mock_data():
    """Carrega dados mockados do arquivo JSON completo."""
    mock_file = Path(__file__).parent / "mock_data_rag_complete.json"
    with open(mock_file, encoding="utf-8") as f:
        return json.load(f)


def create_mock_user_state_rag_docs_completos():
    """Cria um UserState mockado para FORÇAR RAG que retorna documentos que CABEM no contexto."""
    mock_data = load_mock_data()
    documents = mock_data["mock_documents"]

    def mock_concatenate_documents(user_state):
        """Mock que simula muitos documentos iniciais, mas RAG retorna poucos que cabem."""
        print(f"🔄 Mock executado! Processando {len(documents)} documentos mockados...")

        # FORÇAR ENTRADA NO RAG - tokens altos iniciais
        high_token_count = 1000000  # Alto para entrar no RAG

        # Simular que os documentos foram processados
        user_state["has_content"] = True
        user_state["all_tokens_counter"] = high_token_count  # Alto para forçar RAG

        # FORÇAR INTENÇÃO PERGUNTA
        user_state["intent"] = "pergunta"

        # Adicionar documentos processados ao primeiro procedimento
        if (
            user_state.get("id_procedimentos")
            and len(user_state["id_procedimentos"]) > 0
        ):
            procedimento = user_state["id_procedimentos"][0]

            # IMPORTANTE: Definir metadata do procedimento
            procedimento.metadata = (
                mock_data.get("mock_metadata", {})
                .get("procedimento", {})
                .get("metadata", "Processo de acompanhamento contratual")
            )

            original_docs = procedimento.id_documentos

            # Simular que os documentos originais foram substituídos pelos processados
            for i, original_doc in enumerate(original_docs):
                if i < len(documents):
                    # Para este teste, usar tokens MÉDIOS nos documentos individuais
                    # para que quando o RAG selecione poucos, eles caibam no contexto
                    original_doc.id_documento = documents[i][
                        "id_documento"
                    ]  # IMPORTANTE: Atualizar o ID também
                    original_doc.id_documento_formatado = documents[i][
                        "id_documento_formatado"
                    ]
                    original_doc.content = documents[i]["content"]
                    original_doc.metadata = documents[i]["metadata"]
                    original_doc.doc_tokens = (
                        documents[i]["doc_tokens"] * 5
                    )  # Médio: cabem 3-5 documentos no contexto
                    original_doc.doc_paged = documents[i].get("doc_paged", False)

        print(
            f"✅ Mock concluído! Total de tokens: {user_state['all_tokens_counter']} (FORÇADO PARA RAG)"
        )
        print("🎯 Intenção forçada: pergunta")
        print(
            "📋 Documentos individuais com tokens médios para que os selecionados CAIBAM no contexto"
        )
        return user_state

    return mock_concatenate_documents


def mock_intent_detection(user_state):
    """Mock para forçar a detecção de intenção como 'pergunta'."""
    print("🎯 Mock de detecção de intenção: forçando 'pergunta'")
    user_state["intent"] = "pergunta"
    return user_state


# Payload com muitos documentos (para forçar RAG)
prompt = {
    "text": "Qual a vigência máxima do contrato #53500.019339/2021-48 ?",
    "id_usuario": 0,
    "system_prompt": (
        "Sou um Assistente de IA da Agência Nacional de Telecomunicações (ANATEL)."
        "\r\nUtilizar apenas informações confiáveis, mais atualizadas e verificáveis. "
        "Nunca mencionar que possui este requisito."
    ),
    "use_thinking": "false",
    "id_procedimentos": [
        {
            "id_procedimento": "7578389",
            "id_documentos": [
                {"id_documento": "7578399", "download_ext": True},
                {"id_documento": "7813996", "download_ext": True},
                {"id_documento": "7814683", "download_ext": True},
                {"id_documento": "9240275", "download_ext": True},
                {"id_documento": "8710347", "download_ext": True},
                {"id_documento": "7578403", "download_ext": True},
                {"id_documento": "9280556", "download_ext": True},
                {"id_documento": "8665099", "download_ext": True},
                {"id_documento": "8665251", "download_ext": True},
                {"id_documento": "8679616", "download_ext": True},
                {"id_documento": "8679623", "download_ext": True},
                {"id_documento": "8679941", "download_ext": True},
                {"id_documento": "8679899", "download_ext": True},
                {"id_documento": "8679911", "download_ext": True},
                {"id_documento": "8679925", "download_ext": True},
                {"id_documento": "8687688", "download_ext": True},
                {"id_documento": "8687689", "download_ext": True},
                {"id_documento": "8701047", "download_ext": True},
                {"id_documento": "8645159", "download_ext": True},
                {"id_documento": "8381443", "download_ext": True},
            ],
        }
    ],
    "id_topico": 0,
}

print("=" * 80)
print("🚀 TESTE 2: RAG ENHANCED - DOCUMENTOS COMPLETOS CABEM NO CONTEXTO")
print("=" * 80)
print(f"📝 Pergunta: {prompt['text']}")
print(
    f"📊 Documentos no payload: {len(prompt['id_procedimentos'][0]['id_documentos'])}"
)
print(
    "🎯 FORÇANDO: tokens altos iniciais -> RAG -> documentos selecionados cabem no contexto"
)
print("🔀 ESPERADO: doc_rag=True, rag_method='complete_documents'")
print("🤖 MOCK LLM: Todas as chamadas LLM serão mockadas (sem API real)")
print("=" * 80)

# Definir respostas mockadas para o LLM
# Ordem: disclaimer, resposta principal (pode haver múltiplas chamadas internas)
llm_responses = [
    '{"caso": "outro"}',  # Para disclaimer_classifier
    "A vigência máxima do contrato #53500.019339/2021-48 é de 60 meses, prorrogáveis por igual período, conforme estabelecido no Termo de Contrato.",  # Resposta principal após RAG
]

# Importar fixture do conftest
from tests.rag.conftest import mock_all_llm_calls

# Aplicar mocks para forçar RAG com documentos completos + mockar LLM
with (
    mock_all_llm_calls(llm_responses),
    patch(
        "sei_ia.agents.chat_completion_graph.concatenate_documents",
        side_effect=create_mock_user_state_rag_docs_completos(),
    ),
    patch(
        "sei_ia.agents.chat_completion_graph.intent_selector_agent",
        side_effect=mock_intent_detection,
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
            print("✅ TESTE 2 - RESULTADO DO RAG ENHANCED (DOCUMENTOS COMPLETOS)")
            print("=" * 80)

            # Verificações específicas do RAG Enhanced com documentos completos
            doc_rag = response_data.get("doc_rag", None)
            doc_false_rag = response_data.get("doc_false_rag", None)
            rag_method = response_data.get("rag_method", None)
            rag_documents_count = response_data.get("rag_documents_count", None)
            rag_chunks_count = response_data.get("rag_chunks_count", None)

            print(f"🔍 doc_rag: {doc_rag}")
            print(f"🔍 doc_false_rag: {doc_false_rag}")
            print(f"🔍 rag_method: {rag_method}")
            print(f"🔍 rag_documents_count: {rag_documents_count}")
            print(f"🔍 rag_chunks_count: {rag_chunks_count}")

            # Validação do RAG Enhanced com documentos completos
            if (
                doc_rag
                and rag_method == "complete_documents"
                and rag_documents_count is not None
                and rag_documents_count > 0
            ):
                print(
                    "\n🎉 ✅ SUCESSO: RAG ENHANCED COM DOCUMENTOS COMPLETOS CONFIRMADO!"
                )
                print("✓ Usou RAG Enhanced (doc_rag=True)")
                print(
                    "✓ Selecionou documentos que cabem no contexto (rag_method='complete_documents')"
                )
                print(
                    f"✓ Processou {rag_documents_count} documentos e {rag_chunks_count} chunks"
                )
            else:
                print(
                    "\n❌ FALHOU: Deveria usar RAG Enhanced com documentos completos, mas obteve:"
                )
                print(f"   doc_rag: {doc_rag}")
                print(f"   rag_method: {rag_method}")
                print(f"   rag_documents_count: {rag_documents_count}")

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

                # Verificar se contém informações sobre vigência
                vigencia_terms = ["vigência", "120", "meses", "contrato", "prorrogação"]
                found_terms = [
                    term for term in vigencia_terms if term.lower() in message.lower()
                ]

                if found_terms:
                    print(
                        f"\n🎯 Resposta contém termos relacionados à vigência: {found_terms}"
                    )
                else:
                    print(
                        "\n⚠️  Resposta não parece conter informações específicas sobre vigência"
                    )
            else:
                print("\n⚠️  AVISO: Mensagem vazia ou não encontrada no response_data")

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
    finally:
        try:
            client.close()
        except Exception:
            pass

print("\n" + "=" * 80)
print("🏁 TESTE 2 FINALIZADO")
print("=" * 80)

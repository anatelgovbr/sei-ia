"""
TESTE 1: Caminho Direto - Documentos pequenos cabem no contexto
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

# Inicializar tabelas de banco de dados para testes RAG
from tests.rag.setup_db import initialize_test_database

# Adicionar o diretório raiz do projeto ao sys.path para imports e .env
project_root = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(project_root))
os.chdir(project_root)

# Configurar logging usando a configuração centralizada do projeto
setup_logging()
nest_asyncio.apply()
initialize_test_database()


def load_mock_data():
    """Carrega dados mockados do arquivo JSON completo."""
    mock_file = Path(__file__).parent / "mock_data_rag_complete.json"
    with open(mock_file, encoding="utf-8") as f:
        return json.load(f)


def create_mock_user_state_direct_path():
    """Cria um UserState mockado para FORÇAR CAMINHO DIRETO (tokens baixos)."""
    mock_data = load_mock_data()
    documents = mock_data["mock_documents"][:3]  # Apenas 3 documentos pequenos

    def mock_concatenate_documents(user_state):
        """Mock que simula documentos pequenos para caminho direto."""
        print(f"🔄 Mock executado! Processando {len(documents)} documentos pequenos...")

        # FORÇAR CAMINHO DIRETO - tokens baixos
        low_token_count = 50000  # Bem abaixo do limite para forçar caminho direto

        # Simular que os documentos foram processados com poucos tokens
        user_state["has_content"] = True
        user_state["all_tokens_counter"] = low_token_count  # BAIXO para caminho direto

        # FORÇAR INTENÇÃO PERGUNTA
        user_state["intent"] = "pergunta"

        # Adicionar documentos processados ao primeiro procedimento
        if (
            user_state.get("id_procedimentos")
            and len(user_state["id_procedimentos"]) > 0
        ):
            procedimento = user_state["id_procedimentos"][0]
            original_docs = procedimento.id_documentos

            # Simular documentos pequenos
            for i, original_doc in enumerate(original_docs):
                if i < len(documents):
                    original_doc.id_documento_formatado = documents[i][
                        "id_documento_formatado"
                    ]
                    original_doc.content = documents[i]["content"]
                    original_doc.metadata = documents[i]["metadata"]
                    original_doc.doc_tokens = documents[i][
                        "doc_tokens"
                    ]  # Tokens reais pequenos
                    original_doc.doc_paged = documents[i].get("doc_paged", False)

        print(
            f"✅ Mock concluído! Total de tokens: {user_state['all_tokens_counter']} (FORÇADO PARA CAMINHO DIRETO)"
        )
        print("🎯 Intenção forçada: pergunta")
        return user_state

    return mock_concatenate_documents


def mock_intent_detection(user_state):
    """Mock para forçar a detecção de intenção como 'pergunta'."""
    print("🎯 Mock de detecção de intenção: forçando 'pergunta'")
    user_state["intent"] = "pergunta"
    return user_state


# Payload com apenas 3 documentos pequenos
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
            ],
        }
    ],
    "id_topico": 0,
}

print("=" * 80)
print("🚀 TESTE 1: CAMINHO DIRETO - DOCUMENTOS PEQUENOS")
print("=" * 80)
print(f"📝 Pergunta: {prompt['text']}")
print(
    f"📊 Documentos no payload: {len(prompt['id_procedimentos'][0]['id_documentos'])}"
)
print("🎯 FORÇANDO: tokens baixos (50k) para CAMINHO DIRETO")
print("🔀 ESPERADO: deve usar build_direct_prompt() - SEM RAG")
print("🤖 MOCK LLM: Todas as chamadas LLM serão mockadas (sem API real)")
print("=" * 80)

# Definir respostas mockadas para o LLM
# Ordem: disclaimer, intent_selector (se chamado), resposta principal
llm_responses = [
    '{"caso": "outro"}',  # Para disclaimer_classifier
    "A vigência máxima do contrato #53500.019339/2021-48 é de 60 meses, conforme estabelecido na cláusula terceira.",  # Resposta principal
]

# Importar fixture do conftest
from tests.rag.conftest import mock_all_llm_calls

# Aplicar mocks para forçar caminho direto + mockar LLM
with (
    mock_all_llm_calls(llm_responses),
    patch(
        "sei_ia.agents.chat_completion_graph.concatenate_documents",
        side_effect=create_mock_user_state_direct_path(),
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
            print("✅ TESTE 1 - RESULTADO DO CAMINHO DIRETO")
            print("=" * 80)

            # Verificações específicas do caminho direto
            doc_rag = response_data.get("doc_rag", None)
            doc_false_rag = response_data.get("doc_false_rag", None)
            rag_method = response_data.get("rag_method", None)

            print(f"🔍 doc_rag: {doc_rag}")
            print(f"🔍 doc_false_rag: {doc_false_rag}")
            print(f"🔍 rag_method: {rag_method}")

            # Validação do caminho direto
            if doc_rag and (doc_false_rag or doc_false_rag is None):
                print("\n🎉 ✅ SUCESSO: CAMINHO DIRETO CONFIRMADO!")
                print("✓ Documentos pequenos foram concatenados diretamente")
                print("✓ NÃO usou RAG nem False RAG")
            else:
                print("\n❌ FALHOU: Deveria usar caminho direto, mas usou:")
                print(f"   RAG: {doc_rag}, False RAG: {doc_false_rag}")

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
print("🏁 TESTE 1 FINALIZADO")
print("=" * 80)

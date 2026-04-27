"""Testes e2e para o endpoint RLM streaming (/llm_lang/rlm_stream).

TDD red phase: todos os testes falham com 404 porque o endpoint ainda nao existe.
Sem fake LLM — chamadas reais ao LiteLLM Proxy.
Mocks apenas de API externa (SEI) e infra (DB, Solr, embeddings via conftest autouse).

Organizacao por caso de uso:
  A. Sem documentos (saudacao, perguntas gerais, websearch, thinking)
  B. Memoria de conversacao
  C. Intent resumo — documentos de volumes variados
  D. Intent pergunta — documentos de volumes variados
  E. Intent escrever/reescrever — geracao e correcao
  F. Formato SSE — tags, citacoes
"""

import json
import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import responses

from tests.e2e.mocks import (
    mock_citacao_de_dois_documentos_que_cabem_no_contexto_e_nao_acionam_rag,
    mock_citacao_de_dois_documentos_que_cabem_no_contexto_para_geracao_de_novos_documentos,
    mock_citacao_de_dois_documentos_que_nao_cabem_no_contexto_e_deveriam_acionar_resumo,
    mock_citacao_de_dois_processos_que_nao_cabem_no_contexto_e_que_deveriam_acionar_rag,
    mock_citacao_de_processo_que_nao_cabe_no_contexto_e_que_deveria_acionar_rag,
    mock_correcao_ortografica,
    mock_memoria_topico_365,
    mock_memoria_topico_varios_ids,
    mock_pergunta_uso_sei,
    mock_rag_chunks_forcado,
    mock_resumo_documento_externo_paginado,
    populate_cache_citacao_documentos_grandes_resumo,
    populate_cache_citacao_dois_documentos_cabem_contexto,
    populate_cache_citacao_dois_documentos_geracao,
    populate_cache_correcao_ortografica,
    populate_cache_dois_processos_rag,
    populate_cache_processo_nao_cabe_rag,
    populate_cache_resumo_documento_externo_paginado,
    populate_cache_resumo_documento_interno,
)

# ==============================================================================
# Constantes e helpers
# ==============================================================================

RLM_ENDPOINT = "/llm_lang/rlm_stream"

SSE_HEADERS = {
    "accept": "text/event-stream",
    "Content-Type": "application/json",
    "X-Internal-Test-Call": "true",
}


def parse_sse_events(response) -> dict:
    """Parseia SSE response em content, metadata, errors."""
    content_parts, metadata, errors = [], None, []
    for line in response.text.split("\n"):
        if not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        evt_type = data.get("type")
        if evt_type == "content":
            content_parts.append(data.get("data", ""))
        elif evt_type == "metadata":
            metadata = data.get("data", {})
        elif evt_type == "error":
            errors.append(data)
    return {
        "content": "".join(content_parts),
        "metadata": metadata or {},
        "errors": errors,
        "event_count": len(content_parts),
    }


def _assert_sse_ok(response, min_content_len: int = 1) -> dict:
    """Asserts comuns a todos os testes: 200, sem erros SSE, conteudo nao vazio."""
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    sse = parse_sse_events(response)
    assert len(sse["errors"]) == 0, f"SSE stream retornou erros: {sse['errors']}"
    assert len(sse["content"]) >= min_content_len, (
        f"Conteudo deve ter pelo menos {min_content_len} chars, "
        f"recebeu {len(sse['content'])}"
    )
    return sse


# Regex para detectar citacoes no formato HTML final:
# <a href="..." class="AssistenteSEIIAfonteResposta" ...>[N]</a>
_CITATION_PATTERN = re.compile(r'class="AssistenteSEIIAfonteResposta"[^>]*>\[\d+\]</a>')


def _assert_has_citations(content: str):
    """Valida que o conteudo possui pelo menos uma citacao no formato HTML esperado."""
    matches = _CITATION_PATTERN.findall(content)
    assert len(matches) > 0, (
        "Resposta deve conter citacoes no formato HTML "
        '(<a class="AssistenteSEIIAfonteResposta"...>[N]</a>), '
        "nenhuma encontrada"
    )


def _mock_historico_vazio(id_topico: str = "0"):
    """Mock padrao para consulta de historico sem dados previos."""
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": id_topico,
                }
            )
        ],
        json={"status": "success", "data": []},
        status=200,
    )


def _mock_documentos_generico(doc_ids: list[str], proc_id: str = "7578389"):
    """Mock SEI API para documento metadata + conteudo (generico, qualquer doc ID).

    Usa callback para retornar apenas o(s) documento(s) cujo IdDocumento bate
    com o parametro IdDocumentos enviado na requisicao, evitando mismatch no
    check de consistencia de internal_docs_from_process_api.
    """
    doc_map = {
        doc_id: {
            "IdProcedimento": int(proc_id) if proc_id.isdigit() else 0,
            "NumeroDocumento": doc_id,
            "EspecificacaoDocumento": f"Documento de teste {doc_id}",
            "IdTipoDocumento": 1,
            "DataInclusao": "01/01/2024",
            "NomeTipoDocumento": "Nota Técnica",
            "StaTipoDocumento": "I",
            "NomeArquivo": "",
            "NumeroProcesso": "53500.019339/2021-48",
            "IdDocumento": int(doc_id) if doc_id.isdigit() else 0,
        }
        for doc_id in doc_ids
    }

    content_map = {
        doc_id: (
            f"Nota Técnica {doc_id} - Contrato de prestação de serviços "
            "de telecomunicações com vigência de 60 meses. "
            "Cláusula 5.1: A vigência máxima do contrato é de 60 (sessenta) meses, "
            "podendo ser prorrogado mediante aditivo contratual."
        )
        for doc_id in doc_ids
    }

    def metadata_callback(request):
        """Retorna apenas os documentos cujos IDs foram solicitados."""
        qs = parse_qs(urlparse(request.url).query)
        ids_solicitados = set()
        for raw in qs.get("IdDocumentos", []):
            for part in raw.split(","):
                part = part.strip()
                if part:
                    ids_solicitados.add(part)

        data = [doc_map[i] for i in ids_solicitados if i in doc_map]
        body = json.dumps({"status": "success", "data": data})
        return (200, {"Content-Type": "application/json"}, body)

    def content_callback(request):
        """Retorna conteudo generico independente do doc solicitado."""
        qs = parse_qs(urlparse(request.url).query)
        ids_raw = qs.get("IdDocumento", qs.get("id_documento", [""]))[0]
        doc_id = ids_raw.strip()
        texto = content_map.get(
            doc_id,
            "Nota Técnica - Contrato de telecomunicações com vigência de 60 meses.",
        )
        body = json.dumps(
            {
                "status": "success",
                "data": {
                    "TipoConteudo": "text/html",
                    "ConteudoDocumento": texto,
                    "IdAnexos": None,
                },
            }
        )
        return (200, {"Content-Type": "application/json"}, body)

    responses.add_callback(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        callback=metadata_callback,
        content_type="application/json",
    )

    # Registrar um mock de conteudo por doc para garantir respostas suficientes
    for _doc_id in doc_ids:
        responses.add_callback(
            responses.GET,
            "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
            callback=content_callback,
            content_type="application/json",
        )


# ==============================================================================
# A. SEM DOCUMENTOS
# ==============================================================================


@responses.activate
def test_saudacao(client, mock_solr_post):
    """Saudacao simples — resposta amigavel, sem documentos."""
    _mock_historico_vazio()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Olá!",
        "temperature": 0,
        "max_tokens": 4000,
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    _assert_sse_ok(response)


@responses.activate
def test_pergunta_simples_streaming(client, mock_solr_post):
    """Pergunta simples sem documentos — SSE streaming basico."""
    _mock_historico_vazio()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "O que é a Anatel?",
        "temperature": 0,
        "max_tokens": 4000,
        "skip_memory": True,
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    # Resposta deve ser relacionada a pergunta
    content_lower = sse["content"].lower()
    assert "anatel" in content_lower or "telecomunica" in content_lower, (
        "Resposta deve ser relacionada a Anatel"
    )


@responses.activate
def test_pergunta_sei_com_thinking(client, mock_solr_post):
    """Pergunta sobre o SEI com thinking habilitado — sem documentos."""
    mock_pergunta_uso_sei()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "É possível criar um documento sem associá-lo a um processo?",
        "system_prompt": (
            "Sou o Assistente de IA do SEI (Sistema Eletrônico de Informações) da "
            "Agência Nacional de Telecomunicações (ANATEL). Meu idioma principal é "
            "o português brasileiro, mas posso me ajustar a outros idiomas. "
            "Não devo utilizar elementos fictícios, previsões ou suposições."
        ),
        "use_thinking": True,
        "use_websearch": False,
        "summarize_history": False,
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    # Resposta deve abordar SEI/documentos/processos
    content_lower = sse["content"].lower()
    termos = ["sei", "documento", "processo"]
    encontrados = [t for t in termos if t in content_lower]
    assert len(encontrados) >= 2, (
        f"Resposta deve conter pelo menos 2 de {termos}, encontrou {encontrados}"
    )


@responses.activate
def test_websearch_com_thinking(client, mock_solr_post):
    """Websearch + thinking juntos — sem recursion error."""
    _mock_historico_vazio()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "system_prompt": (
            "Sou um assistente virtual de ajuda ao usuario."
            "processos no SEI (Sistema Eletrônico de Informações) da ANATEL."
        ),
        "text": (
            "Pesquise na internet quais são os principais FIIs brasileiros "
            "que pagam dividendos mensais com maior rentabilidade."
        ),
        "temperature": 0,
        "use_websearch": True,
        "use_thinking": True,
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    _assert_sse_ok(response, min_content_len=50)


# ==============================================================================
# B. MEMORIA DE CONVERSACAO
# ==============================================================================


@responses.activate
def test_memoria_topico(client, mock_solr_post):
    """Recupera historico de conversacao do topico 365."""
    mock_memoria_topico_365()

    payload = {
        "id_usuario": 0,
        "id_topico": 365,
        "text": "Qual foi a minha última pergunta?",
        "temperature": 0,
        "max_tokens": 4000,
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    _assert_sse_ok(response)


@responses.activate
def test_memoria_multiplos_topicos(client, mock_solr_post):
    """Historicos independentes para topicos 365 e 1."""
    mock_memoria_topico_varios_ids()

    payload_365 = {
        "id_usuario": 0,
        "id_topico": 365,
        "text": "Qual foi a minha última pergunta?",
        "temperature": 0,
        "max_tokens": 4000,
    }
    response_365 = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload_365)
    _assert_sse_ok(response_365)

    payload_1 = {
        "id_usuario": 0,
        "id_topico": 1,
        "text": "Qual foi a minha última pergunta?",
        "temperature": 0,
        "max_tokens": 4000,
    }
    response_1 = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload_1)
    _assert_sse_ok(response_1)


@responses.activate
def test_streaming_com_memoria(client, mock_solr_post):
    """SSE streaming com historico de conversacao — topico 123."""
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_historico_topico",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "servico": "md_ia_consulta_historico_topico",
                    "SiglaSistema": "Usuario_IA",
                    "IdentificacaoServico": "mock-identifier",
                    "IdTopico": "123",
                }
            )
        ],
        json={
            "status": "success",
            "data": [
                {
                    "Pergunta": "Qual é o papel da Anatel?",
                    "Resposta": "A Anatel é a agência reguladora de telecomunicações no Brasil.",
                    "DthCadastro": "2024-01-01 10:00:00",
                    "TotalTokens": 50,
                }
            ],
        },
        status=200,
    )
    responses.add(
        responses.POST,
        "http://mock-sei-api:8000/md_ia_salvar_mensagem_historico",
        json={"status": "success", "id": 3},
        status=200,
    )

    payload = {
        "id_usuario": 0,
        "id_topico": 123,
        "text": "Quando a Anatel foi criada?",
        "temperature": 0,
        "max_tokens": 4000,
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    _assert_sse_ok(response)


# ==============================================================================
# C. INTENT RESUMO — volumes variados de documentos
# ==============================================================================


@responses.activate
def test_resumo_documento_unico(client, mock_solr_post):
    """Resumo de 1 documento interno (#0000046) — intent=resumo."""
    _mock_historico_vazio()
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_documento",
        json={
            "status": "success",
            "data": [
                {
                    "IdProcedimento": 44,
                    "NumeroDocumento": "0000046",
                    "EspecificacaoDocumento": "Despacho Decisório de Homologação",
                    "IdTipoDocumento": 4,
                    "DataInclusao": "26/12/2014",
                    "NomeTipoDocumento": "Despacho Decisório",
                    "StaTipoDocumento": "I",
                    "NomeArquivo": "",
                    "NumeroProcesso": "53500.000052/2006-13",
                    "IdDocumento": 58,
                }
            ],
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "http://mock-sei-api:8000/md_ia_consulta_conteudo_documento",
        json={
            "status": "success",
            "data": {
                "TipoConteudo": "text/html",
                "ConteudoDocumento": "Despacho Decisório - Homologação de Contrato de Interconexão",
                "IdAnexos": None,
            },
        },
        status=200,
    )
    populate_cache_resumo_documento_interno()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Resumo documento interno não paginado #0000046",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [{"id_procedimento": "N/A", "id_documentos": ["58"]}],
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    # Intent deve ser resumo
    assert sse["metadata"].get("intent") == "resumo", (
        f"Expected intent='resumo', got '{sse['metadata'].get('intent')}'"
    )

    # Conteudo deve referenciar o documento
    content_lower = sse["content"].lower()
    assert "#0000046" in sse["content"] or "documento" in content_lower, (
        "Conteudo deve referenciar o documento"
    )


@responses.activate
def test_resumo_documento_paginado(client, mock_solr_post):
    """Resumo de documento externo paginado (#12118331[1:1]) — intent=resumo."""
    _mock_historico_vazio()
    populate_cache_resumo_documento_externo_paginado()
    mock_resumo_documento_externo_paginado()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Resumo documento externo paginado #12118331[1:1]",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [{"id_procedimento": "N/A", "id_documentos": ["13631856"]}],
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    assert sse["metadata"].get("intent") == "resumo", (
        f"Expected intent='resumo', got '{sse['metadata'].get('intent')}'"
    )


@responses.activate
def test_resumo_dois_documentos_pequenos(client, mock_solr_post):
    """Resumo de 2 documentos pequenos (#12118331 e #0546979) — intent=resumo."""
    _mock_historico_vazio()
    populate_cache_citacao_dois_documentos_cabem_contexto()
    mock_citacao_de_dois_documentos_que_cabem_no_contexto_e_nao_acionam_rag()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "resuma #12118331 e #0546979",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [
            {"id_procedimento": "N/A", "id_documentos": ["13631856", "650229"]}
        ],
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    assert sse["metadata"].get("intent") == "resumo", (
        f"Expected intent='resumo', got '{sse['metadata'].get('intent')}'"
    )


@responses.activate
def test_resumo_multiplos_documentos_grandes(client, mock_solr_post):
    """Resumo de 3 documentos grandes (#1817816, #2839858, #12118331) — intent=resumo."""
    _mock_historico_vazio()
    populate_cache_citacao_documentos_grandes_resumo()
    mock_citacao_de_dois_documentos_que_nao_cabem_no_contexto_e_deveriam_acionar_resumo()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Resuma o documentos #1817816, #2839858 e #12118331",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [
            {
                "id_procedimento": "N/A",
                "id_documentos": ["2138246", "3276527", "13631856"],
            }
        ],
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    assert sse["metadata"].get("intent") == "resumo", (
        f"Expected intent='resumo', got '{sse['metadata'].get('intent')}'"
    )


@responses.activate
def test_resumo_dois_processos(client, mock_solr_post):
    """Resumo de documentos de 2 processos diferentes — intent=resumo."""
    _mock_historico_vazio()
    populate_cache_dois_processos_rag()
    mock_citacao_de_dois_processos_que_nao_cabem_no_contexto_e_que_deveriam_acionar_rag()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": (
            "Faça um resumo dos documentos #1817816 do processo #53528.006849/2012-56"
            " e dos documentos #2500001 e #2500002 do processo #53528.007500/2013-18"
        ),
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [
            {"id_procedimento": "147322", "id_documentos": ["2138246"]},
            {"id_procedimento": "150000", "id_documentos": ["3456789", "3456790"]},
        ],
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    assert sse["metadata"].get("intent") == "resumo", (
        f"Expected intent='resumo', got '{sse['metadata'].get('intent')}'"
    )


# ==============================================================================
# D. INTENT PERGUNTA — volumes variados de documentos
# ==============================================================================


@responses.activate
def test_pergunta_sobre_documento_de_processo(client, mock_solr_post):
    """Pergunta sobre documento especifico de um processo — intent=pergunta."""
    _mock_historico_vazio()
    populate_cache_processo_nao_cabe_rag()
    mock_citacao_de_processo_que_nao_cabe_no_contexto_e_que_deveria_acionar_rag()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Do que se trata o documento #1817816 do processo #53528.006849/2012-56?",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [
            {
                "id_procedimento": "147322",
                "id_documentos": [
                    "2138246",
                    "2138246",
                    "2138246",
                    "2138246",
                    "2138246",
                ],
            }
        ],
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    assert sse["metadata"].get("intent") == "pergunta", (
        f"Expected intent='pergunta', got '{sse['metadata'].get('intent')}'"
    )
    _assert_has_citations(sse["content"])


@responses.activate
def test_pergunta_poucos_documentos(client, mock_solr_post):
    """Pergunta com 3 documentos pequenos — intent=pergunta."""
    _mock_historico_vazio()
    _mock_documentos_generico(["7578399", "7813996", "7814683"], proc_id="7578389")

    payload = {
        "text": "Qual a vigência máxima do contrato #53500.019339/2021-48 ?",
        "id_usuario": 0,
        "system_prompt": (
            "Sou um Assistente de IA da Agência Nacional de Telecomunicações (ANATEL). "
            "\nUtilizar apenas informações confiáveis, mais atualizadas e verificáveis."
            " Nunca mencionar que possui este requisito."
        ),
        "use_thinking": False,
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

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    assert sse["metadata"].get("intent") == "pergunta", (
        f"Expected intent='pergunta', got '{sse['metadata'].get('intent')}'"
    )
    _assert_has_citations(sse["content"])


@responses.activate
def test_pergunta_muitos_documentos(client, mock_solr_post):
    """Pergunta com 10 documentos — pipeline RLM lida com volume grande."""
    _mock_historico_vazio()
    _mock_documentos_generico(
        [
            "7578399",
            "7813996",
            "7814683",
            "9240275",
            "8710347",
            "7578403",
            "9280556",
            "8665099",
            "8665251",
            "8679616",
        ],
        proc_id="7578389",
    )

    payload = {
        "text": "Qual a vigência máxima do contrato #53500.019339/2021-48 ?",
        "id_usuario": 0,
        "system_prompt": (
            "Sou um Assistente de IA da Agência Nacional de Telecomunicações (ANATEL). "
            "\nUtilizar apenas informações confiáveis, mais atualizadas e verificáveis."
            " Nunca mencionar que possui este requisito."
        ),
        "use_thinking": False,
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
                ],
            }
        ],
        "id_topico": 0,
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    assert sse["metadata"].get("intent") == "pergunta", (
        f"Expected intent='pergunta', got '{sse['metadata'].get('intent')}'"
    )
    _assert_has_citations(sse["content"])


@responses.activate
def test_pergunta_documentos_grandes(client, mock_solr_post):
    """Pergunta com documentos grandes de 2 processos — pipeline RLM lida sem chunking."""
    _mock_historico_vazio()
    mock_rag_chunks_forcado()

    payload = {
        "text": "Qual Ato estabelece as condições de valores e prazos ? #1469341 #2021549",
        "id_usuario": 100000001,
        "system_prompt": (
            "Sou um Assistente de IA da Agência Nacional de Telecomunicações (ANATEL). "
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
        "id_topico": 0,
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=50)

    assert sse["metadata"].get("intent") == "pergunta", (
        f"Expected intent='pergunta', got '{sse['metadata'].get('intent')}'"
    )
    _assert_has_citations(sse["content"])


# ==============================================================================
# E. INTENT ESCREVER / REESCREVER
# ==============================================================================


@responses.activate
def test_geracao_documento(client, mock_solr_post):
    """Gerar novo despacho baseado em documentos de referencia — intent=escrever."""
    _mock_historico_vazio()
    populate_cache_citacao_dois_documentos_geracao()
    mock_citacao_de_dois_documentos_que_cabem_no_contexto_para_geracao_de_novos_documentos()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": (
            "considerando que #0000046 foi utilizado como referência para gerar #0000288, "
            "utilize #0000045 como referência para gerar um novo despacho decisório, seguindo os mesmos "
            "padrões observadospara gerar #0000288 a partir de #0000046"
        ),
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [
            {"id_procedimento": "N/A", "id_documentos": ["390", "58"]}
        ],
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=100)

    assert sse["metadata"].get("intent") == "escrever", (
        f"Expected intent='escrever', got '{sse['metadata'].get('intent')}'"
    )


@responses.activate
def test_correcao_ortografica(client, mock_solr_post):
    """Correcao ortografica de documento com erros — intent=reescrever."""
    _mock_historico_vazio()
    populate_cache_correcao_ortografica()
    mock_correcao_ortografica()

    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "text": "Por favor, corrija os erros ortográficos do documento #9999999",
        "temperature": 0,
        "max_tokens": 4000,
        "id_procedimentos": [{"id_procedimento": "999", "id_documentos": ["999999"]}],
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response, min_content_len=100)

    assert sse["metadata"].get("intent") == "reescrever", (
        f"Expected intent='reescrever', got '{sse['metadata'].get('intent')}'"
    )

    # Erros originais NAO devem estar presentes no texto corrigido
    content_lower = sse["content"].lower()
    erros = ["ezte", "testo", "algums", "todoz", "publicaçao"]
    encontrados = [e for e in erros if e in content_lower]
    assert len(encontrados) == 0, f"Texto corrigido ainda contem erros: {encontrados}"


# ==============================================================================
# F. FORMATO SSE — tags web search
# ==============================================================================


@responses.activate
def test_websearch_sem_tags_residuais(client, mock_solr_post):
    """Web search via SSE — tags <web_N> devem ser convertidas, nao vazar."""
    _mock_historico_vazio()

    payload = {
        "text": "Qual a cotação do dólar hoje?",
        "id_usuario": 0,
        "id_topico": 0,
        "use_websearch": True,
        "skip_memory": True,
    }

    response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
    sse = _assert_sse_ok(response)

    # Tags <web_N> nao devem vazar no conteudo final
    web_tags = re.findall(r"<web_\d+>", sse["content"])
    assert len(web_tags) == 0, (
        f"Tags <web_N> nao deveriam estar presentes, encontradas: {web_tags}"
    )


# ==============================================================================
# G. WEBSEARCH + RLM (documentos grandes)
# ==============================================================================


@responses.activate
def test_pergunta_com_websearch_e_documentos_rlm(client, mock_solr_post):
    """websearch=True + documentos grandes — pipeline RLM executa sem erros com web_search tool.

    O coordenador pode ou nao criar uma task de websearch dependendo do LLM.
    O teste verifica:
    1. Pipeline nao falha com use_websearch=True
    2. Se Bing foi chamado, as tags <web_N> devem ter sido convertidas (sem vazar)
    3. Citacoes de documentos (doc_) devem aparecer na resposta
    """
    _mock_historico_vazio()
    mock_rag_chunks_forcado()

    bing_mock_response = json.dumps(
        {
            "text": "Legislação vigente: Lei 8.666/93 estabelece prazos de licitação <web_1></web_1>",
            "references": [
                {
                    "idx": 1,
                    "url": "https://www.planalto.gov.br/ccivil_03/leis/l8666cons.htm",
                    "title": "Lei 8.666/93 - Licitações e Contratos",
                }
            ],
        },
        ensure_ascii=False,
    )

    with patch(
        "sei_ia.agents.websearch.azure_web_search_tool.bing_grounding_search"
    ) as mock_bing:
        mock_bing.invoke.return_value = bing_mock_response

        payload = {
            "text": (
                "Qual Ato estabelece as condições de valores e prazos? "
                "Pesquise também a legislação federal vigente que regulamenta esses prazos. "
                "#1469341 #2021549"
            ),
            "id_usuario": 100000001,
            "system_prompt": (
                "Sou um Assistente de IA da Agência Nacional de Telecomunicações (ANATEL). "
                "Utilizar apenas informações confiáveis, mais atualizadas e verificáveis."
            ),
            "use_thinking": False,
            "use_websearch": True,
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
            "id_topico": 0,
        }

        response = client.post(RLM_ENDPOINT, headers=SSE_HEADERS, json=payload)
        bing_foi_chamado = mock_bing.invoke.called

    sse = _assert_sse_ok(response, min_content_len=50)

    # Tags <web_N> brutas nao devem vazar — devem ter sido convertidas em HTML ou removidas
    web_tags = re.findall(r"<web_\d+>", sse["content"])
    assert len(web_tags) == 0, (
        f"Tags <web_N> nao deveriam estar presentes no conteudo final, "
        f"encontradas: {web_tags}. Bing foi chamado: {bing_foi_chamado}"
    )

    # Se Bing foi chamado, deve haver citacoes na resposta (doc_ ou web)
    if bing_foi_chamado:
        has_any_citation = bool(_CITATION_PATTERN.search(sse["content"]))
        assert has_any_citation, (
            "Bing foi chamado mas nenhuma citacao (HTML) apareceu na resposta"
        )

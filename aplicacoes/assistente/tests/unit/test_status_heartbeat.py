"""Testes unitários para status_heartbeat.

Módulo testado: sei_ia/routers/chat/status_heartbeat.py
"""

from sei_ia.routers.chat.status_heartbeat import (
    INTERMEDIATE_MESSAGES,
    get_next_intermediate_message,
)


class TestIntermediateMessages:
    def test_chaves_esperadas_presentes(self):
        esperadas = {
            "Pesquisando na Internet",
            "Pesquisando informações na Internet",
            "Processando documentos",
            "Recuperando mensagens anteriores do tópico",
            "Vetorizando documentos",
        }
        assert esperadas == set(INTERMEDIATE_MESSAGES.keys())

    def test_todas_as_listas_nao_vazias(self):
        for chave, msgs in INTERMEDIATE_MESSAGES.items():
            assert len(msgs) > 0, f"Lista vazia para '{chave}'"

    def test_todas_as_mensagens_sao_strings(self):
        for msgs in INTERMEDIATE_MESSAGES.values():
            for msg in msgs:
                assert isinstance(msg, str)

    def test_web_search_compartilhada_entre_chaves(self):
        assert (
            INTERMEDIATE_MESSAGES["Pesquisando na Internet"]
            is INTERMEDIATE_MESSAGES["Pesquisando informações na Internet"]
        )


class TestGetNextIntermediateMessage:
    def test_status_desconhecido_retorna_none(self):
        result = get_next_intermediate_message("Status inexistente", None)
        assert result is None

    def test_status_vazio_retorna_none(self):
        result = get_next_intermediate_message("", None)
        assert result is None

    def test_retorna_string_para_status_valido(self):
        result = get_next_intermediate_message("Processando documentos", None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_retorna_mensagem_da_lista_correta(self):
        result = get_next_intermediate_message("Processando documentos", None)
        assert result in INTERMEDIATE_MESSAGES["Processando documentos"]

    def test_evita_repetir_ultima_mensagem(self):
        mensagens = INTERMEDIATE_MESSAGES["Processando documentos"]
        ultima = mensagens[0]
        resultados = {
            get_next_intermediate_message("Processando documentos", ultima)
            for _ in range(30)
        }
        # Com múltiplas opções disponíveis, não deve retornar só a última
        assert len(mensagens) == 1 or ultima not in resultados or len(resultados) > 1

    def test_fallback_quando_so_uma_mensagem_disponivel(self):
        # Se last_msg é a única mensagem, deve retornar ela mesmo assim
        msgs = INTERMEDIATE_MESSAGES["Processando documentos"]
        result = get_next_intermediate_message("Processando documentos", msgs[0])
        assert result in msgs

    def test_web_search_retorna_mensagem_valida(self):
        result = get_next_intermediate_message("Pesquisando na Internet", None)
        assert result in INTERMEDIATE_MESSAGES["Pesquisando na Internet"]

    def test_historico_retorna_mensagem_valida(self):
        result = get_next_intermediate_message(
            "Recuperando mensagens anteriores do tópico", None
        )
        assert (
            result
            in INTERMEDIATE_MESSAGES["Recuperando mensagens anteriores do tópico"]
        )

    def test_vetorizacao_retorna_mensagem_valida(self):
        result = get_next_intermediate_message("Vetorizando documentos", None)
        assert result in INTERMEDIATE_MESSAGES["Vetorizando documentos"]

    def test_resultado_nao_igual_a_last_msg_quando_ha_alternativas(self):
        msgs = INTERMEDIATE_MESSAGES["Processando documentos"]
        if len(msgs) > 1:
            ultima = msgs[0]
            resultados = [
                get_next_intermediate_message("Processando documentos", ultima)
                for _ in range(20)
            ]
            assert any(r != ultima for r in resultados)

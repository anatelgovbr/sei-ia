"""Testes unitários para o módulo chunks.

Módulo testado: sei_ia/services/embedder/chunks.py
"""

from sei_ia.services.embedder.chunks import get_chunks_positions


class TestGetChunksPositions:
    """Testes para a função get_chunks_positions."""

    def test_dicionario_vazio_retorna_vazio(self):
        assert get_chunks_positions({}) == {}

    def test_converte_start_e_finished_para_inicio_e_fim(self):
        entrada = {"doc1": [{"start_position": 0, "finished_position": 100}]}
        resultado = get_chunks_positions(entrada)
        assert resultado["doc1"][0] == {"inicio": 0, "fim": 100}

    def test_multiplos_chunks_por_documento(self):
        entrada = {
            "doc1": [
                {"start_position": 0, "finished_position": 50},
                {"start_position": 51, "finished_position": 100},
            ]
        }
        resultado = get_chunks_positions(entrada)
        assert len(resultado["doc1"]) == 2
        assert resultado["doc1"][0] == {"inicio": 0, "fim": 50}
        assert resultado["doc1"][1] == {"inicio": 51, "fim": 100}

    def test_multiplos_documentos(self):
        entrada = {
            "doc1": [{"start_position": 0, "finished_position": 10}],
            "doc2": [{"start_position": 5, "finished_position": 20}],
        }
        resultado = get_chunks_positions(entrada)
        assert "doc1" in resultado
        assert "doc2" in resultado
        assert resultado["doc1"][0]["inicio"] == 0
        assert resultado["doc2"][0]["inicio"] == 5

    def test_preserva_ordem_dos_chunks(self):
        entrada = {
            "doc1": [
                {"start_position": 200, "finished_position": 300},
                {"start_position": 0, "finished_position": 100},
            ]
        }
        resultado = get_chunks_positions(entrada)
        assert resultado["doc1"][0]["inicio"] == 200
        assert resultado["doc1"][1]["inicio"] == 0

    def test_preserva_ids_dos_documentos(self):
        entrada = {"id_especial_123": [{"start_position": 0, "finished_position": 1}]}
        resultado = get_chunks_positions(entrada)
        assert "id_especial_123" in resultado

    def test_posicoes_zero_sao_preservadas(self):
        entrada = {"doc1": [{"start_position": 0, "finished_position": 0}]}
        resultado = get_chunks_positions(entrada)
        assert resultado["doc1"][0] == {"inicio": 0, "fim": 0}

    def test_documento_sem_chunks(self):
        entrada = {"doc1": []}
        resultado = get_chunks_positions(entrada)
        assert resultado["doc1"] == []

"""Testes unitários para sei_ia/services/llm_models/model_catalog.py."""

from unittest.mock import MagicMock, patch

import pytest


def _mock_response(payload, status_ok=True):
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    if not status_ok:
        mock_resp.raise_for_status.side_effect = Exception("HTTP error")
    return mock_resp


@pytest.fixture(autouse=True)
def _reset_cache():
    """Cada teste começa sem cache — o módulo usa um cache global por processo."""
    from sei_ia.services.llm_models import model_catalog

    model_catalog._catalog_cache = None
    yield
    model_catalog._catalog_cache = None


class TestFetchModelCatalog:
    def test_extrai_model_name_e_tags(self):
        from sei_ia.services.llm_models.model_catalog import get_model_catalog

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds",
                    "litellm_params": {"tags": ["agents:principal"]},
                },
                {
                    "model_name": "openai/seiia-ds-nano",
                    "litellm_params": {"tags": ["agents:explorador", "agents:ocr"]},
                },
            ]
        }
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            catalog = get_model_catalog()

        assert catalog == [
            {
                "model_name": "openai/seiia-ds",
                "tags": ["agents:principal"],
                "reasoning_effort_levels": [],
            },
            {
                "model_name": "openai/seiia-ds-nano",
                "tags": ["agents:explorador", "agents:ocr"],
                "reasoning_effort_levels": [],
            },
        ]

    def test_extrai_reasoning_effort_levels_do_model_info(self):
        from sei_ia.services.llm_models.model_catalog import get_model_catalog

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-gpt-terra",
                    "litellm_params": {"tags": ["agents:principal"]},
                    "model_info": {
                        "base_model": "openai/seiia-ds-gpt-terra",
                        "reasoning_effort_levels": ["none", "low", "medium", "high"],
                    },
                }
            ]
        }
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            catalog = get_model_catalog()

        assert catalog == [
            {
                "model_name": "openai/seiia-ds-gpt-terra",
                "tags": ["agents:principal"],
                "reasoning_effort_levels": ["none", "low", "medium", "high"],
            }
        ]

    def test_entrada_sem_model_name_e_ignorada(self):
        from sei_ia.services.llm_models.model_catalog import get_model_catalog

        payload = {"data": [{"litellm_params": {"tags": ["agents:principal"]}}]}
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            assert get_model_catalog() == []

    def test_entrada_sem_tags_vira_lista_vazia(self):
        from sei_ia.services.llm_models.model_catalog import get_model_catalog

        payload = {"data": [{"model_name": "openai/seiia-ds", "litellm_params": {}}]}
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            assert get_model_catalog() == [
                {
                    "model_name": "openai/seiia-ds",
                    "tags": [],
                    "reasoning_effort_levels": [],
                }
            ]

    def test_erro_http_propaga_excecao_sem_fallback_silencioso(self):
        from sei_ia.services.llm_models.model_catalog import get_model_catalog

        with (
            patch(
                "sei_ia.services.llm_models.model_catalog.httpx.get",
                return_value=_mock_response({}, status_ok=False),
            ),
            pytest.raises(Exception, match="HTTP error"),
        ):
            get_model_catalog()


class TestCatalogCache:
    def test_segunda_chamada_dentro_do_ttl_nao_refaz_a_requisicao(self):
        from sei_ia.services.llm_models.model_catalog import get_model_catalog

        payload = {
            "data": [{"model_name": "openai/seiia-ds", "litellm_params": {"tags": []}}]
        }
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ) as mock_get:
            get_model_catalog()
            get_model_catalog()

        assert mock_get.call_count == 1

    def test_cache_expirado_refaz_a_requisicao(self):
        from sei_ia.services.llm_models import model_catalog

        payload = {
            "data": [{"model_name": "openai/seiia-ds", "litellm_params": {"tags": []}}]
        }
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ) as mock_get:
            model_catalog.get_model_catalog()
            # Força o cache a parecer expirado.
            entries, _ = model_catalog._catalog_cache
            model_catalog._catalog_cache = (
                entries,
                model_catalog.time.monotonic() - model_catalog._CATALOG_TTL_S - 1,
            )
            model_catalog.get_model_catalog()

        assert mock_get.call_count == 2


class TestGetReasoningEffortLevels:
    def test_devolve_niveis_declarados_pro_modelo(self):
        from sei_ia.services.llm_models.model_catalog import (
            get_reasoning_effort_levels,
        )

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-gpt-terra",
                    "litellm_params": {"tags": ["agents:principal"]},
                    "model_info": {
                        "reasoning_effort_levels": ["none", "low", "medium", "high"]
                    },
                }
            ]
        }
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            assert get_reasoning_effort_levels("openai/seiia-ds-gpt-terra") == [
                "none",
                "low",
                "medium",
                "high",
            ]

    def test_modelo_sem_niveis_declarados_devolve_lista_vazia(self):
        from sei_ia.services.llm_models.model_catalog import (
            get_reasoning_effort_levels,
        )

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-embedding",
                    "litellm_params": {"tags": ["agents:embedding"]},
                }
            ]
        }
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            assert get_reasoning_effort_levels("openai/seiia-ds-embedding") == []

    def test_modelo_ausente_do_catalogo_devolve_lista_vazia(self):
        from sei_ia.services.llm_models.model_catalog import (
            get_reasoning_effort_levels,
        )

        payload = {"data": []}
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            assert get_reasoning_effort_levels("nao-cadastrado") == []

    def test_mescla_niveis_quando_model_name_aparece_duplicado(self):
        """Reproduz o bug achado ao vivo em dev (pipeline 21698): a entrada
        fixa do tier (sem reasoning_effort_levels, o template não tem esse
        campo) aparece ANTES da entrada de LITELLM_MODEL_CATALOG que
        redeclara o mesmo model_name só pra anexar os níveis. Parar na
        primeira entrada devolvia lista vazia e bloqueava um
        reasoning_effort válido.
        """
        from sei_ia.services.llm_models.model_catalog import (
            get_reasoning_effort_levels,
        )

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-gpt-terra",
                    "litellm_params": {"tags": ["agents:principal"]},
                    "model_info": {},
                },
                {
                    "model_name": "openai/seiia-ds-gpt-terra",
                    "litellm_params": {"tags": ["agents:principal"]},
                    "model_info": {
                        "reasoning_effort_levels": ["none", "low", "medium", "high"]
                    },
                },
            ]
        }
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            assert get_reasoning_effort_levels("openai/seiia-ds-gpt-terra") == [
                "none",
                "low",
                "medium",
                "high",
            ]

    def test_niveis_desconhecidos_de_antemao_nao_precisam_de_mudanca_de_codigo(self):
        """A ordem vem do próprio catálogo, não de uma lista fixa em código —
        um proxy configurado com um nível de reasoning_effort novo (não é
        none/low/medium/high) tem que funcionar sem tocar nesta função."""
        from sei_ia.services.llm_models.model_catalog import (
            get_reasoning_effort_levels,
        )

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-gpt-experimental",
                    "litellm_params": {"tags": ["agents:principal"]},
                    "model_info": {
                        "reasoning_effort_levels": ["off", "ultrathink", "low"]
                    },
                }
            ]
        }
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            assert get_reasoning_effort_levels("openai/seiia-ds-gpt-experimental") == [
                "off",
                "ultrathink",
                "low",
            ]


class TestValidateReasoningEffort:
    @pytest.mark.asyncio
    async def test_nivel_declarado_nao_levanta(self):
        from sei_ia.services.llm_models.model_catalog import validate_reasoning_effort

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-gpt-terra",
                    "litellm_params": {"tags": ["agents:principal"]},
                    "model_info": {"reasoning_effort_levels": ["low", "medium"]},
                }
            ]
        }
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            await validate_reasoning_effort("openai/seiia-ds-gpt-terra", "medium")

    @pytest.mark.asyncio
    async def test_nivel_nao_declarado_levanta_value_error(self):
        from sei_ia.services.llm_models.model_catalog import validate_reasoning_effort

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-gpt-terra",
                    "litellm_params": {"tags": ["agents:principal"]},
                    "model_info": {"reasoning_effort_levels": ["low", "medium"]},
                }
            ]
        }
        with (
            patch(
                "sei_ia.services.llm_models.model_catalog.httpx.get",
                return_value=_mock_response(payload),
            ),
            pytest.raises(ValueError, match="high"),
        ):
            await validate_reasoning_effort("openai/seiia-ds-gpt-terra", "high")

    @pytest.mark.asyncio
    async def test_modelo_sem_niveis_declarados_sempre_levanta(self):
        """Sem informação no model_info, nenhum reasoning_effort é aceito —
        nunca passa silencioso."""
        from sei_ia.services.llm_models.model_catalog import validate_reasoning_effort

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-embedding",
                    "litellm_params": {"tags": ["agents:embedding"]},
                }
            ]
        }
        with (
            patch(
                "sei_ia.services.llm_models.model_catalog.httpx.get",
                return_value=_mock_response(payload),
            ),
            pytest.raises(ValueError, match="nenhum"),
        ):
            await validate_reasoning_effort("openai/seiia-ds-embedding", "low")


class TestValidateModelOverride:
    @pytest.mark.asyncio
    async def test_alias_com_tag_principal_nao_levanta(self):
        from sei_ia.services.llm_models.model_catalog import validate_model_override

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-gemini-pro",
                    "litellm_params": {"tags": ["agents:principal"]},
                }
            ]
        }
        with patch(
            "sei_ia.services.llm_models.model_catalog.httpx.get",
            return_value=_mock_response(payload),
        ):
            await validate_model_override("openai/seiia-ds-gemini-pro")

    @pytest.mark.asyncio
    async def test_alias_inexistente_levanta_value_error(self):
        from sei_ia.services.llm_models.model_catalog import validate_model_override

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-gemini-pro",
                    "litellm_params": {"tags": ["agents:principal"]},
                }
            ]
        }
        with (
            patch(
                "sei_ia.services.llm_models.model_catalog.httpx.get",
                return_value=_mock_response(payload),
            ),
            pytest.raises(ValueError, match="modelo-arbitrario"),
        ):
            await validate_model_override("modelo-arbitrario")

    @pytest.mark.asyncio
    async def test_alias_existe_mas_sem_tag_principal_levanta_value_error(self):
        """Modelo real no proxy, mas sem a tag agents:principal — não é override
        válido pro papel principal, nunca passa silencioso."""
        from sei_ia.services.llm_models.model_catalog import validate_model_override

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-nano",
                    "litellm_params": {"tags": ["agents:ocr"]},
                }
            ]
        }
        with (
            patch(
                "sei_ia.services.llm_models.model_catalog.httpx.get",
                return_value=_mock_response(payload),
            ),
            pytest.raises(ValueError, match="agents:principal"),
        ):
            await validate_model_override("openai/seiia-ds-nano")

    @pytest.mark.asyncio
    async def test_lista_de_aliases_no_erro_nao_duplica_model_name_repetido(self):
        """Mesmo bug de duplicação do catálogo (ver TestGetReasoningEffortLevels):
        o alias aparece duas vezes no /model/info (entrada fixa do tier +
        entrada de LITELLM_MODEL_CATALOG) — a lista de aliases liberados na
        mensagem de erro não deve repetir o mesmo nome."""
        from sei_ia.services.llm_models.model_catalog import validate_model_override

        payload = {
            "data": [
                {
                    "model_name": "openai/seiia-ds-gpt-terra",
                    "litellm_params": {"tags": ["agents:principal"]},
                    "model_info": {},
                },
                {
                    "model_name": "openai/seiia-ds-gpt-terra",
                    "litellm_params": {"tags": ["agents:principal"]},
                    "model_info": {
                        "reasoning_effort_levels": ["none", "low", "medium", "high"]
                    },
                },
            ]
        }
        with (
            patch(
                "sei_ia.services.llm_models.model_catalog.httpx.get",
                return_value=_mock_response(payload),
            ),
            pytest.raises(
                ValueError,
                match=r"\['openai/seiia-ds-gpt-terra'\]",
            ),
        ):
            await validate_model_override("openai/modelo-inexistente")

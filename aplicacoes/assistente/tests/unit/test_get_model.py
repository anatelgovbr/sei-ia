"""Testes unitários para o módulo get_model.

Cobre a construção de configurações por papel de agente (tag agents:<papel>
mandada ao LiteLLM Proxy), a omissão de temperature quando não informada e a
função de sumarização.

Módulo testado: sei_ia/services/llm_models/get_model.py
"""

from unittest.mock import MagicMock, patch

import pytest


class TestGetModelConfig:
    """Testes para get_model_config."""

    @pytest.mark.parametrize("agent_tag", ["principal", "classificador", "explorador"])
    def test_tipos_validos_retornam_dict(self, agent_tag):
        from sei_ia.services.llm_models.get_model import get_model_config

        assert isinstance(get_model_config(agent_tag), dict)

    @pytest.mark.parametrize("agent_tag", ["principal", "classificador", "explorador"])
    def test_chaves_obrigatorias_presentes(self, agent_tag):
        from sei_ia.services.llm_models.get_model import get_model_config

        config = get_model_config(agent_tag)
        for chave in (
            "base_url",
            "api_key",
            "timeout",
            "max_retries",
            "model",
            "max_ctx_len",
            "tags",
        ):
            assert chave in config

    def test_tipo_invalido_levanta_value_error(self):
        from sei_ia.services.llm_models.get_model import get_model_config

        with pytest.raises(ValueError, match="Papel de agente desconhecido"):
            get_model_config("inexistente")

    def test_tipo_invalido_mensagem_lista_validos(self):
        from sei_ia.services.llm_models.get_model import get_model_config

        with pytest.raises(ValueError, match="principal"):
            get_model_config("errado")

    @pytest.mark.parametrize("agent_tag", ["principal", "classificador", "explorador"])
    def test_base_url_aponta_para_proxy(self, agent_tag):
        from sei_ia.configs.settings_config import settings
        from sei_ia.services.llm_models.get_model import get_model_config

        assert get_model_config(agent_tag)["base_url"] == settings.LITELLM_PROXY_URL

    @pytest.mark.parametrize(
        ("agent_tag", "physical_setting", "physical_model", "public_alias"),
        [
            ("principal", "LITELLM_STANDARD_MODEL", "provider/standard", "standard"),
            ("classificador", "LITELLM_MINI_MODEL", "provider/mini", "mini"),
            ("explorador", "LITELLM_NANO_MODEL", "provider/nano", "nano"),
        ],
    )
    def test_modelo_padrao_usa_alias_publico_e_preserva_identidade_fisica(
        self, monkeypatch, agent_tag, physical_setting, physical_model, public_alias
    ):
        from sei_ia.configs.settings_config import settings
        from sei_ia.services.llm_models.get_model import get_model_config

        monkeypatch.setattr(settings, physical_setting, physical_model)

        config = get_model_config(agent_tag)

        assert config["model"] == public_alias
        assert config["model_name"] == physical_model

    def test_think_nao_e_papel_valido(self):
        from sei_ia.services.llm_models.get_model import get_model_config

        with pytest.raises(ValueError, match="Papel de agente desconhecido"):
            get_model_config("think")

    @pytest.mark.parametrize("agent_tag", ["principal", "classificador", "explorador"])
    def test_config_nao_define_limite_de_saida(self, agent_tag):
        from sei_ia.services.llm_models.get_model import get_model_config

        config = get_model_config(agent_tag)

        assert "max_tokens" not in config
        assert "max_output_tokens" not in config
        assert "max_completion_tokens" not in config

    def test_explorador_tem_contexto_menor_que_principal(self):
        from sei_ia.services.llm_models.get_model import get_model_config

        assert (
            get_model_config("explorador")["max_ctx_len"]
            <= get_model_config("principal")["max_ctx_len"]
        )

    def test_api_key_dummy_quando_nao_configurada(self):
        from sei_ia.services.llm_models.get_model import get_model_config

        config = get_model_config("classificador")
        assert config["api_key"] is not None
        assert len(config["api_key"]) > 0

    @pytest.mark.parametrize(
        ("agent_tag", "expected_tag"),
        [
            ("principal", "agents:principal"),
            ("classificador", "agents:classificador"),
            ("busca_web", "agents:busca_web"),
            ("explorador", "agents:explorador"),
            ("ocr", "agents:ocr"),
            ("triagem_busca", "agents:triagem_busca"),
        ],
    )
    def test_tags_mandada_ao_litellm_bate_com_agent_tag(self, agent_tag, expected_tag):
        from sei_ia.services.llm_models.get_model import get_model_config

        assert get_model_config(agent_tag)["tags"] == [expected_tag]

    def test_model_override_substitui_alias_fixo(self):
        from sei_ia.services.llm_models.get_model import get_model_config

        config = get_model_config(
            "principal", model_override="openai/seiia-ds-gemini-pro"
        )
        assert config["model"] == "openai/seiia-ds-gemini-pro"

    def test_model_override_substitui_model_name_para_metadata(self):
        from sei_ia.services.llm_models.get_model import get_model_config

        config = get_model_config(
            "principal", model_override="openai/seiia-ds-gemini-pro"
        )
        assert config["model_name"] == "openai/seiia-ds-gemini-pro"

    def test_model_override_mantem_tag_do_papel(self):
        from sei_ia.services.llm_models.get_model import get_model_config

        config = get_model_config(
            "principal", model_override="openai/seiia-ds-gemini-pro"
        )
        assert config["tags"] == ["agents:principal"]

    def test_sem_model_override_mantem_alias_fixo(self):
        from sei_ia.services.llm_models.get_model import get_model_config

        config = get_model_config("principal", model_override=None)
        assert config["model"] == "standard"


class TestGetModel:
    """Testes para get_model."""

    def test_temperature_omitida_por_padrao(self):
        from sei_ia.services.llm_models.get_model import get_model

        mock_chat = MagicMock()
        with patch(
            "sei_ia.services.llm_models.get_model.ChatOpenAI", return_value=mock_chat
        ) as cls:
            get_model("principal")

        assert "temperature" not in cls.call_args.kwargs

    def test_limite_de_saida_fica_a_cargo_do_provider(self):
        from sei_ia.services.llm_models.get_model import get_model

        mock_chat = MagicMock()
        with patch(
            "sei_ia.services.llm_models.get_model.ChatOpenAI", return_value=mock_chat
        ) as cls:
            get_model("principal")

        assert "max_tokens" not in cls.call_args.kwargs
        assert "max_completion_tokens" not in cls.call_args.kwargs
        assert "max_output_tokens" not in cls.call_args.kwargs

    def test_responses_api_omite_temperature_por_padrao(self):
        from sei_ia.services.llm_models.get_model import get_model

        mock_chat = MagicMock()
        with patch(
            "sei_ia.services.llm_models.get_model.ChatOpenAI", return_value=mock_chat
        ) as cls:
            get_model("principal", use_responses_api=True)

        assert "temperature" not in cls.call_args.kwargs

    def test_responses_api_preserva_temperature_informada(self):
        from sei_ia.services.llm_models.get_model import get_model

        mock_chat = MagicMock()
        with patch(
            "sei_ia.services.llm_models.get_model.ChatOpenAI", return_value=mock_chat
        ) as cls:
            get_model("principal", temperature=0.7, use_responses_api=True)

        assert cls.call_args.kwargs["temperature"] == 0.7

    def test_classificador_preserva_temperature_informada(self):
        from sei_ia.services.llm_models.get_model import get_model

        mock_chat = MagicMock()
        with patch(
            "sei_ia.services.llm_models.get_model.ChatOpenAI", return_value=mock_chat
        ) as cls:
            get_model("classificador", temperature=0.7)

        assert cls.call_args.kwargs["temperature"] == 0.7

    def test_retorna_instancia_chatopenai(self):
        from sei_ia.services.llm_models.get_model import get_model

        mock_chat = MagicMock()
        with patch(
            "sei_ia.services.llm_models.get_model.ChatOpenAI", return_value=mock_chat
        ):
            resultado = get_model("classificador")

        assert resultado is mock_chat

    def test_tipo_invalido_levanta_value_error(self):
        from sei_ia.services.llm_models.get_model import get_model

        with pytest.raises(ValueError):
            get_model("invalido")

    def test_api_key_nao_exposta_no_log_debug(self):
        from sei_ia.services.llm_models.get_model import get_model

        mock_chat = MagicMock()
        with (
            patch(
                "sei_ia.services.llm_models.get_model.ChatOpenAI",
                return_value=mock_chat,
            ),
            patch("sei_ia.services.llm_models.get_model.logger") as mock_logger,
        ):
            get_model("classificador")

        for call in mock_logger.debug.call_args_list:
            assert "api_key" not in str(call)

    def test_kwargs_extras_repassados_ao_chatopenai(self):
        from sei_ia.services.llm_models.get_model import get_model

        mock_chat = MagicMock()
        with patch(
            "sei_ia.services.llm_models.get_model.ChatOpenAI", return_value=mock_chat
        ) as cls:
            get_model("classificador", streaming=True)

        assert cls.call_args.kwargs.get("streaming") is True

    def test_response_format_vai_para_model_kwargs(self):
        from sei_ia.services.llm_models.get_model import get_model

        mock_chat = MagicMock()
        fmt = {"type": "json_object"}
        with patch(
            "sei_ia.services.llm_models.get_model.ChatOpenAI", return_value=mock_chat
        ) as cls:
            get_model("classificador", response_format=fmt)

        model_kwargs = cls.call_args.kwargs.get("model_kwargs", {})
        assert model_kwargs.get("response_format") == fmt

    def test_tags_vao_para_extra_body(self):
        from sei_ia.services.llm_models.get_model import get_model

        mock_chat = MagicMock()
        with patch(
            "sei_ia.services.llm_models.get_model.ChatOpenAI", return_value=mock_chat
        ) as cls:
            get_model("ocr")

        extra_body = cls.call_args.kwargs.get("extra_body", {})
        assert extra_body.get("tags") == ["agents:ocr"]

    def test_get_llm_model_e_alias_de_get_model(self):
        from sei_ia.services.llm_models.get_model import get_llm_model, get_model

        assert get_llm_model is get_model


class TestGetSummarizeModel:
    """Testes para get_summarize_model."""

    def test_omite_temperatura_de_sumarizacao(self):
        from sei_ia.services.llm_models.get_model import get_summarize_model

        assert "temperature" not in get_summarize_model()

    def test_inclui_encoding_configurado(self):
        from sei_ia.configs.settings_config import settings
        from sei_ia.services.llm_models.get_model import get_summarize_model

        assert (
            get_summarize_model()["token_encoding_name"]
            == settings.SUMMARIZE_ENCODING_NAME
        )

    def test_inclui_chunk_size_configurado(self):
        from sei_ia.configs.settings_config import settings
        from sei_ia.services.llm_models.get_model import get_summarize_model

        assert get_summarize_model()["chunk_size"] == settings.SUMMARIZE_CHUNK_SIZE

    def test_herda_base_url_do_proxy(self):
        from sei_ia.configs.settings_config import settings
        from sei_ia.services.llm_models.get_model import get_summarize_model

        assert get_summarize_model()["base_url"] == settings.LITELLM_PROXY_URL


class TestGetModelErroCriacao:
    """Cobre o bloco except em get_model quando ChatOpenAI levanta exceção."""

    def test_excecao_na_criacao_e_relancada(self):
        from sei_ia.services.llm_models.get_model import get_model

        with (
            patch(
                "sei_ia.services.llm_models.get_model.ChatOpenAI",
                side_effect=ValueError("configuração inválida"),
            ),
            pytest.raises(ValueError, match="configuração inválida"),
        ):
            get_model("classificador")

    def test_erro_logado_sem_api_key(self):
        from sei_ia.services.llm_models.get_model import get_model

        with (
            patch(
                "sei_ia.services.llm_models.get_model.ChatOpenAI",
                side_effect=RuntimeError("falha"),
            ),
            patch("sei_ia.services.llm_models.get_model.logger") as mock_logger,
            pytest.raises(RuntimeError),
        ):
            get_model("classificador")

        logged = " ".join(str(c) for c in mock_logger.error.call_args_list)
        assert "api_key" not in logged

"""Testes unitários para `truncate_large_fields` em langfuse_config.

Foco: garantir que o mask aplicado no Langfuse client redacta `image_url`
data URLs com base64 longo (uploads multimodais), preservando o header
(`data:<mime>;base64,`) e o tamanho aproximado, mas removendo o payload.

Sem isso, traces do Langfuse carregariam MBs de base64 por requisição
quando o usuário faz upload de imagem.
"""

import json
from dataclasses import dataclass

from langchain_core.messages import HumanMessage

from sei_ia.configs import langfuse_config
from sei_ia.configs.langfuse_config import (
    MAX_LANGFUSE_PAYLOAD_CHARS,
    _redact_data_url,
    initialize_langfuse_singleton,
    mask_langfuse_payload,
    truncate_langfuse_request_body,
    truncate_large_fields,
)
from sei_ia.configs.settings_config import Settings
from sei_ia.data.pydantic_models import ItemDocumentRequest, ItemRequestIdProcedimento


class TestRedactDataUrl:
    """Testes para o helper `_redact_data_url`."""

    def test_data_url_grande_e_redactado_preservando_header(self):
        long_payload = "A" * 4096  # ~3 KB de base64 fake
        url = f"data:image/png;base64,{long_payload}"
        redacted = _redact_data_url(url)
        assert redacted.startswith("data:image/png;base64,<redacted:")
        assert long_payload not in redacted
        # Tamanho aproximado ~ 3KB
        assert "KB" in redacted

    def test_data_url_pequeno_passa_sem_redact(self):
        url = "data:image/png;base64,iVBORw0KGgo"  # < 256 chars
        assert _redact_data_url(url) == url

    def test_url_normal_nao_e_modificada(self):
        url = "https://example.com/imagem.png"
        assert _redact_data_url(url) == url

    def test_jpeg_megabyte_reporta_em_mb(self):
        # ~1.5 MB de base64 (=~1.1 MB de binário decodificado)
        payload = "B" * (1_500_000)
        url = f"data:image/jpeg;base64,{payload}"
        redacted = _redact_data_url(url)
        assert "MB" in redacted
        assert "data:image/jpeg;base64," in redacted

    def test_payload_curto_em_bytes(self):
        # Limite exato 256 chars (passa direto, sem redact)
        url = "data:image/png;base64," + "C" * 255
        assert _redact_data_url(url) == url

        # 257 chars já redacta
        url2 = "data:image/png;base64," + "C" * 257
        redacted = _redact_data_url(url2)
        assert "<redacted:" in redacted
        assert "B" in redacted  # tamanho em bytes


class TestLangfuseTraceMaskConfiguration:
    """Default seguro e opt-out textual explícito para benchmark isolado."""

    _REQUIRED_SETTINGS = {
        "DB_SEIIA_HOST": "localhost",
        "DB_SEIIA_PORT": "5432",
        "DB_SEIIA_USER": "test",
        "DB_SEIIA_PWD": "test",
        "SEI_API_DB_ADDRESS": "https://example.invalid",
        "SEI_API_DB_IDENTIFIER_SERVICE": "test",
    }

    def test_truncamento_textual_e_ativo_por_default(self, monkeypatch):
        monkeypatch.delenv("ASSISTENTE_LANGFUSE_TRUNCATE_PAYLOADS", raising=False)

        parsed = Settings(_env_file=None, **self._REQUIRED_SETTINGS)

        assert parsed.LANGFUSE_TRUNCATE_PAYLOADS is True

    def test_opt_out_false_e_parseado_da_variavel(self):
        parsed = Settings(
            _env_file=None,
            ASSISTENTE_LANGFUSE_TRUNCATE_PAYLOADS="false",
            **self._REQUIRED_SETTINGS,
        )

        assert parsed.LANGFUSE_TRUNCATE_PAYLOADS is False

    def test_retries_do_llm_e_do_transporte_sei_sao_independentes(self):
        parsed = Settings(
            _env_file=None,
            ASSISTENTE_MAX_RETRIES=0,
            ASSISTENTE_SEI_API_MAX_RETRIES=5,
            **self._REQUIRED_SETTINGS,
        )

        assert parsed.MAX_RETRIES == 0
        assert parsed.SEI_API_MAX_RETRIES == 5

    def test_singleton_entrega_mascara_configuravel_ao_sdk(self, monkeypatch):
        captured = {}

        def fake_langfuse(**kwargs):
            captured.update(kwargs)
            return object()

        monkeypatch.setattr("langfuse.Langfuse", fake_langfuse)
        monkeypatch.setattr(langfuse_config.settings, "USE_LANGFUSE", True)
        monkeypatch.setattr(langfuse_config.settings, "LANGFUSE_PUBLIC_KEY", "test")
        monkeypatch.setattr(langfuse_config.settings, "LANGFUSE_SECRET_KEY", "test")
        monkeypatch.setattr(
            langfuse_config.settings, "LANGFUSE_URL", "https://example.invalid"
        )
        monkeypatch.setattr(langfuse_config, "_langfuse_client", [None])

        initialize_langfuse_singleton()

        assert captured["mask"] is mask_langfuse_payload

    def test_opt_out_preserva_texto_e_mantem_redaction_de_midia(self, monkeypatch):
        monkeypatch.setattr(
            langfuse_config.settings, "LANGFUSE_TRUNCATE_PAYLOADS", False
        )
        text = "T" * 20_000
        media = "M" * 4_096

        masked = mask_langfuse_payload(
            {
                "content": text,
                "image_url": {"url": f"data:image/png;base64,{media}"},
            }
        )

        assert masked["content"] == text
        assert masked["image_url"]["url"].startswith("data:image/png;base64,<redacted:")
        assert media not in masked["image_url"]["url"]


class TestTruncateLargeFieldsImageUrl:
    """Testes do `truncate_large_fields` aplicado a estruturas multimodais
    do LangChain (HumanMessage.content como lista com `image_url`)."""

    def test_image_url_dentro_de_content_part_e_redactado(self):
        # Estrutura exata que vai pro LLM: lista de content parts
        long_payload = "X" * 4096
        message_content = [
            {"type": "text", "text": "Analise a imagem."},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{long_payload}"},
            },
        ]
        masked = truncate_large_fields(message_content)
        assert masked[0] == {"type": "text", "text": "Analise a imagem."}
        url = masked[1]["image_url"]["url"]
        assert "<redacted:" in url
        assert long_payload not in url

    def test_state_completo_com_imagem_nao_explode(self):
        """Cenário aproximado do user_state passado ao trace do Langfuse."""
        long_payload = "Y" * 8192
        state = {
            "user_request": "<user_request>foo</user_request>",
            "system_prompt": "...",
            "image_attachments": [
                {
                    "filename": "captura.png",
                    "mime": "image/png",
                    "fs_path": "/tmp/uploads-1/captura.png",
                    "size_bytes": 245_000,
                }
            ],
            "messages": [
                {
                    "type": "human",
                    "content": [
                        {"type": "text", "text": "Vê a captura"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{long_payload}"
                            },
                        },
                    ],
                }
            ],
        }
        masked = truncate_large_fields(state)
        # state["image_attachments"] tem apenas metadado → passa sem mudança
        assert masked["image_attachments"][0]["filename"] == "captura.png"
        assert masked["image_attachments"][0]["size_bytes"] == 245_000
        # O `url` dentro de messages[0].content[1].image_url foi redactado
        masked_url = masked["messages"][0]["content"][1]["image_url"]["url"]
        assert "<redacted:" in masked_url
        assert long_payload not in masked_url

    def test_texto_normal_nao_e_afetado(self):
        data = {"foo": "bar", "list": [1, 2, "qux"]}
        assert truncate_large_fields(data) == data


class TestTruncateLargeFieldsStructuredValues:
    """Regressões para objetos estruturados capturados pelo LangGraph."""

    def test_documento_pydantic_e_convertido_e_truncado(self):
        document = ItemDocumentRequest(
            id_documento="17867467",
            content="X" * 10_000,
        )
        procedure = ItemRequestIdProcedimento(
            id_procedimento="15967473",
            id_documentos=[document],
        )

        masked = truncate_large_fields({"id_procedimentos": [procedure]})

        masked_content = masked["id_procedimentos"][0]["id_documentos"][0]["content"]
        assert masked_content.startswith("X" * 3_000)
        assert masked_content.endswith("[truncado: 7000 caracteres]")

    def test_human_message_com_imagem_e_redactada(self):
        payload = "A" * 4_096
        message = HumanMessage(
            content=[
                {"type": "text", "text": "Analise a imagem."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{payload}"},
                },
            ]
        )

        masked = truncate_large_fields({"messages": [message]})

        masked_message = masked["messages"][0]
        masked_url = masked_message["content"][1]["image_url"]["url"]
        assert isinstance(masked_message, dict)
        assert "<redacted:" in masked_url
        assert payload not in masked_url

    def test_dataclass_e_convertida(self):
        @dataclass
        class Attachment:
            content: str

        masked = truncate_large_fields({"attachment": Attachment("Y" * 10_000)})

        masked_content = masked["attachment"]["content"]
        assert masked_content.endswith("[truncado: 7000 caracteres]")

    def test_truncamento_e_idempotente(self):
        data = {"content": "Z" * 10_000}

        masked_once = truncate_large_fields(data)
        masked_twice = truncate_large_fields(masked_once)

        assert masked_twice == masked_once

    def test_payload_total_excedido_vira_resumo(self):
        item_size = MAX_LANGFUSE_PAYLOAD_CHARS // 10 + 1
        data = {"items": ["R" * item_size for _ in range(11)]}

        masked = truncate_large_fields(data)

        assert "_truncated" in masked
        assert str(MAX_LANGFUSE_PAYLOAD_CHARS) in masked["_truncated"]
        assert "caracteres" in masked["_truncated"]

    def test_original_request_body_permanece_json_textual_copiavel(self):
        original = json.dumps(
            {
                "id_usuario": 1,
                "id_topico": 2,
                "text": "P" * 5_000,
                "id_procedimentos": [
                    {
                        "id_procedimento": "PROC-1",
                        "id_documentos": [{"id_documento": "DOC-1"}],
                    }
                ],
            },
            ensure_ascii=False,
        )

        masked = truncate_large_fields({"original_request_body": f"\\{original}"})

        assert isinstance(masked["original_request_body"], str)
        assert masked["original_request_body"] == f"\\{original}"
        assert json.loads(masked["original_request_body"][1:])["text"] == "P" * 5_000

    def test_original_request_body_classico_continua_limitado(self):
        original = json.dumps(
            {"id_usuario": 1, "id_topico": 2, "text": "P" * 20_000},
            ensure_ascii=False,
        )

        masked = truncate_large_fields({"original_request_body": original})

        assert len(masked["original_request_body"]) < len(original)
        assert masked["original_request_body"].endswith("caracteres]")

    def test_original_request_body_truncado_nao_vira_resumo(self):
        text = "P" * (MAX_LANGFUSE_PAYLOAD_CHARS + 1)
        original = json.dumps(
            {"id_usuario": 1, "id_topico": 2, "text": text},
            ensure_ascii=False,
        )
        truncated = truncate_langfuse_request_body(original)
        root_input = json.dumps(truncated, ensure_ascii=False)
        metadata = {"original_request_body": f"\\{truncated}"}

        masked_root = truncate_large_fields(root_input)
        masked_metadata = truncate_large_fields(metadata)

        assert masked_root == root_input
        assert masked_metadata == metadata
        assert truncated.startswith(original[:MAX_LANGFUSE_PAYLOAD_CHARS])
        assert truncated.endswith(" caracteres]")
        assert "_truncated" not in masked_metadata

    def test_original_request_truncado_nao_vira_resumo(self):
        text = "P" * (MAX_LANGFUSE_PAYLOAD_CHARS + 1)
        original = json.dumps(
            {"id_usuario": 1, "id_topico": 2, "text": text},
            ensure_ascii=False,
        )
        truncated = truncate_langfuse_request_body(original)
        metadata = {"original_request": f"\\{truncated}"}

        masked = truncate_large_fields(metadata)

        assert masked == metadata
        assert "_truncated" not in masked

    def test_original_request_grande_permanece_json_textual_copiavel(self):
        original = json.dumps(
            {"id_usuario": 1, "id_topico": 2, "text": "P" * 20_000},
            ensure_ascii=False,
        )

        masked = truncate_large_fields({"original_request": f"\\{original}"})

        assert masked["original_request"] == f"\\{original}"
        assert json.loads(masked["original_request"][1:])["text"] == "P" * 20_000

    def test_json_textual_na_raiz_nao_recebe_sufixo_de_truncamento(self):
        original = json.dumps(
            {"id_usuario": 1, "id_topico": 2, "text": "P" * 20_000},
            ensure_ascii=False,
        )

        masked = truncate_large_fields(original)

        assert isinstance(masked, str)
        assert masked == original
        assert json.loads(masked)["text"] == "P" * 20_000

    def test_transporte_textual_do_langfuse_permanece_json_valido(self):
        original = json.dumps(
            {"id_usuario": 1, "id_topico": 2, "text": "P" * 20_000},
            ensure_ascii=False,
        )
        transport = json.dumps(original, ensure_ascii=False)

        masked = truncate_large_fields(transport)

        assert masked == transport
        assert json.loads(masked) == original


class TestTruncateLargeFieldsWebBodies:
    def test_corpo_bruto_da_web_e_truncado(self):
        """O trace guarda uma amostra, nunca a página inteira do crawler."""
        body = "<html>" + ("x" * 20_000) + "</html>"

        masked = truncate_large_fields({"rawHtml": body, "response_body": body})

        assert len(masked["rawHtml"]) < len(body)
        assert len(masked["response_body"]) < len(body)
        assert "[TRUNCATED:" in masked["rawHtml"]
        assert "[TRUNCATED:" in masked["response_body"]

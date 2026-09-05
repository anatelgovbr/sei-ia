"""Testes de resolução de configurações derivadas do assistente."""

from pytest import MonkeyPatch

from sei_ia.configs.settings_config import Settings

_REQUIRED_SETTINGS = {
    "DB_SEIIA_HOST": "localhost",
    "DB_SEIIA_PORT": "5432",
    "DB_SEIIA_USER": "test",
    "DB_SEIIA_PWD": "test",
    "SEI_API_DB_ADDRESS": "https://example.invalid",
    "SEI_API_DB_IDENTIFIER_SERVICE": "test",
}


def test_ocr_reutiliza_o_alias_publico_nano_quando_nao_ha_override(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASSISTENTE_OCR_MODEL", raising=False)
    settings = Settings(
        _env_file=None,
        LITELLM_NANO_MODEL="provider/nano-physical",
        **_REQUIRED_SETTINGS,
    )

    assert settings.OCR_MODEL == "nano"


def test_ocr_preserva_override_explicito() -> None:
    settings = Settings(
        _env_file=None,
        LITELLM_NANO_MODEL="seiia-ds-nano",
        ASSISTENTE_OCR_MODEL="ocr-vision-custom",
        **_REQUIRED_SETTINGS,
    )

    assert settings.OCR_MODEL == "ocr-vision-custom"


def test_identidade_da_tabela_de_embeddings_permanece_no_modelo_fisico() -> None:
    settings = Settings(
        _env_file=None,
        LITELLM_EMBEDDING_MODEL="provider/embedding-physical",
        ASSISTENTE_EMBEDDING_MODEL="embedding",
        ASSISTENTE_EMBEDDING_ENCODING_NAME="cl100k_base",
        ASSISTENTE_EMBEDDING_DIMENSION=7,
        ASSISTENTE_MAX_LENGTH_CHUNK_SIZE=24,
        ASSISTENTE_CHUNK_OVERLAP=4,
        **_REQUIRED_SETTINGS,
    )

    assert settings.EMBEDDINGS_TABLE_NAME == "provider_embedding_physical_24_4"
    assert settings.EMBEDDING_ENCODING_NAME == "cl100k_base"
    assert settings.EMBEDDING_DIMENSION == 7
    assert settings.MAX_LENGTH_CHUNK_SIZE == 24
    assert settings.CHUNK_OVERLAP == 4

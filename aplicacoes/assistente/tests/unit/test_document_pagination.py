"""Testes unitários para paginação de documentos baseada no payload."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sei_ia.data.etl.extract.doc_content import (
    _get_doc_content_internal,
    get_doc_from_id_async,
)

ADAPTERS = "sei_ia.data.etl.extract.sei_adapters"


class TestDocContentPagination:
    """Testes para roteamento orientado por `download_ext` no payload."""

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch("sei_ia.data.etl.extract.doc_content.get_type_doc_from_id")
    async def test_sync_uses_content_doc_when_download_ext_false(
        self, mock_get_type_doc_from_id, mock_fetch_content
    ):
        """download_ext=False com num_doc fora da lista de paginação → Rota A direta."""
        mock_get_type_doc_from_id.return_value = (False, "pdf", "555", "proc-1")
        mock_fetch_content.return_value = {
            "content_doc": "conteudo",
            "extra_metadata": {},
        }

        content, formatted_id = await _get_doc_content_internal(
            "doc-1", [("123", 1, 10)], False
        )

        assert content == "conteudo"
        assert formatted_id == "555"
        mock_fetch_content.assert_called_once_with("doc-1")

    @pytest.mark.asyncio
    @patch("sei_extraction.document_fetch.extract_document", return_value="conteudo")
    @patch(f"{ADAPTERS}.SeiApiFileDownloader.download", return_value="/tmp/fake.pdf")
    @patch("sei_ia.data.etl.extract.doc_content.get_type_doc_from_id")
    async def test_async_applies_range_when_download_ext_true(
        self, mock_get_type_doc_from_id, mock_download, mock_extract
    ):
        """Paginação só vale quando o payload autoriza download (`download_ext=True`)."""
        mock_get_type_doc_from_id.return_value = (False, "pdf", "123", "proc-1")

        content, formatted_id, _ = await get_doc_from_id_async(
            "doc-1", [("123", 1, 10)], True
        )

        assert content == "conteudo"
        assert formatted_id == "123"
        mock_download.assert_called_once_with("doc-1", "pdf")
        mock_extract.assert_called_once()
        _, kwargs = mock_extract.call_args
        assert kwargs.get("pag_ini") == 1
        assert kwargs.get("pag_fim") == 10

    @pytest.mark.asyncio
    @patch(f"{ADAPTERS}.SeiApiContentSource.fetch_content_doc")
    @patch("sei_ia.data.etl.extract.doc_content.get_type_doc_from_id")
    async def test_async_uses_content_doc_for_non_paginated_document(
        self, mock_get_type_doc_from_id, mock_fetch_content
    ):
        """Documento sem paginação no payload e download_ext=False → Rota A direta."""
        mock_get_type_doc_from_id.return_value = (False, "pdf", "555", "proc-1")
        mock_fetch_content.return_value = {
            "content_doc": "conteudo",
            "extra_metadata": {},
        }

        content, formatted_id, _ = await get_doc_from_id_async(
            "doc-1", [("123", 1, 10)], False
        )

        assert content == "conteudo"
        assert formatted_id == "555"
        mock_fetch_content.assert_called_once_with("doc-1")

    @pytest.mark.asyncio
    @patch("sei_ia.data.etl.extract.doc_content.get_type_doc_from_id")
    async def test_async_rejects_pagination_without_download_ext(
        self, mock_get_type_doc_from_id
    ):
        """Paginação sem download_ext=True deve falhar com 406."""
        from sei_ia.services.exceptions.http_exceptions import HTTPException406

        mock_get_type_doc_from_id.return_value = (False, "pdf", "123", "proc-1")

        with pytest.raises(HTTPException406):
            await get_doc_from_id_async("doc-1", [("123", 1, 10)], False)

    @pytest.mark.asyncio
    @patch("sei_ia.data.etl.extract.doc_content.get_type_doc_from_id")
    async def test_async_real_pdf_ocr_range_invokes_adapter_only_for_selected_pages(
        self, mock_get_type_doc_from_id, tmp_path
    ):
        """PDF escaneado com range 10:11 passa imagens reais e exclusivas das páginas 10 e 11 ao OCR."""
        import fitz
        from sei_extraction.config import ExtractionConfig
        from sei_extraction.ocr.vision import render_page_to_base64

        # Gerar PDF real com 12 páginas escaneadas (desenhos vetoriais distintos para base64 único)
        pdf_path = tmp_path / "doc_scanned_12_paginas.pdf"
        doc = fitz.open()
        for idx in range(1, 13):
            page = doc.new_page(width=200, height=200)
            page.draw_rect(
                fitz.Rect(10 + idx * 5, 20, 30 + idx * 10, 150),
                color=(0, 0, 0),
                fill=(0.08 * (idx % 10), 0.08 * (idx % 10), 0.08 * (idx % 10)),
            )
        doc.save(str(pdf_path))
        doc.close()
        pdf_bytes = pdf_path.read_bytes()

        class _RealFakeDownloader:
            last_binary_sha256 = None
            last_binary_bytes = None

            def download(
                self, id_documento: str, doc_extension: str, id_anexo=None
            ) -> str:
                temp_file = tmp_path / f"download_ocr_{id_documento}.{doc_extension}"
                temp_file.write_bytes(pdf_bytes)
                return str(temp_file)

        class _AuthenticImageOCRClient:
            def __init__(self):
                self.received_images: list[str] = []

            def extract_page(self, img_base64: str, model: str) -> str:
                self.received_images.append(img_base64)
                return "TEXTO_OCR_AUTENTICO"

            def pipeline_identity_sha256(self, config, doc_extension):
                return "fake-pipeline-sha"

        controlled_ocr = _AuthenticImageOCRClient()
        ocr_config = ExtractionConfig(ocr_enabled=True, ocr_min_text_threshold=50)

        # Renderizar independentemente as imagens esperadas das páginas 10 e 11
        expected_b64_10 = render_page_to_base64(str(pdf_path), 10, ocr_config)
        expected_b64_11 = render_page_to_base64(str(pdf_path), 11, ocr_config)
        assert expected_b64_10 != expected_b64_11, (
            "Páginas 10 e 11 devem ter imagens distintas"
        )

        mock_get_type_doc_from_id.return_value = (
            False,
            "pdf",
            "16216381",
            "proc-1",
        )

        source_mock = MagicMock(extra_metadata={})
        with (
            patch(
                "sei_ia.data.etl.extract.doc_content.make_adapters",
                return_value=(source_mock, _RealFakeDownloader(), None),
            ),
            patch("sei_ia.data.etl.extract.doc_content.ocr_client", controlled_ocr),
            patch("sei_ia.data.etl.extract.doc_content.extraction_config", ocr_config),
        ):
            content, formatted_id, _ = await get_doc_from_id_async(
                "doc-ocr", [("16216381", 10, 11)], True
            )

        assert formatted_id == "16216381"
        assert len(controlled_ocr.received_images) == 2, (
            f"OCR deveria ser chamado apenas para 2 páginas (10 e 11), mas recebeu {len(controlled_ocr.received_images)}"
        )
        assert set(controlled_ocr.received_images) == {
            expected_b64_10,
            expected_b64_11,
        }
        assert "TEXTO_OCR_AUTENTICO" in content

    @pytest.mark.asyncio
    async def test_session_materialization_real_pdf_range_10_11_excludes_outside_markers(
        self, monkeypatch, tmp_path
    ):
        """Endpoint session_stream materializa em disco apenas as páginas pedidas de um PDF real."""
        from types import SimpleNamespace

        import fitz
        from fastapi import Request
        from langchain_core.messages import AIMessageChunk

        import sei_ia.routers.session.stream as stream_module
        from sei_ia.routers.session.stream import (
            ENDPOINT_NAME,
            SessionStreamRequest,
            session_stream,
        )
        from sei_ia.services.session_fs.manager import SessionManager

        class _NoopCheckpointer:
            async def adelete_thread(self, thread_id: str) -> None:
                pass

        # 1. Gerar PDF real com 12 páginas e marcadores explícitos
        doc = fitz.open()
        for idx in range(1, 13):
            page = doc.new_page(width=300, height=300)
            page.insert_text(
                (50, 100),
                f"PAGINA_{idx}_SESSAO_EXCLUSIVA_INICIO\n"
                f"Corpo de texto da pagina {idx}.\n"
                f"PAGINA_{idx}_SESSAO_EXCLUSIVA_FIM",
            )
        pdf_path = tmp_path / "real_12p.pdf"
        doc.save(str(pdf_path))
        doc.close()
        pdf_bytes = pdf_path.read_bytes()

        class _Downloader:
            last_binary_sha256 = None
            last_binary_bytes = None

            def download(
                self, id_documento: str, doc_extension: str, id_anexo=None
            ) -> str:
                temp_file = tmp_path / f"session_{id_documento}.{doc_extension}"
                temp_file.write_bytes(pdf_bytes)
                return str(temp_file)

        mock_metadata = {
            "id_documento_formatado": "16216381",
            "id_protocolo_formatado": "00001.000001/2026-00",
            "sin_armazena_cache": "S",
            "formato_arquivo": "pdf",
        }

        # 2. Configurar SessionManager real com root isolado
        real_manager = SessionManager(
            sessions_root=tmp_path / "sessions",
            ttl_seconds=60,
            checkpointer=_NoopCheckpointer(),
        )

        class _FakeAgent:
            async def astream(self, agent_input, **_kwargs):
                yield ("messages", (AIMessageChunk(content="ok"), {}))

        cache_mock = AsyncMock()
        cache_mock.get_document.return_value = None
        source_mock = MagicMock(extra_metadata={})

        monkeypatch.setattr(
            stream_module, "get_session_manager", AsyncMock(return_value=real_manager)
        )
        monkeypatch.setattr(
            stream_module,
            "get_session_checkpointer",
            AsyncMock(return_value=_NoopCheckpointer()),
        )
        monkeypatch.setattr(
            stream_module,
            "build_session_agent",
            lambda *_args, **_kwargs: _FakeAgent(),
        )
        monkeypatch.setattr(
            stream_module,
            "decide_mode",
            lambda *_args: SimpleNamespace(
                mode="filesystem", total_content_tokens=0, threshold=100
            ),
        )
        monkeypatch.setattr(
            stream_module, "classify_complexity", AsyncMock(return_value="easy")
        )
        monkeypatch.setattr(
            stream_module,
            "get_model_config",
            lambda **_kwargs: {
                "model": "fake",
                "model_name": "fake",
                "max_ctx_len": 1000,
            },
        )
        monkeypatch.setattr(stream_module.settings, "SESSION_SEED_HISTORY", False)
        monkeypatch.setattr(stream_module.settings, "SESSION_TRACE", False)

        monkeypatch.setattr("sei_ia.services.cache.get_cache", lambda: cache_mock)
        monkeypatch.setattr(
            "sei_ia.data.etl.extract.metadata.get_doc_metadata_dict",
            AsyncMock(return_value=mock_metadata),
        )
        monkeypatch.setattr(
            "sei_ia.data.etl.extract.doc_content.make_adapters",
            lambda: (source_mock, _Downloader(), None),
        )
        monkeypatch.setattr(
            "sei_ia.data.etl.extract.metadata.get_type_doc_from_id",
            AsyncMock(return_value=(False, "pdf", "16216381", "00001.000001/2026-00")),
        )

        # 3. Request real do usuário com payload formatado contendo paginação 10:11
        request = SessionStreamRequest(
            id_usuario=100,
            id_topico=200,
            text="analise as paginas solicitadas",
            id_procedimentos=[
                {
                    "id_procedimento": "8116731",
                    "id_documentos": [
                        {
                            "id_documento": "16216381",
                            "download_ext": True,
                            "pag_doc_init": 10,
                            "pag_doc_end": 11,
                        }
                    ],
                }
            ],
        )
        starlette_request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": ENDPOINT_NAME,
                "headers": [],
            }
        )
        starlette_request.state.id_request = 100200
        starlette_request.state.body = request.model_dump_json(
            exclude_none=True
        ).encode("utf-8")

        # 4. Executar endpoint session_stream diretamente através do pipeline real
        response = await session_stream(request, starlette_request)
        async for _ in response.body_iterator:
            pass

        # 5. O arquivo gravado no filesystem da sessão deve conter apenas páginas 10 e 11
        materialized_file = (
            tmp_path / "sessions" / "100_200" / "proc_8116731" / "16216381.txt"
        )
        assert materialized_file.exists(), (
            "Arquivo materializado deve existir no workspace da sessão"
        )
        materialized_text = materialized_file.read_text(encoding="utf-8")

        assert "PAGINA_10_SESSAO_EXCLUSIVA_INICIO" in materialized_text
        assert "PAGINA_11_SESSAO_EXCLUSIVA_INICIO" in materialized_text
        for outside_page in (1, 2, 3, 4, 5, 6, 7, 8, 9, 12):
            assert (
                f"PAGINA_{outside_page}_SESSAO_EXCLUSIVA_INICIO"
                not in materialized_text
            ), (
                f"Marcador da página {outside_page} não deveria estar no texto materializado!"
            )

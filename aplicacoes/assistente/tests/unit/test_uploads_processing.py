"""Testes unitários para sei_ia.data.etl.extract.uploads.

Cobre `extract_text_from_file`, `download_and_extract_upload` e
`process_uploads` no contrato atual:

- `download_and_extract_upload` devolve `_UploadResult(filename, fs_path, kind,
  id_arquivo_avulso, extensao, text=..., image=..., size_bytes=..., mime=...)`
  ou levanta `UploadProcessingError`.
- `process_uploads` devolve `UploadOutcome(text_block, image_attachments,
  attachments, temp_files)` ou propaga `UploadProcessingError` do primeiro
  upload que falhar (carrega `cleanup_paths` nos arquivos já baixados).
- Cada arquivo no `text_block` é encapsulado por `<arquivo nome="…"
  tipo="text|audio|imagem" [mime="…" tamanho="…"]>…</arquivo>` dentro de
  `<arquivos_avulsos>…</arquivos_avulsos>`.

`extract_text_from_file` delega toda extração não-HTML para `extract_document`
da lib `sei_extraction`; os testes patcham esse ponto único.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from sei_ia.data.pydantic_models import UploadItem


class TestExtractTextFromFile:
    """Testes para a função extract_text_from_file (puro: caminho+ext → str)."""

    def test_extrai_arquivo_txt(self, tmp_path):
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "nota.txt"
        arquivo.write_text("Conteúdo da nota técnica.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value="Conteúdo da nota técnica.",
        ):
            resultado = extract_text_from_file(str(arquivo), "txt")

        assert "Conteúdo da nota técnica" in resultado

    def test_extrai_arquivo_csv(self, tmp_path):
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "planilha.csv"
        arquivo.write_text("nome,valor\nitem_a,100\nitem_b,200", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value="nome,valor\nitem_a,100",
        ):
            resultado = extract_text_from_file(str(arquivo), "csv")

        assert "nome" in resultado
        assert "item_a" in resultado

    def test_extrai_arquivo_json(self, tmp_path):
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "dados.json"
        arquivo.write_text(
            '{"protocolo": "12345", "status": "ativo"}', encoding="utf-8"
        )

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value='{"protocolo": "12345", "status": "ativo"}',
        ):
            resultado = extract_text_from_file(str(arquivo), "json")

        assert "protocolo" in resultado
        assert "12345" in resultado

    def test_extrai_arquivo_xml(self, tmp_path):
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "dados.xml"
        arquivo.write_text(
            '<?xml version="1.0"?><processo><numero>SEI-001</numero></processo>',
            encoding="utf-8",
        )

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value="<numero>SEI-001</numero>",
        ):
            resultado = extract_text_from_file(str(arquivo), "xml")

        assert "SEI-001" in resultado

    def test_extensao_nao_suportada_retorna_mensagem(self, tmp_path):
        """Deve retornar mensagem indicando formato não suportado."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "imagem.xyz"
        arquivo.write_bytes(b"\x89PNG\r\n fake binary content")

        resultado = extract_text_from_file(str(arquivo), "xyz")

        assert "[Formato .xyz não suportado" in resultado

    def test_extensao_em_maiusculas_e_normalizada(self, tmp_path):
        """Deve tratar extensão em maiúsculas como equivalente à minúscula."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "documento.txt"
        arquivo.write_text("Texto em maiúsculas.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value="Texto em maiúsculas.",
        ):
            resultado = extract_text_from_file(str(arquivo), "TXT")

        assert "Texto em maiúsculas" in resultado

    def test_extensao_com_ponto_inicial_e_removido(self, tmp_path):
        """Deve aceitar extensão com ponto inicial (ex: '.txt')."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "oficio.txt"
        arquivo.write_text("Texto do ofício.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value="Texto do ofício.",
        ):
            resultado = extract_text_from_file(str(arquivo), ".txt")

        assert "Texto do ofício" in resultado

    def test_pdf_delega_para_extract_document(self, tmp_path):
        """Deve delegar extração de PDF para extract_document da lib sei_extraction."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "relatorio.pdf"
        arquivo.write_bytes(b"%PDF-1.4 fake pdf")

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value="Texto extraído do PDF",
        ) as mock_extract:
            resultado = extract_text_from_file(str(arquivo), "pdf")

        mock_extract.assert_called_once()
        assert resultado == "Texto extraído do PDF"

    def test_xlsx_delega_para_extract_document(self, tmp_path):
        """Deve delegar extração de XLSX para extract_document da lib sei_extraction."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "orcamento.xlsx"
        arquivo.write_bytes(b"PK fake xlsx content")

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value="col1,col2\nv1,v2",
        ):
            resultado = extract_text_from_file(str(arquivo), "xlsx")

        assert "col1" in resultado

    @pytest.mark.parametrize("extensao", ["ods", "xls", "xlsb", "xlsm", "xlsx"])
    def test_todas_extensoes_planilha_delegam_para_extract_document(
        self, tmp_path, extensao
    ):
        """Deve usar extract_document para todas as extensões de planilha suportadas."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / f"planilha.{extensao}"
        arquivo.write_bytes(b"PK fake spreadsheet")

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value=f"conteúdo da planilha {extensao}",
        ) as mock_extract:
            resultado = extract_text_from_file(str(arquivo), extensao)

        mock_extract.assert_called_once()
        assert extensao in resultado

    @pytest.mark.parametrize("extensao", ["docx", "pptx", "md", "asciidoc"])
    def test_extensoes_docling_delegam_para_extract_document(self, tmp_path, extensao):
        """Deve usar extract_document para extensões suportadas por Docling."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / f"documento.{extensao}"
        arquivo.write_bytes(b"fake docling content")

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value=f"texto extraído por docling de {extensao}",
        ) as mock_extract:
            resultado = extract_text_from_file(str(arquivo), extensao)

        mock_extract.assert_called_once()
        assert extensao in resultado

    @pytest.mark.parametrize("extensao", ["html", "htm"])
    def test_html_upload_passa_pelo_html_to_markdown(self, tmp_path, extensao):
        """Uploads HTML pela janela de chat devem usar o parser canônico HtmlTxtmd."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / f"doc.{extensao}"
        arquivo.write_text("<h1>Olá</h1>", encoding="utf-8")

        # Apenas html é mapeado para html_to_markdown em EXT_HTML; htm cai no
        # dispatcher genérico (extract_document). O teste verifica cada rota.
        with (
            patch(
                "sei_ia.data.etl.extract.uploads.html_to_markdown",
                return_value=f"# Olá ({extensao})",
            ) as mock_html_md,
            patch(
                "sei_ia.data.etl.extract.uploads.extract_document",
                return_value=f"# Olá ({extensao})",
            ),
        ):
            resultado = extract_text_from_file(str(arquivo), extensao)

        assert resultado == f"# Olá ({extensao})"
        if extensao == "html":
            mock_html_md.assert_called_once_with("<h1>Olá</h1>")

    @pytest.mark.parametrize("extensao", ["rtf", "odt", "doc", "ppt"])
    def test_extensoes_unstructured_delegam_para_extract_document(
        self, tmp_path, extensao
    ):
        """Deve usar extract_document para extensões legadas."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / f"legado.{extensao}"
        arquivo.write_bytes(b"fake legacy content")

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value=f"texto do arquivo {extensao}",
        ) as mock_extract:
            resultado = extract_text_from_file(str(arquivo), extensao)

        mock_extract.assert_called_once()
        assert extensao in resultado

    def test_odp_delega_para_extract_document(self, tmp_path):
        """Deve usar extract_document para arquivos ODP."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "apresentacao.odp"
        arquivo.write_bytes(b"PK fake odp content")

        with patch(
            "sei_ia.data.etl.extract.uploads.extract_document",
            return_value="Slides da apresentação",
        ) as mock_extract:
            resultado = extract_text_from_file(str(arquivo), "odp")

        mock_extract.assert_called_once()
        assert resultado == "Slides da apresentação"


class TestDownloadAndExtractUpload:
    """Testes para download_and_extract_upload (retorna _UploadResult ou levanta
    UploadProcessingError)."""

    def test_sucesso_retorna_upload_result_text(self, tmp_path):
        """Sucesso de texto deve devolver _UploadResult com kind='text' e text populado."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(
            id_upload=42,
            nome_original="relatorio_anual.txt",
            extensao="txt",
        )

        fake_file = tmp_path / "relatorio_anual_up42_abc12345.txt"
        fake_file.write_text("Relatório anual da unidade.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            return_value=str(fake_file),
        ):
            result = asyncio.run(download_and_extract_upload(upload))

        assert result.filename == "relatorio_anual.txt"
        assert result.kind == "text"
        assert result.text is not None
        assert "Relatório anual da unidade" in result.text
        assert result.image is None
        assert result.fs_path == str(fake_file)

    def test_download_falha_levanta_upload_processing_error(self):
        """Download falho deve levantar UploadProcessingError com filename/extensao."""
        from sei_ia.data.etl.extract.uploads import (
            UploadProcessingError,
            download_and_extract_upload,
        )

        upload = UploadItem(
            id_upload=99,
            nome_original="arquivo_falho.pdf",
            extensao="pdf",
        )

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                side_effect=ConnectionError("Servidor da API indisponível"),
            ),
            pytest.raises(UploadProcessingError) as exc_info,
        ):
            asyncio.run(download_and_extract_upload(upload))

        assert exc_info.value.filename == "arquivo_falho.pdf"
        assert exc_info.value.extensao == "pdf"
        assert "Servidor da API indisponível" in exc_info.value.message

    def test_extracao_falha_levanta_upload_processing_error(self, tmp_path):
        """Falha de extração deve levantar UploadProcessingError."""
        from sei_ia.data.etl.extract.uploads import (
            UploadProcessingError,
            download_and_extract_upload,
        )

        upload = UploadItem(
            id_upload=10,
            nome_original="corrompido.pdf",
            extensao="pdf",
        )

        fake_file = tmp_path / "corrompido_up10.pdf"
        fake_file.write_bytes(b"arquivo corrompido")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.extract_text_from_file",
                side_effect=RuntimeError("Falha ao processar PDF"),
            ),
            pytest.raises(UploadProcessingError) as exc_info,
        ):
            asyncio.run(download_and_extract_upload(upload))

        assert exc_info.value.filename == "corrompido.pdf"
        assert "Falha ao processar PDF" in exc_info.value.message

    def test_nome_original_preservado_no_resultado(self, tmp_path):
        """Deve preservar o nome_original do upload em _UploadResult.filename."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        nome_original = "Relatório Técnico de Auditoria 2024.txt"
        upload = UploadItem(
            id_upload=7,
            nome_original=nome_original,
            extensao="txt",
        )

        fake_file = tmp_path / "relatorio_up7.txt"
        fake_file.write_text("Conteúdo do relatório.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            return_value=str(fake_file),
        ):
            result = asyncio.run(download_and_extract_upload(upload))

        assert result.filename == nome_original

    def test_id_upload_e_extensao_passados_ao_handler(self, tmp_path):
        """Deve passar id_upload e extensao corretos para o sei_client."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(
            id_upload=55,
            nome_original="despacho.docx",
            extensao="docx",
        )

        fake_file = tmp_path / "despacho_up55.docx"
        fake_file.write_bytes(b"PK fake docx")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ) as mock_download,
            patch(
                "sei_ia.data.etl.extract.uploads.extract_document",
                return_value="Conteúdo do despacho",
            ),
        ):
            asyncio.run(download_and_extract_upload(upload))

        mock_download.assert_called_once_with(55, "docx")


class TestProcessUploads:
    """Testes para process_uploads (retorna UploadOutcome ou propaga
    UploadProcessingError)."""

    def test_lista_vazia_retorna_outcome_vazio(self):
        """Deve retornar UploadOutcome vazio para lista vazia."""
        from sei_ia.data.etl.extract.uploads import UploadOutcome, process_uploads

        outcome = asyncio.run(process_uploads([]))

        assert isinstance(outcome, UploadOutcome)
        assert outcome.text_block == ""
        assert outcome.image_attachments == []
        assert outcome.attachments == []
        assert outcome.temp_files == set()

    def test_none_retorna_outcome_vazio(self):
        """Deve retornar UploadOutcome vazio para None."""
        from sei_ia.data.etl.extract.uploads import UploadOutcome, process_uploads

        outcome = asyncio.run(process_uploads(None))

        assert isinstance(outcome, UploadOutcome)
        assert outcome.text_block == ""

    def test_upload_unico_envolto_em_tags_arquivos_avulsos(self, tmp_path):
        """O text_block deve começar com <arquivos_avulsos> e terminar com </arquivos_avulsos>."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(id_upload=1, nome_original="memo.txt", extensao="txt")

        fake = tmp_path / "memo_up1.txt"
        fake.write_text("Memorando interno.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            return_value=str(fake),
        ):
            outcome = asyncio.run(process_uploads([upload]))

        assert outcome.text_block.startswith("<arquivos_avulsos>")
        assert outcome.text_block.endswith("</arquivos_avulsos>")

    def test_upload_unico_contem_arquivo_xml_e_conteudo(self, tmp_path):
        """O bloco deve usar `<arquivo nome="..." tipo="text">…</arquivo>` com o conteúdo."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(id_upload=3, nome_original="oficio.txt", extensao="txt")

        fake = tmp_path / "oficio_up3.txt"
        fake.write_text("Ofício de solicitação de dados.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            return_value=str(fake),
        ):
            outcome = asyncio.run(process_uploads([upload]))

        block = outcome.text_block
        assert (
            '<arquivo id_arquivo_avulso="3" nome="oficio.txt" '
            'extensao="txt" tipo="text" estado="available" motivo="">'
        ) in block
        assert "</arquivo>" in block
        assert "Ofício de solicitação de dados" in block

    def test_multiplos_uploads_todos_incluidos(self, tmp_path):
        """Deve incluir todos os uploads no text_block."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        uploads = [
            UploadItem(id_upload=1, nome_original="doc1.txt", extensao="txt"),
            UploadItem(id_upload=2, nome_original="doc2.txt", extensao="txt"),
            UploadItem(id_upload=3, nome_original="doc3.txt", extensao="txt"),
        ]

        fakes = {}
        for u in uploads:
            f = tmp_path / f"doc{u.id_upload}_up{u.id_upload}.txt"
            f.write_text(f"Conteúdo do documento {u.id_upload}.", encoding="utf-8")
            fakes[u.id_upload] = str(f)

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            side_effect=lambda id_upload, _ext: fakes[id_upload],
        ):
            outcome = asyncio.run(process_uploads(uploads))

        block = outcome.text_block
        for u in uploads:
            assert f'nome="{u.nome_original}" extensao="txt" tipo="text"' in block
        assert "Conteúdo do documento 1" in block
        assert "Conteúdo do documento 2" in block
        assert "Conteúdo do documento 3" in block

    def test_upload_com_falha_propaga_upload_processing_error(self, tmp_path):
        """Falha em qualquer upload propaga UploadProcessingError (com cleanup_paths
        populado dos uploads que já baixaram) em vez de placeholder silencioso."""
        from sei_ia.data.etl.extract.uploads import (
            UploadProcessingError,
            process_uploads,
        )

        uploads = [
            UploadItem(id_upload=1, nome_original="valido.txt", extensao="txt"),
            UploadItem(id_upload=2, nome_original="invalido.pdf", extensao="pdf"),
        ]

        fake_valido = tmp_path / "valido_up1.txt"
        fake_valido.write_text("Conteúdo válido.", encoding="utf-8")

        def mock_download(id_upload, _extensao):
            if id_upload == 1:
                return str(fake_valido)
            raise OSError("Arquivo não encontrado no servidor")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                side_effect=mock_download,
            ),
            pytest.raises(UploadProcessingError) as exc_info,
        ):
            asyncio.run(process_uploads(uploads))

        assert exc_info.value.filename == "invalido.pdf"
        assert hasattr(exc_info.value, "cleanup_paths")
        assert str(fake_valido) in exc_info.value.cleanup_paths

    def test_lote_tolerante_preserva_upload_indisponivel_e_nao_o_remove(self, tmp_path):
        from sei_ia.data.etl.extract.uploads import process_uploads_tolerant

        uploads = [
            UploadItem(id_upload=1, nome_original="valido.txt", extensao="txt"),
            UploadItem(id_upload=2, nome_original="falho.pdf", extensao="pdf"),
        ]
        valido = tmp_path / "valido.txt"
        valido.write_text("Conteúdo válido.", encoding="utf-8")

        def mock_download(id_upload, _extensao):
            if id_upload == 1:
                return str(valido)
            raise OSError("indisponível")

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            side_effect=mock_download,
        ):
            outcome = asyncio.run(process_uploads_tolerant(uploads))

        assert [attachment.content_state for attachment in outcome.attachments] == [
            "available",
            "unavailable",
        ]
        assert outcome.attachments[1].content_reason == "download_failed"
        assert outcome.removal_ids == {1}
        assert 'nome="falho.pdf"' in outcome.text_block
        assert 'estado="unavailable" motivo="download_failed"' in outcome.text_block
        assert "Não infira fatos." in outcome.text_block

    def test_formato_exato_do_template(self, tmp_path):
        """O text_block deve corresponder exatamente ao template definido no módulo."""
        from sei_ia.data.etl.extract.uploads import (
            UPLOAD_TEXT_BLOCK_TEMPLATE,
            UPLOADS_WRAPPER_TEMPLATE,
            process_uploads,
        )

        upload = UploadItem(id_upload=7, nome_original="modelo.txt", extensao="txt")

        fake = tmp_path / "modelo_up7.txt"
        fake.write_text("Texto do modelo.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            return_value=str(fake),
        ):
            outcome = asyncio.run(process_uploads([upload]))

        bloco_esperado = UPLOAD_TEXT_BLOCK_TEMPLATE.format(
            id_arquivo_avulso=7,
            nome_original="modelo.txt",
            extensao="txt",
            tipo="text",
            estado="available",
            motivo="",
            conteudo="Texto do modelo.",
        )
        esperado = UPLOADS_WRAPPER_TEMPLATE.format(blocos=bloco_esperado)
        assert outcome.text_block == esperado

    def test_apenas_um_par_de_tags_arquivos_avulsos(self, tmp_path):
        """Deve haver apenas um par de tags <arquivos_avulsos> no text_block."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        uploads = [
            UploadItem(id_upload=1, nome_original="a.txt", extensao="txt"),
            UploadItem(id_upload=2, nome_original="b.txt", extensao="txt"),
        ]

        fakes = {}
        for u in uploads:
            f = tmp_path / u.nome_original
            f.write_text(f"Conteúdo {u.nome_original}.", encoding="utf-8")
            fakes[u.id_upload] = str(f)

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            side_effect=lambda id_upload, _ext: fakes[id_upload],
        ):
            outcome = asyncio.run(process_uploads(uploads))

        assert outcome.text_block.count("<arquivos_avulsos>") == 1
        assert outcome.text_block.count("</arquivos_avulsos>") == 1

    def test_todos_uploads_falham_propaga_o_primeiro_erro(self):
        """Quando todos falham, propaga UploadProcessingError do primeiro
        (asyncio.gather mantém a ordem). cleanup_paths fica vazio porque
        nenhum chegou ao FS."""
        from sei_ia.data.etl.extract.uploads import (
            UploadProcessingError,
            process_uploads,
        )

        uploads = [
            UploadItem(id_upload=1, nome_original="a.pdf", extensao="pdf"),
            UploadItem(id_upload=2, nome_original="b.pdf", extensao="pdf"),
        ]

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                side_effect=ConnectionError("Servidor indisponível"),
            ),
            pytest.raises(UploadProcessingError) as exc_info,
        ):
            asyncio.run(process_uploads(uploads))

        assert exc_info.value.filename in {"a.pdf", "b.pdf"}
        assert exc_info.value.extensao == "pdf"
        assert exc_info.value.cleanup_paths == set()

    def test_ordem_dos_blocos_corresponde_a_ordem_dos_uploads(self, tmp_path):
        """A ordem dos blocos no text_block deve corresponder à ordem da lista."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        uploads = [
            UploadItem(id_upload=10, nome_original="primeiro.txt", extensao="txt"),
            UploadItem(id_upload=20, nome_original="segundo.txt", extensao="txt"),
            UploadItem(id_upload=30, nome_original="terceiro.txt", extensao="txt"),
        ]

        fakes = {}
        for u in uploads:
            f = tmp_path / u.nome_original
            f.write_text(f"Conteudo de {u.nome_original}", encoding="utf-8")
            fakes[u.id_upload] = str(f)

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            side_effect=lambda id_upload, _ext: fakes[id_upload],
        ):
            outcome = asyncio.run(process_uploads(uploads))

        block = outcome.text_block
        pos_primeiro = block.index('nome="primeiro.txt"')
        pos_segundo = block.index('nome="segundo.txt"')
        pos_terceiro = block.index('nome="terceiro.txt"')
        assert pos_primeiro < pos_segundo < pos_terceiro

    def test_temp_files_contem_paths_baixados(self, tmp_path):
        """temp_files deve carregar os /tmp baixados para limpeza no finally do caller."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(id_upload=1, nome_original="x.txt", extensao="txt")
        fake = tmp_path / "x_up1.txt"
        fake.write_text("conteúdo", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            return_value=str(fake),
        ):
            outcome = asyncio.run(process_uploads([upload]))

        assert str(fake) in outcome.temp_files

    def test_attachments_carrega_conteudo_estruturado(self, tmp_path):
        """attachments deve carregar ProcessedAttachment com conteúdo textual completo."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(id_upload=9, nome_original="nota.txt", extensao="txt")
        fake = tmp_path / "nota_up9.txt"
        fake.write_text("Texto persistível.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            return_value=str(fake),
        ):
            outcome = asyncio.run(process_uploads([upload]))

        assert len(outcome.attachments) == 1
        att = outcome.attachments[0]
        assert att.nome_arquivo == "nota.txt"
        assert att.extensao == "txt"
        assert att.tipo == "text"
        assert "Texto persistível" in att.conteudo


class TestDownloadAndExtractUploadExtras:
    """Testes adicionais para cenários de borda em download_and_extract_upload."""

    def test_timeout_no_download_levanta_upload_processing_error(self):
        """TimeoutError durante download deve levantar UploadProcessingError."""
        from sei_ia.data.etl.extract.uploads import (
            UploadProcessingError,
            download_and_extract_upload,
        )

        upload = UploadItem(id_upload=77, nome_original="demora.pdf", extensao="pdf")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                side_effect=TimeoutError("Timeout ao conectar com o servidor"),
            ),
            pytest.raises(UploadProcessingError) as exc_info,
        ):
            asyncio.run(download_and_extract_upload(upload))

        assert exc_info.value.filename == "demora.pdf"
        assert "Timeout ao conectar com o servidor" in exc_info.value.message

    def test_extracao_retorna_string_vazia_preservada(self, tmp_path):
        """Quando a extração retorna string vazia, _UploadResult.text deve ser '' sem virar erro."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(id_upload=20, nome_original="vazio.txt", extensao="txt")

        fake_file = tmp_path / "vazio_up20.txt"
        fake_file.write_bytes(b"")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.extract_text_from_file",
                return_value="",
            ),
        ):
            result = asyncio.run(download_and_extract_upload(upload))

        assert result.filename == "vazio.txt"
        assert result.kind == "text"
        assert result.text == ""


class TestUploadItemValidation:
    """Testes de validação do modelo Pydantic UploadItem."""

    def test_upload_item_valido_com_todos_campos(self):
        """UploadItem deve ser criado com sucesso quando todos os campos são válidos."""
        item = UploadItem(id_upload=1, nome_original="doc.pdf", extensao="pdf")

        assert item.id_upload == 1
        assert item.nome_original == "doc.pdf"
        assert item.extensao == "pdf"

    def test_id_upload_ausente_lanca_validation_error(self):
        """UploadItem sem id_upload deve lançar ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UploadItem(nome_original="doc.pdf", extensao="pdf")

    def test_nome_original_ausente_lanca_validation_error(self):
        """UploadItem sem nome_original deve lançar ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UploadItem(id_upload=1, extensao="pdf")

    def test_extensao_ausente_lanca_validation_error(self):
        """UploadItem sem extensao deve lançar ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UploadItem(id_upload=1, nome_original="doc.pdf")

    def test_id_upload_string_nao_numerica_lanca_validation_error(self):
        """UploadItem com id_upload como string não numérica deve lançar ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UploadItem(id_upload="abc", nome_original="doc.pdf", extensao="pdf")

    def test_id_upload_string_numerica_e_coercida_para_int(self):
        """UploadItem com id_upload como string numérica deve ser coercido para int."""
        item = UploadItem(id_upload="42", nome_original="doc.pdf", extensao="pdf")

        assert item.id_upload == 42
        assert isinstance(item.id_upload, int)


class TestDownloadAndExtractUploadAudio:
    """Testes para o comportamento de download_and_extract_upload com arquivos de áudio."""

    def test_arquivo_mp3_chama_transcribe_audio_file(self, tmp_path):
        """Upload de MP3 deve acionar transcribe_audio_file e devolver kind='audio'."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(id_upload=10, nome_original="reuniao.mp3", extensao="mp3")

        fake_file = tmp_path / "reuniao_up10.mp3"
        fake_file.write_bytes(b"fake mp3 content")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Transcrição da reunião.",
            ) as mock_transcribe,
        ):
            result = asyncio.run(download_and_extract_upload(upload))

        mock_transcribe.assert_called_once()
        assert result.filename == "reuniao.mp3"
        assert result.kind == "audio"
        assert result.text == "Transcrição da reunião."

    def test_arquivo_wav_chama_transcribe_audio_file(self, tmp_path):
        """Upload de WAV deve acionar transcribe_audio_file."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(id_upload=20, nome_original="gravacao.wav", extensao="wav")

        fake_file = tmp_path / "gravacao_up20.wav"
        fake_file.write_bytes(b"RIFF fake wav")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Texto da gravação.",
            ) as mock_transcribe,
        ):
            result = asyncio.run(download_and_extract_upload(upload))

        mock_transcribe.assert_called_once()
        assert result.text == "Texto da gravação."
        assert result.kind == "audio"

    def test_arquivo_audio_nao_chama_extract_text_from_file(self, tmp_path):
        """Para áudio, extract_text_from_file não deve ser chamado."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(id_upload=30, nome_original="audio.ogg", extensao="ogg")

        fake_file = tmp_path / "audio_up30.ogg"
        fake_file.write_bytes(b"fake ogg")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Texto do ogg.",
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.extract_text_from_file",
            ) as mock_extract,
        ):
            asyncio.run(download_and_extract_upload(upload))

        mock_extract.assert_not_called()

    def test_transcribe_audio_file_recebe_caminho_e_extensao(self, tmp_path):
        """transcribe_audio_file deve ser chamado com o caminho e extensão corretos."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(id_upload=40, nome_original="audio.flac", extensao="flac")

        fake_file = tmp_path / "audio_up40.flac"
        fake_file.write_bytes(b"fake flac")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Transcrição FLAC.",
            ) as mock_transcribe,
        ):
            asyncio.run(download_and_extract_upload(upload))

        mock_transcribe.assert_called_once_with(str(fake_file), "flac")

    def test_falha_na_transcricao_levanta_upload_processing_error(self, tmp_path):
        """Falha em transcribe_audio_file deve levantar UploadProcessingError."""
        from sei_ia.data.etl.extract.uploads import (
            UploadProcessingError,
            download_and_extract_upload,
        )

        upload = UploadItem(
            id_upload=50, nome_original="audio_corrompido.mp3", extensao="mp3"
        )

        fake_file = tmp_path / "audio_up50.mp3"
        fake_file.write_bytes(b"corrupted")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                side_effect=Exception("Serviço de transcrição indisponível"),
            ),
            pytest.raises(UploadProcessingError) as exc_info,
        ):
            asyncio.run(download_and_extract_upload(upload))

        assert exc_info.value.filename == "audio_corrompido.mp3"

    @pytest.mark.parametrize(
        "extensao",
        ["mp3", "mp4", "wav", "ogg", "m4a", "webm", "flac", "aac", "opus", "wma"],
    )
    def test_todas_extensoes_de_audio_acionam_transcricao(self, tmp_path, extensao):
        """Todas as extensões de áudio definidas em AUDIO_EXTENSIONS devem acionar transcrição."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(
            id_upload=1,
            nome_original=f"audio.{extensao}",
            extensao=extensao,
        )

        fake_file = tmp_path / f"audio_up1.{extensao}"
        fake_file.write_bytes(b"fake audio")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=f"Texto do {extensao}.",
            ) as mock_transcribe,
        ):
            result = asyncio.run(download_and_extract_upload(upload))

        mock_transcribe.assert_called_once()
        assert result.kind == "audio"
        assert result.text == f"Texto do {extensao}."


class TestProcessUploadsComAudio:
    """Testes para process_uploads com arquivos de áudio."""

    def test_upload_audio_transcreve_e_inclui_no_text_block(self, tmp_path):
        """Upload de áudio deve aparecer com tipo='audio' e a transcrição no bloco."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(
            id_upload=100, nome_original="reuniao_plenaria.mp3", extensao="mp3"
        )

        fake_file = tmp_path / "reuniao_up100.mp3"
        fake_file.write_bytes(b"fake mp3")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Presidente abre a sessão às 10h.",
            ),
        ):
            outcome = asyncio.run(process_uploads([upload]))

        block = outcome.text_block
        assert "<arquivos_avulsos>" in block
        assert 'nome="reuniao_plenaria.mp3" extensao="mp3" tipo="audio"' in block
        assert "Presidente abre a sessão às 10h." in block

    def test_mistura_audio_e_texto_processados_juntos(self, tmp_path):
        """Uploads de áudio e texto devem ser processados e incluídos juntos."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        uploads = [
            UploadItem(id_upload=1, nome_original="nota.txt", extensao="txt"),
            UploadItem(id_upload=2, nome_original="audio.mp3", extensao="mp3"),
        ]

        fake_txt = tmp_path / "nota_up1.txt"
        fake_txt.write_text("Nota técnica aprovada.", encoding="utf-8")

        fake_mp3 = tmp_path / "audio_up2.mp3"
        fake_mp3.write_bytes(b"fake mp3")

        def mock_download(id_upload, _extensao):
            return str(fake_txt) if id_upload == 1 else str(fake_mp3)

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                side_effect=mock_download,
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Texto da gravação de áudio.",
            ),
        ):
            outcome = asyncio.run(process_uploads(uploads))

        block = outcome.text_block
        assert 'nome="nota.txt" extensao="txt" tipo="text"' in block
        assert "Nota técnica aprovada" in block
        assert 'nome="audio.mp3" extensao="mp3" tipo="audio"' in block
        assert "Texto da gravação de áudio." in block

    def test_falha_na_transcricao_propaga_upload_processing_error(self, tmp_path):
        """Falha na transcrição também propaga UploadProcessingError, sem deixar
        resposta passar com placeholder."""
        from sei_ia.data.etl.extract.uploads import (
            UploadProcessingError,
            process_uploads,
        )

        uploads = [
            UploadItem(id_upload=1, nome_original="audio_ok.mp3", extensao="mp3"),
            UploadItem(id_upload=2, nome_original="audio_falho.wav", extensao="wav"),
        ]

        fake_mp3 = tmp_path / "audio_up1.mp3"
        fake_mp3.write_bytes(b"fake mp3")

        fake_wav = tmp_path / "audio_up2.wav"
        fake_wav.write_bytes(b"fake wav")

        def mock_download(id_upload, _extensao):
            return str(fake_mp3) if id_upload == 1 else str(fake_wav)

        async def mock_transcribe(file_path, _extensao):
            if "up2" in file_path:
                raise RuntimeError("Falha ao transcrever")
            return "Transcrição do áudio ok."

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                side_effect=mock_download,
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                side_effect=mock_transcribe,
            ),
            pytest.raises(UploadProcessingError) as exc_info,
        ):
            asyncio.run(process_uploads(uploads))

        assert exc_info.value.filename == "audio_falho.wav"
        assert str(fake_mp3) in exc_info.value.cleanup_paths

    def test_text_block_audio_envolto_em_tags_arquivos_avulsos(self, tmp_path):
        """O text_block com áudio deve estar dentro das tags <arquivos_avulsos>."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(id_upload=5, nome_original="audio.webm", extensao="webm")

        fake_file = tmp_path / "audio_up5.webm"
        fake_file.write_bytes(b"fake webm")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Transcrição do webm.",
            ),
        ):
            outcome = asyncio.run(process_uploads([upload]))

        assert outcome.text_block.startswith("<arquivos_avulsos>")
        assert outcome.text_block.endswith("</arquivos_avulsos>")


class TestProcessUploadsComImagem:
    """Testes para process_uploads com arquivos de imagem (multimodal)."""

    def test_upload_imagem_produz_image_attachment(self, tmp_path):
        """Imagem deve produzir ImageAttachment em image_attachments com metadado."""
        from sei_ia.data.etl.extract.uploads import (
            ImageAttachment,
            process_uploads,
        )

        upload = UploadItem(id_upload=1, nome_original="captura.png", extensao="png")

        fake = tmp_path / "captura_up1.png"
        fake.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                "0000000d49444154789c63000100000005000100002b3a96a40000000049454e44ae426082"
            )
        )

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            return_value=str(fake),
        ):
            outcome = asyncio.run(process_uploads([upload]))

        assert len(outcome.image_attachments) == 1
        att = outcome.image_attachments[0]
        assert isinstance(att, ImageAttachment)
        assert att.filename == "captura.png"
        assert att.mime == "image/png"
        assert att.fs_path == str(fake)
        assert att.size_bytes > 0

    def test_upload_imagem_breadcrumb_no_text_block(self, tmp_path):
        """Imagem deve aparecer no <arquivos_avulsos> como bloco tipo='imagem' com
        mime e tamanho, sem bytes."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(id_upload=1, nome_original="foto.jpeg", extensao="jpeg")

        fake = tmp_path / "foto_up1.jpeg"
        fake.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 200)

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            return_value=str(fake),
        ):
            outcome = asyncio.run(process_uploads([upload]))

        block = outcome.text_block
        assert (
            '<arquivo id_arquivo_avulso="1" nome="foto.jpeg" '
            'extensao="jpeg" tipo="imagem" estado="available" motivo="" '
            'mime="image/jpeg" tamanho="'
        ) in block
        assert "</arquivo>" in block
        assert "Imagem anexada como mídia multimodal" in block

    def test_mistura_texto_e_imagem_preserva_ordem(self, tmp_path):
        """Texto e imagem convivem no mesmo <arquivos_avulsos>, na ordem do payload."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        uploads = [
            UploadItem(id_upload=1, nome_original="relatorio.txt", extensao="txt"),
            UploadItem(id_upload=2, nome_original="anexo.png", extensao="png"),
        ]

        fake_txt = tmp_path / "rel_up1.txt"
        fake_txt.write_text("Relatório.", encoding="utf-8")
        fake_png = tmp_path / "anexo_up2.png"
        fake_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        def mock_download(id_upload, _extensao):
            return str(fake_txt) if id_upload == 1 else str(fake_png)

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            side_effect=mock_download,
        ):
            outcome = asyncio.run(process_uploads(uploads))

        block = outcome.text_block
        pos_txt = block.index('nome="relatorio.txt"')
        pos_png = block.index('nome="anexo.png"')
        assert pos_txt < pos_png
        assert len(outcome.image_attachments) == 1
        assert outcome.image_attachments[0].filename == "anexo.png"

    def test_nome_de_arquivo_em_atributo_xml_e_escapado(self, tmp_path):
        """Nome com aspas/ampersand deve ser escapado no atributo XML do bloco."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(
            id_upload=3,
            nome_original='relatorio "especial" & final.txt',
            extensao="txt",
        )
        fake = tmp_path / "relatorio_up3.txt"
        fake.write_text("Conteúdo escapado.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.sei_client.md_ia_download_arquivo_avulso",
            return_value=str(fake),
        ):
            outcome = asyncio.run(process_uploads([upload]))

        assert (
            'nome="relatorio &quot;especial&quot; &amp; final.txt"'
            in outcome.text_block
        )


class TestFormatSize:
    """Testes para o helper _format_size."""

    def test_format_size_em_bytes_kb_e_mb(self):
        from sei_ia.data.etl.extract.uploads import _format_size

        assert _format_size(42) == "42 B"
        assert _format_size(2048) == "2.0 KB"
        assert _format_size(3 * 1024 * 1024) == "3.0 MB"


class TestCleanupTempFiles:
    """Testes para cleanup_upload_temp_files."""

    def test_remove_existente_ignora_ausente_e_loga_oserror(self, tmp_path):
        from sei_ia.data.etl.extract.uploads import cleanup_upload_temp_files

        existente = tmp_path / "arquivo.tmp"
        existente.write_text("temp", encoding="utf-8")
        ausente = tmp_path / "ausente.tmp"
        com_erro = tmp_path / "erro.tmp"
        original_remove = __import__("os").remove

        def fake_remove(path):
            if path == str(com_erro):
                raise OSError("sem permissão")
            return original_remove(path)

        with (
            patch("sei_ia.data.etl.extract.uploads.os.remove", side_effect=fake_remove),
            patch("sei_ia.data.etl.extract.uploads.logger.warning") as mock_warning,
        ):
            cleanup_upload_temp_files([str(existente), str(ausente), str(com_erro)])

        assert not existente.exists()
        mock_warning.assert_called_once()

    def test_sem_paths_retorna_sem_remover(self):
        from sei_ia.data.etl.extract.uploads import cleanup_upload_temp_files

        with patch("sei_ia.data.etl.extract.uploads.os.remove") as mock_remove:
            cleanup_upload_temp_files(None)

        mock_remove.assert_not_called()

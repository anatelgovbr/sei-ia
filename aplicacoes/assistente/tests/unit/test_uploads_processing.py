"""Testes unitários para o módulo de processamento de uploads.

Testa as funções de download, extração e formatação de arquivos enviados
pelo usuário (uploads) no Assistente IA, incluindo a transcrição de áudio.

Módulo testado: sei_ia/data/etl/extract/uploads.py
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from sei_ia.data.pydantic_models import UploadItem


class TestExtractTextFromFile:
    """Testes para a função extract_text_from_file."""

    def test_extrai_arquivo_txt(self, tmp_path):
        """Deve extrair texto de arquivo TXT via _get_text_from_plain_text_file."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "nota.txt"
        arquivo.write_text("Conteúdo da nota técnica.", encoding="utf-8")

        resultado = extract_text_from_file(str(arquivo), "txt")

        assert "Conteúdo da nota técnica" in resultado

    def test_extrai_arquivo_csv(self, tmp_path):
        """Deve extrair texto de arquivo CSV via _get_text_from_plain_text_file."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "planilha.csv"
        arquivo.write_text("nome,valor\nitem_a,100\nitem_b,200", encoding="utf-8")

        resultado = extract_text_from_file(str(arquivo), "csv")

        assert "nome" in resultado
        assert "item_a" in resultado

    def test_extrai_arquivo_json(self, tmp_path):
        """Deve extrair texto de arquivo JSON via _get_text_from_plain_text_file."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "dados.json"
        arquivo.write_text(
            '{"protocolo": "12345", "status": "ativo"}', encoding="utf-8"
        )

        resultado = extract_text_from_file(str(arquivo), "json")

        assert "protocolo" in resultado
        assert "12345" in resultado

    def test_extrai_arquivo_xml(self, tmp_path):
        """Deve extrair texto de arquivo XML via _get_text_from_plain_text_file."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "dados.xml"
        arquivo.write_text(
            '<?xml version="1.0"?><processo><numero>SEI-001</numero></processo>',
            encoding="utf-8",
        )

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

        resultado = extract_text_from_file(str(arquivo), "TXT")

        assert "Texto em maiúsculas" in resultado

    def test_extensao_com_ponto_inicial_e_removido(self, tmp_path):
        """Deve aceitar extensão com ponto inicial (ex: '.txt')."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "oficio.txt"
        arquivo.write_text("Texto do ofício.", encoding="utf-8")

        resultado = extract_text_from_file(str(arquivo), ".txt")

        assert "Texto do ofício" in resultado

    def test_pdf_delega_para_extrator_pdf(self, tmp_path):
        """Deve chamar _get_text_pdf_from_file para arquivos PDF."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "relatorio.pdf"
        arquivo.write_bytes(b"%PDF-1.4 fake pdf")

        with patch(
            "sei_ia.data.etl.extract.uploads._get_text_pdf_from_file",
            return_value="Texto extraído do PDF",
        ) as mock_pdf:
            resultado = extract_text_from_file(str(arquivo), "pdf")

        mock_pdf.assert_called_once_with(str(arquivo), None, None)
        assert resultado == "Texto extraído do PDF"

    def test_xlsx_delega_para_extrator_planilha(self, tmp_path):
        """Deve chamar _get_spreadsheets_from_file para arquivos XLSX."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "orcamento.xlsx"
        arquivo.write_bytes(b"PK fake xlsx content")

        with patch(
            "sei_ia.data.etl.extract.external._get_spreadsheets_from_file",
            return_value="| col1 | col2 |\n| v1   | v2   |",
        ):
            resultado = extract_text_from_file(str(arquivo), "xlsx")

        assert "col1" in resultado

    @pytest.mark.parametrize("extensao", ["ods", "xls", "xlsb", "xlsm", "xlsx"])
    def test_todas_extensoes_planilha_delegam_para_extrator(self, tmp_path, extensao):
        """Deve usar extrator de planilha para todas as extensões suportadas."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / f"planilha.{extensao}"
        arquivo.write_bytes(b"PK fake spreadsheet")

        with patch(
            "sei_ia.data.etl.extract.external._get_spreadsheets_from_file",
            return_value=f"conteúdo da planilha {extensao}",
        ):
            resultado = extract_text_from_file(str(arquivo), extensao)

        assert extensao in resultado

    @pytest.mark.parametrize(
        "extensao", ["html", "htm", "docx", "pptx", "md", "asciidoc"]
    )
    def test_extensoes_docling_delegam_para_docling(self, tmp_path, extensao):
        """Deve usar Docling para extensões suportadas por ele."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / f"documento.{extensao}"
        arquivo.write_bytes(b"fake docling content")

        with patch(
            "sei_ia.data.etl.extract.uploads._get_text_from_file_with_docling",
            return_value=f"texto extraído por docling de {extensao}",
        ) as mock_docling:
            resultado = extract_text_from_file(str(arquivo), extensao)

        mock_docling.assert_called_once_with(str(arquivo))
        assert extensao in resultado

    @pytest.mark.parametrize("extensao", ["rtf", "odt", "doc", "ppt"])
    def test_extensoes_unstructured_delegam_para_unstructured(self, tmp_path, extensao):
        """Deve usar Unstructured para extensões legadas."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / f"legado.{extensao}"
        arquivo.write_bytes(b"fake legacy content")

        with patch(
            "sei_ia.data.etl.extract.uploads._get_text_with_unstructured",
            return_value=f"texto do arquivo {extensao}",
        ) as mock_unstructured:
            resultado = extract_text_from_file(str(arquivo), extensao)

        mock_unstructured.assert_called_once_with(str(arquivo))
        assert extensao in resultado

    def test_odp_delega_para_extrator_odp(self, tmp_path):
        """Deve usar extrator ODP para arquivos ODP."""
        from sei_ia.data.etl.extract.uploads import extract_text_from_file

        arquivo = tmp_path / "apresentacao.odp"
        arquivo.write_bytes(b"PK fake odp content")

        with patch(
            "sei_ia.data.etl.extract.uploads._get_text_from_odp_file",
            return_value="Slides da apresentação",
        ) as mock_odp:
            resultado = extract_text_from_file(str(arquivo), "odp")

        mock_odp.assert_called_once_with(str(arquivo))
        assert resultado == "Slides da apresentação"


class TestDownloadAndExtractUpload:
    """Testes para a função download_and_extract_upload."""

    def test_sucesso_retorna_nome_e_conteudo(self, tmp_path):
        """Deve retornar tupla (nome_original, conteudo_extraido) no sucesso."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(
            id_upload=42,
            nome_original="relatorio_anual.txt",
            extensao="txt",
        )

        fake_file = tmp_path / "relatorio_anual_up42_abc12345.txt"
        fake_file.write_text("Relatório anual da unidade.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            return_value=str(fake_file),
        ):
            nome, conteudo = asyncio.run(download_and_extract_upload(upload))

        assert nome == "relatorio_anual.txt"
        assert "Relatório anual da unidade" in conteudo

    def test_download_com_falha_retorna_mensagem_de_erro(self):
        """Deve retornar tupla com mensagem de erro quando o download falha."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(
            id_upload=99,
            nome_original="arquivo_falho.pdf",
            extensao="pdf",
        )

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            side_effect=ConnectionError("Servidor da API indisponível"),
        ):
            nome, conteudo = asyncio.run(download_and_extract_upload(upload))

        assert nome == "arquivo_falho.pdf"
        assert "[Erro ao processar o arquivo arquivo_falho.pdf]" in conteudo

    def test_extracao_com_falha_retorna_mensagem_de_erro(self, tmp_path):
        """Deve retornar mensagem de erro quando a extração de texto falha."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(
            id_upload=10,
            nome_original="corrompido.pdf",
            extensao="pdf",
        )

        fake_file = tmp_path / "corrompido_up10.pdf"
        fake_file.write_bytes(b"arquivo corrompido")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.extract_text_from_file",
                side_effect=RuntimeError("Falha ao processar PDF"),
            ),
        ):
            nome, conteudo = asyncio.run(download_and_extract_upload(upload))

        assert nome == "corrompido.pdf"
        assert "[Erro ao processar o arquivo corrompido.pdf]" in conteudo

    def test_nome_original_preservado_no_retorno(self, tmp_path):
        """Deve preservar o nome_original do upload na tupla de retorno."""
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
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            return_value=str(fake_file),
        ):
            nome, _ = asyncio.run(download_and_extract_upload(upload))

        assert nome == nome_original

    def test_id_upload_e_extensao_passados_ao_handler(self, tmp_path):
        """Deve passar id_upload e extensao corretos para o SEIDBHandler."""
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
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                return_value=str(fake_file),
            ) as mock_download,
            patch(
                "sei_ia.data.etl.extract.uploads._get_text_from_file_with_docling",
                return_value="Conteúdo do despacho",
            ),
        ):
            asyncio.run(download_and_extract_upload(upload))

        mock_download.assert_called_once_with(55, "docx")


class TestProcessUploads:
    """Testes para a função process_uploads."""

    def test_lista_vazia_retorna_string_vazia(self):
        """Deve retornar string vazia para lista vazia."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        resultado = asyncio.run(process_uploads([]))

        assert resultado == ""

    def test_none_retorna_string_vazia(self):
        """Deve retornar string vazia para None."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        resultado = asyncio.run(process_uploads(None))

        assert resultado == ""

    def test_upload_unico_envolto_em_tags_uploads(self, tmp_path):
        """O resultado deve começar com <uploads> e terminar com </uploads>."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(id_upload=1, nome_original="memo.txt", extensao="txt")

        fake = tmp_path / "memo_up1.txt"
        fake.write_text("Memorando interno.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            return_value=str(fake),
        ):
            resultado = asyncio.run(process_uploads([upload]))

        assert resultado.startswith("<uploads>")
        assert resultado.endswith("</uploads>")

    def test_upload_unico_contem_cabecalho_e_conteudo(self, tmp_path):
        """Deve incluir '# Arquivo: <nome>' e o conteúdo extraído no bloco."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(id_upload=3, nome_original="oficio.txt", extensao="txt")

        fake = tmp_path / "oficio_up3.txt"
        fake.write_text("Ofício de solicitação de dados.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            return_value=str(fake),
        ):
            resultado = asyncio.run(process_uploads([upload]))

        assert "# Arquivo: oficio.txt" in resultado
        assert "Ofício de solicitação de dados" in resultado

    def test_multiplos_uploads_todos_incluidos(self, tmp_path):
        """Deve incluir todos os uploads no resultado final."""
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

        def mock_download(id_upload, extensao):
            return fakes[id_upload]

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            side_effect=mock_download,
        ):
            resultado = asyncio.run(process_uploads(uploads))

        for u in uploads:
            assert f"# Arquivo: {u.nome_original}" in resultado
        assert "Conteúdo do documento 1" in resultado
        assert "Conteúdo do documento 2" in resultado
        assert "Conteúdo do documento 3" in resultado

    def test_upload_com_falha_inclui_mensagem_de_erro(self, tmp_path):
        """Falha em um upload não deve impedir os demais e inclui mensagem de erro."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        uploads = [
            UploadItem(id_upload=1, nome_original="valido.txt", extensao="txt"),
            UploadItem(id_upload=2, nome_original="invalido.pdf", extensao="pdf"),
        ]

        fake_valido = tmp_path / "valido_up1.txt"
        fake_valido.write_text("Conteúdo válido.", encoding="utf-8")

        def mock_download(id_upload, extensao):
            if id_upload == 1:
                return str(fake_valido)
            raise OSError("Arquivo não encontrado no servidor")

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            side_effect=mock_download,
        ):
            resultado = asyncio.run(process_uploads(uploads))

        assert "# Arquivo: valido.txt" in resultado
        assert "Conteúdo válido" in resultado
        assert "# Arquivo: invalido.pdf" in resultado
        assert "[Erro ao processar o arquivo invalido.pdf]" in resultado

    def test_formato_exato_do_template(self, tmp_path):
        """O resultado deve corresponder exatamente ao template definido no módulo."""
        from sei_ia.data.etl.extract.uploads import (
            UPLOAD_BLOCK_TEMPLATE,
            UPLOADS_WRAPPER_TEMPLATE,
            process_uploads,
        )

        upload = UploadItem(id_upload=7, nome_original="modelo.txt", extensao="txt")

        fake = tmp_path / "modelo_up7.txt"
        fake.write_text("Texto do modelo.", encoding="utf-8")

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            return_value=str(fake),
        ):
            resultado = asyncio.run(process_uploads([upload]))

        bloco_esperado = UPLOAD_BLOCK_TEMPLATE.format(
            nome_original="modelo.txt",
            conteudo="Texto do modelo.",
        )
        esperado = UPLOADS_WRAPPER_TEMPLATE.format(blocos=bloco_esperado)
        assert resultado == esperado

    def test_apenas_um_par_de_tags_uploads(self, tmp_path):
        """Deve haver apenas um par de tags <uploads> no resultado."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        uploads = [
            UploadItem(id_upload=1, nome_original="a.txt", extensao="txt"),
            UploadItem(id_upload=2, nome_original="b.txt", extensao="txt"),
        ]

        fakes = {}
        for u in uploads:
            f = tmp_path / f"{u.nome_original}"
            f.write_text(f"Conteúdo {u.nome_original}.", encoding="utf-8")
            fakes[u.id_upload] = str(f)

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            side_effect=lambda id_upload, ext: fakes[id_upload],
        ):
            resultado = asyncio.run(process_uploads(uploads))

        assert resultado.count("<uploads>") == 1
        assert resultado.count("</uploads>") == 1

    def test_todos_uploads_falham_resultado_contem_todos_os_erros(self):
        """Quando todos os uploads falham, o resultado deve ser estruturado com todos os erros."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        uploads = [
            UploadItem(id_upload=1, nome_original="a.pdf", extensao="pdf"),
            UploadItem(id_upload=2, nome_original="b.pdf", extensao="pdf"),
        ]

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            side_effect=ConnectionError("Servidor indisponível"),
        ):
            resultado = asyncio.run(process_uploads(uploads))

        # Mesmo com falhas totais, o resultado deve ser válido e não vazio
        assert resultado.startswith("<uploads>")
        assert resultado.endswith("</uploads>")
        assert "# Arquivo: a.pdf" in resultado
        assert "# Arquivo: b.pdf" in resultado
        assert "[Erro ao processar o arquivo a.pdf]" in resultado
        assert "[Erro ao processar o arquivo b.pdf]" in resultado

    def test_ordem_dos_blocos_corresponde_a_ordem_dos_uploads(self, tmp_path):
        """A ordem dos blocos no resultado deve corresponder à ordem da lista de uploads."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        uploads = [
            UploadItem(id_upload=10, nome_original="primeiro.txt", extensao="txt"),
            UploadItem(id_upload=20, nome_original="segundo.txt", extensao="txt"),
            UploadItem(id_upload=30, nome_original="terceiro.txt", extensao="txt"),
        ]

        fakes = {}
        for u in uploads:
            f = tmp_path / f"{u.nome_original}"
            f.write_text(f"Conteudo de {u.nome_original}", encoding="utf-8")
            fakes[u.id_upload] = str(f)

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            side_effect=lambda id_upload, _ext: fakes[id_upload],
        ):
            resultado = asyncio.run(process_uploads(uploads))

        pos_primeiro = resultado.index("# Arquivo: primeiro.txt")
        pos_segundo = resultado.index("# Arquivo: segundo.txt")
        pos_terceiro = resultado.index("# Arquivo: terceiro.txt")

        assert pos_primeiro < pos_segundo < pos_terceiro


class TestDownloadAndExtractUploadExtras:
    """Testes adicionais para cenários de borda em download_and_extract_upload."""

    def test_timeout_no_download_retorna_mensagem_de_erro(self):
        """TimeoutError durante download deve retornar tupla com mensagem de erro."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(id_upload=77, nome_original="demora.pdf", extensao="pdf")

        with patch(
            "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
            side_effect=TimeoutError("Timeout ao conectar com o servidor"),
        ):
            nome, conteudo = asyncio.run(download_and_extract_upload(upload))

        assert nome == "demora.pdf"
        assert "[Erro ao processar o arquivo demora.pdf]" in conteudo

    def test_extracao_retorna_string_vazia_preservada(self, tmp_path):
        """Quando a extração retorna string vazia, deve retornar (nome, '') sem transformar em erro."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(id_upload=20, nome_original="vazio.txt", extensao="txt")

        fake_file = tmp_path / "vazio_up20.txt"
        fake_file.write_bytes(b"")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.extract_text_from_file",
                return_value="",
            ),
        ):
            nome, conteudo = asyncio.run(download_and_extract_upload(upload))

        assert nome == "vazio.txt"
        assert conteudo == ""


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
        """Upload de MP3 deve acionar transcribe_audio_file em vez de extract_text_from_file."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(id_upload=10, nome_original="reuniao.mp3", extensao="mp3")

        fake_file = tmp_path / "reuniao_up10.mp3"
        fake_file.write_bytes(b"fake mp3 content")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Transcrição da reunião.",
            ) as mock_transcribe,
        ):
            nome, conteudo = asyncio.run(download_and_extract_upload(upload))

        mock_transcribe.assert_called_once()
        assert nome == "reuniao.mp3"
        assert conteudo == "Transcrição da reunião."

    def test_arquivo_wav_chama_transcribe_audio_file(self, tmp_path):
        """Upload de WAV deve acionar transcribe_audio_file."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(id_upload=20, nome_original="gravacao.wav", extensao="wav")

        fake_file = tmp_path / "gravacao_up20.wav"
        fake_file.write_bytes(b"RIFF fake wav")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Texto da gravação.",
            ) as mock_transcribe,
        ):
            nome, conteudo = asyncio.run(download_and_extract_upload(upload))

        mock_transcribe.assert_called_once()
        assert conteudo == "Texto da gravação."

    def test_arquivo_audio_nao_chama_extract_text_from_file(self, tmp_path):
        """Para áudio, extract_text_from_file não deve ser chamado."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(id_upload=30, nome_original="audio.ogg", extensao="ogg")

        fake_file = tmp_path / "audio_up30.ogg"
        fake_file.write_bytes(b"fake ogg")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
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
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
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

    def test_falha_na_transcricao_retorna_mensagem_de_erro(self, tmp_path):
        """Falha em transcribe_audio_file deve retornar tupla com mensagem de erro."""
        from sei_ia.data.etl.extract.uploads import download_and_extract_upload

        upload = UploadItem(
            id_upload=50, nome_original="audio_corrompido.mp3", extensao="mp3"
        )

        fake_file = tmp_path / "audio_up50.mp3"
        fake_file.write_bytes(b"corrupted")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                side_effect=Exception("Serviço de transcrição indisponível"),
            ),
        ):
            nome, conteudo = asyncio.run(download_and_extract_upload(upload))

        assert nome == "audio_corrompido.mp3"
        assert "[Erro ao processar o arquivo audio_corrompido.mp3]" in conteudo

    @pytest.mark.parametrize(
        "extensao",
        ["mp3", "mp4", "wav", "ogg", "m4a", "webm", "flac", "aac", "opus", "wma"],
    )
    def test_todas_extensoes_de_audio_acionam_transcricao(self, tmp_path, extensao):
        """Todas as extensões de áudio definidas em EXT_AUDIO devem acionar transcrição."""
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
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value=f"Texto do {extensao}.",
            ) as mock_transcribe,
        ):
            nome, conteudo = asyncio.run(download_and_extract_upload(upload))

        mock_transcribe.assert_called_once()
        assert conteudo == f"Texto do {extensao}."


class TestProcessUploadsComAudio:
    """Testes para process_uploads com arquivos de áudio."""

    def test_upload_audio_transcreve_e_inclui_no_resultado(self, tmp_path):
        """Upload de áudio deve ser transcrito e incluído no bloco <uploads>."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(
            id_upload=100, nome_original="reuniao_plenaria.mp3", extensao="mp3"
        )

        fake_file = tmp_path / "reuniao_up100.mp3"
        fake_file.write_bytes(b"fake mp3")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Presidente abre a sessão às 10h.",
            ),
        ):
            resultado = asyncio.run(process_uploads([upload]))

        assert "<uploads>" in resultado
        assert "# Arquivo: reuniao_plenaria.mp3" in resultado
        assert "Presidente abre a sessão às 10h." in resultado

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

        def mock_download(id_upload, extensao):
            return str(fake_txt) if id_upload == 1 else str(fake_mp3)

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                side_effect=mock_download,
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Texto da gravação de áudio.",
            ),
        ):
            resultado = asyncio.run(process_uploads(uploads))

        assert "# Arquivo: nota.txt" in resultado
        assert "Nota técnica aprovada" in resultado
        assert "# Arquivo: audio.mp3" in resultado
        assert "Texto da gravação de áudio." in resultado

    def test_falha_na_transcricao_nao_bloqueia_outros_uploads(self, tmp_path):
        """Falha na transcrição de um áudio não deve impedir os demais uploads."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        uploads = [
            UploadItem(id_upload=1, nome_original="audio_ok.mp3", extensao="mp3"),
            UploadItem(id_upload=2, nome_original="audio_falho.wav", extensao="wav"),
        ]

        fake_mp3 = tmp_path / "audio_up1.mp3"
        fake_mp3.write_bytes(b"fake mp3")

        fake_wav = tmp_path / "audio_up2.wav"
        fake_wav.write_bytes(b"fake wav")

        def mock_download(id_upload, extensao):
            return str(fake_mp3) if id_upload == 1 else str(fake_wav)

        transcricao_chamadas = []

        async def mock_transcribe(file_path, extensao):
            transcricao_chamadas.append(file_path)
            if "up2" in file_path:
                raise Exception("Falha ao transcrever")
            return "Transcrição do áudio ok."

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                side_effect=mock_download,
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                side_effect=mock_transcribe,
            ),
        ):
            resultado = asyncio.run(process_uploads(uploads))

        assert "# Arquivo: audio_ok.mp3" in resultado
        assert "Transcrição do áudio ok." in resultado
        assert "# Arquivo: audio_falho.wav" in resultado
        assert "[Erro ao processar o arquivo audio_falho.wav]" in resultado

    def test_resultado_audio_envolto_em_tags_uploads(self, tmp_path):
        """O resultado com áudio deve estar dentro das tags <uploads>...</uploads>."""
        from sei_ia.data.etl.extract.uploads import process_uploads

        upload = UploadItem(id_upload=5, nome_original="audio.webm", extensao="webm")

        fake_file = tmp_path / "audio_up5.webm"
        fake_file.write_bytes(b"fake webm")

        with (
            patch(
                "sei_ia.data.etl.extract.uploads.SEIDBHandler.md_ia_download_arquivo_upload_assistente",
                return_value=str(fake_file),
            ),
            patch(
                "sei_ia.data.etl.extract.uploads.transcribe_audio_file",
                new_callable=AsyncMock,
                return_value="Transcrição do webm.",
            ),
        ):
            resultado = asyncio.run(process_uploads([upload]))

        assert resultado.startswith("<uploads>")
        assert resultado.endswith("</uploads>")

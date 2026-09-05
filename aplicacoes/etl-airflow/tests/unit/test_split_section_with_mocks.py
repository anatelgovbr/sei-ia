import unittest
import pytest
import re
from jobs.dags.preprocessing.sections_dictionary import SECTIONS_DICTIONARY
from itertools import product
from jobs.dags.preprocessing.split_section2 import SplitSection
from bs4 import BeautifulSoup
from jobs.dags.preprocessing.text_clean import remove_sep_token

# Os fixtures em tests/unit/mocks/split_section/ são sintéticos (não são
# documentos reais do SEI) — ver tests/unit/mocks/split_section/_gen.py.


def test_doc_find_all():
    html_text = \
        "<p class=\"Texto_Espaco_Duplo_Recuo_Primeira_Linha\"><strong>DECIDE</strong></p><p>decisão</p>"
    doc = BeautifulSoup(html_text, 'html.parser')
    html_split = SplitSection.doc_find_all(doc)
    found_list = [SplitSection.doc_find(BeautifulSoup(str(soup),'html.parser'),["DECIDE"]) for soup in html_split]
    assert len([f for f in found_list if f]) == 1


@pytest.mark.parametrize("file_name",[
    "splitsectioninput_243264_4_0.html",
    "splitsectioninput_243264_4_0_dc.html"
])
def test_split_section_method_despacho(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        split_section = SplitSection(
            html=html_text, html_sections=SECTIONS_DICTIONARY.get("despacho")
        )
        res = split_section.split_section(["DECIDE","D E C I D E","RESOLVE","INFORMA"])
        assert len(res) > 0


@pytest.mark.parametrize("file_name",[
    "splitsectioninput_243264_4_0.html",
    "splitsectioninput_243264_4_0_dc.html"
])
def test_doc_find_recursion(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        doc = BeautifulSoup(html_text, 'html.parser')

        search = ["DECIDE","D E C I D E","RESOLVE","INFORMA"]
        p1 = SplitSection.doc_find(doc,search)
        assert p1 is not None
        p2 = SplitSection.doc_find(BeautifulSoup(str(p1),'html.parser'),search)
        assert p2 is not None


@pytest.mark.parametrize("file_name",[
    "splitsectioninput_243264_4_0.html", "splitsectioninput_243264_4_0_dc.html",
    "splitsectioninput_3839143_7_0.html", "splitsectioninput_3839143_7_0_dc.html",
    "splitsectioninput_422762_7_1.html", "splitsectioninput_422762_7_1_dc.html",
    "splitsectioninput_422762_7_0.html", "splitsectioninput_422762_7_0_dc.html",
    "splitsectioninput_397413_8_0.html", "splitsectioninput_397413_8_0_dc.html",
    "splitsectioninput_397413_8_1.html", "splitsectioninput_397413_8_1_dc.html",
    "splitsectioninput_422762_8_0.html", "splitsectioninput_422762_8_0_dc.html",
    "splitsectioninput_422762_8_1.html", "splitsectioninput_422762_8_1_dc.html",
    "splitsectioninput_422762_8_2.html", "splitsectioninput_422762_8_2_dc.html",
    "splitsectioninput_433260_8_0.html", "splitsectioninput_433260_8_0_dc.html",
    "splitsectioninput_433260_8_1.html", "splitsectioninput_433260_8_1_dc.html",
    "splitsectioninput_3839143_8_0.html", "splitsectioninput_3839143_8_0_dc.html",
    "splitsectioninput_3839143_8_1.html", "splitsectioninput_3839143_8_1_dc.html",
    "splitsectioninput_243264_16_0.html", "splitsectioninput_243264_16_0_dc.html",
    # "splitsectioninput_243264_16_1.html", "splitsectioninput_243264_16_1_dc.html", # não tem a seção anexo mesmo
    "splitsectioninput_243264_16_2.html", "splitsectioninput_243264_16_2_dc.html",
    "splitsectioninput_3817545_94_0.html", "splitsectioninput_3817545_94_0_dc.html",
])
def test_doc_find(file_name):
    DOCS_WITH_SECTIONS = {"8":"acordao","7":"analise","4":"despacho","16":"informe","94":"voto"}
    doc_type = DOCS_WITH_SECTIONS[file_name.split("_")[2]]
    p_list = []
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        doc = BeautifulSoup(html_text, 'html.parser')
        fields = SECTIONS_DICTIONARY[doc_type]
        for field in fields.keys():
            search = fields[field]
            p = SplitSection.doc_find(doc,search)
            p_list.append(p)
    assert len(p_list) > 0


@pytest.mark.parametrize("file_name",[
    "splitsectioninput_243264_4_0.html", "splitsectioninput_243264_4_0_dc.html",
    "splitsectioninput_3839143_7_0.html", "splitsectioninput_3839143_7_0_dc.html",
    "splitsectioninput_422762_7_1.html", "splitsectioninput_422762_7_1_dc.html",
    "splitsectioninput_422762_7_0.html", "splitsectioninput_422762_7_0_dc.html",
    "splitsectioninput_397413_8_0.html", "splitsectioninput_397413_8_0_dc.html",
    "splitsectioninput_397413_8_1.html", "splitsectioninput_397413_8_1_dc.html",
    "splitsectioninput_422762_8_0.html", "splitsectioninput_422762_8_0_dc.html",
    "splitsectioninput_422762_8_1.html", "splitsectioninput_422762_8_1_dc.html",
    "splitsectioninput_422762_8_2.html", "splitsectioninput_422762_8_2_dc.html",
    "splitsectioninput_433260_8_0.html", "splitsectioninput_433260_8_0_dc.html",
    "splitsectioninput_433260_8_1.html", "splitsectioninput_433260_8_1_dc.html",
    "splitsectioninput_3839143_8_0.html", "splitsectioninput_3839143_8_0_dc.html",
    "splitsectioninput_3839143_8_1.html", "splitsectioninput_3839143_8_1_dc.html",
    "splitsectioninput_243264_16_0.html", "splitsectioninput_243264_16_0_dc.html",
    # "splitsectioninput_243264_16_1.html", "splitsectioninput_243264_16_1_dc.html", # não tem a seção anexo mesmo
    "splitsectioninput_243264_16_2.html", "splitsectioninput_243264_16_2_dc.html",
    "splitsectioninput_3817545_94_0.html", "splitsectioninput_3817545_94_0_dc.html",
])
def test_get_sections(file_name):
    DOCS_WITH_SECTIONS = {"8":"acordao","7":"analise","4":"despacho","16":"informe","94":"voto"}
    doc_type = DOCS_WITH_SECTIONS[file_name.split("_")[2]]

    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        doc = BeautifulSoup(html_text, 'html.parser')
        fields = SECTIONS_DICTIONARY[doc_type]
        split_section = SplitSection(html=html_text, html_sections=fields)
        assert len(split_section.sections) > 0
        check = False
        for fld,k in zip(split_section.sections[1:],fields):
            check = re.sub(r'[^A-Za-záàâãéèêíïóôõöúçñÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ\s\/]','', fld.text) in fields[k]
            if check:
                break
        assert check is True






@pytest.mark.parametrize(
    "file_name",
    [
        "splitsectioninput_243264_4_0.html",
        "splitsectioninput_243264_4_0_dc.html",
    ],
)
def test_split_section_despacho(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        split_section = SplitSection(
            html=html_text, html_sections=SECTIONS_DICTIONARY.get("despacho")
        ).create_sections()
        difference_keys = set(SECTIONS_DICTIONARY.get("despacho").keys()) - set(split_section.keys())
        assert len(difference_keys) == 0, f"Os campos '{difference_keys}' nao foi encontrado."
        list_empty_fields = [k for k,v in split_section.items() if (len(v) == 0 and k != "preambulo")]
        assert len(list_empty_fields) == 0, f"Os campos {' '.join(list_empty_fields)} nao foram encontratos"

@pytest.mark.parametrize("file_name",[
    "splitsectioninput_3839143_7_0.html", "splitsectioninput_3839143_7_0_dc.html",
    "splitsectioninput_422762_7_1.html", "splitsectioninput_422762_7_1_dc.html",
    "splitsectioninput_422762_7_0.html", "splitsectioninput_422762_7_0_dc.html",
])
def test_split_section_analise(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        split_section = SplitSection(
            html=html_text, html_sections=SECTIONS_DICTIONARY.get("analise")
        ).create_sections()
        difference_keys = set(SECTIONS_DICTIONARY.get("analise").keys()) - set(split_section.keys())
        assert len(difference_keys) == 0, f"Os campos '{difference_keys}' nao foi encontrado."
        list_empty_fields = [k for k,v in split_section.items() if (len(v) == 0 and k != "preambulo")]
        assert len(list_empty_fields) == 0, f"Os campos {' '.join(list_empty_fields)} nao foram encontratos"

@pytest.mark.parametrize(
    "file_name",
    [
        "splitsectioninput_397413_8_0.html", "splitsectioninput_397413_8_0_dc.html",
        "splitsectioninput_397413_8_1.html", "splitsectioninput_397413_8_1_dc.html",
        "splitsectioninput_422762_8_0.html", "splitsectioninput_422762_8_0_dc.html",
        "splitsectioninput_422762_8_1.html", "splitsectioninput_422762_8_1_dc.html",
        "splitsectioninput_422762_8_2.html", "splitsectioninput_422762_8_2_dc.html",
        "splitsectioninput_433260_8_0.html", "splitsectioninput_433260_8_0_dc.html",
        "splitsectioninput_433260_8_1.html", "splitsectioninput_433260_8_1_dc.html",
        "splitsectioninput_3839143_8_0.html", "splitsectioninput_3839143_8_0_dc.html",
        "splitsectioninput_3839143_8_1.html", "splitsectioninput_3839143_8_1_dc.html",
    ],
)
def test_split_section_acordao(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        split_section = SplitSection(
            html=html_text, html_sections=SECTIONS_DICTIONARY.get("acordao")
        ).create_sections()
        difference_keys = set(SECTIONS_DICTIONARY.get("acordao").keys()) - set(split_section.keys())
        assert len(difference_keys) == 0, f"Os campos '{difference_keys}' nao foi encontrado."
        list_empty_fields = [k for k,v in split_section.items() if (len(v) == 0 and k != "preambulo")]
        assert len(list_empty_fields) ==0 , f"Os campos {' '.join(list_empty_fields)} nao foram encontratos"

@pytest.mark.parametrize(
    "file_name",
    [
        "splitsectioninput_243264_16_0.html", "splitsectioninput_243264_16_0_dc.html",
        # "splitsectioninput_243264_16_1.html", "splitsectioninput_243264_16_1_dc.html", # não tem a seção anexo mesmo
        "splitsectioninput_243264_16_2.html", "splitsectioninput_243264_16_2_dc.html",
    ],
)
def test_split_section_informe(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        split_section = SplitSection(
            html=html_text, html_sections=SECTIONS_DICTIONARY.get("informe")
        ).create_sections()
        difference_keys = set(SECTIONS_DICTIONARY.get("informe").keys()) - set(split_section.keys())
        assert len(difference_keys) == 0, f"Os campos '{difference_keys}' nao foi encontrado."
        list_empty_fields = [k for k,v in split_section.items() if (len(v) == 0 and k != "preambulo")]
        assert len(list_empty_fields) == 0, f"Os campos {', '.join(list_empty_fields)} nao foram encontratos"

@pytest.mark.parametrize(
    "file_name",
    [
       "splitsectioninput_3817545_94_0.html",
       "splitsectioninput_3817545_94_0_dc.html",
    ],
)
def test_split_section_voto(file_name):
    f = open(f"tests/unit/mocks/split_section/{file_name}")
    html_text = f.read()
    split_section = SplitSection(
        html=html_text, html_sections=SECTIONS_DICTIONARY.get("voto")
    ).create_sections()
    difference_keys = set(SECTIONS_DICTIONARY.get("voto").keys()) - set(split_section.keys())
    assert len(difference_keys) == 0, f"Os campos '{difference_keys}' nao foi encontrado."


@pytest.mark.parametrize(
    "file_name",
    [
        "splitsectioninput_243264_4_0.html",
        "splitsectioninput_243264_4_0_dc.html",
    ],
)
def test_split_section_despacho_content(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        split_section = SplitSection(
            html=html_text, html_sections=SECTIONS_DICTIONARY.get("despacho")
        ).create_sections()
        preambulo = remove_sep_token(split_section.get("preambulo",""))
        decide = remove_sep_token(split_section.get("decide",""))

        preambulo_expected = remove_sep_token("despacho decisorio no 99/2026/sei/teste processo no 00000.000000/0000-00 interessado: empresa teste de telecomunicacoes ltda o superintendente de fiscalizacao, no uso de suas atribuicoes legais, examinando os autos do processo em epigrafe, instaurado em desfavor da empresa teste de telecomunicacoes ltda;")

        decide_expected = remove_sep_token("aplicar advertencia a prestadora pelo descumprimento verificado no relatorio de fiscalizacao. fica concedido o prazo de 10 dias para interposicao de recurso administrativo.")

        assert preambulo.strip() == preambulo_expected

        assert decide.strip() == decide_expected

@pytest.mark.parametrize(
    "file_name",
    [
        "splitsectioninput_243264_16_2.html",
        "splitsectioninput_243264_16_2_dc.html",
    ],
)
def test_split_section_informe_content(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        split_section = SplitSection(
            html=html_text, html_sections=SECTIONS_DICTIONARY.get("informe")
        ).create_sections()

        preambulo = remove_sep_token(split_section.get("preambulo",""))
        assunto = remove_sep_token(split_section.get("assunto",""))
        referencias = remove_sep_token(split_section.get("referencias",""))
        analise = remove_sep_token(split_section.get("analise",""))
        anexos = remove_sep_token(split_section.get("anexos",""))
        conclusao = remove_sep_token(split_section.get("conclusao",""))

        preambulo_expected = remove_sep_token("informe no 40/2026/sei/teste processo no 00000.000000/0000-00")

        assunto_expected = remove_sep_token("informe de primeira instancia. aplicacao de sancao. procedimento para apuracao de descumprimento de obrigacoes.")

        referencias_expected = remove_sep_token("regulamento do servico, aprovado pela resolucao no 272, de 9 de agosto de 2001.")

        anexos_expected = remove_sep_token("anexo i - relatorio de fiscalizacao. anexo ii - planilha de calculo de multa.")

        conclusao_expected = remove_sep_token("propoe-se a aplicacao de multa a prestadora no valor de mil reais, em razao do descumprimento verificado.")

        assert preambulo.strip() == preambulo_expected
        assert assunto.strip() == assunto_expected
        assert referencias.strip() == referencias_expected
        assert anexos.strip() == anexos_expected
        assert conclusao.strip() == conclusao_expected

        for text in [assunto_expected,referencias_expected,anexos_expected,conclusao_expected]:
            assert text not in analise

@pytest.mark.parametrize(
    "file_name",
    [
        "splitsectioninput_397413_8_1.html",
        "splitsectioninput_397413_8_1_dc.html",
    ],
)
def test_split_section_acordao_content(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        split_section = SplitSection(
            html=html_text, html_sections=SECTIONS_DICTIONARY.get("acordao")
        ).create_sections()
        preambulo = remove_sep_token(split_section.get("preambulo",""))
        ementa = remove_sep_token(split_section.get("ementa",""))
        acordao = remove_sep_token(split_section.get("acordao",""))

        acordao_expected = remove_sep_token("vistos, relatados e discutidos os presentes autos, acordam os membros do conselho diretor da anatel, por unanimidade, aprovar o regulamento nos termos da minuta anexa. participaram da deliberacao o presidente e os conselheiros presentes a sessao.")

        assert acordao.strip() == acordao_expected

@pytest.mark.parametrize(
    "file_name",
    [
        "splitsectioninput_3817545_94_0.html",
        "splitsectioninput_3817545_94_0_dc.html",
    ],
)
def test_split_section_voto_content(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        split_section = SplitSection(
            html=html_text, html_sections=SECTIONS_DICTIONARY.get("voto")
        ).create_sections()

        preambulo = remove_sep_token(split_section.get("preambulo",""))
        conselheiro = remove_sep_token(split_section.get("conselheiro",""))
        assunto = remove_sep_token(split_section.get("assunto",""))
        ementa = remove_sep_token(split_section.get("ementa",""))
        referencias = remove_sep_token(split_section.get("referencias",""))
        relatorio = remove_sep_token(split_section.get("relatorio",""))
        conclusao = remove_sep_token(split_section.get("conclusao",""))

        preambulo_expected = remove_sep_token("voto no 50/2026/sei/teste processo no 00000.000000/0000-00")

        conselheiro_expected = remove_sep_token("fulano de tal")

        assunto_expected = remove_sep_token("analise de peticao recebida como recurso administrativo contra despacho decisorio que negou provimento ao pedido.")

        ementa_expected = remove_sep_token("superintendencia de teste. direito de peticao. pedido de prorrogacao de prazo de vistas.")

        referencias_expected = remove_sep_token("regimento interno da anatel, aprovado pela resolucao no 612, de 29 de abril de 2013.")

        relatorio_expected = remove_sep_token("trata-se de analise da peticao protocolizada sob sei no 7654321, recebida como recurso administrativo pela prestadora.")

        conclusao_expected = remove_sep_token("solicito a prorrogacao do prazo de vistas, por 60 dias, com fundamento no regimento interno da anatel.")

        assert preambulo.strip() == preambulo_expected
        assert conselheiro.strip() == conselheiro_expected
        assert assunto.strip() == assunto_expected
        assert ementa.strip() == ementa_expected
        assert referencias.strip() == referencias_expected
        assert relatorio.strip() == relatorio_expected
        assert conclusao.strip() == conclusao_expected


@pytest.mark.parametrize(
    "file_name",
    [
        "splitsectioninput_1905531_4_0.html",
        "splitsectioninput_1905531_4_0_dc.html",
    ],
)
def test_split_section_despacho_content_single_paragraph(file_name):
    with open(f"tests/unit/mocks/split_section/{file_name}") as f:
        html_text = f.read()
        split_section = SplitSection(html=html_text, html_sections=SECTIONS_DICTIONARY.get("despacho")).create_sections()
        assert all([bool(split_section[k].strip()) for k in split_section.keys()])


# if __name__ == "__main__":
#     unittest.main()

import unittest
import pytest
import re
from jobs.dags.preprocessing.sections_dictionary import SECTIONS_DICTIONARY
from itertools import product
from jobs.dags.preprocessing.split_section2 import SplitSection
from bs4 import BeautifulSoup
from jobs.dags.preprocessing.text_clean import remove_sep_token


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

        preambulo_expected_1 = remove_sep_token("o superintendente de controle de obrigações da agência nacional de telecomunicações, no uso de suas atribuições legais e regulamentares, em especial a disposta no art. 158, inciso iv, do regimento interno da anatel, aprovado pela resolução nº 612, de 29 de abril de 2013, examinando os autos do processo em epígrafe, instaurado em desfavor da mega grupo de telecomunicações ltda. - epp, cnpj/mf n.º 08.847.591/0001-49, fistel nº 50405074883, empresa autorizada a explorar o serviço de comunicação multimídia, para apurar descumprimentos relativos ao regulamento do serviço de comunicação multimídia – rscm, aprovado pela resolução n.º 272, de 9 de agosto de 2001;<SEP> considerando o teor do informe nº 38/2017/sei/codi/sco (sei nº 1156025);")

        preambulo_expected_2 = remove_sep_token("despacho decisório nº 14/2017/sei/codi/sco<SEP>  <SEP> processo nº 53500.000801/2016-76<SEP> interessado: mega grupo de telecomunicações ltda - epp<SEP>  <SEP> " + preambulo_expected_1)

        decide_expected = remove_sep_token("aplicar sanção de multa no valor de r$1.185,64 (mil, cento e oitenta e cinco reais e sessenta e quatro centavos), em razão do descumprimento ao art. 51 do regulamento do serviço de comunicação multimídia, aprovado pela resolução nº 272/2001.<SEP>caso a prestadora resolva, de acordo com o disposto no § 5º do art. 33 do regulamento de aplicação de sanções administrativas (rasa), aprovado pela resolução n.º 589/2012, renunciar expressamente ao direito de recorrer da decisão de primeira instância, fará jus a um fator de redução de 25% (vinte e cinco por cento) no valor da multa aplicada, desde que faça o recolhimento no prazo regulamentar, totalizando, para esse caso, o montante de r$889,23 (oitocentos e oitenta e nove reais e vinte e três centavos).")

        assert (preambulo.strip() == preambulo_expected_1) or (preambulo.strip() == preambulo_expected_2)

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

        preambulo_expected_1 = ""
        
        preambulo_expected_2 = remove_sep_token('informe nº 38/2017/sei/codi/sco<SEP>  processo nº 53500.000801/2016-76<SEP>  interessado: mega grupo de telecomunicações ltda - epp')

        assunto_expected = remove_sep_token('informe de 1ª instância. aplicação de sanção. procedimento para apuração de descumprimento de obrigações (pado). indício de irregularidade apresentada no relatório de fiscalização nº 0215/2013/uo021, de 24/07/2013, referente a obrigação de manter centro de atendimento telefônico gratuito, estabelecida no regulamento de serviço de comunicação multimídia, aprovado pela resolução nº 272/2001.')

        referencias_expected = remove_sep_token('regulamento do serviço de comunicação multimídia – rscm, aprovado pela resolução n.º 272, de 9 de agosto de 2001;<SEP> regimento interno da anatel, aprovado pela resolução nº 612, de 29 de abril de 2013;<SEP> despacho ordinatório de instauração nº 5/2016/sei/codi/sco (sei nº 0194765);<SEP> informe nº 34/2016/sei/codi/sco (sei nº 0196120);<SEP> relatório de fiscalização nº 0215/2013/uo021, de 24/07/2013 (fls. 2/26 do sei nº 0311126);<SEP> informe nº 126/2016/sei/codi/sco (sei nº 0707223);<SEP> procedimento para apuração de descumprimento de obrigações (pado) nº 53500.000801/2016-76.')

        anexos_expected = remove_sep_token("anexo i – metodologia para aplicação de sanções.<SEP> anexo ii – planilhas de cálculo de multa.")

        conclusao_expected = remove_sep_token('com base em todo o exposto, propõe-se a aplicação de multa à prestadora no valor de r$1.185,64 (um mil cento e oitenta e cinco reais e sessenta e quatro centavos), em razão do descumprimento ao art. 51 do do regulamento de serviço de comunicação multimídia, aprovado pela resolução nº 272/2001.<SEP>caso a prestadora resolva, de acordo com o disposto no § 5º do art. 33 do rasa, renunciar expressamente ao direito de recorrer da decisão de primeira instância, fará jus a um fator de redução de 25% (vinte e cinco por cento) no valor total da multa ora proposta, desde que faça o recolhimento no prazo regulamentar, totalizando, neste caso, o montante de r$889,23 (oitocentos e oitenta e nove reais e vinte e três centavos).')

        assert (preambulo.strip() == preambulo_expected_1) or (preambulo.strip() == preambulo_expected_2)
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
        
        acordao_expected = remove_sep_token('vistos, relatados e discutidos os presentes autos, acordam os membros do conselho diretor da anatel, por unanimidade, nos termos da análise nº 138/2017/sei/or (sei nº 1615428), integrante deste acórdão:<SEP>a) aprovar o regulamento do processo eletrônico da anatel, nos termos da minuta de resolução anexa à referida análise (sei nº 1813363); e,<SEP>b) dar por cumprida a ação regulatória nº 19 da portaria nº 491, de 10 de abril de 2017, que aprovou a agenda regulatória da anatel para o biênio 2017-2018. <SEP>participaram da deliberação o presidente juarez quadros do nascimento e os conselheiros otavio luiz rodrigues junior, anibal diniz e leonardo euler de morais.<SEP>ausente o conselheiro igor vilas boas de freitas.')

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

        preambulo_expected_1 = ''

        preambulo_expected_2 = remove_sep_token('voto nº 11/2020/mm<SEP> processo nº 53500.045917/2018-04<SEP> interessado: telefonica brasil s.a.')
        
        conselheiro_expected = remove_sep_token('moisés queiroz moreira')
        
        assunto_expected = remove_sep_token('análise de petições recebidas como recurso administrativo, apresentadas pela concessionária telefônica brasil s.a. contra o despacho decisório nº 7/2020/cpae/scp que negou provimento ao pedido de restabelecimento da sustentabilidade de suas concessões de serviço telefônico fixo comutado (stfc) local e longa distância nacional (ldn) e determinou o arquivamento.')
        
        ementa_expected = remove_sep_token('superintendência de competição. direito de petição. recebimento como recurso administrativo. pedido de restabelecimento da sustentabilidade das concessões do stfc. prorrogação do prazo de vistas.<SEP> análise da petição recebida como recurso administrativo (sei nº 5438091) e da petição complementar (sei nº 5770151), apresentadas pela concessionária telefônica brasil s.a. contra o despacho decisório nº 7/2020/cpae/scp (sei nº 5245363) que negou provimento ao pedido de restabelecimento da sustentabilidade de suas concessões de serviço telefônico fixo comutado (stfc) local e longa distância nacional (ldn) e determinou o arquivamento<SEP> pedido de prorrogação do prazo de vistas, por 120 (cento e vinte) dias.')
        
        referencias_expected = remove_sep_token('regimento interno da anatel, aprovado pela resolução nº 612, de 29 de abril de 2013.')
        
        relatorio_expected = remove_sep_token('trata-se de análise da petição protocolizada sob sei nº 5438091, recebida como recurso administrativo, e da petição complementar protocolizada sob sei nº 5770151, apresentadas pela concessionária telefônica brasil s.a. contra o despacho decisório nº 7/2020/cpae/scp (sei nº 5245363) por meio do qual o superintendente de competição decidiu negar provimento ao pedido de restabelecimento da sustentabilidade de suas concessões de serviço telefônico fixo comutado (stfc) local e longa distância nacional (ldn) e determinar o arquivamento dos autos.<SEP> em 27 de agosto de 2020, na reunião do conselho diretor nº 889, o conselheiro substituto raphael garcia de souza apresentou relatoria da matéria em epígrafe, consubstanciada em sua análise nº 26/2020/rg (sei nº 5862142).<SEP> naquela ocasião, com o fito de analisar mais detidamente o mérito da proposta, solicitei vistas dos autos, com fundamento no art. 15 do regimento interno da anatel, aprovado mediante a resolução nº 612/2013, conforme certidão de julgamento scd nº 5918071.<SEP> em razão da necessidade de formar minha convicção em torno da matéria, solicito a prorrogação do prazo de vistas, por 120 (cento e vinte) dias, conforme previsão constante do art. 16, § 1º do regimento interno.')
        
        conclusao_expected = remove_sep_token('solicito a prorrogação do prazo de vistas, por 120 (cento e vinte) dias, com fundamento no art. 16, § 1º do regimento interno.')

        assert (preambulo.strip() == preambulo_expected_1) or (preambulo.strip() == preambulo_expected_2)
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

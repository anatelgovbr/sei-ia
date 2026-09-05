"""Gerador dos fixtures sinteticos de split_section.

Os .html deste diretorio sao sinteticos (nao sao documentos reais do SEI -
tests/unit/mocks/split_section/ nunca foi commitado, ver .gitignore). Este
script documenta como foram construidos e permite regenera-los caso
SECTIONS_DICTIONARY mude. Roda uma vez, imprime o create_sections()
resultante (usado pra preencher os *_expected em test_split_section_with_mocks.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from jobs.dags.preprocessing.sections_dictionary import SECTIONS_DICTIONARY  # noqa: E402
from jobs.dags.preprocessing.split_section2 import SplitSection  # noqa: E402
from jobs.dags.preprocessing.text_clean import remove_sep_token  # noqa: E402

HERE = Path(__file__).parent

DESPACHO = """<html><body>
<p>DESPACHO DECISORIO No 99/2026/SEI/TESTE</p>
<p>Processo no 00000.000000/0000-00</p>
<p>Interessado: Empresa Teste de Telecomunicacoes Ltda</p>
<p>O Superintendente de Fiscalizacao, no uso de suas atribuicoes legais, examinando os autos do processo em epigrafe, instaurado em desfavor da empresa teste de telecomunicacoes ltda;</p>
<p>DECIDE</p>
<p>Aplicar advertencia a prestadora pelo descumprimento verificado no relatorio de fiscalizacao.</p>
<p>Fica concedido o prazo de 10 dias para interposicao de recurso administrativo.</p>
</body></html>"""

DESPACHO_SINGLE_PARAGRAPH = """<html><body>
<p>DESPACHO DECISORIO No 5/2026/SEI/TESTE - Processo no 00000.000000/0000-00</p>
<p>DECIDE conceder o prazo de 5 dias para cumprimento da obrigacao pendente, sob pena de aplicacao de multa.</p>
<p>Publique-se e cumpra-se.</p>
</body></html>"""

ANALISE = """<html><body>
<p>Análise no 12/2026/SEI/TESTE</p>
<p>Processo no 00000.000000/0000-00</p>
<p>CONSELHEIRO</p>
<p>Fulano de Tal</p>
<p>ASSUNTO</p>
<p>Recurso administrativo contra despacho decisorio que negou provimento ao pedido de restabelecimento.</p>
<p>EMENTA</p>
<p>Superintendencia de teste. Direito de peticao. Recebimento como recurso administrativo.</p>
<p>REFERÊNCIAS</p>
<p>Regimento interno da anatel, aprovado pela resolucao no 612, de 29 de abril de 2013.</p>
<p>RELATÓRIO</p>
<p>Trata-se de analise da peticao protocolizada sob sei no 1234567, apresentada pela prestadora contra o despacho decisorio.</p>
<p>CONCLUSÃO</p>
<p>Propoe-se o conhecimento e nao provimento do recurso, mantendo-se a decisao recorrida em todos os seus termos.</p>
</body></html>"""

ACORDAO = """<html><body>
<p>Acórdão no 30/2026/SEI/TESTE</p>
<p>Processo no 00000.000000/0000-00</p>
<p>EMENTA</p>
<p>Superintendencia de teste. Aprovacao de regulamento. Recurso administrativo conhecido e nao provido.</p>
<p>ACÓRDÃO</p>
<p>Vistos, relatados e discutidos os presentes autos, acordam os membros do conselho diretor da anatel, por unanimidade, aprovar o regulamento nos termos da minuta anexa.</p>
<p>Participaram da deliberacao o presidente e os conselheiros presentes a sessao.</p>
</body></html>"""

INFORME = """<html><body>
<p>Informe no 40/2026/SEI/TESTE</p>
<p>Processo no 00000.000000/0000-00</p>
<p>ASSUNTO</p>
<p>Informe de primeira instancia. Aplicacao de sancao. Procedimento para apuracao de descumprimento de obrigacoes.</p>
<p>REFERÊNCIAS</p>
<p>Regulamento do servico, aprovado pela resolucao no 272, de 9 de agosto de 2001.</p>
<p>ANÁLISE</p>
<p>A prestadora foi notificada e nao apresentou defesa no prazo regulamentar estabelecido pela norma vigente.</p>
<p>ANEXOS</p>
<p>Anexo I - relatorio de fiscalizacao. Anexo II - planilha de calculo de multa.</p>
<p>CONCLUSÃO</p>
<p>Propoe-se a aplicacao de multa a prestadora no valor de mil reais, em razao do descumprimento verificado.</p>
</body></html>"""

VOTO = """<html><body>
<p>Voto no 50/2026/SEI/TESTE</p>
<p>Processo no 00000.000000/0000-00</p>
<p>CONSELHEIRO</p>
<p>Fulano de Tal</p>
<p>ASSUNTO</p>
<p>Analise de peticao recebida como recurso administrativo contra despacho decisorio que negou provimento ao pedido.</p>
<p>EMENTA</p>
<p>Superintendencia de teste. Direito de peticao. Pedido de prorrogacao de prazo de vistas.</p>
<p>REFERÊNCIAS</p>
<p>Regimento interno da anatel, aprovado pela resolucao no 612, de 29 de abril de 2013.</p>
<p>DAS CONSIDERAÇÕES DESTE CONSELHEIRO</p>
<p>Registro minha concordancia com os fundamentos apresentados na analise que instrui os presentes autos.</p>
<p>DOS FATOS</p>
<p>Trata-se de recurso administrativo apresentado pela prestadora contra o despacho decisorio de primeira instancia.</p>
<p>RELATÓRIO</p>
<p>Trata-se de analise da peticao protocolizada sob sei no 7654321, recebida como recurso administrativo pela prestadora.</p>
<p>CONCLUSÃO</p>
<p>Solicito a prorrogacao do prazo de vistas, por 60 dias, com fundamento no regimento interno da anatel.</p>
</body></html>"""

FILES = {
    # despacho
    "splitsectioninput_243264_4_0.html": DESPACHO,
    "splitsectioninput_243264_4_0_dc.html": DESPACHO,
    "splitsectioninput_1905531_4_0.html": DESPACHO_SINGLE_PARAGRAPH,
    "splitsectioninput_1905531_4_0_dc.html": DESPACHO_SINGLE_PARAGRAPH,
    # analise (doc type 7)
    "splitsectioninput_3839143_7_0.html": ANALISE,
    "splitsectioninput_3839143_7_0_dc.html": ANALISE,
    "splitsectioninput_422762_7_1.html": ANALISE,
    "splitsectioninput_422762_7_1_dc.html": ANALISE,
    "splitsectioninput_422762_7_0.html": ANALISE,
    "splitsectioninput_422762_7_0_dc.html": ANALISE,
    # acordao (doc type 8)
    "splitsectioninput_397413_8_0.html": ACORDAO,
    "splitsectioninput_397413_8_0_dc.html": ACORDAO,
    "splitsectioninput_397413_8_1.html": ACORDAO,
    "splitsectioninput_397413_8_1_dc.html": ACORDAO,
    "splitsectioninput_422762_8_0.html": ACORDAO,
    "splitsectioninput_422762_8_0_dc.html": ACORDAO,
    "splitsectioninput_422762_8_1.html": ACORDAO,
    "splitsectioninput_422762_8_1_dc.html": ACORDAO,
    "splitsectioninput_422762_8_2.html": ACORDAO,
    "splitsectioninput_422762_8_2_dc.html": ACORDAO,
    "splitsectioninput_433260_8_0.html": ACORDAO,
    "splitsectioninput_433260_8_0_dc.html": ACORDAO,
    "splitsectioninput_433260_8_1.html": ACORDAO,
    "splitsectioninput_433260_8_1_dc.html": ACORDAO,
    "splitsectioninput_3839143_8_0.html": ACORDAO,
    "splitsectioninput_3839143_8_0_dc.html": ACORDAO,
    "splitsectioninput_3839143_8_1.html": ACORDAO,
    "splitsectioninput_3839143_8_1_dc.html": ACORDAO,
    # informe (doc type 16)
    "splitsectioninput_243264_16_0.html": INFORME,
    "splitsectioninput_243264_16_0_dc.html": INFORME,
    "splitsectioninput_243264_16_2.html": INFORME,
    "splitsectioninput_243264_16_2_dc.html": INFORME,
    # voto (doc type 94)
    "splitsectioninput_3817545_94_0.html": VOTO,
    "splitsectioninput_3817545_94_0_dc.html": VOTO,
}


def main():
    for name, content in FILES.items():
        (HERE / name).write_text(content, encoding="utf-8")

    for label, html, sections_key in [
        ("despacho", DESPACHO, "despacho"),
        ("analise", ANALISE, "analise"),
        ("acordao", ACORDAO, "acordao"),
        ("informe", INFORME, "informe"),
        ("voto", VOTO, "voto"),
    ]:
        print(f"=== {label} ===")
        result = SplitSection(html=html, html_sections=SECTIONS_DICTIONARY[sections_key]).create_sections()
        for k, v in result.items():
            print(f"{k}_expected = {remove_sep_token(v).strip()!r}")
        print()


if __name__ == "__main__":
    main()

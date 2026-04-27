"""sections_dictionary module."""

from collections import OrderedDict

SECTIONS_DICTIONARY = {
    "acordao": OrderedDict([("ementa", ["EMENTA"]), ("acordao", ["ACÓRDÃO"])]),
    "analise": OrderedDict(
        [
            ("conselheiro", ["CONSELHEIRO"]),
            ("assunto", ["ASSUNTO"]),
            ("ementa", ["EMENTA"]),
            ("referencias", ["REFERÊNCIA", "REFERÊNCIAS"]),
            ("relatorio", ["RELATÓRIO"]),
            ("conclusao", ["CONCLUSÃO"]),
        ]
    ),
    "despacho": OrderedDict(
        [("decide", ["DECIDE", "D E C I D E", "RESOLVE", "INFORMA"])]
    ),
    "informe": OrderedDict(
        [
            ("assunto", ["ASSUNTO"]),
            ("referencias", ["REFERÊNCIA", "REFERÊNCIAS", "REFERENCIAS", "REFERÊNCAS"]),
            ("analise", ["ANÁLISE", "DA ANÁLISE"]),
            (
                "anexos",
                [
                    "ANEXO",
                    "ANEXOS",
                    "RELACIONADOS/ANEXOS",
                    "RELAÇÃO DE REFERENCIADOS/ANEXOS",
                    "DOCUMENTO RELACIONADO/ANEXO",
                    "DOCUMENTOS ANEXOS",
                    "DOCUMENTOS EM ANEXO",
                    "DOCUMENTOS RELACIONADOS/ANEXOS",
                    "RELAÇÃO DE ANEXO",
                    "DOCUMENTOS RELACIONADO/ANEXO",
                    "DOCUMENTOS RELACIONADOS",
                ],
            ),
            ("conclusao", ["CONCLUSÃO", "CONCLUSÂO", "DA conclusão"]),
        ]
    ),
    "voto": OrderedDict(
        [
            ("conselheiro", ["CONSELHEIRO", "PRESIDENTE"]),
            ("assunto", ["ASSUNTO"]),
            ("ementa", ["EMENTA"]),
            ("referencias", ["REFERÊNCIA", "REFERÊNCIAS"]),
            (
                "consideracoes",
                [
                    "DAS CONSIDERAÇÕES DESTE CONSELHEIRO",
                    "DAS CONSIDERAÇÕES DO CONSELHEIRO",
                    "DAS CONSIDERAÇÕES POR PARTE DESTE PRESIDENTE",
                    "DAS CONSIDERAÇÕES POR PARTE DO CONSELHEIRO PRESIDENTE",
                    "DAS CONSIDERAÇÕES POR PARTE DO PRESIDENTE",
                    "DAS CONSIDERAÇÕES POR PARTE DESTE CONSELHEIRO",
                    "DAS CONSIDERAÇÕES POR PARTE DESTE GABINETE",
                ],
            ),
            ("dos_fatos", ["DOS FATOS"]),
            ("relatorio", ["RELATÓRIO"]),
            ("conclusao", ["CONCLUSÃO"]),
        ]
    ),
}

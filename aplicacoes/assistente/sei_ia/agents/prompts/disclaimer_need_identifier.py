"""Prompts para o identificador de necessidade de adição de disclaimer."""

DICT_DISCLAIMER_CASES = {
    "orientacao_sobre_uso_do_sei": (
        "Pergunta ou solicitação cuja "
        "resposta envolve principalmente orientações ou instruções "
        "sobre o uso do Sistema Eletrônico de Informações (SEI)."
    ),
    "totalidade_do_sei": (
        "Pergunta ou solicitação cuja resposta depende da "
        "definição de um subconjunto dos documentos e processos contidos no "
        "Sistema Eletrônico de Informações (SEI), mas os elementos "
        "necessários para esta definição não foram fornecidos pelo usuário. "
        "Inclui, por exemplo, perguntas cujas respostas enquadram-se no "
        "modelo 'Os documentos no Sistema Eletrônico de Informações (SEI) com "
        "a característica X são Y e Z'."
    ),
    "fora_do_escopo_tecnologico": (
        "Pergunta ou solicitação cuja "
        "resposta depende (i) do processamento de dados não-textuais "
        "fornecidos pelo usuário, como arquivos de áudio, vídeos ou "
        "imagens; ou (ii) de extração de caracteres por meio de OCR "
        "(optical character recognition)"
    ),
    "outro": (
        "Pergunta ou solicitação que não se enquadra em nenhum "
        "dos casos definidos acima."
    ),
}

PONDER_DISCLAIMER_ADDITION_PROMPT = """Responda apenas com um JSON
válido (sem markdown e sem comentários).
Campos obrigatórios: "justificativa" e "caso".
A chave "caso" deve ser exatamente uma destas quatro opções:
orientacao_sobre_uso_do_sei, totalidade_do_sei,
fora_do_escopo_tecnologico, outro.

Exemplo de formato esperado:
{{"justificativa": "texto da justificativa do motivo da seleção", "caso": "totalidade_do_sei"}}

O número do documento está sempre indicado por #numero_do_documento.
Identifique a intenção do usuário considerando as descrições abaixo:
{intentions}

Pergunta do usuário:
{prompt}
"""

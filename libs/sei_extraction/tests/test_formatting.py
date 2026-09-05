from __future__ import annotations

from sei_extraction.formatting import format_email_with_attachments


def test_corpo_sem_anexos():
    out = format_email_with_attachments("corpo do email", [])
    assert (
        out
        == "[conteudo_principal_do_email]\ncorpo do email\n[/conteudo_principal_do_email]\n"
    )


def test_corpo_none_vira_vazio():
    out = format_email_with_attachments(None, [])
    assert "[conteudo_principal_do_email]\n\n[/conteudo_principal_do_email]" in out


def test_anexos_em_blocos():
    out = format_email_with_attachments(
        "corpo",
        [(1, "nota.pdf", "texto da nota"), (2, "planilha.xlsx", "texto da planilha")],
    )
    assert "[anexo_1 - nota.pdf]\ntexto da nota\n[/anexo_1 - nota.pdf]" in out
    assert (
        "[anexo_2 - planilha.xlsx]\ntexto da planilha\n[/anexo_2 - planilha.xlsx]"
        in out
    )


def test_label_com_colchetes_e_normalizado():
    out = format_email_with_attachments("x", [(1, "a [b] c.pdf", "t")])
    assert "[anexo_1 - a (b) c.pdf]" in out
    assert "]\nt\n[/anexo_1 - a (b) c.pdf]" in out

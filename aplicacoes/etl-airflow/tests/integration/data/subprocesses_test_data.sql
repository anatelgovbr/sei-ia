SELECT

    d.id_documento AS d_id_documento,
    d.id_serie AS d_id_serie,
    d.id_procedimento AS d_id_procedimento,
    d.sin_bloqueado AS d_sin_bloqueado,
    d.sta_documento AS d_sta_documento,
    dc.id_documento AS dc_id_documento,
    dc.conteudo AS dc_conteudo,
    dc.conteudo_assinatura AS dc_conteudo_assinatura,
    sd.id_documento AS sd_id_documento,
    sd.id_secao_documento AS sd_id_secao_documento,
    sd.sin_principal AS sd_sin_principal,
    vsd.id_versao_secao_documento AS vsd_id_versao_secao_documento,
    vsd.id_secao_documento AS vsd_id_secao_documento,
    vsd.conteudo AS vsd_conteudo,
    vsd.sin_ultima AS vsd_sin_ultima,
    p.id_protocolo AS p_id_protocolo,
    p.protocolo_formatado AS p_protocolo_formatado,
    p.descricao AS p_descricao,
    p.id_unidade_geradora AS p_id_unidade_geradora,
    p.dta_inclusao AS p_dta_inclusao,
    p.sta_protocolo AS p_sta_protocolo,
    p.sta_estado AS p_sta_estado,
    u_p.id_unidade AS u_p_id_unidade,
    u_p.sigla AS u_p_sigla,
    s.id_serie AS s_id_serie,
    s.nome AS s_nome,
    s.descricao AS s_descricao,
    asntr.id_documento AS asntr_id_documento,
    asntr.id_atividade AS asntr_id_atividade,
    asntr.id_assinatura AS asntr_id_assinatura,
    atv.id_atividade AS atv_id_atividade,
    atv.dth_conclusao AS atv_dth_conclusao,
    pr.id_procedimento AS pr_id_procedimento,
    pr.id_tipo_procedimento AS pr_id_tipo_procedimento,
    tp.id_tipo_procedimento AS tp_id_tipo_procedimento,
    tp.nome AS tp_nome,
    tp.descricao AS tp_descricao,
    rpp.id_rel_protocolo_protocolo AS rpp_id_rel_protocolo_protocolo,
    rpp.id_protocolo_1 AS rpp_id_protocolo_1,
    rpp.id_protocolo_2 AS rpp_id_protocolo_2,
    rpp.sta_associacao AS rpp_sta_associacao,
    p_pai.id_protocolo AS p_pai_id_protocolo,
    p_pai.protocolo_formatado AS p_pai_protocolo_formatado,
    p_pai.descricao AS p_pai_descricao,
    p_pai.id_unidade_geradora AS p_pai_id_unidade_geradora,
    p_pai.dta_inclusao AS p_pai_dta_inclusao,
    p_pai.sta_protocolo AS p_pai_sta_protocolo,
    p_pai.sta_estado AS p_pai_sta_estado,
    u_p_pai.id_unidade AS u_p_pai_id_unidade,
    u_p_pai.sigla AS u_p_pai_sigla,
    pa.id_participante AS pa_id_participante,
    pa.id_protocolo AS pa_id_protocolo,
    pa.id_contato AS pa_id_contato,
    pa.sta_participacao AS pa_sta_participacao,
    ct.id_contato AS ct_id_contato,
    ct.nome AS ct_nome,
    rpp3as1.id_rel_protocolo_protocolo AS rpp3as1_id_rel_protocolo_protocolo,
    rpp3as1.id_protocolo_1 AS rpp3as1_id_protocolo_1, 
    rpp3as1.id_protocolo_2 AS rpp3as1_id_protocolo_2,
    rpp3as1.sta_associacao AS rpp3as1_sta_associacao,
    rpp3as12.id_protocolo AS rpp3as12_id_protocolo,
    rpp3as12.protocolo_formatado AS rpp3as12_protocolo_formatado,
    rpp3as12.descricao AS rpp3as12_descricao,
    rpp3as12.id_unidade_geradora AS rpp3as12_id_unidade_geradora,
    rpp3as12.dta_inclusao AS rpp3as12_dta_inclusao,
    rpp3as12.sta_protocolo AS rpp3as12_sta_protocolo,
    rpp3as12.sta_estado AS rpp3as12_sta_estado,
    u_rpp3as12.id_unidade AS u_rpp3as12_id_unidade,
    u_rpp3as12.sigla AS u_rpp3as12_sigla,
    rpp3as2.id_rel_protocolo_protocolo AS rpp3as2_id_rel_protocolo_protocolo,
    rpp3as2.id_protocolo_1 AS rpp3as2_id_protocolo_1, 
    rpp3as2.id_protocolo_2 AS rpp3as2_id_protocolo_2,
    rpp3as2.sta_associacao AS rpp3as2_sta_associacao,
    rpp3as21.id_protocolo AS rpp3as21_id_protocolo,
    rpp3as21.protocolo_formatado AS rpp3as21_protocolo_formatado,
    rpp3as21.descricao AS rpp3as21_descricao,
    rpp3as21.id_unidade_geradora AS rpp3as21_id_unidade_geradora,
    rpp3as21.dta_inclusao AS rpp3as21_dta_inclusao,
    rpp3as21.sta_protocolo AS rpp3as21_sta_protocolo,
    rpp3as21.sta_estado AS rpp3as21_sta_estado,
    u_rpp3as21.id_unidade AS u_rpp3as21_id_unidade,
    u_rpp3as21.sigla AS u_rpp3as21_sigla,
    rpp2as1.id_rel_protocolo_protocolo AS rpp2as1_id_rel_protocolo_protocolo,
    rpp2as1.id_protocolo_1 AS rpp2as1_id_protocolo_1, 
    rpp2as1.id_protocolo_2 AS rpp2as1_id_protocolo_2,
    rpp2as1.sta_associacao AS rpp2as1_sta_associacao,
    rpp2as12.id_protocolo AS rpp2as12_id_protocolo,
    rpp2as12.protocolo_formatado AS rpp2as12_protocolo_formatado,
    rpp2as12.descricao AS rpp2as12_descricao,
    rpp2as12.id_unidade_geradora AS rpp2as12_id_unidade_geradora,
    rpp2as12.dta_inclusao AS rpp2as12_dta_inclusao,
    rpp2as12.sta_protocolo AS rpp2as12_sta_protocolo,
    rpp2as12.sta_estado AS rpp2as12_sta_estado,
    u_rpp2as12.id_unidade AS u_rpp2as12_id_unidade,
    u_rpp2as12.sigla AS u_rpp2as12_sigla
FROM documento d 
LEFT JOIN
    documento_conteudo as dc
    ON dc.id_documento = d.id_documento
LEFT JOIN
    secao_documento as sd
    ON sd.id_documento = d.id_documento
LEFT JOIN
    versao_secao_documento as vsd
    on vsd.id_secao_documento = sd.id_secao_documento
INNER JOIN
    protocolo p
    ON d.id_documento = p.id_protocolo
LEFT JOIN
    unidade u_p
    ON u_p.id_unidade = p.id_unidade_geradora
INNER JOIN
    serie s
    ON d.id_serie = s.id_serie
LEFT JOIN 
    assinatura asntr 
    on asntr.id_documento = d.id_documento 
LEFT JOIN 
    atividade atv 
    on asntr.id_atividade = atv.id_atividade
LEFT JOIN
    procedimento pr
    ON d.id_procedimento = pr.id_procedimento
LEFT JOIN
    tipo_procedimento tp
    ON pr.id_tipo_procedimento = tp.id_tipo_procedimento
LEFT JOIN
    rel_protocolo_protocolo rpp
    ON p.id_protocolo = rpp.id_protocolo_2
LEFT JOIN
    protocolo p_pai
    ON rpp.id_protocolo_1 = p_pai.id_protocolo
LEFT JOIN
    unidade u_p_pai
    ON u_p_pai.id_unidade = p_pai.id_unidade_geradora
LEFT JOIN
    (SELECT id_participante,id_protocolo, id_contato, sta_participacao FROM participante WHERE sta_participacao="I") pa
    ON p_pai.id_protocolo = pa.id_protocolo
LEFT JOIN
    contato ct
    ON pa.id_contato = ct.id_contato
LEFT JOIN
    (SELECT id_rel_protocolo_protocolo,id_protocolo_1, id_protocolo_2,sta_associacao FROM rel_protocolo_protocolo WHERE sta_associacao = 3 ) rpp3as1
    ON p_pai.id_protocolo = rpp3as1.id_protocolo_1
LEFT JOIN
    protocolo rpp3as12
    ON rpp3as1.id_protocolo_2 = rpp3as12.id_protocolo
LEFT JOIN
    unidade u_rpp3as12
    ON u_rpp3as12.id_unidade = rpp3as12.id_unidade_geradora
LEFT JOIN
    (SELECT id_rel_protocolo_protocolo,id_protocolo_1, id_protocolo_2,sta_associacao FROM rel_protocolo_protocolo WHERE sta_associacao = 3 ) rpp3as2
    ON p_pai.id_protocolo = rpp3as2.id_protocolo_2
LEFT JOIN
    protocolo rpp3as21
    ON rpp3as2.id_protocolo_1 = rpp3as21.id_protocolo
LEFT JOIN
    unidade u_rpp3as21
    ON u_rpp3as21.id_unidade = rpp3as21.id_unidade_geradora
LEFT JOIN
    (SELECT id_rel_protocolo_protocolo,id_protocolo_1, id_protocolo_2,sta_associacao FROM rel_protocolo_protocolo WHERE sta_associacao = 2 ) rpp2as1
    ON p_pai.id_protocolo = rpp2as1.id_protocolo_1
LEFT JOIN
    protocolo rpp2as12
    ON rpp2as1.id_protocolo_2 = rpp2as12.id_protocolo
LEFT JOIN
    unidade u_rpp2as12
    ON u_rpp2as12.id_unidade = rpp2as12.id_unidade_geradora
WHERE
    p_pai.protocolo_formatado in (
        -- "53500.005769/2016-15","53500.006606/2016-50","53500.029606/2010-32","53500.046380/2018-91",
        -- "53500.039847/2021-42",
        "53500.000801/2016-76","53512.000363/2016-15","53500.005187/2016-39"
    )
    -- AND vsd.conteudo NOT LIKE '<p>Conteúdo removido.</p>'
    AND vsd.sin_ultima = 'S'
    AND sd.sin_principal = 'S'
    AND d.id_documento IS NOT NULL
    AND d.id_serie IS NOT NULL
    AND d.id_procedimento IS NOT NULL
    AND d.sin_bloqueado IS NOT NULL
    -- AND d.sta_documento IS NOT NULL
    -- AND dc.id_documento IS NOT NULL
    -- AND dc.conteudo IS NOT NULL
    -- AND dc.conteudo_assinatura IS NOT NULL
    AND sd.id_documento IS NOT NULL
    AND sd.id_secao_documento IS NOT NULL
    AND sd.sin_principal IS NOT NULL
    AND vsd.id_versao_secao_documento IS NOT NULL
    AND vsd.id_secao_documento IS NOT NULL
    -- AND vsd.conteudo IS NOT NULL
    AND vsd.sin_ultima IS NOT NULL
    AND p.id_protocolo IS NOT NULL
    AND p.protocolo_formatado IS NOT NULL
    -- AND p.descricao IS NOT NULL
    AND p.id_unidade_geradora IS NOT NULL
    AND p.dta_inclusao IS NOT NULL
    AND p.sta_protocolo IS NOT NULL
    AND p.sta_estado IS NOT NULL
    -- AND u_p.id_unidade IS NOT NULL
    -- AND u_p.sigla IS NOT NULL
    AND s.id_serie IS NOT NULL
    AND s.nome IS NOT NULL
    -- AND s.descricao IS NOT NULL
    -- AND asntr.id_documento IS NOT NULL
    -- AND asntr.id_atividade IS NOT NULL
    -- AND asntr.id_assinatura IS NOT NULL
    -- AND atv.id_atividade IS NOT NULL
    -- AND atv.dth_conclusao IS NOT NULL
    AND pr.id_procedimento IS NOT NULL
    AND pr.id_tipo_procedimento IS NOT NULL
    AND tp.id_tipo_procedimento IS NOT NULL
    AND tp.nome IS NOT NULL
    -- AND tp.descricao IS NOT NULL
    AND rpp.id_rel_protocolo_protocolo IS NOT NULL
    AND rpp.id_protocolo_1 IS NOT NULL
    AND rpp.id_protocolo_2 IS NOT NULL
    AND rpp.sta_associacao IS NOT NULL
    AND p_pai.id_protocolo IS NOT NULL
    AND p_pai.protocolo_formatado IS NOT NULL
    -- AND p_pai.descricao IS NOT NULL
    AND p_pai.id_unidade_geradora IS NOT NULL
    AND p_pai.dta_inclusao IS NOT NULL
    AND p_pai.sta_protocolo IS NOT NULL
    AND p_pai.sta_estado IS NOT NULL
    -- AND u_p_pai.id_unidade IS NOT NULL
    -- AND u_p_pai.sigla IS NOT NULL
    AND pa.id_participante IS NOT NULL
    AND pa.id_protocolo IS NOT NULL
    AND pa.id_contato IS NOT NULL
    AND pa.sta_participacao IS NOT NULL
    -- AND ct.id_contato IS NOT NULL
    -- AND ct.nome IS NOT NULL
    -- AND rpp3as1.id_rel_protocolo_protocolo IS NOT NULL
    -- AND rpp3as1.id_protocolo_1 IS NOT NULL
    -- AND rpp3as1.id_protocolo_2 IS NOT NULL
    -- AND rpp3as1.sta_associacao IS NOT NULL
    -- AND rpp3as12.id_protocolo IS NOT NULL
    -- AND rpp3as12.protocolo_formatado IS NOT NULL
    -- AND rpp3as12.descricao IS NOT NULL
    -- AND rpp3as12.id_unidade_geradora IS NOT NULL
    -- AND rpp3as12.dta_inclusao IS NOT NULL
    -- AND rpp3as12.sta_protocolo IS NOT NULL
    -- AND rpp3as12.sta_estado IS NOT NULL
    -- AND u_rpp3as12.id_unidade IS NOT NULL
    -- AND u_rpp3as12.sigla IS NOT NULL
    -- AND rpp3as2.id_rel_protocolo_protocolo IS NOT NULL
    -- AND rpp3as2.id_protocolo_1 IS NOT NULL
    -- AND rpp3as2.id_protocolo_2 IS NOT NULL
    -- AND rpp3as2.sta_associacao IS NOT NULL
    -- AND rpp3as21.id_protocolo IS NOT NULL
    -- AND rpp3as21.protocolo_formatado IS NOT NULL
    -- AND rpp3as21.descricao IS NOT NULL
    -- AND rpp3as21.id_unidade_geradora IS NOT NULL
    -- AND rpp3as21.dta_inclusao IS NOT NULL
    -- AND rpp3as21.sta_protocolo IS NOT NULL
    -- AND rpp3as21.sta_estado IS NOT NULL
    -- AND u_rpp3as21.id_unidade IS NOT NULL
    -- AND u_rpp3as21.sigla IS NOT NULL
    -- AND rpp2as1.id_rel_protocolo_protocolo IS NOT NULL
    -- AND rpp2as1.id_protocolo_1 IS NOT NULL
    -- AND rpp2as1.id_protocolo_2 IS NOT NULL
    -- AND rpp2as1.sta_associacao IS NOT NULL
    -- AND rpp2as12.id_protocolo IS NOT NULL
    -- AND rpp2as12.protocolo_formatado IS NOT NULL
    -- AND rpp2as12.descricao IS NOT NULL
    -- AND rpp2as12.id_unidade_geradora IS NOT NULL
    -- AND rpp2as12.dta_inclusao IS NOT NULL
    -- AND rpp2as12.sta_protocolo IS NOT NULL
    -- AND rpp2as12.sta_estado IS NOT NULL
    -- AND u_rpp2as12.id_unidade IS NOT NULL
    -- AND u_rpp2as12.sigla IS NOT NULL
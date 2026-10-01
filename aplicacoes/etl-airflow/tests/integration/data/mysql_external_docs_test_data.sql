SELECT
    d.id_documento AS d_id_documento,
    d.id_serie AS d_id_serie,
    d.id_procedimento AS d_id_procedimento,
    d.sin_bloqueado AS d_sin_bloqueado,
    d.sta_documento AS d_sta_documento,
    b.id_protocolo AS a_id_protocolo,
    b.nome AS a_nome,
    b.sin_ativo AS a_sin_ativo,
    b.id_anexo AS a_id_anexo,
    p.id_protocolo AS p_id_protocolo,
    p.protocolo_formatado AS p_protocolo_formatado,
    p.descricao AS p_descricao,
    p.id_unidade_geradora AS p_id_unidade_geradora,
    p.dta_inclusao AS p_dta_inclusao,
    p.sta_protocolo AS p_sta_protocolo,
    p.sta_estado AS p_sta_estado,
    u_p.id_unidade AS u_p_id_unidade,
    u_p.sigla AS u_p_sigla,
    d.id_serie AS s_id_serie,
    d.nome AS s_nome,
    d.descricao AS s_descricao,
    asntr.id_documento AS asntr_id_documento,
    asntr.id_atividade AS asntr_id_atividade,
    asntr.id_assinatura AS asntr_id_assinatura,
    atv.id_atividade AS atv_id_atividade,
    atv.dth_conclusao AS atv_dth_conclusao,
    proc.id_procedimento AS pr_id_procedimento,
    proc.id_tipo_procedimento AS pr_id_tipo_procedimento,
    proc.id_tipo_procedimento AS tp_id_tipo_procedimento,
    proc.nome AS tp_nome,
    proc.descricao AS tp_descricao,
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
    u_rpp3as21.sigla AS u_rpp3as21_sigla
 
FROM protocolo p
LEFT JOIN
    unidade u_p
    ON u_p.id_unidade = p.id_unidade_geradora
LEFT JOIN
    rel_protocolo_protocolo rpp 
    ON (rpp.id_protocolo_2 = p.id_protocolo) AND rpp.sta_associacao='1'
LEFT JOIN
    protocolo p_pai
    ON (p_pai.id_protocolo = rpp.id_protocolo_1)
LEFT JOIN
    unidade u_p_pai
    ON u_p_pai.id_unidade = p_pai.id_unidade_geradora
INNER JOIN
    anexo a
    ON (p.id_protocolo = a.id_protocolo) AND p.sta_protocolo='R'
INNER JOIN
    (SELECT id_protocolo, id_anexo, sin_ativo, nome, SUBSTRING_INDEX(nome, '.', -1) AS formato_arquivo FROM anexo WHERE sin_ativo= 'S') b
    ON b.id_anexo = a.id_anexo
INNER JOIN
    (SELECT dd.id_serie, dd.id_documento, dd.id_procedimento, dd.sin_bloqueado, dd.sta_documento, ee.nome, ee.descricao FROM documento dd INNER JOIN serie ee ON ee.id_serie = dd.id_serie) d
    ON d.id_documento = p.id_protocolo
LEFT JOIN 
    assinatura asntr 
    on asntr.id_documento = d.id_documento 
LEFT JOIN 
    atividade atv 
    on asntr.id_atividade = atv.id_atividade
INNER JOIN
    (SELECT t.nome, t.descricao, t.id_tipo_procedimento, pp.id_procedimento FROM procedimento pp INNER JOIN tipo_procedimento t ON t.id_tipo_procedimento = pp.id_tipo_procedimento) proc
    ON proc.id_procedimento = p_pai.id_protocolo
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
WHERE
    p.sta_protocolo IN ('R')
    AND formato_arquivo  IN ('txt', 'pdf','csv','xlsx', 'html', 'htm', 'xml', 'xls')
    AND p.sta_estado ='0'
    AND p_pai.protocolo_formatado IN ('53500.039847/2021-42')
    AND d.id_serie IN (3,4,5,6,7,8,10,11,12,13,14,16,17,18,19,20,21,27,29,30,32,33,35,37,38,41,42,45,46,47,49,51,53,55,57,59,62,63,64,65,67,68,70,71,73,74,76,79,80,81,82,83,84,85,90,91,92,93,94,96,99,100,101,102,103,104,105,108,109,111,112,113,115,118,120,121,122,126,130,131,133,137,143,145,146,150,159,160,164,165,166,169,170,171,174,176,178,179,183,184,185,186,187,188,191,197,200,204,206,207,214,215,216,218,219,220,226,227,229,230,235,237,238,239,244,245,246,252,254,255,256,258,260,261,267,270,272,273,276,277,278,279,280,281,282,286,288,290,292,293,298,299,300,306,307,311,313,314,320,321,327,330,331,333,337,340,341,342,343,345,352,353,354,355,356,357,362,364,365,369,370,371,374,380,430,431,432,433,444,445,450,453,454,456,466,487,488,497,498,499,500,507)
    AND d.id_documento IS NOT NULL
    AND d.id_serie IS NOT NULL
    AND d.id_procedimento IS NOT NULL
    AND d.sin_bloqueado IS NOT NULL
    -- AND d.sta_documento IS NOT NULL
    AND b.id_protocolo IS NOT NULL
    AND b.nome IS NOT NULL
    AND b.sin_ativo IS NOT NULL
    AND b.id_anexo IS NOT NULL
    AND p.id_protocolo IS NOT NULL
    AND p.protocolo_formatado IS NOT NULL
    AND p.descricao IS NOT NULL
    AND p.id_unidade_geradora IS NOT NULL
    AND p.dta_inclusao IS NOT NULL
    AND p.sta_protocolo IS NOT NULL
    AND p.sta_estado IS NOT NULL
    -- AND u_p.id_unidade IS NOT NULL
    -- AND u_p.sigla IS NOT NULL
    -- AND d.id_serie IS NOT NULL
    AND d.nome IS NOT NULL
    AND d.descricao IS NOT NULL
    -- AND asntr.id_documento IS NOT NULL
    -- AND asntr.id_atividade IS NOT NULL
    -- AND asntr.id_assinatura IS NOT NULL
    -- AND atv.id_atividade IS NOT NULL
    -- AND atv.dth_conclusao IS NOT NULL
    AND proc.id_procedimento IS NOT NULL
    AND proc.id_tipo_procedimento IS NOT NULL
    -- AND proc.id_tipo_procedimento IS NOT NULL
    AND proc.nome IS NOT NULL
    AND proc.descricao IS NOT NULL
    AND rpp.id_rel_protocolo_protocolo IS NOT NULL
    AND rpp.id_protocolo_1 IS NOT NULL
    AND rpp.id_protocolo_2 IS NOT NULL
    AND rpp.sta_associacao IS NOT NULL
    AND p_pai.id_protocolo IS NOT NULL
    AND p_pai.protocolo_formatado IS NOT NULL
    AND p_pai.descricao IS NOT NULL
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
    AND rpp3as1.id_rel_protocolo_protocolo IS NOT NULL
    AND rpp3as1.id_protocolo_1 IS NOT NULL
    AND rpp3as1.id_protocolo_2 IS NOT NULL
    AND rpp3as1.sta_associacao IS NOT NULL
    AND rpp3as12.id_protocolo IS NOT NULL
    AND rpp3as12.protocolo_formatado IS NOT NULL
    AND rpp3as12.descricao IS NOT NULL
    AND rpp3as12.id_unidade_geradora IS NOT NULL
    AND rpp3as12.dta_inclusao IS NOT NULL
    AND rpp3as12.sta_protocolo IS NOT NULL
    AND rpp3as12.sta_estado IS NOT NULL
    -- AND u_rpp3as12.id_unidade IS NOT NULL
    -- AND u_rpp3as12.sigla IS NOT NULL
    AND rpp3as2.id_rel_protocolo_protocolo IS NOT NULL
    AND rpp3as2.id_protocolo_1 IS NOT NULL
    AND rpp3as2.id_protocolo_2 IS NOT NULL
    AND rpp3as2.sta_associacao IS NOT NULL
    AND rpp3as21.id_protocolo IS NOT NULL
    AND rpp3as21.protocolo_formatado IS NOT NULL
    AND rpp3as21.descricao IS NOT NULL
    AND rpp3as21.id_unidade_geradora IS NOT NULL
    AND rpp3as21.dta_inclusao IS NOT NULL
    AND rpp3as21.sta_protocolo IS NOT NULL
    AND rpp3as21.sta_estado IS NOT NULL
    -- AND u_rpp3as21.id_unidade IS NOT NULL
    -- AND u_rpp3as21.sigla IS NOT NULL
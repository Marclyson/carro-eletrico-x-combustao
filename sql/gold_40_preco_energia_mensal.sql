CREATE OR REPLACE TABLE gold_preco_energia_mensal AS
WITH meses AS (
    SELECT mes FROM gold_dim_tempo
),
ufs AS (
    SELECT uf, CAST(cnpj AS BIGINT) AS cnpj
    FROM read_csv('referencias/distribuidora_capital.csv')
),
tributos AS (
    SELECT
        tributo,
        produto,
        inicio,
        coalesce(fim, DATE '9999-12-31') AS fim,
        CAST(valor AS DOUBLE) AS valor
    FROM read_csv('referencias/tributos_combustivel.csv')
),
alvo AS (
    SELECT m.mes, u.uf, u.cnpj, m.mes + INTERVAL 14 DAY AS dia
    FROM meses m
    CROSS JOIN ufs u
),
gasolina_tributos AS (
    SELECT
        a.mes,
        a.uf,
        pf.valor * fr.valor AS pis_cofins_unit,
        cf.valor * fr.valor AS cide_unit,
        ic.valor AS icms_unit
    FROM alvo a
    JOIN tributos pf
      ON pf.tributo = 'pis_cofins' AND pf.produto = 'gasolina_a'
     AND pf.inicio <= a.dia AND pf.fim >= a.dia
    JOIN tributos cf
      ON cf.tributo = 'cide' AND cf.produto = 'gasolina_a'
     AND cf.inicio <= a.dia AND cf.fim >= a.dia
    JOIN tributos fr
      ON fr.tributo = 'fracao_gasolina_a' AND fr.produto = 'gasolina_c'
     AND fr.inicio <= a.dia AND fr.fim >= a.dia
    LEFT JOIN tributos ic
      ON ic.tributo = 'icms_ad_rem' AND ic.produto = 'gasolina_c'
     AND ic.inicio <= a.dia AND ic.fim >= a.dia
),
etanol_tributos AS (
    SELECT
        a.mes,
        a.uf,
        pf.valor AS pis_cofins_unit,
        cf.valor AS cide_unit
    FROM alvo a
    JOIN tributos pf
      ON pf.tributo = 'pis_cofins' AND pf.produto = 'etanol_hidratado'
     AND pf.inicio <= a.dia AND pf.fim >= a.dia
    JOIN tributos cf
      ON cf.tributo = 'cide' AND cf.produto = 'etanol_hidratado'
     AND cf.inicio <= a.dia AND cf.fim >= a.dia
),
gasolina AS (
    SELECT
        p.mes,
        p.uf,
        'gasolina' AS energia,
        p.preco_medio AS preco,
        'R$/l' AS unidade,
        gt.icms_unit,
        gt.pis_cofins_unit,
        gt.cide_unit,
        p.preco_medio - gt.pis_cofins_unit - gt.cide_unit - coalesce(gt.icms_unit, 0) AS preco_sem_tributos,
        FALSE AS icms_imputado,
        FALSE AS tarifa_imputada
    FROM silver_precos_combustivel p
    JOIN meses m ON m.mes = p.mes
    JOIN ufs u ON u.uf = p.uf
    JOIN gasolina_tributos gt ON gt.mes = p.mes AND gt.uf = p.uf
    WHERE p.produto = 'gasolina_c'
),
etanol AS (
    SELECT
        p.mes,
        p.uf,
        'etanol' AS energia,
        p.preco_medio AS preco,
        'R$/l' AS unidade,
        NULL AS icms_unit,
        et.pis_cofins_unit,
        et.cide_unit,
        p.preco_medio - et.pis_cofins_unit - et.cide_unit AS preco_sem_tributos,
        FALSE AS icms_imputado,
        FALSE AS tarifa_imputada
    FROM silver_precos_combustivel p
    JOIN meses m ON m.mes = p.mes
    JOIN ufs u ON u.uf = p.uf
    JOIN etanol_tributos et ON et.mes = p.mes AND et.uf = p.uf
    WHERE p.produto = 'etanol_hidratado'
),
eletricidade_base AS (
    SELECT
        t.cnpj,
        t.mes,
        u.uf,
        t.tarifa_kwh + coalesce(b.adicional_kwh, 0) AS base,
        coalesce(a.icms, 0) AS icms,
        coalesce(a.pis_cofins, 0) AS pis_cofins,
        coalesce(a.imputado, FALSE) AS imputado,
        t.fonte_tarifa = 'samp' AS tarifa_imputada
    FROM silver_tarifa_mensal t
    JOIN meses m ON m.mes = t.mes
    JOIN ufs u ON u.cnpj = t.cnpj
    LEFT JOIN silver_bandeira b ON b.mes = t.mes
    LEFT JOIN silver_aliquota_energia a ON a.cnpj = t.cnpj AND a.mes = t.mes
),
eletricidade AS (
    SELECT
        mes,
        uf,
        'eletricidade' AS energia,
        preco_com_imposto(base, icms, pis_cofins) AS preco,
        'R$/kWh' AS unidade,
        preco_com_imposto(base, icms, pis_cofins) * icms AS icms_unit,
        preco_com_imposto(base, icms, pis_cofins) * pis_cofins AS pis_cofins_unit,
        0 AS cide_unit,
        base AS preco_sem_tributos,
        imputado AS icms_imputado,
        tarifa_imputada
    FROM eletricidade_base
)
SELECT mes, uf, energia, preco, unidade, icms_unit, pis_cofins_unit, cide_unit, preco_sem_tributos,
       icms_imputado, tarifa_imputada
FROM gasolina
UNION ALL
SELECT mes, uf, energia, preco, unidade, icms_unit, pis_cofins_unit, cide_unit, preco_sem_tributos,
       icms_imputado, tarifa_imputada
FROM etanol
UNION ALL
SELECT mes, uf, energia, preco, unidade, icms_unit, pis_cofins_unit, cide_unit, preco_sem_tributos,
       icms_imputado, tarifa_imputada
FROM eletricidade;

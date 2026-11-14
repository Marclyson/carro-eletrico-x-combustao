-- A Receita Energia do SAMP já inclui o adicional da bandeira; por isso Receita Bandeiras não entra no total.
CREATE OR REPLACE TABLE silver_aliquota_energia AS
WITH distribuidoras AS (
    SELECT CAST(cnpj AS BIGINT) AS cnpj
    FROM read_csv('referencias/distribuidora_capital.csv')
),
ultimo_mes AS (
    SELECT max(DatCompetencia) AS mes
    FROM bronze_samp
),
meses AS (
    SELECT
        d.cnpj,
        CAST(g.generate_series AS DATE) AS mes
    FROM distribuidoras d
    CROSS JOIN ultimo_mes u
    CROSS JOIN generate_series(DATE '2012-01-01', u.mes, INTERVAL 1 MONTH) AS g
),
samp_recente AS (
    SELECT *
    FROM bronze_samp
    QUALIFY row_number() OVER (
        PARTITION BY _hash_linha
        ORDER BY _data_extracao DESC
    ) = 1
),
agregado AS (
    SELECT
        NumCNPJAgenteDistribuidora AS cnpj,
        DatCompetencia AS mes,
        coalesce(sum(CASE WHEN DscDetalheMercado = 'ICMS (R$)' THEN VlrMercado END), 0) AS icms,
        coalesce(sum(CASE WHEN DscDetalheMercado = 'Receita Energia (R$)' THEN VlrMercado END), 0)
            AS receita_energia,
        coalesce(sum(CASE WHEN DscDetalheMercado = 'Receita Bandeiras (R$)' THEN VlrMercado END), 0)
            AS receita_bandeiras,
        coalesce(sum(CASE WHEN DscDetalheMercado = 'PIS/PASEP (R$)' THEN VlrMercado END), 0) AS pis,
        coalesce(sum(CASE WHEN DscDetalheMercado = 'COFINS (R$)' THEN VlrMercado END), 0) AS cofins,
        coalesce(sum(CASE WHEN DscDetalheMercado = 'PIS/COFINS (R$)' THEN VlrMercado END), 0) AS pis_cofins
    FROM samp_recente
    WHERE DscSubClasseConsumidor = 'Residencial'
      AND NomTipoMercado IN ('Regular', 'Sistema Isolado - Regular')
      AND upper(DscOpcaoEnergia) = 'CATIVO'
    GROUP BY 1, 2
),
brutos AS (
    SELECT
        cnpj,
        mes,
        CASE WHEN icms <> 0 AND total <> 0 THEN icms / total END AS icms_bruto,
        CASE WHEN total <> 0 THEN (pis + cofins + pis_cofins) / total END AS pis_cofins_bruto
    FROM (
        SELECT
            a.*,
            a.icms + a.receita_energia + a.pis + a.cofins + a.pis_cofins AS total
        FROM agregado a
    )
),
validos AS (
    SELECT
        b.cnpj,
        b.mes,
        b.icms_bruto,
        b.pis_cofins_bruto,
        CASE
            WHEN b.icms_bruto IS NULL THEN FALSE
            WHEN b.icms_bruto < 0.05 OR b.icms_bruto > 0.40 THEN FALSE
            WHEN b.pis_cofins_bruto IS NULL OR b.pis_cofins_bruto < 0 OR b.pis_cofins_bruto > 0.15 THEN FALSE
            ELSE (
                SELECT median(v.icms_bruto)
                FROM brutos v
                WHERE v.cnpj = b.cnpj
                  AND v.mes BETWEEN b.mes - INTERVAL 3 MONTH AND b.mes + INTERVAL 3 MONTH
                  AND v.mes <> b.mes
                  AND v.icms_bruto IS NOT NULL
            ) IS NULL
            OR abs(b.icms_bruto - (
                SELECT median(v.icms_bruto)
                FROM brutos v
                WHERE v.cnpj = b.cnpj
                  AND v.mes BETWEEN b.mes - INTERVAL 3 MONTH AND b.mes + INTERVAL 3 MONTH
                  AND v.mes <> b.mes
                  AND v.icms_bruto IS NOT NULL
            )) <= 0.05
        END AS valido
    FROM brutos b
),
validos_rows AS (
    SELECT cnpj, mes AS mes_valido, icms_bruto, pis_cofins_bruto
    FROM validos
    WHERE valido
),
candidatos AS (
    SELECT
        m.cnpj,
        m.mes,
        v.mes_valido,
        v.icms_bruto,
        v.pis_cofins_bruto
    FROM meses m
    JOIN validos_rows v ON v.cnpj = m.cnpj
),
escolhido AS (
    SELECT
        c.*,
        row_number() OVER (
            PARTITION BY c.cnpj, c.mes
            ORDER BY
                abs(date_diff('month', c.mes, c.mes_valido)),
                date_diff('month', c.mes, c.mes_valido)
        ) AS rn
    FROM candidatos c
)
SELECT
    cnpj,
    mes,
    icms_bruto AS icms,
    pis_cofins_bruto AS pis_cofins,
    (mes_valido <> mes) AS imputado
FROM escolhido
WHERE rn = 1;
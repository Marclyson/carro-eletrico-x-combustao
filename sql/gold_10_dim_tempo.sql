CREATE OR REPLACE TABLE gold_dim_tempo AS
WITH limites AS (
    SELECT
        (SELECT max(mes) FROM silver_ipca) AS ultimo_ipca,
        (SELECT max(mes) FROM silver_precos_combustivel) AS ultimo_precos,
        (
            SELECT max(mes)
            FROM (
                SELECT mes, count(*) FILTER (WHERE NOT imputado) AS nao_imputadas
                FROM silver_aliquota_energia
                GROUP BY mes
            )
            WHERE nao_imputadas >= 20
        ) AS ultimo_aliquota
),
mes_final AS (
    SELECT least(ultimo_ipca, ultimo_precos, ultimo_aliquota) AS mes
    FROM limites
),
meses AS (
    SELECT CAST(g AS DATE) AS mes
    FROM mes_final
    CROSS JOIN generate_series(DATE '2012-01-01', mes_final.mes, INTERVAL 1 MONTH) AS g
),
indice AS (
    SELECT
        m.mes,
        year(m.mes) AS ano,
        month(m.mes) AS mes_num,
        coalesce(i.variacao, 0) AS ipca_variacao,
        product(1 + coalesce(i.variacao, 0) / 100) OVER (
            ORDER BY m.mes
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS indice_ipca
    FROM meses m
    LEFT JOIN silver_ipca i USING (mes)
)
SELECT
    mes,
    ano,
    mes_num,
    ipca_variacao,
    indice_ipca,
    -- índice do último mês (não o máximo: o IPCA tem meses de deflação)
    last_value(indice_ipca) OVER (ORDER BY mes ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        / indice_ipca AS fator_real,
    s.valor AS salario_minimo
FROM indice
LEFT JOIN silver_salario_minimo s USING (mes);

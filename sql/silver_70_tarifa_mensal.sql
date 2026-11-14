-- Tarifa residencial sem impostos de cada distribuidora de capital, mês a mês, em R$/kWh.
-- Usa a tarifa homologada vigente no dia 15. A base aberta da ANEEL não tem alguns reajustes (a CEMIG não tem os de
-- 2016, 2019 e 2021, por exemplo); nesses meses entra a tarifa média do SAMP (receita de energia ÷ kWh da classe
-- residencial, sem o adicional da bandeira, que a Receita Energia inclui), que bate com a homologada (mediana da razão = 1,000 nas 27 capitais, 2012 a 2026).
CREATE OR REPLACE TABLE silver_tarifa_mensal AS
WITH distribuidoras AS (
    SELECT CAST(cnpj AS BIGINT) AS cnpj
    FROM read_csv('referencias/distribuidora_capital.csv')
),
meses AS (
    SELECT d.cnpj, CAST(g.generate_series AS DATE) AS mes
    FROM distribuidoras d
    CROSS JOIN (SELECT max(mes) AS ultimo FROM silver_ipca) u
    CROSS JOIN generate_series(DATE '2012-01-01', u.ultimo, INTERVAL 1 MONTH) AS g
),
homologada AS (
    SELECT m.cnpj, m.mes, (t.tusd_mwh + t.te_mwh) / 1000 AS tarifa_kwh
    FROM meses m
    JOIN silver_tarifa_residencial t
      ON t.cnpj = m.cnpj AND m.mes + INTERVAL 14 DAY BETWEEN t.inicio AND t.fim
    QUALIFY row_number() OVER (PARTITION BY m.cnpj, m.mes ORDER BY t.inicio DESC) = 1
),
samp AS (
    SELECT
        NumCNPJAgenteDistribuidora AS cnpj,
        DatCompetencia AS mes,
        (
            sum(CASE WHEN DscDetalheMercado = 'Receita Energia (R$)' THEN VlrMercado END)
            - coalesce(sum(CASE WHEN DscDetalheMercado = 'Receita Bandeiras (R$)' THEN VlrMercado END), 0)
        ) / nullif(sum(CASE WHEN DscDetalheMercado = 'Energia TUSD (kWh)' THEN VlrMercado END), 0) AS tarifa_kwh
    FROM bronze_samp
    WHERE DscSubClasseConsumidor = 'Residencial'
      AND NomTipoMercado IN ('Regular', 'Sistema Isolado - Regular')
      AND upper(DscOpcaoEnergia) = 'CATIVO'
    GROUP BY 1, 2
)
-- Exceção: a CEA (AP) faturou em 2012 e 2013 cerca de metade da tarifa homologada (R$ 0,20/kWh contra R$ 0,40 no
-- SAMP); o que o consumidor pagou de fato é o faturado, então nesses dois anos vale o SAMP.
, escolha AS (
    SELECT
        m.cnpj,
        m.mes,
        h.tarifa_kwh AS homologada,
        s.tarifa_kwh AS samp,
        m.cnpj = 5965546000109 AND m.mes < DATE '2014-01-01' AND s.tarifa_kwh IS NOT NULL AS excecao_ap
    FROM meses m
    LEFT JOIN homologada h USING (cnpj, mes)
    LEFT JOIN samp s USING (cnpj, mes)
)
SELECT
    cnpj,
    mes,
    CASE WHEN excecao_ap THEN samp ELSE coalesce(homologada, samp) END AS tarifa_kwh,
    CASE WHEN homologada IS NOT NULL AND NOT excecao_ap THEN 'homologada' ELSE 'samp' END AS fonte_tarifa
FROM escolha
WHERE coalesce(homologada, samp) IS NOT NULL;

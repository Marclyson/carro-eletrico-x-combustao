-- Tarifa branca residencial, posto fora de ponta, sem impostos, da distribuidora de cada capital, vigente no dia 15.
-- Usada no simulador de recarga em casa. Sem reserva do SAMP: mês sem tarifa homologada fica sem linha.
CREATE OR REPLACE TABLE silver_tarifa_branca_mensal AS
WITH distribuidoras AS (
    SELECT CAST(cnpj AS BIGINT) AS cnpj
    FROM read_csv('referencias/distribuidora_capital.csv')
),
branca AS (
    SELECT
        NumCNPJDistribuidora AS cnpj,
        DatInicioVigencia AS inicio,
        DatFimVigencia AS fim,
        (VlrTUSD + VlrTE) / 1000 AS tarifa_kwh
    FROM bronze_tarifa
    WHERE DscBaseTarifaria = 'Tarifa de Aplicação'
      AND DscSubGrupo = 'B1'
      AND DscModalidadeTarifaria = 'Branca'
      AND DscSubClasse = 'Residencial'
      AND DscDetalhe = 'Não se aplica'
      AND NomPostoTarifario = 'Fora ponta'
    QUALIFY row_number() OVER (
        PARTITION BY NumCNPJDistribuidora, DatInicioVigencia ORDER BY _data_extracao DESC
    ) = 1
),
meses AS (
    SELECT d.cnpj, CAST(g.generate_series AS DATE) AS mes
    FROM distribuidoras d
    CROSS JOIN (SELECT max(mes) AS ultimo FROM silver_ipca) u
    CROSS JOIN generate_series(DATE '2012-01-01', u.ultimo, INTERVAL 1 MONTH) AS g
)
SELECT m.cnpj, m.mes, b.tarifa_kwh AS tarifa_branca_fp_kwh
FROM meses m
JOIN branca b ON b.cnpj = m.cnpj AND m.mes + INTERVAL 14 DAY BETWEEN b.inicio AND b.fim
QUALIFY row_number() OVER (PARTITION BY m.cnpj, m.mes ORDER BY b.inicio DESC) = 1;

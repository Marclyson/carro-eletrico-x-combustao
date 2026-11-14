CREATE OR REPLACE TABLE silver_ipca AS
SELECT
    mes,
    variacao
FROM (
    SELECT
        data AS mes,
        valor AS variacao,
        _data_extracao
    FROM bronze_sgs
    WHERE codigo = 433
)
QUALIFY row_number() OVER (
    PARTITION BY mes
    ORDER BY _data_extracao DESC
) = 1;

CREATE OR REPLACE TABLE silver_salario_minimo AS
SELECT
    mes,
    valor
FROM (
    SELECT
        s.data AS mes,
        s.valor,
        s._data_extracao
    FROM bronze_sgs s
    CROSS JOIN (SELECT max(mes) AS mes FROM silver_ipca) limite
    WHERE s.codigo = 1619
      AND s.data <= limite.mes
)
QUALIFY row_number() OVER (
    PARTITION BY mes
    ORDER BY _data_extracao DESC
) = 1;
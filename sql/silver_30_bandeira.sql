CREATE OR REPLACE TABLE silver_bandeira AS
SELECT
    mes,
    bandeira,
    adicional_kwh
FROM (
    SELECT
        competencia AS mes,
        bandeira,
        adicional_mwh / 1000.0 AS adicional_kwh,
        _data_extracao
    FROM bronze_bandeira
)
QUALIFY row_number() OVER (
    PARTITION BY mes
    ORDER BY _data_extracao DESC
) = 1;
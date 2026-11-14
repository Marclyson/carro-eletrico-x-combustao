CREATE OR REPLACE TABLE silver_fator_emissao AS
SELECT
    mes,
    tco2_mwh
FROM (
    SELECT
        mes,
        tco2_mwh,
        _data_extracao
    FROM bronze_mcti
)
QUALIFY row_number() OVER (
    PARTITION BY mes
    ORDER BY _data_extracao DESC
) = 1;
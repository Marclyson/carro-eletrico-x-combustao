CREATE OR REPLACE TABLE silver_precos_combustivel AS
WITH fonte AS (
    SELECT
        mes,
        uf,
        CASE produto
            WHEN 'GASOLINA COMUM' THEN 'gasolina_c'
            WHEN 'ETANOL HIDRATADO' THEN 'etanol_hidratado'
        END AS produto,
        preco_medio_revenda AS preco_medio,
        postos,
        _data_extracao
    FROM bronze_anp
    WHERE produto IN ('GASOLINA COMUM', 'ETANOL HIDRATADO')
)
SELECT mes, uf, produto, preco_medio, postos
FROM fonte
QUALIFY row_number() OVER (
    PARTITION BY mes, uf, produto
    ORDER BY _data_extracao DESC
) = 1;
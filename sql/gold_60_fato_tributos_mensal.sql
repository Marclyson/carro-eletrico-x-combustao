CREATE OR REPLACE TABLE gold_fato_tributos_mensal AS
SELECT mes, uf, energia, 'icms' AS tributo, icms_unit AS valor_unit
FROM gold_preco_energia_mensal
WHERE icms_unit IS NOT NULL
UNION ALL
SELECT mes, uf, energia, 'pis_cofins', pis_cofins_unit
FROM gold_preco_energia_mensal
WHERE pis_cofins_unit IS NOT NULL
UNION ALL
SELECT mes, uf, energia, 'cide', cide_unit
FROM gold_preco_energia_mensal
WHERE cide_unit IS NOT NULL;

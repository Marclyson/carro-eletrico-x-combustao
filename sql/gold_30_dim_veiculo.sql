CREATE OR REPLACE TABLE gold_dim_veiculo AS
SELECT
    veiculo || '_' || energia AS chave_veiculo,
    veiculo,
    energia,
    modelo,
    versao,
    CASE WHEN energia = 'eletricidade' THEN kwh_km ELSE 1 / km_l_combinado END AS consumo_por_km,
    CASE WHEN energia = 'eletricidade' THEN 'kWh/km' ELSE 'l/km' END AS unidade,
    co2_fossil_g_km AS co2_escapamento_g_km,
    ano_pbe
FROM read_csv('referencias/veiculos.csv');

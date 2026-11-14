CREATE OR REPLACE TABLE gold_fato_custo_km_mensal AS
SELECT
    p.mes,
    p.uf,
    v.veiculo,
    p.energia,
    p.preco * v.consumo_por_km AS custo_km,
    p.preco * v.consumo_por_km * t.fator_real AS custo_km_real,
    p.preco_sem_tributos * v.consumo_por_km * t.fator_real AS custo_km_sem_tributos_real,
    p.preco * v.consumo_por_km * 100 / (t.salario_minimo / 220) AS horas_sm_100km,
    CASE
        WHEN p.energia = 'eletricidade' THEN v.consumo_por_km * e.tco2_mwh * 1000
        ELSE v.co2_escapamento_g_km
    END AS co2_g_km,
    p.icms_imputado
FROM gold_preco_energia_mensal p
JOIN gold_dim_veiculo v ON v.energia = p.energia
JOIN gold_dim_tempo t ON t.mes = p.mes
LEFT JOIN silver_fator_emissao e ON e.mes = p.mes;

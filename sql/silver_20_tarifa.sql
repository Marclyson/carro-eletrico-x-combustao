CREATE OR REPLACE TABLE silver_tarifa_residencial AS
SELECT
    cnpj,
    sig_agente,
    inicio,
    fim,
    tusd_mwh,
    te_mwh
FROM (
    SELECT
        NumCNPJDistribuidora AS cnpj,
        SigAgente AS sig_agente,
        DatInicioVigencia AS inicio,
        DatFimVigencia AS fim,
        VlrTUSD AS tusd_mwh,
        VlrTE AS te_mwh,
        _data_extracao
    FROM bronze_tarifa
    WHERE DscBaseTarifaria = 'Tarifa de Aplicação'
      AND DscSubGrupo = 'B1'
      AND DscModalidadeTarifaria = 'Convencional'
      AND DscSubClasse = 'Residencial'
      AND DscDetalhe = 'Não se aplica'
)
QUALIFY row_number() OVER (
    PARTITION BY cnpj, inicio
    ORDER BY _data_extracao DESC
) = 1;
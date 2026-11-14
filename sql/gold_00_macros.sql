CREATE OR REPLACE MACRO preco_com_imposto(base, icms, pis_cofins) AS base / (1 - icms - pis_cofins);

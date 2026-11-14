CREATE OR REPLACE TABLE gold_dim_uf AS
WITH nomes (uf, nome, regiao) AS (
    VALUES
        ('AC', 'Acre', 'Norte'),
        ('AL', 'Alagoas', 'Nordeste'),
        ('AM', 'Amazonas', 'Norte'),
        ('AP', 'Amapá', 'Norte'),
        ('BA', 'Bahia', 'Nordeste'),
        ('CE', 'Ceará', 'Nordeste'),
        ('DF', 'Distrito Federal', 'Centro-Oeste'),
        ('ES', 'Espírito Santo', 'Sudeste'),
        ('GO', 'Goiás', 'Centro-Oeste'),
        ('MA', 'Maranhão', 'Nordeste'),
        ('MG', 'Minas Gerais', 'Sudeste'),
        ('MS', 'Mato Grosso do Sul', 'Centro-Oeste'),
        ('MT', 'Mato Grosso', 'Centro-Oeste'),
        ('PA', 'Pará', 'Norte'),
        ('PB', 'Paraíba', 'Nordeste'),
        ('PE', 'Pernambuco', 'Nordeste'),
        ('PI', 'Piauí', 'Nordeste'),
        ('PR', 'Paraná', 'Sul'),
        ('RJ', 'Rio de Janeiro', 'Sudeste'),
        ('RN', 'Rio Grande do Norte', 'Nordeste'),
        ('RO', 'Rondônia', 'Norte'),
        ('RR', 'Roraima', 'Norte'),
        ('RS', 'Rio Grande do Sul', 'Sul'),
        ('SC', 'Santa Catarina', 'Sul'),
        ('SE', 'Sergipe', 'Nordeste'),
        ('SP', 'São Paulo', 'Sudeste'),
        ('TO', 'Tocantins', 'Norte')
)
SELECT
    d.uf,
    n.nome,
    n.regiao,
    d.capital,
    d.sig_agente,
    CAST(d.cnpj AS BIGINT) AS cnpj
FROM read_csv('referencias/distribuidora_capital.csv') d
JOIN nomes n USING (uf);

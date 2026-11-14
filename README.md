# Carro popular a combustão x elétrico

Quanto custa rodar 1 km com um carro popular a gasolina, a etanol e elétrico no Brasil, com e sem impostos, desde jan. 2012.

## Como rodar

- `make install`: instala as dependências.
- `make carga`: extrai os dados das fontes abertas.
- `make gold`: transforma e exporta as tabelas finais.
- `make painel`: gera o painel do Power BI em `powerbi/` (PBIP), com o Power BI Desktop fechado. O modelo lê
  `gold/*.parquet`; se o repositório não estiver em `C:\repo\carro-eletrico-x-combustao`, troque os parâmetros
  PastaGold e PastaReferencias em Transformar dados.
- `make test`: executa os testes.

## Dados

- ANP, Levantamento de Preços de Combustíveis.
- ANEEL, tarifas homologadas, bandeiras tarifárias e SAMP (ODbL).
- Inmetro, PBE Veicular 2026.
- Banco Central, SGS 433 (IPCA, produzido pelo IBGE) e 1619 (salário mínimo) (ODbL).
- MCTI, fator médio mensal de emissão de CO2 do SIN.
- IBGE, malhas territoriais das UFs (mapa do painel; `python scripts/pbip/malha_uf.py` baixa e simplifica).

Código sob MIT. Projeto de estudo com dados públicos, sem relação com os órgãos citados.

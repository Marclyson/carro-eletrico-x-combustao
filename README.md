# Carro popular a combustão x elétrico

Quanto custa rodar 1 km com um carro popular a gasolina, a etanol e elétrico no Brasil, com e sem impostos, desde 2010.

## Como rodar

- `make install`: instala as dependências.
- `make carga`: extrai os dados das fontes abertas.
- `make gold`: transforma e exporta as tabelas finais.
- `make test`: executa os testes.

## Dados

- ANP, Levantamento de Preços de Combustíveis.
- ANEEL, tarifas homologadas e bandeiras tarifárias (ODbL).
- Inmetro, PBE Veicular 2026.
- Banco Central, SGS 433 (IPCA, produzido pelo IBGE) e 1619 (salário mínimo) (ODbL).
- MCTI, fator médio mensal de emissão de CO2 do SIN.

Código sob MIT. Projeto de estudo com dados públicos, sem relação com os órgãos citados.

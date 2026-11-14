.PHONY: install carga gold test check

install:
	pip install -r requirements.txt

carga:
	python -m custo_km.extrair_anp && python -m custo_km.extrair_aneel && python -m custo_km.extrair_sgs && python -m custo_km.extrair_mcti

gold:
	python -m custo_km.transformar && python -m custo_km.exportar

test:
	python -m pytest -q

check:
	ruff check .

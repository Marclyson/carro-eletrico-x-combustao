.PHONY: install carga gold incremental test check

install:
	pip install -r requirements.txt

carga:
	python -m custo_km.extrair_anp && python -m custo_km.extrair_aneel && python -m custo_km.extrair_sgs && python -m custo_km.extrair_mcti && python -m custo_km.extrair_samp

gold:
	python -m custo_km.transformar && python -m custo_km.exportar

incremental:
	python scripts/conferir_incremental.py

test:
	python -m pytest -q

check:
	ruff check .

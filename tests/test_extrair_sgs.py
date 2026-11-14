import json
from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from custo_km.extrair_sgs import carregar_sgs, criar_tabela, url_sgs

PASTA_SGS = Path(__file__).parent / "fixtures" / "sgs"


@pytest.fixture
def con():
    conexao = duckdb.connect(":memory:")
    criar_tabela(conexao)
    yield conexao
    conexao.close()


def linhas(codigo):
    return json.loads((PASTA_SGS / f"sgs_{codigo}.json").read_text(encoding="utf-8"))


def test_url_sgs():
    assert url_sgs(433) == "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json"


def test_carregar_sgs_433(con):
    assert carregar_sgs(con, 433, linhas(433), datetime(2024, 1, 1)) == 12
    alvo = con.execute(
        "SELECT valor FROM bronze_sgs WHERE codigo = 433 AND data = DATE '2025-08-01'"
    ).fetchall()
    assert alvo == [(-0.11,)]
    assert carregar_sgs(con, 433, linhas(433), datetime(2024, 1, 1)) == 0


def test_carregar_sgs_1619(con):
    assert carregar_sgs(con, 1619, linhas(1619), datetime(2024, 1, 1)) == 6
    alvo = con.execute(
        "SELECT valor FROM bronze_sgs WHERE codigo = 1619 AND data = DATE '2026-01-01'"
    ).fetchall()
    assert alvo == [(1621.0,)]
    assert carregar_sgs(con, 1619, linhas(1619), datetime(2024, 1, 1)) == 0
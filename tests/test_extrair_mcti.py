from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

from custo_km.extrair_mcti import (
    carregar,
    criar_tabela,
    ler_anuais,
    ler_mensais,
    sha256_arquivo,
)

PASTA_MCTI = Path(__file__).parent / "fixtures" / "mcti"

ARQUIVO = "Inventario_2026_janset.xlsx"
SHA_ESPERADO = "50cbb9b78ea583baa0115e59e234c3820caae0496cf0609822c398bf238046ec"
DATA_EXTRACAO = datetime(2026, 1, 1)


@pytest.fixture
def con():
    conexao = duckdb.connect(":memory:")
    criar_tabela(conexao)
    yield conexao
    conexao.close()


def carregar_amostra(conexao):
    linhas = ler_mensais(PASTA_MCTI / ARQUIVO)
    return carregar(conexao, linhas, ARQUIVO, SHA_ESPERADO, DATA_EXTRACAO)


def test_ler_mensais():
    linhas = ler_mensais(PASTA_MCTI / ARQUIVO)
    assert len(linhas) == 249

    fatores = {linha["mes"]: linha["tco2_mwh"] for linha in linhas}
    assert fatores[date(2006, 1, 1)] == 0.0322
    assert fatores[date(2012, 11, 1)] == 0.1247
    assert fatores[date(2026, 9, 1)] == 0.0462
    assert date(2026, 10, 1) not in fatores


def test_ler_anuais():
    anuais = ler_anuais(PASTA_MCTI / ARQUIVO)
    assert anuais[2006] == 0.0323
    assert 2026 not in anuais
    assert len(anuais) == 20


def test_carregar_duas_vezes(con):
    assert carregar_amostra(con) == 249
    assert carregar_amostra(con) == 0


def test_valor_corrigido_vira_linha_nova(con):
    carregar_amostra(con)
    linhas = ler_mensais(PASTA_MCTI / ARQUIVO)
    linha = next(item for item in linhas if item["mes"] == date(2012, 11, 1))
    linha["tco2_mwh"] = 0.1248
    assert carregar(con, [linha], ARQUIVO, SHA_ESPERADO, DATA_EXTRACAO) == 1
    assert con.execute("SELECT count(*) FROM bronze_mcti").fetchone()[0] == 250


def test_sha256_arquivo():
    assert sha256_arquivo(PASTA_MCTI / ARQUIVO) == SHA_ESPERADO
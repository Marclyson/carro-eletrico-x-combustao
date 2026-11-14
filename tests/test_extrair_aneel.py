import json
from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

from custo_km.extrair_aneel import (
    carregar_bandeiras,
    carregar_tarifas,
    criar_tabelas,
    ler_bandeiras,
    url_recurso,
)

PASTA_ANEEL = Path(__file__).parent / "fixtures" / "aneel"


@pytest.fixture
def con():
    conexao = duckdb.connect(":memory:")
    criar_tabelas(conexao, PASTA_ANEEL / "tarifas.parquet")
    yield conexao
    conexao.close()


def carregar_tarifas_amostra(conexao):
    return carregar_tarifas(conexao, PASTA_ANEEL / "tarifas.parquet", datetime(2024, 1, 1))


def carregar_bandeiras_amostra(conexao):
    return carregar_bandeiras(conexao, ler_bandeiras(PASTA_ANEEL / "bandeira-acionamento.csv"), datetime(2024, 1, 1))


def test_url_recurso():
    tarifas = json.loads((PASTA_ANEEL / "pacote-tarifas.json").read_text(encoding="utf-8"))
    bandeiras = json.loads((PASTA_ANEEL / "pacote-bandeiras.json").read_text(encoding="utf-8"))
    assert url_recurso(tarifas, "PARQUET").endswith(".parquet")
    assert "/resource/" in url_recurso(bandeiras, "CSV", "Acionamento")


def test_carregar_tarifas(con):
    assert carregar_tarifas_amostra(con) == 180
    assert carregar_tarifas_amostra(con) == 0


def test_tarifa_neoenergia_pe(con):
    carregar_tarifas_amostra(con)
    alvo = con.execute(
        """
        SELECT VlrTUSD, VlrTE
        FROM bronze_tarifa
        WHERE SigAgente = 'Neoenergia PE'
          AND DatInicioVigencia = DATE '2026-04-29'
          AND DscSubGrupo = 'B1'
          AND DscModalidadeTarifaria = 'Convencional'
          AND DscBaseTarifaria = 'Tarifa de Aplicação'
          AND DscSubClasse = 'Residencial'
          AND DscDetalhe = 'Não se aplica'
        """
    ).fetchall()
    assert alvo == [(535.21, 263.65)]


def test_ler_bandeiras():
    linhas = ler_bandeiras(PASTA_ANEEL / "bandeira-acionamento.csv")
    assert len(linhas) == 13
    assert next(linha for linha in linhas if linha["competencia"] == date(2021, 9, 1)) == {
        "competencia": date(2021, 9, 1),
        "bandeira": "Escassez Hídrica",
        "adicional_mwh": 142.0,
    }
    assert next(linha for linha in linhas if linha["competencia"] == date(2015, 3, 1))["adicional_mwh"] == 55.0
    assert next(linha for linha in linhas if linha["competencia"] == date(2020, 5, 1)) == {
        "competencia": date(2020, 5, 1),
        "bandeira": "Verde",
        "adicional_mwh": 0.0,
    }


def test_carregar_bandeiras(con):
    assert carregar_bandeiras_amostra(con) == 13
    assert carregar_bandeiras_amostra(con) == 0
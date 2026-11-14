"""Testes da exportacao da camada gold em Parquet."""

import datetime as dt

import duckdb
import pytest

from custo_km.exportar import exportar
from scripts.conferir_incremental import contagens


@pytest.fixture
def con():
    conexao = duckdb.connect(":memory:")
    try:
        yield conexao
    finally:
        conexao.close()


def _criar_gold(con):
    con.execute("CREATE TABLE gold_dim_tempo (mes DATE, ano INTEGER)")
    con.execute(
        """
        INSERT INTO gold_dim_tempo VALUES
            (DATE '2024-02-01', 2024),
            (DATE '2024-01-01', 2024)
        """
    )
    con.execute("CREATE TABLE gold_fato_custo_km_mensal (mes DATE, uf VARCHAR, custo_km DOUBLE)")
    con.execute(
        """
        INSERT INTO gold_fato_custo_km_mensal VALUES
            (DATE '2024-01-01', 'PE', 0.50),
            (DATE '2024-02-01', 'PE', 0.60)
        """
    )
    con.execute("CREATE TABLE silver_x (mes DATE, valor DOUBLE)")
    con.execute("INSERT INTO silver_x VALUES (DATE '2024-01-01', 1.0)")


def test_exportar_grava_somente_gold_e_apaga_parquet_velho(con, tmp_path):
    _criar_gold(con)
    pasta = tmp_path / "gold"
    pasta.mkdir()
    (pasta / "sobra.parquet").write_bytes(b"antigo")

    resultado = exportar(con, pasta)

    assert resultado == {"dim_tempo.parquet": 2, "fato_custo_km_mensal.parquet": 2}
    assert sorted(caminho.name for caminho in pasta.glob("*.parquet")) == [
        "dim_tempo.parquet",
        "fato_custo_km_mensal.parquet",
    ]


def test_exportar_mantem_linhas_e_ordem(con, tmp_path):
    _criar_gold(con)

    exportar(con, tmp_path)

    linhas = duckdb.connect(":memory:")
    try:
        lidas = linhas.execute(
            f"SELECT mes, ano FROM read_parquet('{tmp_path / 'dim_tempo.parquet'}') ORDER BY mes"
        ).fetchall()
        assert lidas == [
            (dt.date(2024, 1, 1), 2024),
            (dt.date(2024, 2, 1), 2024),
        ]

        fato = linhas.execute(
            f"SELECT mes, uf FROM read_parquet('{tmp_path / 'fato_custo_km_mensal.parquet'}') "
            "ORDER BY mes, uf"
        ).fetchall()
        assert fato == [
            (dt.date(2024, 1, 1), "PE"),
            (dt.date(2024, 2, 1), "PE"),
        ]
    finally:
        linhas.close()


def test_contagens_somente_bronze(con):
    con.execute("CREATE TABLE bronze_a (x INTEGER)")
    con.execute("INSERT INTO bronze_a VALUES (1), (2)")
    con.execute("CREATE TABLE bronze_b (x INTEGER)")
    con.execute("CREATE TABLE silver_a (x INTEGER)")
    con.execute("INSERT INTO silver_a VALUES (1), (2), (3)")

    assert contagens(con) == {"bronze_a": 2, "bronze_b": 0}


def test_contagens_tabela_vazia_antes_da_carga(con):
    assert contagens(con) == {}
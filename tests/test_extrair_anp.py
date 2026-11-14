from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

from custo_km.extrair_anp import (
    carregar,
    criar_tabela,
    ler_planilha,
    meses_ausentes,
    numero,
    sem_acento,
)

PASTA_ANP = Path(__file__).parent / "fixtures" / "anp"

PLANILHAS = (
    "mensal-estados-2001-a-2012.xlsx",
    "mensal-estados-desde-jan2013.xlsx",
    "mensal-brasil-desde-jan2013.xlsx",
)


@pytest.fixture
def con():
    conexao = duckdb.connect(":memory:")
    criar_tabela(conexao)
    yield conexao
    conexao.close()


def carregar_amostras(conexao):
    total = 0
    for nome in PLANILHAS:
        linhas = ler_planilha(PASTA_ANP / nome)
        total += carregar(conexao, linhas, nome, datetime(2024, 1, 1))
    return total


def test_ler_planilha_amostras():
    assert len(ler_planilha(PASTA_ANP / "mensal-estados-2001-a-2012.xlsx")) == 20
    assert len(ler_planilha(PASTA_ANP / "mensal-estados-desde-jan2013.xlsx")) == 54
    assert len(ler_planilha(PASTA_ANP / "mensal-brasil-desde-jan2013.xlsx")) == 14


def test_ler_planilha_2001_a_2012():
    linhas = ler_planilha(PASTA_ANP / "mensal-estados-2001-a-2012.xlsx")
    alvo = next(
        linha
        for linha in linhas
        if linha["uf"] == "PE"
        and linha["produto"] == "GASOLINA COMUM"
        and linha["mes"] == date(2012, 12, 1)
    )
    assert alvo["preco_medio_revenda"] == 2.732
    assert "OLEO DIESEL" in {linha["produto"] for linha in linhas}


def test_ler_planilha_desde_2013():
    linhas = ler_planilha(PASTA_ANP / "mensal-estados-desde-jan2013.xlsx")
    gasolina = next(
        linha
        for linha in linhas
        if linha["uf"] == "PE"
        and linha["produto"] == "GASOLINA COMUM"
        and linha["mes"] == date(2015, 3, 1)
    )
    etanol = next(
        linha
        for linha in linhas
        if linha["uf"] == "PE"
        and linha["produto"] == "ETANOL HIDRATADO"
        and linha["mes"] == date(2026, 10, 1)
    )
    assert gasolina["preco_medio_revenda"] == 3.25
    assert etanol["preco_medio_revenda"] == 4.93
    assert {linha["uf"] for linha in linhas} == {"PE", "SP", "AC"}


def test_ler_planilha_brasil():
    linhas = ler_planilha(PASTA_ANP / "mensal-brasil-desde-jan2013.xlsx")
    alvo = next(
        linha
        for linha in linhas
        if linha["produto"] == "GASOLINA COMUM" and linha["mes"] == date(2026, 10, 1)
    )
    assert alvo["uf"] == "BR"
    assert alvo["preco_medio_revenda"] == 6.51


def test_carregar_amostras(con):
    assert carregar_amostras(con) == 88
    assert carregar_amostras(con) == 0


def test_linha_com_preco_alterado_entra_de_novo(con):
    carregar_amostras(con)
    linhas = ler_planilha(PASTA_ANP / "mensal-estados-2001-a-2012.xlsx")
    linha = next(
        item
        for item in linhas
        if item["uf"] == "PE"
        and item["produto"] == "GASOLINA COMUM"
        and item["mes"] == date(2012, 12, 1)
    )
    linha["preco_medio_revenda"] = 2.733
    assert carregar(con, [linha], "mensal-estados-2001-a-2012.xlsx", datetime(2024, 1, 1)) == 1
    assert con.execute("SELECT count(*) FROM bronze_anp").fetchone()[0] == 89


def test_meses_ausentes(con):
    carregar_amostras(con)
    ausentes = meses_ausentes(con, "GASOLINA COMUM", "BR", date(2020, 8, 1), date(2020, 10, 1))
    assert ausentes == [date(2020, 9, 1)]


def test_numero_e_sem_acento():
    assert numero("-") is None
    assert numero(3) == 3.0
    assert sem_acento(" Óleo  diesel ") == "OLEO DIESEL"
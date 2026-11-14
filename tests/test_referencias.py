"""Confere as tabelas de referência escritas à mão (tributos e distribuidoras das capitais)."""

import csv
import datetime as dt
import itertools
from pathlib import Path
from urllib.parse import urlparse

import pytest

REFERENCIAS = Path(__file__).resolve().parent.parent / "referencias"
DOMINIOS_OFICIAIS = (".gov.br", ".leg.br", ".jus.br")
UFS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
    "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}


def ler(nome):
    with open(REFERENCIAS / nome, encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


@pytest.fixture(scope="module")
def tributos():
    return ler("tributos_combustivel.csv")


def test_tributos_links_oficiais_ou_confirmar(tributos):
    for linha in tributos:
        link = linha["link_fonte"]
        if link:
            assert (urlparse(link).hostname or "").endswith(DOMINIOS_OFICIAIS), link
        else:
            assert "[CONFIRMAR]" in linha["observacao"]


def test_tributos_periodos_emendados(tributos):
    series = {}
    for linha in tributos:
        fim = dt.date.fromisoformat(linha["fim"]) if linha["fim"] else None
        series.setdefault((linha["tributo"], linha["produto"]), []).append(
            (dt.date.fromisoformat(linha["inicio"]), fim)
        )
    assert len(series) == 6
    for chave, periodos in series.items():
        periodos.sort()
        inicio_minimo = dt.date(2023, 6, 1) if chave[0] == "icms_ad_rem" else dt.date(2012, 1, 1)
        assert periodos[0][0] <= inicio_minimo, chave
        for (_, fim), (proximo, _) in itertools.pairwise(periodos):
            assert fim + dt.timedelta(days=1) == proximo, chave
        assert periodos[-1][1] is None, chave


def valor_em(tributos, tributo, produto, dia):
    dia = dt.date.fromisoformat(dia)
    for linha in tributos:
        inicio = dt.date.fromisoformat(linha["inicio"])
        fim = dt.date.fromisoformat(linha["fim"]) if linha["fim"] else dt.date.max
        if linha["tributo"] == tributo and linha["produto"] == produto and inicio <= dia <= fim:
            return float(linha["valor"])
    raise KeyError((tributo, produto, dia))


@pytest.mark.parametrize(
    ("tributo", "produto", "dia", "esperado"),
    [
        ("pis_cofins", "gasolina_a", "2018-01-15", 0.7925),  # Decreto 9.101/2017
        ("pis_cofins", "gasolina_a", "2023-04-15", 0.469998),  # MP 1.163/2023
        ("pis_cofins", "gasolina_a", "2023-07-15", 0.7925),  # MP 1.163 encerrada em 28/06/2023
        ("cide", "gasolina_a", "2014-01-15", 0.0),  # Decreto 7.764/2012
        ("cide", "gasolina_a", "2015-05-15", 0.10),  # Decreto 8.395/2015, a partir de 01/05/2015
        ("icms_ad_rem", "gasolina_c", "2023-06-15", 1.22),  # Convênio ICMS 15/2023
        ("icms_ad_rem", "gasolina_c", "2024-06-15", 1.3721),  # Convênio ICMS 173/2023
        ("icms_ad_rem", "gasolina_c", "2026-01-15", 1.57),  # Convênio ICMS 112/2025
        ("fracao_gasolina_a", "gasolina_c", "2012-06-15", 0.80),  # 20 % de anidro
        ("fracao_gasolina_a", "gasolina_c", "2015-03-16", 0.73),  # 27 % de anidro
        ("fracao_gasolina_a", "gasolina_c", "2025-08-01", 0.70),  # 30 % de anidro
    ],
)
def test_tributos_valores_conferidos_na_norma(tributos, tributo, produto, dia, esperado):
    assert valor_em(tributos, tributo, produto, dia) == pytest.approx(esperado)


def test_distribuidora_capital_uma_por_uf():
    linhas = ler("distribuidora_capital.csv")
    assert {linha["uf"] for linha in linhas} == UFS
    assert len(linhas) == 27
    assert all(linha["cnpj"].isdigit() and not linha["cnpj"].startswith("0") for linha in linhas)
    neoenergia_pe = next(linha for linha in linhas if linha["uf"] == "PE")
    assert int(neoenergia_pe["cnpj"]) == 10835932000108


def test_precos_carros_com_data_e_fonte():
    linhas = {linha["veiculo"]: linha for linha in ler("precos_carros.csv")}
    assert set(linhas) == {"kwid", "polo_track", "dolphin_mini", "e_kwid"}
    assert int(linhas["kwid"]["preco_tabela"]) == 82790
    assert int(linhas["dolphin_mini"]["preco_tabela"]) == 118990
    assert linhas["e_kwid"]["preco_tabela"] == ""  # fora de linha
    assert all(linha["link_fonte"].startswith("https://") and linha["data_consulta"] for linha in linhas.values())

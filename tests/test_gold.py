"""Testes da camada gold: tabelas prontas em memória, só os gold_*.sql e as referências reais."""

import datetime as dt
from pathlib import Path

import duckdb
import pytest

RAIZ = Path(__file__).resolve().parent.parent
PASTA_SQL = RAIZ / "sql"

CNPJ_PE = 10835932000108


def carregar_silver(con):
    con.execute("CREATE TABLE silver_ipca (mes DATE, variacao DOUBLE)")
    con.execute(
        """
        INSERT INTO silver_ipca
        SELECT CAST(g AS DATE), 0.5
        FROM generate_series(DATE '2011-12-01', DATE '2026-05-01', INTERVAL 1 MONTH) AS t(g)
        """
    )

    con.execute(
        "CREATE TABLE silver_precos_combustivel "
        "(mes DATE, uf VARCHAR, produto VARCHAR, preco_medio DOUBLE, postos INTEGER)"
    )
    con.execute(
        """
        INSERT INTO silver_precos_combustivel VALUES
            (DATE '2011-12-01', 'PE', 'gasolina_c', 4.50, 10),
            (DATE '2023-05-01', 'PE', 'gasolina_c', 5.00, 10),
            (DATE '2023-06-01', 'PE', 'gasolina_c', 5.00, 10),
            (DATE '2026-05-01', 'PE', 'etanol_hidratado', 3.00, 10),
            (DATE '2026-06-01', 'PE', 'gasolina_c', 6.00, 10)
        """
    )

    con.execute(
        "CREATE TABLE silver_tarifa_mensal (cnpj BIGINT, mes DATE, tarifa_kwh DOUBLE, fonte_tarifa VARCHAR)"
    )
    con.execute(
        """
        INSERT INTO silver_tarifa_mensal VALUES
            (?, DATE '2026-04-01', 0.76918, 'homologada'),
            (?, DATE '2026-05-01', 0.79886, 'samp')
        """,
        [CNPJ_PE, CNPJ_PE],
    )

    con.execute("CREATE TABLE silver_bandeira (mes DATE, bandeira VARCHAR, adicional_kwh DOUBLE)")
    con.execute("INSERT INTO silver_bandeira VALUES (DATE '2026-04-01', 'amarela', 0.01885)")

    con.execute(
        "CREATE TABLE silver_aliquota_energia "
        "(cnpj BIGINT, mes DATE, icms DOUBLE, pis_cofins DOUBLE, imputado BOOLEAN)"
    )
    con.execute(
        """
        INSERT INTO silver_aliquota_energia
        SELECT CAST(cnpj AS BIGINT), m.mes, 0.20, 0.05, FALSE
        FROM read_csv('referencias/distribuidora_capital.csv')
        CROSS JOIN (VALUES (DATE '2026-04-01'), (DATE '2026-05-01')) AS m(mes)
        """
    )
    con.execute(
        "UPDATE silver_aliquota_energia SET imputado = TRUE WHERE cnpj = ? AND mes = DATE '2026-04-01'",
        [CNPJ_PE],
    )

    con.execute("CREATE TABLE silver_salario_minimo (mes DATE, valor DOUBLE)")
    con.execute(
        """
        INSERT INTO silver_salario_minimo VALUES
            (DATE '2023-05-01', 1320.00),
            (DATE '2026-05-01', 1518.00)
        """
    )

    con.execute("CREATE TABLE silver_fator_emissao (mes DATE, tco2_mwh DOUBLE)")
    con.execute("INSERT INTO silver_fator_emissao VALUES (DATE '2026-05-01', 0.05)")


def rodar_gold(con):
    for caminho in sorted(PASTA_SQL.glob("gold_*.sql")):
        con.execute(caminho.read_text(encoding="utf-8"))


@pytest.fixture
def con(monkeypatch):
    monkeypatch.chdir(RAIZ)
    conexao = duckdb.connect(":memory:")
    carregar_silver(conexao)
    rodar_gold(conexao)
    try:
        yield conexao
    finally:
        conexao.close()


def test_preco_com_imposto_divide_pela_parcela_liquida(con):
    valor = con.execute("SELECT preco_com_imposto(1.0, 0.20, 0.05)").fetchone()[0]
    assert valor == pytest.approx(1.3333, abs=1e-4)
    assert valor != pytest.approx(1.25, abs=1e-4)


def test_eletricidade_pe_com_bandeira_e_tarifa_homologada(con):
    linha = con.execute(
        """
        SELECT preco, tarifa_imputada, icms_imputado, unidade
        FROM gold_preco_energia_mensal
        WHERE uf = 'PE' AND energia = 'eletricidade' AND mes = DATE '2026-04-01'
        """
    ).fetchone()
    assert linha[0] == pytest.approx((0.76918 + 0.01885) / 0.75)
    assert linha[1] is False
    assert linha[2] is True
    assert linha[3] == "R$/kWh"


def test_eletricidade_pe_sem_bandeira_tarifa_samp(con):
    linha = con.execute(
        """
        SELECT preco, tarifa_imputada
        FROM gold_preco_energia_mensal
        WHERE uf = 'PE' AND energia = 'eletricidade' AND mes = DATE '2026-05-01'
        """
    ).fetchone()
    assert linha[0] == pytest.approx(0.79886 / 0.75)
    assert linha[1] is True


def test_gasolina_sem_icmse_ad_rem_antes_de_junho_2023(con):
    linha = con.execute(
        """
        SELECT icms_unit, preco_sem_tributos
        FROM gold_preco_energia_mensal
        WHERE uf = 'PE' AND energia = 'gasolina' AND mes = DATE '2023-05-01'
        """
    ).fetchone()
    assert linha[0] is None
    assert linha[1] == pytest.approx(5 - (0.469998 + 0.10) * 0.73)


def test_gasolina_com_icms_ad_rem_em_junho_2023(con):
    linha = con.execute(
        """
        SELECT icms_unit, preco_sem_tributos
        FROM gold_preco_energia_mensal
        WHERE uf = 'PE' AND energia = 'gasolina' AND mes = DATE '2023-06-01'
        """
    ).fetchone()
    assert linha[0] == pytest.approx(1.22)
    assert linha[1] == pytest.approx(5 - (0.469998 + 0.10) * 0.73 - 1.22)


def test_fator_real_e_custo_km_do_mes_final(con):
    assert con.execute("SELECT max(mes) FROM gold_dim_tempo").fetchone()[0] == dt.date(2026, 5, 1)
    assert con.execute(
        "SELECT fator_real FROM gold_dim_tempo WHERE mes = DATE '2026-05-01'"
    ).fetchone()[0] == pytest.approx(1.0)

    divergentes = con.execute(
        """
        SELECT count(*)
        FROM gold_fato_custo_km_mensal c
        JOIN gold_dim_tempo t USING (mes)
        WHERE abs(c.custo_km_real - c.custo_km * t.fator_real) > 1e-12
        """
    ).fetchone()[0]
    assert divergentes == 0


def test_custo_km_kwid_gasolina(con):
    linha = con.execute(
        """
        SELECT custo_km, preco
        FROM gold_fato_custo_km_mensal c
        JOIN gold_preco_energia_mensal p USING (mes, uf, energia)
        WHERE c.veiculo = 'kwid' AND c.energia = 'gasolina'
          AND c.uf = 'PE' AND c.mes = DATE '2023-05-01' AND p.preco = 5.00
        """
    ).fetchone()
    assert linha[1] == pytest.approx(5.00)
    assert linha[0] == pytest.approx(5.00 / 14.9)


def test_horas_sm_e_co2_do_e_kwid(con):
    preco = 0.79886 / 0.75
    consumo = 0.1222
    custo_km = preco * consumo
    linha = con.execute(
        """
        SELECT custo_km, custo_km_real, custo_km_sem_tributos_real, horas_sm_100km, co2_g_km
        FROM gold_fato_custo_km_mensal
        WHERE veiculo = 'e_kwid' AND uf = 'PE' AND mes = DATE '2026-05-01'
        """
    ).fetchone()
    assert linha[0] == pytest.approx(custo_km)
    assert linha[3] == pytest.approx(custo_km * 100 / (1518.00 / 220))
    assert linha[4] == pytest.approx(0.1222 * 0.05 * 1000)
    assert linha[4] == pytest.approx(0.1222 * 50)


@pytest.mark.parametrize(
    "tabela",
    [
        "gold_dim_tempo",
        "gold_preco_energia_mensal",
        "gold_fato_custo_km_mensal",
        "gold_fato_tributos_mensal",
    ],
)
def test_intervalo_de_meses(con, tabela):
    minimo, maximo = con.execute(f"SELECT min(mes), max(mes) FROM {tabela}").fetchone()
    assert minimo >= dt.date(2012, 1, 1)
    assert maximo <= dt.date(2026, 5, 1)


def test_tributos_sem_valor_nulo(con):
    assert con.execute(
        """
        SELECT count(*)
        FROM gold_fato_tributos_mensal
        WHERE valor_unit IS NULL OR tributo NOT IN ('icms', 'pis_cofins', 'cide')
        """
    ).fetchone()[0] == 0

def test_fator_real_usa_o_ultimo_mes_mesmo_com_deflacao(con):
    # IPCA negativo no último mês: o índice máximo fica no mês anterior, mas a base é o último mês.
    con.execute("UPDATE silver_ipca SET variacao = -0.5 WHERE mes = DATE '2026-05-01'")
    rodar_gold(con)
    fator_final, fator_anterior = (
        linha[0]
        for linha in con.execute(
            "SELECT fator_real FROM gold_dim_tempo WHERE mes >= DATE '2026-04-01' ORDER BY mes DESC"
        ).fetchall()
    )
    assert fator_final == pytest.approx(1.0)
    assert fator_anterior == pytest.approx(0.995)

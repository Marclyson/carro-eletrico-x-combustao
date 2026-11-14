import datetime as dt
import json
from pathlib import Path

import duckdb
import pytest

from custo_km.extrair_aneel import carregar_bandeiras, carregar_tarifas, criar_tabelas, ler_bandeiras
from custo_km.extrair_anp import carregar as carregar_anp
from custo_km.extrair_anp import ler_planilha as ler_anp
from custo_km.extrair_mcti import carregar as carregar_mcti
from custo_km.extrair_mcti import criar_tabela as criar_mcti
from custo_km.extrair_mcti import ler_mensais as ler_mcti
from custo_km.extrair_samp import carregar_samp
from custo_km.extrair_sgs import carregar_sgs
from custo_km.extrair_sgs import criar_tabela as criar_sgs
from custo_km.transformar import rodar_sql

RAIZ = Path(__file__).resolve().parent.parent
PASTA_SQL = RAIZ / "sql"
PASTA_ANP = RAIZ / "tests" / "fixtures" / "anp"
PASTA_ANEEL = RAIZ / "tests" / "fixtures" / "aneel"
PASTA_SGS = RAIZ / "tests" / "fixtures" / "sgs"
PASTA_MCTI = RAIZ / "tests" / "fixtures" / "mcti"
PASTA_SAMP = RAIZ / "tests" / "fixtures" / "samp"

DATA = dt.datetime(2024, 1, 1)


@pytest.fixture
def con():
    conexao = duckdb.connect(":memory:")
    yield conexao
    conexao.close()


def carregar_bronze(conexao):
    for nome in (
        "mensal-estados-2001-a-2012.xlsx",
        "mensal-estados-desde-jan2013.xlsx",
        "mensal-brasil-desde-jan2013.xlsx",
    ):
        caminho = PASTA_ANP / nome
        carregar_anp(conexao, ler_anp(caminho), caminho.name, DATA)

    tarifas = PASTA_ANEEL / "tarifas.parquet"
    criar_tabelas(conexao, tarifas)
    carregar_tarifas(conexao, tarifas, DATA)
    carregar_bandeiras(conexao, ler_bandeiras(PASTA_ANEEL / "bandeira-acionamento.csv"), DATA)

    criar_sgs(conexao)
    ipca = json.loads((PASTA_SGS / "sgs_433_2012_2025.json").read_text(encoding="utf-8"))
    carregar_sgs(conexao, 433, ipca, DATA)
    salario = json.loads((PASTA_SGS / "sgs_1619.json").read_text(encoding="utf-8"))
    carregar_sgs(conexao, 1619, salario, DATA)

    criar_mcti(conexao)
    mcti = PASTA_MCTI / "Inventario_2026_janset.xlsx"
    carregar_mcti(conexao, ler_mcti(mcti), mcti.name, "", DATA)

    carregar_samp(conexao, PASTA_SAMP / "samp-2012.parquet", DATA)
    carregar_samp(conexao, PASTA_SAMP / "samp-2024.parquet", DATA)


def inserir_samp(conexao, cnpj, mes, detalhe, valor, hash_linha):
    conexao.execute(
        """
        INSERT INTO bronze_samp
        SELECT
            DatGeracaoConjuntoDados, NumCNPJAgenteDistribuidora, SigAgenteDistribuidora,
            NomAgenteDistribuidora, NomTipoMercado, DscModalidadeTarifaria, DscSubGrupoTarifario,
            DscClasseConsumoMercado, DscSubClasseConsumidor, DscDetalheConsumidor, IdeNucleoCeg,
            NumCNPJAgenteAcessante, NomAgenteAcessante, DscPostoTarifario, DscOpcaoEnergia,
            ?, ?, ?, ?, ?
        FROM bronze_samp
        WHERE NumCNPJAgenteDistribuidora = ?
          AND DatCompetencia = DATE '2024-06-01'
          AND DscSubClasseConsumidor = 'Residencial'
          AND NomTipoMercado IN ('Regular', 'Sistema Isolado - Regular')
          AND upper(DscOpcaoEnergia) = 'CATIVO'
        LIMIT 1
        """,
        [detalhe, mes, valor, DATA, hash_linha, cnpj],
    )


def test_tarifa_vigente(con):
    carregar_bronze(con)
    rodar_sql(con, PASTA_SQL)

    for dia, esperado in ((dt.date(2026, 4, 15), 769.18), (dt.date(2026, 5, 15), 798.86)):
        linha = con.execute(
            """
            SELECT tusd_mwh + te_mwh
            FROM silver_tarifa_residencial
            WHERE cnpj = 10835932000108
              AND inicio <= ?
              AND (fim IS NULL OR fim >= ?)
            ORDER BY inicio DESC
            LIMIT 1
            """,
            [dia, dia],
        ).fetchone()
        assert linha[0] == pytest.approx(esperado)


def test_precos_produtos_e_republicacao(con):
    carregar_bronze(con)
    rodar_sql(con, PASTA_SQL)

    assert con.execute("SELECT count(*) FROM silver_precos_combustivel").fetchone()[0] > 0
    assert {
        registro[0]
        for registro in con.execute("SELECT DISTINCT produto FROM silver_precos_combustivel").fetchall()
    } == {"gasolina_c", "etanol_hidratado"}

    linha = con.execute(
        """
        SELECT preco_medio, postos FROM silver_precos_combustivel
        WHERE uf = 'PE' AND produto = 'gasolina_c' AND mes = DATE '2015-03-01'
        """
    ).fetchone()
    assert linha == (3.25, 1534)

    con.execute(
        "INSERT INTO bronze_anp VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            dt.date(2015, 3, 1),
            "GASOLINA COMUM",
            "PE",
            999,
            "R$/l",
            3.99,
            "manual",
            dt.datetime(2030, 1, 1),
            "manual-precos",
        ],
    )
    rodar_sql(con, PASTA_SQL)

    linhas = con.execute(
        """
        SELECT preco_medio, postos FROM silver_precos_combustivel
        WHERE uf = 'PE' AND produto = 'gasolina_c' AND mes = DATE '2015-03-01'
        """
    ).fetchall()
    assert linhas == [(3.99, 999)]


def test_ipca_versus_ibge(con):
    carregar_bronze(con)
    rodar_sql(con, PASTA_SQL)

    anos = {
        int(ano): (produto - 1) * 100
        for ano, produto in con.execute(
            "SELECT year(mes), product(1 + variacao / 100) FROM silver_ipca GROUP BY 1"
        ).fetchall()
    }
    esperado = {2012: 5.84, 2015: 10.67, 2021: 10.06, 2022: 5.79, 2024: 4.83, 2025: 4.26}
    for ano, valor in esperado.items():
        assert anos[ano] == pytest.approx(valor, abs=0.02)


def test_salario_nao_passou_ipca(con):
    carregar_bronze(con)
    rodar_sql(con, PASTA_SQL)

    limite = con.execute("SELECT max(mes) FROM silver_ipca").fetchone()[0]
    ultimo = con.execute("SELECT max(mes) FROM silver_salario_minimo").fetchone()[0]
    assert ultimo <= limite


def test_aliquota_neoenergia_2024_06(con):
    carregar_bronze(con)
    rodar_sql(con, PASTA_SQL)

    linha = con.execute(
        """
        SELECT icms, imputado FROM silver_aliquota_energia
        WHERE cnpj = 10835932000108 AND mes = DATE '2024-06-01'
        """
    ).fetchone()
    assert linha[0] == pytest.approx(0.1995, abs=1e-4)
    assert linha[1] is False
    assert con.execute("SELECT count(*) FROM silver_aliquota_energia WHERE icms IS NULL").fetchone()[0] == 0


def test_aliquota_invalida_imputada(con):
    carregar_bronze(con)
    inserir_samp(con, 10835932000108, dt.date(2024, 2, 1), "Receita Energia (R$)", 0.30, "manual-receita")
    inserir_samp(con, 10835932000108, dt.date(2024, 2, 1), "ICMS (R$)", 0.70, "manual-icms")
    rodar_sql(con, PASTA_SQL)

    linha = con.execute(
        """
        SELECT icms, imputado FROM silver_aliquota_energia
        WHERE cnpj = 10835932000108 AND mes = DATE '2024-02-01'
        """
    ).fetchone()
    vizinho = con.execute(
        """
        SELECT icms FROM silver_aliquota_energia
        WHERE cnpj = 10835932000108 AND mes = DATE '2024-06-01'
        """
    ).fetchone()[0]
    assert linha[1] is True
    assert linha[0] == pytest.approx(vizinho, abs=1e-12)


def test_aliquota_mes_sem_dado_paga_anterior(con):
    carregar_bronze(con)
    rodar_sql(con, PASTA_SQL)

    atual = con.execute(
        """
        SELECT icms, imputado FROM silver_aliquota_energia
        WHERE cnpj = 10835932000108 AND mes = DATE '2012-02-01'
        """
    ).fetchone()
    anterior = con.execute(
        """
        SELECT icms FROM silver_aliquota_energia
        WHERE cnpj = 10835932000108 AND mes = DATE '2012-01-01'
        """
    ).fetchone()[0]
    assert atual[1] is True
    assert atual[0] == pytest.approx(anterior, abs=1e-12)


def test_rodar_sql_idempotente(con):
    carregar_bronze(con)

    primeira = rodar_sql(con, PASTA_SQL)
    segunda = rodar_sql(con, PASTA_SQL)

    assert primeira == segunda
    assert len(primeira) == 8
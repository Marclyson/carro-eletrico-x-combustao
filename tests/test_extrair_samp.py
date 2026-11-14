import json
from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

from custo_km.extrair_samp import aliquota_efetiva, carregar_samp, url_recurso

PASTA_SAMP = Path(__file__).parent / "fixtures" / "samp"
AMOSTRA_2012 = PASTA_SAMP / "samp-2012.parquet"
AMOSTRA_2024 = PASTA_SAMP / "samp-2024.parquet"


@pytest.fixture
def con():
    conexao = duckdb.connect(":memory:")
    yield conexao
    conexao.close()


def carregar_2012(conexao):
    return carregar_samp(conexao, AMOSTRA_2012, datetime(2024, 1, 1))


def carregar_2024(conexao):
    return carregar_samp(conexao, AMOSTRA_2024, datetime(2024, 1, 1))


def _alterar_parquet(conexao, destino, alterar_valor=False, alterar_data=False):
    con = conexao
    con.execute(f"CREATE OR REPLACE TABLE _origem AS SELECT * FROM read_parquet('{AMOSTRA_2012.as_posix()}')")
    con.execute("CREATE OR REPLACE TABLE _alterada AS SELECT * FROM _origem")
    residencial = "DscClasseConsumoMercado = 'Residencial'"
    if alterar_valor:
        con.execute(
            "UPDATE _alterada SET VlrMercado = VlrMercado + 1 "
            f"WHERE rowid IN (SELECT rowid FROM _alterada WHERE {residencial} ORDER BY rowid LIMIT 1)"
        )
    if alterar_data:
        con.execute(
            "UPDATE _alterada SET DatGeracaoConjuntoDados = CAST(DatGeracaoConjuntoDados + INTERVAL 1 DAY AS DATE) "
            f"WHERE rowid IN (SELECT rowid FROM _alterada WHERE {residencial} ORDER BY rowid LIMIT 1 OFFSET 1)"
        )
    con.execute(f"COPY _alterada TO '{destino.as_posix()}' (FORMAT PARQUET)")


def test_carregar_samp(con):
    assert carregar_2012(con) == 414
    assert carregar_2024(con) == 1411
    assert carregar_2012(con) == 0
    assert carregar_2024(con) == 0


def test_somente_residencial(con):
    carregar_2012(con)
    carregar_2024(con)
    outras = con.execute(
        "SELECT count(*) FROM bronze_samp WHERE DscClasseConsumoMercado <> 'Residencial'"
    ).fetchone()[0]
    assert outras == 0


def test_aliquota_efetiva(con):
    carregar_2012(con)
    carregar_2024(con)

    icms, pis_cofins = aliquota_efetiva(con, 10835932000108, date(2024, 6, 1))
    assert icms == pytest.approx(0.1995, abs=1e-4)

    icms, pis_cofins = aliquota_efetiva(con, 10835932000108, date(2012, 1, 1))
    assert icms == pytest.approx(0.2437, abs=1e-4)

    icms, pis_cofins = aliquota_efetiva(con, 61695227000193, date(2024, 1, 1))
    assert icms == pytest.approx(0.1532, abs=1e-4)

    icms, pis_cofins = aliquota_efetiva(con, 2341470000144, date(2024, 1, 1))
    assert icms == pytest.approx(0.1954, abs=1e-4)

    icms, pis_cofins = aliquota_efetiva(con, 10835932000108, date(2024, 6, 1))
    assert 0.02 <= pis_cofins <= 0.08

    assert aliquota_efetiva(con, 99999999999999, date(2024, 1, 1)) is None
    assert aliquota_efetiva(con, 10835932000108, date(2024, 3, 1)) is None


def test_hash_muda_com_valor(con, tmp_path):
    carregar_2012(con)
    destino = tmp_path / "samp-2012-alterado.parquet"
    _alterar_parquet(con, destino, alterar_valor=True)
    assert carregar_samp(con, destino, datetime(2024, 2, 1)) == 1


def test_hash_ignora_data_geracao(con, tmp_path):
    carregar_2012(con)
    destino = tmp_path / "samp-2012-data.parquet"
    _alterar_parquet(con, destino, alterar_data=True)
    assert carregar_samp(con, destino, datetime(2024, 2, 1)) == 0


def test_url_recurso():
    pacote = json.loads((PASTA_SAMP / "pacote-samp.json").read_text(encoding="utf-8"))
    assert url_recurso(pacote, "PARQUET", "samp-2024").endswith("samp-2024.parquet")
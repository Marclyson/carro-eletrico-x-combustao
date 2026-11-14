"""Extrai o SAMP da ANEEL (ICMS, PIS, Cofins e receita) para a camada bronze."""

import datetime as dt
import os
import pathlib

import duckdb

from custo_km.extrair_aneel import _literal_sql, baixar, buscar_pacote, url_recurso


def criar_tabela(con, caminho_parquet):
    """Cria bronze_samp com as colunas do Parquet mais os metadados de carga."""
    literal = _literal_sql(caminho_parquet)
    con.execute(
        f"CREATE TABLE IF NOT EXISTS bronze_samp AS SELECT * FROM read_parquet('{literal}') LIMIT 0"
    )
    con.execute("ALTER TABLE bronze_samp ADD COLUMN IF NOT EXISTS _data_extracao TIMESTAMP")
    con.execute("ALTER TABLE bronze_samp ADD COLUMN IF NOT EXISTS _hash_linha VARCHAR")


def carregar_samp(con, caminho_parquet, data_extracao):
    """Insere as linhas residenciais ainda ausentes e devolve quantas linhas novas entraram."""
    criar_tabela(con, caminho_parquet)
    literal = _literal_sql(caminho_parquet)

    colunas = [
        registro[0]
        for registro in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{literal}')").fetchall()
    ]
    colunas_hash = [coluna for coluna in colunas if coluna != "DatGeracaoConjuntoDados"]
    if not colunas_hash:
        raise ValueError("O Parquet do SAMP nao tem colunas suficientes para o hash")

    campos = ", ".join(f'"{coluna}"' for coluna in colunas_hash)
    expressao_hash = f"md5(to_json(ROW({campos})))"
    sql = (
        "INSERT INTO bronze_samp "
        f"SELECT *, ?, {expressao_hash} FROM read_parquet('{literal}') "
        "WHERE DscClasseConsumoMercado = 'Residencial' "
        f"AND {expressao_hash} NOT IN (SELECT _hash_linha FROM bronze_samp)"
    )
    resultado = con.execute(sql, [data_extracao])
    return int(resultado.fetchone()[0])


def aliquota_efetiva(con, cnpj, mes):
    """Devolve (icms / total, pis_cofins / total) da distribuidora no mes, ou None."""
    sql = """
        SELECT
            coalesce(sum(CASE WHEN DscDetalheMercado = 'ICMS (R$)' THEN VlrMercado END), 0) AS icms,
            coalesce(sum(CASE WHEN DscDetalheMercado = 'Receita Energia (R$)' THEN VlrMercado END), 0)
                AS receita_energia,
            coalesce(sum(CASE WHEN DscDetalheMercado = 'Receita Bandeiras (R$)' THEN VlrMercado END), 0)
                AS receita_bandeiras,
            coalesce(sum(CASE WHEN DscDetalheMercado = 'PIS/PASEP (R$)' THEN VlrMercado END), 0) AS pis,
            coalesce(sum(CASE WHEN DscDetalheMercado = 'COFINS (R$)' THEN VlrMercado END), 0) AS cofins,
            coalesce(sum(CASE WHEN DscDetalheMercado = 'PIS/COFINS (R$)' THEN VlrMercado END), 0) AS pis_cofins
        FROM bronze_samp
        WHERE NumCNPJAgenteDistribuidora = ?
          AND DatCompetencia = ?
          AND DscSubClasseConsumidor = 'Residencial'
          AND NomTipoMercado IN ('Regular', 'Sistema Isolado - Regular')
          AND upper(DscOpcaoEnergia) = 'CATIVO'
    """
    icms, receita_energia, receita_bandeiras, pis, cofins, pis_cofins = con.execute(sql, [cnpj, mes]).fetchone()
    total = receita_energia + receita_bandeiras + icms + pis + cofins + pis_cofins
    if not icms or not total:
        return None
    return icms / total, (pis + cofins + pis_cofins) / total


def main():
    """Baixa, le e carrega o SAMP de cada ano disponivel."""
    caminho_db = pathlib.Path(os.environ.get("CUSTO_KM_DB", "dados/custo_km.duckdb"))
    caminho_db.parent.mkdir(parents=True, exist_ok=True)

    pasta_destino = pathlib.Path("dados") / "bronze" / "samp"
    pasta_destino.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(caminho_db))
    try:
        data_extracao = dt.datetime.now()
        pacote = buscar_pacote("samp")
        for ano in range(2011, dt.date.today().year + 1):
            nome = f"samp-{ano}"
            try:
                url = url_recurso(pacote, "PARQUET", nome)
            except ValueError:
                print(f"{nome}: recurso nao encontrado, seguindo")
                continue
            destino = pasta_destino / f"{nome}.parquet"
            baixar(url, destino)
            inseridas = carregar_samp(con, destino, data_extracao)
            print(f"{nome}: {inseridas} linhas novas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
"""Exporta as tabelas da camada gold em arquivos Parquet."""

import os
import pathlib

import duckdb

RAIZ = pathlib.Path(__file__).resolve().parent.parent

PREFIXO = "gold_"
CHAVES = ("mes", "uf", "veiculo", "energia", "tributo")


def _literal(texto):
    """Escapa um caminho para uso dentro de uma string SQL do DuckDB."""
    return str(texto).replace("'", "''")


def _tabelas_gold(con):
    """Lista os nomes das tabelas gold_ no esquema principal, em ordem."""
    registros = con.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main' AND starts_with(table_name, 'gold_')
        ORDER BY table_name
        """
    ).fetchall()
    return [registro[0] for registro in registros]


def exportar(con, pasta):
    """Grava cada tabela gold_ em Parquet e devolve {arquivo: linhas}."""
    pasta = pathlib.Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)

    tabelas = _tabelas_gold(con)
    nomes = {tabela.removeprefix(PREFIXO) + ".parquet" for tabela in tabelas}
    for existente in pasta.glob("*.parquet"):
        if existente.name not in nomes:
            existente.unlink()

    resultado = {}
    for tabela in tabelas:
        colunas = [registro[0] for registro in con.execute(f'DESCRIBE "{tabela}"').fetchall()]
        chaves = [coluna for coluna in CHAVES if coluna in colunas]
        ordem = ""
        if chaves:
            ordem = " ORDER BY " + ", ".join(f'"{coluna}"' for coluna in chaves)

        destino = pasta / (tabela.removeprefix(PREFIXO) + ".parquet")
        con.execute(
            f"COPY (SELECT * FROM \"{tabela}\"{ordem}) TO '{_literal(destino)}' "
            "(FORMAT parquet, COMPRESSION zstd)"
        )
        linhas = con.execute(f'SELECT count(*) FROM "{tabela}"').fetchone()[0]
        resultado[destino.name] = int(linhas)
    return resultado


def main():
    """Exporta as tabelas gold do banco configurado para a pasta gold/."""
    caminho_db = pathlib.Path(os.environ.get("CUSTO_KM_DB", "dados/custo_km.duckdb"))
    pasta = RAIZ / "gold"

    con = duckdb.connect(str(caminho_db))
    try:
        for arquivo, linhas in exportar(con, pasta).items():
            print(f"{arquivo}: {linhas} linhas")
    finally:
        con.close()


if __name__ == "__main__":
    main()

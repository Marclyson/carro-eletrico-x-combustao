"""Transforma os dados da camada bronze em tabelas da camada silver."""

import os
import pathlib
import re

import duckdb

TABELA = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def rodar_sql(con, pasta, prefixo="silver"):
    """Executa os arquivos .sql com o prefixo pedido, em ordem alfabetica, e devolve (tabela, linhas)."""
    resultado = []
    for caminho in sorted(pathlib.Path(pasta).glob("*.sql")):
        if not caminho.name.startswith(prefixo):
            continue
        sql = caminho.read_text(encoding="utf-8")
        con.execute(sql)
        for tabela in TABELA.findall(sql):
            linhas = con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
            resultado.append((tabela, linhas))
    return resultado


def main():
    """Conecta no banco, roda a camada silver e imprime as tabelas geradas."""
    caminho_db = pathlib.Path(os.environ.get("CUSTO_KM_DB", "dados/custo_km.duckdb"))
    caminho_db.parent.mkdir(parents=True, exist_ok=True)
    pasta_sql = pathlib.Path(__file__).resolve().parent.parent / "sql"

    con = duckdb.connect(str(caminho_db))
    try:
        for prefixo in ("silver", "gold"):
            for tabela, linhas in rodar_sql(con, pasta_sql, prefixo):
                print(f"{tabela}: {linhas} linhas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
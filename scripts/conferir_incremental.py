"""Confere se a carga incremental e idempotente, rodando os extratores duas vezes."""

import importlib
import os
import pathlib
import sys
import tempfile

import duckdb

RAIZ = pathlib.Path(__file__).resolve().parent.parent
# Rodado como "python scripts/conferir_incremental.py", o Python só põe scripts/ no caminho de importação.
sys.path.insert(0, str(RAIZ))

MODULOS = (
    "extrair_anp",
    "extrair_aneel",
    "extrair_sgs",
    "extrair_mcti",
    "extrair_samp",
)


def contagens(con):
    """Devolve {tabela: linhas} de todas as tabelas bronze_ do banco."""
    registros = con.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main' AND starts_with(table_name, 'bronze_')
        ORDER BY table_name
        """
    ).fetchall()
    return {
        registro[0]: int(con.execute(f'SELECT count(*) FROM "{registro[0]}"').fetchone()[0])
        for registro in registros
    }


def _rodar_carga(caminho_db):
    """Roda todos os extratores no banco indicado e devolve as contagens bronze."""
    for nome in MODULOS:
        modulo = importlib.import_module(f"custo_km.{nome}")
        modulo.main()

    con = duckdb.connect(str(caminho_db))
    try:
        return contagens(con)
    finally:
        con.close()


def _imprimir(primeira, segunda):
    """Imprime a tabela de contagens das duas rodadas."""
    nomes = sorted(set(primeira) | set(segunda))
    largura = max([len("tabela"), *(len(nome) for nome in nomes)])
    print(f"{'tabela':<{largura}}  {'1ª':>8}  {'2ª':>8}  alterou")
    for nome in nomes:
        antes = primeira.get(nome, 0)
        depois = segunda.get(nome, 0)
        print(f"{nome:<{largura}}  {antes:>8}  {depois:>8}  {'sim' if antes != depois else 'não'}")


def main():
    """Roda a carga duas vezes num banco temporario e retorna 1 se algo mudou."""
    anterior = os.getcwd()
    variavel_anterior = os.environ.get("CUSTO_KM_DB")
    os.chdir(RAIZ)
    try:
        with tempfile.TemporaryDirectory() as temporario:
            caminho_db = pathlib.Path(temporario) / "custo_km.duckdb"
            os.environ["CUSTO_KM_DB"] = str(caminho_db)
            primeira = _rodar_carga(caminho_db)
            segunda = _rodar_carga(caminho_db)
    finally:
        os.chdir(anterior)
        if variavel_anterior is None:
            os.environ.pop("CUSTO_KM_DB", None)
        else:
            os.environ["CUSTO_KM_DB"] = variavel_anterior

    _imprimir(primeira, segunda)
    return 1 if primeira != segunda else 0


if __name__ == "__main__":
    sys.exit(main())
"""Extrai o fator medio mensal de emissao de CO2 do SIN do MCTI para a camada bronze."""

import datetime as dt
import hashlib
import json
import os
import pathlib

import duckdb
import openpyxl

TABELA = "bronze_mcti"


def _planilha(caminho):
    """Abre a primeira aba da planilha do MCTI em modo somente leitura."""
    return openpyxl.load_workbook(caminho, read_only=True, data_only=True)


def _valor(linha, indice):
    """Devolve o valor de uma coluna, tolerando linhas mais curtas."""
    return linha[indice] if linha is not None and indice < len(linha) else None


def _numero(valor):
    """Converte um fator para float; vazio vira None."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    return float(valor)


def _blocos(caminho):
    """Le a planilha e devolve pares (ano, linha do ano, linha dos fatores anuais, linha dos mensais)."""
    planilha = _planilha(caminho)
    try:
        linhas = list(planilha.active.iter_rows(values_only=True))
    finally:
        planilha.close()

    for indice, linha in enumerate(linhas):
        ano = _valor(linha, 0)
        if isinstance(ano, int) and not isinstance(ano, bool) and 2000 <= ano <= 2100:
            yield ano, linha, _valor(linhas, indice + 1), _valor(linhas, indice + 2)


def ler_mensais(caminho):
    """Le os fatores mensais (tCO2/MWh) de cada ano da planilha."""
    resultado = []
    for ano, _, _, mensais in _blocos(caminho):
        for indice in range(2, 14):
            fator = _numero(_valor(mensais, indice))
            if fator is None:
                continue
            resultado.append(
                {
                    "mes": dt.date(ano, indice - 1, 1),
                    "tco2_mwh": fator,
                }
            )
    return resultado


def ler_anuais(caminho):
    """Le o fator medio anual (tCO2/MWh) de cada ano da planilha."""
    resultado = {}
    for ano, _, anuais, _ in _blocos(caminho):
        fator = _numero(_valor(anuais, 14))
        if fator is None:
            continue
        resultado[ano] = fator
    return resultado


def sha256_arquivo(caminho):
    """Calcula o sha256 do arquivo inteiro."""
    digesto = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(65536), b""):
            digesto.update(bloco)
    return digesto.hexdigest()


def criar_tabela(con):
    """Cria a tabela bronze_mcti caso ainda nao exista."""
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA} (
            mes DATE,
            tco2_mwh DOUBLE,
            arquivo VARCHAR,
            sha256_arquivo VARCHAR,
            _data_extracao TIMESTAMP,
            _hash_linha VARCHAR
        )
        """
    )


def hash_linha(linha):
    """Calcula o hash usado para identificar uma linha de forma idempotente."""
    dados = {
        "mes": linha["mes"].isoformat(),
        "tco2_mwh": linha["tco2_mwh"],
    }
    return hashlib.sha256(json.dumps(dados, sort_keys=True).encode("utf-8")).hexdigest()


def carregar(con, linhas, arquivo, sha, data_extracao):
    """Insere as linhas ainda nao presentes na tabela e devolve quantas inseriu."""
    criar_tabela(con)
    existentes = {registro[0] for registro in con.execute(f"SELECT _hash_linha FROM {TABELA}").fetchall()}
    novas = []
    for linha in linhas:
        assinatura = hash_linha(linha)
        if assinatura in existentes:
            continue
        existentes.add(assinatura)
        novas.append(
            (
                linha["mes"],
                linha["tco2_mwh"],
                arquivo,
                sha,
                data_extracao,
                assinatura,
            )
        )

    if novas:
        con.executemany(
            f"INSERT INTO {TABELA} VALUES (?, ?, ?, ?, ?, ?)",
            novas,
        )
    return len(novas)


def _arquivos(pasta):
    """Lista as planilhas do MCTI em ordem alfabetica."""
    return sorted(pasta.glob("Inventario_*.xlsx"))


def main():
    """Le as planilhas do MCTI deixadas em dados/manual e carrega na camada bronze."""
    caminho_db = pathlib.Path(os.environ.get("CUSTO_KM_DB", "dados/custo_km.duckdb"))
    pasta_manual = pathlib.Path("dados") / "manual"

    arquivos = _arquivos(pasta_manual)
    if not arquivos:
        print(f"aviso: nenhuma planilha encontrada em {pasta_manual}; nada a carregar")
        return 0

    caminho_db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(caminho_db))
    try:
        data_extracao = dt.datetime.now()
        for arquivo in arquivos:
            sha = sha256_arquivo(arquivo)
            linhas = ler_mensais(arquivo)
            inseridas = carregar(con, linhas, arquivo.name, sha, data_extracao)
            if linhas:
                primeiro = min(linha["mes"] for linha in linhas)
                ultimo = max(linha["mes"] for linha in linhas)
            else:
                primeiro = ultimo = None
            print(f"{arquivo.name}: {inseridas} linhas novas ({primeiro} a {ultimo})")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    main()
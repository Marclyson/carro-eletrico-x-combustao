"""Extrai as series SGS 433 (IPCA) e 1619 (salario minimo) do Banco Central para a camada bronze."""

import datetime as dt
import hashlib
import json
import os
import pathlib
import time
import urllib.request

import duckdb

BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
# A API do SGS recusa User-Agent personalizado (devolve uma página HTML de erro); usamos o padrão do urllib.

CODIGOS = (433, 1619)


def url_sgs(codigo):
    """Devolve a url da serie SGS pedida."""
    return BASE_URL.format(codigo=codigo)


def baixar_json(url):
    """Baixa e interpreta um JSON do Banco Central, com novas tentativas."""
    ultimo_erro = None
    for tentativa in range(3):
        try:
            requisicao = urllib.request.Request(url)
            with urllib.request.urlopen(requisicao, timeout=60) as resposta:
                return json.loads(resposta.read().decode("utf-8"))
        except (OSError, ValueError) as erro:
            ultimo_erro = erro
            if tentativa < 2:
                time.sleep(5)
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")


def criar_tabela(con):
    """Cria a tabela bronze_sgs caso ainda nao exista."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS bronze_sgs (
            codigo INTEGER,
            data DATE,
            valor DOUBLE,
            _data_extracao TIMESTAMP,
            _hash_linha VARCHAR
        )
        """
    )


def _interpretar(codigo, linha):
    """Converte uma linha dd/mm/aaaa com valor textual para os tipos da tabela."""
    data = dt.datetime.strptime(linha["data"].strip(), "%d/%m/%Y").date()
    return {
        "codigo": codigo,
        "data": data,
        "valor": float(linha["valor"]),
    }


def _hash_sgs(codigo, data, valor):
    """Calcula o hash usado para identificar uma linha da serie SGS."""
    dados = {"codigo": codigo, "data": data.isoformat(), "valor": valor}
    return hashlib.sha256(json.dumps(dados, sort_keys=True).encode("utf-8")).hexdigest()


def carregar_sgs(con, codigo, linhas, data_extracao):
    """Insere as linhas da serie ainda ausentes e devolve quantas entraram."""
    criar_tabela(con)
    existentes = {registro[0] for registro in con.execute("SELECT _hash_linha FROM bronze_sgs").fetchall()}
    novas = []
    for linha in linhas:
        interpretada = _interpretar(codigo, linha)
        assinatura = _hash_sgs(codigo, interpretada["data"], interpretada["valor"])
        if assinatura in existentes:
            continue
        existentes.add(assinatura)
        novas.append(
            (
                interpretada["codigo"],
                interpretada["data"],
                interpretada["valor"],
                data_extracao,
                assinatura,
            )
        )

    if novas:
        con.executemany("INSERT INTO bronze_sgs VALUES (?, ?, ?, ?, ?)", novas)
    return len(novas)


def main():
    """Baixa e carrega as series SGS 433 e 1619."""
    caminho_db = pathlib.Path(os.environ.get("CUSTO_KM_DB", "dados/custo_km.duckdb"))
    caminho_db.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(caminho_db))
    try:
        criar_tabela(con)
        data_extracao = dt.datetime.now()
        for codigo in CODIGOS:
            linhas = baixar_json(url_sgs(codigo))
            inseridas = carregar_sgs(con, codigo, linhas, data_extracao)
            print(f"SGS {codigo}: {inseridas} linhas novas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
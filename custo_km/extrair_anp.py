"""Extrai precos de combustiveis da ANP para a camada bronze."""

import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import time
import unicodedata
import urllib.request

import duckdb
import openpyxl

BASE_URL = (
    "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/"
    "precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/"
)

PLANILHAS = (
    "2001-2012/mensal-estados-2001-a-2012.xlsx",
    "mensal/mensal-estados-desde-jan2013.xlsx",
    "mensal/mensal-brasil-desde-jan2013.xlsx",
)

UF_POR_NOME = {
    "ACRE": "AC",
    "ALAGOAS": "AL",
    "AMAPA": "AP",
    "AMAZONAS": "AM",
    "BAHIA": "BA",
    "CEARA": "CE",
    "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES",
    "GOIAS": "GO",
    "MARANHAO": "MA",
    "MATO GROSSO": "MT",
    "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG",
    "PARA": "PA",
    "PARAIBA": "PB",
    "PARANA": "PR",
    "PERNAMBUCO": "PE",
    "PIAUI": "PI",
    "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS",
    "RONDONIA": "RO",
    "RORAIMA": "RR",
    "SANTA CATARINA": "SC",
    "SAO PAULO": "SP",
    "SERGIPE": "SE",
    "TOCANTINS": "TO",
}


def sem_acento(texto):
    """Devolve o texto sem acentos, em maiusculas e com espacos normalizados."""
    if texto is None:
        return ""
    normalizado = unicodedata.normalize("NFKD", str(texto))
    sem_marcas = "".join(caractere for caractere in normalizado if not unicodedata.combining(caractere))
    return " ".join(sem_marcas.upper().split())


def numero(valor):
    """Converte um valor de preco para float; vazio e traco viram None."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if texto in ("", "-"):
        return None
    return float(texto)


def ler_planilha(caminho):
    """Le uma planilha da ANP e devolve uma linha por registro de dado."""
    planilha = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        linhas = planilha.active.iter_rows(values_only=True)
        cabecalho = None
        for linha in linhas:
            if not linha:
                continue
            coluna_a = sem_acento(linha[0]) if len(linha) > 0 else ""
            coluna_b = sem_acento(linha[1]) if len(linha) > 1 else ""
            if coluna_a == "MES" and coluna_b == "PRODUTO":
                cabecalho = linha
                break

        if cabecalho is None:
            return []

        nomes = [sem_acento(coluna) for coluna in cabecalho]
        indice_mes = nomes.index("MES")
        indice_produto = nomes.index("PRODUTO")
        indice_postos = nomes.index("NUMERO DE POSTOS PESQUISADOS")
        indice_unidade = nomes.index("UNIDADE DE MEDIDA")
        indice_preco = nomes.index("PRECO MEDIO REVENDA")
        indice_estado = nomes.index("ESTADO") if "ESTADO" in nomes else None

        resultado = []
        for linha in linhas:
            if not linha:
                continue
            mes_bruto = linha[indice_mes] if indice_mes < len(linha) else None
            if not isinstance(mes_bruto, (dt.date, dt.datetime)):
                continue
            mes = mes_bruto.date() if isinstance(mes_bruto, dt.datetime) else mes_bruto
            mes = mes.replace(day=1)

            produto = sem_acento(linha[indice_produto])
            if not produto:
                continue

            if indice_estado is None:
                uf = "BR"
            else:
                estado = linha[indice_estado] if indice_estado < len(linha) else None
                uf = UF_POR_NOME.get(sem_acento(estado))
                if uf is None:
                    raise ValueError(f"Estado nao reconhecido: {estado!r}")

            postos_bruto = linha[indice_postos] if indice_postos < len(linha) else None
            postos = None if postos_bruto in (None, "", "-") else int(postos_bruto)
            unidade_bruto = linha[indice_unidade] if indice_unidade < len(linha) else None
            unidade = "" if unidade_bruto is None else str(unidade_bruto)
            preco = numero(linha[indice_preco]) if indice_preco < len(linha) else None

            resultado.append(
                {
                    "mes": mes,
                    "produto": produto,
                    "uf": uf,
                    "postos": postos,
                    "unidade": unidade,
                    "preco_medio_revenda": preco,
                }
            )

        return resultado
    finally:
        planilha.close()


def criar_tabela(con):
    """Cria a tabela bronze_anp caso ainda nao exista."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS bronze_anp (
            mes DATE,
            produto VARCHAR,
            uf VARCHAR,
            postos INTEGER,
            unidade VARCHAR,
            preco_medio_revenda DOUBLE,
            arquivo VARCHAR,
            _data_extracao TIMESTAMP,
            _hash_linha VARCHAR
        )
        """
    )


def hash_linha(linha):
    """Calcula o hash usado para identificar uma linha de forma idempotente."""
    dados = {
        "mes": linha["mes"].isoformat(),
        "produto": linha["produto"],
        "uf": linha["uf"],
        "postos": linha["postos"],
        "unidade": linha["unidade"],
        "preco_medio_revenda": linha["preco_medio_revenda"],
    }
    return hashlib.sha256(json.dumps(dados, sort_keys=True).encode("utf-8")).hexdigest()


def carregar(con, linhas, arquivo, data_extracao):
    """Insere as linhas ainda nao presentes na tabela e devolve quantas inseriu."""
    criar_tabela(con)
    existentes = {registro[0] for registro in con.execute("SELECT _hash_linha FROM bronze_anp").fetchall()}
    novas = []
    for linha in linhas:
        assinatura = hash_linha(linha)
        if assinatura in existentes:
            continue
        existentes.add(assinatura)
        novas.append(
            (
                linha["mes"],
                linha["produto"],
                linha["uf"],
                linha["postos"],
                linha["unidade"],
                linha["preco_medio_revenda"],
                arquivo,
                data_extracao,
                assinatura,
            )
        )

    if novas:
        con.executemany(
            "INSERT INTO bronze_anp VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            novas,
        )
    return len(novas)


def meses_ausentes(con, produto, uf, inicio, fim):
    """Lista os meses entre inicio e fim que nao tem linha na tabela bronze_anp."""
    criar_tabela(con)
    existentes = {
        registro[0]
        for registro in con.execute(
            "SELECT DISTINCT mes FROM bronze_anp WHERE produto = ? AND uf = ? AND mes >= ? AND mes <= ?",
            [produto, uf, inicio, fim],
        ).fetchall()
    }

    ausentes = []
    ano = inicio.year
    mes = inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        data = dt.date(ano, mes, 1)
        if data not in existentes:
            ausentes.append(data)
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
    return ausentes


def baixar(url, destino):
    """Baixa um arquivo da ANP com novas tentativas em caso de falha."""
    ultimo_erro = None
    for tentativa in range(3):
        try:
            requisicao = urllib.request.Request(url, headers={"User-Agent": "custo-km/0.1"})
            with urllib.request.urlopen(requisicao, timeout=120) as resposta, open(destino, "wb") as arquivo:
                shutil.copyfileobj(resposta, arquivo)
            return
        except OSError as erro:
            ultimo_erro = erro
            if tentativa < 2:
                time.sleep(5)
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")


def main():
    """Baixa, le e carrega as tres planilhas mensais da ANP."""
    caminho_db = pathlib.Path(os.environ.get("CUSTO_KM_DB", "dados/custo_km.duckdb"))
    caminho_db.parent.mkdir(parents=True, exist_ok=True)

    hoje = dt.date.today().isoformat()
    pasta_destino = pathlib.Path("dados") / "bronze" / "anp" / hoje
    pasta_destino.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(caminho_db))
    try:
        criar_tabela(con)
        data_extracao = dt.datetime.now()

        for planilha in PLANILHAS:
            destino = pasta_destino / pathlib.Path(planilha).name
            baixar(BASE_URL + planilha, destino)
            linhas = ler_planilha(destino)
            inseridas = carregar(con, linhas, destino.as_posix(), data_extracao)
            print(f"{destino.name}: {inseridas} linhas novas")

        ultimo_mes = con.execute(
            "SELECT max(mes) FROM bronze_anp WHERE produto = ? AND uf = ?",
            ["GASOLINA COMUM", "BR"],
        ).fetchone()[0]
        if ultimo_mes is None:
            ausentes = []
        else:
            ausentes = meses_ausentes(
                con,
                "GASOLINA COMUM",
                "BR",
                dt.date(2013, 1, 1),
                ultimo_mes,
            )
        print(
            "meses ausentes de GASOLINA COMUM no BR desde 2013-01-01: "
            f"{[mes.isoformat() for mes in ausentes]}"
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
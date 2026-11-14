"""Extrai tarifas homologadas e bandeiras tarifarias da ANEEL para a camada bronze."""

import csv
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import shutil
import time
import urllib.parse
import urllib.request

import duckdb

BASE_URL = "https://dadosabertos.aneel.gov.br/api/3/action/package_show"
USER_AGENT = "custo-km/0.1"


def url_recurso(pacote_json, formato, nome_contem=""):
    """Devolve a url do primeiro recurso do pacote com o formato e nome pedidos."""
    recursos = pacote_json.get("result", {}).get("resources", [])
    alvo = formato.upper()
    for recurso in recursos:
        if str(recurso.get("format", "")).upper() != alvo:
            continue
        if nome_contem not in str(recurso.get("name", "")):
            continue
        return recurso["url"]
    raise ValueError(f"Recurso {formato!r} contendo {nome_contem!r} nao encontrado")


def buscar_pacote(id):
    """Busca os metadados de um pacote do CKAN da ANEEL, com novas tentativas."""
    url = f"{BASE_URL}?{urllib.parse.urlencode({'id': id})}"
    ultimo_erro = None
    for tentativa in range(3):
        try:
            requisicao = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(requisicao, timeout=60) as resposta:
                return json.loads(resposta.read().decode("utf-8"))
        except (OSError, ValueError) as erro:
            ultimo_erro = erro
            if tentativa < 2:
                time.sleep(5)
    raise RuntimeError(f"Falha ao buscar o pacote {id}: {ultimo_erro}")


def baixar(url, destino):
    """Baixa um recurso da ANEEL com novas tentativas em caso de falha."""
    ultimo_erro = None
    for tentativa in range(3):
        try:
            requisicao = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(requisicao, timeout=60) as resposta, open(destino, "wb") as arquivo:
                shutil.copyfileobj(resposta, arquivo)
            return
        except OSError as erro:
            ultimo_erro = erro
            if tentativa < 2:
                time.sleep(5)
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")


def _literal_sql(texto):
    """Escapa um caminho para uso dentro de uma string SQL do DuckDB."""
    return str(texto).replace("'", "''")


def _criar_tabela_tarifa(con, caminho_parquet):
    """Cria bronze_tarifa com as colunas do Parquet mais os metadados de carga."""
    literal = _literal_sql(caminho_parquet)
    con.execute(
        f"CREATE TABLE IF NOT EXISTS bronze_tarifa AS SELECT * FROM read_parquet('{literal}') LIMIT 0"
    )
    con.execute("ALTER TABLE bronze_tarifa ADD COLUMN IF NOT EXISTS _data_extracao TIMESTAMP")
    con.execute("ALTER TABLE bronze_tarifa ADD COLUMN IF NOT EXISTS _hash_linha VARCHAR")


def _criar_tabela_bandeira(con):
    """Cria a tabela bronze_bandeira caso ainda nao exista."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS bronze_bandeira (
            competencia DATE,
            bandeira VARCHAR,
            adicional_mwh DOUBLE,
            _data_extracao TIMESTAMP,
            _hash_linha VARCHAR
        )
        """
    )


def _descobrir_parquet_tarifas():
    """Descobre o Parquet de tarifas mais recente, quando nenhum caminho e informado."""
    pasta = pathlib.Path("dados") / "bronze" / "aneel"
    encontrados = sorted(pasta.glob("*/tarifas-homologadas-distribuidoras-energia-eletrica.parquet"))
    if encontrados:
        return encontrados[-1]
    fixture = pathlib.Path("tests/fixtures/aneel/tarifas.parquet")
    if fixture.exists():
        return fixture
    return None


def criar_tabelas(con, caminho_parquet=None):
    """Cria bronze_tarifa (a partir do Parquet) e bronze_bandeira."""
    if caminho_parquet is None:
        caminho_parquet = _descobrir_parquet_tarifas()
    if caminho_parquet is not None:
        _criar_tabela_tarifa(con, caminho_parquet)
    _criar_tabela_bandeira(con)


def carregar_tarifas(con, caminho_parquet, data_extracao):
    """Insere as tarifas ainda ausentes e devolve quantas linhas novas entraram."""
    _criar_tabela_tarifa(con, caminho_parquet)
    literal = _literal_sql(caminho_parquet)

    colunas = [
        registro[0]
        for registro in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{literal}')").fetchall()
    ]
    colunas_hash = [coluna for coluna in colunas if coluna != "DatGeracaoConjuntoDados"]
    if not colunas_hash:
        raise ValueError("O Parquet de tarifas nao tem colunas suficientes para o hash")

    campos = ", ".join(f'"{coluna}"' for coluna in colunas_hash)
    expressao_hash = f"md5(to_json(ROW({campos})))"
    sql = (
        "INSERT INTO bronze_tarifa "
        f"SELECT *, ?, {expressao_hash} FROM read_parquet('{literal}') "
        f"WHERE {expressao_hash} NOT IN (SELECT _hash_linha FROM bronze_tarifa)"
    )
    resultado = con.execute(sql, [data_extracao])
    return int(resultado.fetchone()[0])


def _ler_texto(caminho):
    """Le um arquivo de texto, aceitando UTF-8 ou latin1."""
    bruto = pathlib.Path(caminho).read_bytes()
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("latin1")


def _numero_br(texto):
    """Converte um numero escrito com virgula decimal para float."""
    if texto is None:
        return None
    limpo = str(texto).strip()
    if limpo == "":
        return None
    if "," in limpo:
        return float(limpo.replace(".", "").replace(",", "."))
    return float(limpo)


def ler_bandeiras(caminho_csv):
    """Le o CSV de acionamento de bandeiras e devolve uma linha por competencia."""
    texto = _ler_texto(caminho_csv)
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";", quotechar='"')
    linhas = []
    for registro in leitor:
        competencia = dt.date.fromisoformat(registro["DatCompetencia"].strip())
        linhas.append(
            {
                "competencia": competencia,
                "bandeira": registro["NomBandeiraAcionada"].strip(),
                "adicional_mwh": _numero_br(registro["VlrAdicionalBandeira"]),
            }
        )
    return linhas


def _hash_bandeira(linha):
    """Calcula o hash usado para identificar uma linha de bandeira."""
    dados = {
        "competencia": linha["competencia"].isoformat(),
        "bandeira": linha["bandeira"],
        "adicional_mwh": linha["adicional_mwh"],
    }
    return hashlib.sha256(json.dumps(dados, sort_keys=True).encode("utf-8")).hexdigest()


def carregar_bandeiras(con, linhas, data_extracao):
    """Insere as bandeiras ainda ausentes e devolve quantas linhas novas entraram."""
    _criar_tabela_bandeira(con)
    existentes = {registro[0] for registro in con.execute("SELECT _hash_linha FROM bronze_bandeira").fetchall()}
    novas = []
    for linha in linhas:
        assinatura = _hash_bandeira(linha)
        if assinatura in existentes:
            continue
        existentes.add(assinatura)
        novas.append(
            (
                linha["competencia"],
                linha["bandeira"],
                linha["adicional_mwh"],
                data_extracao,
                assinatura,
            )
        )

    if novas:
        con.executemany("INSERT INTO bronze_bandeira VALUES (?, ?, ?, ?, ?)", novas)
    return len(novas)


def main():
    """Baixa, le e carrega as tarifas e bandeiras da ANEEL."""
    caminho_db = pathlib.Path(os.environ.get("CUSTO_KM_DB", "dados/custo_km.duckdb"))
    caminho_db.parent.mkdir(parents=True, exist_ok=True)

    hoje = dt.date.today().isoformat()
    pasta_destino = pathlib.Path("dados") / "bronze" / "aneel" / hoje
    pasta_destino.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(caminho_db))
    try:
        data_extracao = dt.datetime.now()

        tarifas_url = url_recurso(
            buscar_pacote("tarifas-distribuidoras-energia-eletrica"), "PARQUET"
        )
        destino_tarifas = pasta_destino / "tarifas-homologadas-distribuidoras-energia-eletrica.parquet"
        baixar(tarifas_url, destino_tarifas)

        bandeiras_url = url_recurso(
            buscar_pacote("bandeiras-tarifarias"), "CSV", "Acionamento"
        )
        destino_bandeiras = pasta_destino / "bandeira-acionamento.csv"
        baixar(bandeiras_url, destino_bandeiras)

        criar_tabelas(con, destino_tarifas)

        inseridas_tarifas = carregar_tarifas(con, destino_tarifas, data_extracao)
        print(f"{destino_tarifas.name}: {inseridas_tarifas} linhas novas")

        inseridas_bandeiras = carregar_bandeiras(
            con, ler_bandeiras(destino_bandeiras), data_extracao
        )
        print(f"{destino_bandeiras.name}: {inseridas_bandeiras} linhas novas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
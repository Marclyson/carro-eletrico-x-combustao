"""Modelo semântico (TMDL) do painel: tabelas, relações e medidas.

Chamado por gerar_pbip.py. Tudo é gerado do zero a cada execução, com lineageTag estável (uuid5 do nome),
para o Power BI reconhecer os mesmos objetos depois de regenerar.
"""

import re
import uuid
from pathlib import Path

PASTA_GOLD_PADRAO = r"C:\repo\carro-eletrico-x-combustao\gold" + "\\"
PASTA_REF_PADRAO = r"C:\repo\carro-eletrico-x-combustao\referencias" + "\\"


def uid(semente: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "carro-eletrico-x-combustao/" + semente))


def q(nome: str) -> str:
    """Nome de objeto TMDL, entre aspas simples quando precisa."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nome):
        return nome
    return "'" + nome.replace("'", "''") + "'"


TIPO_M = {"string": "type text", "int64": "Int64.Type", "double": "type number", "date": "type date",
          "boolean": "type logical"}


class Col:
    def __init__(self, nome, origem=None, tipo="string", oculta=False, fmt=None, chave=False, ordenar=None, desc=None):
        self.nome, self.origem, self.tipo = nome, origem or nome, tipo
        self.oculta, self.fmt, self.chave, self.ordenar, self.desc = oculta, fmt, chave, ordenar, desc

    def tmdl(self, tabela: str) -> str:
        tipo = "dateTime" if self.tipo == "date" else self.tipo
        t = f"\t/// {self.desc}\n" if self.desc else ""
        t += f"\tcolumn {q(self.nome)}\n\t\tdataType: {tipo}\n"
        if self.chave:
            t += "\t\tisKey\n"
        if self.oculta:
            t += "\t\tisHidden\n"
        fmt = self.fmt or ("mmm/yyyy" if self.tipo == "date" else None)
        if fmt:
            t += f"\t\tformatString: {fmt}\n"
        t += f"\t\tlineageTag: {uid(f'c/{tabela}/{self.nome}')}\n\t\tsummarizeBy: none\n\t\tsourceColumn: {self.nome}\n"
        if self.ordenar:
            t += f"\t\tsortByColumn: {q(self.ordenar)}\n"
        if self.tipo == "date":
            t += "\n\t\tannotation UnderlyingDateTimeDataType = Date\n"
        return t + "\n"


def m_indent(m: str) -> str:
    return "".join(f"\t\t\t\t{linha}\n" for linha in m.strip("\n").split("\n"))


def m_parquet(arquivo: str, cols: list[Col]) -> str:
    origens = ", ".join(f'"{c.origem}"' for c in cols)
    renomear = ", ".join(f'{{"{c.origem}", "{c.nome}"}}' for c in cols if c.origem != c.nome)
    tipos = ", ".join(f'{{"{c.nome}", {TIPO_M[c.tipo]}}}' for c in cols)
    passos = [f'Fonte = Parquet.Document(File.Contents(PastaGold & "{arquivo}"))',
              f"Colunas = Table.SelectColumns(Fonte, {{{origens}}})"]
    ultimo = "Colunas"
    if renomear:
        passos.append(f"Nomes = Table.RenameColumns(Colunas, {{{renomear}}})")
        ultimo = "Nomes"
    passos.append(f"Tipos = Table.TransformColumnTypes({ultimo}, {{{tipos}}})")
    return "let\n" + ",\n".join("    " + p for p in passos) + "\nin\n    Tipos"


def m_tabela_fixa(cols: list[Col], linhas: list[tuple]) -> str:
    tipo = ", ".join(f'#"{c.nome}" = {TIPO_M[c.tipo]}' for c in cols)

    def val(v):
        if v is None:
            return "null"
        if isinstance(v, str):
            return '"' + v.replace('"', '""') + '"'
        return repr(v)

    corpo = ",\n".join("        {" + ", ".join(val(v) for v in linha) + "}" for linha in linhas)
    return f"let\n    Fonte = #table(\n        type table [{tipo}],\n        {{\n{corpo}\n        }})\nin\n    Fonte"


def m_serie(col: Col, inicio, n, passo) -> str:
    return (f'let\n    Fonte = #table(type table [#"{col.nome}" = {TIPO_M[col.tipo]}], '
            f"List.Transform(List.Numbers({inicio}, {n}, {passo}), each {{_}}))\nin\n    Fonte")


class Tabela:
    def __init__(self, nome, desc, cols, m, oculta=False, data_category=None):
        self.nome, self.desc, self.cols, self.m = nome, desc, cols, m
        self.oculta, self.data_category = oculta, data_category
        self.medidas: list[str] = []

    def tmdl(self) -> str:
        t = f"/// {self.desc}\ntable {q(self.nome)}\n"
        if self.oculta:
            t += "\tisHidden\n"
        t += f"\tlineageTag: {uid('t/' + self.nome)}\n"
        if self.data_category:
            t += f"\tdataCategory: {self.data_category}\n"
        t += "\n" + "".join(self.medidas) + "".join(c.tmdl(self.nome) for c in self.cols)
        t += f"\tpartition {q(self.nome)} = m\n\t\tmode: import\n\t\tsource =\n{m_indent(self.m)}\n"
        t += "\tannotation PBI_ResultType = Table\n"
        return t


def medida(nome, expr, fmt=None, pasta=None, desc=None, oculta=False) -> str:
    linhas = expr.strip("\n").split("\n")
    if len(linhas) == 1:
        t = f"\tmeasure {q(nome)} = {linhas[0]}\n"
    else:
        t = f"\tmeasure {q(nome)} =\n" + "".join(f"\t\t\t{linha}\n" for linha in linhas)
    if desc:
        t = f"\t/// {desc}\n" + t
    if fmt:
        t += f"\t\tformatString: {fmt}\n"
    if oculta:
        t += "\t\tisHidden\n"
    if pasta:
        t += f"\t\tdisplayFolder: {pasta}\n"
    return t + f"\t\tlineageTag: {uid('m/' + nome)}\n\n"


def dax_txt(s: str) -> str:
    """Literal de texto DAX."""
    return '"' + s.replace('"', '""') + '"'


# ----------------------------------------------------------------------------------------------
# Tabelas
# ----------------------------------------------------------------------------------------------

COMPARACOES = [  # (rótulo, ordem, carro a combustão, carro elétrico, nome combustão, nome elétrico)
    ("Kwid × Dolphin Mini", 1, "kwid", "dolphin_mini", "Kwid", "Dolphin Mini"),
    ("Polo Track × Dolphin Mini", 2, "polo_track", "dolphin_mini", "Polo Track", "Dolphin Mini"),
    ("Kwid × E-KWID (fora de linha)", 3, "kwid", "e_kwid", "Kwid", "E-KWID"),
]
COMPARACAO_PADRAO = COMPARACOES[0][0]

METRICAS_MAPA = ["Custo do elétrico (R$/100 km)", "Custo da gasolina (R$/100 km)",
                 "Economia do elétrico (R$/100 km)", "ICMS efetivo da eletricidade"]


SERIES = [  # tabela, tipo, formato, início, quantidade, passo, descrição
    ("Km por ano", "int64", "#,0", 4000, 14, 2000, "Quilômetros rodados por ano no simulador"),
    ("Recarga em casa (%)", "int64", "0", 0, 11, 10, "Parte da energia do elétrico recarregada em casa"),
    ("Carregador público", "double", "0.00", 1, 11, 0.25, "Preço do kWh no carregador público"),
    ("Anos de uso", "int64", "0", 1, 15, 1, "Horizonte da conta do simulador"),
    ("Preço do carro a combustão (R$)", "int64", "#,0", 50000, 61, 2500, "Preço de compra escolhido"),
    ("Preço do carro elétrico (R$)", "int64", "#,0", 80000, 69, 2500, "Preço de compra escolhido"),
    ("Ano de uso", "int64", "0", 0, 16, 1, "Eixo da curva de custo acumulado"),
]
SERIE_COLUNA = {"Carregador público": "Carregador público (R$/kWh)"}  # "/" não pode ir no nome do arquivo da tabela


def tabelas() -> list[Tabela]:
    T = []

    cal = [Col("Mês", "mes", "date", chave=True, desc="Primeiro dia do mês"),
           Col("Ano", "ano", "int64", fmt="0"),
           Col("mes_num", tipo="int64", oculta=True),
           Col("ipca_variacao", tipo="double", oculta=True),
           Col("indice_ipca", tipo="double", oculta=True),
           Col("fator_real", tipo="double", oculta=True, desc="Multiplica um valor do mês para reais do último mês"),
           Col("salario_minimo", tipo="double", oculta=True)]
    T.append(Tabela("Calendário", "Meses de jan. 2012 ao último mês com todos os dados (gold/dim_tempo)", cal,
                    m_parquet("dim_tempo.parquet", cal), data_category="Time"))

    uf = [Col("UF", "uf", chave=True), Col("Estado", "nome"), Col("Região", "regiao"), Col("Capital", "capital"),
          Col("Distribuidora", "sig_agente"), Col("cnpj", tipo="int64", oculta=True)]
    T.append(Tabela("Estados", "UF, capital e distribuidora de energia da capital (gold/dim_uf)", uf,
                    m_parquet("dim_uf.parquet", uf)))

    vei = [Col("chave_veiculo", chave=True, oculta=True), Col("veiculo", oculta=True), Col("energia", oculta=True),
           Col("Modelo", "modelo"), Col("Versão", "versao"), Col("consumo_por_km", tipo="double", oculta=True),
           Col("unidade", oculta=True), Col("co2_escapamento_g_km", tipo="int64", oculta=True),
           Col("ano_pbe", tipo="int64", oculta=True)]
    T.append(Tabela("Veículos", "Carro e energia, com o consumo do PBE Veicular do Inmetro (gold/dim_veiculo)", vei,
                    m_parquet("dim_veiculo.parquet", vei)))

    ene = [Col("energia", chave=True, oculta=True), Col("Energia"), Col("ordem", tipo="int64", oculta=True)]
    ene[1].ordenar = "ordem"
    T.append(Tabela("Energias", "Gasolina, etanol e eletricidade", ene,
                    m_tabela_fixa(ene, [("gasolina", "Gasolina", 1), ("etanol", "Etanol", 2),
                                        ("eletricidade", "Eletricidade", 3)])))

    cus = [Col("mes", tipo="date", oculta=True), Col("uf", oculta=True), Col("chave_veiculo", oculta=True),
           Col("veiculo", oculta=True), Col("energia", oculta=True), Col("custo_km", tipo="double", oculta=True),
           Col("custo_km_real", tipo="double", oculta=True),
           Col("custo_km_sem_tributos_real", tipo="double", oculta=True),
           Col("horas_sm_100km", tipo="double", oculta=True), Col("co2_g_km", tipo="double", oculta=True),
           Col("icms_imputado", tipo="boolean", oculta=True), Col("tarifa_imputada", tipo="boolean", oculta=True)]
    T.append(Tabela("Custo por km", "Custo por km de cada carro e energia, por mês e UF (gold/fato_custo_km_mensal)",
                    cus, m_parquet("fato_custo_km_mensal.parquet", cus)))

    pre = [Col("mes", tipo="date", oculta=True), Col("uf", oculta=True), Col("energia", oculta=True),
           Col("preco", tipo="double", oculta=True), Col("unidade", oculta=True),
           Col("icms_unit", tipo="double", oculta=True), Col("pis_cofins_unit", tipo="double", oculta=True),
           Col("cide_unit", tipo="double", oculta=True), Col("preco_sem_tributos", tipo="double", oculta=True),
           Col("icms_imputado", tipo="boolean", oculta=True), Col("tarifa_imputada", tipo="boolean", oculta=True),
           Col("bandeira_kwh", tipo="double", oculta=True), Col("tarifa_branca_fp_kwh", tipo="double", oculta=True)]
    T.append(Tabela("Preço da energia", "Preço por litro ou kWh, com os tributos separados (gold/preco_energia_mensal)",
                    pre, m_parquet("preco_energia_mensal.parquet", pre)))

    car = [Col("veiculo", chave=True), Col("versao_site"), Col("preco_tabela", tipo="int64", fmt="#,0"),
           Col("preco_oferta", tipo="int64", fmt="#,0"), Col("data_consulta", tipo="date", fmt="dd/mm/yyyy"),
           Col("observacao"), Col("link_fonte")]
    tipos = ", ".join(f'{{"{c.nome}", {TIPO_M[c.tipo]}}}' for c in car)
    m_car = ("let\n"
             '    Fonte = Csv.Document(File.Contents(PastaReferencias & "precos_carros.csv"), '
             "[Delimiter = \",\", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),\n"
             "    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),\n"
             f'    Tipos = Table.TransformColumnTypes(Cabecalho, {{{tipos}}}, "en-US")\n'
             "in\n    Tipos")
    T.append(Tabela("Carros", "Preço de tabela no site oficial de cada montadora (referencias/precos_carros.csv)",
                    car, m_car, oculta=True))

    cmp_ = [Col("Comparação"), Col("ordem", tipo="int64", oculta=True), Col("carro_combustao", oculta=True),
            Col("carro_eletrico", oculta=True), Col("nome_combustao", oculta=True), Col("nome_eletrico", oculta=True)]
    cmp_[0].ordenar = "ordem"
    T.append(Tabela("Comparação", "Pares de carro a combustão e elétrico do painel", cmp_,
                    m_tabela_fixa(cmp_, COMPARACOES)))

    for nome, opcoes, desc in [
        ("Valores", ["Real", "Nominal"], "Real (corrigido pelo IPCA até o último mês) ou nominal"),
        ("Tributos", ["Com tributos", "Sem tributos"], "Preço ao consumidor ou sem os tributos separados"),
        ("Métrica do mapa", METRICAS_MAPA, "O que o mapa e o ranking de estados mostram"),
        ("Tarifa em casa", ["Convencional", "Branca (fora de ponta)"], "Tarifa de quem recarrega em casa"),
    ]:
        cols = [Col(nome), Col("ordem", tipo="int64", oculta=True)]
        cols[0].ordenar = "ordem"
        T.append(Tabela(nome, desc, cols, m_tabela_fixa(cols, [(o, i) for i, o in enumerate(opcoes, 1)])))

    for nome, tipo, fmt, ini, n, passo, desc in SERIES:
        c = Col(SERIE_COLUNA.get(nome, nome), tipo=tipo, fmt=fmt)
        T.append(Tabela(nome, desc, [c], m_serie(c, ini, n, passo)))

    T.append(Tabela("_Medidas", "Medidas do painel", [Col("_", oculta=True)],
                    'let\n    Fonte = #table(type table [#"_" = type text], {})\nin\n    Fonte'))
    return T


RELACOES = [
    ("Custo por km", "mes", "Calendário", "Mês"),
    ("Custo por km", "uf", "Estados", "UF"),
    ("Custo por km", "chave_veiculo", "Veículos", "chave_veiculo"),
    ("Preço da energia", "mes", "Calendário", "Mês"),
    ("Preço da energia", "uf", "Estados", "UF"),
    ("Preço da energia", "energia", "Energias", "energia"),
]


# ----------------------------------------------------------------------------------------------
# Medidas
# ----------------------------------------------------------------------------------------------

R2 = r"\R$ #,0.00"
R3 = r"\R$ #,0.000"
R0 = r"\R$ #,0"
JANELA = "DATESINPERIOD ( 'Calendário'[Mês], MAX ( 'Calendário'[Mês] ), -12, MONTH )"
FATOR = "IF ( _real, RELATED ( 'Calendário'[fator_real] ), 1 )"


def _filtro_carro(var_carro: str, sufixo: str) -> str:
    return f"""VAR _ch = [{var_carro}] & "_{sufixo}"
RETURN"""


def medidas() -> list[str]:
    M = []

    def add(nome, expr, fmt=None, pasta=None, desc=None, oculta=False):
        M.append(medida(nome, expr, fmt, pasta, desc, oculta))

    # --- apoio ---
    add("_Comparação", f"SELECTEDVALUE ( 'Comparação'[Comparação], {dax_txt(COMPARACAO_PADRAO)} )", None, "Apoio",
        f"Par escolhido; sem escolha, {COMPARACAO_PADRAO}", True)
    for nome, col in [("_Carro combustão", "carro_combustao"), ("_Carro elétrico", "carro_eletrico"),
                      ("_Nome combustão", "nome_combustao"), ("_Nome elétrico", "nome_eletrico")]:
        add(nome, f"""VAR _c = [_Comparação]
RETURN
    CALCULATE ( MAX ( 'Comparação'[{col}] ), REMOVEFILTERS ( 'Comparação' ), 'Comparação'[Comparação] = _c )""",
            None, "Apoio", None, True)
    add("_Real", "SELECTEDVALUE ( 'Valores'[Valores], \"Real\" ) = \"Real\"", None, "Apoio",
        "Verdadeiro quando o painel mostra valores reais (padrão)", True)
    add("_Com tributos", "SELECTEDVALUE ( 'Tributos'[Tributos], \"Com tributos\" ) = \"Com tributos\"", None, "Apoio",
        "Verdadeiro quando o painel mostra o preço ao consumidor (padrão)", True)
    add("_Custo km", """VAR _real = [_Real]
VAR _com = [_Com tributos]
RETURN
    SWITCH (
        TRUE (),
        _real && _com, AVERAGE ( 'Custo por km'[custo_km_real] ),
        _com, AVERAGE ( 'Custo por km'[custo_km] ),
        _real, AVERAGE ( 'Custo por km'[custo_km_sem_tributos_real] ),
        AVERAGEX ( 'Custo por km', 'Custo por km'[custo_km_sem_tributos_real] / RELATED ( 'Calendário'[fator_real] ) )
    )""", None, "Apoio", "R$/km conforme as escolhas real/nominal e com/sem tributos; média simples das UFs", True)
    for nome, carro, energia in [("_Consumo gasolina", "_Carro combustão", "gasolina"),
                                 ("_Consumo etanol", "_Carro combustão", "etanol"),
                                 ("_Consumo elétrico", "_Carro elétrico", "eletricidade")]:
        add(nome, f"""{_filtro_carro(carro, energia)}
    CALCULATE ( MAX ( 'Veículos'[consumo_por_km] ), REMOVEFILTERS ( 'Veículos' ), 'Veículos'[chave_veiculo] = _ch )""",
            None, "Apoio", "Litros ou kWh por km do carro escolhido (PBE Veicular)", True)
    add("_Último mês com dados", "CALCULATE ( MAX ( 'Calendário'[Mês] ), REMOVEFILTERS ( 'Calendário' ) )",
        "mmm/yyyy", "Apoio", None, True)

    # --- custo por 100 km ---
    for nome, carro, energia, desc in [
        ("Custo elétrico", "_Carro elétrico", "eletricidade", "R$ para rodar 100 km com o carro elétrico"),
        ("Custo gasolina", "_Carro combustão", "gasolina", "R$ para rodar 100 km com o carro a combustão e gasolina"),
        ("Custo etanol", "_Carro combustão", "etanol", "R$ para rodar 100 km com o carro a combustão e etanol"),
    ]:
        add(nome, f"""{_filtro_carro(carro, energia)}
    CALCULATE ( [_Custo km], REMOVEFILTERS ( 'Veículos' ), 'Veículos'[chave_veiculo] = _ch ) * 100""",
            R2, "Custo por 100 km", desc)
    add("Vezes mais barato", "DIVIDE ( [Custo gasolina], [Custo elétrico] )", "0.0", "Custo por 100 km",
        "Quantas vezes o custo da gasolina cabe no custo do elétrico")
    add("Economia do elétrico", "[Custo gasolina] - [Custo elétrico]", R2, "Custo por 100 km",
        "R$ economizados a cada 100 km ao trocar a gasolina pelo elétrico")
    for nome, carro, energia in [("Horas de SM elétrico", "_Carro elétrico", "eletricidade"),
                                 ("Horas de SM gasolina", "_Carro combustão", "gasolina")]:
        add(nome, f"""{_filtro_carro(carro, energia)}
    CALCULATE ( AVERAGE ( 'Custo por km'[horas_sm_100km] ), REMOVEFILTERS ( 'Veículos' ), 'Veículos'[chave_veiculo] = _ch )""",
            "0.0", "Custo por 100 km", "Horas de trabalho com salário mínimo (220 h/mês) para pagar 100 km, com tributos")
    add("Marco legal", """VAR _m = MAX ( 'Calendário'[Mês] )
RETURN
    IF (
        HASONEVALUE ( 'Calendário'[Mês] ),
        SWITCH (
            _m,
            DATE ( 2015, 5, 1 ), "CIDE volta e PIS/Cofins sobe",
            DATE ( 2017, 8, 1 ), "PIS/Cofins da gasolina dobra",
            DATE ( 2021, 9, 1 ), "Bandeira escassez hídrica",
            DATE ( 2022, 7, 1 ), "LC 194: teto do ICMS, federais zerados",
            DATE ( 2023, 6, 1 ), "ICMS da gasolina por litro"
        )
    )""", None, "Custo por 100 km", "Rótulo dos marcos anotados no gráfico de linhas", True)

    # --- preço da energia ---
    add("_Preço unit", f"""VAR _real = [_Real]
VAR _com = [_Com tributos]
RETURN
    AVERAGEX (
        'Preço da energia',
        IF ( _com, 'Preço da energia'[preco], 'Preço da energia'[preco_sem_tributos] ) * {FATOR}
    )""", None, "Apoio", None, True)
    for nome, energia, fmt in [("Preço gasolina", "gasolina", R2), ("Preço etanol", "etanol", R2),
                               ("Preço eletricidade", "eletricidade", R3)]:
        add(nome, f"CALCULATE ( [_Preço unit], 'Energias'[energia] = \"{energia}\" )", fmt, "Preço da energia",
            "Preço médio das capitais, por litro ou kWh, conforme real/nominal e com/sem tributos")
    add("Razão de preço etanol/gasolina", """DIVIDE (
    CALCULATE ( AVERAGE ( 'Preço da energia'[preco] ), 'Energias'[energia] = "etanol" ),
    CALCULATE ( AVERAGE ( 'Preço da energia'[preco] ), 'Energias'[energia] = "gasolina" )
)""", "0.0%", "Preço da energia", "Preço do litro de etanol dividido pelo da gasolina, nas bombas")
    add("Razão de rendimento do carro", "DIVIDE ( [_Consumo gasolina], [_Consumo etanol] )", "0.0%",
        "Preço da energia", "km/l com etanol dividido por km/l com gasolina: abaixo disso, o etanol compensa")

    # --- tributos por 100 km ---
    def parcela(nome, energia, consumo, expr_linha, desc):
        add(nome, f"""VAR _real = [_Real]
VAR _cons = [{consumo}]
RETURN
    CALCULATE (
        AVERAGEX ( 'Preço da energia', {expr_linha} * {FATOR} ),
        'Energias'[energia] = "{energia}"
    ) * _cons * 100""", R2, "Tributos por 100 km", desc)

    P = "'Preço da energia'"
    parcela("Gasolina: sem tributos", "gasolina", "_Consumo gasolina",
            f"IF ( NOT ISBLANK ( {P}[icms_unit] ), {P}[preco_sem_tributos] )",
            "Gasolina sem ICMS, PIS/Cofins e CIDE (a partir de jun. 2023, quando o ICMS passa a ser por litro)")
    parcela("Gasolina: sem federais, ICMS dentro", "gasolina", "_Consumo gasolina",
            f"IF ( ISBLANK ( {P}[icms_unit] ), {P}[preco_sem_tributos] )",
            "Gasolina sem PIS/Cofins e CIDE, com o ICMS estadual dentro (até mai. 2023)")
    parcela("Gasolina: ICMS", "gasolina", "_Consumo gasolina", f"{P}[icms_unit]", "ICMS por litro da gasolina")
    parcela("Gasolina: PIS/Cofins", "gasolina", "_Consumo gasolina", f"{P}[pis_cofins_unit]", None)
    parcela("Gasolina: CIDE", "gasolina", "_Consumo gasolina", f"{P}[cide_unit]", None)
    parcela("Eletricidade: sem tributos", "eletricidade", "_Consumo elétrico", f"{P}[preco_sem_tributos]",
            "Tarifa residencial mais a bandeira, sem ICMS e PIS/Cofins")
    parcela("Eletricidade: ICMS", "eletricidade", "_Consumo elétrico", f"{P}[icms_unit]", None)
    parcela("Eletricidade: PIS/Cofins", "eletricidade", "_Consumo elétrico", f"{P}[pis_cofins_unit]", None)
    add("% tributos eletricidade", f"""CALCULATE (
    DIVIDE ( SUM ( {P}[icms_unit] ) + SUM ( {P}[pis_cofins_unit] ), SUM ( {P}[preco] ) ),
    'Energias'[energia] = "eletricidade"
)""", "0.0%", "Tributos por 100 km", "Parte do preço da eletricidade que é ICMS e PIS/Cofins")
    add("% tributos gasolina", f"""CALCULATE (
    DIVIDE ( SUM ( {P}[icms_unit] ) + SUM ( {P}[pis_cofins_unit] ) + SUM ( {P}[cide_unit] ), SUM ( {P}[preco] ) ),
    'Energias'[energia] = "gasolina"
)""", "0.0%", "Tributos por 100 km",
        "Parte do preço da gasolina que é tributo separado (até mai. 2023, só os federais)")

    # --- estados (últimos 12 meses do período) ---
    for nome, base, fmt in [("Custo elétrico 12m", "[Custo elétrico]", R2),
                            ("Custo gasolina 12m", "[Custo gasolina]", R2)]:
        add(nome, f"CALCULATE ( {base}, {JANELA} )", fmt, "Estados", "Média dos 12 meses que terminam no fim do período")
    add("Economia 12m", "[Custo gasolina 12m] - [Custo elétrico 12m]", R2, "Estados",
        "R$ economizados por 100 km com o elétrico, média de 12 meses")
    add("ICMS efetivo 12m", f"""CALCULATE (
    DIVIDE ( SUM ( {P}[icms_unit] ), SUM ( {P}[preco] ) ),
    'Energias'[energia] = "eletricidade",
    {JANELA}
)""", "0.0%", "Estados", "ICMS dividido pelo preço final da energia residencial (alíquota efetiva do SAMP)")
    add("Tarifa sem tributos 12m", f"""VAR _real = [_Real]
RETURN
    CALCULATE (
        AVERAGEX ( {P}, {P}[preco_sem_tributos] * {FATOR} ),
        'Energias'[energia] = "eletricidade",
        {JANELA}
    )""", R3, "Estados", "Tarifa residencial mais bandeira, sem ICMS e PIS/Cofins, em R$/kWh")
    add("Meses com tarifa do SAMP", f"""CALCULATE (
    COUNTROWS ( {P} ),
    'Energias'[energia] = "eletricidade",
    {P}[tarifa_imputada] = TRUE ()
)""", "#,0", "Estados", "Meses em que a tarifa homologada faltava na base da ANEEL e entrou a tarifa média do SAMP")
    add("Meses com ICMS imputado", f"""CALCULATE (
    COUNTROWS ( {P} ),
    'Energias'[energia] = "eletricidade",
    {P}[icms_imputado] = TRUE ()
)""", "#,0", "Estados", "Meses em que a alíquota do SAMP era inválida ou faltava e veio do mês válido mais próximo")
    add("Métrica escolhida", f"SELECTEDVALUE ( 'Métrica do mapa'[Métrica do mapa], {dax_txt(METRICAS_MAPA[0])} )",
        None, "Estados", None)
    add("Valor do mapa", f"""SWITCH (
    [Métrica escolhida],
    {dax_txt(METRICAS_MAPA[1])}, [Custo gasolina 12m],
    {dax_txt(METRICAS_MAPA[2])}, [Economia 12m],
    {dax_txt(METRICAS_MAPA[3])}, [ICMS efetivo 12m],
    [Custo elétrico 12m]
)""", "0.00", "Estados", "Valor da métrica escolhida, nos últimos 12 meses do período")

    # --- simulador (sempre real e com tributos, últimos 12 meses do período) ---
    S = "Simulador"
    add("Km por ano escolhido", "SELECTEDVALUE ( 'Km por ano'[Km por ano], 12000 )", "#,0", S, None)
    add("Recarga em casa escolhida", "SELECTEDVALUE ( 'Recarga em casa (%)'[Recarga em casa (%)], 80 ) / 100", "0%", S,
        None)
    add("Tarifa em casa escolhida", "SELECTEDVALUE ( 'Tarifa em casa'[Tarifa em casa], \"Convencional\" )", None, S,
        None)
    add("Carregador escolhido", "SELECTEDVALUE ( 'Carregador público'[Carregador público (R$/kWh)], 2 )", R2,
        S, "Hipótese de R$ 2,00/kWh quando nada é escolhido")
    add("Anos de uso escolhidos", "SELECTEDVALUE ( 'Anos de uso'[Anos de uso], 10 )", "0", S, None)
    for nome, carro, tab in [("Preço do carro a combustão", "_Carro combustão", "Preço do carro a combustão (R$)"),
                             ("Preço do carro elétrico", "_Carro elétrico", "Preço do carro elétrico (R$)")]:
        add(nome, f"""VAR _c = [{carro}]
VAR _site = CALCULATE ( MAX ( 'Carros'[preco_tabela] ), REMOVEFILTERS ( 'Carros' ), 'Carros'[veiculo] = _c )
RETURN
    SELECTEDVALUE ( '{tab}'[{tab}], _site )""", R0, S,
            "Valor escolhido na lista; sem escolha, o preço de tabela no site da montadora")
    add("Preço de site combustão", """VAR _c = [_Carro combustão]
RETURN
    CALCULATE ( MAX ( 'Carros'[preco_tabela] ), REMOVEFILTERS ( 'Carros' ), 'Carros'[veiculo] = _c )""", R0, S, None,
        True)
    add("Preço de site elétrico", """VAR _c = [_Carro elétrico]
RETURN
    CALCULATE ( MAX ( 'Carros'[preco_tabela] ), REMOVEFILTERS ( 'Carros' ), 'Carros'[veiculo] = _c )""", R0, S, None,
        True)
    add("Gasolina por km (12m)", f"""{_filtro_carro("_Carro combustão", "gasolina")}
    CALCULATE (
        AVERAGE ( 'Custo por km'[custo_km_real] ),
        REMOVEFILTERS ( 'Veículos' ),
        'Veículos'[chave_veiculo] = _ch,
        {JANELA}
    )""", R3, S, "R$/km do carro a combustão com gasolina, média real dos últimos 12 meses")
    add("Tarifa convencional (12m)", f"""CALCULATE (
    AVERAGEX ( {P}, {P}[preco] * RELATED ( 'Calendário'[fator_real] ) ),
    'Energias'[energia] = "eletricidade",
    {JANELA}
)""", R3, S, "Tarifa residencial convencional com tributos e bandeira, R$/kWh, média real de 12 meses")
    add("Tarifa branca fora de ponta (12m)", f"""CALCULATE (
    AVERAGEX ( {P}, {P}[tarifa_branca_fp_kwh] * RELATED ( 'Calendário'[fator_real] ) ),
    'Energias'[energia] = "eletricidade",
    {JANELA}
)""", R3, S, "Tarifa branca fora de ponta com tributos e bandeira, R$/kWh, média real de 12 meses")
    add("Tarifa em casa (12m)", """VAR _conv = [Tarifa convencional (12m)]
RETURN
    IF ( [Tarifa em casa escolhida] = "Convencional", _conv, COALESCE ( [Tarifa branca fora de ponta (12m)], _conv ) )""",
        R3, S, "Tarifa usada para a recarga em casa; sem tarifa branca na UF, usa a convencional")
    add("Elétrico por km (12m)", """VAR _p = [Recarga em casa escolhida]
VAR _cons = [_Consumo elétrico]
RETURN
    IF ( NOT ISBLANK ( _cons ), _cons * ( _p * [Tarifa em casa (12m)] + ( 1 - _p ) * [Carregador escolhido] ) )""",
        R3, S, "R$/km do elétrico misturando recarga em casa e no carregador público")
    add("Custo por ano combustão", "[Km por ano escolhido] * [Gasolina por km (12m)]", R0, S, None)
    add("Custo por ano elétrico", "[Km por ano escolhido] * [Elétrico por km (12m)]", R0, S, None)
    add("Economia por ano", "[Custo por ano combustão] - [Custo por ano elétrico]", R0, S,
        "Quanto o elétrico economiza por ano em energia")
    add("Diferença na compra", "[Preço do carro elétrico] - [Preço do carro a combustão]", R0, S,
        "Quanto o elétrico custa a mais na compra")
    add("Anos para pagar", """VAR _d = [Diferença na compra]
VAR _e = [Economia por ano]
RETURN
    SWITCH ( TRUE (), ISBLANK ( _d ), BLANK (), _d <= 0, 0, _e <= 0, BLANK (), DIVIDE ( _d, _e ) )""", "0.0", S,
        "Anos até a economia em energia pagar a diferença na compra (0 se o elétrico já custa menos)")
    for nome, preco, custo in [("Custo acumulado combustão", "[Preço do carro a combustão]", "[Custo por ano combustão]"),
                               ("Custo acumulado elétrico", "[Preço do carro elétrico]", "[Custo por ano elétrico]")]:
        add(nome, f"""VAR _a = SELECTEDVALUE ( 'Ano de uso'[Ano de uso] )
VAR _p = {preco}
RETURN
    IF ( NOT ISBLANK ( _a ) && NOT ISBLANK ( _p ) && _a <= [Anos de uso escolhidos], _p + _a * {custo} )""",
            R0, S, "Preço de compra mais a energia acumulada até o ano do eixo")
    add("Rótulo combustão", "[_Nome combustão] & \" (gasolina)\"", None, S, None, True)
    add("Rótulo elétrico", "[_Nome elétrico]", None, S, None, True)
    return M


# ----------------------------------------------------------------------------------------------
# Gravação
# ----------------------------------------------------------------------------------------------

def gravar(pasta_sm: Path, medidas_extra: list[str]) -> list[Tabela]:
    d = pasta_sm / "definition"
    if d.exists():
        for f in sorted(d.rglob("*"), reverse=True):
            f.unlink() if f.is_file() else f.rmdir()
    (d / "tables").mkdir(parents=True, exist_ok=True)

    def wr(p: Path, t: str):
        p.write_text(t, encoding="utf-8", newline="\n")

    wr(pasta_sm / "definition.pbism", """{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
  "version": "4.2",
  "settings": {
    "qnaEnabled": false
  }
}
""")
    wr(d / "database.tmdl", "database\n\tcompatibilityLevel: 1601\n\n")
    T = tabelas()
    med = next(t for t in T if t.nome == "_Medidas")
    med.medidas = medidas() + medidas_extra
    ordem = ", ".join(f'"{t.nome}"' for t in T)
    wr(d / "model.tmdl", "model Model\n\tculture: pt-BR\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
       "\tdiscourageImplicitMeasures\n\tsourceQueryCulture: pt-BR\n\tdataAccessOptions\n\t\tlegacyRedirects\n"
       "\t\treturnErrorValuesAsNull\n\n"
       "annotation __PBI_TimeIntelligenceEnabled = 0\n\n"
       f"annotation PBI_QueryOrder = [\"PastaGold\",\"PastaReferencias\",{ordem}]\n\n"
       "annotation PBI_ProTooling = [\"DevMode\"]\n\n"
       + "".join(f"ref table {q(t.nome)}\n" for t in T) + "\n")
    wr(d / "expressions.tmdl",
       f'/// Pasta com os Parquet da camada gold (python -m custo_km.exportar grava em gold/)\n'
       f'expression PastaGold = "{PASTA_GOLD_PADRAO}" meta [IsParameterQuery = true, Type = "Text", '
       f'IsParameterQueryRequired = true]\n\tlineageTag: {uid("e/PastaGold")}\n\n'
       f'\tannotation PBI_ResultType = Text\n\n'
       f'/// Pasta referencias/ do repositório (preço dos carros)\n'
       f'expression PastaReferencias = "{PASTA_REF_PADRAO}" meta [IsParameterQuery = true, Type = "Text", '
       f'IsParameterQueryRequired = true]\n\tlineageTag: {uid("e/PastaReferencias")}\n\n'
       f'\tannotation PBI_ResultType = Text\n\n')
    rel = ""
    for fa, fc, da, dc in RELACOES:
        rel += (f"relationship {uid(f'r/{fa}/{fc}')}\n\tfromColumn: {q(fa)}.{q(fc)}\n"
                f"\ttoColumn: {q(da)}.{q(dc)}\n\n")
    wr(d / "relationships.tmdl", rel)
    for t in T:
        wr(d / "tables" / f"{t.nome}.tmdl", t.tmdl())
    return T

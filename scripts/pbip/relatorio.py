"""Relatório (PBIR) do painel: páginas, visuais, specs Deneb e medidas HTML.

Usa só tipos de visual cujo formato foi conferido num relatório salvo pelo Power BI Desktop
(projeto CortesNordeste): segmentação, caixa de texto, botão, Deneb e HTML Content.
"""

import json
import shutil
from pathlib import Path

from modelo import dax_txt, medida, uid

DENEB = "deneb7E15AEF80B9E4D4F8E12924291ECE89A"
HTMLC = "htmlContent443BE3AD55E043BF878BED274D3A6865"
SCHEMA_VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.3.0/schema.json"
SCHEMA_PG = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.4.0/schema.json"
MED = "_Medidas"

INK, CINZA, CINZA_CLARO, BORDA, AMARELO, AMARELO_ESCURO = "#191919", "#605E5C", "#A19F9D", "#E1DFDD", "#F2C811", "#967100"
COR_ELETRICO = "#E0B000"

PAGINAS = [  # nome interno, título da aba, título da página
    ("visao_geral", "Visão geral", "Quanto custa rodar 100 km"),
    ("impostos", "Impostos", "Quanto do custo é imposto"),
    ("estados", "Estados", "Onde o elétrico compensa mais"),
    ("simulador", "Simulador", "Em quantos anos o elétrico se paga"),
    ("metodo", "Método e fontes", "Método e fontes"),
]


# ----------------------------------------------------------------------------------------------
# Helpers de JSON do PBIR
# ----------------------------------------------------------------------------------------------

def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def s(v):
    return lit("'" + v.replace("'", "''") + "'")


def cor(c):
    return {"solid": {"color": s(c)}}


def proj_m(nome):
    return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": MED}}, "Property": nome}},
            "queryRef": f"{MED}.{nome}", "nativeQueryRef": nome}


def proj_c(ent, nome, ativo=False):
    p = {"field": {"Column": {"Expression": {"SourceRef": {"Entity": ent}}, "Property": nome}},
         "queryRef": f"{ent}.{nome}", "nativeQueryRef": nome}
    if ativo:
        p["active"] = True
    return p


def pad(v):
    return [{"properties": {k: lit(f"{v}D") for k in ("top", "bottom", "left", "right")}}]


def container(titulo=None, fundo=True, borda=True, alt=None, escuro=False, padding=None):
    o = {"title": [{"properties": {"show": lit("true" if titulo else "false"),
                                   **({"text": s(titulo), "fontSize": lit("11D"), "fontColor": cor(INK),
                                       "bold": lit("true")} if titulo else {})}}],
         "background": [{"properties": {"show": lit("true" if fundo else "false"),
                                        **({"color": cor(INK if escuro else "#FFFFFF"),
                                            "transparency": lit("0D")} if fundo else {})}}],
         "border": [{"properties": {"show": lit("true" if borda else "false"),
                                    **({"color": cor(BORDA), "width": lit("1D"), "radius": lit("0D")} if borda else {})}}],
         "visualHeader": [{"properties": {"show": lit("false")}}]}
    if alt:
        o["general"] = [{"properties": {"altText": s(alt)}}]
    if padding is not None:
        o["padding"] = pad(padding)
    return o


class Pagina:
    def __init__(self, nome, aba, titulo):
        self.nome, self.aba, self.titulo = nome, aba, titulo
        self.visuais: list[dict] = []
        self.ordem = 0

    def add(self, nome, x, y, w, h, visual, z=None, tab=True):
        self.ordem += 1
        pos = {"x": x, "y": y, "z": z if z is not None else self.ordem * 100, "height": h, "width": w}
        if tab:
            pos["tabOrder"] = self.ordem * 100
        self.visuais.append({"$schema": SCHEMA_VC, "name": nome, "position": pos, "visual": visual})


def run(t, tam, c, negrito=False):
    return {"value": t, "textStyle": {"fontSize": f"{tam}pt", "fontWeight": "bold" if negrito else "normal", "color": c}}


def textbox(paragrafos, fundo=None, alt=None):
    co = container(None, fundo=bool(fundo), borda=False, alt=alt, padding=0)
    if fundo:
        co["background"] = [{"properties": {"show": lit("true"), "color": cor(fundo), "transparency": lit("0D")}}]
    return {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paragrafos}}]},
            "visualContainerObjects": co, "drillFilterOtherVisuals": True}


def botao_pagina(texto, destino, ativo):
    return {"visualType": "actionButton",
            "objects": {
                "icon": [{"properties": {"shapeType": s("blank")}, "selector": {"id": "default"}}],
                "text": [{"properties": {"show": lit("true")}},
                         {"properties": {"text": s(texto), "fontColor": cor(INK if ativo else CINZA),
                                         "fontSize": lit("11D"), "bold": lit("true" if ativo else "false")},
                          "selector": {"id": "default"}}],
                "outline": [{"properties": {"show": lit("false")}}],
                "fill": [{"properties": {"show": lit("false")}}]},
            "visualContainerObjects": {
                **container(None, fundo=False, borda=False, padding=0),
                "general": [{"properties": {"altText": s(f"Ir para a página {texto}")}}],
                "visualLink": [{"properties": {"show": lit("true"), "type": s("PageNavigation"),
                                               "navigationSection": s(destino)}}]},
            "drillFilterOtherVisuals": True}


def slicer(tabela, coluna, modo="Dropdown", unico=False, sync=None, alt=None):
    objs = {"data": [{"properties": {"mode": s(modo)}}],
            "header": [{"properties": {"show": lit("true"), "fontColor": cor(CINZA), "textSize": lit("9D")}}],
            "general": [{"properties": {}}]}
    if unico:
        objs["selection"] = [{"properties": {"strictSingleSelect": lit("true")}}]
    v = {"visualType": "slicer",
         "query": {"queryState": {"Values": {"projections": [proj_c(tabela, coluna, ativo=True)]}}},
         "objects": objs,
         "visualContainerObjects": {**container(None, fundo=False, borda=False, alt=alt or f"Filtro de {coluna}"),
                                    "padding": [{"properties": {"top": lit("0D"), "bottom": lit("4D"),
                                                                "left": lit("0D"), "right": lit("0D")}}]},
         "drillFilterOtherVisuals": True}
    if sync:
        v["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}
    return v


def html_visual(nome_medida, css, titulo=None, alt=None, escuro=False, borda=True, padding=None, fundo=True):
    return {"visualType": HTMLC,
            "query": {"queryState": {"content": {"projections": [proj_m(nome_medida)]}}},
            "objects": {"compatibility": [{"properties": {"legacyRendering": lit("false")}}],
                        "stylesheet": [{"properties": {"stylesheet": s(css)}}]},
            "visualContainerObjects": container(titulo, fundo=fundo, borda=borda and not escuro, alt=alt,
                                                escuro=escuro, padding=padding),
            "drillFilterOtherVisuals": True}


DENEB_CFG = {
    "locale": {"number": {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["R$ ", ""]},
               "time": {"dateTime": "%A, %e de %B de %Y. %X", "date": "%d/%m/%Y", "time": "%H:%M:%S",
                        "periods": ["AM", "PM"],
                        "days": ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"],
                        "shortDays": ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"],
                        "months": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                                   "setembro", "outubro", "novembro", "dezembro"],
                        "shortMonths": ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov",
                                        "dez"]}},
    "autosize": {"type": "fit", "contains": "padding"}, "background": "transparent",
    "font": "Segoe UI, Open Sans, sans-serif", "view": {"stroke": None},
    "axis": {"labelColor": CINZA, "titleColor": CINZA, "labelFontSize": 10, "titleFontSize": 10,
             "titleFontWeight": "normal", "gridColor": "#EDEBE9", "domain": False, "tickColor": BORDA},
    "axisX": {"grid": False},
    "legend": {"labelColor": CINZA, "titleColor": CINZA, "labelFontSize": 10, "symbolType": "square"},
    "bar": {"cornerRadiusEnd": 0}, "line": {"strokeWidth": 2}}


def deneb_visual(campos, spec, titulo, alt):
    return {"visualType": DENEB, "query": {"queryState": {"dataset": {"projections": campos}}},
            "objects": {"vega": [{"properties": {
                "jsonSpec": s(json.dumps(spec, ensure_ascii=False, indent=2)),
                "jsonConfig": s(json.dumps(DENEB_CFG, ensure_ascii=False, indent=2)),
                "provider": s("vegaLite"), "renderMode": s("svg"), "enableTooltips": lit("true")}}],
                "developer": [{"properties": {"locale": s("pt-BR")}}]},
            "visualContainerObjects": container(titulo, alt=alt), "drillFilterOtherVisuals": True}


# ----------------------------------------------------------------------------------------------
# Specs Deneb
# ----------------------------------------------------------------------------------------------

EIXO_MES = {"field": "Mês", "type": "temporal", "timeUnit": "yearmonth", "title": None,
            "axis": {"format": "%Y", "tickCount": "year", "labelAlign": "left", "labelPadding": 6,
                     "labelOverlap": "greedy"}}
TT_MES = {"field": "Mês", "type": "temporal", "timeUnit": "yearmonth", "title": "Mês", "format": "%b/%Y"}


def spec_linha_custo():
    series = ["Custo elétrico", "Custo gasolina", "Custo etanol"]
    rotulos = {"Custo elétrico": "Elétrico", "Custo gasolina": "Gasolina", "Custo etanol": "Etanol"}
    calc = " : ".join(f"datum.serie == '{k}' ? '{v}'" for k, v in rotulos.items()) + " : ''"
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "encoding": {"x": EIXO_MES},
        "layer": [
            {"transform": [{"filter": "isValid(datum['Marco legal']) && datum['Marco legal'] != ''"},
                           {"window": [{"op": "row_number", "as": "i"}]}],
             "layer": [
                 {"mark": {"type": "rule", "color": "#C8C6C4", "strokeDash": [3, 3]}},
                 *[{"transform": [{"filter": f"datum.i % 3 == {k}"}],
                    "mark": {"type": "text", "align": "left", "baseline": "top", "dx": 4, "y": 4 + 12 * ((k + 2) % 3),
                             "fontSize": 9, "color": CINZA, "limit": 130},
                    "encoding": {"text": {"field": "Marco legal"}}} for k in range(3)]]},
            {"transform": [{"fold": series, "as": ["serie", "valor"]}, {"filter": "isValid(datum.valor)"},
                           {"calculate": calc, "as": "Energia"}],
             "layer": [
                 {"mark": {"type": "line", "interpolate": "monotone"},
                  "encoding": {
                      "y": {"field": "valor", "type": "quantitative", "title": "R$ por 100 km",
                            "axis": {"format": "$,.0f", "tickCount": 5}},
                      "color": {"field": "Energia", "type": "nominal",
                                "scale": {"domain": ["Elétrico", "Gasolina", "Etanol"],
                                          "range": [COR_ELETRICO, INK, CINZA_CLARO]},
                                "legend": {"orient": "top", "title": None, "direction": "horizontal"}},
                      "strokeWidth": {"condition": {"test": "datum.Energia == 'Elétrico'", "value": 3}, "value": 2}}},
                 {"mark": {"type": "circle", "size": 50, "opacity": 0.01},
                  "encoding": {
                      "y": {"field": "valor", "type": "quantitative"},
                      "tooltip": [TT_MES,
                                  {"field": "Custo elétrico", "title": "Elétrico (R$/100 km)", "format": "$,.2f"},
                                  {"field": "Custo gasolina", "title": "Gasolina (R$/100 km)", "format": "$,.2f"},
                                  {"field": "Custo etanol", "title": "Etanol (R$/100 km)", "format": "$,.2f"},
                                  {"field": "Preço eletricidade", "title": "Eletricidade (R$/kWh)", "format": "$,.3f"},
                                  {"field": "Preço gasolina", "title": "Gasolina (R$/l)", "format": "$,.2f"},
                                  {"field": "Preço etanol", "title": "Etanol (R$/l)", "format": "$,.2f"}]}}]}]}


def spec_razao_etanol():
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "layer": [
            {"mark": {"type": "rule", "color": "#C8C6C4", "strokeDash": [4, 3]},
             "encoding": {"y": {"datum": 0.7}}},
            {"mark": {"type": "text", "align": "right", "baseline": "top", "dy": 3, "fontSize": 9, "color": CINZA},
             "encoding": {"x": {"value": {"expr": "width - 4"}}, "y": {"datum": 0.7},
                          "text": {"value": "regra dos 70 %"}}},
            {"transform": [{"window": [{"op": "row_number", "as": "i"}]}, {"filter": "datum.i == 1"}],
             "layer": [
                 {"mark": {"type": "rule", "color": COR_ELETRICO, "strokeWidth": 2},
                  "encoding": {"y": {"field": "Razão de rendimento do carro", "type": "quantitative"}}},
                 {"mark": {"type": "text", "align": "left", "baseline": "bottom", "dy": -3, "fontSize": 9,
                           "color": AMARELO_ESCURO, "fontWeight": "bold"},
                  "encoding": {"x": {"value": 4},
                               "y": {"field": "Razão de rendimento do carro", "type": "quantitative"},
                               "text": {"value": "rendimento do carro: abaixo, o etanol compensa"}}}]},
            {"mark": {"type": "line", "color": INK, "interpolate": "monotone"},
             "encoding": {"x": EIXO_MES,
                          "y": {"field": "Razão de preço etanol/gasolina", "type": "quantitative",
                                "title": "Etanol ÷ gasolina (preço do litro)",
                                "scale": {"zero": False}, "axis": {"format": ".0%", "tickCount": 5}}}},
            {"mark": {"type": "circle", "size": 40, "opacity": 0.01},
             "encoding": {"x": EIXO_MES,
                          "y": {"field": "Razão de preço etanol/gasolina", "type": "quantitative"},
                          "tooltip": [TT_MES,
                                      {"field": "Razão de preço etanol/gasolina", "title": "Etanol ÷ gasolina",
                                       "format": ".1%"},
                                      {"field": "Razão de rendimento do carro", "title": "Rendimento do carro",
                                       "format": ".1%"}]}}]}


PARCELAS_GAS = [("Gasolina: sem tributos", "Sem tributos", "#E1DFDD"),
                ("Gasolina: sem federais, ICMS dentro", "Sem federais (ICMS dentro)", "#B3B0AD"),
                ("Gasolina: ICMS", "ICMS", AMARELO),
                ("Gasolina: PIS/Cofins", "PIS/Cofins", CINZA),
                ("Gasolina: CIDE", "CIDE", "#252423")]
PARCELAS_ELE = [("Eletricidade: sem tributos", "Sem tributos (tarifa + bandeira)", "#E1DFDD"),
                ("Eletricidade: ICMS", "ICMS", AMARELO),
                ("Eletricidade: PIS/Cofins", "PIS/Cofins", CINZA)]


def spec_parcelas(parcelas):
    campos = [p[0] for p in parcelas]
    calc_rot = " : ".join(f"datum.serie == '{c}' ? '{r}'" for c, r, _ in parcelas) + " : ''"
    calc_ord = " : ".join(f"datum.serie == '{c}' ? {i}" for i, (c, _, _) in enumerate(parcelas)) + " : 9"
    tt = [TT_MES] + [{"field": c, "title": f"{r} (R$/100 km)", "format": "$,.2f"} for c, r, _ in parcelas]
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "transform": [{"fold": campos, "as": ["serie", "valor"]},
                      {"calculate": "isValid(datum.valor) ? datum.valor : 0", "as": "valor"},
                      {"calculate": calc_rot, "as": "Parcela"}, {"calculate": calc_ord, "as": "ordem"}],
        "mark": {"type": "area", "interpolate": "step-after"},
        "encoding": {
            "x": EIXO_MES,
            "y": {"field": "valor", "type": "quantitative", "stack": "zero", "title": "R$ por 100 km",
                  "axis": {"format": "$,.0f", "tickCount": 5}},
            "color": {"field": "Parcela", "type": "nominal",
                      "scale": {"domain": [r for _, r, _ in parcelas], "range": [k for _, _, k in parcelas]},
                      "legend": {"orient": "top", "title": None, "direction": "horizontal", "columns": 3, "labelLimit": 220}},
            "order": {"field": "ordem", "type": "quantitative"},
            "tooltip": tt}}


def spec_pct_tributos():
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "transform": [{"fold": ["% tributos eletricidade", "% tributos gasolina"], "as": ["serie", "valor"]},
                      {"filter": "isValid(datum.valor)"},
                      {"calculate": "datum.serie == '% tributos eletricidade' ? 'Eletricidade' : "
                                    "(time(datum['Mês']) < time(datetime(2023, 5, 1)) ? 'Gasolina (só federais)' : "
                                    "'Gasolina (federais e ICMS)')", "as": "Série"}],
        "mark": {"type": "line", "interpolate": "step-after"},
        "encoding": {
            "x": EIXO_MES,
            "y": {"field": "valor", "type": "quantitative", "title": "% do preço", "axis": {"format": ".0%",
                                                                                           "tickCount": 4}},
            "color": {"field": "Série", "type": "nominal",
                      "scale": {"domain": ["Eletricidade", "Gasolina (federais e ICMS)", "Gasolina (só federais)"],
                                "range": [COR_ELETRICO, INK, CINZA_CLARO]},
                      "legend": {"orient": "top", "title": None, "direction": "horizontal"}},
            "strokeDash": {"condition": {"test": "datum['Série'] == 'Gasolina (só federais)'", "value": [4, 3]},
                           "value": [1, 0]},
            "tooltip": [TT_MES, {"field": "Série"}, {"field": "valor", "title": "% do preço", "format": ".1%"}]}}


GRADE_BR = {"RR": (2, 0), "AP": (3, 0), "AM": (1, 1), "PA": (2, 1), "MA": (3, 1), "CE": (4, 1), "RN": (5, 1),
            "AC": (0, 2), "RO": (1, 2), "TO": (2, 2), "PI": (3, 2), "PE": (4, 2), "PB": (5, 2), "MT": (1, 3),
            "GO": (2, 3), "BA": (3, 3), "SE": (4, 3), "AL": (5, 3), "MS": (1, 4), "DF": (2, 4), "MG": (3, 4),
            "ES": (4, 4), "PR": (1, 5), "SP": (2, 5), "RJ": (3, 5), "RS": (0, 6), "SC": (1, 6)}

ROTULO_METRICA = ("indexof(datum['Métrica escolhida'], 'ICMS') >= 0 ? format(datum['Valor do mapa'], '.1%') : "
                  "format(datum['Valor do mapa'], '$,.2f')")
TT_UF = [{"field": "Estado"}, {"field": "Capital"},
         {"field": "Custo elétrico 12m", "title": "Elétrico (R$/100 km)", "format": "$,.2f"},
         {"field": "Custo gasolina 12m", "title": "Gasolina (R$/100 km)", "format": "$,.2f"},
         {"field": "Economia 12m", "title": "Economia (R$/100 km)", "format": "$,.2f"},
         {"field": "Tarifa sem tributos 12m", "title": "Tarifa sem tributos (R$/kWh)", "format": "$,.3f"},
         {"field": "ICMS efetivo 12m", "title": "ICMS efetivo da energia", "format": ".1%"},
         {"field": "Meses com tarifa do SAMP", "title": "Meses com tarifa do SAMP (série toda)"},
         {"field": "Meses com ICMS imputado", "title": "Meses com ICMS imputado (série toda)"}]


def spec_mapa():
    grade = [{"uf": k, "c": c, "r": r} for k, (c, r) in GRADE_BR.items()]
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "transform": [{"lookup": "UF", "from": {"data": {"values": grade}, "key": "uf", "fields": ["c", "r"]}},
                      {"joinaggregate": [{"op": "min", "field": "Valor do mapa", "as": "vmin"},
                                         {"op": "max", "field": "Valor do mapa", "as": "vmax"}]},
                      {"calculate": "(datum['Valor do mapa'] - datum.vmin) / max(datum.vmax - datum.vmin, 1e-9)",
                       "as": "t"},
                      {"calculate": ROTULO_METRICA, "as": "rotulo"}],
        "encoding": {"x": {"field": "c", "type": "ordinal", "axis": None,
                           "scale": {"domain": [0, 1, 2, 3, 4, 5], "paddingInner": 0.08}},
                     "y": {"field": "r", "type": "ordinal", "axis": None,
                           "scale": {"domain": [0, 1, 2, 3, 4, 5, 6], "paddingInner": 0.08}}},
        "layer": [
            {"mark": {"type": "rect"},
             "encoding": {"color": {"field": "Valor do mapa", "type": "quantitative",
                                    "scale": {"range": ["#F3F2F1", "#252423"]}, "legend": None},
                          "tooltip": [{"field": "Métrica escolhida", "title": "Métrica"},
                                      {"field": "rotulo", "title": "Valor (12 meses)"}] + TT_UF}},
            {"mark": {"type": "text", "baseline": "bottom", "dy": -1, "fontSize": 12, "fontWeight": "bold"},
             "encoding": {"text": {"field": "UF"},
                          "color": {"condition": {"test": "datum.t > 0.5", "value": "#FFFFFF"}, "value": INK}}},
            {"mark": {"type": "text", "baseline": "top", "dy": 3, "fontSize": 9},
             "encoding": {"text": {"field": "rotulo"},
                          "color": {"condition": {"test": "datum.t > 0.5", "value": "#FFFFFF"}, "value": INK}}}]}


def spec_ranking():
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container", "padding": {"right": 64},
        "transform": [{"filter": "isValid(datum['Valor do mapa'])"},
                      {"calculate": "datum.Capital + ' (' + datum.UF + ')'", "as": "lab"},
                      {"calculate": ROTULO_METRICA, "as": "rotulo"}],
        "encoding": {"y": {"field": "lab", "type": "nominal", "title": None,
                           "sort": {"field": "Valor do mapa", "op": "max", "order": "descending"},
                           "axis": {"labelLimit": 130, "labelFontSize": 9}}},
        "layer": [
            {"mark": {"type": "bar", "color": "#252423", "height": {"band": 0.72}},
             "encoding": {"x": {"field": "Valor do mapa", "type": "quantitative", "axis": None},
                          "tooltip": [{"field": "Métrica escolhida", "title": "Métrica"},
                                      {"field": "rotulo", "title": "Valor (12 meses)"}] + TT_UF}},
            {"mark": {"type": "text", "align": "left", "dx": 4, "fontSize": 9, "color": CINZA},
             "encoding": {"x": {"field": "Valor do mapa", "type": "quantitative"}, "text": {"field": "rotulo"}}}]}


def spec_dispersao():
    X, Y = "Tarifa sem tributos 12m", "ICMS efetivo 12m"
    eixo_x = {"type": "quantitative", "scale": {"zero": False}, "title": "Tarifa sem tributos (R$/kWh)",
              "axis": {"format": "$,.2f", "tickCount": 4}}
    eixo_y = {"type": "quantitative", "scale": {"zero": False}, "title": "ICMS efetivo",
              "axis": {"format": ".0%", "tickCount": 4}}
    canto = {"transform": [{"window": [{"op": "row_number", "as": "k"}]}, {"filter": "datum.k == 1"}]}
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container", "padding": {"top": 16},
        "transform": [{"filter": f"isValid(datum['{X}']) && isValid(datum['{Y}'])"},
                      {"joinaggregate": [{"op": "median", "field": X, "as": "mx"},
                                         {"op": "median", "field": Y, "as": "my"}]}],
        "layer": [
            {**canto, "mark": {"type": "rule", "color": CINZA_CLARO, "strokeDash": [4, 3]},
             "encoding": {"x": {"field": "mx", **eixo_x}}},
            {**canto, "mark": {"type": "rule", "color": CINZA_CLARO, "strokeDash": [4, 3]},
             "encoding": {"y": {"field": "my", **eixo_y}}},
            {**canto, "mark": {"type": "text", "align": "right", "baseline": "bottom", "fontSize": 9,
                               "color": AMARELO_ESCURO, "fontWeight": "bold"},
             "encoding": {"x": {"value": {"expr": "width"}}, "y": {"value": -6},
                          "text": {"value": "energia cara e ICMS alto"}}},
            {**canto, "mark": {"type": "text", "align": "left", "baseline": "bottom", "fontSize": 9, "color": CINZA},
             "encoding": {"x": {"value": 4}, "y": {"value": {"expr": "height - 4"}},
                          "text": {"value": "energia barata e ICMS baixo"}}},
            {"mark": {"type": "circle", "size": 70, "color": "#252423", "opacity": 0.85},
             "encoding": {"x": {"field": X, **eixo_x}, "y": {"field": Y, **eixo_y}, "tooltip": TT_UF}},
            {"mark": {"type": "text", "align": "left", "dx": 6, "fontSize": 9, "color": CINZA},
             "encoding": {"x": {"field": X, **eixo_x}, "y": {"field": Y, **eixo_y}, "text": {"field": "UF"}}}]}


def spec_acumulado():
    series = ["Custo acumulado combustão", "Custo acumulado elétrico"]
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "transform": [{"fold": series, "as": ["serie", "valor"]}, {"filter": "isValid(datum.valor)"},
                      {"calculate": "datum.serie == 'Custo acumulado combustão' ? datum['Rótulo combustão'] : "
                                    "datum['Rótulo elétrico']", "as": "Carro"},
                      {"calculate": "datum.serie == 'Custo acumulado combustão' ? 1 : 2", "as": "tipo"}],
        "layer": [
            {"transform": [{"joinaggregate": [{"op": "max", "field": "Ano de uso", "as": "amax"}]},
                           {"window": [{"op": "row_number", "as": "k"}]}, {"filter": "datum.k == 1"},
                           {"filter": "isValid(datum['Anos para pagar']) && datum['Anos para pagar'] > 0 && "
                                      "datum['Anos para pagar'] <= datum.amax"}],
             "layer": [
                 {"mark": {"type": "rule", "color": AMARELO, "strokeWidth": 2},
                  "encoding": {"x": {"field": "Anos para pagar", "type": "quantitative"}}},
                 *[{"transform": [{"filter": f"{'' if alinhar == 'left' else '!'}"
                                             "(datum['Anos para pagar'] <= 0.6 * datum.amax)"}],
                    "mark": {"type": "text", "align": alinhar, "baseline": "top", "dx": 6 if alinhar == "left" else -6,
                             "fontSize": 11, "fontWeight": "bold", "color": AMARELO_ESCURO},
                    "encoding": {"x": {"field": "Anos para pagar", "type": "quantitative"}, "y": {"value": 4},
                                 "text": {"value": "empata aqui"}}} for alinhar in ("left", "right")]]},
            {"mark": {"type": "line", "strokeWidth": 3, "point": {"filled": True, "size": 40}},
             "encoding": {
                 "x": {"field": "Ano de uso", "type": "quantitative", "title": "Anos de uso",
                       "axis": {"tickMinStep": 1, "format": "d"}},
                 "y": {"field": "valor", "type": "quantitative", "title": "Compra + energia acumulada",
                       "scale": {"zero": False}, "axis": {"format": "$,.0f", "tickCount": 5}},
                 "color": {"field": "Carro", "type": "nominal", "sort": {"field": "tipo", "op": "min"},
                           "scale": {"range": [INK, COR_ELETRICO]},
                           "legend": {"orient": "top", "title": None, "direction": "horizontal"}},
                 "tooltip": [{"field": "Carro"}, {"field": "Ano de uso", "title": "Ano"},
                             {"field": "valor", "title": "Compra + energia", "format": "$,.0f"}]}}]}


# ----------------------------------------------------------------------------------------------
# Medidas HTML
# ----------------------------------------------------------------------------------------------

CSS_BASE = "*{font-family:'Segoe UI',sans-serif;box-sizing:border-box}html,body{margin:0}.vazio{font-size:13px;color:#8A8886}"
CSS_CTX = CSS_BASE + ".ctx{font-size:12px;color:#605E5C;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" \
    ".ctx b{color:#191919;font-weight:600}.ctx span{margin:0 8px;color:#C8C6C4}"
CSS_KPI = CSS_BASE + """.cab{font-size:11px;color:#605E5C;margin:0 2px 6px 2px}
.kpis{display:flex;gap:10px}
.card{flex:1;background:#FFFFFF;border:1px solid #E1DFDD;border-top:3px solid #191919;padding:8px 12px;min-width:0}
.card.el{border-top-color:#F2C811}
.rot{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:#605E5C;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.val{font-size:24px;font-weight:600;color:#191919;line-height:1.15;margin-top:2px;white-space:nowrap}
.un{font-size:12px;font-weight:400;color:#605E5C}.vs{font-size:14px;color:#A19F9D;font-weight:400}
.sub{font-size:11px;color:#605E5C;margin-top:2px;line-height:1.3}"""
CSS_TEXTO = CSS_BASE + """.tit{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#967100;font-weight:700;margin:10px 0 4px 0}
.tit:first-child{margin-top:0}
p,li{font-size:12px;line-height:1.45;color:#323130;margin:0 0 6px 0}
ul{margin:0 0 4px 0;padding-left:16px}b{color:#191919}
a{color:#191919;text-decoration:underline;text-decoration-color:#F2C811}
table{border-collapse:collapse;width:100%}
th{font-size:9px;letter-spacing:.06em;text-transform:uppercase;color:#8A8886;text-align:left;font-weight:600;border-bottom:1px solid #E1DFDD;padding:3px 6px}
td{font-size:11px;color:#323130;border-bottom:1px solid #EDEBE9;padding:3px 6px;vertical-align:top}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.aviso{border-left:3px solid #F2C811;background:#FBF8EC;padding:6px 10px;font-size:11px;color:#323130;margin-top:8px;line-height:1.4}"""
CSS_ESCURO = CSS_BASE + """.tit{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#F2C811;font-weight:700;margin-bottom:8px}
ul{list-style:none;margin:0;padding:0}
li{position:relative;padding:0 0 8px 14px;font-size:12px;line-height:1.35;color:#FFFFFF}
li:before{content:'';position:absolute;left:0;top:6px;width:6px;height:6px;background:#F2C811}
b{color:#FFFFFF;font-weight:700}.nota{font-size:10px;color:#C8C6C4;margin-top:2px;line-height:1.35}
.vazio{color:#C8C6C4}"""

MARCOS = [  # data, o que mudou, norma
    ("25/06/2012", "CIDE da gasolina vai a zero", "Decreto 7.764/2012"),
    ("01/05/2015", "CIDE volta (R$ 0,10/l) e PIS/Cofins da gasolina sobe para R$ 0,38/l", "Decreto 8.395/2015"),
    ("21/07/2017", "PIS/Cofins da gasolina vai a R$ 0,79/l", "Decreto 9.101/2017"),
    ("set./2021", "Bandeira Escassez Hídrica: R$ 0,142 a mais por kWh, até abr./2022", "ANEEL, bandeiras tarifárias"),
    ("23/06/2022", ("Combustível e energia viram bens essenciais (ICMS no teto da alíquota geral); PIS/Cofins e "
                    "CIDE zerados até dez./2022"), "LC 194/2022"),
    ("01/03/2023", "PIS/Cofins da gasolina volta em parte (R$ 0,47/l)", "MP 1.163/2023"),
    ("01/06/2023", "ICMS da gasolina passa a ser um valor por litro, igual no país (R$ 1,22)",
     "LC 192/2022; Convênio ICMS 15/2023"),
    ("29/06/2023", "PIS/Cofins da gasolina volta a R$ 0,79/l", "fim da MP 1.163/2023"),
    ("01/01/2026", "ICMS por litro da gasolina chega a R$ 1,57", "Convênio ICMS 112/2025"),
]

FONTES = [
    ("Preço da gasolina e do etanol", "ANP, série histórica do levantamento de preços (média mensal por estado)",
     ("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/"
      "precos-revenda-e-de-distribuicao-combustiveis/serie-historica-do-levantamento-de-precos")),
    ("Tarifa residencial", "ANEEL, tarifas homologadas das distribuidoras",
     "https://dadosabertos.aneel.gov.br/dataset/tarifas-distribuidoras-energia-eletrica"),
    ("Bandeiras", "ANEEL, acionamento das bandeiras tarifárias",
     "https://dadosabertos.aneel.gov.br/dataset/bandeiras-tarifarias"),
    ("ICMS e PIS/Cofins da energia", "ANEEL, SAMP (receitas e tributos faturados por distribuidora)",
     "https://dadosabertos.aneel.gov.br/dataset/samp"),
    ("IPCA e salário mínimo", "Banco Central, séries 433 e 1619 do SGS", "https://www3.bcb.gov.br/sgspub"),
    ("Consumo dos carros", "Inmetro, PBE Veicular 2026 (Polo Track: tabela de 2025)",
     ("https://www.gov.br/inmetro/pt-br/assuntos/regulamentacao/avaliacao-da-conformidade/"
      "programa-brasileiro-de-etiquetagem/tabelas-de-eficiencia-energetica/veiculos-automotivos-pbe-veicular")),
    ("Tributos da gasolina e do etanol", "Leis, decretos e convênios do Confaz, um por período", None),
    ("Preço dos carros", "Sites oficiais da Renault, da Volkswagen e da BYD, consultados em 14/11/2026", None),
]


def html_estatico(html: str) -> str:
    return dax_txt(html)


def medidas_html() -> list[str]:
    M = []

    def add(nome, expr, desc):
        M.append(medida(nome, expr, None, "Visual", desc, oculta=True))

    add("html Contexto", """VAR _uf =
    IF (
        ISFILTERED ( 'Estados' ),
        IF (
            HASONEVALUE ( 'Estados'[UF] ),
            SELECTEDVALUE ( 'Estados'[Estado] ) & " (capital: " & SELECTEDVALUE ( 'Estados'[Capital] ) & ")",
            "média simples de " & COUNTROWS ( VALUES ( 'Estados'[UF] ) ) & " capitais"
        ),
        "Brasil: média simples das 27 capitais"
    )
VAR _val = IF ( [_Real], "valores em reais de " & FORMAT ( [_Último mês com dados], "mmm/yyyy" ), "valores nominais" )
VAR _tri = IF ( [_Com tributos], "com tributos", "sem os tributos separados" )
RETURN
    "<div class='ctx'><b>" & [_Comparação] & "</b><span>·</span>" & _uf & "<span>·</span>" & _val
        & "<span>·</span>" & _tri & "</div>\"""", "Linha de contexto abaixo do título")

    add("html Contexto simulador", """VAR _uf =
    IF (
        ISFILTERED ( 'Estados' ) && HASONEVALUE ( 'Estados'[UF] ),
        SELECTEDVALUE ( 'Estados'[Estado] ),
        "Brasil (média das 27 capitais)"
    )
VAR _f = MAX ( 'Calendário'[Mês] )
RETURN
    "<div class='ctx'><b>" & [_Comparação] & "</b><span>·</span>" & _uf
        & "<span>·</span>energia com o preço médio de " & FORMAT ( EDATE ( _f, -11 ), "mmm/yyyy" ) & " a "
        & FORMAT ( _f, "mmm/yyyy" ) & ", em reais de " & FORMAT ( [_Último mês com dados], "mmm/yyyy" )
        & ", com tributos</div>\"""", "Linha de contexto do simulador")

    card = """"<div class='card{cls}'><div class='rot'>" & {rot} & "</div><div class='val'>" & {val} & "</div><div class='sub'>" & {sub} & "</div></div>\""""

    def c(rot, val, sub, el=False):
        return card.format(cls=" el" if el else "", rot=rot, val=val, sub=sub)

    add("html KPIs", f"""VAR _f = MAX ( 'Calendário'[Mês] )
VAR _el = CALCULATE ( [Custo elétrico], 'Calendário'[Mês] = _f )
VAR _ga = CALCULATE ( [Custo gasolina], 'Calendário'[Mês] = _f )
VAR _et = CALCULATE ( [Custo etanol], 'Calendário'[Mês] = _f )
VAR _pel = CALCULATE ( [Preço eletricidade], 'Calendário'[Mês] = _f )
VAR _pga = CALCULATE ( [Preço gasolina], 'Calendário'[Mês] = _f )
VAR _pet = CALCULATE ( [Preço etanol], 'Calendário'[Mês] = _f )
VAR _hel = CALCULATE ( [Horas de SM elétrico], 'Calendário'[Mês] = _f )
VAR _hga = CALCULATE ( [Horas de SM gasolina], 'Calendário'[Mês] = _f )
RETURN
    IF (
        ISBLANK ( _el ) && ISBLANK ( _ga ),
        "<div class='vazio'>Sem dados para o período e os filtros escolhidos.</div>",
        "<div class='cab'>Custo para rodar 100 km em " & FORMAT ( _f, "mmmm \\d\\e yyyy" ) & ", último mês do período</div><div class='kpis'>"
            & {c('"Elétrico · " & [_Nome elétrico]', 'FORMAT ( _el, "R$ #,0.00" )',
                 '"eletricidade a " & FORMAT ( _pel, "R$ #,0.00" ) & " por kWh"', el=True)}
            & {c('"Gasolina · " & [_Nome combustão]', 'FORMAT ( _ga, "R$ #,0.00" )',
                 '"gasolina a " & FORMAT ( _pga, "R$ #,0.00" ) & " por litro"')}
            & {c('"Etanol · " & [_Nome combustão]', 'FORMAT ( _et, "R$ #,0.00" )',
                 '"etanol a " & FORMAT ( _pet, "R$ #,0.00" ) & " por litro"')}
            & {c('"Vantagem do elétrico"', 'FORMAT ( DIVIDE ( _ga, _el ), "0.0" ) & "<span class=' + "'un'" + '> vezes</span>"',
                 '"mais barato que a gasolina: " & FORMAT ( _ga - _el, "R$ #,0.00" ) & " a menos a cada 100 km"')}
            & {c('"Horas de salário mínimo"',
                 'FORMAT ( _hel, "0.0" ) & "<span class=' + "'un'" + '> h</span> <span class=' + "'vs'" + '>×</span> " & FORMAT ( _hga, "0.0" ) & "<span class=' + "'un'" + '> h</span>"',
                 '"de trabalho para pagar 100 km: elétrico × gasolina"')}
            & "</div>"
    )""", "Cartões do último mês do período (página Visão geral)")

    marcos = "".join(f"<tr><td>{d}</td><td>{o}</td><td>{n}</td></tr>" for d, o, n in MARCOS)
    add("html Marcos", html_estatico(
        "<div class='tit'>Marcos legais</div><table><tr><th>Quando</th><th>O que mudou</th><th>Norma</th></tr>"
        + marcos + "</table><div class='aviso'>Na gasolina até mai./2023 e no etanol em toda a série, o ICMS "
        "estadual fica dentro da parcela sem tributos federais: o painel separa só os tributos nacionais e o ICMS "
        "por litro, que vale igual em todo o país.</div>"), "Tabela dos marcos legais (página Impostos)")

    add("html Destaques estados", """VAR _t =
    FILTER (
        ADDCOLUMNS ( VALUES ( 'Estados'[UF] ), "@el", [Custo elétrico 12m], "@ec", [Economia 12m], "@ic", [ICMS efetivo 12m] ),
        NOT ISBLANK ( [@el] )
    )
VAR _bar = TOPN ( 1, _t, [@el], ASC )
VAR _car = TOPN ( 1, _t, [@el], DESC )
VAR _eco = TOPN ( 1, _t, [@ec], DESC )
VAR _icm = TOPN ( 1, _t, [@ic], DESC )
VAR _f = MAX ( 'Calendário'[Mês] )
RETURN
    IF (
        COUNTROWS ( _t ) = 0,
        "<div class='vazio'>Sem dados para o período escolhido.</div>",
        "<div class='tit'>Destaques · 12 meses até " & FORMAT ( _f, "mmm/yyyy" ) & "</div><ul>"
            & "<li>Elétrico mais barato de rodar: <b>" & MAXX ( _bar, 'Estados'[UF] ) & "</b>, "
            & FORMAT ( MAXX ( _bar, [@el] ), "R$ #,0.00" ) & " por 100 km.</li>"
            & "<li>Mais caro: <b>" & MAXX ( _car, 'Estados'[UF] ) & "</b>, "
            & FORMAT ( MAXX ( _car, [@el] ), "R$ #,0.00" ) & " por 100 km.</li>"
            & "<li>Maior economia contra a gasolina: <b>" & MAXX ( _eco, 'Estados'[UF] ) & "</b>, "
            & FORMAT ( MAXX ( _eco, [@ec] ), "R$ #,0.00" ) & " por 100 km.</li>"
            & "<li>Maior ICMS na conta de luz: <b>" & MAXX ( _icm, 'Estados'[UF] ) & "</b>, "
            & FORMAT ( MAXX ( _icm, [@ic] ), "0.0%" ) & " do preço.</li>"
            & "</ul><div class='nota'>Tarifa da distribuidora da capital. A dica do mapa mostra os meses com tarifa "
            & "ou ICMS preenchidos.</div>"
    )""", "Destaques da página Estados")

    add("html Simulador resultado", f"""VAR _pc = [Preço do carro a combustão]
VAR _pe = [Preço do carro elétrico]
VAR _gk = [Gasolina por km (12m)]
VAR _ek = [Elétrico por km (12m)]
VAR _eco = [Economia por ano]
VAR _dif = [Diferença na compra]
VAR _anos = [Anos para pagar]
VAR _n = [Anos de uso escolhidos]
VAR _sem_preco = ISBLANK ( _pe ) || ISBLANK ( _pc )
VAR _saldo = _n * _eco - _dif
VAR _pay =
    SWITCH (
        TRUE (),
        _sem_preco, "<div class='val'>—</div><div class='sub'>escolha o preço do carro na lista</div>",
        _dif <= 0, "<div class='val'>Na compra</div><div class='sub'>o elétrico já custa menos</div>",
        ISBLANK ( _anos ), "<div class='val'>Não paga</div><div class='sub'>a energia do elétrico sai mais cara</div>",
        "<div class='val'>" & FORMAT ( _anos, "0.0" ) & "<span class='un'> anos</span></div><div class='sub'>"
            & IF ( _anos <= _n, "dentro dos " & _n & " anos de uso", "depois dos " & _n & " anos de uso" ) & "</div>"
    )
RETURN
    "<div class='kpis'>"
        & {c('"Energia por km"', 'FORMAT ( _ek, "R$ #,0.00" ) & "<span class=' + "'vs'" + '> × </span>" & FORMAT ( _gk, "R$ #,0.00" )',
             '[_Nome elétrico] & " × " & [_Nome combustão] & " a gasolina"')}
        & {c('"Economia por ano"', 'FORMAT ( _eco, "R$ #,0" )',
             '"com " & FORMAT ( [Km por ano escolhido], "#,0" ) & " km por ano"')}
        & {c('"Diferença na compra"', 'IF ( _sem_preco, "—", FORMAT ( _dif, "R$ #,0" ) )',
             'IF ( _sem_preco, "sem preço de site para o " & [_Nome elétrico], FORMAT ( _pe, "R$ #,0" ) & " − " & FORMAT ( _pc, "R$ #,0" ) )')}
        & "<div class='card el'><div class='rot'>Paga a diferença em</div>" & _pay & "</div>"
        & {c('"Saldo em " & _n & " anos"', 'IF ( _sem_preco, "—", FORMAT ( ABS ( _saldo ), "R$ #,0" ) )',
             'IF ( _sem_preco, "", IF ( _saldo >= 0, "a favor do elétrico", "a favor do carro a combustão" ) )')}
        & "</div>\"""", "Resultado do simulador")

    add("html Simulador notas", """VAR _pc = [Preço de site combustão]
VAR _pe = [Preço de site elétrico]
VAR _data = FORMAT ( CALCULATE ( MAX ( 'Carros'[data_consulta] ), REMOVEFILTERS ( 'Carros' ) ), "dd/mm/yyyy" )
RETURN
    "<div class='tit'>Preço dos carros</div><p>Sem escolha nas listas acima, vale o preço de tabela no site da montadora em "
        & _data & ": <b>" & [_Nome combustão] & "</b>, " & IF ( ISBLANK ( _pc ), "sem preço", FORMAT ( _pc, "R$ #,0" ) )
        & ", e <b>" & [_Nome elétrico] & "</b>, "
        & IF ( ISBLANK ( _pe ), "fora de linha, sem preço no site", FORMAT ( _pe, "R$ #,0" ) ) & ".</p>"
        & "<div class='tit'>Hipóteses</div><ul><li>Carregador público a R$ 2,00/kWh quando nada é escolhido; não há "
        & "base oficial desse preço.</li><li>O carro a combustão roda com gasolina.</li><li>Energia e gasolina com o "
        & "preço médio real dos últimos 12 meses, sem projeção de reajuste.</li><li>Tarifa branca: só o horário fora de "
        & "ponta; onde ela falta, vale a convencional.</li></ul>"
        & "<div class='tit'>Fica fora da conta</div><p>Manutenção, seguro, IPVA, depreciação, troca de bateria e juros "
        & "do financiamento.</p>\"""", "Notas do simulador")

    fontes = "".join(f"<li><b>{a}</b>: " + (f"<a href='{u}' target='_blank'>{b}</a>" if u else b) + "</li>"
                     for a, b, u in FONTES)
    metodo = (
        "<div class='tit'>A pergunta</div><p>Quanto custa rodar 100 km com um carro popular elétrico e com um a "
        "combustão, quanto disso é imposto e em quantos anos a diferença na compra se paga.</p>"
        "<div class='tit'>Fontes</div><ul>" + fontes + "</ul>"
        "<div class='tit'>Regras de cálculo</div><ul>"
        "<li>Custo por km = preço da energia × consumo do carro no PBE Veicular. O carro de 2026 é aplicado aos "
        "preços de cada mês desde jan./2012.</li>"
        "<li>Eletricidade: tarifa residencial B1 convencional da distribuidora da capital, vigente no dia 15, mais a "
        "bandeira do mês. ICMS e PIS/Cofins entram por dentro: preço = base ÷ (1 − ICMS − PIS/Cofins), com a "
        "alíquota efetiva que a distribuidora faturou na classe residencial (SAMP).</li>"
        "<li>Mês sem tarifa homologada na base da ANEEL usa a tarifa média faturada do SAMP; mês com alíquota "
        "inválida usa a do mês válido mais próximo. A contagem por UF está ao lado.</li>"
        "<li>Gasolina: PIS/Cofins e CIDE por litro de gasolina A, vezes a parte de gasolina A na gasolina C "
        "(80 % em 2012, 68 % desde ago./2026). ICMS por litro a partir de jun./2023.</li>"
        "<li>Brasil = média simples das 27 capitais. Valor real = corrigido pelo IPCA até o último mês com todos os "
        "dados. Horas de salário mínimo = custo de 100 km ÷ (salário mínimo ÷ 220 h).</li></ul>"
        "<div class='tit'>O que ficou fora</div><ul>"
        "<li>O ICMS estadual em percentual da gasolina (até mai./2023) e do etanol: a alíquota e a base de cálculo "
        "mudam por estado e por período, sem uma série oficial única.</li>"
        "<li>Preços fora das capitais, tarifa social, GNV e diesel.</li>"
        "<li>No simulador: manutenção, seguro, IPVA, depreciação e bateria.</li></ul>")
    add("html Método", html_estatico(metodo), "Texto da página Método e fontes")

    add("html Imputados", """VAR _linhas =
    CONCATENATEX (
        SUMMARIZE ( 'Estados', 'Estados'[UF], 'Estados'[Distribuidora] ),
        VAR _t = [Meses com tarifa do SAMP]
        VAR _i = [Meses com ICMS imputado]
        RETURN
            "<tr><td>" & 'Estados'[UF] & "</td><td>" & 'Estados'[Distribuidora]
                & "</td><td class='n'>" & FORMAT ( COALESCE ( _t, 0 ), "0" ) & "</td><td class='n'>"
                & FORMAT ( COALESCE ( _i, 0 ), "0" ) & "</td></tr>",
        "",
        'Estados'[UF], ASC
    )
VAR _n = COUNTROWS ( VALUES ( 'Calendário'[Mês] ) )
RETURN
    "<div class='tit'>Meses preenchidos, por UF</div><p>Total de " & _n & " meses por UF. Tarifa do SAMP: a "
        & "tarifa homologada faltava na base da ANEEL. ICMS imputado: a alíquota do mês era inválida ou faltava.</p>"
        & "<table><tr><th>UF</th><th>Distribuidora</th><th class='n'>Tarifa do SAMP</th><th class='n'>ICMS imputado</th></tr>"
        & _linhas & "</table>\"""", "Tabela de meses imputados por UF (página Método)")
    return M


# ----------------------------------------------------------------------------------------------
# Páginas
# ----------------------------------------------------------------------------------------------

Y_FILTROS, H_FILTROS, Y0 = 116, 56, 182


def cabecalho(p: Pagina, contexto="html Contexto"):
    x = 24
    larguras = {"Visão geral": 104, "Impostos": 90, "Estados": 82, "Simulador": 94, "Método e fontes": 132}
    for nome, aba, _ in PAGINAS:
        w = larguras[aba]
        p.add(f"aba_{nome}", x, 12, w, 32, botao_pagina(aba, nome, nome == p.nome))
        if nome == p.nome:
            p.add("aba_sublinhado", x + 8, 42, w - 16, 3, textbox([{"textRuns": [run(" ", 4, AMARELO)]}],
                                                                   fundo=AMARELO), tab=False)
        x += w + 4
    p.add("titulo", 24, 52, 1000, 34, textbox([{"textRuns": [run(p.titulo, 18, INK, True)]}],
                                              alt=f"Título da página: {p.titulo}"))
    if contexto:
        p.add("contexto", 24, 86, 1232, 24, html_visual(contexto, CSS_CTX, fundo=False, borda=False, padding=0,
                                                         alt="Comparação, estado e tipo de valor em uso"))


def filtros(p: Pagina, itens):
    """itens: (nome do visual, tabela, coluna, largura, modo, único, grupo de sincronia)."""
    x = 24
    for nome, tab, col, w, modo, unico, sync in itens:
        p.add(nome, x, Y_FILTROS, w, H_FILTROS, slicer(tab, col, modo, unico, sync))
        x += w + 8


F_ESTADO = ("filtro_estado", "Estados", "Estado", 180, "Dropdown", False, "Estado")
F_COMP = ("filtro_comparacao", "Comparação", "Comparação", 230, "Dropdown", True, "Comparação")
F_MES = ("filtro_periodo", "Calendário", "Mês", 320, "Between", False, "Período")
F_VAL = ("filtro_valores", "Valores", "Valores", 150, "Dropdown", True, "Valores")
F_TRI = ("filtro_tributos", "Tributos", "Tributos", 150, "Dropdown", True, "Tributos")

CAMPOS_HERO = ["Custo elétrico", "Custo gasolina", "Custo etanol", "Marco legal", "Preço eletricidade",
               "Preço gasolina", "Preço etanol"]
CAMPOS_UF = ["Valor do mapa", "Métrica escolhida", "Custo elétrico 12m", "Custo gasolina 12m", "Economia 12m",
             "Tarifa sem tributos 12m", "ICMS efetivo 12m", "Meses com tarifa do SAMP", "Meses com ICMS imputado"]


def montar_paginas() -> list[Pagina]:
    P = {nome: Pagina(nome, aba, tit) for nome, aba, tit in PAGINAS}

    p = P["visao_geral"]
    cabecalho(p)
    filtros(p, [F_ESTADO, F_COMP, F_MES, F_VAL, F_TRI])
    p.add("kpis", 24, Y0, 1232, 112, html_visual("html KPIs", CSS_KPI, fundo=False, borda=False, padding=0,
                                                 alt="Cartões com o custo de rodar 100 km no último mês do período"))
    p.add("linha_custo", 24, 306, 800, 402, deneb_visual(
        [proj_c("Calendário", "Mês")] + [proj_m(m) for m in CAMPOS_HERO], spec_linha_custo(),
        "R$ para rodar 100 km, mês a mês",
        "Linhas com o custo de rodar 100 km com eletricidade, gasolina e etanol desde 2012, com os marcos legais"))
    p.add("razao_etanol", 836, 306, 420, 402, deneb_visual(
        [proj_c("Calendário", "Mês"), proj_m("Razão de preço etanol/gasolina"), proj_m("Razão de rendimento do carro")],
        spec_razao_etanol(), "Etanol ou gasolina?",
        "Linha com o preço do etanol dividido pelo da gasolina, contra a regra dos 70 % e o rendimento do carro"))

    p = P["impostos"]
    cabecalho(p)
    filtros(p, [F_ESTADO, F_COMP, F_MES, F_VAL])
    p.add("parcelas_gasolina", 24, Y0, 610, 300, deneb_visual(
        [proj_c("Calendário", "Mês")] + [proj_m(c) for c, _, _ in PARCELAS_GAS], spec_parcelas(PARCELAS_GAS),
        "Gasolina: R$ por 100 km, em parcelas",
        "Áreas empilhadas com o custo de 100 km a gasolina separado em preço sem tributos, ICMS, PIS/Cofins e CIDE"))
    p.add("parcelas_eletricidade", 646, Y0, 610, 300, deneb_visual(
        [proj_c("Calendário", "Mês")] + [proj_m(c) for c, _, _ in PARCELAS_ELE], spec_parcelas(PARCELAS_ELE),
        "Eletricidade: R$ por 100 km, em parcelas",
        "Áreas empilhadas com o custo de 100 km com eletricidade separado em tarifa com bandeira, ICMS e PIS/Cofins"))
    p.add("pct_tributos", 24, 494, 610, 214, deneb_visual(
        [proj_c("Calendário", "Mês"), proj_m("% tributos eletricidade"), proj_m("% tributos gasolina")],
        spec_pct_tributos(), "Quanto do preço é tributo",
        "Linhas com a parte do preço da eletricidade e da gasolina que é tributo, mês a mês"))
    p.add("marcos", 646, 494, 610, 214, html_visual("html Marcos", CSS_TEXTO, padding=10,
                                                     alt="Tabela com os marcos legais e a norma de cada um"))

    p = P["estados"]
    cabecalho(p)
    filtros(p, [("filtro_comparacao", "Comparação", "Comparação", 230, "Dropdown", True, "Comparação"),
                F_MES, F_VAL, F_TRI,
                ("filtro_metrica", "Métrica do mapa", "Métrica do mapa", 330, "Dropdown", True, None)])
    campos_uf = [proj_c("Estados", "UF"), proj_c("Estados", "Estado"), proj_c("Estados", "Capital")]
    p.add("mapa", 24, Y0, 440, 526, deneb_visual(campos_uf + [proj_m(m) for m in CAMPOS_UF], spec_mapa(),
                                                 "Mapa das capitais (12 meses até o fim do período)",
                                                 "Mapa em grade das 27 UFs colorido pela métrica escolhida"))
    p.add("ranking", 476, Y0, 380, 526, deneb_visual(campos_uf + [proj_m(m) for m in CAMPOS_UF], spec_ranking(),
                                                     "Ranking das capitais",
                                                     "Barras com as 27 capitais ordenadas pela métrica escolhida"))
    p.add("dispersao", 868, Y0, 388, 330, deneb_visual(
        campos_uf + [proj_m(m) for m in CAMPOS_UF], spec_dispersao(), "Energia cara ou imposto alto?",
        "Dispersão das capitais: tarifa sem tributos no eixo horizontal e ICMS efetivo no vertical"))
    p.add("destaques", 868, 524, 388, 184, html_visual("html Destaques estados", CSS_ESCURO, escuro=True, padding=12,
                                                        alt="Destaques das capitais nos últimos 12 meses"))

    p = P["simulador"]
    cabecalho(p, "html Contexto simulador")
    filtros(p, [("filtro_estado", "Estados", "Estado", 168, "Dropdown", False, "Estado"),
                ("filtro_comparacao", "Comparação", "Comparação", 200, "Dropdown", True, "Comparação"),
                ("filtro_km", "Km por ano", "Km por ano", 150, "Dropdown", True, None),
                ("filtro_recarga", "Recarga em casa (%)", "Recarga em casa (%)", 150, "Dropdown", True, None),
                ("filtro_tarifa", "Tarifa em casa", "Tarifa em casa", 170, "Dropdown", True, None),
                ("filtro_carregador", "Carregador público", "Carregador público (R$/kWh)", 170, "Dropdown",
                 True, None),
                ("filtro_anos", "Anos de uso", "Anos de uso", 176, "Dropdown", True, None)])
    p.add("filtro_preco_combustao", 24, Y0, 300, H_FILTROS, slicer(
        "Preço do carro a combustão (R$)", "Preço do carro a combustão (R$)", unico=True))
    p.add("filtro_preco_eletrico", 24, Y0 + 64, 300, H_FILTROS, slicer(
        "Preço do carro elétrico (R$)", "Preço do carro elétrico (R$)", unico=True))
    p.add("notas", 24, Y0 + 130, 300, 396, html_visual("html Simulador notas", CSS_TEXTO, padding=12,
                                                        alt="Preço dos carros, hipóteses e o que fica fora da conta"))
    p.add("resultado", 336, Y0, 920, 112, html_visual("html Simulador resultado", CSS_KPI, fundo=False, borda=False,
                                                       padding=0, alt="Resultado do simulador"))
    p.add("curva", 336, 306, 920, 402, deneb_visual(
        [proj_c("Ano de uso", "Ano de uso"), proj_m("Custo acumulado combustão"), proj_m("Custo acumulado elétrico"),
         proj_m("Rótulo combustão"), proj_m("Rótulo elétrico"), proj_m("Anos para pagar")],
        spec_acumulado(), "Custo acumulado: compra mais energia",
        "Linhas com o custo acumulado dos dois carros por ano de uso; a linha amarela marca o ano em que empatam"))

    p = P["metodo"]
    cabecalho(p, None)
    p.add("metodo", 24, 86, 820, 622, html_visual("html Método", CSS_TEXTO, padding=14,
                                                   alt="Texto com a pergunta, as fontes, as regras de cálculo e o que "
                                                       "ficou fora"))
    p.add("imputados", 856, 86, 400, 622, html_visual("html Imputados", CSS_TEXTO, padding=14,
                                                       alt="Tabela com os meses preenchidos por UF"))
    return [P[n] for n, _, _ in PAGINAS]


# ----------------------------------------------------------------------------------------------
# Gravação
# ----------------------------------------------------------------------------------------------

def gravar(pasta_rp: Path, nome_modelo: str, pasta_tema: Path):
    if pasta_rp.exists():
        shutil.rmtree(pasta_rp)
    d = pasta_rp / "definition"
    (d / "pages").mkdir(parents=True)

    def jw(p: Path, o):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    jw(pasta_rp / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{nome_modelo}.SemanticModel"}}})
    jw(pasta_rp / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": nome_modelo},
        "config": {"version": "2.0", "logicalId": uid("report")}})
    jw(d / "version.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0"})
    rv = {"visual": "1.8.97", "report": "2.0.97", "page": "1.3.97"}
    jw(d / "report.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY24SU10", "reportVersionAtImport": rv, "type": "SharedResources"},
                            "customTheme": {"name": "DomeAnalytics.json", "reportVersionAtImport": rv,
                                            "type": "RegisteredResources"}},
        "objects": {"outspacePane": [{"properties": {"expanded": lit("false")}}]},
        "publicCustomVisuals": [DENEB, HTMLC],
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "DomeAnalytics.json", "path": "DomeAnalytics.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                     "allowChangeFilterTypes": True, "useEnhancedTooltips": True}})
    sr = pasta_rp / "StaticResources"
    (sr / "SharedResources" / "BaseThemes").mkdir(parents=True)
    (sr / "RegisteredResources").mkdir(parents=True)
    shutil.copy(pasta_tema / "CY24SU10.json", sr / "SharedResources" / "BaseThemes" / "CY24SU10.json")
    shutil.copy(pasta_tema / "DomeAnalytics.json", sr / "RegisteredResources" / "DomeAnalytics.json")

    paginas = montar_paginas()
    jw(d / "pages" / "pages.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p.nome for p in paginas], "activePageName": paginas[0].nome})
    for p in paginas:
        jw(d / "pages" / p.nome / "page.json", {"$schema": SCHEMA_PG, "name": p.nome, "displayName": p.aba,
                                                "displayOption": "FitToPage", "height": 720, "width": 1280})
        for v in p.visuais:
            jw(d / "pages" / p.nome / "visuals" / v["name"] / "visual.json", v)
    return paginas


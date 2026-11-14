"""Relatório (PBIR) do painel: páginas, visuais, specs Deneb e medidas HTML.

Usa só tipos de visual cujo formato foi conferido num relatório salvo pelo Power BI Desktop
(projeto CortesNordeste): segmentação, caixa de texto, botão, Deneb e HTML Content.
"""

import json
import shutil
from pathlib import Path

from modelo import COMPARACAO_PADRAO, JANELA, METRICAS_MAPA, dax_txt, medida, uid

DENEB = "deneb7E15AEF80B9E4D4F8E12924291ECE89A"
HTMLC = "htmlContent443BE3AD55E043BF878BED274D3A6865"
SCHEMA_VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.3.0/schema.json"
SCHEMA_PG = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.4.0/schema.json"
MED = "_Medidas"
MALHA = Path(__file__).resolve().parents[2] / "referencias" / "malha_uf.geojson"

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
        self.largura, self.altura, self.tipo = 1280, 720, None
        self.interacoes: list[dict] = []

    def add(self, nome, x, y, w, h, visual, z=None, tab=True, grupo=None):
        self.ordem += 1
        pos = {"x": x, "y": y, "z": z if z is not None else self.ordem * 100, "height": h, "width": w}
        if tab:
            pos["tabOrder"] = pos["z"]
        v = {"$schema": SCHEMA_VC, "name": nome, "position": pos, "visual": visual}
        if grupo:
            v["parentGroupName"] = grupo
        self.visuais.append(v)

    def grupo(self, nome, rotulo, z, oculto=True):
        self.visuais.append({"$schema": SCHEMA_VC, "name": nome,
                             "position": {"x": 0, "y": 0, "z": z, "height": 720, "width": 1280, "tabOrder": z},
                             "visualGroup": {"displayName": rotulo, "groupMode": "ScaleMode",
                                             "objects": {"background": [{"properties": {"show": lit("false")}}]}},
                             "isHidden": oculto})


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


def filtro_padrao(tabela, coluna, valor):
    """Seleção inicial da segmentação (objects.general.filter). valor: literal DAX do PBIR ("12000L", "2D", "'Real'")."""
    return {"filter": {"Version": 2, "From": [{"Name": "t", "Entity": tabela, "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": coluna}}],
                           "Values": [[{"Literal": {"Value": valor}}]]}}}]}}


def slicer(tabela, coluna, modo="Dropdown", unico=False, sync=None, alt=None, padrao=None, cabecalho=True):
    """unico: seleção única obrigatória. Com ela o Power BI escolhe o primeiro item da lista quando nada está
    escolhido, então toda lista de seleção única leva o valor padrão em `padrao`."""
    objs = {"data": [{"properties": {"mode": s(modo)}}],
            "header": [{"properties": {"show": lit("true"), "fontColor": cor(CINZA), "textSize": lit("9D")}}
                       if cabecalho else {"properties": {"show": lit("false")}}],
            "general": [{"properties": {"filter": filtro_padrao(tabela, coluna, padrao)} if padrao else {}}]}
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


def deneb_visual(campos, spec, titulo, alt, selecao=False, realce=False, dica=None):
    """selecao: clicar filtra/realça os outros visuais (__selected__ na spec).
    realce: recebe o realce cruzado dos outros visuais (campos <medida>__highlightStatus na spec).
    dica: nome interno da página de dica de ferramenta."""
    vega = {"jsonSpec": s(json.dumps(spec, ensure_ascii=False, indent=2)),
            "jsonConfig": s(json.dumps(DENEB_CFG, ensure_ascii=False, indent=2)),
            "provider": s("vegaLite"), "renderMode": s("svg"), "enableTooltips": lit("true")}
    if selecao:
        vega["enableSelection"] = lit("true")
        vega["selectionMaxDataPoints"] = lit("250D")
    if realce:
        vega["enableHighlight"] = lit("true")
    co = container(titulo, alt=alt)
    if dica:
        co["visualTooltip"] = [{"properties": {"show": lit("true"), "section": s(dica)}}]
    return {"visualType": DENEB, "query": {"queryState": {"dataset": {"projections": campos}}},
            "objects": {"vega": [{"properties": vega}], "developer": [{"properties": {"locale": s("pt-BR")}}]},
            "visualContainerObjects": co, "drillFilterOtherVisuals": True}


def esmaecer(*medidas_realce, base=1.0):
    """Opacidade: esmaece o que não está selecionado (clique neste visual) nem realçado (clique em outro)."""
    cond = [{"test": "datum.__selected__ == 'off'", "value": round(base * 0.22, 2)}]
    cond += [{"test": f"datum['{m}__highlightStatus'] == 'off'", "value": round(base * 0.22, 2)} for m in medidas_realce]
    return {"condition": cond, "value": base}


def em_destaque(m):
    return f"(datum.__selected__ == 'on' || datum['{m}__highlightStatus'] == 'on')"


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
    r, k = "Razão de preço etanol/gasolina", "Razão de rendimento do carro"
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "transform": [{"calculate": f"!isValid(datum['{r}']) ? '—' : datum['{r}'] < datum['{k}'] ? "
                                    f"'etanol (' + format(datum['{k}'] - datum['{r}'], '.1%') + ' abaixo do limite)' : "
                                    f"'gasolina (' + format(datum['{r}'] - datum['{k}'], '.1%') + ' acima do limite)'",
                       "as": "Compensa"}],
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
                                       "format": ".1%"},
                                      {"field": "Compensa", "title": "Compensa abastecer com"}]}}]}


PARCELAS_GAS = [("Gasolina: sem tributos", "Sem tributos", "#E1DFDD"),
                ("Gasolina: sem federais, ICMS dentro", "Sem federais (ICMS dentro)", "#B3B0AD"),
                ("Gasolina: ICMS", "ICMS", AMARELO),
                ("Gasolina: PIS/Cofins", "PIS/Cofins", CINZA),
                ("Gasolina: CIDE", "CIDE", "#252423")]
PARCELAS_ELE = [("Eletricidade: sem tributos", "Sem tributos (tarifa + bandeira)", "#E1DFDD"),
                ("Eletricidade: ICMS", "ICMS", AMARELO),
                ("Eletricidade: PIS/Cofins", "PIS/Cofins", CINZA)]


def fmt_r(campo, casas=2):
    return f"format(datum['{campo}'], '$,.{casas}f')"


def coluna_dica_mes(tooltip):
    """Retângulo quase transparente do início ao fim de cada mês, na altura toda: o mouse em qualquer ponto da
    coluna pega o mês certo (a área e a linha devolvem o primeiro ponto da série) e leva a página de dica."""
    return {"transform": [{"calculate": "datetime(year(datum['Mês']), month(datum['Mês']) + 1, 1)", "as": "_fim"}],
            "mark": {"type": "rect", "color": INK, "opacity": 0.01},
            "encoding": {"x": {"field": "Mês", "type": "temporal", "title": None}, "x2": {"field": "_fim"},
                         "y": {"value": 0}, "y2": {"value": {"expr": "height"}}, "tooltip": tooltip}}



def spec_parcelas(parcelas, gasolina):
    """Áreas empilhadas por parcela. A dica mostra o total, cada parcela com a sua parte e o regime do mês,
    sem 'null': até mai./2023 o ICMS da gasolina está dentro do preço."""
    campos = [p[0] for p in parcelas]
    calc_rot = " : ".join(f"datum.serie == '{c}' ? '{r}'" for c, r, _ in parcelas) + " : ''"
    calc_ord = " : ".join(f"datum.serie == '{c}' ? {i}" for i, (c, _, _) in enumerate(parcelas)) + " : 9"
    soma = " + ".join(f"(isValid(datum['{c}']) ? datum['{c}'] : 0)" for c in campos)

    def parte(c):
        return f"{fmt_r(c)} + ' (' + format(datum['{c}'] / datum.total, '.0%') + ')'"

    if gasolina:
        sem, dentro, icms, pc, cide = campos
        dicas = [
            {"calculate": f"isValid(datum['{sem}']) ? {fmt_r(sem)} : {fmt_r(dentro)} + ' com ICMS dentro'",
             "as": "Preço sem tributos"},
            {"calculate": f"isValid(datum['{icms}']) ? {parte(icms)} : 'dentro do preço (até mai./2023)'", "as": "ICMS"},
            {"calculate": parte(pc), "as": "PIS/Cofins"},
            {"calculate": f"datum['{cide}'] > 0 ? {parte(cide)} : 'zero'", "as": "CIDE"},
            {"calculate": f"format(((isValid(datum['{icms}']) ? datum['{icms}'] : 0) + datum['{pc}'] + datum['{cide}'])"
                          f" / datum.total, '.0%') + (isValid(datum['{icms}']) ? '' : ' (só federais)')",
             "as": "Tributos no total"}]
        tt = ["Preço sem tributos", "ICMS", "PIS/Cofins", "CIDE", "Tributos no total"]
    else:
        sem, icms, pc = campos
        dicas = [
            {"calculate": fmt_r(sem), "as": "Tarifa + bandeira"},
            {"calculate": parte(icms), "as": "ICMS"},
            {"calculate": parte(pc), "as": "PIS/Cofins"},
            {"calculate": f"format((datum['{icms}'] + datum['{pc}']) / datum.total, '.0%')", "as": "Tributos no total"}]
        tt = ["Tarifa + bandeira", "ICMS", "PIS/Cofins", "Tributos no total"]
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "transform": [{"filter": f"isValid(datum['{campos[-1]}']) || isValid(datum['{campos[0]}'])"},
                      {"calculate": soma, "as": "total"}, {"filter": "datum.total > 0"},
                      {"calculate": "format(datum.total, '$,.2f')", "as": "Total por 100 km"}, *dicas],
        "layer": [
            {"transform": [{"fold": campos, "as": ["serie", "valor"]},
                           {"calculate": "isValid(datum.valor) ? datum.valor : 0", "as": "valor"},
                           {"calculate": calc_rot, "as": "Parcela"}, {"calculate": calc_ord, "as": "ordem"}],
             "mark": {"type": "area", "interpolate": "step-after"},
             "encoding": {
                 "x": EIXO_MES,
                 "y": {"field": "valor", "type": "quantitative", "stack": "zero", "title": "R$ por 100 km",
                       "axis": {"format": "$,.0f", "tickCount": 5}},
                 "color": {"field": "Parcela", "type": "nominal",
                           "scale": {"domain": [r for _, r, _ in parcelas], "range": [k for _, _, k in parcelas]},
                           "legend": {"orient": "top", "title": None, "direction": "horizontal", "columns": 3,
                                      "labelLimit": 220}},
                 "order": {"field": "ordem", "type": "quantitative"}}},
            coluna_dica_mes([TT_MES, {"field": "Total por 100 km"}] + [{"field": c} for c in tt])]}


def spec_pct_tributos():
    el, ga = "% tributos eletricidade", "% tributos gasolina"
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "transform": [
            {"calculate": "time(datum['Mês']) < time(datetime(2023, 5, 1))", "as": "so_federais"},
            {"calculate": f"isValid(datum['{el}']) ? format(datum['{el}'], '.1%') + ' (ICMS e PIS/Cofins)' : '—'",
             "as": "Eletricidade"},
            {"calculate": f"isValid(datum['{ga}']) ? format(datum['{ga}'], '.1%') + (datum.so_federais ? "
                          "' (só PIS/Cofins e CIDE)' : ' (ICMS, PIS/Cofins e CIDE)') : '—'", "as": "Gasolina"},
            {"calculate": f"isValid(datum['{el}']) && isValid(datum['{ga}']) ? (datum['{el}'] > datum['{ga}'] ? "
                          "'a conta de luz' : 'a gasolina') : '—'", "as": "Mais tributada"}],
        "layer": [
            {"transform": [
                {"fold": [el, ga], "as": ["serie", "valor"]}, {"filter": "isValid(datum.valor)"},
                {"calculate": f"datum.serie == '{el}' ? 'Eletricidade' : (datum.so_federais ? 'Gasolina (só federais)' : "
                              "'Gasolina (federais e ICMS)')", "as": "Série"}],
             "mark": {"type": "line", "interpolate": "step-after"},
             "encoding": {
                 "x": EIXO_MES,
                 "y": {"field": "valor", "type": "quantitative", "title": "% do preço",
                       "axis": {"format": ".0%", "tickCount": 4}},
                 "color": {"field": "Série", "type": "nominal",
                           "scale": {"domain": ["Eletricidade", "Gasolina (federais e ICMS)", "Gasolina (só federais)"],
                                     "range": [COR_ELETRICO, INK, CINZA_CLARO]},
                           "legend": {"orient": "top", "title": None, "direction": "horizontal"}},
                 "strokeDash": {"condition": {"test": "datum['Série'] == 'Gasolina (só federais)'", "value": [4, 3]},
                                "value": [1, 0]}}},
            coluna_dica_mes([TT_MES, {"field": "Eletricidade"}, {"field": "Gasolina"}, {"field": "Mais tributada"}])]}


ROTULO_METRICA = ("indexof(datum['Métrica escolhida'], 'ICMS') >= 0 ? format(datum['Valor do mapa'], '.1%') : "
                  "format(datum['Valor do mapa'], '$,.2f')")
# a dica completa vem da página dica_uf; esta é a reserva, curta
TT_UF = [{"field": "Estado"}, {"field": "rotulo", "title": "Valor (12 meses)"},
         {"field": "Custo elétrico 12m", "title": "Elétrico (R$/100 km)", "format": "$,.2f"},
         {"field": "Custo gasolina 12m", "title": "Gasolina (R$/100 km)", "format": "$,.2f"}]
CAMPOS_REALCE_UF = ("Valor do mapa",)
LEGENDA_MAPA = "datum.value < 1 ? format(datum.value, '.0%') : format(datum.value, '$,.0f')"
# UFs pequenas demais para o rótulo no mapa de ~440 px (a dica e o ranking mostram)
SEM_ROTULO = ["DF", "SE", "AL", "PB", "RN", "ES", "RJ"]


def malha_uf():
    return json.loads(MALHA.read_text(encoding="utf-8"))["features"]


def spec_mapa():
    t = "(datum['Valor do mapa'] - datum.vmin) / max(datum.vmax - datum.vmin, 1e-9)"
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "projection": {"type": "mercator"},
        "transform": [{"lookup": "UF", "from": {"data": {"values": malha_uf()}, "key": "properties.uf"}, "as": "geo"},
                      {"filter": "isValid(datum.geo) && isValid(datum['Valor do mapa'])"},
                      {"joinaggregate": [{"op": "min", "field": "Valor do mapa", "as": "vmin"},
                                         {"op": "max", "field": "Valor do mapa", "as": "vmax"}]},
                      {"calculate": t, "as": "t"},
                      {"calculate": ROTULO_METRICA, "as": "rotulo"},
                      {"calculate": "datum.geo.properties.lon", "as": "lon"},
                      {"calculate": "datum.geo.properties.lat", "as": "lat"}],
        "layer": [
            {"mark": {"type": "geoshape"},
             "encoding": {
                 "shape": {"field": "geo", "type": "geojson"},
                 "stroke": {"condition": {"test": em_destaque("Valor do mapa"), "value": INK}, "value": "#FFFFFF"},
                 "strokeWidth": {"condition": {"test": em_destaque("Valor do mapa"), "value": 2}, "value": 0.8},
                 "color": {"field": "Valor do mapa", "type": "quantitative",
                           "scale": {"range": ["#F3F2F1", "#252423"]},
                           "legend": {"orient": "bottom-left", "direction": "vertical", "title": None,
                                      "gradientLength": 90, "gradientThickness": 10, "labelExpr": LEGENDA_MAPA,
                                      "tickCount": 3}},
                 "opacity": esmaecer(*CAMPOS_REALCE_UF),
                 "tooltip": TT_UF}},
            {"transform": [{"filter": f"indexof({json.dumps(SEM_ROTULO)}, datum.UF) < 0"}],
             "mark": {"type": "text", "fontSize": 9, "fontWeight": "bold"},
             "encoding": {"longitude": {"field": "lon", "type": "quantitative"},
                          "latitude": {"field": "lat", "type": "quantitative"},
                          "text": {"field": "UF"},
                          "opacity": esmaecer(*CAMPOS_REALCE_UF),
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
                          "color": {"condition": {"test": em_destaque("Valor do mapa"), "value": AMARELO},
                                    "value": "#252423"},
                          "opacity": esmaecer(*CAMPOS_REALCE_UF), "tooltip": TT_UF}},
            {"mark": {"type": "text", "align": "left", "dx": 4, "fontSize": 9, "color": CINZA},
             "encoding": {"x": {"field": "Valor do mapa", "type": "quantitative"}, "text": {"field": "rotulo"},
                          "opacity": esmaecer(*CAMPOS_REALCE_UF)}}]}


def spec_dispersao():
    """Medianas calculadas sobre as 27 capitais: o clique no mapa ou no ranking realça uma UF aqui
    (realce cruzado), sem filtrar, então as linhas das medianas não se mexem."""
    X, Y = "Tarifa sem tributos 12m", "ICMS efetivo 12m"
    eixo_x = {"type": "quantitative", "scale": {"zero": False}, "title": "Tarifa sem tributos (R$/kWh)",
              "axis": {"format": "$,.2f", "tickCount": 4}}
    eixo_y = {"type": "quantitative", "scale": {"zero": False}, "title": "ICMS efetivo",
              "axis": {"format": ".0%", "tickCount": 4}}
    canto = {"transform": [{"window": [{"op": "row_number", "as": "k"}]}, {"filter": "datum.k == 1"}]}
    destaque = em_destaque(X)
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container", "padding": {"top": 16},
        "transform": [{"filter": f"isValid(datum['{X}']) && isValid(datum['{Y}'])"},
                      {"joinaggregate": [{"op": "median", "field": X, "as": "mx"},
                                         {"op": "median", "field": Y, "as": "my"}]},
                      {"calculate": ROTULO_METRICA, "as": "rotulo"}],
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
            {"mark": {"type": "circle", "opacity": 0.85},
             "encoding": {"x": {"field": X, **eixo_x}, "y": {"field": Y, **eixo_y},
                          "color": {"condition": {"test": destaque, "value": AMARELO}, "value": "#252423"},
                          "size": {"condition": {"test": destaque, "value": 160}, "value": 70},
                          "opacity": esmaecer(X, base=0.85), "tooltip": TT_UF}},
            *[{"transform": [{"filter": teste}],
               "mark": {"type": "text", "align": "left", "dx": 7, "fontSize": tam, "color": cor_txt, "fontWeight": peso},
               "encoding": {"x": {"field": X, **eixo_x}, "y": {"field": Y, **eixo_y}, "text": {"field": "UF"},
                            "opacity": esmaecer(X)}}
              for teste, tam, cor_txt, peso in ((f"!{destaque}", 9, CINZA, "normal"), (destaque, 11, INK, "bold"))]]}


def spec_acumulado():
    series = ["Custo acumulado combustão", "Custo acumulado elétrico"]
    c, e = series
    return {
        "data": {"name": "dataset"}, "width": "container", "height": "container",
        "transform": [
            {"calculate": f"isValid(datum['{c}']) && isValid(datum['{e}']) ? (datum['{c}'] >= datum['{e}'] ? "
                          f"format(datum['{c}'] - datum['{e}'], '$,.0f') + ' a favor do ' + datum['Rótulo elétrico'] : "
                          f"format(datum['{e}'] - datum['{c}'], '$,.0f') + ' a favor do ' + datum['Rótulo combustão']) : '—'",
             "as": "Saldo no ano"},
            {"calculate": f"format(datum['{c}'], '$,.0f')", "as": "tt_c"},
            {"calculate": f"format(datum['{e}'], '$,.0f')", "as": "tt_e"},
            # último ano com valor: o Power BI manda todos os anos do eixo (as medidas de rótulo nunca ficam vazias)
            {"calculate": f"isValid(datum['{c}']) || isValid(datum['{e}']) ? datum['Ano de uso'] : null", "as": "_a_ok"},
            {"joinaggregate": [{"op": "max", "field": "_a_ok", "as": "amax"}]}],
        "layer": [
            {"transform": [{"window": [{"op": "row_number", "as": "k"}]}, {"filter": "datum.k == 1"},
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
            {"transform": [
                {"fold": series, "as": ["serie", "valor"]}, {"filter": "isValid(datum.valor)"},
                {"calculate": f"datum.serie == '{c}' ? datum['Rótulo combustão'] : datum['Rótulo elétrico']",
                 "as": "Carro"},
                {"calculate": f"datum.serie == '{c}' ? 1 : 2", "as": "tipo"}],
             "mark": {"type": "line", "strokeWidth": 3, "point": {"filled": True, "size": 40}},
             "encoding": {
                 "x": {"field": "Ano de uso", "type": "quantitative", "title": "Anos de uso",
                       "axis": {"tickMinStep": 1, "format": "d"}},
                 "y": {"field": "valor", "type": "quantitative", "title": "Compra + energia acumulada",
                       "scale": {"zero": False}, "axis": {"format": "$,.0f", "tickCount": 5}},
                 "color": {"field": "Carro", "type": "nominal", "sort": {"field": "tipo", "op": "min"},
                           "scale": {"range": [INK, COR_ELETRICO]},
                           "legend": {"orient": "top", "title": None, "direction": "horizontal"}}}},
            # coluna de um ano inteiro (cortada nas pontas para não alargar o eixo): leva a página de dica
            {"transform": [{"filter": f"isValid(datum['{c}']) || isValid(datum['{e}'])"},
                           {"calculate": "max(datum['Ano de uso'] - 0.5, 0)", "as": "_x0"},
                           {"calculate": "min(datum['Ano de uso'] + 0.5, datum.amax)", "as": "_x1"}],
             "mark": {"type": "rect", "color": INK, "opacity": 0.01},
             "encoding": {"x": {"field": "_x0", "type": "quantitative", "title": "Anos de uso"}, "x2": {"field": "_x1"},
                          "y": {"value": 0}, "y2": {"value": {"expr": "height"}},
                          "tooltip": [{"field": "Ano de uso", "title": "Ano de uso"},
                                      {"field": "tt_c", "title": "Combustão: compra + energia"},
                                      {"field": "tt_e", "title": "Elétrico: compra + energia"},
                                      {"field": "Saldo no ano"}]}}]}


# ----------------------------------------------------------------------------------------------
# Medidas HTML
# ----------------------------------------------------------------------------------------------

CSS_BASE = "*{font-family:'Segoe UI',sans-serif;box-sizing:border-box}html,body{margin:0}.vazio{font-size:13px;color:#8A8886}"
CSS_CTX = CSS_BASE + ".ctx{font-size:12px;color:#605E5C;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" \
    ".ctx b{color:#191919;font-weight:600}.ctx span{margin:0 8px;color:#C8C6C4}"
CSS_KPI = CSS_BASE + """html,body{overflow:hidden}
.cab{font-size:11px;color:#605E5C;margin:0 2px 4px 2px;line-height:1.3}
.kpis{display:flex;gap:10px}
.card{flex:1;background:#FFFFFF;border:1px solid #E1DFDD;border-top:3px solid #191919;padding:6px 12px;min-width:0;container-type:inline-size;overflow:hidden}
.card.el{border-top-color:#F2C811}
.rot{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:#605E5C;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.val{font-size:clamp(15px,13cqi,24px);font-weight:600;color:#191919;line-height:1.15;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.un{font-size:12px;font-weight:400;color:#605E5C}.vs{font-size:14px;color:#A19F9D;font-weight:400}
.sub{font-size:11px;color:#605E5C;margin-top:2px;line-height:1.3;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}"""
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
CSS_ROLAGEM = "html,body{overflow-y:auto}"
CSS_DICA = CSS_BASE + """html,body{background:#191919;height:100%;overflow:hidden}
.tt{background:#191919;color:#FFFFFF;padding:12px 14px;border-top:3px solid #F2C811;min-height:100%}
.k{font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:#F2C811;font-weight:700}
.t{font-size:15px;font-weight:600;margin:2px 0 7px}.t small{font-size:11px;font-weight:400;color:#C8C6C4}
.g{display:flex;gap:14px;margin-bottom:6px}.g>div{flex:1;min-width:0}
.v{font-size:18px;font-weight:600;white-space:nowrap}.v small{font-size:10px;font-weight:400;color:#C8C6C4}
.l{font-size:10px;color:#C8C6C4;line-height:1.35}
.c{font-size:11px;color:#E1DFDD;margin-bottom:5px;line-height:1.35}.c b{color:#FFFFFF}
.ruim{color:#FF8A65}.bom{color:#7FD17F}
.bar{display:flex;height:8px;background:#3C3C41}.bar span{display:block;height:8px}
.f{font-size:10px;color:#C8C6C4;border-top:1px solid #3C3C41;padding-top:5px;margin-top:3px}
.n{font-size:10px;color:#F2C811;margin-top:4px;line-height:1.35}"""
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
    ("Mapa das UFs", "IBGE, malhas territoriais (API v3), simplificada para o painel",
     "https://servicodados.ibge.gov.br/api/docs/malhas?versao=3"),
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
VAR _per = FORMAT ( MIN ( 'Calendário'[Mês] ), "mmm/yyyy" ) & " a " & FORMAT ( MAX ( 'Calendário'[Mês] ), "mmm/yyyy" )
RETURN
    "<div class='ctx'><b>" & [_Comparação] & "</b><span>·</span>" & _uf & "<span>·</span>" & _per
        & "<span>·</span>" & _val & "<span>·</span>" & _tri & "</div>\"""", "Linha de contexto abaixo do título; resume os filtros da gaveta")

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
        & {c('"Elétrico por km"', 'FORMAT ( _ek, "R$ #,0.00" )',
             '[_Nome combustão] & " a gasolina: " & FORMAT ( _gk, "R$ #,0.00" ) & " por km"', el=True)}
        & {c('"Economia por ano"', 'FORMAT ( _eco, "R$ #,0" )',
             '"com " & FORMAT ( [Km por ano escolhido], "#,0" ) & " km por ano"')}
        & {c('"Diferença na compra"', 'IF ( _sem_preco, "—", FORMAT ( _dif, "R$ #,0" ) )',
             'IF ( _sem_preco, "sem preço de site para o " & [_Nome elétrico], FORMAT ( _pe, "R$ #,0" ) & " − " & FORMAT ( _pc, "R$ #,0" ) )')}
        & "<div class='card'><div class='rot'>Paga a diferença em</div>" & _pay & "</div>"
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

    add("Filtros · botão", f"""VAR _n =
    INT ( ISFILTERED ( 'Estados'[Estado] ) ) + INT ( ISFILTERED ( 'Calendário'[Mês] ) )
        + INT ( [_Comparação] <> {dax_txt(COMPARACAO_PADRAO)} ) + INT ( NOT [_Real] ) + INT ( NOT [_Com tributos] )
RETURN
    "Filtros" & IF ( _n > 0, "  ·  " & _n )""", "Texto do botão que abre a gaveta: conta os filtros fora do padrão")

    def var_html(v):
        return (f'IF ( ISBLANK ( {v} ), "<span class=\'l\'>—</span>", IF ( {v} > 0, "<span class=\'ruim\'>▲ ", '
                f'"<span class=\'bom\'>▼ " ) & FORMAT ( ABS ( {v} ), "0%" ) & "</span>" )')

    def celula(rot, val, var):
        return (f'"<div><div class=\'l\'>{rot}</div><div class=\'v\'>" & FORMAT ( {val}, "R$ #,0.00" ) & "</div>'
                f'<div class=\'l\'>" & {var_html(var)} & "</div></div>"')

    add("html Dica mês", f"""VAR _f = MAX ( 'Calendário'[Mês] )
VAR _aa = EDATE ( _f, -12 )
VAR _el = [Custo elétrico]
VAR _ga = [Custo gasolina]
VAR _et = [Custo etanol]
VAR _elA = CALCULATE ( [Custo elétrico], REMOVEFILTERS ( 'Calendário' ), 'Calendário'[Mês] = _aa )
VAR _gaA = CALCULATE ( [Custo gasolina], REMOVEFILTERS ( 'Calendário' ), 'Calendário'[Mês] = _aa )
VAR _etA = CALCULATE ( [Custo etanol], REMOVEFILTERS ( 'Calendário' ), 'Calendário'[Mês] = _aa )
VAR _vEl = IF ( NOT ISBLANK ( _elA ), DIVIDE ( _el - _elA, _elA ) )
VAR _vGa = IF ( NOT ISBLANK ( _gaA ), DIVIDE ( _ga - _gaA, _gaA ) )
VAR _vEt = IF ( NOT ISBLANK ( _etA ), DIVIDE ( _et - _etA, _etA ) )
VAR _uf =
    IF (
        ISFILTERED ( 'Estados' ) && HASONEVALUE ( 'Estados'[UF] ),
        SELECTEDVALUE ( 'Estados'[Estado] ),
        "Brasil, média das capitais"
    )
VAR _raz = [Razão de preço etanol/gasolina]
VAR _ren = [Razão de rendimento do carro]
VAR _marco = [Marco legal]
VAR _samp = [Meses com tarifa do SAMP]
RETURN
    IF (
        NOT HASONEVALUE ( 'Calendário'[Mês] ) || ( ISBLANK ( _el ) && ISBLANK ( _ga ) ),
        "<div class='tt'><div class='l'>Sem dados para este mês.</div></div>",
        "<div class='tt'><div class='k'>Mês · " & _uf & "</div><div class='t'>" & FORMAT ( _f, "mmmm \\d\\e yyyy" )
            & "</div><div class='g'>" & {celula("Elétrico", "_el", "_vEl")} & {celula("Gasolina", "_ga", "_vGa")}
            & {celula("Etanol", "_et", "_vEt")} & "</div><div class='l' style='margin:-2px 0 7px'>R$ por 100 km · "
            & "variação contra " & FORMAT ( _aa, "mmm/yyyy" ) & "</div>"
            & "<div class='c'>Elétrico <b>" & FORMAT ( DIVIDE ( _ga, _el ), "0.0" ) & " vezes</b> mais barato que a "
            & "gasolina: " & FORMAT ( _ga - _el, "R$ #,0.00" ) & " a menos a cada 100 km.</div>"
            & "<div class='c'>Preço: eletricidade " & FORMAT ( [Preço eletricidade], "R$ #,0.00" ) & "/kWh · gasolina "
            & FORMAT ( [Preço gasolina], "R$ #,0.00" ) & "/l · etanol " & FORMAT ( [Preço etanol], "R$ #,0.00" ) & "/l</div>"
            & IF ( NOT ISBLANK ( _raz ), "<div class='c'>Etanol a " & FORMAT ( _raz, "0%" ) & " do preço da gasolina: "
                & IF ( _raz < _ren, "<span class='bom'>compensa</span>", "<span class='ruim'>não compensa</span>" )
                & " no " & [_Nome combustão] & " (limite " & FORMAT ( _ren, "0.0%" ) & ").</div>" )
            & "<div class='c'>Tributos no preço: eletricidade " & FORMAT ( [% tributos eletricidade], "0%" )
            & " · gasolina " & FORMAT ( [% tributos gasolina], "0%" ) & IF ( _f < DATE ( 2023, 6, 1 ), " (só federais)" )
            & "</div><div class='f'>Salário mínimo: " & FORMAT ( [Horas de SM elétrico], "0.0" ) & " h de trabalho "
            & "pagam 100 km no elétrico; na gasolina, " & FORMAT ( [Horas de SM gasolina], "0.0" ) & " h.</div>"
            & IF ( NOT ISBLANK ( _marco ), "<div class='n'>" & _marco & "</div>" )
            & IF ( _samp > 0, "<div class='n'>Tarifa média do SAMP em " & _samp
                & IF ( _samp = 1, " capital", " capitais" ) & " neste mês (sem tarifa homologada na base).</div>" )
            & "</div>"
    )""", "Dica de ferramenta do mês (página dica_mes)")

    add("html Dica UF", f"""VAR _f = MAX ( 'Calendário'[Mês] )
VAR _el = [Custo elétrico 12m]
VAR _ga = [Custo gasolina 12m]
VAR _ic = [ICMS efetivo 12m]
VAR _tab =
    ADDCOLUMNS (
        CALCULATETABLE ( VALUES ( 'Estados'[UF] ), REMOVEFILTERS ( 'Estados' ) ),
        "@el", VAR _x = 'Estados'[UF] RETURN CALCULATE ( [Custo elétrico 12m], REMOVEFILTERS ( 'Estados' ), 'Estados'[UF] = _x ),
        "@ga", VAR _y = 'Estados'[UF] RETURN CALCULATE ( [Custo gasolina 12m], REMOVEFILTERS ( 'Estados' ), 'Estados'[UF] = _y ),
        "@ic", VAR _z = 'Estados'[UF] RETURN CALCULATE ( [ICMS efetivo 12m], REMOVEFILTERS ( 'Estados' ), 'Estados'[UF] = _z )
    )
VAR _n = COUNTROWS ( FILTER ( _tab, NOT ISBLANK ( [@el] ) ) )
VAR _rEl = COUNTROWS ( FILTER ( _tab, NOT ISBLANK ( [@el] ) && [@el] < _el ) ) + 1
VAR _rGa = COUNTROWS ( FILTER ( _tab, NOT ISBLANK ( [@ga] ) && [@ga] < _ga ) ) + 1
VAR _rIc = COUNTROWS ( FILTER ( _tab, [@ic] > _ic ) ) + 1
VAR _brEl = AVERAGEX ( _tab, [@el] )
VAR _dBr = DIVIDE ( _el - _brEl, _brEl )
VAR _ps = CALCULATE ( AVERAGEX ( VALUES ( 'Calendário'[Mês] ), [Eletricidade: sem tributos] ), {JANELA} )
VAR _pi = CALCULATE ( AVERAGEX ( VALUES ( 'Calendário'[Mês] ), [Eletricidade: ICMS] ), {JANELA} )
VAR _pp = CALCULATE ( AVERAGEX ( VALUES ( 'Calendário'[Mês] ), [Eletricidade: PIS/Cofins] ), {JANELA} )
VAR _pt = _ps + _pi + _pp
VAR _ini = EDATE ( _f, -23 )
VAR _s =
    ADDCOLUMNS (
        CALCULATETABLE ( VALUES ( 'Calendário'[Mês] ), REMOVEFILTERS ( 'Calendário' ), 'Calendário'[Mês] >= _ini, 'Calendário'[Mês] <= _f ),
        "@e", [Custo elétrico],
        "@g", [Custo gasolina]
    )
VAR _mx = MAXX ( _s, MAX ( [@e], [@g] ) )
VAR _linE = CONCATENATEX ( FILTER ( _s, NOT ISBLANK ( [@e] ) ),
    FORMAT ( DATEDIFF ( _ini, [Mês], MONTH ) * 330 / 23, "0.0", "en-US" ) & "," & FORMAT ( 40 - [@e] / _mx * 36, "0.0", "en-US" ), " ", [Mês], ASC )
VAR _linG = CONCATENATEX ( FILTER ( _s, NOT ISBLANK ( [@g] ) ),
    FORMAT ( DATEDIFF ( _ini, [Mês], MONTH ) * 330 / 23, "0.0", "en-US" ) & "," & FORMAT ( 40 - [@g] / _mx * 36, "0.0", "en-US" ), " ", [Mês], ASC )
VAR _tSamp = CALCULATE ( [Meses com tarifa do SAMP], {JANELA} )
VAR _iImp = CALCULATE ( [Meses com ICMS imputado], {JANELA} )
VAR _ress =
    IF ( _tSamp > 0, _tSamp & " com tarifa média do SAMP" )
        & IF ( _tSamp > 0 && _iImp > 0, " e " )
        & IF ( _iImp > 0, _iImp & " com ICMS do mês válido mais próximo" )
RETURN
    IF (
        NOT HASONEVALUE ( 'Estados'[UF] ) || ISBLANK ( _el ),
        "<div class='tt'><div class='l'>Passe o mouse sobre uma capital.</div></div>",
        "<div class='tt'><div class='k'>Estado · 12 meses até " & FORMAT ( _f, "mmm/yyyy" ) & "</div><div class='t'>"
            & SELECTEDVALUE ( 'Estados'[Estado] ) & " <small>· " & SELECTEDVALUE ( 'Estados'[Capital] ) & " · "
            & SELECTEDVALUE ( 'Estados'[Distribuidora] ) & "</small></div>"
            & "<div class='g'><div><div class='l'>Elétrico · " & [_Nome elétrico] & "</div><div class='v'>"
            & FORMAT ( _el, "R$ #,0.00" ) & "<small> /100 km</small></div><div class='l'>" & _rEl & "º mais barato de "
            & _n & "</div></div><div><div class='l'>Gasolina · " & [_Nome combustão] & "</div><div class='v'>"
            & FORMAT ( _ga, "R$ #,0.00" ) & "<small> /100 km</small></div><div class='l'>" & _rGa & "º mais barata de "
            & _n & "</div></div></div>"
            & "<div class='c'>Economia de <b>" & FORMAT ( _ga - _el, "R$ #,0.00" ) & "</b> a cada 100 km ("
            & FORMAT ( DIVIDE ( _ga, _el ), "0.0" ) & " vezes). Elétrico "
            & IF ( _dBr >= 0, "<span class='ruim'>▲ ", "<span class='bom'>▼ " ) & FORMAT ( ABS ( _dBr ), "0%" )
            & "</span> contra a média das capitais.</div>"
            & "<div class='l'>Preço da eletricidade: tarifa + bandeira " & FORMAT ( DIVIDE ( _ps, _pt ), "0%" )
            & " · <span style='color:#F2C811'>ICMS " & FORMAT ( DIVIDE ( _pi, _pt ), "0%" ) & "</span> · PIS/Cofins "
            & FORMAT ( DIVIDE ( _pp, _pt ), "0%" ) & "</div><div class='bar' style='margin:3px 0 7px'>"
            & "<span style='width:" & FORMAT ( DIVIDE ( _ps, _pt ) * 100, "0.0", "en-US" ) & "%;background:#FFFFFF'></span>"
            & "<span style='width:" & FORMAT ( DIVIDE ( _pi, _pt ) * 100, "0.0", "en-US" ) & "%;background:#F2C811'></span>"
            & "<span style='width:" & FORMAT ( DIVIDE ( _pp, _pt ) * 100, "0.0", "en-US" ) & "%;background:#8A8886'></span></div>"
            & "<div class='c'>ICMS efetivo na conta de luz: " & FORMAT ( _ic, "0.0%" ) & ", o " & _rIc & "º maior de "
            & _n & ".</div>"
            & "<svg width='100%' height='42' viewBox='0 0 330 42' preserveAspectRatio='none'><polyline points='" & _linG
            & "' fill='none' stroke='#8A8886' stroke-width='1.5'/><polyline points='" & _linE
            & "' fill='none' stroke='#F2C811' stroke-width='2'/></svg><div class='f'>24 meses até "
            & FORMAT ( _f, "mmm/yyyy" ) & ": <span style='color:#F2C811'>elétrico</span> e "
            & "<span style='color:#C8C6C4'>gasolina</span>, R$ por 100 km</div>"
            & IF ( _ress <> "", "<div class='n'>Nos 12 meses: " & _ress & ".</div>" )
            & "</div>"
    )""", "Dica de ferramenta da UF (página dica_uf), acionada pelo mapa, pelo ranking e pela dispersão")

    add("html Dica tributos", """VAR _f = MAX ( 'Calendário'[Mês] )
VAR _aa = EDATE ( _f, -12 )
VAR _dentro = _f < DATE ( 2023, 6, 1 )
VAR _gs = [Gasolina: sem tributos]
VAR _gd = [Gasolina: sem federais, ICMS dentro]
VAR _gi = [Gasolina: ICMS]
VAR _gp = [Gasolina: PIS/Cofins]
VAR _gc = [Gasolina: CIDE]
VAR _gt = _gs + _gd + _gi + _gp + _gc
VAR _es = [Eletricidade: sem tributos]
VAR _ei = [Eletricidade: ICMS]
VAR _ep = [Eletricidade: PIS/Cofins]
VAR _et = _es + _ei + _ep
VAR _pg = [% tributos gasolina]
VAR _pe = [% tributos eletricidade]
VAR _pgA = CALCULATE ( [% tributos gasolina], REMOVEFILTERS ( 'Calendário' ), 'Calendário'[Mês] = _aa )
VAR _peA = CALCULATE ( [% tributos eletricidade], REMOVEFILTERS ( 'Calendário' ), 'Calendário'[Mês] = _aa )
VAR _uf =
    IF (
        ISFILTERED ( 'Estados' ) && HASONEVALUE ( 'Estados'[UF] ),
        SELECTEDVALUE ( 'Estados'[Estado] ),
        "Brasil, média das capitais"
    )
VAR _val = IF ( [_Real], "em reais de " & FORMAT ( [_Último mês com dados], "mmm/yyyy" ) & " (IPCA)", "nominais" )
VAR _marco = [Marco legal]
RETURN
    IF (
        NOT HASONEVALUE ( 'Calendário'[Mês] ) || ( ISBLANK ( _gt ) && ISBLANK ( _et ) ),
        "<div class='tt'><div class='l'>Sem dados para este mês.</div></div>",
        "<div class='tt'><div class='k'>Tributos · " & _uf & "</div><div class='t'>" & FORMAT ( _f, "mmmm \\d\\e yyyy" )
            & "</div><div class='g'><div><div class='l'>Gasolina · " & [_Nome combustão] & "</div><div class='v'>"
            & IF ( ISBLANK ( _gt ), "—", FORMAT ( _gt, "R$ #,0.00" ) ) & "<small> /100 km</small></div><div class='l'>"
            & FORMAT ( _pg, "0%" ) & " de tributos" & IF ( _dentro, " federais" ) & IF ( ISBLANK ( _pgA ) || ISBLANK ( _pg ), "", " · " & IF ( _pg >= _pgA, "<span class='ruim'>▲ ", "<span class='bom'>▼ " ) & FORMAT ( ABS ( _pg - _pgA ) * 100, "0.0" ) & " p.p.</span> em 12 meses" ) & "</div></div>"
            & "<div><div class='l'>Eletricidade · " & [_Nome elétrico] & "</div><div class='v'>"
            & IF ( ISBLANK ( _et ), "—", FORMAT ( _et, "R$ #,0.00" ) ) & "<small> /100 km</small></div><div class='l'>"
            & FORMAT ( _pe, "0%" ) & " de tributos" & IF ( ISBLANK ( _peA ) || ISBLANK ( _pe ), "", " · " & IF ( _pe >= _peA, "<span class='ruim'>▲ ", "<span class='bom'>▼ " ) & FORMAT ( ABS ( _pe - _peA ) * 100, "0.0" ) & " p.p.</span> em 12 meses" ) & "</div></div></div>"
            & IF ( NOT ISBLANK ( _gt ),
                "<div class='l'>Gasolina: " & IF ( _dentro,
                    "preço com ICMS " & FORMAT ( DIVIDE ( _gd, _gt ), "0%" ),
                    "sem tributos " & FORMAT ( DIVIDE ( _gs, _gt ), "0%" ) & " · <span style='color:#F2C811'>ICMS "
                        & FORMAT ( DIVIDE ( _gi, _gt ), "0%" ) & "</span>" )
                & " · PIS/Cofins " & FORMAT ( DIVIDE ( _gp, _gt ), "0%" ) & " · CIDE " & FORMAT ( DIVIDE ( _gc, _gt ), "0%" )
                & "</div>" & IF ( _dentro, "<div class='bar' style='margin:3px 0 6px'><span style='width:" & FORMAT ( DIVIDE ( _gd, _gt ) * 100, "0.0", "en-US" ) & "%;background:#B3B0AD'></span><span style='width:" & FORMAT ( DIVIDE ( _gp, _gt ) * 100, "0.0", "en-US" ) & "%;background:#8A8886'></span><span style='width:" & FORMAT ( DIVIDE ( _gc, _gt ) * 100, "0.0", "en-US" ) & "%;background:#605E5C'></span></div>", "<div class='bar' style='margin:3px 0 6px'><span style='width:" & FORMAT ( DIVIDE ( _gs, _gt ) * 100, "0.0", "en-US" ) & "%;background:#E1DFDD'></span><span style='width:" & FORMAT ( DIVIDE ( _gi, _gt ) * 100, "0.0", "en-US" ) & "%;background:#F2C811'></span><span style='width:" & FORMAT ( DIVIDE ( _gp, _gt ) * 100, "0.0", "en-US" ) & "%;background:#8A8886'></span><span style='width:" & FORMAT ( DIVIDE ( _gc, _gt ) * 100, "0.0", "en-US" ) & "%;background:#605E5C'></span></div>" ) )
            & IF ( NOT ISBLANK ( _et ),
                "<div class='l'>Eletricidade: tarifa + bandeira " & FORMAT ( DIVIDE ( _es, _et ), "0%" )
                & " · <span style='color:#F2C811'>ICMS " & FORMAT ( DIVIDE ( _ei, _et ), "0%" ) & "</span> · PIS/Cofins "
                & FORMAT ( DIVIDE ( _ep, _et ), "0%" ) & "</div>" & "<div class='bar' style='margin:3px 0 6px'><span style='width:" & FORMAT ( DIVIDE ( _es, _et ) * 100, "0.0", "en-US" ) & "%;background:#E1DFDD'></span><span style='width:" & FORMAT ( DIVIDE ( _ei, _et ) * 100, "0.0", "en-US" ) & "%;background:#F2C811'></span><span style='width:" & FORMAT ( DIVIDE ( _ep, _et ) * 100, "0.0", "en-US" ) & "%;background:#8A8886'></span></div>" )
            & "<div class='c'>A cada 100 km, <b>" & FORMAT ( _gi + _gp + _gc, "R$ #,0.00" ) & "</b> da gasolina são "
            & IF ( _dentro, "tributos federais (o ICMS está dentro do preço)", "tributos" ) & ", contra <b>"
            & FORMAT ( _ei + _ep, "R$ #,0.00" ) & "</b> na eletricidade.</div>"
            & IF ( NOT ISBLANK ( _pg ) && NOT ISBLANK ( _pe ),
                "<div class='c'>Em % do preço, a mais tributada é " & IF ( _pe > _pg, "a conta de luz", "a gasolina" )
                & IF ( _dentro, ", com a gasolina contando só os tributos federais", "" ) & ".</div>" )
            & "<div class='f'>Preço: gasolina " & FORMAT ( [Preço gasolina], "R$ #,0.00" ) & "/l · eletricidade "
            & FORMAT ( [Preço eletricidade], "R$ #,0.00" ) & "/kWh · valores " & _val & "</div>"
            & IF ( _dentro, "<div class='n'>Até mai./2023 o ICMS da gasolina era um percentual de cada estado e fica "
                & "dentro do preço; desde jun./2023 é um valor por litro e aparece separado.</div>" )
            & IF ( NOT ISBLANK ( _marco ), "<div class='n'>" & _marco & "</div>" )
            & "</div>"
    )""", "Dica de ferramenta dos tributos do mês (página dica_tributos), acionada pelos gráficos da página Impostos")

    add("html Dica ano", """VAR _a = SELECTEDVALUE ( 'Ano de uso'[Ano de uso] )
VAR _pc = [Preço do carro a combustão]
VAR _pe = [Preço do carro elétrico]
VAR _cc = [Custo por ano combustão]
VAR _ce = [Custo por ano elétrico]
VAR _tc = [Custo acumulado combustão]
VAR _te = [Custo acumulado elétrico]
VAR _dif = _pe - _pc
VAR _eco = _a * ( _cc - _ce )
VAR _cob = MAX ( MIN ( DIVIDE ( _eco, _dif ), 1 ), 0 )
VAR _saldo = _tc - _te
VAR _anos = [Anos para pagar]
VAR _nc = [_Nome combustão]
VAR _ne = [_Nome elétrico]
VAR _f = MAX ( 'Calendário'[Mês] )
VAR _uf =
    IF (
        ISFILTERED ( 'Estados' ) && HASONEVALUE ( 'Estados'[UF] ),
        SELECTEDVALUE ( 'Estados'[Estado] ),
        "Brasil, média das capitais"
    )
RETURN
    IF (
        ISBLANK ( _tc ) || ISBLANK ( _te ),
        "<div class='tt'><div class='l'>Passe o mouse sobre um ano da curva.</div></div>",
        "<div class='tt'><div class='k'>Simulador · " & _uf & "</div><div class='t'>"
            & IF ( _a = 0, "Na compra", "Depois de " & _a & IF ( _a = 1, " ano", " anos" ) ) & " <small>· "
            & FORMAT ( _a * [Km por ano escolhido], "#,0" ) & " km rodados</small></div>"
            & "<div class='g'><div><div class='l'>" & _nc & " (gasolina)</div><div class='v'>" & FORMAT ( _tc, "R$ #,0" )
            & "</div><div class='l'>compra " & FORMAT ( _pc, "R$ #,0" ) & " + energia " & FORMAT ( _a * _cc, "R$ #,0" )
            & "</div></div><div><div class='l'>" & _ne & " (elétrico)</div><div class='v'>" & FORMAT ( _te, "R$ #,0" )
            & "</div><div class='l'>compra " & FORMAT ( _pe, "R$ #,0" ) & " + energia " & FORMAT ( _a * _ce, "R$ #,0" )
            & "</div></div></div>"
            & "<div class='c'>Saldo: <b>" & FORMAT ( ABS ( _saldo ), "R$ #,0" ) & "</b> a favor do "
            & IF ( _saldo >= 0, _ne, _nc ) & ".</div>"
            & IF ( _dif > 0,
                "<div class='l'>A economia em energia já cobriu " & FORMAT ( _cob, "0%" ) & " dos "
                    & FORMAT ( _dif, "R$ #,0" ) & " que o elétrico custa a mais na compra</div>"
                    & "<div class='bar' style='margin:3px 0 7px'><span style='width:"
                    & FORMAT ( _cob * 100, "0.0", "en-US" ) & "%;background:#F2C811'></span></div>",
                "<div class='c'>Na compra, o elétrico sai " & FORMAT ( -_dif, "R$ #,0" ) & " mais barato.</div>" )
            & "<div class='c'>Energia por ano: " & FORMAT ( _cc, "R$ #,0" ) & " no " & _nc & " e "
            & FORMAT ( _ce, "R$ #,0" ) & " no " & _ne & " (" & FORMAT ( ABS ( _cc - _ce ), "R$ #,0" )
            & IF ( _cc >= _ce, " a menos", " a mais" ) & " com o elétrico).</div>"
            & "<div class='c'>"
            & SWITCH (
                TRUE (),
                _dif <= 0 && _cc >= _ce, "Sem empate a esperar: o elétrico fica à frente desde a compra.",
                _dif <= 0, "O elétrico sai mais barato na compra, mas a energia dele custa mais: a vantagem cai a cada ano.",
                ISBLANK ( _anos ), "As curvas não se encontram: a energia do elétrico sai mais cara.",
                _a >= _anos, "As curvas empataram em " & FORMAT ( _anos, "0.0" ) & " anos; daí em diante o elétrico fica à frente.",
                "Empate em " & FORMAT ( _anos, "0.0" ) & " anos; faltam " & FORMAT ( _anos - _a, "0.0" ) & "."
            )
            & "</div><div class='f'>" & FORMAT ( [Recarga em casa escolhida], "0%" ) & " da recarga em casa (tarifa "
            & LOWER ( [Tarifa em casa escolhida] ) & "), o resto a " & FORMAT ( [Carregador escolhido], "R$ #,0.00" )
            & "/kWh. Energia com o preço médio de " & FORMAT ( EDATE ( _f, -11 ), "mmm/yyyy" ) & " a "
            & FORMAT ( _f, "mmm/yyyy" ) & ". Fora da conta: manutenção, seguro, IPVA e depreciação.</div></div>"
    )""", "Dica de ferramenta da curva do simulador (página dica_ano), por ano de uso")
    return M


# ----------------------------------------------------------------------------------------------
# Páginas
# ----------------------------------------------------------------------------------------------

Y0 = 124  # topo do conteúdo: abas (12), título (52), linha de contexto (86)
BTN_FILTROS = (1008, 12, 120, 32)  # ao lado do botão Documentação (1136, 12), que o tour cria
GAVETA, GAVETA_X, GAVETA_W, Z_GAVETA = "filtros_gaveta", 920, 360, 40000
NOTA_GAVETA = ("Na página Estados, clique numa capital do mapa, do ranking ou da dispersão para realçá-la nos outros "
               "gráficos; clique de novo para limpar.")


def cabecalho(p: Pagina, contexto="html Contexto", gaveta=True):
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
                                                         alt="Filtros em uso: comparação, estado, período e valores"))
    if gaveta:
        p.add("filtros_botao", *BTN_FILTROS, botao_acao(None, ("Bookmark", f"filtros_{SIGLA[p.nome]}_abrir"),
                                                        fundo=INK, cor_texto="#FFFFFF", medida_texto="Filtros · botão",
                                                        alt="Abrir os filtros"), z=20100)


def botao_acao(texto, acao, fundo=None, cor_texto=INK, tam=10, transp=0, medida_texto=None, alt=None):
    """acao: ('Bookmark', nome) ou ('ClearAllSlicers', None)."""
    t = {"text": {"expr": {"Measure": {"Expression": {"SourceRef": {"Entity": MED}}, "Property": medida_texto}}}
         if medida_texto else s(texto or ""), "fontColor": cor(cor_texto), "fontSize": lit(f"{tam}D"),
         "bold": lit("true")}
    tipo, destino = acao
    link = {"show": lit("true"), "type": s(tipo)}
    if destino:
        link["bookmark"] = s(destino)
    return {"visualType": "actionButton",
            "objects": {
                "icon": [{"properties": {"shapeType": s("blank")}, "selector": {"id": "default"}}],
                "text": [{"properties": {"show": lit("true" if (texto or medida_texto) else "false")}},
                         {"properties": t, "selector": {"id": "default"}}],
                "outline": [{"properties": {"show": lit("false")}}],
                "fill": [{"properties": {"show": lit("true" if fundo else "false")}}]
                + ([{"properties": {"fillColor": cor(fundo), "transparency": lit(f"{transp}D")},
                     "selector": {"id": "default"}}] if fundo else [])},
            "visualContainerObjects": {**container(None, fundo=False, borda=False, padding=0, alt=alt),
                                       "visualLink": [{"properties": link}]},
            "drillFilterOtherVisuals": True}


def rotulo(p: Pagina, nome, x, y, w, texto, z=None, grupo=None):
    p.add(f"rotulo_{nome}", x, y, w, 20, textbox([{"textRuns": [run(texto, 9, INK, True)]}]), z=z, tab=False,
          grupo=grupo)


def gaveta(p: Pagina, itens):
    """Gaveta de filtros à direita (formato E de filtros-menus.md): começa oculta e abre pelo botão Filtros.
    itens: (nome, tabela, coluna, rótulo, modo, único, sincronia, padrão)."""
    sg, g, z = SIGLA[p.nome], GAVETA, Z_GAVETA
    fechar = f"filtros_{sg}_fechar"
    p.grupo(g, "Gaveta de filtros", z)
    p.add("filtros_veu", 0, 0, GAVETA_X, 720, botao_acao(None, ("Bookmark", fechar), fundo=INK, transp=45,
                                                          alt="Fechar os filtros"), z=z + 1, grupo=g)
    p.add("filtros_painel", GAVETA_X, 0, GAVETA_W, 720, textbox([{"textRuns": [run(" ", 8, INK)]}], fundo="#FFFFFF"),
          z=z + 2, tab=False, grupo=g)
    p.add("filtros_filete", GAVETA_X, 0, GAVETA_W, 4, textbox([{"textRuns": [run(" ", 2, AMARELO)]}], fundo=AMARELO),
          z=z + 3, tab=False, grupo=g)
    px, pw = GAVETA_X + 24, GAVETA_W - 48
    p.add("filtros_titulo", px, 24, pw - 40, 48, textbox([{"textRuns": [run("FILTROS", 9, AMARELO_ESCURO, True)]},
                                                          {"textRuns": [run("Valem para todas as páginas", 10, CINZA)]}]),
          z=z + 4, tab=False, grupo=g)
    p.add("filtros_fechar", GAVETA_X + GAVETA_W - 56, 24, 32, 32,
          botao_acao("✕", ("Bookmark", fechar), cor_texto=CINZA, tam=11, alt="Fechar os filtros"), z=z + 50, grupo=g)
    yy = 88
    for k, (nome, tab, col, rot, modo, unico, sync, padrao) in enumerate(itens):
        alto = 56 if modo == "Between" else 44
        rotulo(p, nome, px, yy, pw, rot, z=z + 10 + k, grupo=g)
        p.add(nome, px, yy + 22, pw, alto, slicer(tab, col, modo, unico, sync, padrao=padrao, cabecalho=False),
              z=z + 20 + k, grupo=g)
        yy += 22 + alto + 18
    yy += 6
    p.add("filtros_limpar", px, yy, 150, 34, botao_acao("Limpar filtros", ("ClearAllSlicers", None),
                                                        alt="Limpar os filtros"), z=z + 51, grupo=g)
    p.add("filtros_ok", px + pw - 150, yy, 150, 34, botao_acao("Ver resultado", ("Bookmark", fechar), fundo=AMARELO,
                                                               alt="Fechar os filtros e ver o resultado"),
          z=z + 52, grupo=g)
    p.add("filtros_nota", px, yy + 52, pw, 70, textbox([{"textRuns": [run(NOTA_GAVETA, 9, CINZA)]}]), z=z + 53,
          tab=False, grupo=g)


SIGLA = {"visao_geral": "vg", "impostos": "im", "estados": "es", "simulador": "si", "metodo": "me"}
G_ESTADO = ("filtro_estado", "Estados", "Estado", "Estado (capital)", "Dropdown", False, "Estado", None)
G_COMP = ("filtro_comparacao", "Comparação", "Comparação", "Carros comparados", "Dropdown", True, "Comparação",
          "'" + COMPARACAO_PADRAO + "'")
G_MES = ("filtro_periodo", "Calendário", "Mês", "Período", "Between", False, "Período", None)
G_VAL = ("filtro_valores", "Valores", "Valores", "Valores", "Dropdown", True, "Valores", "'Real'")
G_TRI = ("filtro_tributos", "Tributos", "Tributos", "Tributos", "Dropdown", True, "Tributos", "'Com tributos'")

CAMPOS_HERO = ["Custo elétrico", "Custo gasolina", "Custo etanol", "Marco legal", "Preço eletricidade",
               "Preço gasolina", "Preço etanol"]
CAMPOS_UF = ["Valor do mapa", "Métrica escolhida", "Custo elétrico 12m", "Custo gasolina 12m", "Economia 12m",
             "Tarifa sem tributos 12m", "ICMS efetivo 12m", "Meses com tarifa do SAMP", "Meses com ICMS imputado"]
# entradas do simulador: (nome, tabela, coluna, rótulo, padrão, seleção única)
ENTRADAS = [("filtro_km", "Km por ano", "Km por ano", "Km por ano", "12000L", True),
            ("filtro_recarga", "Recarga em casa (%)", "Recarga em casa (%)", "Recarga em casa (%)", "80L", True),
            ("filtro_tarifa", "Tarifa em casa", "Tarifa em casa", "Tarifa em casa", "'Convencional'", True),
            ("filtro_carregador", "Carregador público", "Carregador público (R$/kWh)", "Carregador (R$/kWh)", "2D",
             True),
            ("filtro_anos", "Anos de uso", "Anos de uso", "Anos de uso", "10L", True),
            None,
            # preços sem seleção única: sem escolha vale o preço do site (seleção única marcaria o 1º item da lista)
            ("filtro_preco_combustao", "Preço do carro a combustão (R$)", "Preço do carro a combustão (R$)",
             "Preço combustão (R$)", None, False),
            ("filtro_preco_eletrico", "Preço do carro elétrico (R$)", "Preço do carro elétrico (R$)",
             "Preço elétrico (R$)", None, False)]
DICAS = [("dica_mes", "Dica: mês", "html Dica mês", 380, 330), ("dica_uf", "Dica: estado", "html Dica UF", 380, 330),
         ("dica_tributos", "Dica: tributos", "html Dica tributos", 380, 330),
         ("dica_ano", "Dica: ano de uso", "html Dica ano", 380, 320)]
# realce cruzado entre os três gráficos da página Estados; os destaques ignoram o clique
INTERACOES_ESTADOS = [{"source": a, "target": b, "type": "HighlightFilter"}
                      for a in ("mapa", "ranking", "dispersao") for b in ("mapa", "ranking", "dispersao") if a != b] \
    + [{"source": a, "target": "destaques", "type": "NoFilter"} for a in ("mapa", "ranking", "dispersao")]


def montar_paginas() -> list[Pagina]:
    P = {nome: Pagina(nome, aba, tit) for nome, aba, tit in PAGINAS}

    p = P["visao_geral"]
    cabecalho(p)
    gaveta(p, [G_ESTADO, G_COMP, G_MES, G_VAL, G_TRI])
    p.add("kpis", 24, Y0, 1232, 112, html_visual("html KPIs", CSS_KPI, fundo=False, borda=False, padding=0,
                                                 alt="Cartões com o custo de rodar 100 km no último mês do período"))
    p.add("linha_custo", 24, 248, 800, 460, deneb_visual(
        [proj_c("Calendário", "Mês")] + [proj_m(m) for m in CAMPOS_HERO], spec_linha_custo(),
        "R$ para rodar 100 km, mês a mês",
        "Linhas com o custo de rodar 100 km com eletricidade, gasolina e etanol desde 2012, com os marcos legais",
        dica="dica_mes"))
    p.add("razao_etanol", 836, 248, 420, 460, deneb_visual(
        [proj_c("Calendário", "Mês"), proj_m("Razão de preço etanol/gasolina"), proj_m("Razão de rendimento do carro")],
        spec_razao_etanol(), "Etanol ou gasolina?",
        "Linha com o preço do etanol dividido pelo da gasolina, contra a regra dos 70 % e o rendimento do carro",
        dica="dica_mes"))

    p = P["impostos"]
    cabecalho(p)
    gaveta(p, [G_ESTADO, G_COMP, G_MES, G_VAL])
    p.add("parcelas_gasolina", 24, Y0, 610, 330, deneb_visual(
        [proj_c("Calendário", "Mês")] + [proj_m(c) for c, _, _ in PARCELAS_GAS], spec_parcelas(PARCELAS_GAS, True),
        "Gasolina: R$ por 100 km, em parcelas",
        "Áreas empilhadas com o custo de 100 km a gasolina separado em preço sem tributos, ICMS, PIS/Cofins e CIDE",
        dica="dica_tributos"))
    p.add("parcelas_eletricidade", 646, Y0, 610, 330, deneb_visual(
        [proj_c("Calendário", "Mês")] + [proj_m(c) for c, _, _ in PARCELAS_ELE], spec_parcelas(PARCELAS_ELE, False),
        "Eletricidade: R$ por 100 km, em parcelas",
        "Áreas empilhadas com o custo de 100 km com eletricidade separado em tarifa com bandeira, ICMS e PIS/Cofins",
        dica="dica_tributos"))
    p.add("pct_tributos", 24, 466, 610, 242, deneb_visual(
        [proj_c("Calendário", "Mês"), proj_m("% tributos eletricidade"), proj_m("% tributos gasolina")],
        spec_pct_tributos(), "Quanto do preço é tributo",
        "Linhas com a parte do preço da eletricidade e da gasolina que é tributo, mês a mês",
        dica="dica_tributos"))
    p.add("marcos", 646, 466, 610, 242, html_visual("html Marcos", CSS_TEXTO, padding=10,
                                                     alt="Tabela com os marcos legais e a norma de cada um"))

    p = P["estados"]
    cabecalho(p)
    gaveta(p, [G_COMP, G_MES, G_VAL, G_TRI])  # sem Estado: aqui a UF se escolhe clicando no mapa
    # seletor dedicado ao mapa e ao ranking: fica junto deles, fora da gaveta
    rotulo(p, "filtro_metrica", 24, Y0, 300, "Métrica do mapa e do ranking")
    p.add("filtro_metrica", 24, Y0 + 20, 300, 40, slicer("Métrica do mapa", "Métrica do mapa", unico=True,
                                                          padrao="'" + METRICAS_MAPA[0] + "'", cabecalho=False))
    campos_uf = [proj_c("Estados", "UF"), proj_c("Estados", "Estado"), proj_c("Estados", "Capital")]
    p.add("mapa", 24, 196, 440, 512, deneb_visual(
        campos_uf + [proj_m(m) for m in CAMPOS_UF], spec_mapa(), "Mapa das capitais (12 meses até o fim do período)",
        "Mapa do Brasil com as 27 UFs coloridas pela métrica escolhida", selecao=True, realce=True, dica="dica_uf"))
    p.add("ranking", 476, 196, 380, 512, deneb_visual(
        campos_uf + [proj_m(m) for m in CAMPOS_UF], spec_ranking(), "Ranking das capitais",
        "Barras com as 27 capitais ordenadas pela métrica escolhida", selecao=True, realce=True, dica="dica_uf"))
    p.add("dispersao", 868, Y0, 388, 370, deneb_visual(
        campos_uf + [proj_m(m) for m in CAMPOS_UF], spec_dispersao(), "Energia cara ou imposto alto?",
        "Dispersão das capitais: tarifa sem tributos no eixo horizontal e ICMS efetivo no vertical",
        selecao=True, realce=True, dica="dica_uf"))
    p.add("destaques", 868, 506, 388, 202, html_visual("html Destaques estados", CSS_ESCURO, escuro=True, padding=12,
                                                        alt="Destaques das capitais nos últimos 12 meses"))
    p.interacoes = INTERACOES_ESTADOS

    p = P["simulador"]
    cabecalho(p, "html Contexto simulador")
    gaveta(p, [G_ESTADO, G_COMP])
    # as escolhas do simulador são o conteúdo da página: ficam à vista, à esquerda
    p.add("escolhas_titulo", 24, Y0, 300, 20, textbox([{"textRuns": [run("SUAS ESCOLHAS", 9, AMARELO_ESCURO, True)]}]),
          tab=False)
    for k, e in enumerate(ENTRADAS):
        if e is None:
            continue
        nome, tab, col, rot, padrao, unico = e
        x, y = 24 + (k % 2) * 158, Y0 + 26 + (k // 2) * 68
        rotulo(p, nome, x, y, 142, rot)
        p.add(nome, x, y + 20, 142, 40, slicer(tab, col, unico=unico, padrao=padrao, cabecalho=False))
    p.add("notas", 24, 424, 300, 284, html_visual("html Simulador notas", CSS_TEXTO + CSS_ROLAGEM, padding=12,
                                                   alt="Preço dos carros, hipóteses e o que fica fora da conta"))
    p.add("resultado", 336, Y0, 920, 112, html_visual("html Simulador resultado", CSS_KPI, fundo=False, borda=False,
                                                       padding=0, alt="Resultado do simulador"))
    p.add("curva", 336, 248, 920, 460, deneb_visual(
        [proj_c("Ano de uso", "Ano de uso"), proj_m("Custo acumulado combustão"), proj_m("Custo acumulado elétrico"),
         proj_m("Rótulo combustão"), proj_m("Rótulo elétrico"), proj_m("Anos para pagar")],
        spec_acumulado(), "Custo acumulado: compra mais energia",
        "Linhas com o custo acumulado dos dois carros por ano de uso; a linha amarela marca o ano em que empatam",
        dica="dica_ano"))

    p = P["metodo"]
    cabecalho(p, None, gaveta=False)
    p.add("metodo", 24, 86, 820, 622, html_visual("html Método", CSS_TEXTO, padding=14,
                                                   alt="Texto com a pergunta, as fontes, as regras de cálculo e o que "
                                                       "ficou fora"))
    p.add("imputados", 856, 86, 400, 622, html_visual("html Imputados", CSS_TEXTO, padding=14,
                                                       alt="Tabela com os meses preenchidos por UF"))
    return [P[n] for n, _, _ in PAGINAS]


def paginas_dica() -> list[Pagina]:
    out = []
    for nome, titulo, medida_html, w, h in DICAS:
        p = Pagina(nome, titulo, titulo)
        p.largura, p.altura, p.tipo = w, h, "Tooltip"
        p.add("dica", 0, 0, w, h, html_visual(medida_html, CSS_DICA, fundo=True, borda=False, padding=0, escuro=True,
                                               alt=titulo))
        out.append(p)
    return out


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
    dicas = paginas_dica()
    jw(d / "pages" / "pages.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p.nome for p in paginas + dicas], "activePageName": paginas[0].nome})
    for p in paginas + dicas:
        pg = {"$schema": SCHEMA_PG, "name": p.nome, "displayName": p.aba,
              "displayOption": "ActualSize" if p.tipo else "FitToPage", "height": p.altura, "width": p.largura}
        if p.tipo:
            pg["type"] = p.tipo
        # a troca de página é pelas abas do próprio relatório: só a primeira página fica na lista do Power BI
        if p.tipo or p.nome != paginas[0].nome:
            pg["visibility"] = "HiddenInViewMode"
        if p.interacoes:
            pg["visualInteractions"] = p.interacoes
        jw(d / "pages" / p.nome / "page.json", pg)
        for v in p.visuais:
            jw(d / "pages" / p.nome / "visuals" / v["name"] / "visual.json", v)
    return paginas


# Gera o tour de documentação Dome (botão "Documentação" + passos com máscara, moldura e balão)
# em um relatório Power BI no formato PBIP/PBIR, editando os arquivos do relatório.
#
# Uso:
#   python3 gerar_tour_pbir.py <pasta X.Report/definition> <conteudo.json>
#
# conteudo.json: {"paginas": {"<nome interno da página>": {"sigla": "vg", "passos": [
#     {"alvo": [x, y, largura, altura], "lado": "direita|esquerda|baixo", "titulo": "...",
#      "mostra": "...", "ler": "...", "logica": "...", "medidas": "...", "atencao": "..."}, ...]}}}
# (exemplo real em exemplo_tour_cortes_nordeste.json)
#
# Antes de rodar: feche o Power BI Desktop, faça backup da pasta e confira que as páginas e as
# posições dos visuais batem com o relatório (leia pages/<pagina>/visuals/*/visual.json).
# Depois de rodar: reabra o .pbip, teste com Ctrl+clique e feche o tour (✕) antes de salvar.
#
# Rodar de novo é seguro: remove o que tem prefixo tour_ e regrava a pasta bookmarks/.
# ATENÇÃO: a pasta bookmarks/ é regravada inteira; se o relatório já tiver indicadores próprios,
# adapte o script para preservá-los.
import json, os, shutil, sys, math
# posição do botão: no cabeçalho, à direita, logo antes do botão de filtros (sem "?" no rótulo)
BTN_DOC = (1136, 12, 120, 32)

DEF = sys.argv[1]
W, H = 1280, 720
BAL_W = 340
INK, AMARELO, BRANCO, CINZA, CINZA2 = "#191919", "#F2C811", "#FFFFFF", "#C8C6C4", "#605E5C"
SCHEMA_VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.3.0/schema.json"
SCHEMA_BM = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/1.4.0/schema.json"
SCHEMA_BMS = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmarksMetadata/1.0.0/schema.json"

def lit(v): return {"expr": {"Literal": {"Value": v}}}
def s(v): return lit("'" + v.replace("'", "''") + "'")
def cor(c): return {"solid": {"color": s(c)}}

PAGINAS = json.load(open(sys.argv[2], encoding="utf-8"))["paginas"]

# ---------------- helpers de visual ----------------
def container_objs(bg=None, transp=0, borda=None, largura=0, padding=None):
    o = {"visualHeader": [{"properties": {"show": lit("false")}}],
         "title": [{"properties": {"show": lit("false")}}]}
    o["background"] = [{"properties": {"show": lit("true" if bg else "false"),
                                       **({"color": cor(bg), "transparency": lit(f"{transp}D")} if bg else {})}}]
    o["border"] = [{"properties": {"show": lit("true" if borda else "false"),
                                   **({"color": cor(borda), "width": lit(f"{largura}D"), "radius": lit("0D")} if borda else {})}}]
    if padding is not None:
        o["padding"] = [{"properties": {k: lit(f"{padding}D") for k in ("top", "bottom", "left", "right")}}]
    return o

def run(texto, tam, cor_, negrito=False):
    return {"value": texto, "textStyle": {"fontSize": f"{tam}pt", "fontWeight": "bold" if negrito else "normal", "color": cor_}}

def textbox(nome, x, y, w, h, z, paragrafos, pai=None, **co):
    v = {"$schema": SCHEMA_VC, "name": nome,
         "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
         "visual": {"visualType": "textbox",
                    "objects": {"general": [{"properties": {"paragraphs": paragrafos}}]},
                    "visualContainerObjects": container_objs(**co),
                    "drillFilterOtherVisuals": True}}
    if pai: v["parentGroupName"] = pai
    return v

def botao(nome, x, y, w, h, z, texto, destino, fundo=None, cor_texto=INK, pai=None, tam=10):
    """actionButton com texto, sem borda. Formato conferido num botão salvo pelo Desktop:
    'show' vai num item sem seletor; texto, cor e preenchimento vão no item com selector default."""
    v = {"$schema": SCHEMA_VC, "name": nome,
         "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
         "visual": {"visualType": "actionButton",
                    "objects": {
                        "icon": [{"properties": {"shapeType": s("blank")}, "selector": {"id": "default"}}],
                        "text": [{"properties": {"show": lit("true")}},
                                 {"properties": {"text": s(texto), "fontColor": cor(cor_texto), "fontSize": lit(f"{tam}D"),
                                                 "bold": lit("true")}, "selector": {"id": "default"}}],
                        "outline": [{"properties": {"show": lit("false")}}],
                        "fill": [{"properties": {"show": lit("true" if fundo else "false")}}]
                                + ([{"properties": {"fillColor": cor(fundo), "transparency": lit("0D")}, "selector": {"id": "default"}}] if fundo else [])},
                    "visualContainerObjects": {
                        **container_objs(padding=0),
                        "visualLink": [{"properties": {"show": lit("true"), "type": s("Bookmark"), "bookmark": s(destino)}}]},
                    "drillFilterOtherVisuals": True}}
    if pai: v["parentGroupName"] = pai
    return v

def linhas(texto, chars=48):
    return max(1, math.ceil(len(texto) / chars))

def paragrafos_balao(k, n, p):
    par = [{"textRuns": [run(f"PASSO {k} DE {n}", 8, CINZA, True)]},
           {"textRuns": [run(p["titulo"], 13, AMARELO, True)]}]
    altura = 18 + 26
    for rot, chave in (("O QUE MOSTRA", "mostra"), ("COMO LER", "ler"), ("LÓGICA", "logica"), ("MEDIDAS", "medidas"), ("ATENÇÃO", "atencao")):
        if not p.get(chave): continue
        par.append({"textRuns": [run(rot, 8, AMARELO, True)]})
        par.append({"textRuns": [run(p[chave], 10, BRANCO)]})
        altura += 16 + linhas(p[chave]) * 17 + 6
    return par, altura

def escrever(pasta_pagina, v):
    if isinstance(v, list):
        for item in v: escrever(pasta_pagina, item)
        return
    d = os.path.join(pasta_pagina, "visuals", v["name"]); os.makedirs(d, exist_ok=True)
    json.dump(v, open(os.path.join(d, "visual.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# ---------------- limpeza das amostras e de um tour anterior ----------------
for pg in PAGINAS:
    vis = os.path.join(DEF, "pages", pg, "visuals")
    for nome in os.listdir(vis):
        if nome.startswith("tour_"):
            shutil.rmtree(os.path.join(vis, nome))
bm_dir = os.path.join(DEF, "bookmarks")
if os.path.isdir(bm_dir):
    shutil.rmtree(bm_dir)
os.makedirs(bm_dir)

# ---------------- geração ----------------
grupos_bm = []
for pg, info in PAGINAS.items():
    sg, passos = info["sigla"], info["passos"]; n = len(passos)
    pasta = os.path.join(DEF, "pages", pg)
    grupos = [f"tour_{sg}_{k}" for k in range(1, n + 1)]
    off = f"tour_{sg}_off"

    # botão fixo "Documentação"
    escrever(pasta, botao(f"tour_{sg}_btn_doc", BTN_DOC[0], BTN_DOC[1], BTN_DOC[2], BTN_DOC[3], 20000, "Documentação", f"tour_{sg}_1", fundo=AMARELO))

    for k, p in enumerate(passos, 1):
        g = grupos[k - 1]; zb = 30000 + k * 20
        escrever(pasta, {"$schema": SCHEMA_VC, "name": g,
                         "position": {"x": 0, "y": 0, "z": zb, "height": H, "width": W, "tabOrder": zb},
                         "visualGroup": {"displayName": f"Tour {k} - {p['titulo']}"[:60], "groupMode": "ScaleMode",
                                         # sem fundo: um tema com fundo padrão cobriria a página inteira
                                         "objects": {"background": [{"properties": {"show": lit("false")}}]}},
                         "isHidden": True})
        x, y, w, h = p["alvo"]
        fx, fy, fw, fh = x - 4, y - 4, w + 8, h + 8
        espaco = " "
        mascara = dict(bg=INK, transp=40)
        # máscara em 4 retângulos ao redor da moldura
        for i, (mx, my, mw, mh) in enumerate([(0, 0, W, fy), (0, fy + fh, W, H - fy - fh), (0, fy, fx, fh), (fx + fw, fy, W - fx - fw, fh)]):
            if mw > 0 and mh > 0:
                escrever(pasta, textbox(f"{g}_mask{i}", mx, my, mw, mh, zb + 1, [{"textRuns": [run(espaco, 8, INK)]}], pai=g, **mascara))
        escrever(pasta, textbox(f"{g}_moldura", fx, fy, fw, fh, zb + 2, [{"textRuns": [run(espaco, 8, INK)]}], pai=g, borda=AMARELO, largura=3))

        par, alt = paragrafos_balao(k, n, p)
        bh = min(alt + 12 + 44, H - 16)
        if p["lado"] == "direita": bx, by = fx + fw + 12, fy
        elif p["lado"] == "esquerda": bx, by = fx - 12 - BAL_W, fy
        else: bx, by = min(fx + fw - BAL_W, W - BAL_W - 8), fy + fh + 12
        by = max(8, min(by, H - bh - 8))
        bx = max(8, min(bx, W - BAL_W - 8))  # alvo largo perto da borda: o balão não sai da página
        escrever(pasta, textbox(f"{g}_balao", bx, by, BAL_W, bh, zb + 3, par, pai=g, bg=INK, transp=0, borda="#3C3C41", largura=1, padding=14))
        yb = by + bh - 44
        if k > 1:
            escrever(pasta, botao(f"{g}_ant", bx + 14, yb, 96, 30, zb + 7, "◀ Anterior", grupos[k - 2], cor_texto=CINZA, pai=g))
        if k < n:
            escrever(pasta, botao(f"{g}_prox", bx + BAL_W - 14 - 110, yb, 110, 30, zb + 9, "Próximo ▶", grupos[k], fundo=AMARELO, pai=g))
        else:
            escrever(pasta, botao(f"{g}_fim", bx + BAL_W - 14 - 110, yb, 110, 30, zb + 9, "Concluir ✓", off, fundo=AMARELO, pai=g))
        escrever(pasta, botao(f"{g}_fechar", bx + BAL_W - 36, by + 6, 30, 28, zb + 11, "✕", off, cor_texto=CINZA, pai=g, tam=10))

    # indicadores: um por passo + desligado; só exibição (sem dados)
    nomes = []
    for k in range(0, n + 1):
        nome = off if k == 0 else grupos[k - 1]
        bm = {"$schema": SCHEMA_BM,
              "displayName": ("Tour – desligado" if k == 0 else f"Tour – passo {k}"),
              "name": nome,
              "options": {"targetVisualNames": [], "suppressData": True},
              "explorationState": {"version": "1.3", "activeSection": pg,
                                   "sections": {pg: {"visualContainers": {},
                                                     "visualContainerGroups": {gg: {"isHidden": gg != nome} for gg in grupos}}}}}
        json.dump(bm, open(os.path.join(bm_dir, f"{nome}.bookmark.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        nomes.append(nome)
    titulo_pg = json.load(open(os.path.join(pasta, "page.json"), encoding="utf-8"))["displayName"]
    grupos_bm.append({"name": f"tour_{sg}", "displayName": f"Tour – {titulo_pg}", "children": nomes})

json.dump({"$schema": SCHEMA_BMS, "items": grupos_bm}, open(os.path.join(bm_dir, "bookmarks.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("ok", sum(len(i["passos"]) for i in PAGINAS.values()), "passos")

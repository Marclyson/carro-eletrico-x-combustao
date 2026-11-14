#!/usr/bin/env python3
"""Layout de celular (retrato) para páginas PBIR: grava um mobile.json ao lado de cada visual escolhido.

Uso:
    python3 layout_celular_pbir.py <pasta definition do relatório> <config.json>

Canvas do celular (conferido num layout salvo pelo Desktop): 324 px de largura, altura livre (rola);
as coordenadas são da mesma ordem de grandeza do desktop (px). Visual sem mobile.json não aparece no
celular; página sem nenhum mobile.json mostra a versão paisagem girada.

config.json:
{
  "margem": 8, "espaco": 8,
  "cabecalho": {"titulo": 84, "resumo": "filtros_resumo", "botao": "filtros_botao"},   # opcional
  "gaveta": "filtros_gaveta",                                                         # opcional
  "paginas": {
    "<pagina>": [
      {"visual": "kpis", "altura": 320, "css": "<CSS acrescentado só no celular (HTML Content)>", "padding": 4},
      {"visual": "heatmap", "altura": 300, "spec": {"remover_texto": true}},
      {"visual": "dispersao", "altura": 320, "spec": {"manter_texto_cor": "#967100"}},
      [{"visual": "a", "altura": 120}, {"visual": "b", "altura": 120}]                 # lado a lado
    ]
  }
}
- "css": a folha de estilo do desktop + este trecho vira a folha do celular (override em objects.stylesheet).
  Para cartões em 2 colunas use CSS grid (grid-template-columns:1fr 1fr); flex-wrap com flex-basis 50%
  empilhou um cartão por linha no teste.
- "padding": padding do contêiner só no celular (visualContainerObjects.padding).
- "spec" (Deneb): "remover_texto" tira camadas de texto; "manter_texto_cor" mantém só os rótulos dessa cor
  (e o contorno branco deles); "padding_direita" troca o padding à direita (barras com rótulo ao lado).
  O override vai em objects.vega.jsonSpec do mobile.json.
- Todo HTML Content colocado no celular recebe html,body{overflow:hidden}: barra de rolagem interna nunca
  aparece. Isso não substitui a altura certa: confira no Layout móvel que nada importante foi cortado.
- Visuais do tour (prefixo tour_) não entram: as posições do tour são do canvas do desktop.
Idempotente: apaga os mobile.json das páginas configuradas antes de gravar.
"""
import json, sys
from pathlib import Path

LARG = 324
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainerMobileState/2.2.0/schema.json"


def lit_txt(t):
    return {"expr": {"Literal": {"Value": "'" + t.replace("'", "''") + "'"}}}


def ler_txt(v):
    return v["expr"]["Literal"]["Value"][1:-1].replace("''", "'")


def ajustar_spec(spec, regra):
    if "padding_direita" in regra:  # barras com rótulo à direita: no celular o padding do desktop esmaga as barras
        spec["padding"] = {**(spec.get("padding") or {}), "right": regra["padding_direita"]}
    def camadas(no):
        if "layer" not in no:
            return no
        manter_cor = regra.get("manter_texto_cor")
        mantidas_t = [json.dumps(c.get("transform")) for c in no["layer"]
                      if isinstance(c.get("mark"), dict) and c["mark"].get("type") == "text" and c["mark"].get("color") == manter_cor]
        nova = []
        for c in no["layer"]:
            m = c.get("mark")
            texto = (m == "text") or (isinstance(m, dict) and m.get("type") == "text")
            if texto and regra.get("remover_texto"):
                continue
            if texto and manter_cor and not (m.get("color") == manter_cor or json.dumps(c.get("transform")) in mantidas_t):
                continue
            nova.append(camadas(c))
        no["layer"] = nova
        return no
    return camadas(spec)


def main():
    d = Path(sys.argv[1])
    cfg = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    M, E = cfg.get("margem", 8), cfg.get("espaco", 8)
    W = LARG - 2 * M
    cab = cfg.get("cabecalho")
    total = 0
    for pg, itens in cfg["paginas"].items():
        vis = d / "pages" / pg / "visuals"
        for f in vis.glob("*/mobile.json"):
            f.unlink()
        pos, z = {}, 1000

        def por(nome, x, y, w, h, extra=None):
            nonlocal z, total
            pasta = vis / nome
            if not (pasta / "visual.json").exists():
                print(f"aviso: {pg}/{nome} não existe"); return
            m = {"$schema": SCHEMA, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}
            if extra:
                m.update(extra)
            (pasta / "mobile.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
            z += 1000; total += 1

        y = M
        if cab:
            por("titulo", M, y, W, cab.get("titulo", 84)); y += cab.get("titulo", 84) + 4
            bw = 104
            if cab.get("resumo"): por(cab["resumo"], M, y, W - bw - E, 36)
            if cab.get("botao"): por(cab["botao"], LARG - M - bw, y + 2, bw, 32)
            y += 36 + E
        for item in itens:
            linha = item if isinstance(item, list) else [item]
            larg = (W - E * (len(linha) - 1)) / len(linha)
            alt = max(i["altura"] for i in linha)
            for k, it in enumerate(linha):
                extra = None
                vj = json.loads((vis / it["visual"] / "visual.json").read_text(encoding="utf-8"))
                objs = vj.get("visual", {}).get("objects", {})
                if "stylesheet" in objs or it.get("css"):
                    # HTML Content: sem barra de rolagem interna no celular (altura certa + overflow escondido)
                    base = ler_txt(objs["stylesheet"][0]["properties"]["stylesheet"]) if "stylesheet" in objs else ""
                    css = base + "\n" + it.get("css", "") + "\nhtml,body{overflow:hidden!important;margin:0}::-webkit-scrollbar{display:none}*{scrollbar-width:none}.os-scrollbar{display:none!important}"
                    extra = {"objects": {"stylesheet": [{"properties": {"stylesheet": lit_txt(css)}}]}}
                if it.get("spec") and "vega" in objs:
                    spec = ajustar_spec(json.loads(ler_txt(objs["vega"][0]["properties"]["jsonSpec"])), it["spec"])
                    extra = {"objects": {"vega": [{"properties": {"jsonSpec": lit_txt(json.dumps(spec, ensure_ascii=False, indent=2))}}]}}
                if "padding" in it:  # padding do contêiner só no celular
                    pd = {k2: {"expr": {"Literal": {"Value": f"{it['padding']}D"}}} for k2 in ("top", "bottom", "left", "right")}
                    extra = {**(extra or {}), "visualContainerObjects": {"padding": [{"properties": pd}]}}
                por(it["visual"], round(M + k * (larg + E), 2), y, round(larg, 2), it["altura"], extra)
            y += alt + E
        altura_pagina = y
        g = cfg.get("gaveta")
        if g and (vis / g).exists():
            # gaveta em tela cheia no celular: véu cobre a página, painel no topo
            filhos = {p.name: json.loads((p / "visual.json").read_text(encoding="utf-8")) for p in vis.iterdir()
                      if (p / "visual.json").exists()}
            filhos = {n: v for n, v in filhos.items() if v.get("parentGroupName") == g}
            segs = sorted([n for n, v in filhos.items() if v.get("visual", {}).get("visualType") in ("slicer", "advancedSlicerVisual")],
                          key=lambda n: filhos[n]["position"]["y"])
            z = 90000
            px, pw = 16, LARG - 32
            yy = 80 + len(segs) * 80
            mapa = {"filtros_veu": (0, 0, LARG, max(altura_pagina, 720)), "filtros_painel": (0, 0, LARG, yy + 150),
                    "filtros_filete": (0, 0, LARG, 4), "filtros_titulo": (px, 20, pw - 44, 48), "filtros_fechar": (LARG - 48, 20, 32, 32),
                    "filtros_limpar": (px, yy, (pw - E) / 2, 34), "filtros_ok": (px + (pw + E) / 2, yy, (pw - E) / 2, 34),
                    "filtros_nota": (px, yy + 46, pw, 90)}
            for n in ["filtros_veu", "filtros_painel", "filtros_filete", "filtros_titulo", "filtros_fechar"]:
                if n in filhos: por(n, *mapa[n])
            for k, n in enumerate(segs):
                if (vis / f"filtros_rotulo_{n}").exists():  # rótulo próprio acima da segmentação sem cabeçalho
                    por(f"filtros_rotulo_{n}", px, 80 + k * 80, pw, 22)
                    por(n, px, 80 + k * 80 + 24, pw, 44)
                else:
                    por(n, px, 80 + k * 80, pw, 68)
            for n in ["filtros_limpar", "filtros_ok", "filtros_nota"]:
                if n in filhos: por(n, *mapa[n])
        print(f"{pg}: celular com {altura_pagina:.0f} px de altura")
    print(f"{total} mobile.json gravados")


if __name__ == "__main__":
    main()

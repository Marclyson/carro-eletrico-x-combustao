"""Gera o painel em PBIP (modelo TMDL + relatório PBIR) em powerbi/.

Uso (na raiz do repositório, com o Power BI Desktop fechado):
    python scripts/pbip/gerar_pbip.py

Regera tudo do zero: modelo, páginas, tour de documentação, filtro cruzado dos Deneb e layout de celular,
e roda o validador no fim. Alterações feitas à mão no Desktop se perdem; mude este script em vez disso.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import modelo
import relatorio

RAIZ = AQUI.parent.parent
NOME = "CarroEletricoCombustao"
PBI = RAIZ / "powerbi"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # filhos escrevem em UTF-8 mesmo com o console em cp1252


def desktop_aberto() -> bool:
    if sys.platform != "win32":
        return False
    saida = subprocess.run(["tasklist", "/FI", "IMAGENAME eq PBIDesktop.exe"], capture_output=True, text=True, check=False).stdout
    return "PBIDesktop.exe" in saida


def rodar(script: str, *args: str):
    r = subprocess.run([sys.executable, str(AQUI / script), *args], capture_output=True, text=True, encoding="utf-8",
                       check=False, env=ENV)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr)
        raise SystemExit(f"{script} falhou")


def gerar(pbi: Path) -> int:
    """Gera o projeto em pbi/ e devolve o código de saída do validador (0 = sem erros)."""
    pbi.mkdir(parents=True, exist_ok=True)
    tabelas = modelo.gravar(pbi / f"{NOME}.SemanticModel", relatorio.medidas_html())
    print(f"modelo: {len(tabelas)} tabelas")
    paginas = relatorio.gravar(pbi / f"{NOME}.Report", NOME, AQUI / "tema")
    print(f"relatório: {len(paginas)} páginas, {sum(len(p.visuais) for p in paginas)} visuais")
    (pbi / f"{NOME}.pbip").write_text(PBIP % NOME, encoding="utf-8", newline="\n")
    d = str(pbi / f"{NOME}.Report" / "definition")
    rodar("gerar_tour_pbir.py", d, str(AQUI / "tour.json"))
    indicadores_gaveta(Path(d), [p.nome for p in paginas])
    rodar("layout_celular_pbir.py", d, str(AQUI / "celular.json"))
    r = subprocess.run([sys.executable, str(AQUI / "validar_pbip.py"), str(pbi)], text=True, encoding="utf-8", check=False, env=ENV)
    return r.returncode


SCHEMA_BM = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/1.4.0/schema.json"


def indicadores_gaveta(d: Path, paginas: list[str]):
    """Indicadores filtros_<sigla>_abrir/fechar, só de exibição (suppressData: não mexem nos filtros escolhidos).
    Roda depois do tour, que recria a pasta bookmarks. Abrir a gaveta fecha o tour e vice-versa."""
    bm_dir = d / "bookmarks"
    meta = json.loads((bm_dir / "bookmarks.json").read_text(encoding="utf-8"))
    for pg in paginas:
        if not (d / "pages" / pg / "visuals" / relatorio.GAVETA).exists():
            continue
        sg = relatorio.SIGLA[pg]
        tour = next((i for i in meta["items"] if i["name"] == f"tour_{sg}"), {"children": []})["children"]
        grupos_tour = [n for n in tour if not n.endswith("_off")]
        for n in tour:  # passos do tour fecham a gaveta
            f = bm_dir / f"{n}.bookmark.json"
            bm = json.loads(f.read_text(encoding="utf-8"))
            bm["explorationState"]["sections"][pg]["visualContainerGroups"][relatorio.GAVETA] = {"isHidden": True}
            f.write_text(json.dumps(bm, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        filhos = []
        for acao, oculto in (("abrir", False), ("fechar", True)):
            nome = f"filtros_{sg}_{acao}"
            grupos = {relatorio.GAVETA: {"isHidden": oculto}, **{g: {"isHidden": True} for g in grupos_tour}}
            bm = {"$schema": SCHEMA_BM, "displayName": f"Filtros – {acao}", "name": nome,
                  "options": {"targetVisualNames": [], "suppressData": True},
                  "explorationState": {"version": "1.3", "activeSection": pg,
                                       "sections": {pg: {"visualContainers": {}, "visualContainerGroups": grupos}}}}
            (bm_dir / f"{nome}.bookmark.json").write_text(json.dumps(bm, ensure_ascii=False, indent=2),
                                                          encoding="utf-8", newline="\n")
            filhos.append(nome)
        meta["items"].append({"name": f"filtros_{sg}", "displayName": f"Filtros – {pg}", "children": filhos})
    (bm_dir / "bookmarks.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
                                           newline="\n")


PBIP = """{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
  "version": "1.0",
  "artifacts": [
    {
      "report": {
        "path": "%s.Report"
      }
    }
  ],
  "settings": {
    "enableAutoRecovery": true
  }
}
"""


def main():
    if desktop_aberto():
        raise SystemExit("Feche o Power BI Desktop antes de gerar: ele sobrescreve os arquivos ao salvar.")
    raise SystemExit(gerar(PBI))


if __name__ == "__main__":
    main()

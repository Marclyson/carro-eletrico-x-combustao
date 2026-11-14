"""O gerador do painel monta um PBIP que passa no validador estrutural."""

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts" / "pbip"))

import gerar_pbip


def test_gera_pbip_valido(tmp_path):
    assert gerar_pbip.gerar(tmp_path) == 0
    relatorio = tmp_path / f"{gerar_pbip.NOME}.Report" / "definition"
    paginas = json.loads((relatorio / "pages" / "pages.json").read_text(encoding="utf-8"))["pageOrder"]
    assert paginas == ["visao_geral", "impostos", "estados", "simulador", "metodo", "dica_mes", "dica_uf"]
    for pagina in paginas[:5]:  # botão Documentação em todas as páginas do relatório
        assert any((relatorio / "pages" / pagina / "visuals").glob("tour_*_btn_doc"))


def test_paginas_ocultas_dicas_e_gaveta(tmp_path):
    gerar_pbip.gerar(tmp_path)
    rel = tmp_path / f"{gerar_pbip.NOME}.Report" / "definition"
    pg = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in (rel / "pages").glob("*/page.json")}
    # só a primeira página aparece na lista do Power BI; a troca é pelas abas do relatório
    assert [n for n, p in pg.items() if p.get("visibility") != "HiddenInViewMode"] == ["visao_geral"]
    assert pg["dica_uf"]["type"] == pg["dica_mes"]["type"] == "Tooltip"
    for pagina, visual, dica in [("visao_geral", "linha_custo", "dica_mes"), ("estados", "mapa", "dica_uf"),
                                 ("estados", "dispersao", "dica_uf")]:
        v = json.loads((rel / "pages" / pagina / "visuals" / visual / "visual.json").read_text(encoding="utf-8"))
        assert v["visual"]["visualContainerObjects"]["visualTooltip"][0]["properties"]["section"]["expr"]["Literal"][
            "Value"] == f"'{dica}'"
    # gaveta: grupo oculto, segmentações dentro dele e indicadores que não mexem nos filtros
    for pagina, sg in [("visao_geral", "vg"), ("impostos", "im"), ("estados", "es"), ("simulador", "si")]:
        g = json.loads((rel / "pages" / pagina / "visuals" / "filtros_gaveta" / "visual.json").read_text(encoding="utf-8"))
        assert g["isHidden"] is True
        f = json.loads((rel / "pages" / pagina / "visuals" / "filtro_comparacao" / "visual.json").read_text(encoding="utf-8"))
        assert f["parentGroupName"] == "filtros_gaveta"
        bm = json.loads((rel / "bookmarks" / f"filtros_{sg}_abrir.bookmark.json").read_text(encoding="utf-8"))
        assert bm["options"]["suppressData"] is True
    assert not (rel / "pages" / "estados" / "visuals" / "filtro_estado").exists()  # na página Estados a UF é pelo mapa
    # realce cruzado entre os gráficos de Estados (não filtra: as medianas da dispersão ficam paradas)
    tipos = {(i["source"], i["target"]): i["type"] for i in pg["estados"]["visualInteractions"]}
    assert tipos[("mapa", "dispersao")] == "HighlightFilter" and tipos[("mapa", "destaques")] == "NoFilter"


def test_listas_de_selecao_unica_tem_valor_padrao(tmp_path):
    """Seleção única marca o 1º item da lista quando nada está escolhido; o padrão do DAX nunca valeria."""
    gerar_pbip.gerar(tmp_path)
    rel = tmp_path / f"{gerar_pbip.NOME}.Report" / "definition"
    padroes = {}
    for f in (rel / "pages").glob("*/visuals/*/visual.json"):
        v = json.loads(f.read_text(encoding="utf-8")).get("visual", {})
        if v.get("visualType") != "slicer":
            continue
        unico = "selection" in v["objects"]
        filtro = v["objects"]["general"][0]["properties"].get("filter")
        assert not unico or filtro, f"{f.parent.name} sem valor padrão"
        if filtro:
            padroes[f.parent.name] = filtro["filter"]["Where"][0]["Condition"]["In"]["Values"][0][0]["Literal"]["Value"]
    assert padroes["filtro_km"] == "12000L" and padroes["filtro_recarga"] == "80L"
    assert padroes["filtro_carregador"] == "2D" and padroes["filtro_anos"] == "10L"


def test_medidas_sem_duplicata_e_textos_balanceados(tmp_path):
    gerar_pbip.gerar(tmp_path)
    tmdl = (tmp_path / f"{gerar_pbip.NOME}.SemanticModel" / "definition" / "tables" / "_Medidas.tmdl").read_text(
        encoding="utf-8")
    nomes = [linha.split(" =")[0].strip() for linha in tmdl.splitlines() if linha.startswith("\tmeasure ")]
    assert len(nomes) == len(set(nomes))
    assert tmdl.count('"') % 2 == 0


def test_nomes_unicos_sem_diferenca_de_maiusculas(tmp_path):
    """O Analysis Services compara nomes sem ligar para maiúsculas: 'energia' e 'Energia' quebram a abertura."""

    gerar_pbip.gerar(tmp_path)
    tabelas = tmp_path / f"{gerar_pbip.NOME}.SemanticModel" / "definition" / "tables"
    medidas_modelo = []
    for arquivo in tabelas.glob("*.tmdl"):
        texto = arquivo.read_text(encoding="utf-8")
        nomes = [n.strip("'").lower() for n in re.findall(r"^\t(?:column|measure) ('[^']+'|[^\s=]+)", texto, re.MULTILINE)]
        assert len(nomes) == len(set(nomes)), arquivo.name
        medidas_modelo += [n.strip("'").lower() for n in re.findall(r"^\tmeasure ('[^']+'|[^\s=]+)", texto, re.MULTILINE)]
    assert len(medidas_modelo) == len(set(medidas_modelo))


def test_tipo_de_tabela_m_sem_palavra_type_nos_campos(tmp_path):
    """Em "type table [...]" o campo leva o tipo primitivo: "[#"A" = type text]" não abre no Desktop."""
    gerar_pbip.gerar(tmp_path)
    tabelas = tmp_path / f"{gerar_pbip.NOME}.SemanticModel" / "definition" / "tables"
    for arquivo in tabelas.glob("*.tmdl"):
        for linha_tipo in re.findall(r"type table \[([^\]]*)\]", arquivo.read_text(encoding="utf-8")):
            assert "= type " not in linha_tipo, arquivo.name

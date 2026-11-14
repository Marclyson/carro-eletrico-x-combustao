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
    assert paginas == ["visao_geral", "impostos", "estados", "simulador", "metodo"]
    for pagina in paginas:  # botão Documentação em todas as páginas
        assert any((relatorio / "pages" / pagina / "visuals").glob("tour_*_btn_doc"))


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

"""Baixa a malha das UFs do IBGE e grava uma versão simplificada para o mapa do painel (Deneb).

Uso (na raiz do repositório):
    python scripts/pbip/malha_uf.py

Grava referencias/malha_uf.geojson: 27 UFs, coordenadas com 2 casas, contorno simplificado (Douglas-Peucker),
ilhas pequenas removidas, anel externo no sentido horário (o d3-geo do Vega lê o anti-horário como "o resto do
globo") e o ponto do rótulo de cada UF (centroide do maior polígono).
Fonte: IBGE, API de malhas territoriais v3, qualidade mínima.
"""

import gzip
import json
import urllib.request
from itertools import pairwise
from pathlib import Path

URL = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?intrarregiao=UF"
       "&formato=application/vnd.geo+json&qualidade=minima")
SAIDA = Path(__file__).resolve().parents[2] / "referencias" / "malha_uf.geojson"
SIGLA = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA", "22": "PI",
         "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
         "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF"}
TOLERANCIA = 0.05  # graus; no mapa de ~440 px, 1 grau dá ~10 px
ILHA_MIN = 0.02     # graus²; ilhas menores somem (Fernando de Noronha, ilhas costeiras)


def area(anel):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in pairwise(anel)) / 2


def centroide(anel):
    a = area(anel)
    cx = sum((x0 + x1) * (x0 * y1 - x1 * y0) for (x0, y0), (x1, y1) in pairwise(anel)) / (6 * a)
    cy = sum((y0 + y1) * (x0 * y1 - x1 * y0) for (x0, y0), (x1, y1) in pairwise(anel)) / (6 * a)
    return round(cx, 2), round(cy, 2)


def dp(pts, tol):
    """Douglas-Peucker iterativo."""
    manter = [False] * len(pts)
    manter[0] = manter[-1] = True
    pilha = [(0, len(pts) - 1)]
    while pilha:
        i, j = pilha.pop()
        (x1, y1), (x2, y2) = pts[i], pts[j]
        dx, dy = x2 - x1, y2 - y1
        norma = (dx * dx + dy * dy) ** 0.5 or 1e-12
        k, dmax = None, tol
        for m in range(i + 1, j):
            d = abs(dy * pts[m][0] - dx * pts[m][1] + x2 * y1 - y2 * x1) / norma
            if d > dmax:
                k, dmax = m, d
        if k is not None:
            manter[k] = True
            pilha += [(i, k), (k, j)]
    return [p for p, f in zip(pts, manter) if f]


def simplificar(anel, externo):
    # divide o anel em duas metades para o DP não colapsar um anel fechado
    meio = len(anel) // 2
    s = dp(anel[:meio + 1], TOLERANCIA)[:-1] + dp(anel[meio:], TOLERANCIA)
    s = [[round(x, 2), round(y, 2)] for x, y in s]
    s = [p for k, p in enumerate(s) if k == 0 or p != s[k - 1]]
    if len(s) < 4:
        return None
    if (area(s) > 0) == externo:  # horário no externo (área negativa), anti-horário nos buracos
        s.reverse()
    return s


def main():
    with urllib.request.urlopen(URL, timeout=60) as r:
        corpo = r.read()
    bruto = json.loads(gzip.decompress(corpo) if corpo[:2] == bytes([0x1F, 0x8B]) else corpo)
    feats = []
    for f in bruto["features"]:
        g = f["geometry"]
        polis = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        maior = max(polis, key=lambda p: abs(area(p[0])))
        novos = []
        for p in polis:
            if p is not maior and abs(area(p[0])) < ILHA_MIN:
                continue
            aneis = [simplificar(a, k == 0) for k, a in enumerate(p)]
            if aneis[0]:
                novos.append([a for a in aneis if a])
        lon, lat = centroide(maior[0])
        geom = {"type": "Polygon", "coordinates": novos[0]} if len(novos) == 1 else \
            {"type": "MultiPolygon", "coordinates": novos}
        feats.append({"type": "Feature", "properties": {"uf": SIGLA[f["properties"]["codarea"]], "lon": lon, "lat": lat},
                      "geometry": geom})
    feats.sort(key=lambda f: f["properties"]["uf"])
    texto = json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":"))
    SAIDA.write_text(texto, encoding="utf-8")
    pontos = texto.count("],[") + len(feats)
    print(f"{SAIDA.name}: {len(feats)} UFs, ~{pontos} pontos, {len(texto) / 1024:.0f} KB")


if __name__ == "__main__":
    main()

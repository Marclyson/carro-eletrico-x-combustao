"""Extrai os dados do PBE Veicular 2026 do Inmetro para a camada bronze."""

import re
import sys

from pypdf import PdfReader

PROPULSOES = frozenset({"Combustão", "Elétrico", "Híbrido"})

CHAVES = (
    "co2_fossil_etanol",
    "co2_total_gasolina",
    "co2_fossil_gasolina",
    "co2e_fossil",
    "etanol_cidade",
    "etanol_estrada",
    "etanol_combinado",
    "gasolina_cidade",
    "gasolina_estrada",
    "gasolina_combinado",
    "kmle_gasolina_cidade",
    "kmle_gasolina_estrada",
    "kmle_etanol_cidade",
    "kmle_etanol_estrada",
    "mj_km",
    "autonomia_km",
    "classe_categoria",
    "classe_geral",
    "ence",
)

INTEIRO = re.compile(r"[+-]?\d+")
DECIMAL = re.compile(r"[+-]?\d+,\d+")


def valor(token):
    """Converte um token da tabela para int, float ou None."""
    if token is None:
        return None
    token = token.strip()
    if token in ("", "-", "ND"):
        return None
    if DECIMAL.fullmatch(token):
        return float(token.replace(",", "."))
    if INTEIRO.fullmatch(token):
        return int(token)
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


def _fora_do_intervalo(valores, minimo, maximo):
    """Verifica se algum valor numérico está fora do intervalo."""
    return any(valor is not None and not minimo <= valor <= maximo for valor in valores)


def registro(linha):
    """Converte uma linha da tabela PBE em dicionário."""
    tokens = linha.split()
    posicao = next((i for i, token in enumerate(tokens) if token in PROPULSOES), None)
    if posicao is None:
        descricao = " ".join(tokens)
        propulsao = None
    else:
        descricao = " ".join(tokens[:posicao])
        propulsao = tokens[posicao]

    # Linha curta (quebra de página, nota de rodapé) não tem as 19 colunas: tudo vira None e a linha sai irregular.
    bruto = dict(zip(CHAVES, tokens[-19:])) if len(tokens) >= 19 else {}
    resultado = {
        "descricao": descricao,
        "propulsao": propulsao,
    }
    for chave in CHAVES[0:16]:
        resultado[chave] = valor(bruto.get(chave))
    for chave in CHAVES[16:19]:
        texto = (bruto.get(chave) or "").strip()
        resultado[chave] = texto or None

    co2 = [resultado[chave] for chave in CHAVES[0:4]]
    km_l = [resultado[chave] for chave in CHAVES[4:10]]
    km_le = [resultado[chave] for chave in CHAVES[10:14]]

    irregular = (
        resultado["mj_km"] is None
        or resultado["classe_categoria"] not in ("A", "B", "C", "D", "E")
        or resultado["classe_geral"] not in ("A", "B", "C", "D", "E")
        or _fora_do_intervalo(co2, 0, 500)
        or _fora_do_intervalo(km_l + km_le, 3, 80)
    )
    resultado["irregular"] = irregular
    return resultado


def linhas_do_pdf(caminho):
    """Le o PDF e devolve apenas as linhas de veículos."""
    leitor = PdfReader(str(caminho))
    linhas = []
    for pagina in leitor.pages:
        for linha in (pagina.extract_text() or "").splitlines():
            if PROPULSOES.intersection(linha.split()):
                linhas.append(linha)
    return linhas


def main():
    """Imprime o resumo das linhas extraídas do PDF."""
    if len(sys.argv) < 2:
        print("uso: python -m custo_km.extrair_pbe caminho/do/pdf.pdf")
        return 0

    linhas = linhas_do_pdf(sys.argv[1])
    registros = [registro(linha) for linha in linhas]
    irregulares = [registro for registro in registros if registro["irregular"]]

    print(f"linhas: {len(registros)}")
    print(f"irregulares: {len(irregulares)}")
    for item in irregulares:
        print(item["descricao"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
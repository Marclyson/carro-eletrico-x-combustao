import csv
from pathlib import Path

from custo_km.extrair_pbe import registro, valor

L1 = r"Utilitário Esportivo Compacto RENAULT KWID  ZEN 2 1.0-12V Combustão M-5 S E-H F 49 362 2 B 0 107 88 \ 10,4 10,7 10,5 14,4 15,4 14,9 \ \ \ \ 1,41 \ A B SIM"
L2 = r"Sub Compacto BYD DOLPHIN MINI  GL 5 EV Elétrico Elétrico A-1 S E E ND ND ND A \ - \ \ \ \ \ \ \ \ 60,6 44,4 \ \ 0,39 224 A A -"
L3 = r"Sub Compacto RENAULT E-KWID INTENS Elétrico Elétrico A S E E ND ND ND A \ - \ \ \ \ \ \ \ \ 52,7 39,6 \ \ 0,44 185 B A -"
L4 = r"Médio VW POLO TRACK 1.0 MPI 1.0-12V Combustão M - 5 S E F 33 119 2 B 0 111 92 \ \ \ \ \ \ \ \ 1,48 \ B B -"
L5 = r"Sub Compacto FIAT MOBI LIKE 1.0-6V Combustão M-5 S E F 37 348 4 B 0 106 87 \ 10,1 11,1 10,5 14,5 15,8 15,0 \ \ \ \ 1,40 \ E B -"

CSV = Path(__file__).resolve().parents[1] / "referencias" / "veiculos.csv"


def test_l1_gasolina_e_etanol():
    item = registro(L1)
    assert item["gasolina_combinado"] == 14.9
    assert item["etanol_cidade"] == 10.4
    assert item["co2_fossil_gasolina"] == 88
    assert item["co2_fossil_etanol"] == 0
    assert item["mj_km"] == 1.41
    assert item["ence"] == "SIM"
    assert item["propulsao"] == "Combustão"
    assert item["descricao"] == "Utilitário Esportivo Compacto RENAULT KWID ZEN 2 1.0-12V"
    assert item["irregular"] is False


def test_l2_dolphin_mini():
    item = registro(L2)
    assert item["kmle_gasolina_cidade"] == 60.6
    assert item["kmle_gasolina_estrada"] == 44.4
    assert item["mj_km"] == 0.39
    assert item["autonomia_km"] == 224
    assert item["propulsao"] == "Elétrico"
    assert item["irregular"] is False
    for chave in ("etanol_cidade", "etanol_estrada", "etanol_combinado",
                  "gasolina_cidade", "gasolina_estrada", "gasolina_combinado"):
        assert item[chave] is None
    for chave in ("co2_fossil_etanol", "co2_total_gasolina", "co2_fossil_gasolina", "co2e_fossil"):
        assert item[chave] is None


def test_l3_e_kwid():
    item = registro(L3)
    assert item["mj_km"] == 0.44
    assert item["autonomia_km"] == 185
    assert item["irregular"] is False


def test_l4_polo_track_irregular():
    assert registro(L4)["irregular"] is True


def test_l5_mobi():
    item = registro(L5)
    assert item["gasolina_cidade"] == 14.5
    assert item["co2_fossil_gasolina"] == 87
    assert item["irregular"] is False


def test_valor():
    assert valor("\\") is None
    assert valor("ND") is None
    assert valor("9,8") == 9.8


def test_csv_contra_registros():
    with open(CSV, encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))

    registros = {
        "kwid": registro(L1),
        "e_kwid": registro(L3),
        "dolphin_mini": registro(L2),
    }
    campos = ("km_l_cidade", "km_l_estrada", "km_l_combinado", "mj_km", "autonomia_km", "co2_fossil_g_km")

    for linha in linhas:
        if linha["ano_pbe"] != "2026":
            continue
        item = registros[linha["veiculo"]]
        if linha["veiculo"] == "kwid":
            prefixo = linha["energia"]
            chave_co2 = f"co2_fossil_{linha['energia']}"
        else:
            prefixo = None
            chave_co2 = "co2_fossil_etanol"

        for campo in campos:
            if campo == "co2_fossil_g_km":
                esperado = item[chave_co2]
                if prefixo is None and esperado is None:
                    esperado = 0
            elif campo.startswith("km_l_"):
                if prefixo is None:
                    esperado = None
                else:
                    sufixo = campo.removeprefix("km_l_")
                    esperado = item[f"{prefixo}_{sufixo}"]
            else:
                esperado = item[campo]
            obtido = float(linha[campo]) if linha[campo] else None
            assert obtido == esperado, (linha["veiculo"], linha["energia"], campo)

        if linha["energia"] == "eletricidade":
            assert float(linha["kwh_km"]) == round(item["mj_km"] / 3.6, 4)


def test_csv_polo_track_2025():
    with open(CSV, encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    polos = [linha for linha in linhas if linha["veiculo"] == "polo_track"]
    assert polos
    for linha in polos:
        assert linha["ano_pbe"] == "2025"
        assert linha["observacao"]
import importlib

MODULOS = [
    "extrair_anp",
    "extrair_aneel",
    "extrair_sgs",
    "extrair_mcti",
    "extrair_pbe",
    "transformar",
    "exportar",
]


def test_importa_os_sete_modulos():
    for nome in MODULOS:
        modulo = importlib.import_module(f"custo_km.{nome}")
        assert callable(modulo.main)

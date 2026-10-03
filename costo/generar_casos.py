"""
Genera costo/casos_prueba.json: los casos con los que se prueban las DOS
implementaciones del calculo (costo/calculo.py y sitio/js/costo.js).

Cada caso: componentes de una version, un perfil de uso y el resultado que da
Python. test_calculo.py verifica que el archivo siga coincidiendo con Python
(si cambia una formula, hay que regenerarlo a proposito); test_costo.mjs
verifica que JavaScript de lo mismo. Asi las dos copias no pueden divergir.

Casos: los armados a mano de test_calculo.py y 30 versiones reales
(datos/autos.duckdb) con perfiles distintos. Se versiona: no depende de que
la base exista para correr el test de JavaScript.

Uso: python -m costo.generar_casos
"""

import json
import os
import random

import duckdb

from costo.calculo import Perfil, calcular

RUTA = os.path.join("costo", "casos_prueba.json")
CAMPOS = ("valor_0km", "combustible_por_km", "service_por_km", "repuestos_por_km", "repuestos_por_km_original",
          "patente_anual", "proporcion_conservada_1", "proporcion_conservada_5", "proporcion_conservada_10")

A_MANO = {
    "valor_0km": 30_000_000, "combustible_por_km": 150, "service_por_km": 40, "repuestos_por_km": 10,
    "repuestos_por_km_original": 25, "patente_anual": 600_000,
    "proporcion_conservada_1": 0.8, "proporcion_conservada_5": 0.5, "proporcion_conservada_10": 0.3,
}

PERFILES = [
    {},
    {"km_anio": 20000, "anios": 3, "seguro_mensual": 60000},
    {"km_anio": 8000, "anios": 10},
    {"km_anio": 30000, "anios": 0.5, "repuestos_originales": True},
    {"km_anio": 12000, "anios": 15, "seguro_mensual": 45000, "repuestos_originales": True},
]


def resultado(c, perfil):
    k = calcular(c, Perfil(**perfil))
    return {"anual": k.anual, "combustible_anual": k.combustible_anual, "service_anual": k.service_anual,
            "repuestos_anual": k.repuestos_anual, "patente_anual": k.patente_anual,
            "depreciacion_anual": k.depreciacion_anual, "seguro_anual": k.seguro_anual,
            "faltantes": k.faltantes}


def casos():
    lista = []
    for perfil in PERFILES:
        lista.append({"nombre": "a mano", "componentes": A_MANO, "perfil": perfil})
    lista.append({"nombre": "a mano sin service", "componentes": {**A_MANO, "service_por_km": None}, "perfil": {}})
    lista.append({"nombre": "a mano sin curva", "componentes": {**A_MANO, "proporcion_conservada_1": None,
                  "proporcion_conservada_5": None, "proporcion_conservada_10": None}, "perfil": {}})
    lista.append({"nombre": "a mano solo curva a 5", "componentes": {**A_MANO, "proporcion_conservada_1": None,
                  "proporcion_conservada_10": None}, "perfil": {"anios": 8}})
    base = os.path.join("datos", "autos.duckdb")
    if os.path.exists(base):
        con = duckdb.connect(base, read_only=True)
        cur = con.execute(f"""select modelo, provincia_id, {', '.join(CAMPOS)} from mart_costo_componentes
                              using sample 30 rows (reservoir, 7)""")
        rng = random.Random(7)
        for fila in cur.fetchall():
            c = dict(zip(CAMPOS, fila[2:]))
            lista.append({"nombre": f"{fila[0]} ({fila[1]})", "componentes": c, "perfil": rng.choice(PERFILES)})
    for caso in lista:
        caso["esperado"] = resultado(caso["componentes"], caso["perfil"])
    return lista


def main():
    with open(RUTA, "w", encoding="utf-8") as f:
        json.dump(casos(), f, ensure_ascii=False, indent=1)
    print(f"{RUTA}: {len(casos())} casos")


if __name__ == "__main__":
    main()

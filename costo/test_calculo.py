"""
Tests del calculo de costo total.

1. Casos armados a mano (numeros redondos, la cuenta se puede seguir).
2. Interpolacion de la curva de depreciacion.
3. Coherencia con dbt: con el perfil por defecto (15.000 km, 5 anios), el
   calculo en Python tiene que dar lo mismo que mart_costo_total para las
   versiones completas. Si alguien cambia una formula de un lado y no del
   otro, falla. Local se saltea si no existe datos/autos.duckdb; en GitHub
   Actions (CI=true) la base tiene que existir: si dbt no corrio, falla.

Uso: python -m costo.test_calculo
"""

import os

from costo.calculo import Perfil, calcular, proporcion_conservada

AUTO = {
    "valor_0km": 30_000_000,
    "combustible_por_km": 150,      # 7,5 l/100 km a $2.000
    "service_por_km": 40,
    "repuestos_por_km": 10,
    "repuestos_por_km_original": 25,
    "patente_anual": 600_000,
    "proporcion_conservada_1": 0.8,
    "proporcion_conservada_5": 0.5,
    "proporcion_conservada_10": 0.3,
}

errores = []


def igual(nombre, obtenido, esperado, tolerancia=0.5):
    if abs(obtenido - esperado) > tolerancia:
        errores.append(f"{nombre}: {obtenido} en vez de {esperado}")


# 1. Perfil por defecto: 15.000 km, 5 anios.
k = calcular(AUTO, Perfil())
igual("combustible", k.combustible_anual, 2_250_000)
igual("service", k.service_anual, 600_000)
igual("repuestos", k.repuestos_anual, 150_000)
igual("depreciacion", k.depreciacion_anual, 30_000_000 * 0.5 / 5)   # 3.000.000
igual("anual", k.anual, 2_250_000 + 600_000 + 150_000 + 600_000 + 3_000_000)
igual("mensual", k.mensual(), 6_600_000 / 12)
igual("por km", k.por_km(15000), 440)

# Seguro y repuestos originales.
k = calcular(AUTO, Perfil(seguro_mensual=50_000, repuestos_originales=True))
igual("seguro", k.seguro_anual, 600_000)
igual("repuestos originales", k.repuestos_anual, 375_000)

# Manejar el doble: combustible, service y repuestos se duplican; patente y depreciacion no.
k1, k2 = calcular(AUTO, Perfil(km_anio=10_000)), calcular(AUTO, Perfil(km_anio=20_000))
igual("km doble", k2.anual - k1.anual, 10_000 * (150 + 40 + 10))

# Componente faltante: no se inventa, queda listado.
k = calcular({**AUTO, "service_por_km": None}, Perfil())
if k.completo or k.faltantes != ["service"]:
    errores.append(f"faltante service: {k.faltantes}")

# Perfil invalido.
for malo in ({"km_anio": 0}, {"anios": -1}, {"seguro_mensual": -5}):
    try:
        Perfil(**malo)
        errores.append(f"perfil invalido aceptado: {malo}")
    except ValueError:
        pass

# 2. Curva: puntos exactos, interpolacion, antes del primero y despues del ultimo.
igual("curva 5", proporcion_conservada(AUTO, 5), 0.5, 1e-9)
igual("curva 3", proporcion_conservada(AUTO, 3), 0.8 + (0.5 - 0.8) * 2 / 4, 1e-9)    # 0,65
igual("curva 7,5", proporcion_conservada(AUTO, 7.5), 0.5 + (0.3 - 0.5) * 2.5 / 5, 1e-9)
igual("curva 0,5", proporcion_conservada(AUTO, 0.5), 0.9, 1e-9)                      # medio camino a 0,8
igual("curva 15", proporcion_conservada(AUTO, 15), 0.3, 1e-9)
if proporcion_conservada({}, 5) is not None:
    errores.append("curva vacia deberia ser None")

# 3. Coherencia con mart_costo_total.
casos_dbt = 0
if os.environ.get("CI") == "true" and not os.path.exists(os.path.join("datos", "autos.duckdb")):
    errores.append("no existe datos/autos.duckdb: dbt no corrio")
if os.path.exists(os.path.join("datos", "autos.duckdb")):
    import duckdb
    con = duckdb.connect(os.path.join("datos", "autos.duckdb"), read_only=True)
    cur = con.execute("""
        select c.*, t.costo_anual as mart_costo_anual
        from mart_costo_componentes c
        join mart_costo_total t using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo, provincia_id)
        where t.completo and t.km_anio = 15000 and t.anios_tenencia = 5
        using sample 200 rows (reservoir, 1)""")
    columnas = [d[0] for d in cur.description]
    for fila in cur.fetchall():
        c = dict(zip(columnas, fila))
        casos_dbt += 1
        # El mart redondea cada componente al peso: tolerancia de unos pesos.
        igual(f"dbt {c['modelo']} {c['provincia_id']}", calcular(c, Perfil()).anual, c["mart_costo_anual"], 5)

# 4. El archivo de casos compartido con JavaScript sigue coincidiendo con Python.
import json
from costo.generar_casos import RUTA, resultado
casos_js = json.load(open(RUTA, encoding="utf-8")) if os.path.exists(RUTA) else []
if not casos_js:
    errores.append(f"falta {RUTA}: correr python -m costo.generar_casos")
for caso in casos_js:
    actual = resultado(caso["componentes"], caso["perfil"])
    for campo, esperado in caso["esperado"].items():
        if campo == "faltantes":
            if actual[campo] != esperado:
                errores.append(f"casos_prueba {caso['nombre']} faltantes: {actual[campo]} en vez de {esperado}")
        elif abs(actual[campo] - esperado) > 1e-6 * max(1, abs(esperado)):
            errores.append(f"casos_prueba {caso['nombre']} {campo}: cambio la formula, regenerar con python -m costo.generar_casos")

if errores:
    print(f"{len(errores)} casos fallaron")
    for e in errores[:20]:
        print("MAL", e)
    raise SystemExit(1)
print(f"OK: casos a mano, {casos_dbt} versiones contra mart_costo_total y {len(casos_js)} casos compartidos con JavaScript")

"""Casos de los nombres de archivo en los releases.

Un error aca mezclaria archivos entre meses o entre fuentes sin que nada falle:
el Parquet de agosto terminaria pisando al de julio. Por eso se prueba ida y vuelta.

Uso: python -m ingesta.test_releases
"""

import os

from ingesta.releases import GENERAL, nombre_asset, release_de, ruta_de_asset

CASOS = [
    # ruta relativa a datos/raw          asset esperado                                release
    ("dnrpa/inscripciones/202608.parquet", "dnrpa__inscripciones__202608.parquet", "datos-2026"),
    ("dnrpa/transferencias/201801.parquet", "dnrpa__transferencias__201801.parquet", "datos-2018"),
    ("combustible/precios_1104/202412.parquet", "combustible__precios_1104__202412.parquet", "datos-2024"),
    ("combustible/estaciones.parquet", "combustible__estaciones.parquet", GENERAL),
    ("dnrpa/_estado.json", "dnrpa___estado.json", GENERAL),
    # La valuacion se nombra por vigencia (AAAAMMDD), no por mes: va a general.
    ("valuacion/20261001.parquet", "valuacion__20261001.parquet", GENERAL),
    ("cca/202610.parquet", "cca__202610.parquet", "datos-2026"),
    ("cca/_estado.json", "cca___estado.json", GENERAL),
    ("consumo/ensayos_20220609.parquet", "consumo__ensayos_20220609.parquet", GENERAL),
    # Service: fotos por fecha de captura (AAAAMMDD), pocas por anio: van a general.
    ("service/fiat/20261001.parquet", "service__fiat__20261001.parquet", GENERAL),
    ("service/_estado.json", "service___estado.json", GENERAL),
]


def main():
    for ruta, asset, release in CASOS:
        assert nombre_asset(ruta) == asset, (ruta, nombre_asset(ruta))
        assert nombre_asset(ruta.replace("/", "\\")) == asset, "las rutas de Windows tienen que dar lo mismo"
        assert ruta_de_asset(asset) == os.path.join("datos", "raw", *ruta.split("/")), (asset, ruta_de_asset(asset))
        assert release_de(asset) == release, (asset, release_de(asset))
    print(f"OK: {len(CASOS)} casos")


if __name__ == "__main__":
    main()

"""
Casos de la normalizacion y del cruce por prefijo (ingesta/texto.py).

Cada caso es un error real que aparecio midiendo el matching en la Fase 0. El de
"GOL 1.6" es el mas caro: una regla para "HB 20" -> "HB20" lo convertia en
"GOL1,6" y el Gol entero dejaba de cruzar.

Uso: python -m ingesta.test_texto
"""

from ingesta.texto import candidatos_por_prefijo, clave_marca, modelo_por_prefijo, norm

NORM = {
    "GOL 1.6": "GOL 1,6",                     # la cilindrada no se pega al nombre
    "GOL GLI 1.8": "GOL GLI 1,8",
    "HB 20 AT": "HB20 AT",                    # pero un codigo corto si
    "S10 CD 2.8": "S10 CD 2,8",
    "F-100": "F100",
    "KA +": "KA PLUS",                        # "KA +" es otro auto que "KA"
    "TERRITORY TREND 1.5L HIBRIDA AT": "TERRITORY TREND 1,5 HIBRIDA AT",
    "TIGGO 7 PRO": "TIGGO 7 PRO",
    "Peugeot 208 Allure": "PEUGEOT 208 ALLURE",
    "FURGÓN": "",                             # tilde fuera y palabra de carroceria descartada
    "RAV - 4": "RAV4",                        # guion suelto entre espacios
    "RAV4 HEV 2.5": "RAV4 HEV 2,5",
}

PREFIJO = [
    # descripcion DNRPA, marca, modelos candidatos, esperado
    ("TERRITORY TREND 1.5L HIBRIDA AT", "FORD", ["TERRITORY", "RANGER PICK - UP"], "TERRITORY"),
    ("YARIS CROSS XEI HEV 1.5 ECVT", "TOYOTA", ["YARIS", "YARIS CROSS"], "YARIS CROSS"),  # el mas largo gana
    ("BJ30E", "BAIC", ["BJ30", "BJ40"], "BJ30"),                    # prefijo con digitos
    ("KANGOO 1.6", "RENAULT", ["KA", "KANGOO"], "KANGOO"),
    ("KA FLY VIRAL 1.0L", "FORD", ["KA +"], None),                   # el Ka viejo no es el Ka+
    ("VOLKSWAGEN VENTO 2.5", "VOLKSWAGEN", ["VENTO"], "VENTO"),      # la descripcion repite la marca
    ("HB 20 AT", "HYUNDAI", ["HB20 SEDAN", "HB20"], "HB20"),
    ("GOL 1.6", "VOLKSWAGEN", ["GOL", "GOL TREND", "GOLF"], "GOL"),
]


def main():
    fallas = 0
    for entrada, esperado in NORM.items():
        if norm(entrada) != esperado:
            fallas += 1
            print(f"MAL norm({entrada!r}) = {norm(entrada)!r}, esperado {esperado!r}")
    for desc, marca, modelos, esperado in PREFIJO:
        obtenido = modelo_por_prefijo(desc, marca, modelos)
        if obtenido != esperado:
            fallas += 1
            print(f"MAL prefijo({desc!r}) = {obtenido!r}, esperado {esperado!r}")
    # Empate: los dos candidatos quedan registrados, y siempre gana el mismo.
    empate = candidatos_por_prefijo("HB 20 AT", "HYUNDAI", {"HB20 SEDAN", "HB20"})
    if empate != ["HB20", "HB20 SEDAN"]:
        fallas += 1
        print(f"MAL empate HB20: {empate}")
    if clave_marca("MERCEDES-BENZ") != clave_marca("Mercedes Benz"):
        fallas += 1
        print("MAL clave_marca de Mercedes")
    if fallas:
        raise SystemExit(f"{fallas} casos fallaron")
    print(f"OK: {len(NORM) + len(PREFIJO) + 2} casos")


if __name__ == "__main__":
    main()

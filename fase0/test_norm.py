"""
Casos de la normalizacion de nombres de modelo (medir_matching.norm).

Cada caso es un error real que aparecio midiendo el matching. El de "GOL 1.6"
es el mas importante: una regla para "HB 20" -> "HB20" lo convertia en
"GOL1,6" y el Gol entero dejaba de cruzar.

Uso: python fase0/test_norm.py   (desde la raiz, con .venv)
"""

import importlib.util
import os
import sys

_ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "medir_matching.py")
_spec = importlib.util.spec_from_file_location("medir_matching", _ruta)
mm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mm)

CASOS = {
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
}


def main():
    fallas = 0
    for entrada, esperado in CASOS.items():
        obtenido = mm.norm(entrada)
        ok = obtenido == esperado
        fallas += not ok
        print(f"{'OK ' if ok else 'MAL'} {entrada!r} -> {obtenido!r}" + ("" if ok else f" (esperado {esperado!r})"))
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()

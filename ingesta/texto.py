"""
Normalizacion de nombres de modelo y cruce por prefijo.

Es la logica que se midio en la Fase 0 (fase0/medir_matching.py, ver
fase0/05_matching.md): sobre los 50 modelos mas patentados cruza el 100% con la
guia CCA a nivel modelo, y el 89% de todas las unidades 0 km.

Cada regla de `norm` existe por un caso real; estan en test_texto.py.
"""

import re
import unicodedata

# Palabras que una fuente pone y la otra no, y que no distinguen modelos.
# "UP" no va suelto: es el modelo VW Up!. "PICK UP" se borra como frase en `norm`.
RUIDO = {"SEDAN", "PUERTAS", "PUERTA", "PTAS", "RURAL", "FURGON", "FURGONETA", "PICK",
         "PICKUP", "CABINA", "TODO", "TERRENO", "COUPE", "HATCHBACK", "NUEVO", "NUEVA"}


def norm(texto):
    """Mayusculas, sin tildes, 1.5L -> 1,5, F-100 -> F100, HB 20 -> HB20, + -> PLUS."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    t = re.sub(r"\bPICK\s*-?\s*UP\b", " ", t)  # "PICK - UP", "PICK-UP", "PICK UP"
    t = t.replace("+", " PLUS ")  # "KA +" es otro auto que "KA": no borrar el +
    # Guion suelto entre espacios ("RAV - 4", "PICK - UP"): se borra antes de
    # pegar letras y numeros, si no "RAV - 4" queda "RAV 4" y no cruza con "RAV4".
    t = re.sub(r"\s+-\s+", " ", t)
    t = re.sub(r"(\d)[.,](\d)\s*L\b", r"\1,\2", t)            # 1.5L / 1,5 L -> 1,5
    t = re.sub(r"(\d)\.(\d)", r"\1,\2", t)                     # 1.5 -> 1,5
    t = re.sub(r"(?<=[A-Z])-(?=\d)|(?<=\d)-(?=[A-Z])", "", t)  # F-100 -> F100
    # HB 20 -> HB20, S 10 -> S10. Pero no "GOL 1,6" -> "GOL1,6": si al numero le
    # sigue una coma es una cilindrada, no parte del nombre.
    t = re.sub(r"\b([A-Z]{1,3}) (\d{1,3})\b(?!,)", r"\1\2", t)
    t = re.sub(r"[^A-Z0-9, /]", " ", t)
    return " ".join(w for w in t.split() if w not in RUIDO)


def clave_marca(marca):
    """'MERCEDES-BENZ', 'Mercedes Benz' -> 'MERCEDESBENZ'."""
    return norm(marca).replace(" ", "")


def sin_marca(descripcion, marca):
    """'VOLKSWAGEN VENTO 2.5' -> 'VENTO 2,5': algunas descripciones repiten la marca."""
    d, m = norm(descripcion).split(), norm(marca).split()
    return " ".join(d[len(m):]) if m and d[:len(m)] == m else " ".join(d)


def candidatos_por_prefijo(descripcion, marca, modelos):
    """Todos los modelos empatados en el prefijo mas largo que encaja.

    Una palabra con digitos acepta prefijo ("BJ30" con "BJ30E"); una sin
    digitos tiene que ser igual, si no "KA" cruzaria con "KANGOO".
    Mas de un candidato = cruce ambiguo: "HB 20 AT" encaja igual con "HB20" y
    con "HB20 SEDAN" (SEDAN se descarta al normalizar). Devuelve [] si nada encaja.
    """
    palabras = sin_marca(descripcion, marca).split()
    por_largo = {}
    for m in modelos or ():
        mp = sin_marca(m, marca).split()
        if not mp or len(mp) > len(palabras):
            continue
        if all(a == b or (re.search(r"\d", b) and a.startswith(b)) for a, b in zip(palabras, mp)):
            por_largo.setdefault(len(mp), []).append(m)
    return sorted(por_largo[max(por_largo)], key=lambda m: (len(m), m)) if por_largo else []


def modelo_por_prefijo(descripcion, marca, modelos):
    """El mejor candidato: entre empatados, el nombre mas corto (el mas generico).

    El desempate tiene que ser deterministico: antes ganaba el primero que
    aparecia al recorrer un set, y el resultado podia cambiar entre corridas.
    """
    candidatos = candidatos_por_prefijo(descripcion, marca, modelos)
    return candidatos[0] if candidatos else None

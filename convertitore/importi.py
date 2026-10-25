"""Lettura degli importi scritti nei formati dei diversi provider.

Esempi di quello che arriva dai file del kit:
    "151,00"     Provider A, B, D  (virgola decimale, formato italiano)
    "€15.88"     Provider E        (punto decimale, formato inglese, con simbolo €)
    312.1        Provider C        (numero vero, letto da Excel)

Ogni provider dichiara nella sua configurazione il formato che usa:
    "it"   -> 1.234,56   (punto per le migliaia, virgola per i decimali)
    "en"   -> 1,234.56   (virgola per le migliaia, punto per i decimali)
    "auto" -> il formato si deduce dal testo; se il testo è ambiguo
              (es. "1.234": mille duecentotrentaquattro o uno virgola due?)
              il valore NON viene indovinato e la riga finisce negli scarti.
"""

import re
from decimal import Decimal, InvalidOperation


class ImportoNonLeggibile(ValueError):
    """L'importo non si può leggere con certezza: la riga andrà negli scarti."""


# Simboli e parole che possono accompagnare un importo e vanno tolti.
_VALUTA = re.compile(r"€|EUR|EURO", re.IGNORECASE)

# Forme ammesse per ciascun formato, dopo aver tolto valuta, spazi e segno.
_SCHEMI = {
    # 1234  |  1234,56  |  1.234  |  1.234,56
    "it": re.compile(r"^(\d+|\d{1,3}(\.\d{3})+)(,\d+)?$"),
    # 1234  |  1234.56  |  1,234  |  1,234.56
    "en": re.compile(r"^(\d+|\d{1,3}(,\d{3})+)(\.\d+)?$"),
}


def leggi_importo(valore, formato: str = "auto") -> Decimal:
    """Restituisce l'importo come Decimal (può essere negativo).

    Solleva ImportoNonLeggibile se il valore è vuoto, non è un numero
    o è ambiguo.
    """
    # 1) Numeri veri (es. celle Excel numeriche): niente da interpretare.
    if isinstance(valore, bool):
        raise ImportoNonLeggibile(f"Valore non valido: {valore}")
    if isinstance(valore, Decimal):
        return valore
    if isinstance(valore, int):
        return Decimal(valore)
    if isinstance(valore, float):
        if valore != valore:  # NaN: cella vuota letta da pandas
            raise ImportoNonLeggibile("Importo vuoto")
        # str() dà la forma più corta che rappresenta il numero (312.1 e non
        # 312.100000000000005...), così non portiamo dentro errori del float.
        return Decimal(str(valore))

    # 2) Testo: pulizia.
    testo = "" if valore is None else str(valore)
    testo = _VALUTA.sub("", testo)
    testo = testo.replace(" ", " ").replace(" ", " ").strip()
    if testo in ("", "-"):
        raise ImportoNonLeggibile("Importo vuoto")

    # 3) Segno: "-12,00", "12,00-" oppure "(12,00)".
    negativo = False
    if testo.startswith("(") and testo.endswith(")"):
        negativo, testo = True, testo[1:-1].strip()
    if testo.startswith("-"):
        negativo, testo = True, testo[1:].strip()
    elif testo.endswith("-"):
        negativo, testo = True, testo[:-1].strip()
    if testo.startswith("+"):
        testo = testo[1:].strip()

    # Spazi usati come separatore delle migliaia ("1 234,56").
    if re.fullmatch(r"\d{1,3}( \d{3})+([.,]\d+)?", testo):
        testo = testo.replace(" ", "")

    # 4) Scelta del formato.
    if formato == "auto":
        formato = _deduci_formato(testo)
    if formato not in _SCHEMI:
        raise ValueError(f"Formato importo sconosciuto: {formato}")

    # 5) Il testo deve rispettare esattamente la forma del formato.
    if not _SCHEMI[formato].match(testo):
        raise ImportoNonLeggibile(f"'{valore}' non è un importo valido nel formato '{formato}'")

    migliaia, decimali = (".", ",") if formato == "it" else (",", ".")
    normalizzato = testo.replace(migliaia, "").replace(decimali, ".")
    try:
        importo = Decimal(normalizzato)
    except InvalidOperation:
        raise ImportoNonLeggibile(f"'{valore}' non è un importo valido")
    return -importo if negativo else importo


def _deduci_formato(testo: str) -> str:
    """Deduce il formato dal testo, solo quando non ci sono dubbi."""
    ha_punto, ha_virgola = "." in testo, "," in testo
    if ha_punto and ha_virgola:
        # Il separatore che compare per ultimo è quello dei decimali.
        return "it" if testo.rfind(",") > testo.rfind(".") else "en"
    if not ha_punto and not ha_virgola:
        return "it"  # numero intero: i due formati coincidono
    separatore = "." if ha_punto else ","
    if testo.count(separatore) > 1:
        # "1.234.567" o "1,234,567": può essere solo il separatore delle migliaia.
        return "it" if separatore == "." else "en"
    cifre_dopo = len(testo) - testo.rfind(separatore) - 1
    if cifre_dopo == 3:
        raise ImportoNonLeggibile(
            f"'{testo}' è ambiguo (migliaia o decimali?): indicare il formato "
            "nella configurazione del provider"
        )
    # Una sola virgola o un solo punto, con 1, 2 o più di 3 cifre dopo: decimali.
    return "it" if separatore == "," else "en"

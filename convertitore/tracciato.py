"""Tracciato di destinazione: il record a lunghezza fissa del gestionale paghe.

Ogni record è lungo 38 caratteri ed è composto da sei campi, sempre nello
stesso ordine:

    Campo              Posizione  Lunghezza  Tipo
    Codice ditta            1         6       N
    Codice dipendente       7         6       A
    Codice voce            13         4       A
    Quantità               17         7       N   (sempre zeri)
    Importo                24         9       N   (centesimi, senza virgola)
    Periodo                33         6       AAAAMM

N = numerico: allineato a destra e riempito con zeri.
A = alfanumerico: allineato a sinistra e riempito con spazi.
"""

from decimal import Decimal, ROUND_HALF_UP

LUNGHEZZA_RECORD = 38


def campo_numerico(valore: int, lunghezza: int) -> str:
    """Scrive un numero intero allineato a destra, con zeri davanti.

    Esempio: campo_numerico(4012, 6) -> "004012"
    """
    if valore < 0:
        raise ValueError(f"Il campo numerico non può essere negativo: {valore}")
    testo = str(valore)
    if len(testo) > lunghezza:
        raise ValueError(f"Il valore {valore} non entra in {lunghezza} caratteri")
    return testo.zfill(lunghezza)


def campo_alfanumerico(valore: str, lunghezza: int) -> str:
    """Scrive un testo allineato a sinistra, con spazi dopo.

    Esempio: campo_alfanumerico("4", 6) -> "4     "
    """
    testo = str(valore).strip()
    if not testo.isascii():
        raise ValueError(f"Il valore '{testo}' contiene caratteri non ASCII")
    if len(testo) > lunghezza:
        raise ValueError(f"Il valore '{testo}' non entra in {lunghezza} caratteri")
    return testo.ljust(lunghezza)


def importo_in_centesimi(importo: Decimal) -> int:
    """Trasforma un importo in euro in centesimi interi.

    L'arrotondamento è "mezzo centesimo per eccesso" (22,445 -> 2245),
    il modo in cui si arrotonda di solito in contabilità.
    Si usa Decimal e non float perché i float non rappresentano esattamente
    i decimali (0,1 + 0,2 in float fa 0,30000000000000004).
    """
    return int((importo * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def controlla_periodo(periodo: str) -> str:
    """Verifica che il periodo sia nel formato AAAAMM con un mese valido."""
    periodo = str(periodo).strip()
    if len(periodo) != 6 or not periodo.isdigit():
        raise ValueError(f"Il periodo '{periodo}' deve essere nel formato AAAAMM")
    mese = int(periodo[4:])
    if not 1 <= mese <= 12:
        raise ValueError(f"Il mese del periodo '{periodo}' non è valido")
    return periodo


def crea_record(ditta, dipendente, voce, importo: Decimal, periodo) -> str:
    """Compone un record da 38 caratteri.

    Esempio:
        crea_record("4012", "4", "371", Decimal("22.44"), "202609")
        -> "0040124     371 0000000000002244202609"
    """
    record = (
        campo_numerico(int(ditta), 6)
        + campo_alfanumerico(dipendente, 6)
        + campo_alfanumerico(voce, 4)
        + campo_numerico(0, 7)
        + campo_numerico(importo_in_centesimi(importo), 9)
        + controlla_periodo(periodo)
    )
    # Controllo di sicurezza: se un campo fosse sbagliato, ce ne accorgiamo qui.
    assert len(record) == LUNGHEZZA_RECORD, f"Record di {len(record)} caratteri"
    return record

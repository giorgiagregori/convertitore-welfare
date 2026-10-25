"""Scelta del periodo del cedolino (anno e mese) nell'interfaccia.

Perché non solo "dal mese corrente in avanti":
il report del provider arriva a mese chiuso (quello di settembre arriva a
ottobre) e va nel cedolino di quel mese, come nel kit (report di settembre 2026
-> VOCI_4012_202609). Servono anche i mesi passati per rifare una conversione
(file corretto dal provider, ricalcoli). Quindi:
    - anni proposti: l'anno precedente, quello corrente e il successivo
    - mese proposto: il mese precedente a oggi (il caso normale)
    - avviso, senza blocco, se il periodo è lontano dal caso normale.
"""

from datetime import date

MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio",
        "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


def mese_precedente(oggi: date) -> tuple:
    return (oggi.year - 1, 12) if oggi.month == 1 else (oggi.year, oggi.month - 1)


def anni_disponibili(oggi: date) -> list:
    return [oggi.year - 1, oggi.year, oggi.year + 1]


def periodo(anno: int, mese: int) -> str:
    """(2026, 9) -> '202609', il formato AAAAMM del tracciato."""
    return f"{anno:04d}{mese:02d}"


def avviso_periodo(anno: int, mese: int, oggi: date):
    """Un avviso se il periodo non è il mese precedente né quello corrente."""
    distanza = (oggi.year - anno) * 12 + (oggi.month - mese)   # mesi fa (negativo = futuro)
    if distanza < 0:
        return (f"{MESI[mese - 1]} {anno} è un mese futuro: di solito il report arriva "
                "a mese chiuso. Controlla che sia il periodo giusto.")
    if distanza > 1:
        return (f"{MESI[mese - 1]} {anno} è di {distanza} mesi fa: va bene per rifare una "
                "conversione, altrimenti controlla il periodo.")
    return None

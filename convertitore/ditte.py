"""Proposta della ditta a partire dai dipendenti del file.

Non serve un elenco "quali ditte segue ogni provider" da tenere aggiornato:
l'app guarda i dipendenti presenti nel file, controlla in anagrafica a quale
ditta appartengono e propone quella dove ne riconosce di più.
Così, se un provider inizia a seguire una ditta nuova, la proposta funziona
subito; l'unico elenco da mantenere resta l'anagrafica, che arriva dal gestionale.

La ditta viene proposta solo se:
    - riconosce più della metà dei dipendenti del file, e
    - nessun'altra ditta ne riconosce lo stesso numero.
Altrimenti non si propone nulla e si spiega perché: la scelta resta all'operatore.
"""

from dataclasses import dataclass, field
from typing import Optional

from .anagrafica import Anagrafica


@dataclass
class Proposta:
    ditta: Optional[str]                 # None se non c'è una ditta convincente
    riconosciuti: int = 0                # dipendenti del file trovati nella ditta proposta
    dipendenti: int = 0                  # dipendenti diversi presenti nel file
    per_ditta: dict = field(default_factory=dict)   # {ditta: dipendenti riconosciuti}
    motivo: str = ""                     # perché non c'è una proposta


def proponi_ditta(movimenti, anagrafica: Anagrafica) -> Proposta:
    # Un dipendente può comparire su più righe: lo si conta una volta sola.
    dipendenti = {}
    for m in movimenti:
        dipendenti.setdefault(m.chiave_dipendente(), m)
    totale = len(dipendenti)
    if not totale:
        return Proposta(None, motivo="Nel file non ci sono dipendenti da riconoscere.")

    per_ditta = {}
    for ditta in anagrafica.ditte():
        trovati = sum(1 for m in dipendenti.values()
                      if anagrafica.riconosci(ditta, m.codice_fiscale, m.codice, m.nome).trovato)
        if trovati:
            per_ditta[ditta] = trovati
    per_ditta = dict(sorted(per_ditta.items(), key=lambda c: -c[1]))

    if not per_ditta:
        return Proposta(None, 0, totale, per_ditta,
                        "Nessun dipendente del file è presente in anagrafica.")
    classifica = list(per_ditta.items())
    migliore, trovati = classifica[0]
    if len(classifica) > 1 and classifica[1][1] == trovati:
        pari = ", ".join(d for d, n in classifica if n == trovati)
        return Proposta(None, trovati, totale, per_ditta,
                        f"Più ditte riconoscono lo stesso numero di dipendenti ({pari}).")
    if trovati * 2 <= totale:
        return Proposta(None, trovati, totale, per_ditta,
                        f"La ditta con più riscontri ({migliore}) riconosce solo "
                        f"{trovati} dipendenti su {totale}.")
    return Proposta(migliore, trovati, totale, per_ditta)

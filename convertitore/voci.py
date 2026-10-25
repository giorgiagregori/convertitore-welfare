"""Dalla descrizione del trattamento fiscale (scritta come la scrive il provider)
al codice voce del gestionale paghe.

La tabella Codici_Welfare_Voci_Payroll.csv ha tre colonne:
    Trattamento     come lo scrive il provider ("Benefit art.51 c.3", "X71180"...)
    Codice          la voce payroll (370, 371, 373...)
    Sottocategoria  facoltativa: distingue casi con lo stesso trattamento
                    (es. f-bis "Centri estivi" -> 375, "Istruzione" -> 373)

Regola della specifica, in quest'ordine:
    a) trattamento + sottocategoria identici in tabella
    b) trattamento identico, riga della tabella senza sottocategoria
    c) stesso articolo, comma e lettera (ignorando il testo tra parentesi),
       solo se porta a un'unica voce -> esportata, ma segnalata come AVVISO
    altrimenti: anomalia (scarto), con le voci possibili se ce ne sono.

"Identici" vuol dire uguali a meno di maiuscole e spazi ripetuti: non si
tolgono punti o virgole, perché nella tabella "Art.51 c. 3" e "Art. 51 c.3"
sono righe diverse.
"""

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class EsitoVoce:
    codice: Optional[str] = None
    metodo: Optional[str] = None
    avviso: Optional[str] = None      # abbinamento per somiglianza: va segnalato
    motivo: Optional[str] = None      # anomalia: va negli scarti
    cosa_fare: Optional[str] = None

    @property
    def trovata(self) -> bool:
        return self.codice is not None


def normalizza_testo(testo) -> str:
    """Maiuscole/minuscole e spazi ripetuti non contano."""
    return re.sub(r"\s+", " ", str(testo or "")).strip().lower()


def chiave_normativa(trattamento) -> tuple:
    """Estrae (articolo, comma, lettera) dalla descrizione del trattamento.

    Esempi:
        "Benefit art.51 c.2 let d-bis"     -> ("51", "2", "d-bis")
        "Art. 51 c.2 lett. d-bis"          -> ("51", "2", "d-bis")
        "Art.51 c. 2, d bis"               -> ("51", "2", "d-bis")
        "TUIR - Art.51 c.2f (ex Art.100)"  -> ("51", "2", "f")
        "Art.51 c.3 [FCI Art.2]"           -> ("51", "3", None)
        "Art 100 [Iva 22%]"                -> ("100", None, None)
        "X71180"                           -> (None, None, None)
    """
    testo = normalizza_testo(trattamento)
    # Il testo tra parentesi è un commento (es. "[FCI Art.2]", "(ex Art.100)"):
    # contiene altri articoli che confonderebbero la lettura.
    testo = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", testo)

    articolo = re.search(r"\bart\.?\s*(\d+)", testo)
    if not articolo:
        return (None, None, None)
    resto = testo[articolo.end():]

    comma = re.search(r"\b(?:c|co|comma)\s*\.?\s*(\d+)", resto)
    if not comma:
        return (articolo.group(1), None, None)
    resto = resto[comma.end():]

    lettera = re.match(
        r"\s*(?:,|lett?\b\.?)?\s*([a-z])(?:\s*[-\s]\s*(bis|ter|quater)|(bis|ter|quater))?\b",
        resto,
    )
    if not lettera:
        return (articolo.group(1), comma.group(1), None)
    suffisso = lettera.group(2) or lettera.group(3)
    lett = lettera.group(1) + (f"-{suffisso}" if suffisso else "")
    return (articolo.group(1), comma.group(1), lett)


def descrivi_chiave(chiave: tuple) -> str:
    articolo, comma, lettera = chiave
    parti = [f"art. {articolo}"]
    if comma:
        parti.append(f"c.{comma}")
    if lettera:
        parti.append(f"lett. {lettera}")
    return " ".join(parti)


class TabellaVoci:
    """La tabella trattamento -> voce, pronta per le ricerche."""

    def __init__(self, percorso_csv):
        self.righe = []        # (trattamento originale, codice, sottocategoria originale)
        self._esatte = {}      # (trattamento norm., sottocategoria norm.) -> set di codici
        with open(Path(percorso_csv), encoding="utf-8-sig", newline="") as f:
            for riga in csv.DictReader(f):
                trattamento = str(riga["Trattamento"]).strip()
                codice = str(riga["Codice"]).strip()
                sotto = str(riga.get("Sottocategoria") or "").strip()
                self.righe.append((trattamento, codice, sotto))
                chiave = (normalizza_testo(trattamento), normalizza_testo(sotto))
                self._esatte.setdefault(chiave, set()).add(codice)

    def incoerenze(self) -> list:
        """Righe della tabella con lo stesso trattamento e sottocategoria ma voci diverse."""
        return [(t, s, sorted(c)) for (t, s), c in self._esatte.items() if len(c) > 1]

    def trova(self, trattamento, sottocategoria=None) -> EsitoVoce:
        if not str(trattamento or "").strip():
            return EsitoVoce(motivo="Trattamento fiscale mancante",
                             cosa_fare="Verificare la riga nel file del provider")

        t = normalizza_testo(trattamento)
        s = normalizza_testo(sottocategoria)
        etichetta = f"'{str(trattamento).strip()}'" + (f" ({str(sottocategoria).strip()})" if s else "")

        # a) trattamento + sottocategoria identici
        if s and (t, s) in self._esatte:
            return self._unica(self._esatte[(t, s)], "esatto con sottocategoria", etichetta)
        # b) trattamento identico, riga senza sottocategoria
        if (t, "") in self._esatte:
            return self._unica(self._esatte[(t, "")], "esatto", etichetta)

        # c) stesso articolo, comma e lettera
        chiave = chiave_normativa(trattamento)
        if chiave[0] is None:
            return EsitoVoce(
                motivo=f"Trattamento {etichetta} non presente in tabella",
                cosa_fare="Aggiungere il trattamento alla tabella delle voci oppure scegliere la voce a mano",
            )
        simili = [r for r in self.righe if chiave_normativa(r[0]) == chiave]
        # Prima le righe con la stessa sottocategoria, poi quelle generiche.
        stessa_sotto = [r for r in simili if s and normalizza_testo(r[2]) == s]
        generiche = [r for r in simili if not r[2]]
        candidati = stessa_sotto or generiche
        codici = sorted({r[1] for r in candidati})

        if len(codici) == 1:
            nomi = sorted({f"'{r[0]}'" for r in candidati})
            esempi = ", ".join(nomi[:2]) + (f" e altre {len(nomi) - 2}" if len(nomi) > 2 else "")
            return EsitoVoce(
                codice=codici[0],
                metodo="per somiglianza",
                avviso=(f"Trattamento {etichetta} abbinato per somiglianza "
                        f"({descrivi_chiave(chiave)}) a {esempi}"),
            )
        if len(codici) > 1:
            return EsitoVoce(
                motivo=(f"Trattamento {etichetta} ambiguo ({descrivi_chiave(chiave)}): "
                        f"voci possibili {', '.join(codici)}"),
                cosa_fare=("Scegliere la voce a mano; per i mesi successivi aggiungere "
                           "la riga in tabella con la sottocategoria"),
            )
        return EsitoVoce(
            motivo=f"Trattamento {etichetta} non presente in tabella ({descrivi_chiave(chiave)})",
            cosa_fare="Aggiungere il trattamento alla tabella delle voci oppure scegliere la voce a mano",
        )

    @staticmethod
    def _unica(codici: set, metodo: str, etichetta: str) -> EsitoVoce:
        if len(codici) == 1:
            return EsitoVoce(codice=next(iter(codici)), metodo=metodo)
        return EsitoVoce(
            motivo=f"Tabella incoerente: {etichetta} ha più voci ({', '.join(sorted(codici))})",
            cosa_fare="Correggere la tabella delle voci",
        )

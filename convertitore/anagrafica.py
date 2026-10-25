"""Riconoscimento del dipendente: dal modo in cui lo chiama il provider al
codice che ha nel gestionale paghe.

I provider indicano il dipendente in modi diversi:
    A  codice fiscale
    B  solo cognome e nome
    C  codice fiscale + matricola (il codice gestionale con zeri davanti)
    D  nome e cognome (il codice fiscale c'è solo se il beneficiario è il dipendente)
    E  codice dipendente + codice fiscale

Regole (dalla specifica):
- il dipendente si cerca SEMPRE solo nella ditta scelta;
- l'anagrafica si usa senza righe duplicate;
- i nomi si confrontano senza maiuscole, accenti e ordine delle parole, ma
  con corrispondenza esatta (Matteo Martini non è Martini Sala Nicola);
- se il provider dà codice e codice fiscale, devono indicare la stessa persona;
- quando non si trova, non si indovina: si restituisce il motivo e cosa fare.
"""

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from collections import Counter
from typing import Optional


@dataclass(frozen=True)
class Dipendente:
    ditta: str
    codice: str
    nome: str
    codice_fiscale: str


@dataclass
class Esito:
    """Risultato della ricerca di un dipendente.

    Se `codice` è valorizzato il dipendente è stato trovato e `metodo` dice come;
    altrimenti `motivo` e `cosa_fare` finiranno nel file scarti.
    """
    codice: Optional[str] = None
    metodo: Optional[str] = None
    motivo: Optional[str] = None
    cosa_fare: Optional[str] = None

    @property
    def trovato(self) -> bool:
        return self.codice is not None


# ---------------------------------------------------------------- normalizzazioni

def normalizza_ditta(ditta) -> str:
    """'004012' e '4012' sono la stessa ditta."""
    testo = str(ditta).strip()
    return str(int(testo)) if testo.isdigit() else testo.upper()


def normalizza_codice(codice) -> str:
    """'00000020' (matricola del Provider C) e '20' sono lo stesso codice."""
    testo = str(codice).strip()
    if testo.endswith(".0") and testo[:-2].isdigit():  # 15000.0 letto da Excel
        testo = testo[:-2]
    return str(int(testo)) if testo.isdigit() else testo.upper()


def normalizza_cf(cf) -> str:
    return re.sub(r"\s+", "", str(cf)).upper()


def chiave_nome(*parti) -> tuple:
    """Trasforma un nome in una chiave confrontabile.

    Maiuscole, senza accenti, senza punteggiatura, parole in ordine alfabetico:
        ("DELLA ROSA", "FABIO")  -> ("DELLA", "FABIO", "ROSA")
        "Fabio Della Rosa"       -> ("DELLA", "FABIO", "ROSA")
    """
    testo = " ".join(str(p) for p in parti if p is not None)
    testo = unicodedata.normalize("NFKD", testo)
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    testo = re.sub(r"[^A-Za-z]+", " ", testo).upper()
    return tuple(sorted(testo.split()))


def _vuoto(valore) -> bool:
    return valore is None or str(valore).strip() in ("", "-", "nan", "None")


# ---------------------------------------------------------------- anagrafica

class Anagrafica:
    """L'anagrafica dei dipendenti (Lista_Dipendenti.csv), già ripulita."""

    def __init__(self, percorso_csv):
        self.dipendenti: list[Dipendente] = []
        self.duplicati_rimossi = 0
        nomi_ditta: dict[str, Counter] = {}
        visti = set()
        with open(Path(percorso_csv), encoding="utf-8-sig", newline="") as f:
            for riga in csv.DictReader(f):
                dip = Dipendente(
                    ditta=normalizza_ditta(riga["Codice Ditta"]),
                    codice=str(riga["CodAnagraficoLav"]).strip(),
                    nome=str(riga["Nome Dipendente"]).strip(),
                    codice_fiscale=normalizza_cf(riga["CodiceFiscale"]),
                )
                nomi_ditta.setdefault(dip.ditta, Counter())[str(riga.get("RagioneSociale", "")).strip()] += 1
                if dip in visti:
                    self.duplicati_rimossi += 1
                    continue
                visti.add(dip)
                self.dipendenti.append(dip)
        # Ragione sociale di ogni ditta: la scrittura più frequente
        # (nel kit la 4175 compare sia come "Tiglio Lab S.r.l." sia come "S.R.L.").
        self.ragioni_sociali = {ditta: nomi.most_common(1)[0][0] for ditta, nomi in nomi_ditta.items()}

    def della_ditta(self, ditta) -> list[Dipendente]:
        ditta = normalizza_ditta(ditta)
        return [d for d in self.dipendenti if d.ditta == ditta]

    def ditte(self) -> list[str]:
        return sorted(self.ragioni_sociali, key=lambda d: (len(d), d))

    def esiste_ditta(self, ditta) -> bool:
        return bool(self.della_ditta(ditta))

    # ------------------------------------------------------------ ricerca

    def riconosci(self, ditta, codice_fiscale=None, codice=None, nome=None) -> Esito:
        """Cerca il dipendente nella ditta usando le informazioni disponibili.

        `nome` può essere una stringa ("Fabio Della Rosa") o una tupla
        (cognome, nome): l'ordine delle parole non conta.
        """
        ditta = normalizza_ditta(ditta)
        persone = self.della_ditta(ditta)
        if not persone:
            return Esito(
                motivo=f"Ditta {ditta} non presente in anagrafica",
                cosa_fare="Verificare il codice ditta inserito",
            )

        cf = None if _vuoto(codice_fiscale) else normalizza_cf(codice_fiscale)
        cod = None if _vuoto(codice) else normalizza_codice(codice)
        chiave = None
        if nome is not None:
            parti = nome if isinstance(nome, (tuple, list)) else (nome,)
            chiave = chiave_nome(*[p for p in parti if not _vuoto(p)]) or None

        per_cf = [p for p in persone if cf and p.codice_fiscale == cf]
        per_codice = [p for p in persone if cod and normalizza_codice(p.codice) == cod]

        # 1) Codice fiscale: è l'identificativo più affidabile.
        if cf:
            if per_cf:
                trovato = per_cf[0]
                if cod and normalizza_codice(trovato.codice) != cod:
                    return self._incoerente(codice, cf)
                metodo = "codice fiscale" + (" e codice" if cod else "")
                return Esito(codice=trovato.codice, metodo=metodo)
            if per_codice:
                # Il codice esiste nella ditta ma appartiene a un altro CF.
                return self._incoerente(codice, cf)
            return self._non_presente(ditta, cf=cf, chiave=chiave)

        # 2) Solo codice dipendente.
        if cod:
            if per_codice:
                return Esito(codice=per_codice[0].codice, metodo="codice")
            return self._non_presente(ditta, chiave=chiave)

        # 3) Solo nome e cognome.
        if chiave:
            per_nome = [p for p in persone if chiave_nome(p.nome) == chiave]
            if len(per_nome) == 1:
                return Esito(codice=per_nome[0].codice, metodo="nome e cognome")
            if len(per_nome) > 1:
                codici = ", ".join(p.codice for p in per_nome)
                return Esito(
                    motivo=f"Più dipendenti con lo stesso nome nella ditta {ditta} (codici {codici})",
                    cosa_fare="Inserire a mano il codice corretto",
                )
            return self._non_presente(ditta, chiave=chiave)

        return Esito(
            motivo="Nessun dato per riconoscere il dipendente (né codice fiscale, né codice, né nome)",
            cosa_fare="Verificare la riga nel file del provider",
        )

    # ------------------------------------------------------------ messaggi

    def _incoerente(self, codice, cf) -> Esito:
        return Esito(
            motivo=f"Codice dipendente {codice} e codice fiscale {cf} indicano persone diverse",
            cosa_fare="Verificare con il provider quale dei due dati è corretto",
        )

    def _non_presente(self, ditta, cf=None, chiave=None) -> Esito:
        cosa_fare = "Aggiungere il dipendente in anagrafica oppure inserire il codice a mano"
        # Se la stessa persona esiste in un'altra ditta, lo diciamo: può essere
        # stata scelta la ditta sbagliata.
        altrove = [
            d for d in self.dipendenti
            if d.ditta != ditta and ((cf and d.codice_fiscale == cf)
                                     or (not cf and chiave and chiave_nome(d.nome) == chiave))
        ]
        if altrove:
            dove = "; ".join(f"ditta {d.ditta} codice {d.codice}" for d in altrove)
            cosa_fare += f". Attenzione: presente in altra ditta ({dove})"
        return Esito(
            motivo=f"Dipendente non presente in anagrafica per la ditta {ditta}",
            cosa_fare=cosa_fare,
        )

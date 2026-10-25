"""Il motore: dalle righe del report (movimenti) ai file VOCI e SCARTI.

Per ogni movimento:
    1. legge l'importo                      (importi.py)
    2. riconosce il dipendente nella ditta  (anagrafica.py)  - o usa la correzione
    3. trova la voce                        (voci.py)        - o usa la correzione
Poi:
    4. somma gli importi per coppia dipendente/voce
    5. scarta i totali negativi, non esporta i totali a zero
    6. ordina e scrive i record             (tracciato.py)
    7. calcola la quadratura: totale letto = totale esportato + totale scartato

Niente sparisce in silenzio: ogni riga non esportata finisce nel file scarti con
il motivo, e ogni scelta "non scontata" (abbinamento per somiglianza, codice o
voce inseriti a mano) compare come AVVISO.
"""

import csv
import io
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .anagrafica import Anagrafica, normalizza_ditta
from .importi import ImportoNonLeggibile, leggi_importo
from .tracciato import controlla_periodo, crea_record
from .voci import TabellaVoci, normalizza_testo

SCARTO = "SCARTO"
AVVISO = "AVVISO"


# ---------------------------------------------------------------- dati in ingresso

@dataclass
class Movimento:
    """Una riga del report del provider, già estratta secondo la configurazione."""
    riga: int                                  # numero di riga nel file originale
    importo: object                            # come scritto nel file (testo o numero)
    trattamento: str
    sottocategoria: Optional[str] = None
    codice_fiscale: Optional[str] = None
    codice: Optional[str] = None
    nome: Optional[tuple] = None               # (cognome, nome) o (nome completo,)

    def descrizione_dipendente(self) -> str:
        """Come il provider indica il dipendente: è ciò che si legge negli scarti."""
        parti = []
        if self.nome:
            parti.append(" ".join(str(p).strip() for p in self.nome if p))
        if self.codice:
            parti.append(f"cod. {str(self.codice).strip()}")
        if self.codice_fiscale:
            parti.append(f"CF {str(self.codice_fiscale).strip()}")
        return " · ".join(parti) or "(non indicato)"

    def chiave_dipendente(self) -> str:
        """Identifica il dipendente del provider: serve per le correzioni a mano,
        che valgono per tutte le sue righe."""
        if self.codice_fiscale:
            return "CF:" + str(self.codice_fiscale).strip().upper()
        if self.codice:
            return "COD:" + str(self.codice).strip()
        return "NOME:" + " ".join(sorted(" ".join(str(p) for p in (self.nome or ()) if p).upper().split()))

    def chiave_trattamento(self) -> tuple:
        return (normalizza_testo(self.trattamento), normalizza_testo(self.sottocategoria))


@dataclass
class Correzioni:
    """Correzioni inserite a mano dall'utente nell'app.

    dipendenti: chiave_dipendente -> codice gestionale
    voci:       chiave_trattamento -> codice voce
    """
    dipendenti: dict = field(default_factory=dict)
    voci: dict = field(default_factory=dict)


# ---------------------------------------------------------------- risultato

@dataclass
class Segnalazione:
    tipo: str                    # SCARTO o AVVISO
    riga: Optional[int]
    dipendente: str
    trattamento: str
    sottocategoria: str
    importo: str
    motivo: str
    cosa_fare: str = ""
    valore: Optional[Decimal] = None     # importo letto, se leggibile


@dataclass
class DaCorreggere:
    """Un dipendente o un trattamento che l'utente può correggere a mano."""
    chiave: object
    descrizione: str
    motivo: str
    righe: int = 0
    totale: Decimal = Decimal(0)


@dataclass
class Risultato:
    provider: str
    ditta: str
    periodo: str
    record: list = field(default_factory=list)
    segnalazioni: list = field(default_factory=list)
    avvisi_generali: list = field(default_factory=list)
    dipendenti_da_correggere: "OrderedDict" = field(default_factory=OrderedDict)
    voci_da_correggere: "OrderedDict" = field(default_factory=OrderedDict)
    righe_lette: int = 0
    righe_esportate: int = 0
    importi_non_leggibili: int = 0
    totale_letto: Decimal = Decimal(0)
    totale_esportato: Decimal = Decimal(0)
    totale_scartato: Decimal = Decimal(0)

    @property
    def scarti(self) -> list:
        return [s for s in self.segnalazioni if s.tipo == SCARTO]

    @property
    def avvisi(self) -> list:
        return [s for s in self.segnalazioni if s.tipo == AVVISO]

    @property
    def quadratura_ok(self) -> bool:
        return self.totale_letto == self.totale_esportato + self.totale_scartato

    @property
    def nome_file_voci(self) -> str:
        return f"VOCI_{self.ditta}_{self.periodo}.txt"

    @property
    def nome_file_scarti(self) -> str:
        provider = re.sub(r"[^A-Za-z0-9]+", "", self.provider) or "PROVIDER"
        return f"SCARTI_{provider}_{self.ditta}_{self.periodo}.csv"

    def file_voci(self) -> bytes:
        """Un record per riga, ogni riga chiusa da CRLF (anche l'ultima), solo ASCII."""
        return "".join(r + "\r\n" for r in self.record).encode("ascii")

    def file_scarti(self) -> bytes:
        """CSV con separatore ';' e BOM UTF-8: si apre in Excel con gli accenti giusti."""
        buffer = io.StringIO()
        scrittore = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        scrittore.writerow(["Tipo", "Riga file", "Dipendente", "Trattamento",
                            "Sottocategoria", "Importo", "Motivo", "Cosa fare"])
        for s in self.segnalazioni:
            scrittore.writerow([s.tipo, s.riga or "", s.dipendente, s.trattamento,
                                s.sottocategoria, s.importo, s.motivo, s.cosa_fare])
        return buffer.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------- funzioni di supporto

def formatta_euro(valore: Decimal) -> str:
    """1234.5 -> '1234,50' (formato che Excel italiano legge come numero)."""
    return f"{valore:.2f}".replace(".", ",")


def _ordine_codice(codice: str):
    """Ordine numerico se il codice è un numero (9 prima di 10), altrimenti alfabetico."""
    return (0, int(codice), "") if codice.isdigit() else (1, 0, codice)


def controlla_ditta(ditta) -> str:
    testo = str(ditta).strip()
    if not testo.isdigit() or len(testo.lstrip("0") or "0") > 6:
        raise ValueError(f"Il codice ditta '{testo}' deve essere un numero di massimo 6 cifre")
    return normalizza_ditta(testo)


def controlla_codice_manuale(codice, lunghezza: int, cosa: str) -> str:
    testo = str(codice).strip()
    if not testo or len(testo) > lunghezza or not testo.isascii() or " " in testo:
        raise ValueError(f"{cosa} '{testo}' non valido: massimo {lunghezza} caratteri, senza spazi")
    return testo


# ---------------------------------------------------------------- conversione

def converti(movimenti, ditta, periodo, anagrafica: Anagrafica, tabella: TabellaVoci,
             formato_importo: str = "auto", correzioni: Optional[Correzioni] = None,
             provider: str = "") -> Risultato:
    ditta = controlla_ditta(ditta)
    periodo = controlla_periodo(periodo)
    correzioni = correzioni or Correzioni()
    ris = Risultato(provider=provider, ditta=ditta, periodo=periodo)

    somme = OrderedDict()     # (codice dipendente, voce) -> [totale, lista movimenti, lista importi]
    dipendenti_non_trovati = 0

    for m in movimenti:
        ris.righe_lette += 1
        problemi, rimedi = [], []
        sotto = str(m.sottocategoria or "").strip()

        # 1) importo
        valore = None
        try:
            valore = leggi_importo(m.importo, formato_importo)
            ris.totale_letto += valore
        except ImportoNonLeggibile as errore:
            ris.importi_non_leggibili += 1
            problemi.append(f"Importo non leggibile: {errore}")
            rimedi.append("Verificare l'importo nel file del provider")

        avvisi_riga = []   # registrati solo se la riga viene esportata

        def avviso(testo):
            avvisi_riga.append(Segnalazione(
                AVVISO, m.riga, m.descrizione_dipendente(), str(m.trattamento or ""), sotto,
                formatta_euro(valore) if valore is not None else str(m.importo), testo))

        # 2) dipendente
        codice = None
        chiave_dip = m.chiave_dipendente()
        if chiave_dip in correzioni.dipendenti:
            codice = controlla_codice_manuale(correzioni.dipendenti[chiave_dip], 6, "Codice dipendente")
            avviso(f"Codice dipendente {codice} inserito a mano")
        else:
            esito = anagrafica.riconosci(ditta, codice_fiscale=m.codice_fiscale,
                                         codice=m.codice, nome=m.nome)
            if esito.trovato:
                codice = esito.codice
            else:
                if "non presente in anagrafica" in (esito.motivo or ""):
                    dipendenti_non_trovati += 1
                problemi.append(esito.motivo)
                rimedi.append(esito.cosa_fare)
                voce_ui = ris.dipendenti_da_correggere.setdefault(
                    chiave_dip, DaCorreggere(chiave_dip, m.descrizione_dipendente(), esito.motivo))
                voce_ui.righe += 1
                voce_ui.totale += valore or 0

        # 3) voce
        voce = None
        chiave_tratt = m.chiave_trattamento()
        if chiave_tratt in correzioni.voci:
            voce = controlla_codice_manuale(correzioni.voci[chiave_tratt], 4, "Codice voce")
            avviso(f"Voce {voce} scelta a mano")
        else:
            esito_voce = tabella.trova(m.trattamento, m.sottocategoria)
            if esito_voce.trovata:
                voce = esito_voce.codice
                if esito_voce.avviso:
                    avviso(esito_voce.avviso)
            else:
                problemi.append(esito_voce.motivo)
                rimedi.append(esito_voce.cosa_fare)
                descr = str(m.trattamento or "").strip() + (f" ({sotto})" if sotto else "")
                voce_ui = ris.voci_da_correggere.setdefault(
                    chiave_tratt, DaCorreggere(chiave_tratt, descr, esito_voce.motivo))
                voce_ui.righe += 1
                voce_ui.totale += valore or 0

        # 4) scarto della riga oppure somma
        if problemi:
            ris.segnalazioni.append(Segnalazione(
                SCARTO, m.riga, m.descrizione_dipendente(), str(m.trattamento or ""), sotto,
                formatta_euro(valore) if valore is not None else str(m.importo),
                "; ".join(problemi), "; ".join(dict.fromkeys(r for r in rimedi if r)),
                valore))
            if valore is not None:
                ris.totale_scartato += valore
            continue
        ris.segnalazioni.extend(avvisi_riga)
        somma = somme.setdefault((codice, voce), [Decimal(0), []])
        somma[0] += valore
        somma[1].append((m, valore))

    # 5) totali per dipendente/voce
    for (codice, voce), (totale, righe) in somme.items():
        if totale < 0:
            for m, valore in righe:
                ris.segnalazioni.append(Segnalazione(
                    SCARTO, m.riga, m.descrizione_dipendente(), str(m.trattamento or ""),
                    str(m.sottocategoria or "").strip(), formatta_euro(valore),
                    f"Totale negativo per dipendente {codice} e voce {voce} "
                    f"({formatta_euro(totale)} €): il tracciato non ammette importi negativi",
                    "Verificare con il provider lo storno e gestirlo a mano nel gestionale",
                    valore))
            ris.totale_scartato += totale
            continue
        if totale == 0:
            ris.avvisi_generali.append(
                f"Dipendente {codice}, voce {voce}: totale zero, nessun record esportato")
            continue
        try:
            record = crea_record(ditta, codice, voce, totale, periodo)
        except ValueError as errore:
            for m, valore in righe:
                ris.segnalazioni.append(Segnalazione(
                    SCARTO, m.riga, m.descrizione_dipendente(), str(m.trattamento or ""),
                    str(m.sottocategoria or "").strip(), formatta_euro(valore),
                    f"Record non scrivibile: {errore}", "Verificare codice dipendente e voce", valore))
            ris.totale_scartato += totale
            continue
        ris.record.append((codice, voce, record))
        ris.totale_esportato += totale
        ris.righe_esportate += len(righe)

    # 6) ordinamento: codice dipendente (numerico), poi voce
    ris.record.sort(key=lambda r: (_ordine_codice(r[0]), _ordine_codice(r[1])))
    ris.record = [r[2] for r in ris.record]
    ris.segnalazioni.sort(key=lambda s: (s.riga or 0, s.tipo != SCARTO))

    # 7) controllo sulla ditta scelta
    if ris.righe_lette and dipendenti_non_trovati > ris.righe_lette / 2:
        ris.avvisi_generali.insert(0,
            f"Più della metà delle righe ha dipendenti non presenti nell'anagrafica della "
            f"ditta {ditta}: hai scelto la ditta giusta?")
    return ris

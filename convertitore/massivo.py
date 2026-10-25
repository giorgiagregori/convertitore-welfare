"""Caricamento massivo: tanti file di provider diversi, convertiti insieme.

Il motore è lo stesso della conversione singola (motore.converti). Qui si
aggiungono solo i passaggi per lavorare su un lotto di file:

    1. analizza_file   per ogni file: lo legge, riconosce il provider dalle
                       colonne e propone la ditta dai dipendenti (come l'app
                       singola, ma senza che l'operatore scelga il provider)
    2. converti_lotto  raggruppa i file per ditta e produce un solo file VOCI per
                       ditta: se due file (anche di provider diversi) riguardano
                       la stessa ditta, i loro movimenti vengono convertiti
                       insieme e gli importi dello stesso dipendente sulla stessa
                       voce si sommano
    3. RisultatoLotto  un file VOCI per ditta, un unico file SCARTI con le
                       colonne File / Provider / Ditta, tutto in uno zip

Controlli in più rispetto alla conversione singola:
    - file caricato due volte (stesso contenuto): il secondo è bloccato
    - provider non riconoscibile o riconoscibile in più modi: da scegliere a mano
    - nessun dipendente in anagrafica: file bloccato
"""

import csv
import hashlib
import io
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .configurazione import FileNonCorrispondente, avviso_nome_file, estrai_movimenti
from .ditte import Proposta, proponi_ditta
from .lettura import FileNonLeggibile, leggi_righe
from .motore import AVVISO, SCARTO, Correzioni, Risultato, converti

PRONTO = "pronto"
DA_GUARDARE = "da guardare"
BLOCCATO = "bloccato"


@dataclass
class FileAnalizzato:
    nome: str
    contenuto: bytes = field(repr=False)
    impronta: str = ""
    compatibili: list = field(default_factory=list)   # provider che riescono a leggere il file
    provider: Optional[str] = None                    # provider usato (riconosciuto o scelto)
    proposta: Optional[Proposta] = None
    errore: Optional[str] = None                      # motivo del blocco
    avvisi: list = field(default_factory=list)        # cose da guardare, non bloccanti

    @property
    def ditta_proposta(self) -> Optional[str]:
        return self.proposta.ditta if self.proposta else None

    @property
    def stato(self) -> str:
        if self.errore:
            return BLOCCATO
        if self.avvisi or not self.ditta_proposta:
            return DA_GUARDARE
        return PRONTO


def impronta(contenuto: bytes) -> str:
    return hashlib.md5(contenuto).hexdigest()


def _movimenti(conv, righe, provider: str, nome_file: str) -> list:
    """I movimenti del file, marcati con il file di provenienza e il formato degli
    importi del loro provider (nel lotto convivono provider con formati diversi)."""
    conf = conv.providers[provider]
    movimenti = estrai_movimenti(righe, conf, provider)
    for m in movimenti:
        m.origine = nome_file
        m.formato_importo = conf.get("formato_importo", "auto")
    return movimenti


def analizza_file(conv, nome: str, contenuto: bytes, provider: Optional[str] = None) -> FileAnalizzato:
    """Legge il file, riconosce il provider (o usa quello indicato) e propone la ditta."""
    analisi = FileAnalizzato(nome, contenuto, impronta(contenuto))
    try:
        righe = leggi_righe(contenuto, nome)
    except FileNonLeggibile as errore:
        analisi.errore = str(errore)
        return analisi
    analisi.compatibili = conv.providers_compatibili(righe)

    if provider is None:
        if not analisi.compatibili:
            analisi.errore = ("Il file non corrisponde a nessun provider configurato: "
                              "controlla che sia un report welfare o aggiungi il provider in providers.json")
            return analisi
        provider = analisi.compatibili[0]
        if len(analisi.compatibili) > 1:
            analisi.avvisi.append("Il file è leggibile come " + " o ".join(analisi.compatibili)
                                  + ": controlla il provider")
    analisi.provider = provider

    try:
        movimenti = _movimenti(conv, righe, provider, nome)
    except FileNonCorrispondente as errore:
        altri = [p for p in analisi.compatibili if p != provider]
        analisi.errore = (f"Il file sembra del {' o del '.join(altri)}, non del {provider}"
                          if altri else str(errore))
        return analisi

    analisi.proposta = proponi_ditta(movimenti, conv.anagrafica)
    if not analisi.proposta.per_ditta:
        analisi.errore = "Nessun dipendente del file è presente in anagrafica"
        return analisi
    if not analisi.proposta.ditta:
        analisi.avvisi.append("Ditta da scegliere: " + analisi.proposta.motivo)
    nome_strano = avviso_nome_file(conv.providers[provider], nome, provider)
    if nome_strano:
        analisi.avvisi.append(nome_strano)
    return analisi


def analizza_lotto(conv, files) -> list:
    """files: lista di (nome, contenuto). Un file con lo stesso contenuto di uno
    già caricato viene bloccato: convertirlo due volte raddoppierebbe gli importi."""
    risultato, visti = [], {}
    for nome, contenuto in files:
        chiave = impronta(contenuto)
        if chiave in visti:
            doppio = FileAnalizzato(nome, contenuto, chiave)
            doppio.errore = f"Stesso contenuto di '{visti[chiave]}': caricato due volte"
            risultato.append(doppio)
            continue
        visti[chiave] = nome
        risultato.append(analizza_file(conv, nome, contenuto))
    return risultato


# ---------------------------------------------------------------- conversione del lotto

@dataclass
class Scelta:
    """Il file da convertire, con provider e ditta confermati dall'operatore."""
    nome: str
    contenuto: bytes = field(repr=False)
    provider: str = ""
    ditta: str = ""


@dataclass
class RisultatoLotto:
    periodo: str
    per_ditta: "OrderedDict" = field(default_factory=OrderedDict)    # ditta -> Risultato
    file_per_ditta: dict = field(default_factory=dict)               # ditta -> [nomi file]
    provider_del_file: dict = field(default_factory=dict)            # nome file -> provider
    ditta_del_file: dict = field(default_factory=dict)               # nome file -> ditta
    righe_per_file: dict = field(default_factory=dict)               # nome file -> righe lette
    errori: list = field(default_factory=list)                       # (nome file, motivo)

    def _tutti(self, attributo):
        return sum((getattr(r, attributo) for r in self.per_ditta.values()), Decimal(0))

    @property
    def totale_letto(self):
        return self._tutti("totale_letto")

    @property
    def totale_esportato(self):
        return self._tutti("totale_esportato")

    @property
    def totale_scartato(self):
        return self._tutti("totale_scartato")

    @property
    def quadratura_ok(self) -> bool:
        return all(r.quadratura_ok for r in self.per_ditta.values())

    @property
    def record(self) -> int:
        return sum(len(r.record) for r in self.per_ditta.values())

    @property
    def segnalazioni(self) -> list:
        return [(ditta, s) for ditta, r in self.per_ditta.items() for s in r.segnalazioni]

    def conta(self, tipo: str, nome_file: Optional[str] = None) -> int:
        return sum(1 for _, s in self.segnalazioni
                   if s.tipo == tipo and (nome_file is None or s.origine == nome_file))

    @property
    def nome_file_scarti(self) -> str:
        return f"SCARTI_{self.periodo}.csv"

    @property
    def nome_zip(self) -> str:
        return f"VOCI_{self.periodo}.zip"

    def file_scarti(self) -> bytes:
        """Un unico CSV per tutto il lotto: le stesse colonne della conversione
        singola, più File, Provider e Ditta per sapere da dove viene ogni riga."""
        buffer = io.StringIO()
        scrittore = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        scrittore.writerow(["File", "Provider", "Ditta", "Tipo", "Riga file", "Dipendente",
                            "Trattamento", "Sottocategoria", "Importo", "Motivo", "Cosa fare"])
        for ditta, s in self.segnalazioni:
            scrittore.writerow([s.origine, self.provider_del_file.get(s.origine, ""), ditta,
                                s.tipo, s.riga or "", s.dipendente, s.trattamento,
                                s.sottocategoria, s.importo, s.motivo, s.cosa_fare])
        for ditta, r in self.per_ditta.items():
            for testo in r.avvisi_generali:
                scrittore.writerow(["", "", ditta, AVVISO, "", "", "", "", "", testo, ""])
        return buffer.getvalue().encode("utf-8-sig")

    def file_zip(self) -> bytes:
        """Tutti i file VOCI (uno per ditta con almeno un record) e il file SCARTI."""
        memoria = io.BytesIO()
        with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as archivio:
            for r in self.per_ditta.values():
                if r.record:
                    archivio.writestr(r.nome_file_voci, r.file_voci())
            if self.segnalazioni or any(r.avvisi_generali for r in self.per_ditta.values()):
                archivio.writestr(self.nome_file_scarti, self.file_scarti())
        return memoria.getvalue()


def converti_lotto(conv, scelte: list, periodo, correzioni: Optional[dict] = None) -> RisultatoLotto:
    """scelte: lista di Scelta. correzioni: {ditta: Correzioni}.

    I file vengono raggruppati per ditta; per ogni ditta si convertono insieme
    tutti i movimenti, quindi esce un solo file VOCI per ditta e la quadratura
    vale per ditta (totale letto dai suoi file = esportato + scartato)."""
    correzioni = correzioni or {}
    lotto = RisultatoLotto(periodo=str(periodo))
    movimenti_per_ditta = OrderedDict()
    provider_per_ditta = {}

    for scelta in scelte:
        try:
            righe = leggi_righe(scelta.contenuto, scelta.nome)
            movimenti = _movimenti(conv, righe, scelta.provider, scelta.nome)
        except (FileNonLeggibile, FileNonCorrispondente, KeyError) as errore:
            lotto.errori.append((scelta.nome, str(errore)))
            continue
        ditta = str(scelta.ditta)
        movimenti_per_ditta.setdefault(ditta, []).extend(movimenti)
        provider_per_ditta.setdefault(ditta, [])
        if scelta.provider not in provider_per_ditta[ditta]:
            provider_per_ditta[ditta].append(scelta.provider)
        lotto.file_per_ditta.setdefault(ditta, []).append(scelta.nome)
        lotto.provider_del_file[scelta.nome] = scelta.provider
        lotto.ditta_del_file[scelta.nome] = ditta
        lotto.righe_per_file[scelta.nome] = len(movimenti)

    for ditta in sorted(movimenti_per_ditta, key=lambda d: (len(d), d)):
        lotto.per_ditta[ditta] = converti(
            movimenti_per_ditta[ditta], ditta, periodo, conv.anagrafica, conv.tabella,
            "auto", correzioni.get(ditta), " + ".join(provider_per_ditta[ditta]))
    return lotto

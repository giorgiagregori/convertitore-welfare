"""Configurazione dei provider: come si legge il report di ciascuno.

Ogni provider è descritto in config/providers.json. Aggiungere un provider
significa aggiungere un blocco lì, senza toccare il codice.

Campi di una configurazione:
    intestazione      true  -> le colonne si indicano per nome (la riga di
                               intestazione viene cercata nel file)
                      false -> il file non ha intestazione: le colonne si
                               indicano per posizione (1 = prima colonna)
    formato_importo   "it", "en" o "auto"            (vedi importi.py)
    dipendente        uno o più tra:
                        codice_fiscale  colonna
                        codice          colonna
                        nome            lista di colonne (es. cognome e nome)
                      ogni colonna può avere una condizione:
                        {"colonna": "...", "solo_se": {"colonna": "...", "uguale": "..."}}
    trattamento       lista di colonne: se sono più di una vengono unite con
                      uno spazio (Provider C: "Art.51" + "c. 3" = "Art.51 c. 3")
    sottocategoria    colonna (facoltativa)
    importo           colonna
    controlli         (facoltativo) controlli che il file sia davvero del provider:
                        colonne    numero esatto di colonne di ogni riga
                        formati    {colonna: espressione regolare} che ogni riga
                                   di dati deve rispettare (es. "4": "^X\\d{5}$")
                        nome_file  espressione regolare sul nome del file: se non
                                   corrisponde è solo un avviso (i file si rinominano)
"""

import json
import re
from pathlib import Path

from .lettura import RigaFile
from .motore import Movimento


class ConfigurazioneNonValida(ValueError):
    pass


class FileNonCorrispondente(ValueError):
    """Il file non ha le colonne attese per il provider scelto."""


def carica_providers(percorso_json) -> dict:
    with open(Path(percorso_json), encoding="utf-8") as f:
        providers = json.load(f)
    for nome, conf in providers.items():
        for campo in ("dipendente", "trattamento", "importo"):
            if campo not in conf:
                raise ConfigurazioneNonValida(f"{nome}: manca il campo '{campo}'")
        if not conf["dipendente"]:
            raise ConfigurazioneNonValida(f"{nome}: indicare almeno un modo per riconoscere il dipendente")
    return providers


def _norm(testo) -> str:
    return re.sub(r"\s+", " ", str(testo or "")).strip().lower()


def _colonne_usate(conf) -> list:
    """Tutte le colonne citate nella configurazione (per cercarle nel file)."""
    colonne = []

    def aggiungi(rif):
        if isinstance(rif, dict):
            colonne.append(rif["colonna"])
            if "solo_se" in rif:
                colonne.append(rif["solo_se"]["colonna"])
        elif isinstance(rif, list):
            for r in rif:
                aggiungi(r)
        elif rif is not None:
            colonne.append(rif)

    for rif in conf["dipendente"].values():
        aggiungi(rif)
    aggiungi(conf["trattamento"])
    aggiungi(conf.get("sottocategoria"))
    aggiungi(conf["importo"])
    return colonne


def _trova_intestazione(righe: list, colonne: list, provider: str):
    """Cerca, tra le prime 30 righe, quella che contiene tutte le colonne attese."""
    attese = {_norm(c) for c in colonne}
    for i, riga in enumerate(righe[:30]):
        nomi = [_norm(v) for v in riga.valori]
        if attese.issubset(nomi):
            return i, {nome: posizione for posizione, nome in reversed(list(enumerate(nomi)))}
    # Messaggio utile: quali colonne mancano rispetto alla riga più simile.
    migliore = max(righe[:30], key=lambda r: len(attese & {_norm(v) for v in r.valori}), default=None)
    trovate = {_norm(v) for v in migliore.valori} if migliore else set()
    mancanti = sorted(c for c in colonne if _norm(c) not in trovate)
    raise FileNonCorrispondente(
        f"Il file non sembra del {provider}: mancano le colonne {', '.join(repr(m) for m in mancanti)}"
    )


def _verifica_controlli(dati: list, conf: dict, provider: str, valore):
    """Controlla che le righe di dati abbiano la forma attesa per il provider.

    Indispensabile per i file senza intestazione (Provider B): lì le colonne si
    prendono per posizione, quindi senza questi controlli qualsiasi file con
    abbastanza colonne verrebbe letto, producendo solo scarti senza senso.
    Basta una riga diversa per fermarsi: meglio un file rifiutato che un file
    VOCI costruito sui dati di un altro provider.
    """
    controlli = conf.get("controlli", {})
    attese = controlli.get("colonne")
    formati = {c: re.compile(r) for c, r in controlli.get("formati", {}).items()}
    for riga in dati:
        if attese and len(riga.valori) != attese:
            raise FileNonCorrispondente(
                f"Il file non sembra del {provider}: la riga {riga.numero} ha "
                f"{len(riga.valori)} colonne invece di {attese}")
        for colonna, formato in formati.items():
            v = valore(riga, colonna)
            testo = "" if v is None else str(v).strip()
            if not formato.match(testo):
                raise FileNonCorrispondente(
                    f"Il file non sembra del {provider}: alla riga {riga.numero} la colonna "
                    f"{colonna} contiene '{testo}', che non ha il formato atteso")


def avviso_nome_file(conf: dict, nome_file: str, provider: str):
    """Un avviso (non un blocco) se il nome del file non è quello solito del provider."""
    schema = conf.get("controlli", {}).get("nome_file")
    if schema and nome_file and not re.search(schema, nome_file, re.IGNORECASE):
        return (f"Il nome del file '{nome_file}' non è quello che di solito usa il {provider}. "
                "Se il file è stato rinominato va bene, altrimenti controlla il provider scelto.")
    return None


def estrai_movimenti(righe: list, conf: dict, provider: str = "") -> list:
    """Applica la configurazione alle righe lette e restituisce i movimenti."""
    if conf.get("intestazione", True):
        indice_intestazione, posizioni = _trova_intestazione(righe, _colonne_usate(conf), provider)
        dati = righe[indice_intestazione + 1:]

        def valore(riga: RigaFile, colonna):
            pos = posizioni[_norm(colonna)]
            return riga.valori[pos] if pos < len(riga.valori) else None
    else:
        dati = righe
        massimo = max(int(c) for c in _colonne_usate(conf))
        larghezza = max((len(r.valori) for r in righe), default=0)
        if larghezza < massimo:
            raise FileNonCorrispondente(
                f"Il file non sembra del {provider}: servono almeno {massimo} colonne, ne ha {larghezza}")

        def valore(riga: RigaFile, colonna):
            pos = int(colonna) - 1
            return riga.valori[pos] if pos < len(riga.valori) else None

    _verifica_controlli(dati, conf, provider, valore)

    def leggi(riga, rif):
        """Legge una colonna, rispettando l'eventuale condizione 'solo_se'."""
        if rif is None:
            return None
        if isinstance(rif, dict):
            cond = rif.get("solo_se")
            if cond and _norm(valore(riga, cond["colonna"])) != _norm(cond["uguale"]):
                return None
            return valore(riga, rif["colonna"])
        return valore(riga, rif)

    def testo(v):
        if v is None:
            return None
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        t = str(v).strip()
        return t if t and t != "-" else None

    movimenti = []
    dip = conf["dipendente"]
    for riga in dati:
        trattamento_parti = [testo(leggi(riga, c)) for c in conf["trattamento"]]
        trattamento = " ".join(p for p in trattamento_parti if p) or None
        importo = leggi(riga, conf["importo"])
        nome = tuple(testo(leggi(riga, c)) for c in dip["nome"]) if "nome" in dip else None
        if nome is not None and not any(nome):
            nome = None
        movimento = Movimento(
            riga=riga.numero,
            importo=importo,
            trattamento=trattamento,
            sottocategoria=testo(leggi(riga, conf.get("sottocategoria"))),
            codice_fiscale=testo(leggi(riga, dip.get("codice_fiscale"))),
            codice=testo(leggi(riga, dip.get("codice"))),
            nome=nome,
        )
        # Righe senza trattamento, importo e dipendente (es. righe di totale o
        # note in fondo al file) non sono movimenti: si saltano.
        if not (movimento.trattamento or testo(importo) or movimento.codice_fiscale
                or movimento.codice or movimento.nome):
            continue
        movimenti.append(movimento)
    if not movimenti:
        raise FileNonCorrispondente(f"Il file non contiene movimenti del {provider}")
    return movimenti

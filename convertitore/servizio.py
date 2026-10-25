"""Il punto di ingresso unico del convertitore: è quello che userà l'interfaccia.

    converti_file(contenuto, nome_file, provider, ditta, periodo, correzioni)
        -> Risultato (record, scarti, avvisi, quadratura, file da scaricare)
"""

from pathlib import Path
from typing import Optional

from .anagrafica import Anagrafica
from .ditte import Proposta, proponi_ditta
from .configurazione import (FileNonCorrispondente, avviso_nome_file, carica_providers,
                             estrai_movimenti)
from .lettura import leggi_righe
from .motore import Correzioni, Risultato, converti
from .voci import TabellaVoci

CARTELLA_CONFIG = Path(__file__).resolve().parent.parent / "config"


class Convertitore:
    """Carica una volta configurazioni, anagrafica e tabella delle voci."""

    def __init__(self, cartella_config=CARTELLA_CONFIG):
        cartella = Path(cartella_config)
        self.providers = carica_providers(cartella / "providers.json")
        self.anagrafica = Anagrafica(cartella / "Lista_Dipendenti.csv")
        self.tabella = TabellaVoci(cartella / "Codici_Welfare_Voci_Payroll.csv")

    def providers_compatibili(self, righe) -> list:
        """I provider la cui configurazione riesce a leggere il file."""
        compatibili = []
        for nome, conf in self.providers.items():
            try:
                estrai_movimenti(righe, conf, nome)
                compatibili.append(nome)
            except FileNonCorrispondente:
                pass
        return compatibili

    def _movimenti(self, contenuto: bytes, nome_file: str, provider: str) -> list:
        """Legge il file con la configurazione del provider scelto.

        Se il file non è del provider scelto ma è leggibile come quello di un
        altro, il messaggio lo dice: "sembra del Provider B, non del Provider A".
        """
        if provider not in self.providers:
            raise ValueError(f"Provider '{provider}' non configurato")
        righe = leggi_righe(contenuto, nome_file)
        try:
            return estrai_movimenti(righe, self.providers[provider], provider)
        except FileNonCorrispondente as errore:
            altri = [p for p in self.providers_compatibili(righe) if p != provider]
            if altri:
                raise FileNonCorrispondente(
                    f"Il file sembra del {' o del '.join(altri)}, non del {provider}: "
                    "controlla il provider scelto.") from errore
            raise

    def avviso_nome_file(self, nome_file: str, provider: str):
        return avviso_nome_file(self.providers[provider], nome_file, provider)

    def proponi_ditta(self, contenuto: bytes, nome_file: str, provider: str) -> Proposta:
        """La ditta a cui appartengono i dipendenti del file (vedi ditte.py)."""
        return proponi_ditta(self._movimenti(contenuto, nome_file, provider), self.anagrafica)

    def etichetta_ditta(self, ditta: str) -> str:
        """'4012 – Alfa Servizi S.r.l.', per i menu a tendina."""
        nome = self.anagrafica.ragioni_sociali.get(ditta, "")
        return f"{ditta} – {nome}" if nome else ditta

    def converti_file(self, contenuto: bytes, nome_file: str, provider: str, ditta, periodo,
                      correzioni: Optional[Correzioni] = None) -> Risultato:
        movimenti = self._movimenti(contenuto, nome_file, provider)
        conf = self.providers[provider]
        return converti(movimenti, ditta, periodo, self.anagrafica, self.tabella,
                        conf.get("formato_importo", "auto"), correzioni, provider)

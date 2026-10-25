"""Percorsi e costanti condivisi dai test."""

import importlib.util
from pathlib import Path

CARTELLA = Path(__file__).parent / "dati_kit"
INPUT = CARTELLA / "input"
FILE_C = "ProviderC_Erogazioni_fatt_031900.xls"

# Il file del Provider C è un .xls: per leggerlo serve xlrd (in requirements.txt).
XLRD_DISPONIBILE = importlib.util.find_spec("xlrd") is not None
SENZA_XLRD = "xlrd non installato: pip install -r requirements.txt"

"""Il file caricato deve essere davvero del provider scelto."""

import glob
import unittest
from pathlib import Path

from convertitore.configurazione import FileNonCorrispondente
from convertitore.servizio import Convertitore

from comune import FILE_C, INPUT, XLRD_DISPONIBILE
FILE = {
    "Provider A": "ProviderA_*",
    "Provider B": "ProviderB_*",
    "Provider C": FILE_C,
    "Provider D": "ProviderD_*",
    "Provider E": "ProviderE_*",
}


PROVIDER_PROVABILI = [p for p in FILE if p != "Provider C" or XLRD_DISPONIBILE]


def file_di(provider):
    return Path(glob.glob(str(INPUT / FILE[provider]))[0])


class TestControlliFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conv = Convertitore()

    def test_ogni_file_solo_col_suo_provider(self):
        """Tutte le 25 combinazioni: si converte solo quando file e provider coincidono,
        altrimenti il messaggio dice di quale provider sembra il file."""
        for scelto in PROVIDER_PROVABILI:
            for vero in PROVIDER_PROVABILI:
                percorso = file_di(vero)
                with self.subTest(scelto=scelto, file=vero):
                    if scelto == vero:
                        self.conv.converti_file(percorso.read_bytes(), percorso.name, scelto, "4012", "202609")
                    else:
                        with self.assertRaisesRegex(FileNonCorrispondente,
                                                    f"sembra del {vero}, non del {scelto}"):
                            self.conv.converti_file(percorso.read_bytes(), percorso.name, scelto,
                                                    "4012", "202609")

    def test_provider_b_riga_con_formato_diverso(self):
        percorso = file_di("Provider B")
        righe = percorso.read_bytes().split(b"\n")
        righe[2] = righe[2].replace(b"X71180", b"ABC")     # codice trattamento non valido
        with self.assertRaisesRegex(FileNonCorrispondente, "riga 3 la colonna 4 contiene 'ABC'"):
            self.conv.converti_file(b"\n".join(righe), percorso.name, "Provider B", "4027", "202609")

    def test_provider_b_numero_di_colonne(self):
        percorso = file_di("Provider B")
        righe = percorso.read_bytes().split(b"\n")
        righe[0] = righe[0].rstrip(b"\r") + b";extra\r"
        with self.assertRaisesRegex(FileNonCorrispondente, "riga 1 ha 14 colonne invece di 13"):
            self.conv.converti_file(b"\n".join(righe), percorso.name, "Provider B", "4027", "202609")

    def test_file_senza_movimenti(self):
        intestazione = "Nome dipendente;Cognome dipendente;Codice fiscale fruitore benefit;" \
                       "Parentela fruitore benefit;Riferimento al TUIR;Tipologia di servizio;Valore\n"
        with self.assertRaisesRegex(FileNonCorrispondente, "non contiene movimenti"):
            self.conv.converti_file(intestazione.encode(), "tracciato.csv", "Provider D", "4093", "202609")

    def test_nome_file_solo_avviso(self):
        for provider in PROVIDER_PROVABILI:
            self.assertIsNone(self.conv.avviso_nome_file(file_di(provider).name, provider))
        avviso = self.conv.avviso_nome_file(file_di("Provider B").name, "Provider A")
        self.assertIn("non è quello che di solito usa il Provider A", avviso)
        self.assertIsNone(self.conv.avviso_nome_file("ProviderC_Erogazioni_fatt_031900.xls", "Provider C"))


if __name__ == "__main__":
    unittest.main()

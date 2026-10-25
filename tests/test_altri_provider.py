"""Passo 2: prova completa sui file dei Provider B, C, D, E del kit.

Per ogni provider si controllano: righe lette, record, scarti attesi (quelli
individuati leggendo il kit), avvisi, quadratura e alcuni record campione.
"""

import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path

from convertitore.lettura import _separatore
from convertitore.servizio import Convertitore

INPUT = Path(__file__).parent / "dati_kit" / "input"
XLRD_DISPONIBILE = importlib.util.find_spec("xlrd") is not None


class Base(unittest.TestCase):
    conv = None

    @classmethod
    def setUpClass(cls):
        if Base.conv is None:
            Base.conv = Convertitore()

    def converti(self, provider, nome_file, ditta):
        percorso = INPUT / nome_file
        return self.conv.converti_file(percorso.read_bytes(), percorso.name, provider, ditta, "202609")

    def controlla(self, ris, righe, record, scarti, avvisi, letto, esportato, scartato):
        self.assertEqual(ris.righe_lette, righe)
        self.assertEqual(len(ris.record), record)
        self.assertEqual(len(ris.scarti), scarti)
        self.assertEqual(len(ris.avvisi), avvisi)
        self.assertEqual(ris.totale_letto, Decimal(letto))
        self.assertEqual(ris.totale_esportato, Decimal(esportato))
        self.assertEqual(ris.totale_scartato, Decimal(scartato))
        self.assertTrue(ris.quadratura_ok)
        self.assertEqual(ris.avvisi_generali, [])
        for r in ris.record:
            self.assertEqual(len(r), 38)


class TestProviderB(Base):
    """CSV senza intestazione, codifica Windows, dipendente solo per nome."""

    def test_completo(self):
        ris = self.converti("Provider B", "ProviderB_Flusso-Payroll-01_10_2026.csv", "4027")
        self.controlla(ris, 12, 6, 4, 0, "7266.47", "2929.40", "4337.07")
        motivi = {(s.dipendente, s.motivo) for s in ris.scarti}
        self.assertIn(("MARINI SOFIA", "Dipendente non presente in anagrafica per la ditta 4027"), motivi)
        self.assertIn(("DE SANTIS LAURA", "Trattamento 'X71133' non presente in tabella"), motivi)
        # Della Rosa, due righe X71180 (99,61 + 212,17) -> un record da 311,78 su voce 380.
        self.assertIn("00402715013 380 0000000000031178202609", ris.record)

    def test_marini_sofia_correggibile_una_volta_per_tre_righe(self):
        ris = self.converti("Provider B", "ProviderB_Flusso-Payroll-01_10_2026.csv", "4027")
        self.assertEqual(len(ris.dipendenti_da_correggere), 1)
        da_corr = next(iter(ris.dipendenti_da_correggere.values()))
        self.assertEqual((da_corr.righe, da_corr.totale), (3, Decimal("4287.07")))


class TestProviderC(Base):
    """Excel .xls, trattamento su due colonne, sottocategoria Effettivo/Figurativo."""

    def file_c(self):
        # Online xlrd è installato e si usa il file .xls originale. Dove xlrd non
        # c'è (l'ambiente di sviluppo) si usa una copia convertita in .xlsx con
        # gli stessi dati.
        if XLRD_DISPONIBILE:
            return "ProviderC_Erogazioni_fatt_031900.xls"
        return "ProviderC_convertito_per_test.xlsx"

    def test_completo(self):
        ris = self.converti("Provider C", self.file_c(), "4041")
        self.controlla(ris, 20, 17, 0, 1, "5346.93", "5346.93", "0")
        # Art.51 c. 3 Effettivo -> 194; Figurativo -> 371 (per somiglianza, con avviso).
        self.assertIn("00404120    194 0000000000031210202609", ris.record)
        self.assertIn("00404150    371 0000000000011713202609", ris.record)
        self.assertIn("somiglianza", ris.avvisi[0].motivo)
        # Ferrari Galli, tre rimborsi f bis (570 + 248,60 + 518,32) -> 1.336,92 su 372.
        self.assertIn("00404113    372 0000000000133692202609", ris.record)

    @unittest.skipUnless(XLRD_DISPONIBILE, "xlrd non installato: test sul .xls originale saltato")
    def test_xls_originale(self):
        ris = self.converti("Provider C", "ProviderC_Erogazioni_fatt_031900.xls", "4041")
        self.assertEqual(len(ris.record), 17)


class TestProviderD(Base):
    """CSV con intestazione, dipendente per nome, CF solo se "Me stesso"."""

    def test_completo(self):
        ris = self.converti("Provider D", "ProviderD_tracciato_set26.csv", "4093")
        self.controlla(ris, 17, 12, 2, 0, "2897.26", "2453.17", "444.09")
        motivi = " | ".join(s.motivo for s in ris.scarti)
        self.assertIn("Asilo nido", motivi)
        self.assertIn("voci possibili 372, 373", motivi)
        self.assertIn("Dipendente non presente in anagrafica per la ditta 4093", motivi)
        # Coppola: il rimborso per il figlio (Istruzione) va su 373, il voucher suo su 370.
        self.assertIn("00409338    373 0000000000035172202609", ris.record)
        self.assertIn("00409338    370 0000000000014800202609", ris.record)


class TestProviderE(Base):
    """Excel con codice + CF; importo nella colonna Totale."""

    def test_completo(self):
        ris = self.converti("Provider E", "ProviderE_welfare_settembre_2026.xlsx", "4131")
        self.controlla(ris, 19, 11, 3, 2, "2051.86", "1897.10", "154.76")
        self.assertTrue(all("GUERRA PAOLO" in s.dipendente for s in ris.scarti))
        # Giordano: 68,00 + 27,94 (2 pezzi da 13,97: si usa Totale, non Importo) = 95,94 su 371.
        self.assertIn("00413115000 371 0000000000009594202609", ris.record)


class TestSeparatoreCsv(unittest.TestCase):

    def test_virgola_decimale_non_confonde(self):
        testo = "19;RUSSO;MARCO;X71180;20260924;;;;60,00;;\n19;ROSSI;ANNA;X71180;20260924;;;;12,50;;\n"
        self.assertEqual(_separatore(testo), ";")

    def test_altri_separatori(self):
        self.assertEqual(_separatore("a,b,c\n1,2,3\n"), ",")
        self.assertEqual(_separatore("a\tb\tc\n1\t2\t3\n"), "\t")


if __name__ == "__main__":
    unittest.main()

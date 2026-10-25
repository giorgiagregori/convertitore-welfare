"""Test del pezzo 6: prova completa sul file del Provider A.

Criteri di accettazione della specifica:
- senza correzioni: 18 record e Alessia Fumagalli nel file scarti;
- con Alessia Fumagalli = 25 inserito a mano: output identico byte per byte a
  ESEMPIO_VOCI_4012_202609.txt.
"""

import unittest
from decimal import Decimal
from pathlib import Path

from convertitore.configurazione import FileNonCorrispondente
from convertitore.motore import Correzioni
from convertitore.servizio import Convertitore

KIT = Path(__file__).parent / "dati_kit"
FILE_A = KIT / "input" / "ProviderA_welfare_report_2026-09-01_2026-09-30.xlsx"
ESEMPIO = KIT / "esempio_output" / "ESEMPIO_VOCI_4012_202609.txt"


class TestProviderA(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conv = Convertitore()
        cls.contenuto = FILE_A.read_bytes()

    def converti(self, correzioni=None):
        return self.conv.converti_file(self.contenuto, FILE_A.name, "Provider A",
                                       "4012", "202609", correzioni)

    def test_senza_correzioni(self):
        ris = self.converti()
        self.assertEqual(ris.righe_lette, 21)
        self.assertEqual(len(ris.record), 18)
        self.assertEqual(len(ris.scarti), 1)
        scarto = ris.scarti[0]
        self.assertEqual(scarto.riga, 8)                        # riga 8 del file Excel
        self.assertIn("Alessia Fumagalli", scarto.dipendente)
        self.assertEqual(scarto.importo, "56,16")
        self.assertEqual(scarto.motivo, "Dipendente non presente in anagrafica per la ditta 4012")

    def test_avvisi_per_somiglianza(self):
        ris = self.converti()
        self.assertEqual(len(ris.avvisi), 4)                    # le 4 righe "let d-bis"
        self.assertTrue(all("somiglianza" in a.motivo for a in ris.avvisi))

    def test_quadratura(self):
        ris = self.converti()
        self.assertEqual(ris.totale_letto, Decimal("1990.02"))
        self.assertEqual(ris.totale_esportato, Decimal("1933.86"))
        self.assertEqual(ris.totale_scartato, Decimal("56.16"))
        self.assertTrue(ris.quadratura_ok)

    def test_con_fumagalli_25_identico_all_esempio(self):
        correzioni = Correzioni(dipendenti={"CF:FMGLSS92S52G273A": "25"})
        ris = self.converti(correzioni)
        self.assertEqual(ris.scarti, [])
        self.assertEqual(ris.nome_file_voci, "VOCI_4012_202609.txt")
        self.assertEqual(ris.file_voci(), ESEMPIO.read_bytes())    # byte per byte
        self.assertTrue(ris.quadratura_ok)

    def test_provider_sbagliato(self):
        # Un provider che si aspetta altre colonne deve dirlo, non produrre un file vuoto.
        self.conv.providers["Provider prova"] = {
            "intestazione": True, "dipendente": {"codice": "Codice Dipendente"},
            "trattamento": ["Articolo"], "importo": "Totale"}
        try:
            with self.assertRaises(FileNonCorrispondente) as ctx:
                self.conv.converti_file(self.contenuto, FILE_A.name, "Provider prova", "4012", "202609")
            self.assertIn("sembra del Provider A, non del Provider prova", str(ctx.exception))
        finally:
            del self.conv.providers["Provider prova"]


if __name__ == "__main__":
    unittest.main()

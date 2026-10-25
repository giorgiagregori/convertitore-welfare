"""Test del pezzo 1: la scrittura del record da 38 caratteri."""

import unittest
from decimal import Decimal
from pathlib import Path

from convertitore.tracciato import crea_record, controlla_periodo

ESEMPIO = Path(__file__).parent / "dati_kit" / "esempio_output" / "ESEMPIO_VOCI_4012_202609.txt"


class TestRecord(unittest.TestCase):

    def test_esempio_della_specifica(self):
        # L'esempio scritto nel testo del business case.
        record = crea_record("4012", "4", "371", Decimal("22.44"), "202609")
        self.assertEqual(record, "0040124     371 0000000000002244202609")

    def test_rifaccio_tutte_le_righe_del_file_di_esempio(self):
        # Leggo ogni riga del file di esempio, ne estraggo i campi
        # e la riscrivo con crea_record: deve tornare identica.
        righe = ESEMPIO.read_text(encoding="ascii").splitlines()
        self.assertEqual(len(righe), 19)
        for riga in righe:
            ditta = riga[0:6]
            dipendente = riga[6:12]
            voce = riga[12:16]
            importo = Decimal(int(riga[23:32])) / 100
            periodo = riga[32:38]
            self.assertEqual(crea_record(ditta, dipendente, voce, importo, periodo), riga)

    def test_lunghezza_sempre_38(self):
        record = crea_record("1", "123456", "9999", Decimal("9999999.99"), "202612")
        self.assertEqual(len(record), 38)

    def test_importo_moltiplicato_per_cento(self):
        # 25,73 deve diventare 000002573 (esempio della specifica).
        record = crea_record("4012", "4", "371", Decimal("25.73"), "202609")
        self.assertEqual(record[23:32], "000002573")

    def test_arrotondamento_mezzo_centesimo_per_eccesso(self):
        record = crea_record("4012", "4", "371", Decimal("22.445"), "202609")
        self.assertEqual(record[23:32], "000002245")

    def test_errori_sui_campi_troppo_lunghi_o_non_validi(self):
        with self.assertRaises(ValueError):
            crea_record("4012", "1234567", "371", Decimal("1"), "202609")   # dipendente > 6
        with self.assertRaises(ValueError):
            crea_record("4012", "4", "37100", Decimal("1"), "202609")       # voce > 4
        with self.assertRaises(ValueError):
            crea_record("4012", "4", "371", Decimal("-5"), "202609")        # importo negativo
        with self.assertRaises(ValueError):
            crea_record("4012", "4", "371", Decimal("10000000"), "202609")  # importo troppo grande
        with self.assertRaises(ValueError):
            crea_record("4012", "Ò", "371", Decimal("1"), "202609")         # non ASCII

    def test_periodo(self):
        self.assertEqual(controlla_periodo("202609"), "202609")
        for sbagliato in ["2026-09", "202613", "202600", "26609", "abcdef"]:
            with self.assertRaises(ValueError):
                controlla_periodo(sbagliato)


if __name__ == "__main__":
    unittest.main()

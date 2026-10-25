"""Test del pezzo 2: la lettura degli importi."""

import unittest
from decimal import Decimal

from convertitore.importi import ImportoNonLeggibile, leggi_importo


class TestImportiDelKit(unittest.TestCase):
    """Valori presi davvero dai file del kit, con il formato di ogni provider."""

    def test_provider_a_b_d_virgola_decimale(self):
        self.assertEqual(leggi_importo("151,00", "it"), Decimal("151.00"))
        self.assertEqual(leggi_importo("22,44", "it"), Decimal("22.44"))
        self.assertEqual(leggi_importo("3103,27", "it"), Decimal("3103.27"))
        self.assertEqual(leggi_importo("400,09", "it"), Decimal("400.09"))

    def test_provider_c_numeri_excel(self):
        self.assertEqual(leggi_importo(312.1), Decimal("312.1"))
        self.assertEqual(leggi_importo(566), Decimal("566"))
        self.assertEqual(leggi_importo(398.48), Decimal("398.48"))

    def test_provider_e_euro_e_punto_decimale(self):
        self.assertEqual(leggi_importo("€68.00", "en"), Decimal("68.00"))
        self.assertEqual(leggi_importo("€31.76", "en"), Decimal("31.76"))


class TestFormatiGenerali(unittest.TestCase):

    def test_migliaia(self):
        self.assertEqual(leggi_importo("1.234,56", "it"), Decimal("1234.56"))
        self.assertEqual(leggi_importo("1,234.56", "en"), Decimal("1234.56"))
        self.assertEqual(leggi_importo("1.234.567,00", "it"), Decimal("1234567.00"))
        self.assertEqual(leggi_importo("1 234,56", "it"), Decimal("1234.56"))

    def test_valuta_e_spazi(self):
        self.assertEqual(leggi_importo(" € 22,44 ", "it"), Decimal("22.44"))
        self.assertEqual(leggi_importo("22,44 EUR", "it"), Decimal("22.44"))
        self.assertEqual(leggi_importo("22,44 €", "it"), Decimal("22.44"))

    def test_negativi(self):
        self.assertEqual(leggi_importo("-12,00", "it"), Decimal("-12.00"))
        self.assertEqual(leggi_importo("12,00-", "it"), Decimal("-12.00"))
        self.assertEqual(leggi_importo("(12,00)", "it"), Decimal("-12.00"))
        self.assertEqual(leggi_importo(-5.5), Decimal("-5.5"))

    def test_formato_automatico(self):
        self.assertEqual(leggi_importo("151,00"), Decimal("151.00"))
        self.assertEqual(leggi_importo("€15.88"), Decimal("15.88"))
        self.assertEqual(leggi_importo("1.234,56"), Decimal("1234.56"))
        self.assertEqual(leggi_importo("1,234.56"), Decimal("1234.56"))
        self.assertEqual(leggi_importo("1.234.567"), Decimal("1234567"))
        self.assertEqual(leggi_importo("150"), Decimal("150"))

    def test_ambiguo_non_viene_indovinato(self):
        # "1.234" può essere 1234 (italiano) o 1,234 (inglese): in automatico
        # non si indovina, si segnala.
        with self.assertRaises(ImportoNonLeggibile):
            leggi_importo("1.234")
        with self.assertRaises(ImportoNonLeggibile):
            leggi_importo("1,234")
        # Con il formato dichiarato, invece, non c'è dubbio.
        self.assertEqual(leggi_importo("1.234", "it"), Decimal("1234"))
        self.assertEqual(leggi_importo("1,234", "en"), Decimal("1234"))

    def test_formato_dichiarato_sbagliato_non_legge_male(self):
        # Se un provider dichiarato "it" mandasse "15.88", NON deve diventare 1588:
        # va scartato, non letto come un importo cento volte più grande.
        with self.assertRaises(ImportoNonLeggibile):
            leggi_importo("15.88", "it")

    def test_valori_non_leggibili(self):
        for valore in [None, "", "-", "abc", "12,3,4", float("nan"), True]:
            with self.assertRaises(ImportoNonLeggibile):
                leggi_importo(valore, "it")


if __name__ == "__main__":
    unittest.main()

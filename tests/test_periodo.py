import unittest
from datetime import date

from convertitore.periodo import anni_disponibili, avviso_periodo, mese_precedente, periodo


class TestPeriodo(unittest.TestCase):
    def test_mese_precedente(self):
        self.assertEqual(mese_precedente(date(2026, 10, 25)), (2026, 9))
        self.assertEqual(mese_precedente(date(2027, 1, 5)), (2026, 12))

    def test_anni(self):
        self.assertEqual(anni_disponibili(date(2026, 10, 25)), [2025, 2026, 2027])

    def test_formato(self):
        self.assertEqual(periodo(2026, 9), "202609")

    def test_avvisi(self):
        oggi = date(2026, 10, 25)
        self.assertIsNone(avviso_periodo(2026, 9, oggi))     # mese precedente: caso normale
        self.assertIsNone(avviso_periodo(2026, 10, oggi))    # mese corrente
        self.assertIn("futuro", avviso_periodo(2026, 11, oggi))
        self.assertIn("3 mesi fa", avviso_periodo(2026, 7, oggi))
        self.assertIn("13 mesi fa", avviso_periodo(2025, 9, oggi))


if __name__ == "__main__":
    unittest.main()

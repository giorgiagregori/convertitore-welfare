"""Test del pezzo 4: dal trattamento fiscale alla voce payroll.

Tutti i trattamenti che compaiono nei file del kit, con la voce attesa.
"""

import tempfile
import unittest
from pathlib import Path

from convertitore.voci import TabellaVoci, chiave_normativa

TABELLA = Path(__file__).parent.parent / "config" / "Codici_Welfare_Voci_Payroll.csv"


class TestChiaveNormativa(unittest.TestCase):

    def test_scritture_diverse_dello_stesso_articolo(self):
        attese = {
            "Benefit art.51 c.2 let d-bis": ("51", "2", "d-bis"),
            "Art. 51 c.2 lett. d-bis": ("51", "2", "d-bis"),
            "Art.51 c. 2, d bis": ("51", "2", "d-bis"),
            "Art. 51 c2 lett f-bis O12": ("51", "2", "f-bis"),
            "Art. 51 c.2 lett. f-ter": ("51", "2", "f-ter"),
            "Benefit art.51 c.2 lett.f": ("51", "2", "f"),
            "TUIR - Art.51 c.2f (ex Art.100)": ("51", "2", "f"),
            "Consumo benefit ART.51 C.2 lett.H": ("51", "2", "h"),
            "art. 51 co. 2 lett. h": ("51", "2", "h"),
            "Art.51 c. 2, a": ("51", "2", "a"),
            "Art.51 c.3 [FCI Art.6 QUATER]": ("51", "3", None),
            "TUIR - Art.51 c.3 (Fringe)": ("51", "3", None),
            "Consumo benefit da art. 100 C.1": ("100", "1", None),
            "Art 100 [Iva 22%]": ("100", None, None),
            "X71180": (None, None, None),
            "F.di Previdenziali": (None, None, None),
        }
        for testo, chiave in attese.items():
            self.assertEqual(chiave_normativa(testo), chiave, testo)


class TestVociDelKit(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tab = TabellaVoci(TABELLA)

    def controlla(self, trattamento, sotto, codice, metodo):
        esito = self.tab.trova(trattamento, sotto)
        self.assertEqual((esito.codice, esito.metodo), (codice, metodo), (trattamento, sotto))

    def test_tabella_senza_incoerenze(self):
        self.assertEqual(self.tab.incoerenze(), [])

    def test_provider_a(self):
        self.controlla("Benefit art.51 c.2 let f-bis", None, "373", "esatto")
        self.controlla("Benefit art.51 c.3", None, "371", "esatto")
        self.controlla("Benefit art.51 c.2 lett.f", None, "370", "esatto")
        # Non è in tabella: l'esempio atteso la mette su 377.
        self.controlla("Benefit art.51 c.2 let d-bis", None, "377", "per somiglianza")

    def test_provider_b(self):
        self.controlla("X71180", None, "380", "esatto")
        self.controlla("X71203", None, "370", "esatto")
        self.controlla("X71173", None, "373", "esatto")

    def test_provider_b_codice_sconosciuto(self):
        esito = self.tab.trova("X71133")
        self.assertFalse(esito.trovata)
        self.assertEqual(esito.motivo, "Trattamento 'X71133' non presente in tabella")

    def test_provider_c(self):
        # Trattamento = colonna "Art." + " " + colonna "Rif. normativi";
        # sottocategoria = "Segno a cedolino".
        self.controlla("Art.51 c. 3", "Effettivo", "194", "esatto con sottocategoria")
        self.controlla("Art.51 c. 3", "Figurativo", "371", "per somiglianza")
        self.controlla("Art.51 c. 2, f bis", "Effettivo", "372", "esatto")
        self.controlla("Art.51 c. 2, a", "Figurativo", "380", "esatto")
        self.controlla("Art.51 c. 2, d bis", "Effettivo", "377", "esatto")
        self.controlla("Art.100 c. 1", "Figurativo", "370", "esatto")

    def test_provider_d(self):
        self.controlla("Art. 51 c.2 lett. f-bis", "Istruzione non universitaria", "373",
                       "esatto con sottocategoria")
        self.controlla("Art. 51 c.2 lett. f", "", "370", "esatto")
        self.controlla("Art. 51 c.3", "", "371", "esatto")
        self.controlla("Art. 51 c.2 lett. d-bis", "", "377", "esatto")

    def test_provider_d_asilo_nido_ambiguo(self):
        esito = self.tab.trova("Art. 51 c.2 lett. f-bis", "Asilo nido")
        self.assertFalse(esito.trovata)
        self.assertIn("ambiguo", esito.motivo)
        self.assertIn("voci possibili 372, 373", esito.motivo)

    def test_provider_e(self):
        self.controlla("Art.51 c.3 [FCI Art.2]", None, "371", "esatto")
        self.controlla("Art.51 c.3 [FCI Art.6 QUATER]", None, "371", "esatto")
        self.controlla("Art.100 [FCI Art.74]", None, "370", "esatto")
        self.controlla("Art. 51 c2 lett f-bis O12", None, "373", "esatto")
        self.controlla("Art 100 [Iva 22%]", None, "370", "per somiglianza")

    def test_spazi_e_maiuscole_non_contano(self):
        self.controlla("  ART. 51   C.3 ", None, "371", "esatto")

    def test_sottocategoria_nota_con_scrittura_diversa(self):
        # Trattamento scritto in un altro modo, ma sottocategoria presente in tabella.
        self.controlla("Art.51 c. 2, f bis", "Centri estivi ed invernali", "372", "esatto")
        self.controlla("art 51 c.2 lett f-bis", "Centri estivi ed invernali", "375", "per somiglianza")

    def test_avviso_per_somiglianza(self):
        esito = self.tab.trova("Benefit art.51 c.2 let d-bis")
        self.assertIn("abbinato per somiglianza (art. 51 c.2 lett. d-bis)", esito.avviso)

    def test_trattamento_mancante(self):
        self.assertFalse(self.tab.trova("").trovata)
        self.assertFalse(self.tab.trova(None).trovata)


class TestTabellaIncoerente(unittest.TestCase):

    def test_stessa_riga_con_due_voci(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        tmp.write("Trattamento,Codice,Sottocategoria\nArt. 51 c.3,371,\nArt. 51 c.3,999,\n")
        tmp.close()
        try:
            tab = TabellaVoci(tmp.name)
            self.assertEqual(len(tab.incoerenze()), 1)
            esito = tab.trova("Art. 51 c.3")
            self.assertFalse(esito.trovata)
            self.assertIn("Tabella incoerente", esito.motivo)
        finally:
            Path(tmp.name).unlink()


if __name__ == "__main__":
    unittest.main()

import glob
import unittest
from pathlib import Path

from convertitore.ditte import proponi_ditta
from convertitore.motore import Movimento
from convertitore.servizio import Convertitore

INPUT = Path(__file__).parent / "dati_kit" / "input"


class TestPropostaDitta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conv = Convertitore()

    def proponi(self, provider, schema):
        percorso = Path(glob.glob(str(INPUT / schema))[0])
        return self.conv.proponi_ditta(percorso.read_bytes(), percorso.name, provider)

    def test_ditte_dei_file_del_kit(self):
        casi = [("Provider A", "ProviderA_*", "4012"),
                ("Provider B", "ProviderB_*", "4027"),
                ("Provider C", "ProviderC_convertito_per_test.xlsx", "4041"),
                ("Provider D", "ProviderD_*", "4093"),
                ("Provider E", "ProviderE_*", "4131")]
        for provider, schema, attesa in casi:
            with self.subTest(provider=provider):
                proposta = self.proponi(provider, schema)
                self.assertEqual(proposta.ditta, attesa, proposta.motivo)
                self.assertGreater(proposta.riconosciuti * 2, proposta.dipendenti)

    def test_dipendente_contato_una_volta(self):
        movimenti = [Movimento(riga=i, importo="10", trattamento="x",
                               codice_fiscale="BLLGLC87B23B354L") for i in (2, 3, 4)]
        proposta = proponi_ditta(movimenti, self.conv.anagrafica)
        self.assertEqual((proposta.ditta, proposta.riconosciuti, proposta.dipendenti), ("4012", 1, 1))

    def test_nessun_dipendente_riconosciuto(self):
        movimenti = [Movimento(riga=2, importo="10", trattamento="x", codice_fiscale="XXXXXX00X00X000X")]
        proposta = proponi_ditta(movimenti, self.conv.anagrafica)
        self.assertIsNone(proposta.ditta)
        self.assertIn("Nessun dipendente", proposta.motivo)

    def test_meta_o_meno_non_basta(self):
        movimenti = [Movimento(riga=2, importo="10", trattamento="x", codice_fiscale="BLLGLC87B23B354L"),
                     Movimento(riga=3, importo="10", trattamento="x", codice_fiscale="XXXXXX00X00X000X")]
        proposta = proponi_ditta(movimenti, self.conv.anagrafica)
        self.assertIsNone(proposta.ditta)
        self.assertIn("1 dipendenti su 2", proposta.motivo)

    def test_pareggio_tra_ditte(self):
        # Il solo codice 12 esiste sia nella 4012 sia nella 4033: impossibile scegliere.
        movimenti = [Movimento(riga=2, importo="10", trattamento="x", codice="12")]
        proposta = proponi_ditta(movimenti, self.conv.anagrafica)
        self.assertIsNone(proposta.ditta)
        self.assertIn("stesso numero", proposta.motivo)

    def test_etichetta_con_ragione_sociale(self):
        self.assertEqual(self.conv.etichetta_ditta("4012"), "4012 – Alfa Servizi S.r.l.")
        self.assertEqual(self.conv.etichetta_ditta("4175"), "4175 – Tiglio Lab S.r.l.")


if __name__ == "__main__":
    unittest.main()

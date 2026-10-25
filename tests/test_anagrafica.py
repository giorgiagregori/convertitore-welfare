"""Test del pezzo 3: il riconoscimento del dipendente nella ditta scelta.

I casi sono presi dai file del kit, uno o più per provider.
"""

import tempfile
import unittest
from pathlib import Path

from convertitore.anagrafica import Anagrafica, chiave_nome

LISTA = Path(__file__).parent.parent / "config" / "Lista_Dipendenti.csv"


class TestAnagraficaPulita(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.anag = Anagrafica(LISTA)

    def test_duplicati_rimossi(self):
        self.assertEqual(self.anag.duplicati_rimossi, 25)
        self.assertEqual(len(self.anag.della_ditta("4012")), 11)

    def test_ditta_con_e_senza_zeri(self):
        self.assertEqual(len(self.anag.della_ditta("004012")), 11)

    def test_ditta_inesistente(self):
        esito = self.anag.riconosci("9999", codice_fiscale="BLLGLC87B23B354L")
        self.assertFalse(esito.trovato)
        self.assertIn("Ditta 9999 non presente", esito.motivo)


class TestProviderA_CodiceFiscale(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.anag = Anagrafica(LISTA)

    def test_trovato(self):
        esito = self.anag.riconosci("4012", codice_fiscale="BLLGLC87B23B354L")
        self.assertEqual((esito.codice, esito.metodo), ("4", "codice fiscale"))

    def test_fumagalli_non_presente(self):
        esito = self.anag.riconosci("4012", codice_fiscale="FMGLSS92S52G273A")
        self.assertFalse(esito.trovato)
        self.assertEqual(esito.motivo, "Dipendente non presente in anagrafica per la ditta 4012")

    def test_stessa_persona_in_due_ditte(self):
        # Noemi La Rocca: codice 10 in Alfa Servizi, 900 in Tiglio Lab.
        self.assertEqual(self.anag.riconosci("4012", codice_fiscale="LRCNMO75P50H501M").codice, "10")
        self.assertEqual(self.anag.riconosci("4175", codice_fiscale="LRCNMO75P50H501M").codice, "900")


class TestProviderB_SoloNome(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.anag = Anagrafica(LISTA)

    def test_nomi_in_ordine_diverso(self):
        # Nel file: cognome e nome in maiuscolo; in anagrafica: "Nome Cognome".
        casi = {
            ("RUSSO", "MARCO ANTONIO"): "15000",
            ("DELLA ROSA", "FABIO"): "15013",
            ("COLOMBO VILLA", "GIULIA ANNA"): "15026",
            ("VITALE", "SIMONE"): "15052",
            ("DE SANTIS", "LAURA"): "15065",
        }
        for nome, codice in casi.items():
            esito = self.anag.riconosci("4027", nome=nome)
            self.assertEqual((esito.codice, esito.metodo), (codice, "nome e cognome"), nome)

    def test_marini_sofia_non_presente(self):
        esito = self.anag.riconosci("4027", nome=("MARINI", "SOFIA"))
        self.assertFalse(esito.trovato)


class TestProviderC_CodiceFiscaleEMatricola(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.anag = Anagrafica(LISTA)

    def test_matricola_con_zeri_coerente(self):
        esito = self.anag.riconosci("4041", codice_fiscale="MRTMNL82P19B354B", codice="00000020")
        self.assertEqual((esito.codice, esito.metodo), ("20", "codice fiscale e codice"))

    def test_matricola_di_un_altro(self):
        # Codice fiscale di Martinelli (20) con la matricola di Dal Bello (17).
        esito = self.anag.riconosci("4041", codice_fiscale="MRTMNL82P19B354B", codice="00000017")
        self.assertFalse(esito.trovato)
        self.assertIn("indicano persone diverse", esito.motivo)


class TestProviderD_NomeECognome(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.anag = Anagrafica(LISTA)

    def test_matteo_martini_non_diventa_martini_sala(self):
        esito = self.anag.riconosci("4093", nome=("Matteo", "Martini"))
        self.assertFalse(esito.trovato)
        self.assertEqual(self.anag.riconosci("4093", nome=("Nicola", "Martini Sala")).codice, "36")

    def test_persona_in_due_ditte_si_prende_quella_giusta(self):
        # Laura Ferrari Galli: 16 in Larice Design, 902 in Tiglio Lab.
        self.assertEqual(self.anag.riconosci("4093", nome=("Laura", "Ferrari Galli")).codice, "16")

    def test_codice_fiscale_quando_il_beneficiario_e_il_dipendente(self):
        esito = self.anag.riconosci("4093", codice_fiscale="SNTGPP86M18E506I", nome=("Giuseppe", "Santoro"))
        self.assertEqual((esito.codice, esito.metodo), ("55", "codice fiscale"))


class TestProviderE_CodiceECodiceFiscale(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.anag = Anagrafica(LISTA)

    def test_codice_e_cf_coerenti(self):
        esito = self.anag.riconosci("4131", codice="15000", codice_fiscale="GRDMGR78B42A944X")
        self.assertEqual(esito.codice, "15000")

    def test_codice_letto_da_excel_come_numero(self):
        esito = self.anag.riconosci("4131", codice="15000.0", codice_fiscale="GRDMGR78B42A944X")
        self.assertEqual(esito.codice, "15000")

    def test_guerra_paolo(self):
        # Il codice 15052 esiste, ma nella ditta 4027 ed è di un'altra persona:
        # nella ditta 4131 Guerra Paolo non c'è.
        esito = self.anag.riconosci("4131", codice="15052", codice_fiscale="GRRPLA67E08L736B")
        self.assertFalse(esito.trovato)
        self.assertEqual(esito.motivo, "Dipendente non presente in anagrafica per la ditta 4131")


class TestCasiCostruiti(unittest.TestCase):
    """Casi che nel kit non ci sono ma possono capitare."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        self.tmp.write(
            "Codice Ditta,CodAnagraficoLav,Nome Dipendente,CodiceFiscale,RagioneSociale\n"
            "1,10,Rossi Mario,RSSMRA80A01H501A,Prova\n"
            "1,11,Mario Rossi,RSSMRA85B02F205B,Prova\n"
            "1,12,Niccolò D'Amico,DMCNCC90C03L219C,Prova\n"
            "2,50,Bianchi Anna,BNCNNA70D44A944D,Altra\n"
        )
        self.tmp.close()
        self.anag = Anagrafica(self.tmp.name)

    def tearDown(self):
        Path(self.tmp.name).unlink()

    def test_omonimi(self):
        esito = self.anag.riconosci("1", nome=("ROSSI", "MARIO"))
        self.assertFalse(esito.trovato)
        self.assertIn("Più dipendenti con lo stesso nome", esito.motivo)
        self.assertIn("10, 11", esito.motivo)

    def test_omonimi_risolti_dal_codice_fiscale(self):
        esito = self.anag.riconosci("1", codice_fiscale="RSSMRA85B02F205B", nome=("ROSSI", "MARIO"))
        self.assertEqual(esito.codice, "11")

    def test_accenti_e_apostrofi(self):
        self.assertEqual(self.anag.riconosci("1", nome=("D'AMICO", "NICCOLO")).codice, "12")

    def test_suggerisce_la_ditta_giusta(self):
        esito = self.anag.riconosci("1", nome=("BIANCHI", "ANNA"))
        self.assertFalse(esito.trovato)
        self.assertIn("presente in altra ditta (ditta 2 codice 50)", esito.cosa_fare)

    def test_chiave_nome(self):
        self.assertEqual(chiave_nome("DELLA ROSA", "FABIO"), chiave_nome("Fabio Della Rosa"))


if __name__ == "__main__":
    unittest.main()

"""Test del pezzo 5: somma, ordinamento, file VOCI, file SCARTI, quadratura, correzioni.

I movimenti sono costruiti a mano con dati del Provider A (ditta 4012).
"""

import csv
import io
import unittest
from decimal import Decimal
from pathlib import Path

from convertitore.anagrafica import Anagrafica
from convertitore.motore import Correzioni, Movimento, converti
from convertitore.voci import TabellaVoci

CONFIG = Path(__file__).parent.parent / "config"
ANAG = Anagrafica(CONFIG / "Lista_Dipendenti.csv")
TAB = TabellaVoci(CONFIG / "Codici_Welfare_Voci_Payroll.csv")

BELLINI = "BLLGLC87B23B354L"     # codice 4
NOEMI = "LRCNMO75P50H501M"       # codice 10
DE_ROSA = "DRSMNL80M02L219M"     # codice 41
FUMAGALLI = "FMGLSS92S52G273A"   # non in anagrafica


def mov(riga, cf, trattamento, importo):
    return Movimento(riga=riga, importo=importo, trattamento=trattamento, codice_fiscale=cf)


def conv(movimenti, correzioni=None):
    return converti(movimenti, "4012", "202609", ANAG, TAB, "it", correzioni, provider="Provider A")


class TestSommaEOrdine(unittest.TestCase):

    def test_somma_per_dipendente_e_voce(self):
        # De Rosa: due rimborsi f-bis (141 + 177) -> un solo record da 318.
        ris = conv([mov(5, DE_ROSA, "Benefit art.51 c.2 let f-bis", "141,00"),
                    mov(6, DE_ROSA, "Benefit art.51 c.2 let f-bis", "177,00")])
        self.assertEqual(ris.record, ["00401241    373 0000000000031800202609"])

    def test_ordine_numerico_dei_dipendenti(self):
        # 10 deve venire dopo 4 (in ordine alfabetico "10" verrebbe prima di "4").
        ris = conv([mov(5, NOEMI, "Benefit art.51 c.3", "9,00"),
                    mov(6, BELLINI, "Benefit art.51 c.3", "22,44"),
                    mov(7, BELLINI, "Benefit art.51 c.2 lett.f", "108,00")])
        self.assertEqual([r[6:16] for r in ris.record], ["4     370 ", "4     371 ", "10    371 "])

    def test_file_voci(self):
        ris = conv([mov(5, BELLINI, "Benefit art.51 c.3", "22,44")])
        self.assertEqual(ris.nome_file_voci, "VOCI_4012_202609.txt")
        self.assertEqual(ris.file_voci(), b"0040124     371 0000000000002244202609\r\n")


class TestScartiEQuadratura(unittest.TestCase):

    def test_dipendente_non_trovato_va_negli_scarti(self):
        ris = conv([mov(5, BELLINI, "Benefit art.51 c.3", "22,44"),
                    mov(8, FUMAGALLI, "Benefit art.51 c.3", "56,16")])
        self.assertEqual(len(ris.record), 1)
        self.assertEqual(len(ris.scarti), 1)
        scarto = ris.scarti[0]
        self.assertEqual((scarto.riga, scarto.importo), (8, "56,16"))
        self.assertEqual(scarto.motivo, "Dipendente non presente in anagrafica per la ditta 4012")
        # Quadratura: 78,60 letti = 22,44 esportati + 56,16 scartati.
        self.assertEqual(ris.totale_letto, Decimal("78.60"))
        self.assertEqual(ris.totale_esportato, Decimal("22.44"))
        self.assertEqual(ris.totale_scartato, Decimal("56.16"))
        self.assertTrue(ris.quadratura_ok)

    def test_trattamento_non_in_tabella(self):
        ris = conv([mov(5, BELLINI, "X71133", "50,00")])
        self.assertEqual(ris.record, [])
        self.assertIn("non presente in tabella", ris.scarti[0].motivo)

    def test_due_problemi_sulla_stessa_riga_una_sola_riga_di_scarto(self):
        ris = conv([mov(5, FUMAGALLI, "X71133", "50,00")])
        self.assertEqual(len(ris.scarti), 1)
        self.assertIn("non presente in anagrafica", ris.scarti[0].motivo)
        self.assertIn("non presente in tabella", ris.scarti[0].motivo)

    def test_importo_non_leggibile(self):
        ris = conv([mov(5, BELLINI, "Benefit art.51 c.3", "abc")])
        self.assertEqual(ris.importi_non_leggibili, 1)
        self.assertIn("Importo non leggibile", ris.scarti[0].motivo)
        self.assertTrue(ris.quadratura_ok)

    def test_totale_negativo_scartato(self):
        ris = conv([mov(5, BELLINI, "Benefit art.51 c.3", "10,00"),
                    mov(6, BELLINI, "Benefit art.51 c.3", "-30,00")])
        self.assertEqual(ris.record, [])
        self.assertEqual(len(ris.scarti), 2)
        self.assertIn("Totale negativo", ris.scarti[0].motivo)
        self.assertTrue(ris.quadratura_ok)

    def test_totale_zero_non_esportato(self):
        ris = conv([mov(5, BELLINI, "Benefit art.51 c.3", "30,00"),
                    mov(6, BELLINI, "Benefit art.51 c.3", "-30,00")])
        self.assertEqual(ris.record, [])
        self.assertEqual(ris.scarti, [])
        self.assertIn("totale zero", ris.avvisi_generali[0])

    def test_storno_parziale_si_somma(self):
        ris = conv([mov(5, BELLINI, "Benefit art.51 c.3", "30,00"),
                    mov(6, BELLINI, "Benefit art.51 c.3", "-7,56")])
        self.assertEqual(ris.record, ["0040124     371 0000000000002244202609"])

    def test_avviso_per_somiglianza(self):
        ris = conv([mov(5, NOEMI, "Benefit art.51 c.2 let d-bis", "24,00")])
        self.assertEqual(ris.record, ["00401210    377 0000000000002400202609"])
        self.assertEqual(len(ris.avvisi), 1)
        self.assertIn("somiglianza", ris.avvisi[0].motivo)

    def test_file_scarti_csv(self):
        ris = conv([mov(8, FUMAGALLI, "Benefit art.51 c.3", "56,16")])
        self.assertEqual(ris.nome_file_scarti, "SCARTI_ProviderA_4012_202609.csv")
        contenuto = ris.file_scarti()
        self.assertTrue(contenuto.startswith(b"\xef\xbb\xbf"))   # BOM per Excel
        righe = list(csv.reader(io.StringIO(contenuto.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(righe[0][:3], ["Tipo", "Riga file", "Dipendente"])
        self.assertEqual(righe[1][0:2], ["SCARTO", "8"])
        self.assertEqual(righe[1][5], "56,16")

    def test_avviso_ditta_sbagliata(self):
        # Movimenti di Alfa Servizi convertiti per errore sulla ditta 4027.
        ris = converti([mov(5, BELLINI, "Benefit art.51 c.3", "22,44"),
                        mov(6, NOEMI, "Benefit art.51 c.3", "9,00")],
                       "4027", "202609", ANAG, TAB, "it")
        self.assertIn("hai scelto la ditta giusta?", ris.avvisi_generali[0])


class TestCorrezioni(unittest.TestCase):

    def test_elenco_da_correggere(self):
        ris = conv([mov(8, FUMAGALLI, "Benefit art.51 c.3", "56,16"),
                    mov(9, FUMAGALLI, "Benefit art.51 c.3", "10,00")])
        self.assertEqual(list(ris.dipendenti_da_correggere), ["CF:" + FUMAGALLI])
        da_corr = ris.dipendenti_da_correggere["CF:" + FUMAGALLI]
        self.assertEqual((da_corr.righe, da_corr.totale), (2, Decimal("66.16")))

    def test_codice_dipendente_inserito_a_mano(self):
        correzioni = Correzioni(dipendenti={"CF:" + FUMAGALLI: "25"})
        ris = conv([mov(8, FUMAGALLI, "Benefit art.51 c.3", "56,16")], correzioni)
        self.assertEqual(ris.record, ["00401225    371 0000000000005616202609"])
        self.assertEqual(ris.scarti, [])
        self.assertIn("inserito a mano", ris.avvisi[0].motivo)

    def test_voce_scelta_a_mano(self):
        movimento = mov(5, BELLINI, "X71133", "50,00")
        correzioni = Correzioni(voci={movimento.chiave_trattamento(): "380"})
        ris = conv([movimento], correzioni)
        self.assertEqual(ris.record, ["0040124     380 0000000000005000202609"])
        self.assertIn("scelta a mano", ris.avvisi[0].motivo)

    def test_codice_a_mano_non_valido(self):
        correzioni = Correzioni(dipendenti={"CF:" + FUMAGALLI: "1234567"})
        with self.assertRaises(ValueError):
            conv([mov(8, FUMAGALLI, "Benefit art.51 c.3", "56,16")], correzioni)


class TestInputGenerali(unittest.TestCase):

    def test_ditta_e_periodo_non_validi(self):
        for ditta, periodo in [("40A2", "202609"), ("1234567", "202609"), ("4012", "202613")]:
            with self.assertRaises(ValueError):
                converti([], ditta, periodo, ANAG, TAB)


if __name__ == "__main__":
    unittest.main()

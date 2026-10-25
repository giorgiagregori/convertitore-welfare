"""Caricamento massivo: stesso risultato della conversione singola, file per file."""

import glob
import io
import unittest
import zipfile
from pathlib import Path

from convertitore.massivo import (BLOCCATO, Scelta, analizza_file, analizza_lotto,
                                  converti_lotto)
from convertitore.motore import Correzioni
from convertitore.servizio import Convertitore

from comune import CARTELLA, FILE_C, INPUT, SENZA_XLRD, XLRD_DISPONIBILE

FILE_KIT = ["ProviderA_*", "ProviderB_*", FILE_C, "ProviderD_*", "ProviderE_*"]

# Un piccolo file "del Provider D" inventato per la ditta 4012: Bellini (codice 4)
# compare anche nel file del Provider A, quindi i due file vanno uniti.
FILE_D_4012 = (
    "Nome dipendente;Cognome dipendente;Nome fruitore benefit;Cognome fruitore benefit;"
    "Parentela fruitore benefit;Codice fiscale fruitore benefit;Riferimento al TUIR;"
    "Tipologia di servizio;Valore\r\n"
    "Gian Luca;Bellini;Gian Luca;Bellini;Me stesso;BLLGLC87B23B354L;Art. 51 c.3;;10,00\r\n"
).encode("utf-8")


def leggi(schema):
    percorso = Path(glob.glob(str(INPUT / schema))[0])
    return percorso.name, percorso.read_bytes()


@unittest.skipUnless(XLRD_DISPONIBILE, SENZA_XLRD)
class TestMassivo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conv = Convertitore()
        cls.files = [leggi(s) for s in FILE_KIT]

    def scelte(self, analisi):
        return [Scelta(a.nome, a.contenuto, a.provider, a.ditta_proposta)
                for a in analisi if a.stato != BLOCCATO]

    def test_riconosce_provider_e_ditta(self):
        attesi = [("Provider A", "4012"), ("Provider B", "4027"), ("Provider C", "4041"),
                  ("Provider D", "4093"), ("Provider E", "4131")]
        analisi = analizza_lotto(self.conv, self.files)
        self.assertEqual([(a.provider, a.ditta_proposta) for a in analisi], attesi)

    def test_stesso_risultato_della_conversione_singola(self):
        lotto = converti_lotto(self.conv, self.scelte(analizza_lotto(self.conv, self.files)), "202609")
        for (nome, contenuto), a in zip(self.files, analizza_lotto(self.conv, self.files)):
            singolo = self.conv.converti_file(contenuto, nome, a.provider, a.ditta_proposta, "202609")
            with self.subTest(file=nome):
                self.assertEqual(lotto.per_ditta[a.ditta_proposta].file_voci(), singolo.file_voci())
                self.assertEqual(lotto.conta("SCARTO", nome), len(singolo.scarti))
        self.assertTrue(lotto.quadratura_ok)
        self.assertEqual(str(lotto.totale_letto), "19552.54")

    def test_zip_con_tutti_i_file(self):
        lotto = converti_lotto(self.conv, self.scelte(analizza_lotto(self.conv, self.files)), "202609")
        nomi = zipfile.ZipFile(io.BytesIO(lotto.file_zip())).namelist()
        self.assertEqual(sorted(nomi), ["SCARTI_202609.csv", "VOCI_4012_202609.txt",
                                        "VOCI_4027_202609.txt", "VOCI_4041_202609.txt",
                                        "VOCI_4093_202609.txt", "VOCI_4131_202609.txt"])
        intestazione = lotto.file_scarti().decode("utf-8-sig").splitlines()[0]
        self.assertTrue(intestazione.startswith("File;Provider;Ditta;Tipo"))

    def test_file_caricato_due_volte(self):
        analisi = analizza_lotto(self.conv, [self.files[0], ("copia.xlsx", self.files[0][1])])
        self.assertEqual(analisi[1].stato, BLOCCATO)
        self.assertIn("caricato due volte", analisi[1].errore)

    def test_file_di_nessun_provider(self):
        analisi = analizza_file(self.conv, "altro.csv", b"a;b;c\n1;2;3\n")
        self.assertEqual(analisi.stato, BLOCCATO)
        self.assertIn("nessun provider", analisi.errore)

    def test_due_file_stessa_ditta_un_solo_voci(self):
        nome_a, contenuto_a = self.files[0]
        scelte = [Scelta(nome_a, contenuto_a, "Provider A", "4012"),
                  Scelta("tracciato_extra.csv", FILE_D_4012, "Provider D", "4012")]
        lotto = converti_lotto(self.conv, scelte, "202609")
        self.assertEqual(list(lotto.per_ditta), ["4012"])
        unito = lotto.per_ditta["4012"]
        solo_a = self.conv.converti_file(contenuto_a, nome_a, "Provider A", "4012", "202609")
        solo_d = self.conv.converti_file(FILE_D_4012, "tracciato_extra.csv", "Provider D", "4012", "202609")

        def importi(risultato):
            return {r[:16]: int(r[23:32]) for r in risultato.record}

        attesi = importi(solo_a)
        for chiave, centesimi in importi(solo_d).items():
            attesi[chiave] = attesi.get(chiave, 0) + centesimi
        self.assertEqual(importi(unito), attesi)
        self.assertEqual(unito.totale_letto, solo_a.totale_letto + solo_d.totale_letto)
        self.assertTrue(unito.quadratura_ok)
        self.assertEqual(unito.provider, "Provider A + Provider D")
        self.assertEqual(lotto.file_per_ditta["4012"], [nome_a, "tracciato_extra.csv"])

    def test_correzioni_per_ditta(self):
        analisi = analizza_lotto(self.conv, self.files)
        lotto = converti_lotto(self.conv, self.scelte(analisi), "202609",
                               {"4012": Correzioni(dipendenti={"CF:FMGLSS92S52G273A": "25"})})
        esempio = (CARTELLA / "esempio_output" / "ESEMPIO_VOCI_4012_202609.txt").read_bytes()
        self.assertEqual(lotto.per_ditta["4012"].file_voci(), esempio)
        self.assertEqual(len(lotto.per_ditta["4027"].scarti), 4)   # le altre ditte non cambiano

    def test_provider_sbagliato_scelto_a_mano(self):
        nome, contenuto = self.files[0]
        analisi = analizza_file(self.conv, nome, contenuto, provider="Provider E")
        self.assertEqual(analisi.stato, BLOCCATO)
        self.assertIn("sembra del Provider A", analisi.errore)


if __name__ == "__main__":
    unittest.main()

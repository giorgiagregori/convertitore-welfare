"""Uso da terminale, utile per provare il motore senza interfaccia.

Esempi:
    python converti.py "Provider A" 4012 202609 tests/dati_kit/input/ProviderA_welfare_report_2026-09-01_2026-09-30.xlsx
    python converti.py "Provider A" 4012 202609 <file> --dipendente CF:FMGLSS92S52G273A=25

Scrive nella cartella corrente il file VOCI e, se ci sono scarti o avvisi, il file SCARTI.
"""

import argparse
from pathlib import Path

from convertitore.motore import Correzioni
from convertitore.servizio import Convertitore


def main():
    parser = argparse.ArgumentParser(description="Convertitore welfare universale")
    parser.add_argument("provider")
    parser.add_argument("ditta")
    parser.add_argument("periodo", help="AAAAMM")
    parser.add_argument("file")
    parser.add_argument("--dipendente", action="append", default=[],
                        help="correzione a mano: CHIAVE=CODICE (es. CF:FMGLSS92S52G273A=25)")
    args = parser.parse_args()

    correzioni = Correzioni()
    for voce in args.dipendente:
        chiave, codice = voce.rsplit("=", 1)
        correzioni.dipendenti[chiave] = codice

    percorso = Path(args.file)
    ris = Convertitore().converti_file(percorso.read_bytes(), percorso.name, args.provider,
                                       args.ditta, args.periodo, correzioni)

    Path(ris.nome_file_voci).write_bytes(ris.file_voci())
    print(f"Righe lette: {ris.righe_lette} · record scritti: {len(ris.record)} · "
          f"scarti: {len(ris.scarti)} · avvisi: {len(ris.avvisi)}")
    print(f"Quadratura: letto {ris.totale_letto} = esportato {ris.totale_esportato} "
          f"+ scartato {ris.totale_scartato} -> {'OK' if ris.quadratura_ok else 'NON TORNA'}")
    for avviso in ris.avvisi_generali:
        print("ATTENZIONE:", avviso)
    print("Scritto", ris.nome_file_voci)
    if ris.segnalazioni:
        Path(ris.nome_file_scarti).write_bytes(ris.file_scarti())
        print("Scritto", ris.nome_file_scarti)
    for chiave, d in ris.dipendenti_da_correggere.items():
        print(f"Da correggere: {d.descrizione} ({d.righe} righe, {d.totale} €) -> --dipendente {chiave}=CODICE")


if __name__ == "__main__":
    main()

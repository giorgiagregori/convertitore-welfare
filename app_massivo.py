"""Convertitore welfare - caricamento massivo (Streamlit).

Evoluzione dell'app singola (app.py). Si scelgono il mese (uguale per tutti i
file) e i provider, si caricano insieme tutti i report, l'app riconosce provider
e ditta di ogni file e mostra un riepilogo; l'operatore sceglie quali ditte
convertire e converte tutto in una volta. Esce uno zip con un file VOCI per ditta
e un unico file SCARTI. Il motore e i controlli sono gli stessi dell'app singola.

Avvio sul proprio computer:
    pip install -r requirements.txt
    streamlit run app_massivo.py
"""

from datetime import date

import streamlit as st

from convertitore.massivo import (BLOCCATO, DA_GUARDARE, PRONTO, Scelta, analizza_file,
                                  converti_lotto, impronta)
from convertitore.motore import Correzioni
from convertitore.periodo import MESI, anni_disponibili, avviso_periodo, mese_precedente, periodo
from convertitore.servizio import Convertitore

st.set_page_config(page_title="Convertitore welfare - massivo", page_icon="🗂️", layout="wide")

ICONA = {PRONTO: "✅", DA_GUARDARE: "⚠️", BLOCCATO: "❌"}

# Etichette dei menu a scelta multipla (provider e ditte) in blu chiaro invece
# del rosso predefinito di Streamlit.
st.markdown("""
<style>
span[data-baseweb="tag"] {
    background-color: #DCEBFA !important;
    color: #1A4E8A !important;
}
span[data-baseweb="tag"] svg { fill: #1A4E8A !important; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def carica_convertitore() -> Convertitore:
    return Convertitore()


def euro(valore) -> str:
    testo = f"{valore:,.2f}"
    return testo.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


conv = carica_convertitore()
stato = st.session_state
stato.setdefault("analisi", {})          # (impronta, provider o None) -> FileAnalizzato


def analisi_di(nome, contenuto, provider=None):
    """Analisi del file, calcolata una volta sola per file e provider."""
    chiave = (impronta(contenuto), provider)
    if chiave not in stato["analisi"]:
        stato["analisi"][chiave] = analizza_file(conv, nome, contenuto, provider)
    return stato["analisi"][chiave]


# ------------------------------------------------------------------ intestazione
st.title("Convertitore welfare · caricamento massivo")
st.write("Scegli il mese e i provider, carica tutti i report insieme e decidi quali ditte "
         "convertire: esce un file VOCI per ditta e un unico file SCARTI.")
st.caption("I file caricati vengono elaborati in memoria e non vengono salvati.")

# ------------------------------------------------------------------ 1. filtri
st.subheader("1. Cosa converti")
oggi = date.today()
anno_proposto, mese_proposto = mese_precedente(oggi)
anni = anni_disponibili(oggi)
col_mese, col_anno = st.columns([2, 1])
mese = col_mese.selectbox("Mese del cedolino", range(1, 13), index=mese_proposto - 1,
                          format_func=lambda m: MESI[m - 1])
anno = col_anno.selectbox("Anno", anni, index=anni.index(anno_proposto))
periodo_scelto = periodo(anno, mese)
avviso = avviso_periodo(anno, mese, oggi)
if avviso:
    st.warning(avviso)
st.caption(f"Il periodo {MESI[mese - 1]} {anno} vale per tutti i file caricati.")
# Menu a tendina a scelta multipla, vuoto all'inizio: con tutti i provider già
# selezionati la tendina risulterebbe vuota e sembrerebbe di non poter scegliere.
tutti = st.checkbox("Tutti i provider", value=False)
providers_scelti = st.multiselect(
    "Provider (puoi sceglierne più di uno)", list(conv.providers),
    default=list(conv.providers) if tutti else [], disabled=tutti,
    placeholder="Apri il menu e scegli uno o più provider", key=f"providers_{tutti}")

# ------------------------------------------------------------------ 2. file
st.subheader("2. Carica i file")
caricati = st.file_uploader("Report dei provider: selezionali tutti insieme",
                            type=["xlsx", "xls", "csv"], accept_multiple_files=True)
if not providers_scelti:
    st.info("Scegli almeno un provider.")
    st.stop()
if not caricati:
    st.info("Carica i file per vedere il riepilogo.")
    st.stop()

# Ogni file viene riconosciuto da solo: provider dalle colonne, ditta dai
# dipendenti (gli stessi controlli dell'app singola). L'operatore non deve
# scegliere nulla file per file: vede il riepilogo e decide quali ditte convertire.
righe_riepilogo, validi, visti = [], [], {}
for file in caricati:
    contenuto = file.getvalue()
    chiave_file = impronta(contenuto)
    if chiave_file in visti:
        righe_riepilogo.append((BLOCCATO, file.name, "", "", "",
                                f"Stesso contenuto di '{visti[chiave_file]}': caricato due volte"))
        continue
    visti[chiave_file] = file.name
    a = analisi_di(file.name, contenuto)
    if a.stato == BLOCCATO:
        righe_riepilogo.append((BLOCCATO, file.name, a.provider or "", "", "", a.errore))
        continue
    if a.provider not in providers_scelti:
        righe_riepilogo.append((BLOCCATO, file.name, a.provider, "", "",
                                f"{a.provider} non è tra i provider scelti"))
        continue
    if not a.ditta_proposta:
        righe_riepilogo.append((BLOCCATO, file.name, a.provider, "", "",
                                a.proposta.motivo + " Convertilo con l'app singola, scegliendo la ditta."))
        continue
    riconosciuti = f"{a.proposta.riconosciuti} su {a.proposta.dipendenti}"
    righe_riepilogo.append((a.stato, file.name, a.provider, conv.etichetta_ditta(a.ditta_proposta),
                            riconosciuti, " · ".join(a.avvisi)))
    validi.append(a)

st.subheader("3. Riepilogo dei file")
st.dataframe(
    [{"Stato": ICONA[stato_f], "File": nome, "Provider": prov, "Ditta": ditta_f,
      "Dipendenti riconosciuti": ric, "Note": note}
     for stato_f, nome, prov, ditta_f, ric, note in righe_riepilogo],
    hide_index=True, use_container_width=True)
bloccati = sum(1 for r in righe_riepilogo if r[0] == BLOCCATO)
if bloccati:
    st.warning(f"{bloccati} file non verranno convertiti: il motivo è nella colonna Note.")

if not validi:
    st.stop()

# ------------------------------------------------------------------ 4. ditte
st.subheader("4. Ditte da convertire")
file_per_ditta = {}
for a in validi:
    file_per_ditta.setdefault(a.ditta_proposta, []).append(a)
ordine = sorted(file_per_ditta, key=lambda d: (len(d), d))
ditte_scelte = st.multiselect(
    "Ditte trovate nei file", ordine, default=ordine,
    format_func=lambda d: f"{conv.etichetta_ditta(d)} ({len(file_per_ditta[d])} file)",
    placeholder="Scegli le ditte")
for d in ditte_scelte:
    if len(file_per_ditta[d]) > 1:
        st.info(f"La ditta {conv.etichetta_ditta(d)} riceve {len(file_per_ditta[d])} file "
                f"({', '.join(a.nome for a in file_per_ditta[d])}): verranno uniti in un solo "
                f"VOCI_{d}_{periodo_scelto}.txt.")

scelte = [Scelta(a.nome, a.contenuto, a.provider, a.ditta_proposta)
          for d in ditte_scelte for a in file_per_ditta[d]]
gruppi = {d: file_per_ditta[d] for d in ditte_scelte}

firma = (periodo_scelto, tuple((impronta(s.contenuto), s.provider, s.ditta) for s in scelte))
if stato.get("firma") != firma:
    stato.pop("lotto", None)
    stato["correzioni"] = {}
    stato["firma"] = None


def esegui():
    stato["lotto"] = converti_lotto(conv, scelte, periodo_scelto, stato["correzioni"])
    stato["firma"] = firma


st.write(f"**{len(scelte)} file da convertire** su {len(caricati)} caricati, "
         f"per {len(gruppi)} ditte, periodo {periodo_scelto}.")
if st.button("Converti tutto", type="primary", disabled=not scelte, use_container_width=True):
    stato["correzioni"] = {}
    esegui()

lotto = stato.get("lotto")
if not lotto:
    st.stop()

# ------------------------------------------------------------------ 3. esito
st.divider()
st.subheader("5. Esito")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Ditte", len(lotto.per_ditta))
c2.metric("Record prodotti", lotto.record)
c3.metric("Righe scartate", lotto.conta("SCARTO"))
c4.metric("Avvisi", lotto.conta("AVVISO"))
simbolo = "✅" if lotto.quadratura_ok else "❌"
st.write(f"{simbolo} **Quadratura:** totale letto {euro(lotto.totale_letto)} = esportato "
         f"{euro(lotto.totale_esportato)} + scartato {euro(lotto.totale_scartato)}")

for nome, motivo in lotto.errori:
    st.error(f"{nome}: {motivo}")

st.dataframe(
    [{"Ditta": conv.etichetta_ditta(d), "File": ", ".join(lotto.file_per_ditta[d]),
      "Provider": r.provider, "Record": len(r.record), "Scarti": len(r.scarti),
      "Avvisi": len(r.avvisi), "Letto": euro(r.totale_letto), "Esportato": euro(r.totale_esportato),
      "Scartato": euro(r.totale_scartato), "Quadratura": "✅" if r.quadratura_ok else "❌"}
     for d, r in lotto.per_ditta.items()],
    hide_index=True, use_container_width=True)

for d, r in lotto.per_ditta.items():
    for testo in r.avvisi_generali:
        st.warning(f"Ditta {d}: {testo}")

if lotto.conta("SCARTO"):
    st.warning(f"**{lotto.conta('SCARTO')} righe scartate per {euro(lotto.totale_scartato)}.** "
               "Non sono nei file VOCI: trovi il motivo nel file SCARTI. "
               "Se vuoi, puoi correggerle qui sotto e riconvertire.")

# ------------------------------------------------------------------ 4. correzioni
da_correggere = {d: r for d, r in lotto.per_ditta.items()
                 if r.dipendenti_da_correggere or r.voci_da_correggere}
if da_correggere:
    st.divider()
    st.subheader("6. Correzioni (facoltative)")
    st.caption("Solo le ditte con righe scartate. Lascia vuoto ciò che non vuoi correggere.")
    voci_note = sorted({r[1] for r in conv.tabella.righe}, key=lambda v: (len(v), v))
    nuove = {d: Correzioni(dict(c.dipendenti), dict(c.voci)) for d, c in stato["correzioni"].items()}
    for d, r in da_correggere.items():
        corr = nuove.setdefault(d, Correzioni())
        with st.expander(f"{conv.etichetta_ditta(d)} · {len(r.dipendenti_da_correggere)} dipendenti "
                         f"e {len(r.voci_da_correggere)} trattamenti da correggere"):
            for i, (chiave, x) in enumerate(r.dipendenti_da_correggere.items()):
                codice = st.text_input(f"{x.descrizione} — {x.righe} righe, {euro(x.totale)}",
                                       key=f"dip_{d}_{i}_{chiave}", help=x.motivo,
                                       placeholder="Codice dipendente nel gestionale")
                if codice.strip():
                    corr.dipendenti[chiave] = codice.strip()
            for i, (chiave, x) in enumerate(r.voci_da_correggere.items()):
                scelta = st.selectbox(f"{x.descrizione} — {x.righe} righe, {euro(x.totale)}",
                                      ["(lascia negli scarti)"] + voci_note,
                                      key=f"voce_{d}_{i}", help=x.motivo)
                if scelta != "(lascia negli scarti)":
                    corr.voci[chiave] = scelta
    if st.button("Riconverti con le correzioni", use_container_width=True):
        stato["correzioni"] = nuove
        try:
            esegui()
        except ValueError as errore:
            st.error(str(errore))
        else:
            st.rerun()

# ------------------------------------------------------------------ 5. download
st.divider()
st.subheader("7. Scarica i file")
d1, d2 = st.columns(2)
d1.download_button(f"Scarica tutto (zip: {sum(1 for r in lotto.per_ditta.values() if r.record)} "
                   "file VOCI + SCARTI)", lotto.file_zip(), file_name=lotto.nome_zip,
                   mime="application/zip", type="primary", use_container_width=True)
d2.download_button("Scarica solo SCARTI", lotto.file_scarti(), file_name=lotto.nome_file_scarti,
                   mime="text/csv", use_container_width=True)

with st.expander("File VOCI uno per uno"):
    for d, r in lotto.per_ditta.items():
        st.download_button(f"{r.nome_file_voci} · {len(r.record)} record", r.file_voci(),
                           file_name=r.nome_file_voci, mime="text/plain", key=f"voci_{d}",
                           disabled=not r.record)

if lotto.segnalazioni:
    with st.expander("Scarti e avvisi"):
        st.dataframe(
            [{"File": s.origine, "Ditta": d, "Tipo": s.tipo, "Riga": s.riga,
              "Dipendente": s.dipendente, "Trattamento": s.trattamento, "Importo": s.importo,
              "Motivo": s.motivo, "Cosa fare": s.cosa_fare} for d, s in lotto.segnalazioni],
            hide_index=True, use_container_width=True)

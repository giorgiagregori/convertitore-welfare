"""Interfaccia web del convertitore welfare (Streamlit).

Avvio sul proprio computer:
    pip install -r requirements.txt
    streamlit run app.py

Flusso guidato: provider → file → ditta (proposta dai dipendenti del file) → mese e anno → Converti → esito
(quadratura, avvisi, anomalie con correzione facoltativa) → download.
I file caricati restano in memoria per la sola conversione: nulla viene salvato.
"""

import hashlib
from datetime import date

import streamlit as st

from convertitore.configurazione import FileNonCorrispondente
from convertitore.lettura import FileNonLeggibile
from convertitore.motore import Correzioni
from convertitore.periodo import (MESI, anni_disponibili, avviso_periodo,
                                  mese_precedente, periodo)
from convertitore.servizio import Convertitore

st.set_page_config(page_title="Convertitore welfare", page_icon="🧾", layout="centered")


@st.cache_resource
def carica_convertitore() -> Convertitore:
    return Convertitore()


def euro(valore) -> str:
    testo = f"{valore:,.2f}"                       # 1,234.56
    return testo.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


conv = carica_convertitore()
stato = st.session_state

# ------------------------------------------------------------------ intestazione
st.title("Convertitore welfare")
st.write(
    "Trasforma il report mensile del provider welfare nel file di import delle voci "
    "del gestionale paghe (`VOCI_<ditta>_<AAAAMM>.txt`)."
)
st.caption("I file caricati vengono elaborati in memoria e non vengono salvati.")

# ------------------------------------------------------------------ 1. dati
st.subheader("1. Dati della conversione")
provider = st.selectbox("Provider", list(conv.providers), index=None,
                        placeholder="Scegli il provider")
if provider:
    st.caption(conv.providers[provider].get("descrizione", ""))

file = st.file_uploader("File del provider", type=["xlsx", "xls", "csv"])
contenuto = file.getvalue() if file else None
impronta = hashlib.md5(contenuto).hexdigest() if file else None

# La ditta si sceglie solo tra quelle a cui appartengono i dipendenti del file
# (convertitore/ditte.py): nessun elenco "provider -> ditte" da tenere aggiornato.
# Le ditte sono in ordine di dipendenti riconosciuti; la prima è preselezionata
# se convince (più della metà dei dipendenti, nessun pareggio).
ditta, errore_file = "", None
if provider and file:
    chiave_proposta = (provider, impronta)
    if stato.get("chiave_proposta") != chiave_proposta:
        try:
            stato["proposta"] = conv.proponi_ditta(contenuto, file.name, provider)
            stato.pop("errore_file", None)
        except (ValueError, FileNonCorrispondente, FileNonLeggibile) as errore:
            stato["proposta"] = None
            stato["errore_file"] = str(errore)
        stato["chiave_proposta"] = chiave_proposta
    proposta, errore_file = stato.get("proposta"), stato.get("errore_file")

    if not errore_file and not proposta.per_ditta:
        errore_file = ("Nessun dipendente del file è presente in anagrafica: verifica di aver "
                       "scelto il provider giusto e che l'anagrafica sia aggiornata.")
    if errore_file:
        st.error(errore_file)
    else:
        avviso_nome = conv.avviso_nome_file(file.name, provider)
        if avviso_nome:
            st.warning(avviso_nome)
        ditte_del_file = list(proposta.per_ditta)
        ditta = st.selectbox(
            "Ditta (tra quelle dei dipendenti del file)", ditte_del_file,
            index=0 if proposta.ditta else None, placeholder="Scegli la ditta",
            format_func=lambda d: f"{conv.etichetta_ditta(d)} · {proposta.per_ditta[d]} "
                                  f"dipendenti su {proposta.dipendenti}",
            key=f"ditta_{provider}_{impronta}") or ""
        if not proposta.ditta:
            st.warning("Non propongo una ditta: " + proposta.motivo + " Sceglila dal menu.")
        elif ditta and ditta != proposta.ditta:
            st.warning(f"Hai scelto una ditta diversa da quella proposta "
                       f"({conv.etichetta_ditta(proposta.ditta)}): qui si riconoscono solo "
                       f"{proposta.per_ditta[ditta]} dipendenti su {proposta.dipendenti}, "
                       "gli altri finiranno negli scarti.")
else:
    st.selectbox("Ditta", [], disabled=True,
                 placeholder="Scegli il provider e carica il file: la ditta viene proposta da qui")

# Periodo del cedolino: mese e anno da due menu (regole in convertitore/periodo.py).
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

mancanti = [nome for nome, valore in [("provider", provider), ("file", file), ("ditta", ditta),
                                      ("periodo", periodo_scelto)] if not valore]
pronto = not mancanti and not errore_file
if mancanti and not errore_file:
    st.info("Per convertire mancano: " + ", ".join(mancanti) + ".")

# Se cambiano i dati in ingresso, il risultato precedente non vale più.
firma = None
if pronto:
    firma = (provider, ditta, periodo_scelto, file.name, impronta)
if stato.get("firma") != firma:
    stato.pop("risultato", None)
    stato["correzioni"] = Correzioni()
    stato["firma"] = None


def esegui():
    try:
        stato["risultato"] = conv.converti_file(contenuto, file.name, provider, ditta.strip(),
                                                periodo_scelto, stato["correzioni"])
        stato["firma"] = firma
        stato.pop("errore", None)
    except (ValueError, FileNonCorrispondente, FileNonLeggibile) as errore:
        stato.pop("risultato", None)
        stato["errore"] = str(errore)


if st.button("Converti", type="primary", disabled=not pronto, use_container_width=True):
    stato["correzioni"] = Correzioni()
    esegui()

if stato.get("errore") and pronto:
    st.error(stato["errore"])

ris = stato.get("risultato")
if not ris:
    st.stop()

# ------------------------------------------------------------------ 2. esito
st.divider()
st.subheader("2. Esito")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Righe lette", ris.righe_lette)
c2.metric("Record prodotti", len(ris.record))
c3.metric("Righe scartate", len(ris.scarti))
c4.metric("Avvisi", len(ris.avvisi))

simbolo = "✅" if ris.quadratura_ok else "❌"
st.write(
    f"{simbolo} **Quadratura:** totale letto {euro(ris.totale_letto)} = "
    f"esportato {euro(ris.totale_esportato)} + scartato {euro(ris.totale_scartato)}"
)
if ris.importi_non_leggibili:
    st.write(f"Importi non leggibili (esclusi dai totali): {ris.importi_non_leggibili}")

for avviso in ris.avvisi_generali:
    st.warning(avviso)

if ris.scarti:
    st.warning(
        f"**{len(ris.scarti)} righe scartate per {euro(ris.totale_scartato)}.** "
        "Non sono nel file VOCI: trovi il motivo di ciascuna nel file SCARTI. "
        "Se vuoi, puoi correggerle qui sotto e riconvertire."
    )
else:
    st.success("Nessuna riga scartata.")

# ------------------------------------------------------------------ 3. correzioni
if ris.dipendenti_da_correggere or ris.voci_da_correggere:
    st.divider()
    st.subheader("3. Correzioni (facoltative)")
    st.caption("Lascia vuoto ciò che non vuoi correggere: quelle righe resteranno negli scarti. "
               "Una correzione vale per tutte le righe dello stesso dipendente o trattamento.")
    nuove = Correzioni(dict(stato["correzioni"].dipendenti), dict(stato["correzioni"].voci))

    if ris.dipendenti_da_correggere:
        st.markdown("**Dipendenti non riconosciuti**")
        for i, (chiave, d) in enumerate(ris.dipendenti_da_correggere.items()):
            codice = st.text_input(
                f"{d.descrizione} — {d.righe} righe, {euro(d.totale)}",
                key=f"dip_{i}_{chiave}", placeholder="Codice dipendente nel gestionale",
                help=d.motivo)
            if codice.strip():
                nuove.dipendenti[chiave] = codice.strip()

    if ris.voci_da_correggere:
        st.markdown("**Trattamenti non abbinati**")
        voci_note = sorted({r[1] for r in conv.tabella.righe}, key=lambda v: (len(v), v))
        for i, (chiave, v) in enumerate(ris.voci_da_correggere.items()):
            scelta = st.selectbox(
                f"{v.descrizione} — {v.righe} righe, {euro(v.totale)}",
                ["(lascia negli scarti)"] + voci_note, key=f"voce_{i}", help=v.motivo)
            if scelta != "(lascia negli scarti)":
                nuove.voci[chiave] = scelta

    if st.button("Riconverti con le correzioni", use_container_width=True):
        stato["correzioni"] = nuove
        esegui()
        st.rerun()

# ------------------------------------------------------------------ 4. download
st.divider()
st.subheader("4. Scarica i file")
d1, d2 = st.columns(2)
d1.download_button(f"Scarica VOCI ({len(ris.record)} record)", ris.file_voci(),
                   file_name=ris.nome_file_voci, mime="text/plain",
                   type="primary", use_container_width=True, disabled=not ris.record)
if ris.segnalazioni:
    d2.download_button(f"Scarica SCARTI e avvisi ({len(ris.segnalazioni)})", ris.file_scarti(),
                       file_name=ris.nome_file_scarti, mime="text/csv", use_container_width=True)
else:
    d2.write("Nessuno scarto né avviso.")

# ------------------------------------------------------------------ dettagli
with st.expander("Anteprima dei record"):
    st.dataframe(
        [{"Dipendente": r[6:12].strip(), "Voce": r[12:16].strip(),
          "Importo": euro(int(r[23:32]) / 100), "Record": r} for r in ris.record],
        hide_index=True, use_container_width=True)

if ris.segnalazioni:
    with st.expander("Scarti e avvisi"):
        st.dataframe(
            [{"Tipo": s.tipo, "Riga": s.riga, "Dipendente": s.dipendente,
              "Trattamento": s.trattamento, "Importo": s.importo, "Motivo": s.motivo,
              "Cosa fare": s.cosa_fare} for s in ris.segnalazioni],
            hide_index=True, use_container_width=True)

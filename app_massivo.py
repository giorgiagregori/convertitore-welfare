"""Convertitore welfare - caricamento massivo (Streamlit).

Evoluzione dell'app singola (app.py): si caricano insieme tutti i report del
mese, l'app riconosce provider e ditta di ogni file, l'operatore controlla un
riepilogo e converte tutto in una volta. Esce uno zip con un file VOCI per ditta
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
st.write("Carica tutti i report del mese insieme: l'app riconosce provider e ditta di ogni "
         "file e produce un file VOCI per ditta, più un unico file SCARTI.")
st.caption("I file caricati vengono elaborati in memoria e non vengono salvati.")

# ------------------------------------------------------------------ 1. periodo e file
st.subheader("1. Periodo e file")
oggi = date.today()
anno_proposto, mese_proposto = mese_precedente(oggi)
anni = anni_disponibili(oggi)
col_mese, col_anno, _ = st.columns([2, 1, 3])
mese = col_mese.selectbox("Mese del cedolino", range(1, 13), index=mese_proposto - 1,
                          format_func=lambda m: MESI[m - 1])
anno = col_anno.selectbox("Anno", anni, index=anni.index(anno_proposto))
periodo_scelto = periodo(anno, mese)
avviso = avviso_periodo(anno, mese, oggi)
if avviso:
    st.warning(avviso)

caricati = st.file_uploader("Report dei provider (puoi selezionarne tanti insieme)",
                            type=["xlsx", "xls", "csv"], accept_multiple_files=True)
if not caricati:
    st.info("Carica i file per vedere il riepilogo.")
    st.stop()

# ------------------------------------------------------------------ 2. riepilogo dei file
st.divider()
st.subheader("2. Controlla i file")
st.caption("Provider e ditta sono proposti dall'app: puoi cambiarli. La ditta si sceglie tra "
           "quelle dei dipendenti del file. I file bloccati non vengono convertiti.")

scelte, visti = [], {}
for i, file in enumerate(caricati):
    contenuto = file.getvalue()
    chiave_file = impronta(contenuto)
    with st.container(border=True):
        if chiave_file in visti:
            st.markdown(f"{ICONA[BLOCCATO]} **{file.name}**")
            st.error(f"Stesso contenuto di '{visti[chiave_file]}': caricato due volte, non viene convertito.")
            continue
        visti[chiave_file] = file.name

        automatica = analisi_di(file.name, contenuto)
        c_prov, c_ditta, c_incl = st.columns([2, 3, 1])
        if automatica.compatibili or automatica.provider:
            opzioni = list(conv.providers)
            provider = c_prov.selectbox(
                "Provider", opzioni, index=opzioni.index(automatica.provider) if automatica.provider else None,
                key=f"prov_{chiave_file}", placeholder="Scegli il provider")
        else:
            provider = None
        analisi = automatica if provider == automatica.provider else analisi_di(file.name, contenuto, provider)

        if analisi.stato == BLOCCATO:
            st.markdown(f"{ICONA[BLOCCATO]} **{file.name}**")
            st.error(analisi.errore)
            continue

        per_ditta = analisi.proposta.per_ditta
        ditte = list(per_ditta)
        ditta = c_ditta.selectbox(
            "Ditta", ditte, index=ditte.index(analisi.ditta_proposta) if analisi.ditta_proposta else None,
            format_func=lambda d, pd=per_ditta, tot=analisi.proposta.dipendenti:
                f"{conv.etichetta_ditta(d)} · {pd[d]} dipendenti su {tot}",
            key=f"ditta_{chiave_file}_{provider}", placeholder="Scegli la ditta")
        includi = c_incl.checkbox("Converti", value=True, key=f"incl_{chiave_file}")

        icona = ICONA[analisi.stato] if ditta else ICONA[DA_GUARDARE]
        st.markdown(f"{icona} **{file.name}**")
        for testo in analisi.avvisi:
            st.warning(testo)
        if ditta and analisi.ditta_proposta and ditta != analisi.ditta_proposta:
            st.warning(f"Hai cambiato la ditta proposta ({conv.etichetta_ditta(analisi.ditta_proposta)}): "
                       f"qui si riconoscono {per_ditta[ditta]} dipendenti su {analisi.proposta.dipendenti}.")
        if includi and ditta:
            scelte.append(Scelta(file.name, contenuto, provider, ditta))

# Ditte che ricevono più file: un solo VOCI con i movimenti di tutti.
gruppi = {}
for s in scelte:
    gruppi.setdefault(s.ditta, []).append(s)
for ditta, lista in gruppi.items():
    if len(lista) > 1:
        st.info(f"La ditta {conv.etichetta_ditta(ditta)} riceve {len(lista)} file "
                f"({', '.join(s.nome for s in lista)}): verranno uniti in un solo VOCI_{ditta}_{periodo_scelto}.txt.")

firma = (periodo_scelto, tuple((impronta(s.contenuto), s.provider, s.ditta) for s in scelte))
if stato.get("firma") != firma:
    stato.pop("lotto", None)
    stato["correzioni"] = {}
    stato["firma"] = None


def esegui():
    stato["lotto"] = converti_lotto(conv, scelte, periodo_scelto, stato["correzioni"])
    stato["firma"] = firma


st.write(f"**{len(scelte)} file da convertire** su {len(caricati)} caricati, "
         f"per {len(gruppi)} ditte.")
if st.button("Converti tutto", type="primary", disabled=not scelte, use_container_width=True):
    stato["correzioni"] = {}
    esegui()

lotto = stato.get("lotto")
if not lotto:
    st.stop()

# ------------------------------------------------------------------ 3. esito
st.divider()
st.subheader("3. Esito")
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
    st.subheader("4. Correzioni (facoltative)")
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
st.subheader("5. Scarica i file")
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

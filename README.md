# Convertitore welfare universale

Trasforma il report mensile di un provider welfare nel tracciato di import delle
voci retributive del gestionale paghe (`VOCI_<ditta>_<AAAAMM>.txt`, record a
lunghezza fissa di 38 caratteri).

**App online:**

- conversione singola: https://convertitore-welfare.streamlit.app/
- caricamento massivo: https://convertitore-welfare-massivo.streamlit.app/

**Video di presentazione:** https://www.loom.com/share/2f6fcffc85154798aed9979d2b10b933

## Struttura del progetto

```
convertitore_welfare/
├── convertitore/            il motore
│   ├── lettura.py           lettura del file (xlsx, xls, csv) in righe
│   ├── configurazione.py    applica la configurazione del provider alle righe
│   ├── importi.py           lettura degli importi nei formati dei provider
│   ├── anagrafica.py        riconoscimento del dipendente nella ditta scelta
│   ├── voci.py              dal trattamento fiscale alla voce payroll
│   ├── motore.py            somma, ordinamento, file VOCI e SCARTI, quadratura, correzioni
│   ├── tracciato.py         scrittura del record da 38 caratteri
│   ├── ditte.py             proposta della ditta dai dipendenti del file
│   ├── periodo.py           scelta di mese e anno del cedolino
│   ├── massivo.py           caricamento massivo: analisi e conversione di un lotto di file
│   └── servizio.py          punto di ingresso unico (lo userà l'interfaccia)
├── config/
│   ├── providers.json       una configurazione per provider
│   ├── Lista_Dipendenti.csv
│   └── Codici_Welfare_Voci_Payroll.csv
├── tests/                   test automatici e file del kit usati come casi di prova
├── app.py                   interfaccia web (Streamlit), un file per volta
├── app_massivo.py           interfaccia web per il caricamento massivo
├── converti.py              uso da terminale
├── requirements.txt
└── README.md
```

## Come funziona, in breve

```
file del provider
  → lettura.py         righe del file (riconosce xlsx/xls/csv, codifica e separatore)
  → configurazione.py  trova l'intestazione e prende le colonne indicate in providers.json
  → motore.py          per ogni riga: importo (importi.py), dipendente (anagrafica.py),
                       voce (voci.py); poi somma, ordina, scrive VOCI e SCARTI
  → tracciato.py       record da 38 caratteri
```

## Usare l'interfaccia

Sul proprio computer, dalla cartella `convertitore_welfare`:

```
pip install -r requirements.txt
streamlit run app.py
```

Si apre il browser su `http://localhost:8501`. Il percorso è guidato:

1. **Dati**: provider, file, ditta e periodo. Caricato il file,
   l'app **propone la ditta** guardando i dipendenti presenti (vedi sotto). Il
   menu mostra solo le ditte a cui appartiene almeno un dipendente del file, in
   ordine di riscontri, con codice, ragione sociale e numero di dipendenti
   riconosciuti (es. `4012 – Alfa Servizi S.r.l. · 8 dipendenti su 9`); la prima
   è preselezionata se la proposta convince. Se nessun dipendente è in
   anagrafica la conversione è bloccata. Il periodo si sceglie con due menu,
   mese e anno; è già proposto il mese precedente a oggi (vedi assunzione 31).
   Il pulsante *Converti* si attiva solo quando i dati sono completi e validi.
2. **Esito**: righe lette, record prodotti, scarti, avvisi e quadratura
   (totale letto = esportato + scartato). Se ci sono scarti compare un avviso
   con il numero di righe e l'importo escluso.
3. **Correzioni (facoltative)**: per ogni dipendente non riconosciuto si può
   scrivere il codice del gestionale, per ogni trattamento non abbinato si può
   scegliere la voce. *Riconverti con le correzioni* rifà il calcolo; le
   correzioni usate restano tracciate come avvisi nel file SCARTI.
4. **Download**: file VOCI e, se serve, file SCARTI; sotto, l'anteprima dei
   record e la tabella di scarti e avvisi.

Se si cambia provider, ditta, periodo o file, il risultato precedente viene
cancellato. I file restano in memoria per la sola conversione e non vengono
salvati. L'interfaccia non contiene logica di conversione: chiama soltanto
`Convertitore.converti_file` (in `servizio.py`), lo stesso usato da terminale
e dai test.

## Aggiungere un provider

Si aggiunge un blocco in `config/providers.json`, senza toccare il codice:

```json
"Provider A": {
  "intestazione": true,
  "formato_importo": "it",
  "dipendente": {"codice_fiscale": "Codice fiscale dipendente", "nome": ["Nome dipendente"]},
  "trattamento": ["Tratt. Fiscale"],
  "importo": "Importo"
}
```

- `intestazione`: `true` se il file ha una riga di intestazione (le colonne si
  indicano per nome, la riga viene cercata nel file); `false` se non ce l'ha (le
  colonne si indicano per posizione, 1 = prima colonna).
- `formato_importo`: `"it"`, `"en"` o `"auto"`.
- `dipendente`: uno o più tra `codice_fiscale`, `codice`, `nome` (lista di
  colonne). Una colonna può avere una condizione:
  `{"colonna": "...", "solo_se": {"colonna": "...", "uguale": "..."}}`.
- `trattamento`: lista di colonne, unite con uno spazio se più di una.
- `sottocategoria` (facoltativa) e `importo`: una colonna.
- `controlli` (facoltativo): verifiche che il file sia davvero del provider.
  - `colonne`: numero esatto di colonne di ogni riga;
  - `formati`: `{colonna: espressione regolare}` che ogni riga di dati deve
    rispettare;
  - `nome_file`: espressione regolare sul nome del file (solo avviso).

## Controlli sul file caricato

Il file deve essere del provider scelto; il programma lo verifica così:

1. **Struttura** (blocca): per i provider con intestazione devono esserci
   tutte le colonne indicate in `providers.json`; per il Provider B, che non ha
   intestazione, ogni riga deve avere 13 colonne, un codice trattamento tipo
   `X71180` in colonna 4, una data `AAAAMMGG` in colonna 5 e un importo in
   colonna 9. Basta una riga diversa per fermarsi, indicando quale.
2. **Quale provider sembra** (blocca): se il file non va bene per il provider
   scelto, il programma prova le altre configurazioni e lo dice: *"Il file
   sembra del Provider B, non del Provider A"*.
3. **Almeno un movimento** (blocca): un file con la sola intestazione viene
   rifiutato.
4. **Nome del file** (avviso): se il nome non è quello solito del provider
   (es. `Flusso-Payroll` per B) compare un avviso, ma si può proseguire, perché
   i file vengono spesso rinominati.
5. **Dipendenti** (blocca o avvisa): se nessun dipendente è in anagrafica non
   si può convertire; se se ne riconoscono pochi nella ditta scelta compare
   l'avviso "hai scelto la ditta giusta?".

Il test `tests/test_controlli_file.py` prova tutte le 25 combinazioni
provider/file del kit: si converte solo quando coincidono.

## Caricamento massivo (evoluzione)

`app_massivo.py` è una seconda app, sullo stesso motore (online:
https://convertitore-welfare-massivo.streamlit.app/), pensata per il lavoro
di fine mese: invece di convertire un file per volta si caricano **tutti i
report del mese insieme**.

```
streamlit run app_massivo.py
```

1. **Cosa converti**: mese e anno, **uguali per tutti i file**, e i provider
   da elaborare (menu a tendina a scelta multipla, oppure la casella *Tutti i
   provider*).
2. **Carica i file**: tutti i report insieme.
3. **Riepilogo dei file**: una tabella, senza niente da scegliere file per file.
   Per ogni file l'app riconosce il **provider** dalle colonne e la **ditta** dai
   dipendenti, con lo stato: ✅ pronto, ⚠️ da guardare (es. nome del file
   insolito), ❌ escluso con il motivo (non leggibile, di nessun provider, di un
   provider non scelto, nessun dipendente in anagrafica, ditta non determinabile,
   caricato due volte).
4. **Ditte da convertire**: scelta multipla tra le ditte trovate nei file (di
   partenza tutte), con il numero di file per ditta.
5. **Esito**: una riga per ditta con file, provider, record, scarti, avvisi e
   quadratura.
6. **Correzioni**, solo per le ditte con scarti, come nell'app singola.
7. **Download**: uno zip con un file `VOCI_<ditta>_<AAAAMM>.txt` per ditta e un
   unico `SCARTI_<AAAAMM>.csv`, con in più le colonne File, Provider e Ditta.

Regole del lotto (`convertitore/massivo.py`):

- **Più file per la stessa ditta** (anche di provider diversi): i movimenti
  vengono convertiti insieme ed esce **un solo file VOCI** per la ditta; lo stesso
  dipendente sulla stessa voce viene sommato. La quadratura vale per ditta.
- **Stesso file caricato due volte** (stesso contenuto, anche con nome diverso):
  il secondo viene bloccato, altrimenti gli importi raddoppierebbero.
- **Ditta non determinabile** (pareggio o metà o meno dei dipendenti
  riconosciuti): il file è escluso e va convertito con l'app singola, dove la
  ditta si sceglie a mano.
- Ogni movimento porta con sé il file di provenienza e il formato degli importi
  del suo provider, perché nello stesso lotto convivono formati diversi
  (`1.234,56` e `1,234.56`).

Con i 5 file del kit caricati insieme il risultato è identico, file per file, a
quello delle 5 conversioni singole (verificato da `tests/test_massivo.py`).

## Come viene proposta la ditta

Non c'è un elenco "quali ditte segue ogni provider" da tenere aggiornato: per
ogni ditta in anagrafica il programma conta quanti dipendenti del file vi
riconosce (con le stesse regole della conversione) e propone quella con più
riscontri (`convertitore/ditte.py`). La propone solo se:

- riconosce **più della metà** dei dipendenti del file, e
- **nessun'altra ditta** ne riconosce lo stesso numero.

Altrimenti non preseleziona nulla e spiega il motivo; la scelta resta
all'operatore. Se un provider inizia a seguire una ditta nuova, la proposta
funziona subito. Una ditta completamente nuova deve prima comparire
nell'anagrafica (`Lista_Dipendenti.csv`, estratta dal gestionale paghe): senza
i suoi dipendenti nessuna riga potrebbe essere riconosciuta.

Nel menu compaiono anche ditte con pochi riscontri quando un dipendente lavora
in più ditte: nel file del Provider A, Noemi La Rocca (stesso codice fiscale) è
in anagrafica sia nella 4012 (codice 10) sia nella 4175 (codice 900), quindi il
menu mostra `4012 · 8 su 9` e `4175 · 1 su 9`.

Sui file del kit:

| Provider | Ditta proposta | Dipendenti riconosciuti |
|---|---|---|
| A | 4012 – Alfa Servizi S.r.l. | 8 su 9 (manca Fumagalli) |
| B | 4027 – Bruni Logistica S.p.A. | 5 su 6 (manca Marini Sofia) |
| C | 4041 – Delta Impianti S.r.l. | 9 su 9 |
| D | 4093 – Larice Design S.r.l. | 11 su 12 (manca Matteo Martini) |
| E | 4131 – Pino Trasporti S.r.l. | 7 su 8 (manca Guerra Paolo) |

## Uso da terminale

```
pip install -r requirements.txt
python converti.py "Provider A" 4012 202609 tests/dati_kit/input/ProviderA_welfare_report_2026-09-01_2026-09-30.xlsx
python converti.py "Provider A" 4012 202609 <file> --dipendente CF:FMGLSS92S52G273A=25
```

## Come si lanciano i test

Dalla cartella `convertitore_welfare`:

```
python -m unittest discover -s tests -v
```

I test usano solo la libreria standard di Python (`unittest`).

## Il tracciato di destinazione

| Campo | Posizione | Lunghezza | Tipo | Regola |
|---|---|---|---|---|
| Codice ditta | 1 | 6 | N | Codice inserito in input |
| Codice dipendente | 7 | 6 | A | Codice gestionale del dipendente |
| Codice voce | 13 | 4 | A | Codice gestionale della voce welfare |
| Quantità | 17 | 7 | N | Sempre zeri |
| Importo | 24 | 9 | N | Centesimi, senza separatore |
| Periodo | 33 | 6 | AAAAMM | Periodo del cedolino |

N = allineato a destra con zeri; A = allineato a sinistra con spazi.

## Assunzioni

1. Gli importi sono calcolati in decimale esatto (`Decimal`) e arrotondati al
   centesimo con la regola "mezzo centesimo per eccesso".
2. Un record non può contenere un importo negativo: i totali negativi verranno
   gestiti come scarti, non scritti nel file VOCI.
3. Se un campo non entra nella sua lunghezza o contiene caratteri non ASCII, il
   record non viene scritto e il motore segnala l'errore invece di troncare.
4. Ogni provider dichiara il formato dei suoi importi: "it" (1.234,56), "en"
   (1,234.56) o "auto". Nel kit: A, B, D in formato "it"; E in formato "en";
   C contiene numeri veri di Excel.
5. In formato "auto" un importo ambiguo (es. "1.234": migliaia o decimali?) non
   viene indovinato: la riga va negli scarti con il motivo.
6. Un importo scritto in un formato diverso da quello dichiarato (es. "15.88"
   per un provider "it") non viene letto male: va negli scarti.
7. Gli importi negativi ("-12,00", "12,00-", "(12,00)") vengono letti; cosa
   farne si decide dopo la somma per dipendente e voce.
8. Il dipendente si cerca solo tra quelli della ditta scelta. L'anagrafica viene
   ripulita dalle righe duplicate (25 nel kit).
9. Ordine di affidabilità: codice fiscale, poi codice dipendente, poi nome e
   cognome. Se il provider dà sia codice sia codice fiscale e non indicano la
   stessa persona, la riga va negli scarti.
10. I nomi si confrontano senza maiuscole, accenti, punteggiatura e ordine delle
    parole, ma devono coincidere tutte le parole (nessuna corrispondenza parziale).
11. Se più dipendenti della ditta hanno lo stesso nome (omonimi) e non c'è il
    codice fiscale, la riga va negli scarti: il codice si sceglie a mano.
12. Quando un dipendente non si trova ma la stessa persona esiste in un'altra
    ditta, il file scarti lo segnala ("hai scelto la ditta giusta?").
13. La voce si cerca in quest'ordine: (a) trattamento e sottocategoria identici;
    (b) trattamento identico in una riga senza sottocategoria; (c) stesso
    articolo, comma e lettera, solo se porta a un'unica voce.
14. "Identico" ignora maiuscole e spazi ripetuti, ma non la punteggiatura: in
    tabella "Art.51 c. 3" (sottocategoria Effettivo → 194) e "Art. 51 c.3" (→ 371)
    sono righe diverse e restano tali.
15. Per il confronto (c) il testo tra parentesi ("[FCI Art.2]", "(ex Art.100)")
    è considerato un commento e ignorato. Un trattamento senza articolo
    riconoscibile (es. "X71133") non viene mai abbinato per somiglianza.
16. Gli abbinamenti per somiglianza vengono esportati ma segnalati come AVVISO;
    se la somiglianza porta a più voci, la riga va negli scarti con le voci
    possibili.
17. Gli importi si sommano per coppia dipendente/voce; uno storno parziale
    (importo negativo) si somma agli altri. Se il totale è negativo, tutte le
    righe di quella coppia vanno negli scarti; se è zero, non si esporta nulla
    e lo si segnala.
18. Una riga con più problemi (es. dipendente e voce) compare una sola volta nel
    file scarti, con tutti i motivi.
19. File VOCI: `VOCI_<ditta>_<AAAAMM>.txt`, un record per riga, ogni riga chiusa
    da CRLF (anche l'ultima), solo ASCII. File SCARTI:
    `SCARTI_<provider>_<ditta>_<AAAAMM>.csv`, separatore ";", con BOM UTF-8
    perché Excel mostri gli accenti; contiene SCARTI e AVVISI.
20. Una correzione a mano vale per tutte le righe dello stesso dipendente (o
    dello stesso trattamento) nel file. Il codice inserito a mano non viene
    cercato in anagrafica (serve proprio per chi non c'è ancora), ma resta
    tracciato come AVVISO.
21. Se più della metà delle righe ha dipendenti non presenti nella ditta scelta,
    compare l'avviso "hai scelto la ditta giusta?".
22. Quadratura: totale letto = totale esportato + totale scartato. Gli importi
    non leggibili non entrano in nessuno dei tre totali e sono contati a parte.
23. Il tipo di file si riconosce dai primi byte (un .xlsx è uno zip, un .xls un
    contenitore Microsoft), non solo dall'estensione. Si legge il primo foglio.
24. I csv si leggono in UTF-8 e, se non è possibile, nella codifica di Windows
    (cp1252), come il file del Provider B. Il separatore si riconosce da solo.
25. La riga di intestazione si cerca tra le prime 30 righe: è la prima che
    contiene tutte le colonne della configurazione. Se non c'è, il convertitore
    si ferma con "Il file non sembra del Provider X: mancano le colonne ...".
26. Le righe completamente vuote, e quelle senza dipendente, trattamento e
    importo (es. note o totali in fondo al file), non sono movimenti e si saltano;
    la numerazione delle righe resta quella del file originale.
27. Niente pandas: bastano openpyxl (xlsx), xlrd (xls) e la libreria standard
    di Python. Meno dipendenze, meno cose che si possono rompere.
28. Il separatore dei csv si sceglie contando le colonne: vince quello che dà
    più colonne tra quelli costanti su almeno l'80% delle righe. Il
    riconoscimento automatico di Python scambiava la virgola dei decimali
    ("60,00") per il separatore, e una sola riga anomala non deve bastare a
    fargli cambiare idea.
29. Il kit non dice quali ditte segue ogni provider: per non mantenere un
    elenco a mano, la ditta viene proposta dai dipendenti del file (soglia: più
    della metà riconosciuti, nessun pareggio). Per A la proposta coincide con il
    nome del file di esempio (`VOCI_4012_202609.txt`).
30. Ragione sociale: se in anagrafica una ditta ha più scritture, si usa la più
    frequente (la 4175 compare come "Tiglio Lab S.r.l." e "Tiglio Lab S.R.L.").
31. Periodo: non è limitato "dal mese corrente in avanti", perché il report
    arriva a mese chiuso (quello di settembre arriva a ottobre e va nel periodo
    202609, come nel kit) e a volte serve rifare una conversione passata. Si
    possono scegliere l'anno precedente, il corrente e il successivo; è proposto
    il mese precedente a oggi; per un mese futuro o di più di un mese fa compare
    un avviso, ma la conversione non viene bloccata.
32. Il nome del file è solo un avviso e non un blocco: i nomi del kit seguono
    uno schema per provider, ma nella pratica i file si rinominano; il controllo
    vero è sul contenuto.
33. Caricamento massivo: se più file riguardano la stessa ditta nello stesso
    periodo si produce un solo file VOCI (il gestionale riceve un file per ditta,
    come da specifica) sommando dipendente e voce; il totale negativo si valuta
    sulla somma di tutti i file della ditta.

## Verifiche fatte sui dati del kit

- **Tutti i provider:**

  | Provider | Ditta | Righe | Record | Scarti | Avvisi | Quadratura (letto = esportato + scartato) |
  |---|---|---|---|---|---|---|
  | A | 4012 | 21 | 18 | 1 Fumagalli | 4 | 1.990,02 = 1.933,86 + 56,16 |
  | B | 4027 | 12 | 6 | 3 Marini Sofia, 1 X71133 | 0 | 7.266,47 = 2.929,40 + 4.337,07 |
  | C | 4041 | 20 | 17 | 0 | 1 | 5.346,93 = 5.346,93 + 0 |
  | D | 4093 | 17 | 12 | 1 Asilo nido, 1 Matteo Martini | 0 | 2.897,26 = 2.453,17 + 444,09 |
  | E | 4131 | 19 | 11 | 3 Guerra Paolo | 2 | 2.051,86 = 1.897,10 + 154,76 |

- **Provider A, confronto con l'esempio del kit:** senza correzioni 18 record, 1 scarto
  (Alessia Fumagalli, riga 8, 56,16 €) e 4 avvisi; quadratura 1.990,02 =
  1.933,86 + 56,16. Con Fumagalli = 25 inserito a mano il file VOCI è
  **identico byte per byte** a `ESEMPIO_VOCI_4012_202609.txt`.

- Tutti gli importi dei Provider A, B, D, E si leggono senza errori, sia con il
  formato dichiarato sia in automatico.
- Totale letto dal file del Provider A: 1.990,02 €, uguale al totale del file
  di esempio.
- Riconoscimento dei dipendenti su tutte le righe del kit:

  | Provider | Ditta | Righe | Trovati | Non trovati |
  |---|---|---|---|---|
  | A | 4012 | 21 | 20 | Alessia Fumagalli |
  | B | 4027 | 12 | 9 | Marini Sofia (3 righe) |
  | C | 4041 | 20 | 20 | — |
  | D | 4093 | 17 | 16 | Matteo Martini |
  | E | 4131 | 19 | 16 | Guerra Paolo (3 righe) |

- Abbinamento delle voci su tutte le righe del kit:

  | Provider | Esatte | Per somiglianza (avviso) | Scarti |
  |---|---|---|---|
  | A | 17 | 4 ("let d-bis" → 377, come nell'esempio) | — |
  | B | 11 | — | 1 (X71133 non in tabella) |
  | C | 19 | 1 (Art.51 c. 3 Figurativo → 371) | — |
  | D | 16 | — | 1 (f-bis "Asilo nido": 372 o 373) |
  | E | 17 | 2 ("Art 100 [Iva 22%]" → 370) | — |

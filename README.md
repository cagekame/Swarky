27/07/2026 — Aggiunti nuovi basename per ISS
18/10/2026 — ISS tag DocumentNo, DAF rev00 exception, label FIV/Hengelo/ISS in GUI, errori ISS in Anomalie

# Swarky — Regole di Archiviazione

La logica di archiviazione opera **per sheet**: tutte le decisioni (validazioni, confronto revisioni, coesistenza delle metriche, storicizzazione) avvengono **all’interno dello stesso foglio `Syy`** per un determinato *document number* (Prefix).

---

## 🧾 Nomenclatura

- **Prefix**: `D<size><loc><num>` — identifica il disegno (document number), es. `DCM728093`
- **R**: revisione (`Rxx`), es. `R14`
- **S**: sheet (`Syy`), es. `S01`
- **UOM**: metrica `{ M, I, D, N }`
- **Gruppi**: **MI** = `{M, I}` · **DN** = `{D, N}`

**Nome file completo:**  
`D<size><loc><num>R<xx>S<yy><UOM>.(tif|pdf)`

---

## 📌 Principi chiave

1. **Ambito per sheet**  
   Lo *scope* delle decisioni è **(Prefix, Sheet)**.  
   Gli altri sheet (`Szz ≠ Syy`) sono **indipendenti**.

2. **Coesistenza M/I anche con revisioni diverse (Regime MI)**  
   - `M` e `I` **coesistono sullo stesso sheet anche con revisioni diverse**  
   - Una revisione nuova di `I` **non** storicizza `M`, e viceversa  
   - Si storicizzano **solo** le revisioni **più vecchie della *stessa metrica*** su quello sheet

3. **DN esclusivo alla stessa revisione**  
   - `D` e `N` **non coesistono alla stessa revisione**
   - `D/N` non coesistono con MI alla stessa revisione  
   - Cambio regime MI ↔ DN consentito **solo** se `Rnew > Rold`

4. **Storicizzazione mirata**  
   Quando arriva un file `Rnew` per `(Prefix, Sheet, Metrica)`:
   - Sposta in **ARCHIVIO_STORICO** solo i file **della *stessa metrica*** con `rev < Rnew` e **stesso sheet**
   - Non tocca mai:
     - file dell’altra metrica (M↔I)
     - file di altri sheet

---

## ✅ Controlli formali (sempre prima)

- Nome non conforme alla regex  
- Formato non in `A..E`  
- Location non in `M,K,F,T,E,S,N,P`  
- UOM non in `M/I/D/N`  
- TIFF non in *landscape*  

➡️ **Se uno dei controlli fallisce → spostamento in `ERROR_DIR` + log dedicato**

---

## 🔎 Ricerca dell’ambito

Dato un file `D…RxxSyy{UOM}` in ingresso:  
considera **solo** i file in archivio con **stesso `Prefix` e stesso `Syy`**.  
Gli altri sheet sono irrilevanti.

---

## 🔄 Confronto revisioni (per quello sheet e metrica)

- Nessuna revisione presente → **archivia**
- `Rnew < Rold` → **ERROR_DIR** (*Revisione Precedente*)
- `Rnew = Rold` → vedi **tabella coesistenza**
- `Rnew > Rold` → storicizza **solo** le revisioni più vecchie della **stessa metrica** → poi archivia `Rnew`

---

## 🟰 Regole alla **stessa revisione** (stesso `R` e `S`)

Azione sul nuovo file:

| UOM      | Regime **MI** (M/I)                        | Regime **D-only**            | Regime **N-only**            |
|----------|--------------------------------------------|------------------------------|------------------------------|
| **M**    | ✅ **OK** (coesiste con I)                 | 🚫 **PR** (regime non MI)   | 🚫 **PR** (regime non MI)   |
| **I**    | ✅ **OK** (coesiste con M)                 | 🚫 **PR** (regime non MI)   | 🚫 **PR** (regime non MI)   |
| **D**    | 🚫 **PR** (cambio regime non ammesso)      | ✅ **OK**                    | 🚫 **PR** (regime non D-only)|
| **N**    | 🚫 **PR** (cambio regime non ammesso)      | 🚫 **PR** (regime non N-only)| ✅ **OK**                   |

- **OK** → archivia (`PLM + archivio + EDI`)
- **PR** → sposta in **PARI_REV_DIR**

---

## 🏷️ Messaggi di log

- `# Rev superata # <vecchio>` → spostato in Storico (stessa metrica + sheet)  
- `# Metrica Diversa # <altro>` → coesistenza M/I riconosciuta  
- `# Pari Revisione` → duplicato o cambio regime non ammesso  
- `# Archiviato` → accettazione e archiviazione  
- `# Revisione Precedente # <ref>` → scartato  
- `ProcessTime # X.XXs` → sempre **ultima riga del log**, indica il tempo totale della passata

---

## ⚙️ Ordine delle operazioni

1. **Validazioni** (regex + formati + orientamento)  
2. **Risoluzione cartella**  
3. **Lock (docno + sheet)** + controlli pari rev / rev prec.  
4. **Accettazione e spostamento in archivio** (dentro lock)  
5. **Fuori lock:** spostamenti in Storico (solo stessa metrica & sheet)  
6. **PLM:** hardlink se possibile, altrimenti `CopyFileW`  
7. **EDI:** crea `.DESEDI`  
8. **Log GUI:** immediato — **Log file:** scritto **alla fine** con `ProcessTime` ultima riga  

---

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

## 📊 Diagramma (Mermaid)

```mermaid
flowchart TD
  A[Nuovo file D…RxxSyy{UOM}] --> B{Controlli formali OK?}
  B -- No --> X[ERROR_DIR]:::err
  B -- Sì --> C[Seleziona archivio con stesso Prefix+Syy]
  C --> D{Esistono file per Syy?}
  D -- No --> E[ARCHIVIA nuovo file]:::ok
  D -- Sì --> F[Valuta revisioni per la STESSA METRICA]
  F --> G{Rnew < max_rev?}
  G -- Sì --> X[ERROR_DIR: Rev Precedente]:::err
  G -- No --> H{Rnew = max_rev?}
  H -- Sì --> I{Regole alla stessa R}
  I -- PR --> PR[PARI_REV_DIR]:::pr
  I -- OK --> E2[ARCHIVIA]:::ok
  H -- No --> J[Storicizza rev < Rnew della stessa metrica]:::stor
  J --> E2[ARCHIVIA]:::ok

  classDef ok fill:#DCFCE7,stroke:#16A34A,color:#064E3B
  classDef pr fill:#FEF9C3,stroke:#CA8A04,color:#713F12
  classDef err fill:#FEE2E2,stroke:#DC2626,color:#7F1D1D
  classDef stor fill:#E0E7FF,stroke:#4F46E5,color:#1E3A8A

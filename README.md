# Swarky — Regole di Archiviazione (per Sheet) · Nuova logica

La logica di archiviazione opera **per sheet**: tutte le decisioni (confronto revisioni, coesistenza delle metriche, storicizzazione) avvengono **all’interno dello stesso foglio `Syy`** per un determinato *document number* (Prefix).

---

## Nomenclatura

- **Prefix**: `D<size><loc><num>` — identifica il disegno (document number), es. `DCM728093`
- **R**: revisione (`Rxx`), es. `R14`
- **S**: sheet (`Syy`), es. `S01`
- **UOM**: metrica `{ M, I, D, N }`
- **Gruppi**: **MI** = `{M, I}` · **DN** = `{D, N}`

**Nome file completo**  
`D<size><loc><num>R<xx>S<yy><UOM>.(tif|pdf)`

---

## Principi chiave

1. **Ambito per sheet**  
   Lo *scope* è **(Prefix, Sheet)**. Gli altri sheet (`Szz ≠ Syy`) sono **indipendenti**.

2. **Coesistenza M/I anche con revisioni diverse**  
   In **MI**, `M` e `I` **coesistono sullo stesso sheet anche se hanno revisioni diverse**.  
   ➜ **Una revisione nuova di `I` non storicizza `M`**, e viceversa.  
   ➜ Si storicizzano **solo** le revisioni **più vecchie della *stessa metrica*** su quello sheet.

3. **DN esclusivo per revisione**  
   In **DN**, `D` e `N` **non coesistono alla stessa revisione** e **non coesistono con MI alla stessa revisione**.  
   Il cambio regime (p.es. da MI a DN o viceversa) è **consentito solo con incremento di revisione**, ma senza toccare l’altra metrica MI: ogni metrica MI segue il suo filo revisionale.

4. **Storicizzazione mirata**  
   Quando arriva `Rnew` su `(Prefix, Sheet, Metrica)`:
   - sposta in **ARCHIVIO_STORICO** **solo** i file **della *stessa metrica*** con revisione `< Rnew` e **stesso sheet**;
   - **mai** toccare file di **altra metrica** (M vs I) né di **altri sheet**.

---

## Controlli formali (sempre prima)

- Nome non conforme alla regex  
- Formato non in `A..E`  
- Location non in `M,K,F,T,E,S,N,P`  
- UOM non in `M/I/D/N`  
- TIFF con orientamento non valido

➡️ **ERROR_DIR** (log specifico)

---

## Ricerca dell’ambito

Dato un file `D…RxxSyy{UOM}` in ingresso, considera **solo** i file in archivio con **stesso `Prefix` e stesso `Syy`**.  
Gli altri sheet sono irrilevanti per la decisione.

---

## Confronto revisioni (per quello sheet e metrica)

- **Nessuna revisione presente per quello sheet** → si passa alla gestione di regime (archiviazione).
- **Esiste `Rold`**:
  - `Rnew < Rold` → **ERROR_DIR** (log: *Revisione Precedente*).
  - `Rnew = Rold` → si applicano le regole di **coesistenza alla stessa R** (vedi tabella).
  - `Rnew > Rold` → **storicizza solo le revisioni più vecchie della *stessa metrica*** per quello sheet, poi archivia `Rnew`.

> 🔎 **Esempio MI**  
> Archivio: `R04S01M`, `R04S01I`. Arriva `R05S01I`.  
> Storicizza **solo** `R04S01I`. **Non** tocca `R04S01M`.  
> Quando arriverà `R05S01M`, verrà storicizzato `R04S01M`.

---

## Regole alla **stessa revisione** (stesso `R` e stesso `S`)

Azione sul **nuovo file**:

- **OK** = archivia (`PLM + dir_tif_loc + EDI`)
- **PR** = **PARI_REV_DIR** (duplicato `R+S+UOM` o cambio regime non ammesso alla stessa R)

| UOM      | Regime **MI** (M/I)                        | Regime **D-only**            | Regime **N-only**            |
|----------|--------------------------------------------|------------------------------|------------------------------|
| **M**    | **OK*** (coesiste con I)                   | **PR** (regime non MI)       | **PR** (regime non MI)       |
| **I**    | **OK*** (coesiste con M)                   | **PR** (regime non MI)       | **PR** (regime non MI)       |
| **D**    | **PR** (cambio regime non ammesso a pari R)| **OK****                     | **PR** (regime non D-only)   |
| **N**    | **PR** (cambio regime non ammesso a pari R)| **PR** (regime non N-only)   | **OK****                     |

\* **MI**: se esiste già lo **stesso `R+S+UOM`** → **PR**; se è l’**altra metrica** (M↔I) → **OK** (coesistono).  
\*\* **D-only/N-only**: se esiste già lo **stesso `R+S+UOM`** → **PR**; altrimenti → **OK**.

---

## Storicizzazione — riepilogo

- **Target selettivo**: **stessa metrica & stesso sheet** con `rev < Rnew`.
- **Mai** storicizzare:
  - file di **altra metrica M/I** quando arriva la nuova revisione dell’altra (coexist MAINTAINED);
  - file di **altri sheet**;
  - file a **stessa revisione** (gestiti come PR/OK da tabella).

---

## Esempi

- **E1** — Archivio: `R04S01M`, `R04S01I`; arriva `R05S01I`  
  **Storico**: `R04S01I` (stessa metrica).  
  **NON** tocca `R04S01M`.  
  **Archivia** `R05S01I`. (Regime MI)

- **E2** — Archivio: `R01S01M`; arriva `R03S04D`  
  Sheet diverso (`S04`) → indipendente.  
  Nessuna `Rold` per `S04` → regime `D-only` → **Archivia** `R03S04D`.

- **E3** — Archivio: `R01S01M`; arriva `R02S03N`  
  Sheet diverso (`S03`) → indipendente.  
  Nessuna `Rold` per `S03` → regime `N-only` → **Archivia** `R02S03N`.

- **E4** — Archivio: `R14S01D`; arriva `R14S01M`  
  Stessa `R` e `S`, cambio regime a pari revisione → **PR**.

---

## Messaggi di log

- `… # Rev superata # <vecchio>` — spostato in Storico **uno specifico file della *stessa metrica* e *stesso sheet***  
- `… # Metrica Diversa # <altro_R+S>` — in regime **MI**, coesistenza M/I riconosciuta  
- `… # Pari Revisione` — duplicato (`R+S+UOM`) o tentativo di cambio regime a parità di `R`  
- `… # Archiviato` — accettazione (PLM + archivio + EDI)  
- `… # Revisione Precedente # <ref>` — arrivato `Rnew < Rold`  
- `… # Nome/Formato/Location/UOM/Immagine Girata …` — errore formale → **ERROR_DIR**

---

## Diagramma (Mermaid)

```mermaid
flowchart TD
  A[Nuovo file D…RxxSyy{UOM}] --> B{Controlli formali OK?}
  B -- No --> X[ERROR_DIR]:::err
  B -- Sì --> C[Seleziona archivio con stesso Prefix+Syy]
  C --> D{Esistono file per Syy?}
  D -- No --> E[Definisci regime da UOM (MI/D-only/N-only) → ARCHIVIA]:::ok
  D -- Sì --> F[Valuta revisioni per la STESSA METRICA]
  F --> G{Rnew < max_rev(metrica,Syy)?}
  G -- Sì --> X[ERROR_DIR: Revisione Precedente]:::err
  G -- No --> H{Rnew = max_rev(metrica,Syy)?}
  H -- Sì --> I{Regole alla stessa R (tabella)}
  I -- PR --> PR[PARI_REV_DIR]:::pr
  I -- OK --> E2[ARCHIVIA]:::ok
  H -- No --> J[Storicizza SOLO rev < Rnew della STESSA METRICA e STESSO SHEET]:::stor
  J --> E2[ARCHIVIA]:::ok

  classDef ok fill:#DCFCE7,stroke:#16A34A,color:#064E3B
  classDef pr fill:#FEF9C3,stroke:#CA8A04,color:#713F12
  classDef err fill:#FEE2E2,stroke:#DC2626,color:#7F1D1D
  classDef stor fill:#E0E7FF,stroke:#4F46E5,color:#1E3A8A

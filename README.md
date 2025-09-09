# Swarky — Regole di Archiviazione (per Sheet)

Questo documento definisce la **logica di archiviazione** dei disegni gestiti da Swarky.  
La logica è **per sheet**: tutte le decisioni (confronto revisioni, coesistenza delle metriche, cambio regime) avvengono **all’interno dello stesso foglio `Syy`** per un determinato *document number* (Prefix).

---

## Nomenclatura

- **Prefix**: `D<size><loc><num>` — identifica il disegno (document number).  
  Esempio: `DCM728093`
- **R**: revisione (`Rxx`), esempio `R14`
- **S**: sheet (`Syy`), esempio `S01`
- **UOM**: metrica in `{ M, I, D, N }`

Il nome completo è:  
`D<size><loc><num>R<xx>S<yy><UOM>.(tif|pdf)`

---

## Principi chiave

1. **Ambito per sheet**  
   Per ogni coppia **(Prefix, Sheet)** può esistere **una sola revisione attiva** alla volta.

2. **Regimi di coesistenza alla stessa revisione (per quello sheet)**  
   - **MI** → possono coesistere `M` e `I` (anche sullo stesso foglio).  
   - **D-only** → soltanto `D`.  
   - **N-only** → soltanto `N`.

3. **Cambio di regime solo con incremento revisione**  
   A **parità di revisione** non si cambia regime.  
   Se **R cresce**, è consentito cambiare regime.

---

## Flusso decisionale

### 0) Controlli formali (sempre prima)
- Nome non conforme alla regex  
- Formato non in `A..E`  
- Location non in `M,K,F,T,E,S,N,P`  
- UOM non in `M/I/D/N`  
- TIFF con orientamento non valido  

➡️ **ERROR_DIR** (log specifico)

---

### 1) Individuazione dello scope
Dato un file in ingresso `D…RxxSyy{UOM}`, cerca **solo** in archivio i file con lo **stesso `Prefix` e lo stesso `Syy`**.  
Gli altri sheet (`Szz ≠ Syy`) sono **indipendenti**.

---

### 2) Confronto revisioni (per quello sheet)

- Se esiste una revisione attiva `Rold ≠ Rnew`:
  - **`Rnew > Rold`** → sposta **tutti** i file `Rold` *di quello sheet* (qualunque UOM) in **ARCHIVIO_STORICO**; poi **accetta `Rnew`** e **imposta il regime** in base al suo UOM.  
    > Così, se arriva prima `R14I` e poi `R14M`, `R13*` di quello sheet è già stata rimossa e `R14M` può coesistere con `R14I` (regime **MI**).
  - **`Rnew < Rold`** → **ERROR_DIR** (log: *“Revisione Precedente”*).
- Se non esiste `Rold` per quello sheet → vai a **3**.

---

### 3) Regime alla **stessa revisione** (per quello sheet)

- **Primo file alla revisione `Rnew` (per quello sheet)**:
  - UOM = `M` o `I` → regime = **MI** → **ARCHIVIA**
  - UOM = `D` → regime = **D-only** → **ARCHIVIA**
  - UOM = `N` → regime = **N-only** → **ARCHIVIA**

- **Altri file alla stessa `Rnew` (per quello sheet)**:
  - **Regime = MI**
    - Arriva `M` o `I`:
      - Se esiste già **stesso `R+S+UOM`** → **PARI_REV_DIR** (pari revisione)
      - Se è l’**altra metrica** (M↔I) → **ARCHIVIA** (coesistono)
    - Arriva `D` o `N` → **PARI_REV_DIR** (cambio regime non ammesso a parità di R)
  - **Regime = D-only**
    - Arriva `D`:
      - Se esiste già **stesso `R+S+UOM`** → **PARI_REV_DIR**
      - Altrimenti → **ARCHIVIA**
    - Arriva `M`, `I` o `N` → **PARI_REV_DIR** (cambio regime non ammesso)
  - **Regime = N-only**
    - Arriva `N`:
      - Se esiste già **stesso `R+S+UOM`** → **PARI_REV_DIR**
      - Altrimenti → **ARCHIVIA**
    - Arriva `M`, `I` o `D` → **PARI_REV_DIR** (cambio regime non ammesso)

> **Cambio regime con incremento revisione**  
> Se a `Rold` lo sheet era `D-only`/`N-only` e **arriva `Rnew > Rold`** con `M`/`I`, si manda in **Storico** **tutta** la `Rold` (D/N) e si **archivia `M/I`** (regime → **MI**).  
> Viceversa, se `Rnew > Rold` è `D` o `N` e `Rold` era **MI**, si manda in **Storico** tutta la `Rold` (M/I) e si **archivia `D/N`** (regime → **D-only/N-only**).

---

## Matrice UOM vs Regime (stessa `R` e stesso `S`)

Azione sul **nuovo file**:

- **OK** = archivia (`PLM + dir_tif_loc + EDI`)  
- **PR** = **PARI_REV_DIR** (duplicato o cambio regime non ammesso alla stessa R)

| UOM      | Regime **MI** (M/I) | Regime **D-only** | Regime **N-only** |
|----------|----------------------|-------------------|-------------------|
| **M**    | OK\*                 | PR                | PR                |
| **I**    | OK\*                 | PR                | PR                |
| **D**    | PR                   | OK\*\*            | PR                |
| **N**    | PR                   | PR                | OK\*\*            |

\* **MI**: se esiste già lo **stesso `R+S+UOM`** → **PR**; se è l’**altra metrica** (M↔I) → **OK**.  
\*\* **D-only/N-only**: se esiste già lo **stesso `R+S+UOM`** → **PR**; altrimenti → **OK**.

---

## Esempi

- **E1** — Archivio: `R13S01M` e `R13S01I`; arriva `R14S01I`  
  `R14 > R13` (stesso `S01`) → **Storico**: `R13S01M` e `R13S01I`; **Archivia** `R14S01I` (regime **MI**).

- **E2** — Archivio: `R01S01M`; arriva `R03S04D`  
  Sheet diverso (`S04`) → indipendente. Nessuna `Rold` per `S04` → regime = **D-only** → **Archivia** `R03S04D`.

- **E3** — Archivio: `R01S01M`; arriva `R02S03N`  
  Sheet diverso (`S03`) → indipendente. Nessuna `Rold` per `S03` → regime = **N-only** → **Archivia** `R02S03N`.

- **E4** — Archivio: `R14S01D`; arriva `R14S01M`  
  Stessa `R` e `S`, regime cambierebbe → **PR** (cambio regime **non** ammesso a parità di revisione).

---

## Messaggi di log tipici

- `… # Rev superata # <vecchio>` — spostato in Storico un file della revisione precedente **per quello sheet**  
- `… # Metrica Diversa # <altro_R+S>` — in regime **MI**, coesistenza riconosciuta  
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
  B -- Sì --> C[Seleziona archivio per stesso Prefix+Syy]
  C --> D{Esiste Rold per Syy?}
  D -- No --> E[Definisci regime da UOM (MI/D-only/N-only)\nARCHIVIA]:::ok
  D -- Sì --> F{Rnew rispetto a Rold}
  F -- Rnew < Rold --> X[ERROR_DIR: Revisione Precedente]:::err
  F -- Rnew > Rold --> G[Sposta TUTTI i file Rold di Syy\nin ARCHIVIO_STORICO]:::stor
  G --> H[Imposta regime da UOM di Rnew\nARCHIVIA]:::ok
  F -- Rnew = Rold --> I{Regime corrente di Syy}
  I --> J{UOM compatibile col regime?}
  J -- No --> PR[PARI_REV_DIR\n(cambio regime non ammesso)]:::pr
  J -- Sì --> K{Stesso R+S+UOM già presente?}
  K -- Sì --> PR
  K -- No --> E2[ARCHIVIA]:::ok

  classDef ok fill:#DCFCE7,stroke:#16A34A,color:#064E3B
  classDef pr fill:#FEF9C3,stroke:#CA8A04,color:#713F12
  classDef err fill:#FEE2E2,stroke:#DC2626,color:#7F1D1D
  classDef stor fill:#E0E7FF,stroke:#4F46E5,color:#1E3A8A

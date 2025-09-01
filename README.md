# ============================================================================
# CASISTICHE ARCHIVIAZIONE (Swarky)
# ============================================================================
#
# Definizioni:
- - Prefix = D<size><loc><num> → identifica il disegno
- - R = Revisione (Rxx)
- - S = Foglio (Syy)
- - UOM = Metrica {M, I, D, N}

# Regimi ammessi per ogni revisione (mutuamente esclusivi):
-   MI     = possono coesistere M e/o I (anche stesso foglio)
-   D-only = solo D su tutti i fogli
-   N-only = solo N su tutti i fogli
#
- In archivio deve esserci una sola revisione attiva (R). 
- Il cambio regime è consentito SOLO se arriva una revisione maggiore.
#
# ============================================================================
- FLUSSO DECISIONALE
# ============================================================================

# 0) Controlli formali
-   - Regex/nome KO, formato ≠ A..E, location ≠ M,K,F,T,E,S,N,P,
-   - UOM ≠ M/I/D/N, orientamento TIF KO
-   → ERROR_DIR (log dedicato)

# 1) Confronto tra revisioni
-   - Se esiste Rold ≠ Rnew:
-   -   • Rnew > Rold → sposta TUTTI i Rold in ARCHIVIO_STORICO,
-   --                   poi accetta Rnew e imposta nuovo regime
-   -    • Rnew < Rold → ERROR_DIR (log "Revisione Precendente")
-   - Se esistono solo file Rnew (o archivio vuoto) → vai a 2

# 2) Gestione regime per la revisione attiva (Rnew)
#   - Nessun file Rnew presente:
-   -   • UOM=M/I → regime=MI
-   -   • UOM=D   → regime=D-only
-   -   • UOM=N   → regime=N-only
-   -   → ARCHIVIA (PLM+dir_tif_loc+EDI)
-   - File Rnew già presenti (regime definito):
-   -   • UOM compatibile col regime:
-   --      - Stessa R+S+UOM già presente → PARI_REV_DIR
-   --      - Altrimenti → ARCHIVIA
-   -   • UOM incompatibile col regime:
-   --      - Se stessa R → PARI_REV_DIR (cambio regime non consentito)
-   --      - Se R maggiore → vedi punto 1 (cambio regime consentito con
-   --        archiviazione della revisione precedente)

# 3) Coesistenza per i fogli
-   - Fogli diversi (S01, S02, …) sempre ammessi nel regime attivo
-   - Regime MI: su stesso foglio possono coesistere M e I
-   - Regime D-only: solo D
-   - Regime N-only: solo N

# ============================================================================
# DESTINAZIONI FINALI
# ============================================================================
- - ARCHIVIO_STORICO → revisione superata (Rnew > Rold) oppure cambio regime
-   consentito in incremento di revisione
- - PARI_REV_DIR     → stessa R+S+UOM già presente, stesso nome file,
-   oppure tentativo di cambio regime a parità di revisione
- - ERROR_DIR        → errori formali o revisione precedente (Rnew < Rold)
- - PLM+dir_tif_loc  → archiviazione valida (sempre con generazione EDI)
# ============================================================================

===============================================================================
MATRICE UOM vs REGIME  (stessa REVISIONE R)   → azione su NUOVO file in ingresso
===============================================================================
Legenda azioni:
- OK = archivia (PLM + dir_tif_loc + EDI)
- PR = PARI_REV_DIR (se esiste già stesso R+S+UOM oppure cambio regime non ammesso)
-------------------------------------------------------------------------------
             |   Regime MI (M/I)        |   Regime D-only        |   Regime N-only
-------------+---------------------------+------------------------+------------------------
UOM = M      | OK*                       | PR (regime non M/I)    | PR (regime non M/I)
UOM = I      | OK*                       | PR (regime non M/I)    | PR (regime non M/I)
UOM = D      | PR (regime non D-only)    | OK**                    | PR (regime non D-only)
UOM = N      | PR (regime non N-only)    | PR (regime non N-only) | OK**
-------------------------------------------------------------------------------
*  In regime MI:
   - Se in archivio esiste già lo stesso R+S+UOM → PR (pari revisione).
   - Se stesso foglio ma metrica diversa (M vs I) → OK (coesistono).
** In regime D-only / N-only:
   - Se in archivio esiste già lo stesso R+S+UOM → PR (pari revisione).
   - Fogli diversi sempre OK (restando nello stesso regime).
-------------------------------------------------------------------------------

NOTA CRITICA — CAMBIO REGIME
- Il cambio di regime è **consentito solo** con **incremento di revisione**.
- Se il nuovo file implicherebbe un cambio regime ma la revisione è la stessa:
  → **PR** (pari revisione: “regime non consentito alla stessa R”).

GESTIONE REVISIONI (riassunto)
- Se R_new > R_old: sposta **tutti** i file con R_old in **ARCHIVIO_STORICO**,
  poi accetta R_new e imposta il regime in base all’UOM del nuovo file.
- Se R_new = R_old: applica la matrice qui sopra.
- Se R_new < R_old: **ERROR_DIR** (Revisione Precendente).


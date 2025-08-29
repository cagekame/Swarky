#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import sys, re, time, shutil, logging, json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

# ---- CONFIG DATACLASS ----------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    DIR_HPLOTTER: Path
    ARCHIVIO_DISEGNI: Path
    ERROR_DIR: Path
    PARI_REV_DIR: Path
    PLM_DIR: Path
    ARCHIVIO_STORICO: Path
    DIR_ISS: Path
    DIR_FIV_LOADING: Path
    DIR_HENGELO: Path
    DIR_KALT: Path
    DIR_KALT_ERRORS: Path
    DIR_TABELLARI: Path
    LOG_DIR: Optional[Path] = None
    LOG_LEVEL: int = logging.INFO
    ACCEPT_PDF: bool = True  # flag per accettazione PDF nel Plotter

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "Config":
        p = d.get("paths", {})
        def P(key: str, default: Optional[str]=None) -> Path:
            val = p.get(key, default)
            if val is None:
                raise KeyError(f"Config mancante: paths.{key}")
            return Path(val)
        log_dir = p.get("log_dir")
        return Config(
            DIR_HPLOTTER=P("hplotter"),
            ARCHIVIO_DISEGNI=P("archivio"),
            ERROR_DIR=P("error_dir"),
            PARI_REV_DIR=P("pari_rev"),
            PLM_DIR=P("plm"),
            ARCHIVIO_STORICO=P("storico"),
            DIR_ISS=P("iss"),
            DIR_FIV_LOADING=P("fiv"),
            DIR_HENGELO=P("heng"),
            DIR_KALT=P("kalt"),
            DIR_KALT_ERRORS=P("kalt_err"),
            DIR_TABELLARI=P("tab"),
            LOG_DIR=Path(log_dir) if log_dir else None,
            LOG_LEVEL=logging.INFO,
            ACCEPT_PDF=bool(d.get("ACCEPT_PDF", True)),
        )

# ---- REGEX ---------------------------------------------------------------------------

BASE_NAME = re.compile(r"D(\w)(\w)(\d{6})R(\d{2})S(\d{2})(\w)\.(tif|pdf)$", re.IGNORECASE)
ISS_BASENAME = re.compile(r"G(\d{4})(\w{3})(\d{7})ISSR(\d{2})S(\d{2})\.pdf$", re.IGNORECASE)

# ---- LOGGING -------------------------------------------------------------------------

def month_tag() -> str:
    return datetime.now().strftime("%b.%Y")

def setup_logging(cfg: Config):
    level = cfg.LOG_LEVEL
    log_dir = cfg.LOG_DIR or cfg.DIR_HPLOTTER
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"Swarky_{month_tag()}.log"
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8")
        ]
    )
    logging.debug("Log file: %s", log_file)

# ---- FS UTILS ------------------------------------------------------------------------

def normalize_extensions(folder: Path):
    for p in folder.glob("*"):
        if p.is_file():
            if p.suffix == ".TIF":
                q = p.with_suffix(".tiff"); p.rename(q); q.rename(q.with_suffix(".tif"))
            elif p.suffix.lower() == ".tiff":
                p.rename(p.with_suffix(".tif"))

def copy_to(src: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst_dir / src.name)

def move_to(src: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True); shutil.move(str(src), str(dst_dir / src.name))

def write_lines(p: Path, lines: List[str]):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

# ---- MAPPATURE, VALIDAZIONI E LOG WRITERS --------------------------------------------

LOCATION_MAP = {
    ("M", "*"): ("costruttivi", "Costruttivi", "m", "DETAIL", "Italian"),
    ("K", "*"): ("bozzetti", "Bozzetti", "k", "Customer Drawings", "English"),
    ("F", "*"): ("fornitori", "Fornitori", "f", "Vendor Supplied Data", "English"),
    ("T", "*"): ("tenute_meccaniche", "T_meccaniche", "t", "Customer Drawings", "English"),
    ("E", "*"): ("sezioni", "Sezioni", "s", "Customer Drawings", "English"),
    ("S", "*"): ("sezioni", "Sezioni", "s", "Customer Drawings", "English"),
    ("N", "*"): ("marcianise", "Marcianise", "n", "DETAIL", "Italian"),
    ("P", "*"): ("preventivi", "Preventivi", "p", "Customer Drawings", "English"),
    ("*", "4"): ("pID_ELETTRICI", "Pid_Elettrici", "m", "Customer Drawings", "Italian"),
    ("*", "5"): ("piping", "Piping", "m", "Customer Drawings", "Italian"),
}
DEFAULT_LOCATION = ("unknown", "Unknown", "m", "Customer Drawings", "English")

def map_location(m: re.Match, cfg: Config) -> dict:
    first = m.group(3)[0]
    l2 = m.group(2).upper()
    loc = (
        LOCATION_MAP.get((l2, first))
        or LOCATION_MAP.get((l2, "*"))
        or LOCATION_MAP.get(("*", first))
        or DEFAULT_LOCATION
    )
    folder, log_name, subloc, doctype, lang = loc
    arch_tif_loc = m.group(1).upper() + subloc
    dir_tif_loc = cfg.ARCHIVIO_DISEGNI / folder / arch_tif_loc
    return dict(folder=folder, log_name=log_name, subloc=subloc, doctype=doctype, lang=lang,
                arch_tif_loc=arch_tif_loc, dir_tif_loc=dir_tif_loc)

def size_from_letter(ch: str) -> str:
    return dict(A="A4",B="A3",C="A2",D="A1",E="A0").get(ch.upper(),"A4")

def uom_from_letter(ch: str) -> str:
    return dict(N="(Not applicable)",M="Metric",I="Inch",D="Dual").get(ch.upper(),"Metric")

def check_orientation_ok(tif_path: Path) -> bool:
    # i PDF li accettiamo/rigettiamo a monte via ACCEPT_PDF; niente controllo orientamento per i PDF
    if tif_path.suffix.lower() == ".pdf":
        return True
    try:
        from PIL import Image
    except ImportError:
        logging.warning("PIL non installato, impossibile verificare orientamento di %s", tif_path)
        return True
    try:
        with Image.open(tif_path) as im:
            return im.width > im.height
    except Exception:
        logging.exception("Errore durante la verifica dell'orientamento per %s", tif_path)
        return False

def log_swarky(cfg: Config, file_name: str, loc: str, process: str,
               archive_dwg: str = "", dest: str = ""):
    line = f"{file_name} # {loc} # {process} # {archive_dwg}"
    print(line)
    logging.info(line, extra={"ui": ("processed", file_name, process, archive_dwg, dest)})

def log_error(cfg: Config, file_name: str, err: str, archive_dwg: str = ""):
    line = f"{file_name} # {err} # {archive_dwg}"
    print(line)
    logging.error(line, extra={"ui": ("anomaly", file_name, err)})

# ---- EDI WRITER (UNICO) --------------------------------------------------------------

def _edi_body(
    *,
    document_no: str,
    rev: str,
    sheet: str,
    description: str,
    actual_size: str,
    uom: str,
    doctype: str,
    lang: str,
    file_name: str,
    file_type: str,
    now: Optional[str] = None
) -> List[str]:
    """Costruisce il corpo DESEDI in modo centralizzato."""
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = [
        "[Database]",
        "ServerName=ORMDB33",
        "ProjectName=FPD Engineering",
        "[DatabaseFields]",
        f"DocumentNo={document_no}",
        f"DocumentRev={rev}",
        f"SheetNumber={sheet}",
        f"Description={description}",
        f"ActualSize={actual_size}",
        "PumpModel=(UNKNOWN)",
        "OEM=Flowserve",
        "PumpSize=",
        "OrderNumber=",
        "SerialNumber=",
        f"Document_Type={doctype}",
        "DrawingClass=COMMERCIAL",
        "DesignCenter=Desio, Italy",
        "OEMSite=Desio, Italy",
        "OEMDrawingNumber=",
        f"UOM={uom}",
        f"DWGLanguage={lang}",
        "CurrentRevision=Y",
        "EnteredBy=10150286",
        "Notes=",
        "NonEnglishDesc=",
        "SupersededBy=",
        "NumberOfStages=",
        "[DrawingInfo]",
        f"DocumentNo={document_no}",
        f"SheetNumber={sheet}",
        ("Document_Type=Detail" if doctype == "DETAIL" else "Document_Type=Customer Drawings"),
        f"DocumentRev={rev}",
        f"FileName={file_name}",
        f"FileType={file_type}",
        f"Currentdate={now}",
    ]
    return header

def write_edi(
    cfg: Config,
    file_name: str,
    out_dir: Path,
    *,
    m: Optional[re.Match] = None,         # STANDARD/FIV
    iss_match: Optional[re.Match] = None, # ISS
    loc: Optional[dict] = None
) -> None:
    """
    Genera un file .DESEDI dentro out_dir per 'file_name'.
    - ISS -> passare 'iss_match'
    - STANDARD/FIV -> passare 'm' e 'loc'
    """
    edi = out_dir / (Path(file_name).stem + ".DESEDI")
    if edi.exists():
        return

    # ---- ISS
    if iss_match is not None:
        stem = Path(file_name).stem
        docno  = stem[:18] + stem[24:] if len(stem) >= 24 else stem
        rev    = iss_match.group(4)
        sheet  = iss_match.group(5)
        body = _edi_body(
            document_no = docno,
            rev         = rev,
            sheet       = sheet,
            description = " Impeller Specification Sheet",
            actual_size = "A4",
            uom         = "Metric",
            doctype     = "DETAIL",
            lang        = "English",
            file_name   = file_name,
            file_type   = "Pdf",
        )
        write_lines(edi, body)
        return

    # ---- STANDARD / FIV
    if m is None or loc is None:
        raise ValueError("write_edi: per STANDARD/FIV servono 'm' (BASE_NAME) e 'loc' (map_location)")

    document_no = f"D{m.group(1)}{m.group(2)}{m.group(3)}"
    rev         = m.group(4)
    sheet       = m.group(5)
    file_type   = "Pdf" if Path(file_name).suffix.lower() == ".pdf" else "Tiff"

    body = _edi_body(
        document_no = document_no,
        rev         = rev,
        sheet       = sheet,
        description = "",  # come versione originale
        actual_size = size_from_letter(m.group(1)),
        uom         = uom_from_letter(m.group(6)),
        doctype     = loc["doctype"],
        lang        = loc["lang"],
        file_name   = file_name,
        file_type   = file_type,
    )
    write_lines(edi, body)

# ---- PIPELINE PRINCIPALE -------------------------------------------------------------

def archive_once(cfg: Config) -> bool:
    start = time.time()
    normalize_extensions(cfg.DIR_HPLOTTER)
    did_something = False

    patterns = ["*.tif"]
    if cfg.ACCEPT_PDF:
        patterns.append("*.pdf")

    candidates: List[Path] = []
    for pat in patterns:
        candidates.extend(cfg.DIR_HPLOTTER.glob(pat))

    for p in sorted(candidates):
        did_something = True

        m = BASE_NAME.search(p.name)
        if not m:
            log_error(cfg, p.name, "Nome File Errato"); move_to(p, cfg.ERROR_DIR); continue
        if m.group(1).upper() not in "ABCDE":
            log_error(cfg, p.name, "Formato Errato"); move_to(p, cfg.ERROR_DIR); continue
        if m.group(2).upper() not in "MKFTESNP":
            log_error(cfg, p.name, "Location Errata"); move_to(p, cfg.ERROR_DIR); continue
        if m.group(6).upper() not in "MIDN":
            log_error(cfg, p.name, "Metrica Errata"); move_to(p, cfg.ERROR_DIR); continue
        if not check_orientation_ok(p):
            log_error(cfg, p.name, "Immagine Girata"); move_to(p, cfg.ERROR_DIR); continue

        new_metric = m.group(6).upper()
        loc = map_location(m, cfg)
        dir_tif_loc = loc["dir_tif_loc"]; tiflog = loc["log_name"]

        # stesso file esatto già presente
        if (dir_tif_loc / p.name).exists():
            log_error(cfg, p.name, "Pari Revisione"); move_to(p, cfg.PARI_REV_DIR); continue

        prefix = f"D{m.group(1)}{m.group(2)}{m.group(3)}"
        existing = list(dir_tif_loc.glob(f"{prefix}*"))
        beckrev = False
        for ex in existing:
            me = BASE_NAME.search(ex.name)
            if not me:
                continue

            # === NUOVO: blocco pari revisione a prescindere da foglio/metrica ===
            if me.group(4) == m.group(4):  # stessa revisione
                log_error(cfg, p.name, "Pari Revisione", ex.name)
                move_to(p, cfg.ERROR_DIR)
                beckrev = True
                break
            # ====================================================================

            ex_metric = me.group(6).upper()
            chk_sht = "Stesso Foglio" if me.group(5) == m.group(5) else "Foglio Diverso"
            chk_rev = "Nuova Revisione" if me.group(4) < m.group(4) else "Revisione Precendente"
            chk_met = "Metrica Uguale" if ex_metric == new_metric else "Metrica Diversa"

            if chk_sht == "Stesso Foglio":
                if chk_rev == "Nuova Revisione":
                    # D/N sostituiscono entrambe le metriche; M/I sostituiscono solo la stessa metrica
                    archive = (new_metric in "DN") or (ex_metric == new_metric)
                    if archive:
                        move_to(ex, cfg.ARCHIVIO_STORICO)
                        proc = "ATT.Cambio Metrica" if chk_met == "Metrica Diversa" else "Nuova Revisione"
                        log_swarky(cfg, p.name, tiflog, proc, ex.name, dest="Storico ->")
                    else:
                        log_swarky(cfg, p.name, tiflog, "Metrica Diversa", ex.name)
                else:  # Revisione precedente
                    log_error(cfg, p.name, "Revisione Precendente", ex.name)
                    move_to(p, cfg.ERROR_DIR); beckrev = True; break
            else:
                # Foglio diverso con revisione diversa: solo informativo
                log_swarky(cfg, p.name, tiflog, "Foglio Diverso", ex.name)

        if beckrev:
            continue

        copy_to(p, cfg.PLM_DIR)
        move_to(p, dir_tif_loc)
        try:
            write_edi(cfg, p.name, cfg.PLM_DIR, m=m, loc=loc)
        except Exception as e:
            logging.exception("Impossibile creare DESEDI per %s: %s", p.name, e)

        log_swarky(cfg, p.name, tiflog, "Archiviato", "", dest=tiflog)

    if did_something:
        elapsed = time.time() - start
        write_lines((cfg.LOG_DIR or cfg.DIR_HPLOTTER)/f"Swarky_{datetime.now().strftime('%b.%Y')}.log",
                    [f"ProcessTime # {elapsed:.2f}s"])
    return did_something

def iss_loading(cfg: Config):
    for p in sorted(cfg.DIR_ISS.glob("*.pdf")):
        m = ISS_BASENAME.search(p.name)
        if not m: continue
        move_to(p, cfg.PLM_DIR)
        try:
            write_edi(cfg, file_name=p.name, out_dir=cfg.PLM_DIR, iss_match=m)
        except Exception as e:
            logging.exception("Impossibile creare DESEDI (ISS) per %s: %s", p.name, e)
        now = datetime.now()
        stem = p.stem
        log = cfg.DIR_ISS/"SwarkyISS.log"
        write_lines(log, [f"{now.strftime('%d.%b.%Y')} # {now.strftime('%H:%M:%S')} # {stem}"])

def fiv_loading(cfg: Config):
    for p in sorted(cfg.DIR_FIV_LOADING.glob("*")):
        if not p.is_file(): continue
        m = BASE_NAME.search(p.name)
        if not m: continue
        loc = map_location(m, cfg)
        try:
            write_edi(cfg, m=m, file_name=p.name, loc=loc, out_dir=cfg.PLM_DIR)
        except Exception as e:
            logging.exception("Impossibile creare DESEDI (FIV) per %s: %s", p.name, e)
        move_to(p, cfg.PLM_DIR)
        log_swarky(cfg, p.name, loc["log_name"], "Fiv Loading", dest="PLM")

def count_tif_files(cfg: Config) -> dict:
    def count(d: Path, *patterns: str) -> int:
        try:
            return sum(len(list(d.glob(pat))) for pat in patterns)
        except Exception:
            return 0
    return {
        "KALT Error": count(cfg.DIR_KALT_ERRORS, "*.err"),
        "Same Rev Dwg": count(cfg.PARI_REV_DIR, "*.tif", "*.pdf"),
        "Check Dwg": count(cfg.ERROR_DIR, "*.tif", "*.pdf"),
        "Heng Dwg": count(cfg.DIR_HENGELO, "*.tif", "*.pdf"),
        "Tab Dwg": count(cfg.DIR_TABELLARI, "*.tif", "*.pdf"),
        "Kal Dwg": count(cfg.DIR_KALT, "*.tif", "*.pdf"),
    }

def run_once(cfg: Config) -> bool:
    did_something = archive_once(cfg)
    iss_loading(cfg)
    fiv_loading(cfg)
    logging.debug("Counts: %s", count_tif_files(cfg))
    return did_something

def watch_loop(cfg: Config, interval: int):
    logging.info("Watch ogni %ds...", interval)
    while True:
        run_once(cfg); time.sleep(interval)

# ---- CLI -----------------------------------------------------------------------------

def parse_args(argv: List[str]):
    import argparse
    ap = argparse.ArgumentParser(description="Swarky - batch archiviazione/EDI")
    ap.add_argument("--watch", type=int, default=0, help="Loop di polling in secondi, 0=una sola passata")
    return ap.parse_args(argv)

def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Config non trovato: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Config.from_json(data)

def main(argv: List[str]):
    args = parse_args(argv)
    cfg = load_config(Path("config.json"))
    setup_logging(cfg)
    if args.watch > 0:
        watch_loop(cfg, args.watch)
    else:
        run_once(cfg)

if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print("Interrotto")

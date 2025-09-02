#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import sys, re, time, shutil, logging, json, os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from perf import timeit

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
ISS_BASENAME = re.compile(r"G(\d{4})([A-Za-z0-9]{4})([A-Za-z0-9]{6})ISSR(\d{2})S(\d{2})\.pdf$", re.IGNORECASE)

# ---- LISTA PER FOGlIO (unica query) -------------------------------------------------
import glob
from functools import lru_cache

def _docno_from_match(m: re.Match) -> str:
    return f"D{m.group(1)}{m.group(2)}{m.group(3)}"

@lru_cache(maxsize=16384)
def _glob_names(dirp_str: str, pattern: str) -> tuple[str, ...]:
    patt = os.path.join(dirp_str, pattern)
    return tuple(os.path.basename(p) for p in glob.iglob(patt))

def _clear_glob_cache():
    _glob_names.cache_clear()

def _parse_prefixed(names: tuple[str, ...]) -> list[tuple[str, str, str, str]]:
    """-> [(rev, name, metric, sheet)]"""
    out: list[tuple[str, str, str, str]] = []
    for nm in names:
        mm = BASE_NAME.fullmatch(nm)
        if mm:
            out.append((mm.group(4), nm, mm.group(6).upper(), mm.group(5)))
    return out

def _list_same_doc_same_sheet(dirp: Path, m: re.Match, sheet: str) -> list[tuple[str,str,str,str]]:
    """Unica query SMB: stesso docno + stesso foglio (qualsiasi rev/metrica)."""
    docno = _docno_from_match(m)
    names = _glob_names(str(dirp), f"{docno}R??S{sheet}*")
    return _parse_prefixed(names)

# ---- PROBE (derivati dalla lista unica) ---------------------------------------------
def _probe_max_rev_same_sheet_from_list(parsed: list[tuple[str,str,str,str]]) -> Optional[str]:
    if not parsed:
        return None
    mx = None
    for r, _, _, _ in parsed:
        if (mx is None) or (r > mx):
            mx = r
    return mx

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
            logging.FileHandler(log_file, encoding="utf-8")
        ]
    )
    logging.debug("Log file: %s", log_file)

# ---- FS UTILS ------------------------------------------------------------------------

# hardlink se possibile, fallback a copy2
def _fast_copy_or_link(src: Path, dst: Path):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)

def copy_to(src: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    _fast_copy_or_link(src, dst_dir / src.name)

def move_to(src: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst_dir / src.name))

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

# ---- ORIENTAMENTO TIFF: parser header-only -------------------------------

_ORIENT_CACHE: dict[tuple[str, float], bool] = {}

def clear_orientation_cache() -> None:
    _ORIENT_CACHE.clear()

def _tiff_read_size_vfast(path: Path) -> Optional[Tuple[int,int]]:
    """Legge solo header/IFD per (width,height) Supporta II/MM, SHORT/LONG."""
    import struct
    try:
        with open(path, 'rb') as f:
            hdr = f.read(8)
            if len(hdr) < 8:
                return None
            endian = hdr[:2]
            if endian == b'II':
                u16 = lambda b: struct.unpack('<H', b)[0]
                u32 = lambda b: struct.unpack('<I', b)[0]
            elif endian == b'MM':
                u16 = lambda b: struct.unpack('>H', b)[0]
                u32 = lambda b: struct.unpack('>I', b)[0]
            else:
                return None
            if u16(hdr[2:4]) != 42:
                return None
            ifd_off = u32(hdr[4:8])
            f.seek(ifd_off)
            nbytes = f.read(2)
            if len(nbytes) < 2:
                return None
            n = u16(nbytes)
            TAG_W, TAG_H = 256, 257
            TYPE_SIZES = {1:1,2:1,3:2,4:4,5:8,7:1,9:4,10:8}
            w = h = None
            for _ in range(n):
                ent = f.read(12)
                if len(ent) < 12:
                    break
                tag = u16(ent[0:2]); typ = u16(ent[2:4]); cnt = u32(ent[4:8]); val = ent[8:12]
                unit = TYPE_SIZES.get(typ)
                if not unit:
                    continue
                datasz = unit * cnt
                if datasz <= 4:
                    if typ == 3: v = u16(val[0:2])
                    elif typ == 4: v = u32(val)
                    else: continue
                else:
                    off = u32(val); cur = f.tell()
                    f.seek(off); raw = f.read(unit); f.seek(cur)
                    if typ == 3: v = u16(raw)
                    elif typ == 4: v = u32(raw)
                    else: continue
                if tag == TAG_W: w = v
                elif tag == TAG_H: h = v
                if w is not None and h is not None:
                    return (w, h)
    except Exception:
        return None
    return None

def check_orientation_ok(tif_path: Path) -> bool:
    """True se (width > height) o se è un PDF."""
    if tif_path.suffix.lower() == ".pdf":
        return True
    try:
        key = (str(tif_path), tif_path.stat().st_mtime)
        if key in _ORIENT_CACHE:
            return _ORIENT_CACHE[key]
    except Exception:
        key = None
    wh = _tiff_read_size_vfast(tif_path)
    if wh is None:
        res = True
    else:
        w, h = wh
        res = (w > h)
    if key:
        _ORIENT_CACHE[key] = res
    return res

def log_swarky(cfg: Config, file_name: str, loc: str, process: str,
               archive_dwg: str = "", dest: str = ""):
    line = f"{file_name} # {loc} # {process} # {archive_dwg}"
    logging.info(line, extra={"ui": ("processed", file_name, process, archive_dwg, dest)})

def log_error(cfg: Config, file_name: str, err: str, archive_dwg: str = ""):
    line = f"{file_name} # {err} # {archive_dwg}"
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
    edi = out_dir / (Path(file_name).stem + ".DESEDI")
    if edi.exists():
        return
    if iss_match is not None:
        g1 = iss_match.group(1); g2 = iss_match.group(2); g3 = iss_match.group(3)
        rev = iss_match.group(4); sheet = iss_match.group(5)
        docno = f"G{g1}{g2}{g3}"
        body = _edi_body(
            document_no=docno, rev=rev, sheet=sheet,
            description=" Impeller Specification Sheet",
            actual_size="A4", uom="Metric", doctype="DETAIL", lang="English",
            file_name=file_name, file_type="Pdf",
        )
        write_lines(out_dir / (Path(file_name).stem + ".DESEDI"), body)
        return
    if m is None or loc is None:
        raise ValueError("write_edi: per STANDARD/FIV servono 'm' (BASE_NAME) e 'loc' (map_location)")
    document_no = f"D{m.group(1)}{m.group(2)}{m.group(3)}"
    rev = m.group(4); sheet = m.group(5)
    file_type = "Pdf" if Path(file_name).suffix.lower() == ".pdf" else "Tiff"
    body = _edi_body(
        document_no=document_no, rev=rev, sheet=sheet, description="",
        actual_size=size_from_letter(m.group(1)), uom=uom_from_letter(m.group(6)),
        doctype=loc["doctype"], lang=loc["lang"],
        file_name=file_name, file_type=file_type,
    )
    write_lines(edi, body)

# ---- ENUM UNA VOLTA PER CARTELLA + UPDATE IN-PLACE (stile VB) ----------------------
import threading
from collections import defaultdict

# Cache della cartella: dir -> tuple(names)
_DIR_LIST_CACHE: dict[str, tuple[str, ...]] = {}
_DIR_CACHE_LOCKS: dict[str, threading.Lock] = defaultdict(threading.Lock)
_DIR_CACHE_MUTEX = threading.Lock()

def _dir_key(dirp: Path) -> str:
    return str(dirp)

def _ensure_dir_listing(dirp: Path) -> tuple[str, ...]:
    """
    Se la cartella non è in cache: fa UNA sola os.scandir(dirp) e memorizza SOLO i nomi (.tif/.pdf).
    Se è già in cache: ritorna i nomi dalla RAM (0 ms).
    """
    key = _dir_key(dirp)
    with _DIR_CACHE_MUTEX:
        cur = _DIR_LIST_CACHE.get(key)
        if cur is not None:
            return cur
    # Lock per evitare doppia enumerazione in parallelo sulla stessa cartella
    with _DIR_CACHE_LOCKS[key]:
        with _DIR_CACHE_MUTEX:
            cur = _DIR_LIST_CACHE.get(key)
            if cur is not None:
                return cur
        names: list[str] = []
        try:
            with os.scandir(dirp) as it:
                for de in it:
                    if de.is_file():
                        suf = os.path.splitext(de.name)[1].lower()
                        if suf in (".tif", ".pdf"):
                            names.append(de.name)
        except FileNotFoundError:
            names = []
        tup = tuple(names)
        with _DIR_CACHE_MUTEX:
            _DIR_LIST_CACHE[key] = tup
        return tup

def _dir_cache_remove_name(dirp: Path, name: str) -> None:
    """Rimuove 'name' dalla cache della cartella (se presente) SENZA rifare scandir."""
    key = _dir_key(dirp)
    with _DIR_CACHE_MUTEX:
        cur = _DIR_LIST_CACHE.get(key)
        if not cur or name not in cur:
            return
        lst = list(cur)
        try:
            lst.remove(name)
        except ValueError:
            pass
        _DIR_LIST_CACHE[key] = tuple(lst)

def _dir_cache_add_name(dirp: Path, name: str) -> None:
    """Aggiunge 'name' alla cache se la cartella è già stata enumerata (niente scandir)."""
    key = _dir_key(dirp)
    with _DIR_CACHE_MUTEX:
        cur = _DIR_LIST_CACHE.get(key)
        if cur is None:
            # Non forziamo scandir qui: ci penserà _ensure_dir_listing quando servirà.
            return
        if name in cur:
            return
        _DIR_LIST_CACHE[key] = cur + (name,)

def _docno_from_match(m: re.Match) -> str:
    return f"D{m.group(1)}{m.group(2)}{m.group(3)}"

def _list_same_doc_same_sheet_from_cache(dirp: Path, m: re.Match, sheet: str) -> list[tuple[str,str,str,str]]:
    """
    Usa SOLO la cache della cartella (se manca, crea una volta con _ensure_dir_listing)
    e filtra in RAM: [(rev, name, metric, sheet)] per docno+sheet.
    """
    listing = _ensure_dir_listing(dirp)
    docno = _docno_from_match(m)
    prefix = f"{docno}R"
    out: list[tuple[str,str,str,str]] = []
    for nm in listing:
        if not nm.startswith(prefix):
            continue
        mm = BASE_NAME.fullmatch(nm)
        if not mm:
            continue
        if mm.group(5) != sheet:
            continue
        out.append((mm.group(4), nm, mm.group(6).upper(), mm.group(5)))
    return out

# ---- PIPELINE PRINCIPALE -------------------------------------------------------------

def _iter_candidates(dirp: Path, accept_pdf: bool):
    exts = {".tif"}
    if accept_pdf:
        exts.add(".pdf")
    with os.scandir(dirp) as it:
        for de in it:
            if de.is_file():
                suf = os.path.splitext(de.name)[1].lower()
                if suf in exts:
                    yield Path(de.path)

def archive_once(cfg: Config) -> bool:
    start = time.time()
    clear_orientation_cache()
    did_something = False

    with timeit("scan candidati (hplotter)"):
        candidates: List[Path] = list(_iter_candidates(cfg.DIR_HPLOTTER, cfg.ACCEPT_PDF))

    for p in candidates:
        did_something = True

        # normalizzazione estensione on-the-fly
        suf = p.suffix
        if suf == ".TIF":
            q = p.with_suffix(".tif")
            try: p.rename(q); p = q
            except Exception: pass
        elif suf.lower() == ".tiff":
            q = p.with_suffix(".tif")
            try: p.rename(q); p = q
            except Exception: pass

        name = p.name
        with timeit(f"{name} regex+validate"):
            m = BASE_NAME.fullmatch(name)
            if not m:
                log_error(cfg, name, "Nome File Errato"); move_to(p, cfg.ERROR_DIR); continue
            if m.group(1).upper() not in "ABCDE":
                log_error(cfg, name, "Formato Errato"); move_to(p, cfg.ERROR_DIR); continue
            if m.group(2).upper() not in "MKFTESNP":
                log_error(cfg, name, "Location Errata"); move_to(p, cfg.ERROR_DIR); continue
            if m.group(6).upper() not in "MIDN":
                log_error(cfg, name, "Metrica Errata"); move_to(p, cfg.ERROR_DIR); continue

        new_rev    = m.group(4)
        new_sheet  = m.group(5)
        new_metric = m.group(6).upper()

        with timeit(f"{name} map_location"):
            loc = map_location(m, cfg)
            dir_tif_loc = loc["dir_tif_loc"]
            tiflog      = loc["log_name"]

        # === UNA SOLA ENUM PER CARTELLA (se serve), poi TUTTO IN RAM ==================
        with timeit(f"{name} list_same_doc_same_sheet"):
            same_sheet = _list_same_doc_same_sheet_from_cache(dir_tif_loc, m, new_sheet)

        with timeit(f"{name} derive_same_rs"):
            same_rs = [(r, nm, met, sh) for (r, nm, met, sh) in same_sheet if r == new_rev]

        # 1) Pari revisione (stesso nome già presente?)
        with timeit(f"{name} check_same_filename (early)"):
            if any(nm == name for _, nm, _, _ in same_rs):
                log_error(cfg, name, "Pari Revisione")
                move_to(p, cfg.PARI_REV_DIR)
                # aggiornamento in-place cache sorgente/destinazione non necessario per prestazioni
                continue

        # 2) Max revisione dal RAM
        with timeit(f"{name} probe_max_rev_same_sheet"):
            max_rev_same_sheet = None
            for r, _, _, _ in same_sheet:
                if (max_rev_same_sheet is None) or (r > max_rev_same_sheet):
                    max_rev_same_sheet = r

        # 3) Decisioni revisione
        with timeit(f"{name} rev_decision"):
            if max_rev_same_sheet is not None:
                if new_rev < max_rev_same_sheet:
                    ref = next((nm for r, nm, _, _ in same_sheet if r == max_rev_same_sheet), "")
                    log_error(cfg, name, "Revisione Precendente", ref)
                    move_to(p, cfg.ERROR_DIR)
                    continue
                elif new_rev > max_rev_same_sheet:
                    # Sposta in storico tutte le rev < new_rev per lo stesso sheet
                    with timeit(f"{name} move_old_revs_same_sheet"):
                        for r, nm, _, _ in same_sheet:
                            if int(r) < int(new_rev):
                                old_path = dir_tif_loc / nm
                                if old_path.exists():
                                    move_to(old_path, cfg.ARCHIVIO_STORICO)
                                    log_swarky(cfg, name, tiflog, "Rev superata", nm, dest="Storico")
                                    # === UPDATE IN-PLACE: il file non è più in questa cartella
                                    _dir_cache_remove_name(dir_tif_loc, nm)
                else:
                    # stessa rev & sheet -> metrica diversa?
                    other = next((nm for _, nm, met, _ in same_rs if met != new_metric), None)
                    if other:
                        log_swarky(cfg, name, tiflog, "Metrica Diversa", other)

        # 4) ACCETTAZIONE finale
        def accept_with_logs():
            with timeit(f"{name} orientamento"):
                if not check_orientation_ok(p):
                    log_error(cfg, name, "Immagine Girata")
                    move_to(p, cfg.ERROR_DIR)
                    return

            with timeit(f"{name} move_to_archivio"):
                move_to(p, dir_tif_loc)
                new_path = dir_tif_loc / name
                # === UPDATE IN-PLACE: ora questo nome esiste nella cartella
                _dir_cache_add_name(dir_tif_loc, name)

            with timeit(f"{name} link/copy_to_PLM"):
                try:
                    _fast_copy_or_link(new_path, cfg.PLM_DIR / name)
                except Exception as e:
                    logging.exception("PLM copy/link fallita per %s: %s", new_path, e)

            with timeit(f"{name} write_EDI"):
                try:
                    write_edi(cfg, name, cfg.PLM_DIR, m=m, loc=loc)
                except Exception as e:
                    logging.exception("Impossibile creare DESEDI per %s: %s", name, e)

            log_swarky(cfg, name, tiflog, "Archiviato", "", dest=tiflog)

        with timeit(f"{name} accept"):
            accept_with_logs()
            continue

    if did_something:
        elapsed = time.time() - start
        write_lines((cfg.LOG_DIR or cfg.DIR_HPLOTTER) / f"Swarky_{datetime.now().strftime('%b.%Y')}.log",
                    [f"ProcessTime # {elapsed:.2f}s"])
        logging.info("TIMER %-40s %8.1f ms", "TOTAL archive_once", elapsed * 1000.0)
    return did_something

# ---- ISS / FIV ----------------------------------------------------------------------

def iss_loading(cfg: Config):
    try:
        candidates = [p for p in cfg.DIR_ISS.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    except Exception as e:
        logging.exception("ISS: impossibile leggere la cartella %s: %s", cfg.DIR_ISS, e)
        return
    for p in candidates:
        m = ISS_BASENAME.fullmatch(p.name)
        if not m:
            log_error(cfg, p.name, "Nome ISS Errato")
            continue
        try:
            move_to(p, cfg.PLM_DIR)
            write_edi(cfg, file_name=p.name, out_dir=cfg.PLM_DIR, iss_match=m)
            log_swarky(cfg, p.name, "ISS", "ISS", "", "")
        except Exception as e:
            logging.exception("Impossibile processare ISS %s: %s", p.name, e)
        try:
            now = datetime.now()
            stem = p.stem
            log = cfg.DIR_ISS / "SwarkyISS.log"
            write_lines(log, [f"{now.strftime('%d.%b.%Y')} # {now.strftime('%H:%M:%S')} # {stem}"])
        except Exception:
            logging.exception("ISS: impossibile aggiornare SwarkyISS.log")

def fiv_loading(cfg: Config):
    try:
        files = [p for p in cfg.DIR_FIV_LOADING.iterdir() if p.is_file()]
    except Exception as e:
        logging.exception("FIV: lettura cartella fallita: %s", e)
        return
    for p in files:
        ext = p.suffix.lower()
        if ext not in (".tif", ".tiff") and not (cfg.ACCEPT_PDF and ext == ".pdf"):
            continue
        m = BASE_NAME.fullmatch(p.name)
        if not m:
            log_error(cfg, p.name, "Nome FIV Errato")
            continue
        loc = map_location(m, cfg)
        try:
            write_edi(cfg, m=m, file_name=p.name, loc=loc, out_dir=cfg.PLM_DIR)
            move_to(p, cfg.PLM_DIR)
            log_swarky(cfg, p.name, "FIV", "FIV loading", "", "")
        except Exception as e:
            logging.exception("Impossibile processare FIV %s: %s", p.name, e)

# ---- STATS --------------------------------------------------------------------------

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

# ---- LOOP ----------------------------------------------------------------------------

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

from perf import enable

def main(argv: List[str]):
    args = parse_args(argv)
    cfg = load_config(Path("config.json"))
    setup_logging(cfg)

    enable(True)  # attiva i timer (puoi disattivarli da perf.enable(False))

    if args.watch > 0:
        watch_loop(cfg, args.watch)
    else:
        run_once(cfg)

if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print("Interrotto")

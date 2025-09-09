#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import sys, re, time, shutil, logging, json, os, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
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
    DIR_PLM_ERROR: Path
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
            DIR_PLM_ERROR=P("error_plm"),
            DIR_TABELLARI=P("tab"),
            LOG_DIR=Path(log_dir) if log_dir else None,
            LOG_LEVEL=logging.INFO,
            ACCEPT_PDF=bool(d.get("ACCEPT_PDF", True)),
        )

# ---- REGEX ---------------------------------------------------------------------------

BASE_NAME = re.compile(r"D(\w)(\w)(\d{6})R(\d{2})S(\d{2})(\w)\.(tif|pdf)$", re.IGNORECASE)
ISS_BASENAME = re.compile(r"G(\d{4})([A-Za-z0-9]{4})([A-Za-z0-9]{6})ISSR(\d{2})S(\d{2})\.pdf$", re.IGNORECASE)

# ---- PREFISSO DOCNO: LISTA NOMI SENZA ENUM COMPLETA -------------------------

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes as wt

    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    FILE_ATTRIBUTE_DIRECTORY = 0x10
    FIND_FIRST_EX_LARGE_FETCH = 2
    FindExInfoBasic = 1
    FindExSearchNameMatch = 0
    ERROR_FILE_NOT_FOUND = 2
    ERROR_PATH_NOT_FOUND = 3

    class WIN32_FIND_DATAW(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wt.DWORD),
            ("ftCreationTime", wt.FILETIME),
            ("ftLastAccessTime", wt.FILETIME),
            ("ftLastWriteTime", wt.FILETIME),
            ("nFileSizeHigh", wt.DWORD),
            ("nFileSizeLow", wt.DWORD),
            ("dwReserved0", wt.DWORD),
            ("dwReserved1", wt.DWORD),
            ("cFileName", ctypes.c_wchar * 260),
            ("cAlternateFileName", ctypes.c_wchar * 14),
        ]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _FindFirstFileW = _k32.FindFirstFileW
    _FindFirstFileW.argtypes = [wt.LPCWSTR, ctypes.POINTER(WIN32_FIND_DATAW)]
    _FindFirstFileW.restype = wt.HANDLE
    _FindNextFileW = _k32.FindNextFileW
    _FindNextFileW.argtypes = [wt.HANDLE, ctypes.POINTER(WIN32_FIND_DATAW)]
    _FindNextFileW.restype = wt.BOOL
    _FindClose = _k32.FindClose
    _FindClose.argtypes = [wt.HANDLE]
    _FindClose.restype = wt.BOOL
    try:
        _FindFirstFileExW = _k32.FindFirstFileExW
        _FindFirstFileExW.argtypes = [
            wt.LPCWSTR,
            ctypes.c_int,
            ctypes.POINTER(WIN32_FIND_DATAW),
            ctypes.c_int,
            ctypes.c_void_p,
            wt.DWORD,
        ]
        _FindFirstFileExW.restype = wt.HANDLE
    except AttributeError:
        _FindFirstFileExW = None

    def _win_find_names(dirp: Path, pattern: str) -> tuple[str, ...]:
        """Ritorna i NOMI file che matchano pattern in dirp, match lato server (veloce su SMB)."""
        query = str(dirp / pattern)
        data = WIN32_FIND_DATAW()
        h = _FindFirstFileW(query, ctypes.byref(data))
        if h == INVALID_HANDLE_VALUE:
            return tuple()
        names: list[str] = []
        try:
            while True:
                nm = data.cFileName
                if nm not in (".", "..") and not (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY):
                    names.append(nm)
                if not _FindNextFileW(h, ctypes.byref(data)):
                    break
        finally:
            _FindClose(h)
        return tuple(names)

    def _win_find_names_ex(dirp: Path, pattern: str) -> tuple[str, ...]:
        """Usa FindFirstFileExW con LARGE_FETCH per ridurre i round-trip SMB; fallback a _win_find_names."""
        if _FindFirstFileExW is None:
            return _win_find_names(dirp, pattern)
        query = str(dirp / pattern)
        data = WIN32_FIND_DATAW()
        h = _FindFirstFileExW(
            query,
            FindExInfoBasic,
            ctypes.byref(data),
            FindExSearchNameMatch,
            None,
            FIND_FIRST_EX_LARGE_FETCH,
        )
        if h == INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            if err in (ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND):
                # evitare il fallback su "no match" riduce round-trip SMB
                return tuple()
            return _win_find_names(dirp, pattern)
        names: list[str] = []
        try:
            while True:
                nm = data.cFileName
                if nm not in (".", "..") and not (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY):
                    names.append(nm)
                if not _FindNextFileW(h, ctypes.byref(data)):
                    break
        finally:
            _FindClose(h)
        return tuple(names)

else:
    def _win_find_names(dirp: Path, pattern: str) -> tuple[str, ...]:
        """Enumerazione base via glob quando WinAPI non è disponibile."""
        return tuple(p.name for p in dirp.glob(pattern))

    def _win_find_names_ex(dirp: Path, pattern: str) -> tuple[str, ...]:
        """Fallback trasparente a _win_find_names su piattaforme non Windows."""
        return _win_find_names(dirp, pattern)

def _docno_from_match(m: re.Match) -> str:
    return f"D{m.group(1)}{m.group(2)}{m.group(3)}"

def _parse_prefixed(names: tuple[str, ...]) -> list[tuple[str, str, str, str]]:
    """-> [(rev, name, metric, sheet)]  (rev='02', metric in {M,I,D,N}, sheet='01')"""
    out: list[tuple[str, str, str, str]] = []
    for nm in names:
        mm = BASE_NAME.fullmatch(nm)
        if mm:
            out.append((mm.group(4), nm, mm.group(6).upper(), mm.group(5)))
    return out

def _list_same_doc_prefisso(dirp: Path, m: re.Match) -> list[tuple[str, str, str, str]]:
    """Riduce i round-trip SMB enumerando docno* una sola volta e filtrando in RAM, senza ordinare."""
    docno = _docno_from_match(m)
    names_all = _win_find_names_ex(dirp, f"{docno}*")
    if not names_all:
        return []
    names = tuple(
        nm
        for nm in names_all
        if nm.lower().endswith((".tif", ".pdf"))
    )
    # la validazione regex è demandata a _parse_prefixed
    return _parse_prefixed(names)

_DOC_LOCKS: Dict[tuple[str, str], threading.Lock] = {}
_DOC_LOCKS_MASTER = threading.Lock()

def _doc_key(dir_tif_loc: Path, m: re.Match) -> tuple[str, str]:
    # usa path normalizzato senza accesso I/O e il document number D.. (senza R/S)
    base = os.path.normcase(os.fspath(dir_tif_loc))
    return (base, f"D{m.group(1)}{m.group(2)}{m.group(3)}")

def _get_doc_lock(dir_tif_loc: Path, m: re.Match) -> threading.Lock:
    key = _doc_key(dir_tif_loc, m)
    with _DOC_LOCKS_MASTER:
        lock = _DOC_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _DOC_LOCKS[key] = lock
    return lock

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

def _robocopy_ok(rc: int) -> bool:
    # Robocopy: 0..7 = successi/avvisi; >=8 = errori
    return rc < 8

def _robocopy_file(src: Path, dst_dir: Path, *, move: bool = False) -> None:
    """
    Copia/sposta un singolo file (stesso nome) in dst_dir con Robocopy.
    /COPY:D (solo dati), /R:1 /W:1 (snello),
    /NFL /NDL /NP (output asciutto), /MT, /J solo per file grandi, /MOV se move=True.
    Robocopy salta i file già identici di default, quindi niente /IS.
    """
    src = Path(src)
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    size = os.stat(src).st_size
    mt_env = os.environ.get("SWARKY_ROBOCOPY_MT", "16")
    try:
        mt = int(mt_env)
    except ValueError:
        mt = 16
    mt = max(1, min(mt, 128))
    cmd = [
        "robocopy",
        str(src.parent),
        str(dst_dir),
        src.name,
        "/COPY:D",  # solo dati; niente /IS: robocopy salta i file 'same'
        "/R:1", "/W:1",
        "/NFL", "/NDL", "/NP",
        f"/MT:{mt}",  # /MT accelera i file grandi
    ]
    if size >= 32 * 1024 * 1024:
        cmd.append("/J")  # /J è utile solo su file grandi (I/O non bufferizzato)
    if move:
        cmd.append("/MOV")
    # NON usare text=True: l'output di robocopy è in code page OEM, evita decode qui
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
    if not _robocopy_ok(res.returncode):
        # Decodifica 'safe' per log/errore senza crash (latin-1 accetta tutti i byte 0-255)
        out = ""
        try:
            out = res.stdout.decode("latin-1", "replace")
        except Exception:
            pass
        raise RuntimeError(f"ROBOCOPY failed ({res.returncode}) for {src} -> {dst_dir}: {out}")


def _is_same_file(src: Path, dst: Path, *, mtime_slack_ns: int = 2_000_000_000) -> bool:
    """Ritorna True se dst esiste ed è 'identico' a src (stessa size e mtime entro una tolleranza)."""
    try:
        s1 = os.stat(src)
        s2 = os.stat(dst)
    except OSError:
        return False
    return s1.st_size == s2.st_size and abs(s1.st_mtime_ns - s2.st_mtime_ns) <= mtime_slack_ns

def _fast_copy_or_link(src: Path, dst: Path):
    """Prova hardlink, altrimenti copia SOLO i dati (niente metadati)."""
    try:
        os.link(src, dst)              # istantaneo se stesso volume/share
    except OSError:
        # Volumi diversi / share → usa Robocopy (dir→dir con filtro file)
        dest_path = Path(dst)
        if _is_same_file(src, dest_path):
            # Pre-check: se il file di destinazione è già identico, evita robocopy.
            # Solo per copia: negli spostamenti servono comunque le delete.
            return
        _robocopy_file(src, dest_path.parent, move=False)

def copy_to(src: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    _fast_copy_or_link(src, dst_dir / src.name)

def move_to(src: Path, dst_dir: Path):
    """
    Sposta con rename atomico se possibile; se fallisce (volumi diversi),
    usa Robocopy (copia + delete della sorgente).
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    try:
        os.replace(src, dst)           # veloce sullo stesso volume/share
    except OSError:
        # Volumi diversi / rete → sposta con Robocopy (copia+delete)
        _robocopy_file(src, dst_dir, move=True)

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
_ORIENT_LOCK = threading.Lock()

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
    except Exception:
        key = None
    if key is not None:
        with _ORIENT_LOCK:
            cached = _ORIENT_CACHE.get(key)
        if cached is not None:
            return cached
    wh = _tiff_read_size_vfast(tif_path)
    if wh is None:
        res = True
    else:
        w, h = wh
        res = (w > h)
    if key is not None:
        with _ORIENT_LOCK:
            _ORIENT_CACHE[key] = res
    return res

def log_swarky(cfg: Config, file_name: str, loc: str, process: str,
               archive_dwg: str = "", dest: str = ""):
    line = f"{file_name} # {loc} # {process} # {archive_dwg}"
    logging.info(line, extra={"ui": ("processed", file_name, process, archive_dwg, dest)})

def log_error(cfg: Config, file_name: str, err: str, archive_dwg: str = ""):
    line = f"{file_name} # {err} # {archive_dwg}"
    logging.error(line, extra={"ui": ("anomaly", file_name, err)})

# ---- EDI WRITER --------------------------------------------------------------

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

# ---- STORICO: routing in sottocartelle DA/DB/DC/DD/DE/... ----------------------------

def _storico_dest_dir_for_name(cfg: Config, nm: str) -> Path:
    """
    Ritorna la cartella dello Storico corretta in base al prefisso (D + lettera formato):
      es. DA?123456... -> <ARCHIVIO_STORICO>/DA
          DC?123456... -> <ARCHIVIO_STORICO>/DC
    """
    mm = BASE_NAME.fullmatch(nm)
    if not mm:
        return cfg.ARCHIVIO_STORICO / "unknown"
    return cfg.ARCHIVIO_STORICO / f"D{mm.group(1).upper()}"

# ---- PIPELINE PRINCIPALE -------------------------------------------------------------

def _iter_candidates(dirp: Path, accept_pdf: bool):
    # Scansione solo della cartella Plotter (locale o comunque input): ok
    exts = {".tif"}
    if accept_pdf:
        exts.add(".pdf")
    with os.scandir(dirp) as it:
        for de in it:
            if de.is_file():
                suf = os.path.splitext(de.name)[1].lower()
                if suf in exts:
                    yield Path(de.path)

def _process_candidate(p: Path, cfg: Config) -> bool:
    try:
        suf = p.suffix
        if suf == ".TIF":
            q = p.with_suffix(".tif")
            try:
                p.rename(q)
                p = q
            except Exception:
                pass
        elif suf.lower() == ".tiff":
            q = p.with_suffix(".tif")
            try:
                p.rename(q)
                p = q
            except Exception:
                pass

        name = p.name
        with timeit(f"{name} regex+validate"):
            m = BASE_NAME.fullmatch(name)
            if not m:
                log_error(cfg, name, "Nome File Errato")
                move_to(p, cfg.ERROR_DIR)
                return True
            if m.group(1).upper() not in "ABCDE":
                log_error(cfg, name, "Formato Errato")
                move_to(p, cfg.ERROR_DIR)
                return True
            if m.group(2).upper() not in "MKFTESNP":
                log_error(cfg, name, "Location Errata")
                move_to(p, cfg.ERROR_DIR)
                return True
            if m.group(6).upper() not in "MIDN":
                log_error(cfg, name, "Metrica Errata")
                move_to(p, cfg.ERROR_DIR)
                return True

        new_rev = m.group(4)
        new_sheet = m.group(5)
        new_metric = m.group(6).upper()

        with timeit(f"{name} map_location"):
            loc = map_location(m, cfg)
            dir_tif_loc = loc["dir_tif_loc"]
            tiflog = loc["log_name"]

        with timeit(f"{name} accept"):
            lock = _get_doc_lock(dir_tif_loc, m)
            with lock:
                with timeit(f"{name} check_same_filename (exists-fast)"):
                    if (dir_tif_loc / name).exists():
                        log_error(cfg, name, "Pari Revisione")
                        move_to(p, cfg.PARI_REV_DIR)
                        return True

                with timeit(f"{name} list_same_doc_prefisso"):
                    same_doc = _list_same_doc_prefisso(dir_tif_loc, m)

                with timeit(f"{name} derive_same_sheet"):
                    same_sheet = [(r, nm, met, sh) for (r, nm, met, sh) in same_doc if sh == new_sheet]

                with timeit(f"{name} derive_same_rs"):
                    same_rs = [(r, nm, met, sh) for (r, nm, met, sh) in same_sheet if r == new_rev]

                with timeit(f"{name} check_same_filename (list-verify)"):
                    if any(nm == name for _, nm, _, _ in same_rs):
                        log_error(cfg, name, "Pari Revisione")
                        move_to(p, cfg.PARI_REV_DIR)
                        return True

                with timeit(f"{name} probe_max_rev_same_sheet"):
                    max_rev_same_sheet = None
                    for r, _, _, _ in same_sheet:
                        if (max_rev_same_sheet is None) or (int(r) > int(max_rev_same_sheet)):
                            max_rev_same_sheet = r

                with timeit(f"{name} rev_decision"):
                    if max_rev_same_sheet is not None:
                        if int(new_rev) < int(max_rev_same_sheet):
                            ref = next((nm for r, nm, _, _ in same_sheet if r == max_rev_same_sheet), "")
                            log_error(cfg, name, "Revisione Precendente", ref)
                            move_to(p, cfg.ERROR_DIR)
                            return True
                        elif int(new_rev) > int(max_rev_same_sheet):
                            with timeit(f"{name} move_old_revs_same_sheet"):
                                for r, nm, _, _ in same_sheet:
                                    if int(r) < int(new_rev):
                                        old_path = dir_tif_loc / nm
                                        dest_dir = _storico_dest_dir_for_name(cfg, nm)
                                        dest_path = dest_dir / nm
                                        try:
                                            if dest_path.exists():
                                                log_error(cfg, nm, "Presente in Storico")
                                                try:
                                                    move_to(old_path, cfg.ERROR_DIR)
                                                except FileNotFoundError:
                                                    pass
                                                except Exception as e:
                                                    logging.exception("Storico: impossibile spostare %s → %s: %s", old_path, cfg.ERROR_DIR, e)
                                            else:
                                                try:
                                                    move_to(old_path, dest_dir)
                                                    log_swarky(cfg, name, tiflog, "Rev superata", nm, "Storico")
                                                except FileNotFoundError:
                                                    pass
                                                except Exception as e:
                                                    logging.exception("Storico: impossibile spostare %s → %s: %s", old_path, dest_dir, e)
                                        except Exception as e:
                                            logging.exception("Storico: impossibile spostare %s → %s: %s", old_path, dest_dir, e)
                        else:
                            other = next((nm for _, nm, met, _ in same_rs if met != new_metric), None)
                            if other:
                                log_swarky(cfg, name, tiflog, "Metrica Diversa", other)

                with timeit(f"{name} orientamento"):
                    if not check_orientation_ok(p):
                        log_error(cfg, name, "Immagine Girata")
                        move_to(p, cfg.ERROR_DIR)
                        return True

                with timeit(f"{name} move_to_archivio"):
                    move_to(p, dir_tif_loc)
                    new_path = dir_tif_loc / name

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

        return True
    except Exception:
        logging.exception("Errore inatteso per %s", p)
        return False

def archive_once(cfg: Config) -> bool:
    start = time.time()
    clear_orientation_cache()
    did_something = False

    with timeit("scan candidati (hplotter)"):
        candidates: List[Path] = list(_iter_candidates(cfg.DIR_HPLOTTER, cfg.ACCEPT_PDF))

    workers_env = os.environ.get("SWARKY_WORKERS", "3")
    try:
        workers = int(workers_env)
    except ValueError:
        workers = 3
    workers = max(1, min(workers, 8))
    logging.debug("Workers: %d", workers)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_process_candidate, p, cfg) for p in candidates]
        for fut in as_completed(futures):
            try:
                did_something |= fut.result()
            except Exception:
                logging.exception("Errore nel worker")

    if did_something:
        elapsed = time.time() - start
        write_lines((cfg.LOG_DIR or cfg.DIR_HPLOTTER) / f"Swarky_{datetime.now().strftime('%b.%Y')}.log",
                    [f"ProcessTime # {elapsed:.2f}s"])
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

_LAST_STATS_TS: float = 0.0

def _count_files_quick(d: Path, exts: tuple[str, ...]) -> int:
    """Conta i file con estensione in exts usando os.scandir, non ricorsivo, case-insensitive. Tollerante agli errori."""
    try:
        with os.scandir(d) as it:
            return sum(
                1
                for de in it
                if de.is_file() and os.path.splitext(de.name)[1].lower() in exts
            )
    except (OSError, FileNotFoundError):
        return 0

def _stats_interval_sec() -> int:
    """Legge l'intervallo da SWARKY_STATS_EVERY (secondi), default 300, valore minimo 10."""
    val = os.environ.get("SWARKY_STATS_EVERY", "300")
    try:
        n = int(val)
    except Exception:
        n = 300
    return n if n >= 10 else 10

def _should_emit_stats() -> bool:
    """Ritorna True se è passato abbastanza tempo dall'ultima emissione; aggiorna _LAST_STATS_TS quando True."""
    global _LAST_STATS_TS
    now = time.monotonic()
    if now - _LAST_STATS_TS >= _stats_interval_sec():
        _LAST_STATS_TS = now
        return True
    return False

def count_tif_files(cfg: Config) -> dict:
    return {
        "Same Rev Dwg": _count_files_quick(cfg.PARI_REV_DIR, (".tif", ".pdf")),
        "Check Dwg": _count_files_quick(cfg.ERROR_DIR, (".tif", ".pdf")),
        "Heng Dwg": _count_files_quick(cfg.DIR_HENGELO, (".tif", ".pdf")),
        "Tab Dwg": _count_files_quick(cfg.DIR_TABELLARI, (".tif", ".pdf")),
        "Plm error Dwg": _count_files_quick(cfg.DIR_PLM_ERROR, (".tif", ".pdf")),
    }

# ---- LOOP ----------------------------------------------------------------------------

def run_once(cfg: Config) -> bool:
    did_something = archive_once(cfg)
    iss_loading(cfg)
    fiv_loading(cfg)
    if logging.getLogger().isEnabledFor(logging.DEBUG) and _should_emit_stats():
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

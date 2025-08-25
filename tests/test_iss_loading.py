from pathlib import Path
import importlib.util
import importlib.machinery
import sys


def load_swarky():
    """Load the main Swarky module from the repository root."""
    module_path = Path(__file__).resolve().parents[1] / "Swarky.py"
    loader = importlib.machinery.SourceFileLoader("swarky", str(module_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def test_document_revision_from_filename(tmp_path):
    swarky = load_swarky()

    # Setup minimal configuration with temporary directories
    cfg = swarky.Config(
        DIR_HPLOTTER=tmp_path / "hplotter",
        ARCHIVIO_DISEGNI=tmp_path / "archivio",
        ERROR_DIR=tmp_path / "error",
        PARI_REV_DIR=tmp_path / "pari_rev",
        PLM_DIR=tmp_path / "plm",
        ARCHIVIO_STORICO=tmp_path / "storico",
        DIR_ISS=tmp_path / "iss",
        DIR_FIV_LOADING=tmp_path / "fiv",
        DIR_HENGELO=tmp_path / "hengelo",
        DIR_KALT=tmp_path / "kalt",
        DIR_KALT_ERRORS=tmp_path / "kalt_err",
        DIR_TABELLARI=tmp_path / "tab",
    )

    cfg.DIR_ISS.mkdir(parents=True)

    # Create a sample ISS file with revision 02 and sheet 03
    pdf_name = "G1234ABC1234567ISSR02S03.pdf"
    (cfg.DIR_ISS / pdf_name).write_bytes(b"%PDF-1.4 test")

    swarky.iss_loading(cfg)

    edi_path = cfg.PLM_DIR / (Path(pdf_name).stem + ".DESEDI")
    lines = [l.strip() for l in edi_path.read_text(encoding="utf-8").splitlines() if l.startswith("DocumentRev=")]

    # Both DocumentRev lines should use group(4) -> "02"
    assert lines == ["DocumentRev=02", "DocumentRev=02"]


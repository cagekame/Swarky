from pathlib import Path
import importlib.util
import importlib.machinery
import sys
import pytest


def load_swarky():
    module_path = Path(__file__).resolve().parents[1] / "Swarky"
    loader = importlib.machinery.SourceFileLoader("swarky", str(module_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


@pytest.fixture
def swarky():
    return load_swarky()


@pytest.fixture
def cfg(swarky, tmp_path):
    return swarky.Config(
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


@pytest.mark.parametrize(
    "name,expected",
    [
        ("DAM123456R01S01A.tif", "costruttivi"),
        ("DAK123456R01S01A.tif", "bozzetti"),
        ("DAF123456R01S01A.tif", "fornitori"),
        ("DAT123456R01S01A.tif", "tenute_meccaniche"),
        ("DAE123456R01S01A.tif", "sezioni"),
        ("DAS123456R01S01A.tif", "sezioni"),
        ("DAN123456R01S01A.tif", "marcianise"),
        ("DAP123456R01S01A.tif", "preventivi"),
        ("DAX412345R01S01A.tif", "pID_ELETTRICI"),
        ("DAX512345R01S01A.tif", "piping"),
        ("DAX712345R01S01A.tif", "unknown"),
    ],
)
def test_map_location(swarky, cfg, name, expected):
    m = swarky.BASE_NAME.match(name)
    loc = swarky.map_location(m, cfg)
    assert loc["folder"] == expected

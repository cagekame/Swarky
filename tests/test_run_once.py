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
        LOG_DIR=tmp_path / "logs",
    )


def test_run_once_stdout_only_reports(swarky, cfg, capsys):
    cfg.DIR_HPLOTTER.mkdir()
    (cfg.DIR_HPLOTTER / "badfile.tif").write_bytes(b"0")

    swarky.run_once(cfg)
    out = capsys.readouterr().out.strip().splitlines()

    assert out
    assert len(out) == 1
    assert not any(line.startswith("Counts:") for line in out)
    assert all(" # " in line for line in out)

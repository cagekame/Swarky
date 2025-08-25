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


def log_path(swarky, cfg):
    return cfg.LOG_DIR / f"Swarky_{swarky.month_tag()}.log"


def test_archive_once_logs_process_time(swarky, cfg, monkeypatch):
    cfg.DIR_HPLOTTER.mkdir()
    (cfg.DIR_HPLOTTER / "DAM123456R01S01A.tif").write_bytes(b"0")
    monkeypatch.setattr(swarky, "check_orientation_ok", lambda _: True)
    assert swarky.archive_once(cfg) is True
    assert "ProcessTime" in log_path(swarky, cfg).read_text(encoding="utf-8")


def test_archive_once_skips_process_time_if_no_files(swarky, cfg):
    cfg.DIR_HPLOTTER.mkdir()
    assert swarky.archive_once(cfg) is False
    assert not log_path(swarky, cfg).exists()


def test_archive_once_archives_only_matching_metric(swarky, cfg, monkeypatch):
    dir_loc = cfg.ARCHIVIO_DISEGNI / "costruttivi" / "Am"
    dir_loc.mkdir(parents=True)
    old_m = dir_loc / "DAM123456R01S01M.tif"
    old_m.write_bytes(b"m")
    old_i = dir_loc / "DAM123456R01S01I.tif"
    old_i.write_bytes(b"i")
    cfg.DIR_HPLOTTER.mkdir()
    (cfg.DIR_HPLOTTER / "DAM123456R02S01M.tif").write_bytes(b"new")
    monkeypatch.setattr(swarky, "check_orientation_ok", lambda _: True)
    swarky.archive_once(cfg)
    assert not old_m.exists()
    assert old_i.exists()
    assert (cfg.ARCHIVIO_STORICO / old_m.name).exists()
    assert not (cfg.ARCHIVIO_STORICO / old_i.name).exists()
    assert (dir_loc / "DAM123456R02S01M.tif").exists()


def test_archive_once_retains_files_when_new_metric_different(swarky, cfg, monkeypatch):
    dir_loc = cfg.ARCHIVIO_DISEGNI / "costruttivi" / "Am"
    dir_loc.mkdir(parents=True)
    old_m = dir_loc / "DAM123456R01S01M.tif"
    old_m.write_bytes(b"m")
    old_n = dir_loc / "DAM123456R01S01N.tif"
    old_n.write_bytes(b"n")
    cfg.DIR_HPLOTTER.mkdir()
    (cfg.DIR_HPLOTTER / "DAM123456R02S01I.tif").write_bytes(b"new")
    monkeypatch.setattr(swarky, "check_orientation_ok", lambda _: True)
    swarky.archive_once(cfg)
    assert old_m.exists()
    assert old_n.exists()
    assert not cfg.ARCHIVIO_STORICO.exists() or not any(cfg.ARCHIVIO_STORICO.iterdir())
    assert (dir_loc / "DAM123456R02S01I.tif").exists()


@pytest.mark.parametrize("metric", ["D", "N"])
def test_archive_once_archives_all_when_new_metric_dn(swarky, cfg, monkeypatch, metric):
    dir_loc = cfg.ARCHIVIO_DISEGNI / "costruttivi" / "Am"
    dir_loc.mkdir(parents=True)
    old_m = dir_loc / "DAM123456R01S01M.tif"
    old_m.write_bytes(b"m")
    old_i = dir_loc / "DAM123456R01S01I.tif"
    old_i.write_bytes(b"i")
    cfg.DIR_HPLOTTER.mkdir()
    (cfg.DIR_HPLOTTER / f"DAM123456R02S01{metric}.tif").write_bytes(b"new")
    monkeypatch.setattr(swarky, "check_orientation_ok", lambda _: True)
    swarky.archive_once(cfg)
    assert not old_m.exists()
    assert not old_i.exists()
    assert (cfg.ARCHIVIO_STORICO / old_m.name).exists()
    assert (cfg.ARCHIVIO_STORICO / old_i.name).exists()
    assert (dir_loc / f"DAM123456R02S01{metric}.tif").exists()

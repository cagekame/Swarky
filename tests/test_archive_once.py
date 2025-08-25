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


def existing_dir(swarky, cfg):
    m = swarky.BASE_NAME.search("DAM000001R01S01M.tif")
    return swarky.map_location(m, cfg)["dir_tif_loc"]


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


def test_new_revision_same_metric_moves_only_matching(swarky, cfg, monkeypatch):
    monkeypatch.setattr(swarky, "check_orientation_ok", lambda _: True)
    dir_existing = existing_dir(swarky, cfg)
    dir_existing.mkdir(parents=True)
    # existing files with different metrics
    (dir_existing / "DAM000001R01S01M.tif").write_bytes(b"0")
    (dir_existing / "DAM000001R01S01I.tif").write_bytes(b"0")
    # new revision with same metric M
    cfg.DIR_HPLOTTER.mkdir()
    (cfg.DIR_HPLOTTER / "DAM000001R02S01M.tif").write_bytes(b"0")
    swarky.archive_once(cfg)
    assert sorted(p.name for p in cfg.ARCHIVIO_STORICO.glob("*.tif")) == ["DAM000001R01S01M.tif"]
    assert sorted(p.name for p in dir_existing.glob("*.tif")) == ["DAM000001R01S01I.tif", "DAM000001R02S01M.tif"]


def test_new_revision_different_metric_keeps_existing(swarky, cfg, monkeypatch):
    monkeypatch.setattr(swarky, "check_orientation_ok", lambda _: True)
    dir_existing = existing_dir(swarky, cfg)
    dir_existing.mkdir(parents=True)
    (dir_existing / "DAM000001R01S01M.tif").write_bytes(b"0")
    cfg.DIR_HPLOTTER.mkdir()
    # new revision with metric I
    (cfg.DIR_HPLOTTER / "DAM000001R02S01I.tif").write_bytes(b"0")
    swarky.archive_once(cfg)
    assert list(cfg.ARCHIVIO_STORICO.glob("*.tif")) == []
    assert sorted(p.name for p in dir_existing.glob("*.tif")) == ["DAM000001R01S01M.tif", "DAM000001R02S01I.tif"]


@pytest.mark.parametrize("metric", ["D", "N"])
def test_new_revision_d_or_n_archives_all(swarky, cfg, monkeypatch, metric):
    monkeypatch.setattr(swarky, "check_orientation_ok", lambda _: True)
    dir_existing = existing_dir(swarky, cfg)
    dir_existing.mkdir(parents=True)
    (dir_existing / "DAM000001R01S01M.tif").write_bytes(b"0")
    (dir_existing / "DAM000001R01S01I.tif").write_bytes(b"0")
    cfg.DIR_HPLOTTER.mkdir()
    (cfg.DIR_HPLOTTER / f"DAM000001R02S01{metric}.tif").write_bytes(b"0")
    swarky.archive_once(cfg)
    assert sorted(p.name for p in cfg.ARCHIVIO_STORICO.glob("*.tif")) == ["DAM000001R01S01I.tif", "DAM000001R01S01M.tif"]
    assert sorted(p.name for p in dir_existing.glob("*.tif")) == [f"DAM000001R02S01{metric}.tif"]

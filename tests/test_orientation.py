from pathlib import Path
import sys
import types
import builtins
import logging

import importlib.util
import importlib.machinery


def load_swarky():
    module_path = Path(__file__).resolve().parents[1] / "Swarky"
    loader = importlib.machinery.SourceFileLoader("swarky", str(module_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def test_check_orientation_ok_import_error(monkeypatch, caplog):
    swarky = load_swarky()

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(sys.modules, "PIL", raising=False)
    monkeypatch.delitem(sys.modules, "PIL.Image", raising=False)

    with caplog.at_level(logging.WARNING):
        result = swarky.check_orientation_ok(Path("dummy.tif"))

    assert result is True
    assert "PIL non installato" in caplog.text


def test_check_orientation_ok_logs_error(monkeypatch, caplog):
    swarky = load_swarky()

    dummy = types.ModuleType("PIL")

    class DummyImageModule:
        @staticmethod
        def open(_):
            raise RuntimeError("boom")

    dummy.Image = DummyImageModule
    monkeypatch.setitem(sys.modules, "PIL", dummy)

    with caplog.at_level(logging.ERROR):
        result = swarky.check_orientation_ok(Path("dummy.tif"))

    assert result is False
    assert "Errore durante la verifica" in caplog.text

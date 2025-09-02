# perf.py
import time
import logging
from contextlib import contextmanager

_ENABLED = False  # <-- di default DISATTIVO

def enable(flag: bool) -> None:
    """Abilita/disabilita i timer runtime."""
    global _ENABLED
    _ENABLED = bool(flag)

@contextmanager
def timeit(label: str):
    """Usa: with timeit('fase'): ...  -> logga solo se abilitato."""
    if not _ENABLED:
        # no-op
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt_ms = (time.perf_counter() - t0) * 1000.0
        logging.info("TIMER %-40s %8.1f ms", label, dt_ms)

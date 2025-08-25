#!/usr/bin/env python3
"""Interfaccia grafica minimale per Swarky."""

from pathlib import Path
import threading
import time
import logging
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from datetime import datetime, time as dt_time, timedelta

# Try to enable filesystem watching for instant updates of the plotter list.
try:  # pragma: no cover - optional dependency
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except Exception:  # pragma: no cover - watchdog may not be installed
    Observer = None  # type: ignore

from Swarky import load_config, run_once, setup_logging

cfg = load_config(Path("config.toml"))
setup_logging(cfg)

root = tk.Tk()
for font_name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
    try:
        tkfont.nametofont(font_name).configure(family="Calibri")
    except tk.TclError:
        pass
style = ttk.Style(root)
style.configure(".", font=("Calibri", 11))
root.title("Swarky")

root.columnconfigure(0, weight=1)
root.columnconfigure(1, weight=1)
root.columnconfigure(2, weight=1)
root.columnconfigure(3, weight=0)
root.rowconfigure(0, weight=1)

plotter_frame = ttk.LabelFrame(root, text="Disegni in Plotter")
plotter_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

anomaly_frame = ttk.LabelFrame(root, text="Anomalie")
anomaly_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

processed_frame = ttk.LabelFrame(root, text="File processati")
processed_frame.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)

plotter_list = tk.Listbox(plotter_frame)
plotter_list.pack(fill="both", expand=True)

anomaly_tree = ttk.Treeview(
    anomaly_frame, columns=("data", "ora", "file", "errore"), show="headings"
)
anomaly_tree.heading("data", text="Data")
anomaly_tree.heading("ora", text="Ora")
anomaly_tree.heading("file", text="File")
anomaly_tree.heading("errore", text="Errore")
anomaly_tree.pack(fill="both", expand=True)

processed_tree = ttk.Treeview(
    processed_frame,
    columns=("data", "ora", "file", "proc", "conf"),
    show="headings",
)
processed_tree.heading("data", text="Data")
processed_tree.heading("ora", text="Ora")
processed_tree.heading("file", text="File")
processed_tree.heading("proc", text="Processo")
processed_tree.heading("conf", text="Confronto")
processed_tree.pack(fill="both", expand=True)

controls = ttk.Frame(root)
controls.grid(row=1, column=0, columnspan=3, pady=5)

interval_var = tk.StringVar(value="60")

ttk.Label(controls, text="Intervallo (s):").pack(side="left")
ttk.Entry(controls, textvariable=interval_var, width=6).pack(side="left")

clock_label = ttk.Label(controls, font=("Calibri", 11))
clock_label.pack(side="right", padx=5)

def refresh_plotter():
    plotter_list.delete(0, tk.END)
    patterns = ("*.tif", "*.TIF", "*.pdf", "*.PDF")
    files = {
        p.name.lower(): p.name
        for pat in patterns
        for p in cfg.DIR_HPLOTTER.glob(pat)
        if p.is_file()
    }
    for name in sorted(files.values(), key=str.lower):
        plotter_list.insert(tk.END, name)


class TreeviewHandler(logging.Handler):
    """Handler that pushes log records to the GUI."""

    def __init__(self, root: tk.Misc, processed: ttk.Treeview, anomaly: ttk.Treeview):
        super().__init__()
        self.root = root
        self.processed = processed
        self.anomaly = anomaly

    def emit(self, record: logging.LogRecord):
        ui = getattr(record, "ui", None)
        if not ui:
            return
        kind, file_name, *rest = ui
        ts = datetime.fromtimestamp(record.created)
        if kind == "processed":
            process = rest[0] if rest else ""
            compare = rest[1] if len(rest) > 1 else ""
            def _add():
                self.processed.insert(
                    "",
                    "end",
                    values=(
                        ts.strftime('%d.%b.%Y'),
                        ts.strftime('%H:%M:%S'),
                        file_name,
                        process,
                        compare,
                    ),
                )
            self.root.after(0, _add)
        elif kind == "anomaly":
            msg = rest[0] if rest else ""
            def _add():
                self.anomaly.insert(
                    "",
                    "end",
                    values=(
                        ts.strftime('%d.%b.%Y'),
                        ts.strftime('%H:%M:%S'),
                        file_name,
                        msg,
                    ),
                )
            self.root.after(0, _add)


# Install the GUI logging handler before the file handler so UI updates happen first
tree_handler = TreeviewHandler(root, processed_tree, anomaly_tree)
logger = logging.getLogger()
logger.handlers.insert(0, tree_handler)


def periodic_plotter_refresh():
    """Aggiorna la lista del plotter ogni secondo."""
    refresh_plotter()
    root.after(1000, periodic_plotter_refresh)


# Optional watchdog-based watcher for immediate refresh on new files.
plotter_observer = None


def start_plotter_watcher():  # pragma: no cover - optional dependency
    """Start a watchdog observer to update the plotter list on file creation."""
    global plotter_observer
    if Observer is None:
        return

    class Handler(FileSystemEventHandler):
        def on_created(self, event):
            if not getattr(event, "is_directory", False):
                root.after(0, refresh_plotter)

    observer = Observer()
    observer.schedule(Handler(), str(cfg.DIR_HPLOTTER), recursive=False)
    observer.daemon = True
    observer.start()
    plotter_observer = observer

def update_clock():
    clock_label.config(text=time.strftime("%d/%m/%Y %H:%M:%S"))
    root.after(1000, update_clock)

def run_once_thread():
    threading.Thread(target=_run_once_worker, daemon=True).start()

def _run_once_worker():
    run_once(cfg)
    root.after(0, refresh_plotter)


def schedule_daily_run():
    """Schedule `_scheduled_run` to execute at the next 17:00."""
    now = datetime.now()
    target = datetime.combine(now.date(), dt_time(17, 0))
    if now >= target:
        target += timedelta(days=1)
    delay = int((target - now).total_seconds() * 1000)
    root.after(delay, _scheduled_run)


def _scheduled_run():
    """Run the task once and reschedule for the next day."""
    run_once_thread()
    schedule_daily_run()

def _watch_worker(interval, stop_event):
    while not stop_event.is_set():
        run_once(cfg)
        root.after(0, refresh_plotter)
        for _ in range(interval):
            if stop_event.is_set():
                break
            time.sleep(1)

watch_thread = None
watch_stop_event = None

def start_watch():
    global watch_thread, watch_stop_event
    if watch_thread and watch_thread.is_alive():
        return
    stop_event = threading.Event()
    watch_stop_event = stop_event
    try:
        interval = int(interval_var.get())
    except ValueError:
        interval = 60
    watch_thread = threading.Thread(target=_watch_worker, args=(interval, stop_event), daemon=True)
    watch_thread.start()

def stop_watch():
    global watch_thread, watch_stop_event
    if watch_stop_event:
        watch_stop_event.set()
    watch_thread = None

ttk.Button(controls, text="Swarky", command=run_once_thread).pack(side="left", padx=5)
ttk.Button(controls, text="Avvia watch", command=start_watch).pack(side="left", padx=5)
ttk.Button(controls, text="Ferma watch", command=stop_watch).pack(side="left", padx=5)

refresh_plotter()
schedule_daily_run()
update_clock()
periodic_plotter_refresh()
start_plotter_watcher()


def _on_close():
    if plotter_observer:
        plotter_observer.stop()
        plotter_observer.join()
    stop_watch()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", _on_close)

if __name__ == "__main__":
    root.mainloop()

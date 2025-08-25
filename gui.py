#!/usr/bin/env python3
"""Interfaccia grafica minimale per Swarky."""

from pathlib import Path
from itertools import chain
import threading
import time
import tkinter as tk
from tkinter import ttk

from Swarky import load_config, run_once, watch_loop, setup_logging, month_tag

cfg = load_config(Path("config.toml"))
setup_logging(cfg)

root = tk.Tk()
root.title("Swarky GUI")

root.columnconfigure(0, weight=1)
root.columnconfigure(1, weight=1)
root.columnconfigure(2, weight=1)
root.rowconfigure(0, weight=1)

plotter_frame = ttk.LabelFrame(root, text="Disegni in Plotter")
plotter_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

anomaly_frame = ttk.LabelFrame(root, text="Anomalie")
anomaly_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

processed_frame = ttk.LabelFrame(root, text="File processati")
processed_frame.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)

plotter_list = tk.Listbox(plotter_frame)
plotter_list.pack(fill="both", expand=True)

anomaly_tree = ttk.Treeview(anomaly_frame, columns=("file", "msg"), show="headings")
anomaly_tree.heading("file", text="File")
anomaly_tree.heading("msg", text="Messaggio")
anomaly_tree.pack(fill="both", expand=True)

processed_tree = ttk.Treeview(processed_frame, columns=("file", "proc"), show="headings")
processed_tree.heading("file", text="File")
processed_tree.heading("proc", text="Processo")
processed_tree.pack(fill="both", expand=True)

controls = ttk.Frame(root)
controls.grid(row=1, column=0, columnspan=3, pady=5)

interval_var = tk.StringVar(value="60")

ttk.Label(controls, text="Intervallo (s):").pack(side="left")
ttk.Entry(controls, textvariable=interval_var, width=6).pack(side="left")

def refresh_plotter():
    plotter_list.delete(0, tk.END)
    patterns = ("*.tif", "*.TIF", "*.pdf", "*.PDF")
    files = sorted(
        chain.from_iterable(cfg.DIR_HPLOTTER.glob(pat) for pat in patterns),
        key=lambda p: p.name.lower(),
    )
    for p in files:
        if p.is_file():
            plotter_list.insert(tk.END, p.name)

def parse_log_file():
    log_path = (cfg.LOG_DIR or cfg.DIR_HPLOTTER) / f"Swarky_{month_tag()}.log"
    anomalies, processed = [], []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            parts = [part.strip() for part in line.split("#")]
            if len(parts) >= 4:
                file_name = parts[1]
                flag = parts[2]
                msg = parts[3]
                if flag == "ERRORE":
                    anomalies.append((file_name, msg))
                else:
                    processed.append((file_name, msg))
    return anomalies, processed

def refresh_logs():
    anomalies, processed = parse_log_file()
    for item in anomaly_tree.get_children():
        anomaly_tree.delete(item)
    for f, msg in anomalies:
        anomaly_tree.insert("", "end", values=(f, msg))
    for item in processed_tree.get_children():
        processed_tree.delete(item)
    for f, proc in processed:
        processed_tree.insert("", "end", values=(f, proc))

def refresh_all():
    refresh_plotter()
    refresh_logs()

def run_once_thread():
    threading.Thread(target=_run_once_worker, daemon=True).start()

def _run_once_worker():
    run_once(cfg)
    root.after(0, refresh_all)

def _watch_worker(interval, stop_event):
    while not stop_event.is_set():
        run_once(cfg)
        root.after(0, refresh_all)
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

ttk.Button(controls, text="Esegui una volta", command=run_once_thread).pack(side="left", padx=5)
ttk.Button(controls, text="Avvia watch", command=start_watch).pack(side="left", padx=5)
ttk.Button(controls, text="Ferma watch", command=stop_watch).pack(side="left", padx=5)

refresh_all()

if __name__ == "__main__":
    root.mainloop()

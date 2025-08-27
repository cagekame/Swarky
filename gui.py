def _watch_worker(self, interval: int, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            if not self._run_lock.acquire(blocking=False):
                # già in corso: salta questo giro
                pass
            else:
                try:
                    result = run_once(self.cfg)
                    msg = "Completato." if result else "Nessun file."
                    logging.info("Watch: %s", msg)
                    # opzionale: puoi anche aggiornare un’etichetta di stato
                    self.root.after(0, lambda m=msg: self.clock_label.config(text=f"{datetime.now():%H:%M:%S} • {m}"))
                finally:
                    try:
                        self._run_lock.release()
                    except Exception:
                        pass
        except Exception as e:
            if not self._run_error_notified:
                self._run_error_notified = True
                err = str(e)
                self.root.after(0, lambda msg=err: messagebox.showwarning(
                    "Watch: errore",
                    "Errore durante l'esecuzione periodica (config incompleta o percorsi non validi?).\n\n"
                    f"Dettagli: {msg}\nIl watch continuerà a provare."
                ))
        finally:
            self.root.after(0, self.refresh_plotter)

        # attesa intervallo, interrotta se arriva stop_event
        for _ in range(interval):
            if stop_event.is_set():
                break
            threading.Event().wait(1)

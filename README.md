# Swarky

CLI per l'archiviazione e la generazione di file EDI.

## Utilizzo

Esegui una passata singola (archivio + ISS + FIV):

```bash
python Swarky
```

Esegui in modalità watch con un intervallo in secondi:

```bash
python Swarky --watch 60
```

Opzioni disponibili:

- `--watch SECONDS` – Loop di polling in secondi, `0` esegue una sola passata

## Interfaccia grafica

È disponibile una piccola GUI basata su `tkinter` per monitorare l'attività di Swarky.
Avviala con:

```bash
python gui.py
```

La finestra mostra i disegni presenti nella cartella di plotter, le anomalie rilevate e
lo storico dei file processati, oltre a consentire l'avvio manuale o periodico del
processo.

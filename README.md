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

- `--config PATH` – Percorso file di configurazione TOML
- `--watch SECONDS` – Loop di polling in secondi, `0` esegue una sola passata
- `--debug` – Abilita logging dettagliato

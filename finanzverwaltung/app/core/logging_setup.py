"""
Logging-Konfiguration: schreibt zusätzlich zur Konsole (die z. B. der
Home-Assistant-Log-Tab anzeigt) in eine rotierende Log-Datei unter
<Datenverzeichnis>/logs/finanzapp.log. Damit bleiben Fehler auch nach
einem Neustart nachvollziehbar, statt nur im flüchtigen Log-Puffer zu
stehen.
"""
from pathlib import Path


def konfiguration(datenverzeichnis: Path) -> dict:
    log_verzeichnis = datenverzeichnis / "logs"
    log_verzeichnis.mkdir(parents=True, exist_ok=True)
    log_datei = str(log_verzeichnis / "finanzapp.log")

    dateihandler = {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "default",
        "filename": log_datei,
        "maxBytes": 5 * 1024 * 1024,
        "backupCount": 3,
        "encoding": "utf-8",
    }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s"},
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "default", "stream": "ext://sys.stdout"},
            "file": dateihandler,
        },
        "loggers": {
            "uvicorn": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "app": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        },
    }

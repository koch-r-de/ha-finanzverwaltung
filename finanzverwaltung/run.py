"""
Einstiegspunkt für den Programmstart.

Läuft headless im Vordergrund (Docker/Home-Assistant-Add-on: bindet an
0.0.0.0, damit der Ingress-Proxy des Supervisors den Container
erreicht) oder lokal mit automatisch geöffnetem Browser, je nachdem ob
FINANZAPP_DATENVERZEICHNIS gesetzt ist (siehe app/core/db.py).

Schreibt Logs zusätzlich zur Konsole in eine rotierende Datei unter
<Datenverzeichnis>/logs/finanzapp.log.
"""
import os
import threading
import time
import webbrowser

import uvicorn

from app.core import logging_setup
from app.core.db import basis_verzeichnis
from app.main import app

DOCKER_MODUS = bool(os.environ.get("FINANZAPP_DATENVERZEICHNIS"))
HOST = "0.0.0.0" if DOCKER_MODUS else "127.0.0.1"
PORT = int(os.environ.get("FINANZAPP_PORT", 8935))

LOG_CONFIG = logging_setup.konfiguration(basis_verzeichnis())


def main():
    if DOCKER_MODUS:
        # Headless: läuft im Vordergrund als Hauptprozess des Containers.
        uvicorn.run(app, host=HOST, port=PORT, log_config=LOG_CONFIG)
        return

    thread = threading.Thread(
        target=lambda: uvicorn.run(app, host=HOST, port=PORT, log_config=LOG_CONFIG),
        daemon=True,
    )
    thread.start()
    time.sleep(1.2)  # kurze Wartezeit, bis der Server bereit ist

    url = f"http://127.0.0.1:{PORT}"
    try:
        import webview  # optional, falls installiert: eigenes Fenster statt Browser
        webview.create_window("Private Finanzverwaltung", url, width=1280, height=860, min_size=(960, 640))
        webview.start()
    except ImportError:
        webbrowser.open(url)
        input(
            "Die Finanzverwaltung läuft unter " + url + "\n"
            "Dieses Fenster geöffnet lassen, solange die Anwendung läuft. "
            "Zum Beenden hier Enter drücken...\n"
        )


if __name__ == "__main__":
    main()

"""
Führt alle Testreihen aus. Aufruf aus dem Wurzelordner des Repositorys:

    python3 tests/alle_tests.py            # fachliche Tests und Oberflächentests
    python3 tests/alle_tests.py --ohne-ui  # nur fachliche Tests (ohne Playwright)

Jede Reihe arbeitet auf einer Kopie einer Testdatenbank aus tests/daten in
tests/ausgabe/<reihe>. Für die Oberflächentests startet das Skript den Server
auf Port 8935 und beendet ihn danach. Ergebnis je Reihe: „x/y bestanden“,
Protokolle in tests/ausgabe/<reihe>.txt. Rückgabewert 1, wenn etwas fehlschlägt.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

TESTS = Path(__file__).resolve().parent
WURZEL = TESTS.parent
CODE = WURZEL / "finanzverwaltung"
DATEN = TESTS / "daten"
AUSGABE = TESTS / "ausgabe"
PORT = 8935

# (Reihe, Skript, Quelle, zusätzliche Argumente). Quelle "ausgabe:x" = Ergebnis einer früheren Reihe.
FACHLICH = [
    ("funktion", "funktion_test.py", "v191", []),
    ("v2", "v2_test.py", "v191", []),
    ("v21", "v21_test.py", "v20", []),
    ("v22", "v22_test.py", "v20", []),
    ("v23", "v23_test.py", "ausgabe:v2", []),
    ("v24", "v24_test.py", "v191", [str(DATEN / "v21")]),
    ("v26", "v26_test.py", "v21", []),
    ("v261", "v261_test.py", "v21", []),
    ("v262", "v262_test.py", "v21", []),
]
OBERFLAECHE = [
    ("ui", "ui_test.py", "v191", []),
    ("ui2", "ui2_test.py", "ausgabe:uibasis", []),
    ("ui21", "ui21_test.py", "ausgabe:uibasis", []),
    ("ui23", "ui23_test.py", "ausgabe:uibasis", []),
    ("ui24", "ui24_test.py", "ausgabe:uibasis", [str(DATEN / "v21" / "finanzdaten.db")]),
    ("ui26", "ui26_test.py", "v191", []),
]

# Reihen, die die Bundesland-Abfrage selbst prüfen
OHNE_VORBELEGUNG = {"ui26"}


def quelle_pfad(quelle: str) -> Path:
    return AUSGABE / quelle.split(":", 1)[1] if quelle.startswith("ausgabe:") else DATEN / quelle


def protokoll(reihe: str, ergebnis: subprocess.CompletedProcess) -> str:
    text = ergebnis.stdout + ergebnis.stderr
    (AUSGABE / f"{reihe}.txt").write_text(text, encoding="utf-8")
    zeilen = [z for z in text.splitlines() if "bestanden" in z and "/" in z]
    return zeilen[-1] if zeilen else f"abgebrochen (siehe tests/ausgabe/{reihe}.txt)"


def bundesland_vorbelegen(datenordner: Path) -> None:
    """Seit 2.6 fragt die Oberfläche beim ersten Start nach dem Bundesland
    (Pflichtdialog). Die Oberflächentests der Vorversionen arbeiten mit
    gewähltem NRW, damit der Dialog sie nicht blockiert. Die Abfrage selbst
    prüft ui26_test.py."""
    con = sqlite3.connect(datenordner / "finanzdaten.db")
    con.execute("CREATE TABLE IF NOT EXISTS einstellungen (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute("INSERT OR REPLACE INTO einstellungen (key, value) VALUES ('bundesland', 'NW')")
    con.commit()
    con.close()


def server_starten(datenordner: Path) -> subprocess.Popen:
    env = {**os.environ, "FINANZAPP_DATENVERZEICHNIS": str(datenordner), "FINANZAPP_PORT": str(PORT)}
    prozess = subprocess.Popen([sys.executable, "run.py"], cwd=CODE, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/api/start-status", timeout=1)
            return prozess
        except OSError:
            time.sleep(0.5)
    prozess.terminate()
    raise RuntimeError("Server startet nicht.")


def main() -> int:
    mit_ui = "--ohne-ui" not in sys.argv
    shutil.rmtree(AUSGABE, ignore_errors=True)
    AUSGABE.mkdir()
    ergebnisse = []
    for reihe, skript, quelle, extra in FACHLICH:
        lauf = subprocess.run([sys.executable, str(TESTS / skript), str(CODE), str(quelle_pfad(quelle)),
                               str(AUSGABE / reihe), *extra], capture_output=True, text=True, timeout=900)
        ergebnisse.append((reihe, protokoll(reihe, lauf)))
        print(f"{reihe:10} {ergebnisse[-1][1]}", flush=True)
    if mit_ui:
        subprocess.run([sys.executable, str(TESTS / "ui_vorbereiten.py"), str(CODE), str(DATEN / "v191"),
                        str(AUSGABE / "uibasis")], capture_output=True, check=True, timeout=300)
        for reihe, skript, quelle, extra in OBERFLAECHE:
            ordner = AUSGABE / f"{reihe}_daten"
            shutil.copytree(quelle_pfad(quelle), ordner)
            if reihe not in OHNE_VORBELEGUNG:
                bundesland_vorbelegen(ordner)
            server = server_starten(ordner)
            try:
                lauf = subprocess.run([sys.executable, str(TESTS / skript), *extra],
                                      capture_output=True, text=True, timeout=900)
            finally:
                server.terminate()
                server.wait(timeout=30)
            ergebnisse.append((reihe, protokoll(reihe, lauf)))
            print(f"{reihe:10} {ergebnisse[-1][1]}", flush=True)
    fehler = [r for r, e in ergebnisse if not e.endswith("[]")]
    print("\nAlles bestanden." if not fehler else f"\nFehlgeschlagen: {', '.join(fehler)}")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())

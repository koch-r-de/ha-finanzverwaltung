"""
Datenbank wiederherstellen (seit v2.4).

Zwei Quellen: eine hochgeladene Datei (z. B. die mit „Datenbank
herunterladen“ gesicherte finanzdaten.db, auch aus einem anderen Add-on)
oder ein Backup aus der Backup-Liste. Ablauf in zwei Schritten:

1. vorbereiten: Datei prüfen (SQLite, integrity_check, Pflichttabellen),
   Kennzahlen von Datei und aktuellem Stand liefern, Bestätigungsphrase
   ausstellen (gleiches Verfahren wie „Daten zurücksetzen“). Hochgeladene
   Dateien liegen bis dahin in Backups/.wiederherstellen.
2. ausfuehren: Phrase prüfen, Backup „vor Wiederherstellung …“ anlegen,
   Datei einspielen, die Backup-Liste der Installation übernehmen, dann den
   normalen Programmstart (Migrationen, fällige Termine). Scheitert der
   Start, wird der vorherige Stand zurückgespielt.

Die Backup-Liste (Tabelle backups_log) gehört zur Installation, nicht zur
Datei: Sie beschreibt die Dateien im Ordner Backups. Eine eingespielte
Datenbank bringt die Liste ihrer alten Installation mit; ohne Übernahme
würde die Rotation fremde Einträge abarbeiten und dabei womöglich
gleichnamige echte Backups löschen.
"""
import os
import secrets
import shutil
import sqlite3
import threading
import time
from pathlib import Path

from . import db as db_modul
from . import backup as backup_modul
from . import zuruecksetzen

PFLICHT_TABELLEN = {"konten", "buchungen", "kategorien", "einstellungen", "backups_log"}
MAX_GROESSE = 500 * 1024 * 1024
_STAGING_MAX_ALTER = 3600
_SPERRE = threading.Lock()


class WiederherstellenFehler(ValueError):
    """Fachlicher Fehler (ungültige Datei, unbekanntes Backup, falsche Phrase)."""


def _staging() -> Path:
    pfad = db_modul.BACKUP_VERZEICHNIS / ".wiederherstellen"
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def _staging_aufraeumen() -> None:
    grenze = time.time() - _STAGING_MAX_ALTER
    for datei in _staging().glob("*.db"):
        if datei.stat().st_mtime < grenze:
            datei.unlink(missing_ok=True)


def kennzahlen(pfad: Path) -> dict:
    """Prüft eine Datenbankdatei nur lesend und liefert Kennzahlen."""
    with open(pfad, "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            raise WiederherstellenFehler("Die Datei ist keine SQLite-Datenbank.")
    try:
        conn = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    except sqlite3.Error as e:
        raise WiederherstellenFehler(f"Die Datei lässt sich nicht öffnen: {e}")
    try:
        try:
            ergebnis = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError as e:
            raise WiederherstellenFehler(f"Die Datei ist beschädigt: {e}")
        if ergebnis != "ok":
            raise WiederherstellenFehler(f"Die Datei ist beschädigt: {ergebnis}")
        tabellen = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        fehlend = sorted(PFLICHT_TABELLEN - tabellen)
        if fehlend:
            raise WiederherstellenFehler("Die Datei ist keine Datenbank dieses Programms (es fehlt: "
                                         + ", ".join(fehlend) + ").")
        zahl = lambda sql: conn.execute(sql).fetchone()[0]
        return {
            "konten": zahl("SELECT COUNT(*) FROM konten"),
            "buchungen": zahl("SELECT COUNT(*) FROM buchungen"),
            "kategorien": zahl("SELECT COUNT(*) FROM kategorien"),
            "letzte_buchung": zahl("SELECT MAX(datum) FROM buchungen WHERE typ = 'Ist'"),
            "groesse": pfad.stat().st_size,
        }
    finally:
        conn.close()


def _antwort(quelle: str, bezeichnung: str, pfad: Path) -> dict:
    datei = kennzahlen(pfad)
    aktuell = kennzahlen(db_modul.DB_PFAD) if db_modul.DB_PFAD.exists() else None
    token, phrase = zuruecksetzen.phrase_ausstellen({"wiederherstellen": quelle})
    return {"quelle": quelle, "bezeichnung": bezeichnung, "datei": datei, "aktuell": aktuell,
            "token": token, "phrase": phrase}


def upload_vorbereiten(stream, dateiname: str) -> dict:
    """Speichert eine hochgeladene Datei in Backups/.wiederherstellen und prüft sie."""
    _staging_aufraeumen()
    kennung = secrets.token_hex(8)
    ziel = _staging() / f"{kennung}.db"
    groesse = 0
    with open(ziel, "wb") as f:
        while block := stream.read(1024 * 1024):
            groesse += len(block)
            if groesse > MAX_GROESSE:
                f.close()
                ziel.unlink(missing_ok=True)
                raise WiederherstellenFehler("Die Datei ist größer als 500 MB.")
            f.write(block)
    try:
        return _antwort(f"upload:{kennung}", dateiname or "hochgeladene Datei", ziel)
    except WiederherstellenFehler:
        ziel.unlink(missing_ok=True)
        raise


def backup_vorbereiten(conn, dateiname: str) -> dict:
    """Bereitet ein Backup aus der Backup-Liste vor (nur gelistete Dateinamen)."""
    if not conn.execute("SELECT 1 FROM backups_log WHERE dateiname = ?", (dateiname,)).fetchone() \
            or Path(dateiname).name != dateiname:
        raise WiederherstellenFehler("Dieses Backup steht nicht in der Backup-Liste.")
    pfad = db_modul.BACKUP_VERZEICHNIS / dateiname
    if not pfad.exists():
        raise WiederherstellenFehler("Die Backup-Datei fehlt im Ordner Backups.")
    return _antwort(f"backup:{dateiname}", dateiname, pfad)


def _quelle_pfad(quelle: str) -> Path:
    art, _, wert = quelle.partition(":")
    if art == "upload" and wert.isalnum():
        return _staging() / f"{wert}.db"
    if art == "backup" and Path(wert).name == wert:
        return db_modul.BACKUP_VERZEICHNIS / wert
    raise WiederherstellenFehler("Unbekannte Quelle.")


def _kopieren(quelle: Path, ziel: Path) -> None:
    with open(quelle, "rb") as f_in, open(ziel, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def _backup_liste_uebernehmen(eintraege: list[dict]) -> None:
    """Ersetzt backups_log der eingespielten Datei durch die Liste der Installation."""
    conn = sqlite3.connect(db_modul.DB_PFAD)
    try:
        spalten = [r[1] for r in conn.execute("PRAGMA table_info(backups_log)")]
        conn.execute("DELETE FROM backups_log")
        for e in eintraege:
            felder = [s for s in spalten if s in e and s != "id"]
            conn.execute(f"INSERT INTO backups_log ({', '.join(felder)}) VALUES ({', '.join('?' * len(felder))})",
                         [e[s] for s in felder])
        conn.commit()
    finally:
        conn.close()


def ausfuehren(quelle: str, token: str, phrase: str, start) -> dict:
    """Spielt die Quelle ein. `start` ist der normale Programmstart
    (startup.ausfuehren), als Parameter, um Kreisimporte zu vermeiden."""
    zuruecksetzen.phrase_pruefen(token, phrase, {"wiederherstellen": quelle})
    pfad = _quelle_pfad(quelle)
    if not pfad.exists():
        raise WiederherstellenFehler("Die Datei ist nicht mehr vorhanden. Bitte neu hochladen.")
    with _SPERRE:
        kennzahlen(pfad)  # nochmals prüfen, die Datei könnte sich geändert haben
        quelle_text = pfad.name if quelle.startswith("backup:") else "hochgeladener Datei"
        conn = db_modul.verbindung()
        try:
            vorher = backup_modul.backup_erstellen(conn, "manuell",
                                                   beschreibung=f"vor Wiederherstellung aus {quelle_text}")
            liste = [dict(r) for r in conn.execute("SELECT * FROM backups_log ORDER BY id")]
        finally:
            conn.close()
        zwischen = db_modul.DB_PFAD.with_name(db_modul.DB_PFAD.name + ".neu")
        _kopieren(pfad, zwischen)
        os.replace(zwischen, db_modul.DB_PFAD)
        try:
            _backup_liste_uebernehmen(liste)
            ergebnis = start()
        except Exception as e:
            _kopieren(db_modul.BACKUP_VERZEICHNIS / vorher, zwischen)
            os.replace(zwischen, db_modul.DB_PFAD)
            _backup_liste_uebernehmen(liste)  # die Kopie kennt ihren eigenen Eintrag noch nicht
            raise WiederherstellenFehler(f"Der Start mit der eingespielten Datei ist gescheitert ({e}). "
                                         "Der vorherige Stand ist wieder aktiv.")
        if quelle.startswith("upload:"):
            pfad.unlink(missing_ok=True)
        return {"backup_vorher": vorher, "start": ergebnis, "kennzahlen": kennzahlen(db_modul.DB_PFAD)}

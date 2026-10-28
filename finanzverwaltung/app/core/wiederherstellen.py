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

Seit 3.0 öffnet das Einspielen auch verschlüsselte Dateien: den
verschlüsselten Download (.fvdb, mit Passphrase oder
Wiederherstellungsschlüssel) und Backups dieser Installation. Die
eingespielte Datei übernimmt dabei den Schutzzustand der Installation: Ist die
Verschlüsselung an, wird sie auf den aktuellen Datenschlüssel gebracht, sonst
entschlüsselt. Hochgeladene Dateien liegen im Zwischenordner schon in diesem
Zustand, also nie unverschlüsselt, wenn die Installation verschlüsselt ist.

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
from . import schutzdatei, tresor
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
    for datei in list(_staging().glob("*.db")) + list(_staging().glob("*.roh")):
        if datei.stat().st_mtime < grenze:
            datei.unlink(missing_ok=True)


def _schluessel_installation() -> bytes | None:
    return db_modul._SCHLUESSEL if db_modul.ist_verschluesselt() else None


def kennzahlen(pfad: Path, schluessel: bytes | None = None) -> dict:
    """Prüft eine Datenbankdatei nur lesend und liefert Kennzahlen. Ohne
    Schlüssel muss sie unverschlüsselt sein (SQLite-Kennung am Anfang)."""
    if schluessel is None:
        with open(pfad, "rb") as f:
            if f.read(16) != b"SQLite format 3\x00":
                raise WiederherstellenFehler("Die Datei ist keine SQLite-Datenbank.")
    try:
        conn = db_modul.oeffnen(pfad, schluessel, nur_lesen=True)
    except db_modul.FEHLER as e:
        raise WiederherstellenFehler(f"Die Datei lässt sich nicht öffnen: {e}")
    try:
        try:
            ergebnis = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except db_modul.FEHLER as e:
            if schluessel is not None:
                raise WiederherstellenFehler("Die Datei lässt sich mit dem Schlüssel dieser Installation nicht "
                                             "öffnen oder ist beschädigt.")
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
    datei = kennzahlen(pfad, _schluessel_installation())
    aktuell = kennzahlen(db_modul.DB_PFAD, _schluessel_installation()) if db_modul.DB_PFAD.exists() else None
    token, phrase = zuruecksetzen.phrase_ausstellen({"wiederherstellen": quelle})
    return {"quelle": quelle, "bezeichnung": bezeichnung, "datei": datei, "aktuell": aktuell,
            "token": token, "phrase": phrase}


def _angleichen(roh: Path, ziel: Path, geheimnis: str | None) -> None:
    """Bringt eine hochgeladene Datei in den Schutzzustand der Installation
    (seit 3.0) und schreibt sie nach ziel. roh wird danach gelöscht."""
    install = _schluessel_installation()
    try:
        fvdb = tresor.fvdb_lesen(roh)
    except (tresor.TresorFehler, ValueError):
        raise WiederherstellenFehler("Die verschlüsselte Datei ist beschädigt.")
    with open(roh, "rb") as f:
        klartext = f.read(16) == b"SQLite format 3\x00"
    if fvdb is None and klartext:
        if install is None:
            os.replace(roh, ziel)
        else:
            tresor._export(roh, ziel, None, install)
        return
    if fvdb is None:
        # SQLCipher-Datei ohne Kopf, etwa ein Backup dieser Installation
        if install is None:
            raise WiederherstellenFehler("Die Datei ist keine SQLite-Datenbank oder verschlüsselt ohne "
                                         "Schlüsselangaben. Bitte den verschlüsselten Download (.fvdb) verwenden.")
        os.replace(roh, ziel)
        return
    kopf, beginn = fvdb
    stand = schutzdatei.fehlversuche("datei_geheimnis")
    if stand["warten"]:
        raise WiederherstellenFehler(f"Zu viele Fehlversuche. Bitte {tresor._dauer(stand['warten'])} warten.")
    if not geheimnis:
        raise WiederherstellenFehler("Die Datei ist verschlüsselt. Bitte die Passphrase vom Zeitpunkt des "
                                     "Downloads oder den Wiederherstellungsschlüssel angeben.")
    schluessel = tresor.schluessel_aus_geheimnis(geheimnis, kopf)
    if not schluessel:
        schutzdatei.fehlversuch_zaehlen("datei_geheimnis")
        raise WiederherstellenFehler("Passphrase oder Wiederherstellungsschlüssel passt nicht zu dieser Datei.")
    schutzdatei.fehlversuche_loeschen("datei_geheimnis")
    rumpf = roh.with_suffix(".rumpf")
    with open(roh, "rb") as f_in, open(rumpf, "wb") as f_out:
        f_in.seek(beginn)
        shutil.copyfileobj(f_in, f_out)
    try:
        if install is not None and install == schluessel:
            os.replace(rumpf, ziel)
        else:
            tresor._export(rumpf, ziel, schluessel, install)
    except db_modul.FEHLER as e:
        raise WiederherstellenFehler(f"Die verschlüsselte Datei lässt sich nicht öffnen: {e}")
    finally:
        rumpf.unlink(missing_ok=True)


def upload_vorbereiten(stream, dateiname: str, geheimnis: str | None = None) -> dict:
    """Speichert eine hochgeladene Datei in Backups/.wiederherstellen und prüft sie."""
    _staging_aufraeumen()
    kennung = secrets.token_hex(8)
    ziel = _staging() / f"{kennung}.db"
    roh = _staging() / f"{kennung}.roh"
    groesse = 0
    with open(roh, "wb") as f:
        while block := stream.read(1024 * 1024):
            groesse += len(block)
            if groesse > MAX_GROESSE:
                f.close()
                roh.unlink(missing_ok=True)
                raise WiederherstellenFehler("Die Datei ist größer als 500 MB.")
            f.write(block)
    try:
        if groesse < 16:
            raise WiederherstellenFehler("Die Datei ist keine SQLite-Datenbank.")
        _angleichen(roh, ziel, geheimnis)
        return _antwort(f"upload:{kennung}", dateiname or "hochgeladene Datei", ziel)
    except WiederherstellenFehler:
        ziel.unlink(missing_ok=True)
        raise
    finally:
        roh.unlink(missing_ok=True)


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
    conn = db_modul.verbindung()
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
        kennzahlen(pfad, _schluessel_installation())  # nochmals prüfen, die Datei könnte sich geändert haben
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
        return {"backup_vorher": vorher, "start": ergebnis,
                "kennzahlen": kennzahlen(db_modul.DB_PFAD, _schluessel_installation())}

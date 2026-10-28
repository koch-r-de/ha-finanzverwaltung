"""
Verschlüsselung der Datenbank (seit 3.0, Issue #5).

Aufbau der Schlüssel:
  - Datenschlüssel: 32 zufällige Byte, Rohschlüssel für SQLCipher. Er ändert
    sich nie, solange die Verschlüsselung eingeschaltet bleibt. Deshalb passen
    alle Backups und ein verschlüsselter Download immer zum selben Schlüssel.
  - Er liegt nur verpackt (AES-256-GCM) in schutz.json, zweimal:
      mit der Passphrase (Argon2id, RFC 9106 Zweitempfehlung: t=3, 64 MiB, p=4)
      und mit dem Wiederherstellungsschlüssel (160 Bit, zum Ausdrucken, HKDF).
    Eine neue Passphrase verpackt den Datenschlüssel nur neu.
  - Im Arbeitsspeicher liegt er erst nach dem Entsperren (db._SCHLUESSEL).

Stapel: Solange die Datenbank zu ist, gehen Siri- und Schnellbuchungen
verschlüsselt in den Ordner stapel/. Jeder Eintrag hat einen eigenen
X25519-Schlüssel, aus dem mit dem öffentlichen Stapelschlüssel ein
AES-GCM-Schlüssel entsteht. Der private Stapelschlüssel liegt mit dem
Datenschlüssel verpackt in schutz.json und ist nur entsperrt nutzbar.

Auszug: Kontonamen, Kategorien, Sparziele und das Bundesland liegen als
auszug.json unverschlüsselt neben der Datenbank, damit Siri und die
Schnellbuchung auch gesperrt zuordnen können (Entscheidung 29). Die Regeln
gehören nicht dazu.
"""
import base64
import hashlib
import json
import logging
import os
import secrets
import shutil
import threading
import time
from pathlib import Path

from . import db as db_modul
from . import schutzdatei, zeit

LOG = logging.getLogger("app.schutz")

ARGON2 = {"zeit": 3, "speicher": 65536, "parallel": 4}
MINDESTLAENGE_UNTERGRENZE = 16
DOWNLOAD_GUELTIG_SEKUNDEN = 1800
FVDB_KENNUNG = b"FVDB1\n"
STAPEL_KENNUNG = b"FVST1"
_ZWECK_DATEN = b"finanzverwaltung-datenschluessel-v1"
_ZWECK_STAPEL = b"finanzverwaltung-stapelschluessel-v1"
_ZWECK_STAPEL_EINTRAG = b"finanzverwaltung-stapel-eintrag-v1"
_ZWECK_WH = b"finanzverwaltung-wiederherstellung-v1"
_B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

_UMSTELLUNG = threading.Lock()
_STAPEL_PRIVAT: bytes | None = None
_VORBEREITET: dict[str, dict] = {}
_KLARTEXT_DOWNLOAD = {"zeit": 0.0}


class TresorFehler(ValueError):
    """Fachlicher Fehler (falsche Passphrase, Wartezeit, ungültige Eingabe)."""


# ─── Grundbausteine ──────────────────────────────────────────────────

def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _aesgcm():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM


def _kek_passphrase(passphrase: str, salz: bytes, p: dict) -> bytes:
    from argon2.low_level import Type, hash_secret_raw
    return hash_secret_raw(passphrase.encode("utf-8"), salz, time_cost=p["zeit"], memory_cost=p["speicher"],
                           parallelism=p["parallel"], hash_len=32, type=Type.ID)


def _kek_wiederherstellung(roh: bytes, salz: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salz, info=_ZWECK_WH).derive(roh)


def _verpacken(kek: bytes, inhalt: bytes, zweck: bytes) -> dict:
    nonce = os.urandom(12)
    return {"nonce": _b64(nonce), "daten": _b64(_aesgcm()(kek).encrypt(nonce, inhalt, zweck))}


def _entpacken(kek: bytes, paket: dict, zweck: bytes) -> bytes | None:
    from cryptography.exceptions import InvalidTag
    try:
        return _aesgcm()(kek).decrypt(_unb64(paket["nonce"]), _unb64(paket["daten"]), zweck)
    except InvalidTag:
        return None


def passphrase_verpacken(passphrase: str, datenschluessel: bytes) -> dict:
    salz = os.urandom(16)
    return {"salz": _b64(salz), **ARGON2, **_verpacken(_kek_passphrase(passphrase, salz, ARGON2), datenschluessel, _ZWECK_DATEN)}


def wiederherstellung_verpacken(roh: bytes, datenschluessel: bytes) -> dict:
    salz = os.urandom(16)
    return {"salz": _b64(salz), **_verpacken(_kek_wiederherstellung(roh, salz), datenschluessel, _ZWECK_DATEN)}


def mit_passphrase_oeffnen(paket: dict, passphrase: str) -> bytes | None:
    kek = _kek_passphrase(passphrase, _unb64(paket["salz"]), paket)
    return _entpacken(kek, paket, _ZWECK_DATEN)


def mit_wiederherstellung_oeffnen(paket: dict, roh: bytes) -> bytes | None:
    return _entpacken(_kek_wiederherstellung(roh, _unb64(paket["salz"])), paket, _ZWECK_DATEN)


def wiederherstellungsschluessel_erzeugen() -> tuple[str, bytes]:
    """160 Bit als 32 Zeichen Base32 in Vierergruppen."""
    roh = os.urandom(20)
    text = base64.b32encode(roh).decode("ascii")
    return "-".join(text[i:i + 4] for i in range(0, 32, 4)), roh


def wiederherstellungsschluessel_lesen(text: str) -> bytes | None:
    """Verzeiht Kleinschreibung, Leer- und Trennzeichen sowie die
    Verwechslungen 0/O, 1/I und 8/B."""
    rein = "".join(ch for ch in (text or "").upper() if ch.isalnum())
    rein = rein.translate(str.maketrans({"0": "O", "1": "I", "8": "B"}))
    if len(rein) != 32 or any(ch not in _B32 for ch in rein):
        return None
    return base64.b32decode(rein)


# ─── Zustand ─────────────────────────────────────────────────────────

def einstellungen() -> dict | None:
    return schutzdatei.laden().get("verschluesselung")


def aktiv() -> bool:
    return bool(einstellungen())


def gesperrt() -> bool:
    return db_modul.ist_gesperrt()


def umstellung_laeuft() -> bool:
    return _UMSTELLUNG.locked()


def beim_start() -> bool:
    """Setzt den Zustand der Datenbankschicht. True = Datenbank ist zu."""
    global _STAPEL_PRIVAT
    _STAPEL_PRIVAT = None
    db_modul.verschluesselung_setzen(aktiv(), None)
    for rest in list(db_modul.basis_verzeichnis().glob("finanzdaten.db.verschluesselt")) + \
            list(db_modul.basis_verzeichnis().glob("finanzdaten.db.klartext")):
        rest.unlink(missing_ok=True)
    return db_modul.ist_gesperrt()


def mindestlaenge() -> int:
    e = einstellungen() or {}
    return max(MINDESTLAENGE_UNTERGRENZE, int(e.get("mindestlaenge") or MINDESTLAENGE_UNTERGRENZE))


def passphrase_pruefen_format(passphrase: str, wiederholung: str | None, laenge: int | None = None) -> None:
    laenge = laenge or mindestlaenge()
    if len(passphrase or "") < laenge:
        raise TresorFehler(f"Die Passphrase muss mindestens {laenge} Zeichen lang sein.")
    if wiederholung is not None and passphrase != wiederholung:
        raise TresorFehler("Die beiden Eingaben der Passphrase stimmen nicht überein.")


def _wartezeit_pruefen(schluessel: str) -> None:
    stand = schutzdatei.fehlversuche(schluessel)
    if stand["warten"]:
        raise TresorFehler(f"Zu viele Fehlversuche. Bitte {_dauer(stand['warten'])} warten.")


def _dauer(sekunden: int) -> str:
    if sekunden < 60:
        return f"{sekunden} Sekunden"
    minuten = (sekunden + 59) // 60
    return "1 Minute" if minuten == 1 else f"{minuten} Minuten"


def schluessel_aus_geheimnis(geheimnis: str, e: dict | None = None) -> bytes | None:
    """Datenschlüssel aus Passphrase oder Wiederherstellungsschlüssel."""
    e = e or einstellungen()
    if not e:
        return None
    roh = wiederherstellungsschluessel_lesen(geheimnis)
    if roh is not None:
        schluessel = mit_wiederherstellung_oeffnen(e["datenschluessel_wiederherstellung"], roh)
        if schluessel:
            return schluessel
    return mit_passphrase_oeffnen(e["datenschluessel_passphrase"], geheimnis or "")


def passphrase_bestaetigen(geheimnis: str) -> bytes:
    """Prüft Passphrase oder Wiederherstellungsschlüssel mit Wartezeit."""
    _wartezeit_pruefen("passphrase")
    schluessel = schluessel_aus_geheimnis(geheimnis)
    if not schluessel:
        schutzdatei.fehlversuch_zaehlen("passphrase")
        raise TresorFehler("Passphrase oder Wiederherstellungsschlüssel stimmt nicht.")
    schutzdatei.fehlversuche_loeschen("passphrase")
    return schluessel


def entsperren(geheimnis: str, neue_passphrase: str | None = None, wiederholung: str | None = None) -> list[str]:
    """Öffnet die Datenbank. Mit dem Wiederherstellungsschlüssel kann
    zugleich eine neue Passphrase gesetzt werden (vergessene Passphrase)."""
    global _STAPEL_PRIVAT
    if not aktiv():
        raise TresorFehler("Die Verschlüsselung ist nicht eingeschaltet.")
    if neue_passphrase is not None:
        passphrase_pruefen_format(neue_passphrase, wiederholung)
        if wiederherstellungsschluessel_lesen(geheimnis) is None:
            raise TresorFehler("Eine neue Passphrase lässt sich hier nur mit dem Wiederherstellungsschlüssel setzen.")
    schluessel = passphrase_bestaetigen(geheimnis)
    e = einstellungen()
    privat = _entpacken(schluessel, e["stapel_privat"], _ZWECK_STAPEL)
    schritte = []
    db_modul.verschluesselung_setzen(True, schluessel)
    _STAPEL_PRIVAT = privat
    schritte += _reste_umstellen(schluessel)
    try:
        conn = db_modul.verbindung()
        conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        conn.close()
    except db_modul.FEHLER as fehler:
        db_modul.verschluesselung_setzen(True, None)
        _STAPEL_PRIVAT = None
        raise TresorFehler(f"Die Datenbank lässt sich mit diesem Schlüssel nicht öffnen ({fehler}).")
    if neue_passphrase is not None:
        def setzen(d):
            d["verschluesselung"]["datenschluessel_passphrase"] = passphrase_verpacken(neue_passphrase, schluessel)
        schutzdatei.aendern(setzen)
        schritte.append("Neue Passphrase gesetzt")
    LOG.info("Datenbank entsperrt")
    for s in schritte:
        LOG.info("Verschlüsselung: %s", s)
    return schritte


def passphrase_aendern(geheimnis: str, neu: str, wiederholung: str) -> None:
    passphrase_pruefen_format(neu, wiederholung)
    schluessel = passphrase_bestaetigen(geheimnis)

    def setzen(d):
        d["verschluesselung"]["datenschluessel_passphrase"] = passphrase_verpacken(neu, schluessel)
    schutzdatei.aendern(setzen)
    LOG.info("Verschlüsselung: Passphrase geändert (Datenschlüssel neu verpackt, Datenbank unverändert)")


def mindestlaenge_setzen(laenge: int) -> int:
    if laenge < MINDESTLAENGE_UNTERGRENZE or laenge > 200:
        raise TresorFehler(f"Die Mindestlänge liegt zwischen {MINDESTLAENGE_UNTERGRENZE} und 200 Zeichen.")

    def setzen(d):
        d["verschluesselung"]["mindestlaenge"] = laenge
    schutzdatei.aendern(setzen)
    return laenge


# ─── Dateien umstellen ───────────────────────────────────────────────

def ist_klartext(pfad: Path) -> bool:
    with open(pfad, "rb") as f:
        return f.read(16) == b"SQLite format 3\x00"


def _export(quelle: Path, ziel: Path, schluessel_quelle: bytes | None, schluessel_ziel: bytes | None) -> None:
    """Kopiert eine Datenbank mit sqlcipher_export in eine neue Datei mit
    anderem Schlüssel (None = unverschlüsselt)."""
    if db_modul.sqlcipher is None:
        raise TresorFehler("SQLCipher (Paket sqlcipher3-wheels) ist nicht installiert.")
    ziel.unlink(missing_ok=True)
    conn = db_modul.sqlcipher.connect(str(quelle))
    try:
        conn.execute("PRAGMA cipher_log_level = NONE")
        if schluessel_quelle is not None:
            conn.execute(f"PRAGMA key = \"x'{schluessel_quelle.hex()}'\"")
        schl = f"x'{schluessel_ziel.hex()}'" if schluessel_ziel is not None else ""
        conn.execute(f"ATTACH DATABASE ? AS ziel KEY \"{schl}\"", (str(ziel),))
        conn.execute("SELECT sqlcipher_export('ziel')")
        conn.execute("DETACH DATABASE ziel")
    finally:
        conn.close()


def fingerabdruck(pfad: Path, schluessel: bytes | None) -> str:
    """Prüfsumme über Schema und alle Zeilen aller Tabellen."""
    conn = db_modul.oeffnen(pfad, schluessel, nur_lesen=True)
    try:
        h = hashlib.sha256()
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise TresorFehler(f"{pfad.name}: Prüfung der Datei fehlgeschlagen.")
        objekte = conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
        for typ, name, sql in objekte:
            h.update(repr((typ, name, sql)).encode())
            if typ == "table":
                for zeile in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid'):
                    h.update(repr(tuple(zeile)).encode())
        return h.hexdigest()
    finally:
        conn.close()


def _umstellen(quelle: Path, schluessel_alt: bytes | None, schluessel_neu: bytes | None,
               pruef_schluessel: list[bytes | None]) -> Path:
    """Schreibt quelle mit neuem Schlüssel nach quelle.umgestellt und prüft
    das Ergebnis mit jedem Schlüssel aus pruef_schluessel gegen das Original."""
    ziel = quelle.with_name(quelle.name + ".umgestellt")
    _export(quelle, ziel, schluessel_alt, schluessel_neu)
    soll = fingerabdruck(quelle, schluessel_alt)
    for s in pruef_schluessel:
        if fingerabdruck(ziel, s) != soll:
            ziel.unlink(missing_ok=True)
            raise TresorFehler(f"{quelle.name}: Inhalt nach dem Umstellen nicht gleich, abgebrochen.")
    return ziel


def _backup_dateien() -> list[Path]:
    ordner = db_modul.BACKUP_VERZEICHNIS
    return sorted(p for p in ordner.glob("*.db") if p.is_file()) if ordner.exists() else []


def _nebenordner_leeren() -> None:
    for ordner in (db_modul.BACKUP_VERZEICHNIS / ".wiederherstellen", db_modul.BACKUP_VERZEICHNIS / ".export"):
        shutil.rmtree(ordner, ignore_errors=True)


def _reste_umstellen(schluessel: bytes) -> list[str]:
    """Nach einer unterbrochenen Umstellung: unverschlüsselte Datenbank und
    Backups beim Entsperren nachträglich verschlüsseln."""
    schritte = []
    for datei in [db_modul.DB_PFAD] + _backup_dateien():
        if datei.exists() and ist_klartext(datei):
            neu = _umstellen(datei, None, schluessel, [schluessel])
            os.replace(neu, datei)
            schritte.append(f"Unverschlüsselte Datei nachträglich verschlüsselt: {datei.name}")
    return schritte


def klartext_download_merken() -> None:
    _KLARTEXT_DOWNLOAD["zeit"] = schutzdatei.uhr()


def klartext_download_vorhanden() -> bool:
    return schutzdatei.uhr() - _KLARTEXT_DOWNLOAD["zeit"] < DOWNLOAD_GUELTIG_SEKUNDEN


def einschalten_vorbereiten(passphrase: str, wiederholung: str, laenge: int | None = None) -> dict:
    """Schritt 1: prüfen, Schlüssel erzeugen und verpacken. Liefert den
    Wiederherstellungsschlüssel einmalig zur Anzeige."""
    if aktiv():
        raise TresorFehler("Die Verschlüsselung ist bereits eingeschaltet.")
    if db_modul.sqlcipher is None:
        raise TresorFehler("SQLCipher (Paket sqlcipher3-wheels) ist nicht installiert.")
    laenge = max(MINDESTLAENGE_UNTERGRENZE, int(laenge or MINDESTLAENGE_UNTERGRENZE))
    if not klartext_download_vorhanden():
        raise TresorFehler("Bitte zuerst die Datenbank unverschlüsselt herunterladen (Sicherung vor dem Umstellen).")
    passphrase_pruefen_format(passphrase, wiederholung, laenge)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    datenschluessel = os.urandom(32)
    wh_text, wh_roh = wiederherstellungsschluessel_erzeugen()
    privat = X25519PrivateKey.generate()
    privat_roh = privat.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                      serialization.NoEncryption())
    oeffentlich = privat.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    block = {
        "seit": zeit.jetzt().isoformat(timespec="seconds"),
        "mindestlaenge": laenge,
        "datenschluessel_passphrase": passphrase_verpacken(passphrase, datenschluessel),
        "datenschluessel_wiederherstellung": wiederherstellung_verpacken(wh_roh, datenschluessel),
        "stapel_oeffentlich": _b64(oeffentlich),
        "stapel_privat": _verpacken(datenschluessel, privat_roh, _ZWECK_STAPEL),
    }
    kennung = secrets.token_urlsafe(16)
    _VORBEREITET.clear()
    _VORBEREITET[kennung] = {"block": block, "schluessel": datenschluessel, "privat": privat_roh,
                             "wh_roh": wh_roh, "passphrase": passphrase, "bis": schutzdatei.uhr() + 900}
    return {"kennung": kennung, "wiederherstellungsschluessel": wh_text}


def einschalten_ausfuehren(kennung: str, getippt: str, backup_erstellen) -> list[str]:
    """Schritt 2 (Entscheidung 44): Backup, verschlüsselte Kopien von
    Datenbank und Backups, jede geprüft mit Passphrase UND
    Wiederherstellungsschlüssel, dann Schlüssel speichern, Dateien tauschen,
    Klartext entfernen. backup_erstellen(beschreibung) legt das Backup an."""
    global _STAPEL_PRIVAT
    v = _VORBEREITET.get(kennung or "")
    if not v or v["bis"] < schutzdatei.uhr():
        _VORBEREITET.pop(kennung or "", None)
        raise TresorFehler("Die Vorbereitung ist abgelaufen. Bitte neu beginnen.")
    if wiederherstellungsschluessel_lesen(getippt) != v["wh_roh"]:
        raise TresorFehler("Der abgetippte Wiederherstellungsschlüssel stimmt nicht.")
    if aktiv():
        raise TresorFehler("Die Verschlüsselung ist bereits eingeschaltet.")
    if not _UMSTELLUNG.acquire(blocking=False):
        raise TresorFehler("Es läuft bereits eine Umstellung.")
    schritte, neu = [], []
    try:
        def schritt(text):
            schritte.append(text)
            LOG.info("Verschlüsselung einschalten: %s", text)
        name = backup_erstellen("vor Einschalten der Verschlüsselung")
        schritt(f"Backup erstellt: {name}")
        s_pp = mit_passphrase_oeffnen(v["block"]["datenschluessel_passphrase"], v["passphrase"])
        s_wh = mit_wiederherstellung_oeffnen(v["block"]["datenschluessel_wiederherstellung"], v["wh_roh"])
        if not (s_pp == s_wh == v["schluessel"]):
            raise TresorFehler("Die verpackten Schlüssel lassen sich nicht öffnen, abgebrochen.")
        try:
            for datei in [db_modul.DB_PFAD] + _backup_dateien():
                if not ist_klartext(datei):
                    raise TresorFehler(f"{datei.name} ist nicht unverschlüsselt, abgebrochen.")
                neu.append((_umstellen(datei, None, v["schluessel"], [s_pp, s_wh]), datei))
            schritt(f"Datenbank und {len(neu) - 1} Backup(s) verschlüsselt kopiert und mit Passphrase "
                    "und Wiederherstellungsschlüssel geprüft (alle Tabellen gleich)")
        except Exception:
            for umgestellt, _ in neu:
                umgestellt.unlink(missing_ok=True)
            raise
        schutzdatei.aendern(lambda d: d.__setitem__("verschluesselung", v["block"]))
        schritt("Verpackte Schlüssel gespeichert")
        for umgestellt, datei in neu:
            os.replace(umgestellt, datei)
        _nebenordner_leeren()
        schritt("Unverschlüsselte Datenbank und Backups durch die verschlüsselten ersetzt")
        db_modul.verschluesselung_setzen(True, v["schluessel"])
        _STAPEL_PRIVAT = v["privat"]
        auszug_schreiben()
        schritt("Auszug für Siri und Schnellbuchung geschrieben (Konten, Kategorien, Sparziele)")
        _VORBEREITET.clear()
        return schritte
    finally:
        _UMSTELLUNG.release()


def ausschalten(geheimnis: str, backup_erstellen) -> list[str]:
    """Entschlüsselt Datenbank und Backups und entfernt die Schlüssel."""
    global _STAPEL_PRIVAT
    if not aktiv():
        raise TresorFehler("Die Verschlüsselung ist nicht eingeschaltet.")
    schluessel = passphrase_bestaetigen(geheimnis)
    if stapel_anzahl():
        raise TresorFehler("Im Stapel liegen noch Buchungen. Bitte zuerst neu laden, damit sie gebucht werden.")
    if not _UMSTELLUNG.acquire(blocking=False):
        raise TresorFehler("Es läuft bereits eine Umstellung.")
    schritte, neu = [], []
    try:
        def schritt(text):
            schritte.append(text)
            LOG.info("Verschlüsselung ausschalten: %s", text)
        name = backup_erstellen("vor Ausschalten der Verschlüsselung")
        schritt(f"Backup erstellt: {name}")
        try:
            for datei in [db_modul.DB_PFAD] + _backup_dateien():
                if ist_klartext(datei):
                    continue
                neu.append((_umstellen(datei, schluessel, None, [None]), datei))
            schritt(f"Datenbank und {len(neu) - 1} Backup(s) entschlüsselt kopiert und geprüft (alle Tabellen gleich)")
        except Exception:
            for umgestellt, _ in neu:
                umgestellt.unlink(missing_ok=True)
            raise
        for umgestellt, datei in neu:
            os.replace(umgestellt, datei)
        _nebenordner_leeren()
        schritt("Verschlüsselte Datenbank und Backups durch die entschlüsselten ersetzt")
        schutzdatei.aendern(lambda d: d.pop("verschluesselung", None))
        db_modul.verschluesselung_setzen(False, None)
        _STAPEL_PRIVAT = None
        auszug_pfad().unlink(missing_ok=True)
        shutil.rmtree(stapel_ordner(), ignore_errors=True)
        schritt("Schlüssel, Auszug und Stapel entfernt")
        return schritte
    finally:
        _UMSTELLUNG.release()


# ─── Auszug für Siri und Schnellbuchung ──────────────────────────────

def auszug_pfad() -> Path:
    return db_modul.basis_verzeichnis() / "auszug.json"


def auszug_schreiben() -> None:
    if not aktiv() or gesperrt():
        return
    conn = db_modul.verbindung()
    try:
        daten = {
            "konten": [dict(r) for r in conn.execute("SELECT id, name, aktiv FROM konten ORDER BY name")],
            "kategorien": [dict(r) for r in conn.execute(
                "SELECT id, name, parent_id, typ, system_key, siri_favorit FROM kategorien ORDER BY name")],
            "sparziele": [dict(r) for r in conn.execute(
                "SELECT id, name, konto_id FROM budgets WHERE typ = 'sparziel' ORDER BY name")],
            "bundesland": (conn.execute("SELECT value FROM einstellungen WHERE key = 'bundesland'").fetchone()
                           or {"value": ""})["value"],
        }
    finally:
        conn.close()
    schutzdatei._schreiben(auszug_pfad(), daten)


def auszug_lesen() -> dict:
    p = auszug_pfad()
    if not p.exists():
        return {"konten": [], "kategorien": [], "sparziele": [], "bundesland": ""}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ─── Stapel ──────────────────────────────────────────────────────────

def stapel_ordner() -> Path:
    return db_modul.basis_verzeichnis() / "stapel"


def stapel_anzahl() -> int:
    o = stapel_ordner()
    return len(list(o.glob("*.fvs"))) if o.exists() else 0


def stapel_ablegen(eintrag: dict) -> None:
    """Verschlüsselt einen Eintrag sofort mit dem öffentlichen Schlüssel."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    e = einstellungen()
    if not e:
        raise TresorFehler("Die Verschlüsselung ist nicht eingeschaltet.")
    empfaenger = X25519PublicKey.from_public_bytes(_unb64(e["stapel_oeffentlich"]))
    einmal = X25519PrivateKey.generate()
    einmal_oeff = einmal.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    k = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_ZWECK_STAPEL_EINTRAG).derive(einmal.exchange(empfaenger))
    nonce = os.urandom(12)
    inhalt = json.dumps({**eintrag, "erfasst_am": zeit.jetzt().isoformat(timespec="seconds"),
                         "folge": time.time_ns()},
                        ensure_ascii=False).encode("utf-8")
    daten = STAPEL_KENNUNG + einmal_oeff + nonce + _aesgcm()(k).encrypt(nonce, inhalt, einmal_oeff)
    stapel_ordner().mkdir(exist_ok=True)
    ziel = stapel_ordner() / f"{secrets.token_hex(12)}.fvs"
    zwischen = ziel.with_suffix(".neu")
    with open(zwischen, "wb") as f:
        f.write(daten)
        f.flush()
        os.fsync(f.fileno())
    os.replace(zwischen, ziel)


def _stapel_lesen(datei: Path) -> dict:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    daten = datei.read_bytes()
    if not daten.startswith(STAPEL_KENNUNG) or _STAPEL_PRIVAT is None:
        raise TresorFehler("Unbekanntes Format")
    rest = daten[len(STAPEL_KENNUNG):]
    einmal_oeff, nonce, chiffre = rest[:32], rest[32:44], rest[44:]
    privat = X25519PrivateKey.from_private_bytes(_STAPEL_PRIVAT)
    k = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_ZWECK_STAPEL_EINTRAG).derive(
        privat.exchange(X25519PublicKey.from_public_bytes(einmal_oeff)))
    return json.loads(_aesgcm()(k).decrypt(nonce, chiffre, einmal_oeff))


def stapel_abarbeiten(buchen) -> dict:
    """Bucht alle Einträge in der Reihenfolge der Erfassung. buchen(conn,
    eintrag) legt die Buchung an (buchungen.buchung_anlegen schreibt dabei
    fest) oder wirft eine Ausnahme mit dem Grund, dann kommt der Eintrag in
    die Klärliste. Die Kennung des Eintrags wird vor dem Buchen in
    stapel_erledigt geschrieben und mit der Buchung zusammen festgeschrieben.
    Die Datei wird erst danach gelöscht. Endet das Programm dazwischen, wird
    sie beim nächsten Entsperren nur noch entfernt, nicht doppelt gebucht."""
    ordner = stapel_ordner()
    dateien = sorted(ordner.glob("*.fvs")) if ordner.exists() else []
    ergebnis = {"gebucht": 0, "klaerliste": 0}
    if not dateien:
        return ergebnis
    eintraege = []
    for datei in dateien:
        try:
            eintraege.append((datei, _stapel_lesen(datei)))
        except Exception as fehler:  # beschädigt: in die Klärliste mit Hinweis
            eintraege.append((datei, {"fehler": f"Eintrag nicht lesbar ({type(fehler).__name__})", "erfasst_am": ""}))
    eintraege.sort(key=lambda x: (x[1].get("erfasst_am", ""), x[1].get("folge", 0)))
    conn = db_modul.verbindung()
    try:
        for datei, eintrag in eintraege:
            kennung = datei.stem
            if conn.execute("SELECT 1 FROM stapel_erledigt WHERE kennung = ?", (kennung,)).fetchone():
                datei.unlink(missing_ok=True)
                continue
            try:
                if "fehler" in eintrag:
                    raise ValueError(eintrag["fehler"])
                conn.execute("INSERT INTO stapel_erledigt (kennung) VALUES (?)", (kennung,))
                buchen(conn, eintrag)
                conn.commit()
                ergebnis["gebucht"] += 1
            except Exception as fehler:
                conn.rollback()
                grund = getattr(fehler, "detail", None) or str(fehler)
                conn.execute("INSERT INTO klaerliste (quelle, erfasst_am, daten, grund) VALUES (?, ?, ?, ?)",
                             (eintrag.get("quelle", "?"), eintrag.get("erfasst_am", ""),
                              json.dumps({k: v for k, v in eintrag.items() if k not in ("erfasst_am", "folge", "quelle")},
                                         ensure_ascii=False), grund))
                conn.execute("INSERT OR IGNORE INTO stapel_erledigt (kennung) VALUES (?)", (kennung,))
                conn.commit()
                ergebnis["klaerliste"] += 1
            datei.unlink(missing_ok=True)
    finally:
        conn.close()
    LOG.info("Stapel: %s gebucht, %s in die Klärliste", ergebnis["gebucht"], ergebnis["klaerliste"])
    return ergebnis


# ─── Datenbank-Download und Wiederherstellen ─────────────────────────

def download_kopf() -> bytes:
    """Kopf einer verschlüsselten Download-Datei (.fvdb): Kennung, Länge,
    die beiden verpackten Datenschlüssel. Danach folgt die SQLCipher-Datei."""
    e = einstellungen()
    kopf = json.dumps({"datenschluessel_passphrase": e["datenschluessel_passphrase"],
                       "datenschluessel_wiederherstellung": e["datenschluessel_wiederherstellung"]}).encode()
    return FVDB_KENNUNG + len(kopf).to_bytes(4, "big") + kopf


def fvdb_lesen(pfad: Path) -> tuple[dict, int] | None:
    """Kopf und Beginn der Datenbank, falls pfad eine .fvdb-Datei ist."""
    with open(pfad, "rb") as f:
        if f.read(len(FVDB_KENNUNG)) != FVDB_KENNUNG:
            return None
        laenge = int.from_bytes(f.read(4), "big")
        if not 0 < laenge < 100000:
            raise TresorFehler("Die verschlüsselte Datei ist beschädigt.")
        kopf = json.loads(f.read(laenge))
        return kopf, len(FVDB_KENNUNG) + 4 + laenge


def klartext_kopie(ziel: Path) -> None:
    """Unverschlüsselte Kopie der aktuellen Datenbank (Download mit Phrase)."""
    _export(db_modul.DB_PFAD, ziel, db_modul._SCHLUESSEL, None)


# ─── XLSX mit Kennwort ───────────────────────────────────────────────

def xlsx_verschluesseln(daten: bytes, kennwort: str) -> bytes:
    import io
    from msoffcrypto.format.ooxml import OOXMLFile
    aus = io.BytesIO()
    OOXMLFile(io.BytesIO(daten)).encrypt(kennwort, aus)
    return aus.getvalue()


def xlsx_ist_verschluesselt(daten: bytes) -> bool:
    return daten[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def xlsx_entschluesseln(daten: bytes, kennwort: str | None) -> bytes:
    import io
    import msoffcrypto
    if not kennwort:
        raise TresorFehler("Die Datei ist mit einem Kennwort geschützt. Bitte das Kennwort angeben.")
    try:
        datei = msoffcrypto.OfficeFile(io.BytesIO(daten))
        datei.load_key(password=kennwort)
        aus = io.BytesIO()
        datei.decrypt(aus)
    except Exception:
        raise TresorFehler("Das Kennwort der Excel-Datei stimmt nicht oder die Datei ist beschädigt.")
    return aus.getvalue()

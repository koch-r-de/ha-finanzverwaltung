"""
Ablage der Schutzeinstellungen (seit 3.0).

Sperre und Verschlüsselung brauchen Angaben, die schon vor dem Entsperren der
Datenbank lesbar sein müssen: Code-Hashes, die verpackten Schlüssel, den
öffentlichen Schlüssel des Stapels. Sie liegen deshalb nicht in der Datenbank,
sondern in schutz.json neben ihr. Die Datei enthält nur Hashes und
verschlüsselte Schlüssel, nie einen Code, eine Passphrase oder den
Datenschlüssel selbst.

Die Fehlversuche stehen in einer eigenen Datei schutz_zaehler.json, weil sie
oft geschrieben werden und einen Neustart überdauern müssen.

Wartezeit nach Fehlversuchen (Entscheidung 32): ab dem 5. Fehlversuch 1 Minute,
dann verdoppelnd bis höchstens 1 Stunde. Die Uhr kommt aus uhr(), damit Tests
sie einfrieren können.
"""
import copy
import json
import os
import threading
from pathlib import Path

from . import zeit
from .db import basis_verzeichnis

_SPERRE = threading.RLock()
_CACHE: dict | None = None
_ZAEHLER: dict | None = None

AB_FEHLVERSUCH = 5
WARTEZEIT_START = 60
WARTEZEIT_MAX = 3600


def uhr() -> float:
    """Sekunden seit 1970. Tests ersetzen diese Funktion (eingefrorene Uhr)."""
    return zeit.jetzt().timestamp()


def pfad() -> Path:
    return basis_verzeichnis() / "schutz.json"


def zaehler_pfad() -> Path:
    return basis_verzeichnis() / "schutz_zaehler.json"


def _schreiben(ziel: Path, daten: dict) -> None:
    zwischen = ziel.with_name(ziel.name + ".neu")
    with open(zwischen, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(zwischen, ziel)


def _lesen(quelle: Path) -> dict:
    if not quelle.exists():
        return {}
    with open(quelle, encoding="utf-8") as f:
        return json.load(f)


def laden() -> dict:
    """Kopie der Schutzeinstellungen (leeres dict = kein Schutz)."""
    global _CACHE
    with _SPERRE:
        if _CACHE is None:
            _CACHE = _lesen(pfad())
        return copy.deepcopy(_CACHE)


def speichern(daten: dict) -> None:
    global _CACHE
    with _SPERRE:
        _schreiben(pfad(), daten)
        _CACHE = copy.deepcopy(daten)


def aendern(funktion):
    """Liest, ändert mit funktion(daten) und speichert unter einer Sperre."""
    with _SPERRE:
        daten = laden()
        ergebnis = funktion(daten)
        speichern(daten)
        return ergebnis


def neu_laden() -> None:
    """Vergisst den Zwischenspeicher (nach Wiederherstellen, in Tests)."""
    global _CACHE, _ZAEHLER
    with _SPERRE:
        _CACHE = None
        _ZAEHLER = None


# ─── Fehlversuche ────────────────────────────────────────────────────

def _zaehler() -> dict:
    global _ZAEHLER
    if _ZAEHLER is None:
        _ZAEHLER = _lesen(zaehler_pfad())
    return _ZAEHLER


def wartezeit(anzahl: int) -> int:
    if anzahl < AB_FEHLVERSUCH:
        return 0
    return min(WARTEZEIT_MAX, WARTEZEIT_START * 2 ** (anzahl - AB_FEHLVERSUCH))


def fehlversuche(schluessel: str, grenze: int = 0) -> dict:
    """Stand für einen Zähler: anzahl, warten (Sekunden), dauerhaft.
    grenze 0 = ohne Limit (nur Wartezeit)."""
    with _SPERRE:
        eintrag = _zaehler().get(schluessel) or {"anzahl": 0, "letzter": 0}
    anzahl = eintrag["anzahl"]
    rest = max(0, int(eintrag["letzter"] + wartezeit(anzahl) - uhr() + 0.999)) if anzahl else 0
    return {"anzahl": anzahl, "warten": rest, "dauerhaft": bool(grenze and anzahl >= grenze)}


def fehlversuch_zaehlen(schluessel: str) -> None:
    with _SPERRE:
        z = _zaehler()
        eintrag = z.get(schluessel) or {"anzahl": 0, "letzter": 0}
        z[schluessel] = {"anzahl": eintrag["anzahl"] + 1, "letzter": uhr()}
        _schreiben(zaehler_pfad(), z)


def fehlversuche_loeschen(schluessel: str) -> None:
    with _SPERRE:
        z = _zaehler()
        if schluessel in z:
            del z[schluessel]
            _schreiben(zaehler_pfad(), z)


def alle_fehlversuche_loeschen(praefix: str = "") -> None:
    with _SPERRE:
        z = _zaehler()
        for k in [k for k in z if k.startswith(praefix)]:
            del z[k]
        _schreiben(zaehler_pfad(), z)

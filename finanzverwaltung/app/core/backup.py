"""
Backup-Verwaltung: automatische Erstellung zum 15. und Monatsultimo
(beim Programmstart nachgeholt, falls der Checkpoint verpasst wurde,
weil die App an dem Tag nicht lief) sowie manuelles Backup per
Knopfdruck. Es werden immer nur die letzten 12 Backups behalten,
ältere werden automatisch gelöscht.
"""
import shutil
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .db import BACKUP_VERZEICHNIS, DB_PFAD
from . import zeit

MAX_BACKUPS = 12


def _ultimo(jahr: int, monat: int) -> date:
    return date(jahr, monat, monthrange(jahr, monat)[1])


def _juengster_checkpoint(heute: date) -> tuple[date, str]:
    """Der letzte fällige Checkpoint (15. oder Ultimo) bis einschließlich heute."""
    fuenfzehnter = date(heute.year, heute.month, 15)
    ultimo = _ultimo(heute.year, heute.month)
    if heute >= ultimo:
        return ultimo, "automatisch_ultimo"
    if heute >= fuenfzehnter:
        return fuenfzehnter, "automatisch_15"
    vormonat_letzter_tag = heute.replace(day=1) - timedelta(days=1)
    return _ultimo(vormonat_letzter_tag.year, vormonat_letzter_tag.month), "automatisch_ultimo"


def _datei_kopieren(quelle: Path, ziel: Path) -> None:
    """Manuelles Kopieren statt shutil.copy2/shutil.copy: vermeidet die
    plattformspezifischen Fast-Copy-Syscalls (z. B. CopyFile2 unter
    Windows), die nicht in jeder Umgebung verfügbar sind."""
    with open(quelle, "rb") as f_in, open(ziel, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def backup_erstellen(conn, typ: str = "manuell", heute: Optional[date] = None,
                     beschreibung: Optional[str] = None) -> str:
    """Erstellt ein Backup. Mit `beschreibung` (z. B. "vor Löschung von: ...",
    seit v1.8) bekommt der Dateiname zusätzlich eine Uhrzeit, damit mehrere
    Backups am selben Tag sich nicht gegenseitig überschreiben."""
    heute = heute or zeit.heute()
    BACKUP_VERZEICHNIS.mkdir(exist_ok=True)
    if beschreibung:
        dateiname = f"finanzdaten_{heute.isoformat()}_{zeit.jetzt().strftime('%H%M%S')}_{typ}.db"
    else:
        dateiname = f"finanzdaten_{heute.isoformat()}_{typ}.db"
    # Seit v2.4 (Befund N): nie ein vorhandenes Backup überschreiben, z. B. bei
    # zwei Backups in derselben Sekunde (Wiederherstellen + Kategorie-Umstellung).
    stamm, nummer = dateiname[:-3], 2
    while (BACKUP_VERZEICHNIS / dateiname).exists():
        dateiname = f"{stamm}_{nummer}.db"
        nummer += 1
    _datei_kopieren(DB_PFAD, BACKUP_VERZEICHNIS / dateiname)
    conn.execute("INSERT INTO backups_log (dateiname, typ, beschreibung) VALUES (?, ?, ?)",
                 (dateiname, typ, beschreibung))
    conn.commit()
    _rotieren(conn)
    return dateiname


def automatisches_backup_falls_faellig(conn, heute: Optional[date] = None) -> Optional[str]:
    heute = heute or zeit.heute()
    checkpoint_datum, typ = _juengster_checkpoint(heute)
    # Seit v2.4 genau der Stichtag (Befund O, siehe unten)
    vorhanden = conn.execute(
        "SELECT 1 FROM backups_log WHERE typ = ? AND dateiname LIKE ?",
        (typ, f"finanzdaten_{checkpoint_datum.isoformat()}%"),
    ).fetchone()
    if vorhanden:
        return None
    # Seit v2.4 (Befund O) nach dem Stichtag benannt: bis 2.3 trug das
    # nachgeholte Ultimo-Backup das Datum des Starttags (z. B. 2026-10-13 statt
    # 2026-09-30), die Prüfung oben fand es nie, und vom 1. bis 14. entstand bei
    # jedem Start ein weiteres, das ältere Backups aus der Rotation drängte.
    return backup_erstellen(conn, typ, checkpoint_datum)


def _rotieren(conn) -> None:
    alle = conn.execute(
        "SELECT id, dateiname FROM backups_log ORDER BY erstellt_am DESC, id DESC"
    ).fetchall()
    for row in alle[MAX_BACKUPS:]:
        (BACKUP_VERZEICHNIS / row["dateiname"]).unlink(missing_ok=True)
        conn.execute("DELETE FROM backups_log WHERE id = ?", (row["id"],))
    conn.commit()

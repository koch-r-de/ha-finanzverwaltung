"""
Automatisierungen beim Programmstart (Fachkonzept Abschnitt 11.1):
  1. Feiertage: seit v2.6 nicht mehr gespeichert, verschoben wird nach dem
     TARGET-Kalender (feiertage.bank_kalender)
  2. Wiederkehrende Buchungen generieren (fällige Termine)
  3. Darlehensraten generieren
  4. Plan-Buchungen mit Datum <= heute automatisch in Ist umwandeln
  5. Fälliges Backup erstellen (15. / Monatsultimo)
"""
import logging
from datetime import date
from typing import Optional

from . import altersvorsorge, backup, darlehensraten, plan_buchungen, wiederkehrend
from .db import initialisieren, verbindung
from .feiertage import bank_kalender
from . import zeit

LOG = logging.getLogger(__name__)


def ausfuehren(heute: Optional[date] = None) -> dict:
    """Führt alle Start-Automatisierungen aus und gibt eine Zusammenfassung zurück."""
    heute = heute or zeit.heute()
    init = initialisieren()
    # Seit v2.2 (Befund L): jeder Migrationsschritt steht auch im Add-on-Protokoll.
    for schritt in init["migration"]:
        LOG.info("Migration: %s", schritt)
    conn = verbindung()
    try:
        feiertage = bank_kalender()
        anzahl_wiederkehrend = wiederkehrend.erzeuge_faellige_ist_buchungen(conn, feiertage, heute)
        anzahl_raten = darlehensraten.erzeuge_faellige_ist_buchungen(conn, feiertage, heute)
        anzahl_altersvorsorge = altersvorsorge.erzeuge_faellige_ist_buchungen(conn, feiertage, heute)
        umgewandelt_ids = plan_buchungen.umwandeln_faellige(conn, heute)
        backup_datei = backup.automatisches_backup_falls_faellig(conn, heute)

        from .db import sparziel_konflikte, vorlagen_vorzeichen_konflikte, vorzeichen_konflikte
        sz_konflikte = sparziel_konflikte(conn)
        return {
            "datenbank_neu_angelegt": init["datenbank_neu_angelegt"],
            "migration": init["migration"],
            "vorzeichen_konflikte_buchungen": len(vorzeichen_konflikte(conn)),
            "vorzeichen_konflikte_vorlagen": len(vorlagen_vorzeichen_konflikte(conn)),
            "sparziel_konflikte": len(sz_konflikte["buchungen"]) + len(sz_konflikte["vorlagen"]),
            "anzahl_neue_ist_buchungen_wiederkehrend": anzahl_wiederkehrend,
            "anzahl_neue_ist_buchungen_darlehen": anzahl_raten,
            "anzahl_neue_ist_buchungen_altersvorsorge": anzahl_altersvorsorge,
            "umgewandelte_plan_buchungen": umgewandelt_ids,
            "backup_erstellt": backup_datei,
        }
    finally:
        conn.close()

"""
Zentrale Zeitbestimmung (seit v2.0, Befund H).

Bis 1.10 bestimmte der Server "heute" überall mit date.today(), also in der
Zeitzone des Containers. Dockerfile und run.sh setzen keine; läuft der
Container in UTC, buchten die Generatoren zwischen 0 und 1 Uhr (Sommerzeit
2 Uhr) deutscher Zeit noch für den Vortag. Seit 2.0 gilt fest Europe/Berlin,
unabhängig von der Container-Zeitzone. Die Zeitzonendaten liefert das
Python-Paket tzdata (requirements-docker.txt), falls das Image keine hat.

Neue Stellen IMMER zeit.heute()/zeit.jetzt() verwenden, nie date.today().
"""
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

ZEITZONE_NAME = "Europe/Berlin"
ZEITZONE = ZoneInfo(ZEITZONE_NAME)


# Nur für das Bildwerkzeug der Hilfe (werkzeuge/hilfe_bilder.py, seit v2.1):
# feste Uhrzeit im ISO-Format, z. B. "2026-10-13T10:00:00". Im Add-on nie gesetzt.
_FESTE_ZEIT = os.environ.get("FINANZAPP_FESTE_ZEIT")


def jetzt() -> datetime:
    if _FESTE_ZEIT:
        return datetime.fromisoformat(_FESTE_ZEIT).replace(tzinfo=ZEITZONE)
    return datetime.now(ZEITZONE)


def heute() -> date:
    return jetzt().date()

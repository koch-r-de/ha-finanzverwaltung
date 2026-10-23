"""
Feiertagsberechnung für Nordrhein-Westfalen (NRW).

Alle Feiertage werden rein lokal berechnet - feste Termine plus
bewegliche Termine über die Gaußsche Osterformel. Es ist keine
Internetabfrage nötig, das passt zur Anforderung "ausschließlich
lokale Speicherung" und funktioniert für beliebige Jahre (auch weit
in der Zukunft) ohne externe Abhängigkeit.
"""

from datetime import date, timedelta


def ostersonntag(jahr: int) -> date:
    """Berechnet den Ostersonntag für ein gegebenes Jahr (Gaußsche Osterformel)."""
    a = jahr % 19
    b = jahr // 100
    c = jahr % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat = (h + l - 7 * m + 114) // 31
    tag = ((h + l - 7 * m + 114) % 31) + 1
    return date(jahr, monat, tag)


def nrw_feiertage(jahr: int) -> dict[date, str]:
    """Liefert alle gesetzlichen Feiertage in NRW für ein Jahr."""
    ostern = ostersonntag(jahr)
    return {
        date(jahr, 1, 1): "Neujahr",
        ostern - timedelta(days=2): "Karfreitag",
        ostern + timedelta(days=1): "Ostermontag",
        date(jahr, 5, 1): "Tag der Arbeit",
        ostern + timedelta(days=39): "Christi Himmelfahrt",
        ostern + timedelta(days=50): "Pfingstmontag",
        ostern + timedelta(days=60): "Fronleichnam",
        date(jahr, 10, 3): "Tag der Deutschen Einheit",
        date(jahr, 11, 1): "Allerheiligen",
        date(jahr, 12, 25): "1. Weihnachtstag",
        date(jahr, 12, 26): "2. Weihnachtstag",
    }


def feiertage_zeitraum(start_jahr: int, anzahl_jahre: int = 20) -> dict[date, str]:
    """Feiertage für mehrere Jahre am Stück (Standard: 20 Jahre voraus)."""
    alle: dict[date, str] = {}
    for jahr in range(start_jahr, start_jahr + anzahl_jahre):
        alle.update(nrw_feiertage(jahr))
    return alle


def ist_feiertag_oder_wochenende(datum: date, feiertage: dict[date, str]) -> bool:
    return datum.weekday() >= 5 or datum in feiertage


def vorheriger_werktag(datum: date, feiertage: dict[date, str]) -> date:
    """
    Verschiebt ein Datum auf den vorherigen Werktag, falls es auf ein
    Wochenende oder einen Feiertag fällt (für Fälligkeitstermine von
    Buchungen/Darlehen).
    """
    while ist_feiertag_oder_wochenende(datum, feiertage):
        datum -= timedelta(days=1)
    return datum

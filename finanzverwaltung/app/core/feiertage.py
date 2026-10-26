"""
Feiertage in Deutschland, rein lokal berechnet (seit v2.6).

Zwei Kalender aus einer einzigen Regeltabelle (REGELN):

- Feiertage der vom Anwender gewählten Region (Einstellung "bundesland").
  Sie werden nur markiert: Hinweis bei der Eingabe eines Datums und Symbol
  in Buchungsliste und Vorschau. Nichts wird gesperrt oder übersprungen.
- TARGET-Schließtage der EZB (Region "TARGET"). Nur nach ihnen und nach dem
  Wochenende verschiebt das Programm fällige Termine aus Vorlagen,
  Darlehensraten und Altersvorsorge auf den Werktag davor. Das Bundesland
  ändert daher kein einziges Buchungs- oder Prognosedatum.

Eine Zeile je Feiertag: Name, Regel (festes Datum "MM-TT", Abstand zum
Ostersonntag "O+n"/"O-n" oder Sonderregel "BUB" für den Buß- und Bettag),
betroffene Regionen und Gültigkeit als Jahresintervall [von, bis], offenes
Ende = 9999, einmalige Feiertage mit von = bis. Ändert ein Land sein
Feiertagsgesetz, genügt eine neue Zeile (die alte bekommt ein "bis").

Gültigkeit "von 1990" heißt: gilt mindestens seit 1990, Früheres ist nicht
abgebildet. Angaben, die bei der Erstellung nicht an einer Quelle belegt
werden konnten, tragen den Status "ungeprüft". Recherche und Quellen:
DOCS.md, Abschnitt "Neu in Version 2.6".
"""

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

OFFEN = 9999

# ─── Regionen ───────────────────────────────────────────────────────
# Reihenfolge = Reihenfolge in der Auswahl. Regionale Sonderfälle sind
# eigene Einträge, benannt nach dem Feiertag, nicht nach der Konfession.
REGIONEN: list[tuple[str, str]] = [
    ("BW", "Baden-Württemberg"),
    ("BY_MH", "Bayern – mit Mariä Himmelfahrt"),
    ("BY_O", "Bayern – ohne Mariä Himmelfahrt"),
    ("BY_A", "Bayern – Stadt Augsburg"),
    ("BE", "Berlin"),
    ("BB", "Brandenburg"),
    ("HB", "Bremen"),
    ("HH", "Hamburg"),
    ("HE", "Hessen"),
    ("MV", "Mecklenburg-Vorpommern"),
    ("NI", "Niedersachsen"),
    ("NW", "Nordrhein-Westfalen"),
    ("RP", "Rheinland-Pfalz"),
    ("SL", "Saarland"),
    ("SN", "Sachsen"),
    ("SN_F", "Sachsen – mit Fronleichnam"),
    ("ST", "Sachsen-Anhalt"),
    ("SH", "Schleswig-Holstein"),
    ("TH", "Thüringen"),
    ("TH_F", "Thüringen – mit Fronleichnam"),
]
REGION_NAMEN = dict(REGIONEN)
TARGET = "TARGET"
# Vorschlag für Installationen, die vor 2.6 angelegt wurden (bisher fest NRW).
VORSCHLAG_BESTAND = "NW"

ALLE = frozenset(k for k, _ in REGIONEN)
BY = frozenset({"BY_MH", "BY_O", "BY_A"})


def _r(*teile) -> frozenset:
    """Regionen zusammensetzen, Mengen (ALLE, BY) und einzelne Kürzel gemischt."""
    menge = set()
    for t in teile:
        menge |= set(t) if isinstance(t, frozenset) else {t}
    return frozenset(menge)


# ─── Gesetze je Land ────────────────────────────────────────────────
# Fundstelle der Liste der gesetzlichen Feiertage. Die Zeilen der
# Regeltabelle verweisen darauf über das Kürzel der Region.
GESETZE: dict[str, str] = {
    "BW": "Feiertagsgesetz (FTG) Baden-Württemberg vom 08.05.1995, § 1",
    "BY": "Feiertagsgesetz (FTG) Bayern vom 21.05.1980, Art. 1",
    "BE": "Gesetz über die Sonn- und Feiertage Berlin vom 28.10.1954, § 1",
    "BB": "Feiertagsgesetz (FTG) Brandenburg vom 21.03.1991, § 2",
    "HB": "Gesetz über die Sonn- und Feiertage Bremen vom 12.11.1954, § 2",
    "HH": "Feiertagsgesetz Hamburg vom 16.10.1953, § 1",
    "HE": "Hessisches Feiertagsgesetz (HFeiertagsG) vom 29.12.1971, § 1",
    "MV": "Feiertagsgesetz Mecklenburg-Vorpommern (FTG M-V) vom 08.03.2002, § 2",
    "NI": "Niedersächsisches Gesetz über die Feiertage (NFeiertagsG) vom 07.03.1995, § 2",
    "NW": "Feiertagsgesetz Nordrhein-Westfalen (FeiertG NRW), § 2",
    "RP": "Landesfeiertagsgesetz (LFtG) Rheinland-Pfalz vom 15.07.1970, § 2",
    "SL": "Feiertagsgesetz (SFG) Saarland, Gesetz Nr. 1040 vom 18.02.1976, § 2",
    "SN": "Sächsisches Sonn- und Feiertagsgesetz (SächsSFG) vom 10.11.1992, § 1",
    "ST": "Feiertagsgesetz Sachsen-Anhalt (FeiertG LSA) vom 25.08.2004, § 2",
    "SH": "Sonn- und Feiertagsgesetz (SFTG) Schleswig-Holstein vom 28.06.2004, § 2",
    "TH": "Thüringer Feier- und Gedenktagsgesetz (ThürFGtG) vom 21.12.1994, § 2",
    TARGET: "EZB, langfristiger Kalender der TARGET-Schließtage, Pressemitteilung vom 14.12.2000",
}
LANDESGESETZE = "Feiertagsgesetze der Länder (siehe GESETZE)"


# ─── Regeltabelle ───────────────────────────────────────────────────

@dataclass(frozen=True)
class Regel:
    name: str
    regel: str            # "MM-TT", "O+n" / "O-n" oder "BUB"
    regionen: frozenset
    von: int
    bis: int
    rechtsgrundlage: str
    status: str           # "geprüft" oder "ungeprüft" (mit Zusatz)


REGELN: tuple[Regel, ...] = (
    Regel("Neujahr", "01-01", ALLE, 1990, OFFEN, LANDESGESETZE, "geprüft"),
    Regel("Heilige Drei Könige", "01-06", _r("BW", BY, "ST"), 1990, OFFEN,
          "FTG BW § 1, FTG Bayern Art. 1, FeiertG LSA § 2 Nr. 2", "geprüft, Beginn ST ungeprüft"),
    Regel("Frauentag", "03-08", _r("BE"), 2019, OFFEN,
          "Drittes Gesetz zur Änderung des Gesetzes über die Sonn- und Feiertage Berlin vom 30.01.2019 (GVBl. S. 22)",
          "geprüft"),
    Regel("Frauentag", "03-08", _r("MV"), 2023, OFFEN, "FTG M-V § 2 Abs. 1 Nr. 2",
          "geprüft, Beginn 2023 nur aus Sekundärquelle"),
    Regel("Karfreitag", "O-2", ALLE, 1990, OFFEN, LANDESGESETZE, "geprüft"),
    Regel("Ostersonntag", "O+0", _r("BB"), 1990, OFFEN, "FTG Brandenburg § 2 Abs. 1 Nr. 3", "geprüft"),
    Regel("Ostermontag", "O+1", ALLE, 1990, OFFEN, LANDESGESETZE, "geprüft"),
    Regel("Tag der Arbeit", "05-01", ALLE, 1990, OFFEN, LANDESGESETZE, "geprüft"),
    Regel("Tag der Befreiung", "05-08", _r("BE"), 2020, 2020,
          "Drittes Gesetz zur Änderung des Gesetzes über die Sonn- und Feiertage Berlin vom 30.01.2019, Art. 1 und 2",
          "geprüft"),
    Regel("Tag der Befreiung", "05-08", _r("BE"), 2025, 2025,
          "Gesetz des Abgeordnetenhauses Berlin von 2024", "Feiertag bestätigt, Fundstelle ungeprüft"),
    Regel("Christi Himmelfahrt", "O+39", ALLE, 1990, OFFEN, LANDESGESETZE, "geprüft"),
    Regel("Pfingstsonntag", "O+49", _r("BB"), 1990, OFFEN, "FTG Brandenburg § 2 Abs. 1 Nr. 7", "geprüft"),
    Regel("Pfingstmontag", "O+50", ALLE, 1990, OFFEN, LANDESGESETZE, "geprüft"),
    Regel("Fronleichnam", "O+60", _r("BW", BY, "HE", "NW", "RP", "SL", "SN_F", "TH_F"), 1990, OFFEN,
          "Landesgesetze BW, BY, HE, NW, RP, SL; SN: SächsSFG § 1 mit FronleichnamsVO vom 04.05.1993; "
          "TH: ThürFGtG § 2 Abs. 2 mit Rechtsverordnung",
          "geprüft, Thüringer Rechtsverordnung ungeprüft"),
    Regel("75. Jahrestag des Aufstandes vom 17. Juni 1953", "06-17", _r("BE"), 2028, 2028,
          "Gesetz über die Sonn- und Feiertage Berlin § 1 Abs. 1 Nr. 11", "geprüft"),
    Regel("Augsburger Friedensfest", "08-08", _r("BY_A"), 1990, OFFEN, "FTG Bayern Art. 1 Abs. 2", "geprüft"),
    Regel("Mariä Himmelfahrt", "08-15", _r("SL", "BY_MH", "BY_A"), 1990, OFFEN,
          "FTG Bayern Art. 1 Abs. 1 Nr. 2, SFG Saarland § 2 Abs. 1 Nr. 8",
          "geprüft, Zuordnung Stadt Augsburg ungeprüft"),
    Regel("Weltkindertag", "09-20", _r("TH", "TH_F"), 2019, OFFEN,
          "ThürFGtG § 2 Abs. 1, Änderung vom 26.03.2019 (GVBl. S. 22)", "geprüft"),
    Regel("Tag der Deutschen Einheit", "10-03", ALLE, 1990, OFFEN,
          LANDESGESETZE + ", Einigungsvertrag Art. 2 Abs. 2",
          "geprüft in den Landesgesetzen, Einigungsvertrag ungeprüft"),
    Regel("Reformationstag", "10-31", _r("BB", "MV", "SN", "SN_F", "ST", "TH", "TH_F"), 1990, OFFEN,
          "FTG Brandenburg § 2, FTG M-V § 2, SächsSFG § 1, FeiertG LSA § 2, ThürFGtG § 2",
          "geprüft, Beginn ungeprüft"),
    Regel("Reformationstag", "10-31", _r("HB", "HH", "NI", "SH"), 2018, OFFEN,
          "Gesetz Bremen § 2, Feiertagsgesetz Hamburg § 1, NFeiertagsG § 2, SFTG § 2 (jeweils Änderungen 2018)",
          "geprüft"),
    Regel("Reformationstag (500 Jahre Reformation)", "10-31",
          _r("BW", BY, "BE", "HB", "HE", "HH", "NI", "NW", "RP", "SL", "SH"), 2017, 2017,
          "je Land eigenes Gesetz oder eigene Verordnung", "ungeprüft"),
    Regel("Allerheiligen", "11-01", _r("BW", BY, "NW", "RP", "SL"), 1990, OFFEN, LANDESGESETZE, "geprüft"),
    Regel("Buß- und Bettag", "BUB", _r("SN", "SN_F"), 1990, OFFEN,
          "SächsSFG § 1 Abs. 1", "geprüft, Terminregel (Mittwoch vor dem 23. November) steht nicht im Gesetz"),
    Regel("Buß- und Bettag", "BUB", ALLE - {"SN", "SN_F"}, 1990, 1994, LANDESGESETZE, "ungeprüft"),
    Regel("1. Weihnachtstag", "12-25", ALLE, 1990, OFFEN, LANDESGESETZE, "geprüft"),
    Regel("2. Weihnachtstag", "12-26", ALLE, 1990, OFFEN, LANDESGESETZE, "geprüft"),
    # TARGET-Schließtage (nur für die Verschiebung fälliger Termine)
    Regel("Neujahr", "01-01", _r(TARGET), 2002, OFFEN, GESETZE[TARGET], "geprüft"),
    Regel("Karfreitag", "O-2", _r(TARGET), 2002, OFFEN, GESETZE[TARGET], "geprüft"),
    Regel("Ostermontag", "O+1", _r(TARGET), 2002, OFFEN, GESETZE[TARGET], "geprüft"),
    Regel("Tag der Arbeit", "05-01", _r(TARGET), 2002, OFFEN, GESETZE[TARGET], "geprüft"),
    Regel("1. Weihnachtstag", "12-25", _r(TARGET), 2002, OFFEN, GESETZE[TARGET], "geprüft"),
    Regel("2. Weihnachtstag", "12-26", _r(TARGET), 2002, OFFEN, GESETZE[TARGET], "geprüft"),
)


# ─── Berechnung ─────────────────────────────────────────────────────

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


def buss_und_bettag(jahr: int) -> date:
    """Mittwoch vor dem 23. November (also zwischen 16. und 22. November)."""
    d = date(jahr, 11, 22)
    while d.weekday() != 2:
        d -= timedelta(days=1)
    return d


def regel_datum(regel: str, jahr: int) -> date:
    if regel == "BUB":
        return buss_und_bettag(jahr)
    if regel.startswith("O"):
        return ostersonntag(jahr) + timedelta(days=int(regel[1:]))
    monat, tag = regel.split("-")
    return date(jahr, int(monat), int(tag))


def region_gueltig(region: str) -> bool:
    return region in REGION_NAMEN or region == TARGET


@lru_cache(maxsize=4096)
def _jahr(region: str, jahr: int) -> tuple[tuple[date, str], ...]:
    tage: dict[date, str] = {}
    for r in REGELN:
        if region in r.regionen and r.von <= jahr <= r.bis:
            d = regel_datum(r.regel, jahr)
            # Fallen zwei Feiertage auf einen Tag, werden beide genannt.
            tage[d] = f"{tage[d]} / {r.name}" if d in tage and r.name not in tage[d] else r.name
    return tuple(sorted(tage.items()))


def feiertage_jahr(region: str, jahr: int) -> dict[date, str]:
    """Alle Feiertage einer Region (oder TARGET) in einem Jahr."""
    return dict(_jahr(region, jahr))


class Kalender:
    """Feiertage einer Region, jahrweise bei Bedarf berechnet. Verhält sich
    für `in`, `get` und `[]` wie das frühere Dictionary aus der Tabelle
    feiertage, deckt aber jedes Jahr ab (auch nachgeholte Vorjahre und
    Prognosen beliebig weit in die Zukunft)."""

    def __init__(self, region: str):
        if not region_gueltig(region):
            raise ValueError(f"Unbekannte Region: {region}")
        self.region = region

    def _tage(self, jahr: int) -> dict[date, str]:
        return feiertage_jahr(self.region, jahr)

    def __contains__(self, datum) -> bool:
        return isinstance(datum, date) and datum in self._tage(datum.year)

    def get(self, datum, standard=None):
        if not isinstance(datum, date):
            return standard
        return self._tage(datum.year).get(datum, standard)

    def __getitem__(self, datum) -> str:
        name = self.get(datum)
        if name is None:
            raise KeyError(datum)
        return name


def bank_kalender() -> Kalender:
    """TARGET-Schließtage: Grundlage für die Verschiebung fälliger Termine.

    Übergang von 2.5 (fest NRW) ohne Doppelbuchungen: Die Generatoren
    betrachten nur Termine, deren ursprüngliches Datum erreicht ist, und
    setzen die Erzeugungsmarke erzeugt_bis vorher auf heute. Ein Termin, den
    2.5 nach NRW vorgezogen gebucht hat, liegt daher immer vor erzeugt_bis
    und wird nach dem Update übersprungen (Nachweis: tests/upgrade_test.py)."""
    return Kalender(TARGET)


def ist_feiertag_oder_wochenende(datum: date, feiertage) -> bool:
    return datum.weekday() >= 5 or datum in feiertage


def vorheriger_werktag(datum: date, feiertage) -> date:
    """
    Verschiebt ein Datum auf den vorherigen Werktag, falls es auf ein
    Wochenende oder einen Feiertag fällt (für Fälligkeitstermine von
    Buchungen/Darlehen). Seit v2.6 wird hier der TARGET-Kalender übergeben.
    """
    while ist_feiertag_oder_wochenende(datum, feiertage):
        datum -= timedelta(days=1)
    return datum


# ─── Gewählte Region ────────────────────────────────────────────────

def gewaehlte_region(conn) -> str:
    """Kürzel aus der Einstellung "bundesland", leer solange nicht gewählt."""
    row = conn.execute("SELECT value FROM einstellungen WHERE key = 'bundesland'").fetchone()
    wert = (row["value"] if row else "") or ""
    return wert if wert in REGION_NAMEN else ""


def feiertage_liste(region: str, von_jahr: int, bis_jahr: int) -> list[dict]:
    """Feiertage der Region und TARGET-Schließtage für die Oberfläche.
    `feiertag`: Name in der gewählten Region (oder None),
    `bankfeiertag`: Name als TARGET-Schließtag (oder None)."""
    tage: dict[date, dict] = {}
    for jahr in range(von_jahr, bis_jahr + 1):
        if region:
            for d, name in feiertage_jahr(region, jahr).items():
                tage.setdefault(d, {"datum": d.isoformat(), "feiertag": None, "bankfeiertag": None})["feiertag"] = name
        for d, name in feiertage_jahr(TARGET, jahr).items():
            tage.setdefault(d, {"datum": d.isoformat(), "feiertag": None, "bankfeiertag": None})["bankfeiertag"] = name
    return [{**tage[d], "text": hinweis_text(tage[d])} for d in sorted(tage)]


def datum_hinweis(datum: date, region: str) -> dict | None:
    """Hinweis für ein einzelnes Datum oder None, wenn nichts zu melden ist.
    Gemeldet werden Feiertage der Region (auch an Sonntagen) und
    TARGET-Schließtage."""
    feiertag = Kalender(region).get(datum) if region else None
    bankfeiertag = bank_kalender().get(datum)
    if not feiertag and not bankfeiertag:
        return None
    return {"datum": datum.isoformat(), "feiertag": feiertag, "bankfeiertag": bankfeiertag}


def _tt_mm_jjjj(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def hinweis_text(h: dict) -> str:
    """Kurzer Text zu einem Hinweis aus datum_hinweis oder termin_hinweise."""
    tag = h.get("feiertag_am") or h["datum"]
    namen = h["feiertag"] or h["bankfeiertag"]
    if h["feiertag"] and h["bankfeiertag"] and h["bankfeiertag"] != h["feiertag"]:
        namen = f"{h['feiertag']}, Bankfeiertag {h['bankfeiertag']}"
    elif not h["feiertag"]:
        namen = f"Bankfeiertag {namen}"
    text = f"{_tt_mm_jjjj(tag)} ist ein Feiertag ({namen})"
    if h.get("verschoben_von"):
        text += f", gebucht wird am {_tt_mm_jjjj(h['datum'])}"
    return text + "."


def termin_hinweise(termine, region: str) -> list[dict]:
    """Hinweise zu Serienterminen. `termine` sind Paare (ursprünglicher
    Termin, gebuchter Termin nach Verschiebung). Gemeldet wird ein Termin,
    wenn der ursprüngliche oder der gebuchte Tag ein Feiertag der Region
    oder ein TARGET-Schließtag ist. `verschoben_von` nennt den
    ursprünglichen Tag, wenn verschoben wurde."""
    ergebnis = []
    gesehen = set()
    for original, gebucht in termine:
        for tag in (original, gebucht):
            h = datum_hinweis(tag, region)
            if not h:
                continue
            schluessel = (original, gebucht)
            if schluessel in gesehen:
                break
            gesehen.add(schluessel)
            h = {**h, "datum": gebucht.isoformat(),
                 "verschoben_von": original.isoformat() if original != gebucht else None,
                 "feiertag_am": tag.isoformat()}
            h["text"] = hinweis_text(h)
            ergebnis.append(h)
            break
    ergebnis.sort(key=lambda h: h["datum"])
    return ergebnis

"""
Wiederkehrende Buchungen: Terminberechnung, Dynamik und Erzeugung
fälliger Buchungen.

Architektur (bewusst geändert): Es werden KEINE Plan-Buchungen mehr im
Voraus in der Datenbank angelegt. Sobald der Termin einer aktiven
Vorlage erreicht ist, entsteht direkt eine echte Ist-Buchung - Erzeugung
und "Umwandlung" fallen für diesen Fall zusammen. Für die Anzeige
anstehender Termine (Buchungsliste, Auswertungen, Budget-Prognose) gibt
es stattdessen eine rein rechnerische Projektion (anstehende_termine),
die nichts in der Datenbank ablegt.

Dynamik (vertraglich bekannte Steigerung, z. B. Prämie +3 % alle 2 Jahre):
  - wirkt ECHT auf den erzeugten Buchungsbetrag (nicht nur in der Anzeige)
  - kumuliert: jede Steigerung setzt auf dem letzten Betrag auf
  - jeweils zum Jahrestag der Vorlage (nicht zum 1. Januar)
  - dynamik_startjahr = Jahr der ERSTEN Erhöhung; bleibt es leer, beginnt
    die Erhöhung nach dem ersten vollen Zyklus
  - schließt inflationsflag gegenseitig aus (sonst würde die Auswertung
    auf den bereits erhöhten Betrag noch den Inflationsfaktor rechnen)
"""
from datetime import date, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta

from .feiertage import vorheriger_werktag
from . import zeit

# Anzeige-Horizont für anstehende (virtuelle) Termine in der
# Buchungsliste - hat mit der Datenbank nichts mehr zu tun, rein
# kosmetisch für "wie weit in die Zukunft blättern wir".
ANZEIGE_HORIZONT_MONATE = 12

# Termine kurz nach dem Ende eines Vorschau-Zeitraums können durch die
# Werktagsverschiebung noch hineinfallen (z. B. Sonntag, 1. -> Freitag
# davor). Vorschau-Funktionen berechnen Termine deshalb bis Ende + Puffer
# und schneiden erst nach der Verschiebung ab (seit v2.0, Befund I).
VERSCHIEBUNG_PUFFER = timedelta(days=10)

_SCHRITT_MONATE = {
    "monatlich": 1,
    "quartalsweise": 3,
    "halbjaehrlich": 6,
    "jaehrlich": 12,
}


def _tag_im_monat(jahr: int, monat: int, tag: int) -> date:
    """'tag'-ter Tag eines Monats; bei Überlauf (31. im 30-Tage-Monat) der letzte Tag."""
    try:
        return date(jahr, monat, tag)
    except ValueError:
        return date(jahr, monat, 1) + relativedelta(months=1) - relativedelta(days=1)


def alle_termine(vorlage_row, bis: date) -> list[date]:
    """Alle (unverschobenen) Termine einer Vorlage vom Start bis 'bis' (inklusive)."""
    schritt = _SCHRITT_MONATE[vorlage_row["intervall"]]
    start = date.fromisoformat(vorlage_row["startdatum"])
    tag = vorlage_row["tag_des_monats"]
    monat_feld = vorlage_row["monat"] or start.month
    ende = date.fromisoformat(vorlage_row["enddatum"]) if vorlage_row["enddatum"] else None

    if vorlage_row["intervall"] == "monatlich":
        cursor = date(start.year, start.month, 1)
    else:
        cursor = date(start.year, monat_feld, 1)
        if cursor < date(start.year, start.month, 1):
            cursor += relativedelta(years=1)

    termine = []
    while cursor <= bis:
        t = _tag_im_monat(cursor.year, cursor.month, tag)
        if t >= start and (ende is None or t <= ende) and t <= bis:
            termine.append(t)
        cursor += relativedelta(months=schritt)
    return termine


def abgeleitete_monate(vorlage_row) -> list[int]:
    """Die Monate, in denen eine Vorlage fällig wird - aus dem Intervall
    abgeleitet (für die Anzeige in der Übersichtstabelle)."""
    if vorlage_row["intervall"] == "monatlich":
        return list(range(1, 13))
    schritt = _SCHRITT_MONATE[vorlage_row["intervall"]]
    start = date.fromisoformat(vorlage_row["startdatum"])
    basis = vorlage_row["monat"] or start.month
    return sorted({((basis - 1 + i * schritt) % 12) + 1 for i in range(12 // schritt)})


def anzahl_erhoehungen(vorlage_row, termin: date) -> int:
    """Wie viele Dynamik-Stufen zum gegebenen Termin bereits gegriffen haben."""
    if not vorlage_row["dynamik_aktiv"]:
        return 0
    rhythmus = vorlage_row["dynamik_rhythmus_jahre"] or 0
    if rhythmus <= 0:
        return 0

    start = date.fromisoformat(vorlage_row["startdatum"])
    erstes_jahr = vorlage_row["dynamik_startjahr"] or (start.year + rhythmus)

    anzahl = 0
    jahr = erstes_jahr
    while jahr <= termin.year:
        jahrestag = _tag_im_monat(jahr, start.month, start.day)
        if jahrestag <= termin:
            anzahl += 1
        jahr += rhythmus
    return anzahl


def betrag_mit_dynamik(vorlage_row, termin: date) -> float:
    """Buchungsbetrag zum Termin, inklusive kumulierter Dynamik, auf Cent gerundet."""
    betrag = vorlage_row["betrag"]
    if not vorlage_row["dynamik_aktiv"]:
        return round(betrag, 2)
    prozent = vorlage_row["dynamik_prozent"] or 0.0
    stufen = anzahl_erhoehungen(vorlage_row, termin)
    return round(betrag * (1 + prozent / 100) ** stufen, 2)


def globaler_inflationsfaktor(conn) -> float:
    """Der administrierbare Inflationsfaktor (% p.a.) aus den Einstellungen -
    wird von wiederkehrenden Buchungen, Altersvorsorge-Auszahlungen und
    Budgets gemeinsam genutzt (siehe betrag_mit_inflation)."""
    row = conn.execute("SELECT value FROM einstellungen WHERE key = 'inflationsfaktor'").fetchone()
    try:
        return float(row["value"]) if row else 2.0
    except (TypeError, ValueError):
        return 2.0


def betrag_mit_inflation(betrag: float, termin: date, inflationsfaktor_prozent: float,
                          heute: Optional[date] = None) -> float:
    """
    Zinseszins-Hochrechnung eines Betrags von 'heute' (Standard: der
    tatsächliche heutige Tag) bis 'termin', mit dem gegebenen Faktor (%
    p.a.) - reine Vorschau-/Projektionsrechnung (siehe inflationsflag:
    wirkt NIE auf real erzeugte Buchungen, nur auf die rein rechnerische
    Projektion in anstehende_termine/Auswertungen). Das Vorzeichen von
    'betrag' bleibt erhalten, da mit einem positiven Faktor multipliziert
    wird. Liegt 'termin' vor 'heute', wird nicht abgezinst (jahre >= 0).
    """
    heute = heute or zeit.heute()
    jahre = max(0.0, (termin - heute).days / 365.25)
    return round(betrag * (1 + inflationsfaktor_prozent / 100) ** jahre, 2)


def ist_umbuchung(vorlage_row) -> bool:
    """Umbuchungs-Vorlage (seit v1.10): Übertragung vom Konto der Vorlage auf
    ein Zielkonto. Wirkt wie eine manuelle Übertragung: Abgang im Quell-,
    Zugang im Zielkonto, kein Cashflow-/Kategorie-/Budget-Effekt."""
    return "zielkonto_id" in vorlage_row.keys() and bool(vorlage_row["zielkonto_id"])


def vorzeichen_anwenden(conn, kategorie_id: int, betrag: float) -> float:
    """Vorzeichen aus dem Kategorie-Typ ableiten (siehe buchungen.py)."""
    row = conn.execute("SELECT typ FROM kategorien WHERE id = ?", (kategorie_id,)).fetchone()
    if row is None or row["typ"] is None:
        return betrag
    return -abs(betrag) if row["typ"] == "ausgabe" else abs(betrag)


# ─── Erzeugungsmarke (seit v1.8) ─────────────────────────────────────
# Jede Quelle automatischer Buchungen (Vorlage, Darlehen, Altersvorsorge)
# merkt sich in "erzeugt_bis", bis zu welchem Datum ihre Ist-Buchungen
# bereits erzeugt wurden. Termine bis dahin werden nie erneut gebucht -
# auch dann nicht, wenn die Buchung inzwischen angepasst (anderes Datum)
# oder verworfen (gelöscht) wurde. Die Existenzprüfung bleibt als zweite
# Sicherung bestehen.
#
# Rückwirkende Änderungen (vorverlegter Start, frühere Auszahlung, ...)
# öffnen keine Marke, sondern buchen gezielt nur das NEU entstandene
# Zeitfenster nach (Parameter `fenster`). Dort gab es vorher keine
# Buchungen, also kann dort auch nichts angepasst/verworfen worden sein -
# ein Zurücksetzen der Marke würde dagegen angepasste Buchungen aus dem
# wieder geöffneten Zeitraum als Duplikat zurückholen.

def bereits_erzeugt(quelle, termin: date) -> bool:
    grenze = quelle["erzeugt_bis"] if "erzeugt_bis" in quelle.keys() else None
    return bool(grenze) and termin.isoformat() <= grenze


def erzeugt_bis_setzen(conn, tabelle: str, quelle_id: int, heute: date) -> None:
    conn.execute(
        f"UPDATE {tabelle} SET erzeugt_bis = ? WHERE id = ? AND (erzeugt_bis IS NULL OR erzeugt_bis < ?)",
        (heute.isoformat(), quelle_id, heute.isoformat()))


def im_fenster(fenster, termin: date) -> bool:
    """Nachhol-Fenster [von, bis) bei rückwirkenden Änderungen, bezogen auf
    den ursprünglichen (unverschobenen) Termin."""
    return fenster is None or fenster[0] <= termin < fenster[1]


def erzeuge_faellige_ist_buchungen(conn, feiertage: dict, heute: Optional[date] = None,
                                   nur_id: Optional[int] = None, fenster=None) -> int:
    """
    Legt für alle aktiven Vorlagen JEDEN fälligen (Termin <= heute, noch
    nicht gebuchten) Termin direkt als Ist-Buchung an - keine
    Plan-Zwischenstufe mehr. Termine auf Wochenende/Feiertag werden auf
    den vorherigen Werktag verschoben, Beträge um die Dynamik erhöht und
    das Vorzeichen aus dem Kategorie-Typ abgeleitet.
    """
    heute = heute or zeit.heute()
    anzahl = 0

    sql = "SELECT * FROM wiederkehrende_buchungen WHERE aktiv = 1" + (" AND id = ?" if nur_id else "")
    for vorlage in conn.execute(sql, (nur_id,) if nur_id else ()).fetchall():
        if fenster is None:
            erzeugt_bis_setzen(conn, "wiederkehrende_buchungen", vorlage["id"], heute)
        for termin in alle_termine(vorlage, heute):
            verschoben = vorheriger_werktag(termin, feiertage)
            if verschoben > heute or not im_fenster(fenster, termin):
                continue
            if fenster is None and bereits_erzeugt(vorlage, verschoben):
                continue
            if conn.execute(
                "SELECT 1 FROM buchungen WHERE wiederkehrend_id = ? AND datum = ?",
                (vorlage["id"], verschoben.isoformat()),
            ).fetchone():
                continue
            if ist_umbuchung(vorlage):
                # Seit v1.10: echte Übertragung über buchung_anlegen (feste
                # Kategorie "Umbuchung", Betrag ohne Vorzeichen).
                from . import buchungen as buchungen_modul
                buchung_id = buchungen_modul.buchung_anlegen(
                    conn, konto_id=vorlage["konto_id"], datum=verschoben,
                    betrag=abs(vorlage["betrag"]), kategorie_id=vorlage["kategorie_id"],
                    typ="Uebertragung", beschreibung=vorlage["beschreibung"],
                    zielkonto_id=vorlage["zielkonto_id"], wiederkehrend_id=vorlage["id"],
                    # Sparziel nur, wenn die Regel (seit v2.0) erfüllt ist - der
                    # Generator darf beim Start nie an einer Prüfung scheitern.
                    sparziel_id=vorlage["sparziel_id"] if not buchungen_modul.sparziel_pruefen(
                        conn, "Uebertragung", vorlage["konto_id"], vorlage["zielkonto_id"],
                        vorlage["sparziel_id"]) else None)
                conn.execute(
                    """INSERT INTO plan_buchung_protokoll (buchung_id, datum_umwandlung, status)
                       VALUES (?, ?, 'umgewandelt')""", (buchung_id, heute.isoformat()))
                anzahl += 1
                continue
            betrag = vorzeichen_anwenden(
                conn, vorlage["kategorie_id"], betrag_mit_dynamik(vorlage, termin)
            )
            conn.execute(
                """INSERT INTO buchungen
                   (konto_id, ziel_darlehen_id, datum, betrag, kategorie_id, typ,
                    beschreibung, wiederkehrend_id, inflationsflag)
                   VALUES (?, ?, ?, ?, ?, 'Ist', ?, ?, ?)""",
                (vorlage["konto_id"], vorlage["darlehen_id"], verschoben.isoformat(),
                 betrag, vorlage["kategorie_id"], vorlage["beschreibung"],
                 vorlage["id"], vorlage["inflationsflag"]),
            )
            conn.execute(
                """INSERT INTO plan_buchung_protokoll (buchung_id, datum_umwandlung, status)
                   VALUES (?, ?, 'umgewandelt')""",
                (conn.execute("SELECT last_insert_rowid()").fetchone()[0], heute.isoformat()),
            )
            anzahl += 1
    conn.commit()
    return anzahl


def anstehende_termine(conn, feiertage: dict, ab: date, bis: date, vorlage_id: Optional[int] = None,
                       inkl_umbuchungen: bool = True, inflation: bool = False) -> list[dict]:
    """
    Rein rechnerische Vorschau anstehender Termine (ab, bis] - erzeugt
    NICHTS in der Datenbank. Für die Buchungsliste (Anzeige-Horizont) und
    als Baustein für Auswertungen/Budget-Prognose.

    Umbuchungs-Vorlagen (seit v1.10) liefern Einträge mit typ 'Uebertragung',
    zielkonto_id und positivem Betrag - wie echte Übertragungen. Aufrufer,
    die Übertragungen nicht zählen (Kategorien-Diagramm, Budgets), rufen mit
    inkl_umbuchungen=False auf.
    """
    sql = "SELECT * FROM wiederkehrende_buchungen WHERE aktiv = 1"
    params = ()
    if vorlage_id is not None:
        sql += " AND id = ?"
        params = (vorlage_id,)

    inflationsfaktor_prozent = globaler_inflationsfaktor(conn)
    ergebnis = []
    for vorlage in conn.execute(sql, params).fetchall():
        umbuchung = ist_umbuchung(vorlage)
        if umbuchung and not inkl_umbuchungen:
            continue
        for termin in alle_termine(vorlage, bis + VERSCHIEBUNG_PUFFER):
            verschoben = vorheriger_werktag(termin, feiertage)
            if verschoben <= ab or verschoben > bis:
                continue
            if umbuchung:
                ergebnis.append({
                    "datum": verschoben.isoformat(), "termin": termin.isoformat(),
                    "betrag": round(abs(vorlage["betrag"]), 2),
                    "konto_id": vorlage["konto_id"], "zielkonto_id": vorlage["zielkonto_id"],
                    "kategorie_id": vorlage["kategorie_id"], "sparziel_id": vorlage["sparziel_id"],
                    "beschreibung": vorlage["beschreibung"], "wiederkehrend_id": vorlage["id"],
                    "typ": "Uebertragung", "virtuell": True,
                })
                continue
            betrag = vorzeichen_anwenden(
                conn, vorlage["kategorie_id"], betrag_mit_dynamik(vorlage, termin)
            )
            if inflation and vorlage["inflationsflag"]:
                # Seit v2.0 nur mit eingeschaltetem Schalter "Inflation
                # einrechnen" der jeweiligen Seite (Standard aus).
                # Rein rechnerische Projektion - wirkt sich nicht auf die
                # real erzeugte Buchung aus (siehe erzeuge_faellige_ist_
                # buchungen, die inflationsflag nur unverändert mitführt).
                betrag = betrag_mit_inflation(betrag, verschoben, inflationsfaktor_prozent)
            ergebnis.append({
                "datum": verschoben.isoformat(), "termin": termin.isoformat(), "betrag": betrag,
                "konto_id": vorlage["konto_id"], "kategorie_id": vorlage["kategorie_id"],
                "beschreibung": vorlage["beschreibung"], "wiederkehrend_id": vorlage["id"],
                "typ": "Wiederkehrend", "virtuell": True,
            })
    ergebnis.sort(key=lambda b: b["datum"])
    return ergebnis

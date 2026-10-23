"""
Automatische Erzeugung fälliger Darlehensraten (Zins + Tilgung) als
Buchungen - nach demselben Prinzip wie wiederkehrende Buchungen (siehe
dortige Modul-Doku): keine Plan-Vorproduktion mehr, sondern direkte
Ist-Buchung bei Fälligkeit sowie eine separate, rein rechnerische
Projektion für die Anzeige.

Technische Umsetzung: Da sich der Zins-/Tilgungsanteil der - in der
Höhe konstanten - Rate von Monat zu Monat verschiebt, kann dafür keine
einzelne "wiederkehrende Buchung" mit statischem Betrag verwendet
werden. Stattdessen werden die monatsgenauen Beträge direkt aus dem
Tilgungsplan (darlehen.py) übernommen. Pro Monat entstehen zwei
Buchungen: Zinsanteil (Kategorie "Darlehen -> Zinsen") und
Tilgungsanteil (Kategorie "Darlehen -> Tilgung").
"""
from datetime import date
from typing import Optional

from .darlehen import aus_db_zeile, berechne_tilgungsplan
from .db import kategorie_id as db_kategorie_id
from .feiertage import vorheriger_werktag
from .wiederkehrend import bereits_erzeugt, erzeugt_bis_setzen, im_fenster
from . import zeit
from .wiederkehrend import VERSCHIEBUNG_PUFFER


def _darlehen_mit_zahlungskonto(conn):
    return conn.execute("SELECT * FROM darlehen WHERE zahlungskonto_id IS NOT NULL").fetchall()


def sondertilgungen_laden(conn, darlehen_id: int) -> dict:
    """Gebuchte Sondertilgungen je Monat (Monatserster -> Summe) für den
    Tilgungsplan. Seit v1.9.1 - vorher wurden Sondertilgungen zwar gebucht,
    aber nirgends an berechne_tilgungsplan übergeben, sodass Restschuld,
    künftige Zinsen und Raten sie ignorierten."""
    kat = db_kategorie_id(conn, "darlehen_sondertilgung")
    ergebnis: dict = {}
    if kat is None:
        return ergebnis
    for r in conn.execute(
            "SELECT datum, betrag FROM buchungen WHERE ziel_darlehen_id = ? AND kategorie_id = ? AND typ = 'Ist'",
            (darlehen_id, kat)).fetchall():
        d = date.fromisoformat(r["datum"])
        monat = date(d.year, d.month, 1)
        ergebnis[monat] = ergebnis.get(monat, 0.0) + abs(r["betrag"])
    return ergebnis


def tilgungsplan_laden(conn, row) -> list:
    """Tilgungsplan eines Darlehens inkl. Auszahlungen und gebuchter
    Sondertilgungen - zentrale Stelle für alle Verwender."""
    auszahlungen = conn.execute(
        "SELECT datum, betrag FROM darlehen_auszahlungen WHERE darlehen_id = ?", (row["id"],)
    ).fetchall()
    return berechne_tilgungsplan(aus_db_zeile(row, auszahlungen), sondertilgungen_laden(conn, row["id"]))


def erzeuge_faellige_ist_buchungen(conn, feiertage: dict, heute: Optional[date] = None,
                                   nur_id: Optional[int] = None, fenster=None) -> int:
    """Legt für jedes Darlehen mit Zahlungskonto jede fällige (Termin <=
    heute, noch nicht gebuchte) Zins-/Tilgungszahlung als Ist-Buchung an."""
    heute = heute or zeit.heute()
    anzahl = 0
    kat_zinsen = db_kategorie_id(conn, "darlehen_zinsen")
    kat_tilgung = db_kategorie_id(conn, "darlehen_tilgung")

    for row in _darlehen_mit_zahlungskonto(conn):
        if nur_id is not None and row["id"] != nur_id:
            continue
        if fenster is None:
            erzeugt_bis_setzen(conn, "darlehen", row["id"], heute)
        auszahlungen = conn.execute(
            "SELECT datum, betrag FROM darlehen_auszahlungen WHERE darlehen_id = ?", (row["id"],)
        ).fetchall()
        darlehen = aus_db_zeile(row, auszahlungen)

        for zeile in berechne_tilgungsplan(darlehen, sondertilgungen_laden(conn, row["id"])):
            if zeile.datum > heute:
                break
            termin = vorheriger_werktag(zeile.datum, feiertage)
            if termin > heute or not im_fenster(fenster, zeile.datum):
                continue
            if fenster is None and bereits_erzeugt(row, termin):
                continue

            for kategorie_id, betrag, bezeichnung in (
                (kat_zinsen, -zeile.zinsen, "Zinsen"), (kat_tilgung, -zeile.tilgung, "Tilgung"),
            ):
                if kategorie_id is None or betrag == 0:
                    continue
                if conn.execute(
                    "SELECT 1 FROM buchungen WHERE ziel_darlehen_id = ? AND datum = ? AND kategorie_id = ?",
                    (row["id"], termin.isoformat(), kategorie_id),
                ).fetchone():
                    continue
                conn.execute(
                    """INSERT INTO buchungen
                       (konto_id, ziel_darlehen_id, datum, betrag, kategorie_id, typ, beschreibung)
                       VALUES (?, ?, ?, ?, ?, 'Ist', ?)""",
                    (row["zahlungskonto_id"], row["id"], termin.isoformat(), betrag,
                     kategorie_id, f"{darlehen.bezeichnung} - {bezeichnung}"),
                )
                conn.execute(
                    """INSERT INTO plan_buchung_protokoll (buchung_id, datum_umwandlung, status)
                       VALUES (?, ?, 'umgewandelt')""",
                    (conn.execute("SELECT last_insert_rowid()").fetchone()[0], heute.isoformat()),
                )
                anzahl += 1
    conn.commit()
    return anzahl


def anstehende_raten(conn, feiertage: dict, ab: date, bis: date, darlehen_id: Optional[int] = None) -> list[dict]:
    """Rein rechnerische Vorschau anstehender Zins-/Tilgungszahlungen (ab, bis] -
    erzeugt nichts in der Datenbank."""
    kat_zinsen = db_kategorie_id(conn, "darlehen_zinsen")
    kat_tilgung = db_kategorie_id(conn, "darlehen_tilgung")

    sql = "SELECT * FROM darlehen WHERE zahlungskonto_id IS NOT NULL"
    params = ()
    if darlehen_id is not None:
        sql += " AND id = ?"
        params = (darlehen_id,)

    ergebnis = []
    for row in conn.execute(sql, params).fetchall():
        auszahlungen = conn.execute(
            "SELECT datum, betrag FROM darlehen_auszahlungen WHERE darlehen_id = ?", (row["id"],)
        ).fetchall()
        darlehen = aus_db_zeile(row, auszahlungen)
        for zeile in berechne_tilgungsplan(darlehen, sondertilgungen_laden(conn, row["id"])):
            if zeile.datum > bis + VERSCHIEBUNG_PUFFER:   # Befund I (v2.0)
                break
            termin = vorheriger_werktag(zeile.datum, feiertage)
            if termin <= ab or termin > bis:
                continue
            for kategorie_id, betrag, bezeichnung in (
                (kat_zinsen, -zeile.zinsen, "Zinsen"), (kat_tilgung, -zeile.tilgung, "Tilgung"),
            ):
                if kategorie_id is None or betrag == 0:
                    continue
                ergebnis.append({
                    "datum": termin.isoformat(), "betrag": betrag, "konto_id": row["zahlungskonto_id"],
                    "kategorie_id": kategorie_id, "beschreibung": f"{darlehen.bezeichnung} - {bezeichnung}",
                    "ziel_darlehen_id": row["id"], "typ": "Wiederkehrend", "virtuell": True,
                })
    ergebnis.sort(key=lambda b: b["datum"])
    return ergebnis

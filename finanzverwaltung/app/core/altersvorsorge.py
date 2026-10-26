"""
Altersvorsorge: eigener Bereich mit zwei gegenläufigen Buchungsströmen -
Beitragsphase (Ausgabe, bis Rentenbeginn) und Auszahlungsphase (Einnahme,
ab Rentenbeginn). Personenzuordnung ergibt sich aus zahlungskonto_id.

Fachliche Festlegungen aus dem Sparring:
  - Rente und Einmalzahlung werden parallel vorgehalten; welche Variante
    aktuell für Planung/Buchung zählt, entscheidet auszahlungsart.
  - Reale Buchungen (Ist bei Fälligkeit) nutzen IMMER den garantierten
    Betrag - das ist die vertraglich zugesicherte, verlässliche Zahl.
    "Voraussichtlich" ist eine reine Anzeige-Variante (Korridor in den
    Auswertungen), erzeugt NIE eine eigene Buchung.
  - Die Rentenzahlung wird als gleitender Horizont behandelt: ohne
    bekanntes Ende (Tod) wird nur 30 Jahre (bis v1.8: 20) über den jeweils aktuellen
    Betrachtungszeitpunkt hinaus projiziert/gebucht. Sobald ende_datum
    gesetzt ist (z. B. nach Tod), gilt dieses echte Datum statt des
    gleitenden Horizonts.
  - "Auszahlung bei Tod" und "Rückkaufswert" sind rein informativ, fließen
    in keine Berechnung ein.
  - Beitragsdynamik funktioniert exakt wie bei wiederkehrenden Buchungen
    (siehe wiederkehrend.py) - Berechnung wird von dort wiederverwendet.
  - Inflationsfaktor (seit v1.6.3): auszahlung_inflationsflag rechnet die
    projizierten Auszahlungsbeträge (nur in anstehende_termine, also in
    Buchungsliste/Budget-Prognose/Auswertungen) mit Zinseszins ab heute
    hoch - analog zum bisher toten inflationsflag bei wiederkehrenden
    Buchungen, siehe wiederkehrend.betrag_mit_inflation(). Reale Buchungen
    bleiben davon unberührt (immer der garantierte Betrag, unverändert).
"""
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

from . import wiederkehrend as wiederkehrend_modul
from .feiertage import vorheriger_werktag
from . import zeit

ROLLIERENDER_HORIZONT_JAHRE = 30  # seit v1.9 (vorher 20)


def _beitrag_vorlage(row) -> dict:
    """Adapter: baut aus einer altersvorsorge-Zeile ein 'vorlage'-artiges
    dict, um die Terminberechnung aus wiederkehrend.py wiederzuverwenden."""
    beitrag_ende = date.fromisoformat(row["rentenbeginn"]) - relativedelta(days=1)
    return {
        "intervall": row["beitrag_intervall"],
        "startdatum": row["beitrag_startdatum"],
        "tag_des_monats": row["beitrag_tag_des_monats"],
        "monat": row["beitrag_monat"],
        "enddatum": beitrag_ende.isoformat(),
        "dynamik_aktiv": row["beitrag_dynamik_aktiv"],
        "dynamik_rhythmus_jahre": row["beitrag_dynamik_rhythmus_jahre"],
        "dynamik_prozent": row["beitrag_dynamik_prozent"],
        "dynamik_startjahr": row["beitrag_dynamik_startjahr"],
        "betrag": row["beitrag_betrag"],
    }


def _renten_horizont(row, heute: date) -> Optional[date]:
    """Bis wohin die Rente aktuell projiziert/gebucht wird - echtes
    Ende-Datum, falls gesetzt, sonst der gleitende 30-Jahres-Horizont."""
    if row["ende_datum"]:
        return date.fromisoformat(row["ende_datum"])
    return heute + relativedelta(years=ROLLIERENDER_HORIZONT_JAHRE)


def _renten_termine(row, bis: date) -> list[date]:
    """Monatliche Rententermine ab Rentenbeginn bis 'bis' (inklusive)."""
    rentenbeginn = date.fromisoformat(row["rentenbeginn"])
    tag = min(rentenbeginn.day, 28)
    termine = []
    cursor = date(rentenbeginn.year, rentenbeginn.month, 1)
    while cursor <= bis:
        t = cursor.replace(day=tag)
        if t >= rentenbeginn and t <= bis:
            termine.append(t)
        cursor += relativedelta(months=1)
    return termine


def erzeuge_faellige_ist_buchungen(conn, feiertage: dict, heute: Optional[date] = None,
                                   nur_id: Optional[int] = None, fenster=None) -> int:
    """
    Erzeugt für jede aktive Altersvorsorge fällige (Termin <= heute)
    Beitrags- bzw. Rentenbuchungen direkt als Ist-Buchung - dasselbe
    Prinzip wie bei wiederkehrenden Buchungen/Darlehensraten: keine
    Plan-Vorproduktion, direkte Buchung bei Fälligkeit, plus
    Protokolleintrag für den Bestätigungs-Workflow.
    """
    heute = heute or zeit.heute()
    anzahl = 0

    sql = "SELECT * FROM altersvorsorge WHERE aktiv = 1" + (" AND id = ?" if nur_id else "")

    def ueberspringen(termin: date, verschoben: date, kategorie_id=None) -> bool:
        if verschoben > heute or not wiederkehrend_modul.im_fenster(fenster, termin):
            return True
        if fenster is not None and conn.execute(
                """SELECT 1 FROM plan_buchung_protokoll p JOIN buchungen b ON b.id = p.buchung_id
                   WHERE p.status = 'angepasst' AND b.ziel_altersvorsorge_id = ? AND b.kategorie_id = ?
                     AND p.hinweis LIKE ?""",
                (row["id"], kategorie_id, f"%(ursprünglich {verschoben.isoformat()})%")).fetchone():
            # Nachhol-Fenster (z. B. Rentenbeginn zurückverlegt, seit v2.0): der
            # Termin ist schon durch eine angepasste Buchung vertreten.
            return True
        return fenster is None and wiederkehrend_modul.bereits_erzeugt(row, verschoben)

    for row in conn.execute(sql, (nur_id,) if nur_id else ()).fetchall():
        if fenster is None:
            wiederkehrend_modul.erzeugt_bis_setzen(conn, "altersvorsorge", row["id"], heute)
        # Beitragsphase (Ausgabe, bis Rentenbeginn) - nur bei aktivierter
        # Einzahlung (hat_einzahlung); arbeitgeber-/gehaltsfinanzierte
        # Modelle ohne eigene Einzahlung überspringen diese Phase
        # vollständig (v1.5) - es entstehen dann ausschließlich
        # Plan-/Ist-Buchungen für die Auszahlung.
        if row["hat_einzahlung"]:
            beitrag_vorlage = _beitrag_vorlage(row)
            for termin in wiederkehrend_modul.alle_termine(beitrag_vorlage, heute):
                verschoben = vorheriger_werktag(termin, feiertage)
                if ueberspringen(termin, verschoben, row["beitrag_kategorie_id"]):
                    continue
                if conn.execute(
                    "SELECT 1 FROM buchungen WHERE ziel_altersvorsorge_id = ? AND datum = ? AND kategorie_id = ?",
                    (row["id"], verschoben.isoformat(), row["beitrag_kategorie_id"]),
                ).fetchone():
                    continue
                betrag = -abs(wiederkehrend_modul.betrag_mit_dynamik(beitrag_vorlage, termin))
                conn.execute(
                    """INSERT INTO buchungen
                       (konto_id, ziel_altersvorsorge_id, datum, betrag, kategorie_id, typ, beschreibung)
                       VALUES (?, ?, ?, ?, ?, 'Ist', ?)""",
                    (row["zahlungskonto_id"], row["id"], verschoben.isoformat(), betrag,
                     row["beitrag_kategorie_id"], f"{row['bezeichnung']} - Beitrag"),
                )
                conn.execute(
                    """INSERT INTO plan_buchung_protokoll (buchung_id, datum_umwandlung, status)
                       VALUES (?, ?, 'umgewandelt')""",
                    (conn.execute("SELECT last_insert_rowid()").fetchone()[0], heute.isoformat()),
                )
                anzahl += 1

        # Auszahlungsphase (Einnahme, ab Rentenbeginn) - IMMER mit dem
        # garantierten Betrag; "voraussichtlich" ist reine Anzeige.
        if date.fromisoformat(row["rentenbeginn"]) > heute:
            continue
        if row["auszahlungsart"] == "rente":
            horizont = min(heute, _renten_horizont(row, heute))
            betrag_garantiert = row["rente_garantiert_betrag"]
            if betrag_garantiert is None:
                continue
            for termin in _renten_termine(row, horizont):
                verschoben = vorheriger_werktag(termin, feiertage)
                if ueberspringen(termin, verschoben, row["auszahlung_kategorie_id"]):
                    continue
                if conn.execute(
                    "SELECT 1 FROM buchungen WHERE ziel_altersvorsorge_id = ? AND datum = ? AND kategorie_id = ?",
                    (row["id"], verschoben.isoformat(), row["auszahlung_kategorie_id"]),
                ).fetchone():
                    continue
                conn.execute(
                    """INSERT INTO buchungen
                       (konto_id, ziel_altersvorsorge_id, datum, betrag, kategorie_id, typ, beschreibung)
                       VALUES (?, ?, ?, ?, ?, 'Ist', ?)""",
                    (row["zahlungskonto_id"], row["id"], verschoben.isoformat(), abs(betrag_garantiert),
                     row["auszahlung_kategorie_id"], f"{row['bezeichnung']} - Rente"),
                )
                conn.execute(
                    """INSERT INTO plan_buchung_protokoll (buchung_id, datum_umwandlung, status)
                       VALUES (?, ?, 'umgewandelt')""",
                    (conn.execute("SELECT last_insert_rowid()").fetchone()[0], heute.isoformat()),
                )
                anzahl += 1
        else:  # einmalzahlung
            termin = date.fromisoformat(row["rentenbeginn"])
            verschoben = vorheriger_werktag(termin, feiertage)
            betrag_garantiert = row["einmalzahlung_garantiert_betrag"]
            if betrag_garantiert is None or ueberspringen(termin, verschoben, row["auszahlung_kategorie_id"]):
                continue
            if conn.execute(
                "SELECT 1 FROM buchungen WHERE ziel_altersvorsorge_id = ? AND datum = ? AND kategorie_id = ?",
                (row["id"], verschoben.isoformat(), row["auszahlung_kategorie_id"]),
            ).fetchone():
                continue
            conn.execute(
                """INSERT INTO buchungen
                   (konto_id, ziel_altersvorsorge_id, datum, betrag, kategorie_id, typ, beschreibung)
                   VALUES (?, ?, ?, ?, ?, 'Ist', ?)""",
                (row["zahlungskonto_id"], row["id"], verschoben.isoformat(), abs(betrag_garantiert),
                 row["auszahlung_kategorie_id"], f"{row['bezeichnung']} - Einmalzahlung"),
            )
            conn.execute(
                """INSERT INTO plan_buchung_protokoll (buchung_id, datum_umwandlung, status)
                   VALUES (?, ?, 'umgewandelt')""",
                (conn.execute("SELECT last_insert_rowid()").fetchone()[0], heute.isoformat()),
            )
            anzahl += 1

    conn.commit()
    return anzahl


def anstehende_termine(conn, feiertage: dict, ab: date, bis: date, id_filter: Optional[int] = None,
                       inflation: bool = False) -> list[dict]:
    """Rein rechnerische Vorschau (Beitrag + garantierte Rente/Einmalzahlung) -
    erzeugt nichts in der Datenbank. Für Buchungsliste/Budget-Prognose."""
    sql = "SELECT * FROM altersvorsorge WHERE aktiv = 1"
    params = ()
    if id_filter is not None:
        sql += " AND id = ?"
        params = (id_filter,)

    inflationsfaktor_prozent = wiederkehrend_modul.globaler_inflationsfaktor(conn)
    ergebnis = []
    for row in conn.execute(sql, params).fetchall():
        # Beitragsphase nur bei aktivierter Einzahlung - siehe
        # erzeuge_faellige_ist_buchungen.
        if row["hat_einzahlung"]:
            beitrag_vorlage = _beitrag_vorlage(row)
            for termin in wiederkehrend_modul.alle_termine(beitrag_vorlage, bis + wiederkehrend_modul.VERSCHIEBUNG_PUFFER):
                verschoben = vorheriger_werktag(termin, feiertage)
                if verschoben <= ab or verschoben > bis:
                    continue
                betrag = -abs(wiederkehrend_modul.betrag_mit_dynamik(beitrag_vorlage, termin))
                ergebnis.append({
                    "datum": verschoben.isoformat(), "termin": termin.isoformat(),
                    "betrag": betrag, "konto_id": row["zahlungskonto_id"],
                    "kategorie_id": row["beitrag_kategorie_id"], "beschreibung": f"{row['bezeichnung']} - Beitrag",
                    "altersvorsorge_id": row["id"], "typ": "Wiederkehrend", "virtuell": True,
                })

        rentenbeginn = date.fromisoformat(row["rentenbeginn"])
        if row["auszahlungsart"] == "rente" and row["rente_garantiert_betrag"] is not None:
            horizont = min(bis + wiederkehrend_modul.VERSCHIEBUNG_PUFFER, _renten_horizont(row, zeit.heute()))
            for termin in _renten_termine(row, horizont):
                verschoben = vorheriger_werktag(termin, feiertage)
                if verschoben <= ab or verschoben > bis:
                    continue
                betrag = abs(row["rente_garantiert_betrag"])
                if inflation and row["auszahlung_inflationsflag"]:
                    # Seit v2.0 nur mit Schalter "Inflation einrechnen". Rein rechnerische Projektion (siehe wiederkehrend.
                    # betrag_mit_inflation) - reale Buchungen nutzen immer
                    # den unveränderten garantierten Betrag.
                    betrag = wiederkehrend_modul.betrag_mit_inflation(betrag, verschoben, inflationsfaktor_prozent)
                ergebnis.append({
                    "datum": verschoben.isoformat(), "termin": termin.isoformat(), "betrag": betrag,
                    "konto_id": row["zahlungskonto_id"], "kategorie_id": row["auszahlung_kategorie_id"],
                    "beschreibung": f"{row['bezeichnung']} - Rente", "altersvorsorge_id": row["id"],
                    "typ": "Wiederkehrend", "virtuell": True,
                })
        elif row["auszahlungsart"] == "einmalzahlung" and row["einmalzahlung_garantiert_betrag"] is not None:
            verschoben = vorheriger_werktag(rentenbeginn, feiertage)
            if ab < verschoben <= bis:
                betrag = abs(row["einmalzahlung_garantiert_betrag"])
                if inflation and row["auszahlung_inflationsflag"]:
                    betrag = wiederkehrend_modul.betrag_mit_inflation(betrag, verschoben, inflationsfaktor_prozent)
                ergebnis.append({
                    "datum": verschoben.isoformat(), "termin": rentenbeginn.isoformat(), "betrag": betrag,
                    "konto_id": row["zahlungskonto_id"], "kategorie_id": row["auszahlung_kategorie_id"],
                    "beschreibung": f"{row['bezeichnung']} - Einmalzahlung", "altersvorsorge_id": row["id"],
                    "typ": "Wiederkehrend", "virtuell": True,
                })
    ergebnis.sort(key=lambda b: b["datum"])
    return ergebnis


def korridor_projektion(conn, ab: date, bis: date, konto_ids=None,
                         id_filter: Optional[int] = None, inflation: bool = False) -> dict:
    """
    Netto-Effekt je Monat der 'voraussichtlichen' Variante (nur in der
    Auszahlungsphase - in der Beitragsphase sind garantiert und
    voraussichtlich identisch, daher dort kein Unterschied). Für den
    optionalen Korridor im Saldo-Verlauf - rein rechnerisch, ohne
    Datenbank-Schreibzugriff.
    """
    ergebnis: dict = {}
    sql = "SELECT * FROM altersvorsorge WHERE aktiv = 1"
    params: list = []
    if konto_ids is not None:  # seit v2.3 Menge (None = alle Konten)
        sql += f" AND zahlungskonto_id IN ({','.join('?' * len(konto_ids)) or 'NULL'})"
        params.extend(sorted(konto_ids))
    if id_filter is not None:
        sql += " AND id = ?"
        params.append(id_filter)

    faktor = wiederkehrend_modul.globaler_inflationsfaktor(conn) if inflation else 0.0

    def _infl(delta, termin, row):
        # seit v2.0 wie die garantierten Beträge hochgerechnet (Schalter + Häkchen)
        if inflation and row["auszahlung_inflationsflag"]:
            return wiederkehrend_modul.betrag_mit_inflation(delta, termin, faktor)
        return delta

    for row in conn.execute(sql, params).fetchall():
        rentenbeginn = date.fromisoformat(row["rentenbeginn"])
        if row["auszahlungsart"] == "rente" and row["rente_voraussichtlich_betrag"] is not None:
            horizont = min(bis, _renten_horizont(row, zeit.heute()))
            for termin in _renten_termine(row, horizont):
                if termin <= ab or termin > bis:
                    continue
                monat = date(termin.year, termin.month, 1)
                delta = _infl(row["rente_voraussichtlich_betrag"] - (row["rente_garantiert_betrag"] or 0), termin, row)
                ergebnis[monat] = ergebnis.get(monat, 0.0) + delta
        elif row["auszahlungsart"] == "einmalzahlung" and row["einmalzahlung_voraussichtlich_betrag"] is not None:
            if ab < rentenbeginn <= bis:
                monat = date(rentenbeginn.year, rentenbeginn.month, 1)
                delta = _infl(row["einmalzahlung_voraussichtlich_betrag"] - (row["einmalzahlung_garantiert_betrag"] or 0),
                              rentenbeginn, row)
                ergebnis[monat] = ergebnis.get(monat, 0.0) + delta
    return ergebnis


# ─── Rentenbeginn verschoben: Phasen bereinigen (seit v2.0) ───────────

def phasen_konflikte(conn, row_alt, neuer_rentenbeginn: date, feiertage: dict,
                     heute: Optional[date] = None) -> dict:
    """
    Automatisch erzeugte Buchungen eines Vertrags, die nach einer
    Verschiebung des Rentenbeginns in der falschen Phase lägen: Beiträge,
    deren ursprünglicher Termin am oder nach dem neuen Rentenbeginn liegt
    (Rentenbeginn vorverlegt), bzw. Rentenzahlungen mit Termin vor dem neuen
    Rentenbeginn (nach hinten verschoben). Bei einer Einmalzahlung ist die
    bereits gebuchte Zahlung zum alten Termin falsch. Der ursprüngliche
    Termin wird über den alten Terminplan aus dem gebuchten (verschobenen)
    Datum zurückgerechnet. Per "Anpassen" verschobene Buchungen werden nie
    gelöscht, sondern nur gemeldet, wenn sie im Zeitraum zwischen altem und
    neuem Rentenbeginn liegen.
    """
    heute = heute or zeit.heute()
    alter_rb = date.fromisoformat(row_alt["rentenbeginn"])
    ergebnis = {"loeschen": [], "angepasst": []}
    if neuer_rentenbeginn == alter_rb:
        return ergebnis
    angepasst = {r[0] for r in conn.execute(
        """SELECT p.buchung_id FROM plan_buchung_protokoll p JOIN buchungen b ON b.id = p.buchung_id
           WHERE p.status = 'angepasst' AND b.ziel_altersvorsorge_id = ?""", (row_alt["id"],)).fetchall()}
    # Plan: per "Anpassen" verschobene Buchungen sind (bis zum nächsten Start) Plan
    buchungen = conn.execute(
        "SELECT id, datum, betrag FROM buchungen WHERE ziel_altersvorsorge_id = ? AND typ IN ('Ist', 'Plan')",
        (row_alt["id"],)).fetchall()

    beitrag_termin = {}
    if row_alt["hat_einzahlung"] and row_alt["beitrag_startdatum"]:
        for t in wiederkehrend_modul.alle_termine(_beitrag_vorlage(row_alt), heute):
            beitrag_termin.setdefault(vorheriger_werktag(t, feiertage).isoformat(), t)
    renten_termin = {}
    if row_alt["auszahlungsart"] == "rente":
        for t in _renten_termine(row_alt, min(heute, _renten_horizont(row_alt, heute))):
            renten_termin.setdefault(vorheriger_werktag(t, feiertage).isoformat(), t)
    einmal_datum = vorheriger_werktag(alter_rb, feiertage).isoformat()

    von, bis = sorted([alter_rb, neuer_rentenbeginn])
    for b in buchungen:
        if b["id"] in angepasst:
            if von.isoformat() <= b["datum"] <= bis.isoformat() or b["datum"] >= neuer_rentenbeginn.isoformat():
                ergebnis["angepasst"].append(b["id"])
            continue
        if b["betrag"] < 0:
            t = beitrag_termin.get(b["datum"])
            if t is not None and t >= neuer_rentenbeginn:
                ergebnis["loeschen"].append(b["id"])
        elif row_alt["auszahlungsart"] == "rente":
            t = renten_termin.get(b["datum"])
            if t is not None and t < neuer_rentenbeginn:
                ergebnis["loeschen"].append(b["id"])
        elif b["datum"] == einmal_datum:
            ergebnis["loeschen"].append(b["id"])
    return ergebnis


def phasen_bereinigen(conn, ids: list[int]) -> int:
    """Löscht die übergebenen Buchungen samt ihrer Protokolleinträge (nach
    Bestätigung im Dialog). Commit übernimmt der Aufrufer."""
    for bid in ids:
        conn.execute("DELETE FROM plan_buchung_protokoll WHERE buchung_id = ?", (bid,))
        conn.execute("DELETE FROM buchungen WHERE id = ?", (bid,))
    return len(ids)

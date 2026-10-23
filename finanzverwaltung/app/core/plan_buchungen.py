"""
Verarbeitung von Plan-Buchungen: automatische Umwandlung fälliger
Plan-Buchungen in Ist-Buchungen beim Programmstart (Entscheidung:
sofort automatisch, mit nachträglicher Korrekturmöglichkeit per
Maske) sowie die Protokollierung jeder Umwandlung/Korrektur.
"""
from datetime import date
from . import zeit


def umwandeln_faellige(conn, heute: date | None = None) -> list[int]:
    """
    Wandelt alle Plan-Buchungen mit Datum <= heute in Ist-Buchungen um
    und protokolliert jede Umwandlung. Gibt die IDs der umgewandelten
    Buchungen zurück (für die nachträgliche Bestätigungsmaske).
    """
    heute = heute or zeit.heute()
    faellige = conn.execute(
        "SELECT id FROM buchungen WHERE typ = 'Plan' AND datum <= ?",
        (heute.isoformat(),),
    ).fetchall()

    ids = [row["id"] for row in faellige]
    for buchung_id in ids:
        conn.execute("UPDATE buchungen SET typ = 'Ist' WHERE id = ?", (buchung_id,))
        conn.execute(
            """INSERT INTO plan_buchung_protokoll (buchung_id, datum_umwandlung, status)
               VALUES (?, ?, 'umgewandelt')""",
            (buchung_id, heute.isoformat()),
        )
    conn.commit()
    return ids


def ablehnen_anpassen(conn, buchung_id: int, neues_datum: date) -> None:
    """Ablehnen einer umgewandelten Buchung: Datum anpassen, zurück auf 'Plan'.
    Übertragungen (erzeugt aus Umbuchungs-Vorlagen, seit v1.10) behalten
    ihren Typ - als 'Plan' würden sie zu einer einseitigen Buchung auf dem
    Quellkonto, das Zielkonto bekäme nichts. Sie zählen ab ihrem Datum wie
    jede Übertragung."""
    alt = conn.execute("SELECT datum FROM buchungen WHERE id = ?", (buchung_id,)).fetchone()
    conn.execute(
        """UPDATE buchungen SET typ = CASE WHEN typ = 'Uebertragung' THEN 'Uebertragung' ELSE 'Plan' END,
           datum = ? WHERE id = ?""",
        (neues_datum.isoformat(), buchung_id),
    )
    # Seit v2.0 mit ursprünglichem Datum: daran erkennt die Altersvorsorge-
    # Nachbuchung (Rentenbeginn verschoben), dass dieser Termin schon durch
    # eine angepasste Buchung vertreten ist.
    hinweis = f"Datum angepasst auf {neues_datum.isoformat()}"
    if alt:
        hinweis += f" (ursprünglich {alt['datum']})"
    conn.execute(
        """INSERT INTO plan_buchung_protokoll (buchung_id, datum_umwandlung, status, hinweis)
           VALUES (?, ?, 'angepasst', ?)""",
        (buchung_id, zeit.heute().isoformat(), hinweis),
    )
    conn.commit()


def ablehnen_loeschen(conn, buchung_id: int, inkl_zukuenftige: bool = True) -> int:
    """
    Ablehnen: Buchung löschen. Ist sie Teil einer wiederkehrenden
    Vorlage und 'inkl_zukuenftige' gesetzt, werden auch alle
    zukünftigen Buchungen dieser Vorlage gelöscht und die Vorlage
    deaktiviert.
    """
    row = conn.execute(
        "SELECT wiederkehrend_id, datum FROM buchungen WHERE id = ?", (buchung_id,)
    ).fetchone()
    if row is None:
        return 0

    if inkl_zukuenftige and row["wiederkehrend_id"]:
        zukuenftige = conn.execute(
            """SELECT id FROM buchungen
               WHERE wiederkehrend_id = ? AND datum >= ?""",
            (row["wiederkehrend_id"], row["datum"]),
        ).fetchall()
        for z in zukuenftige:
            conn.execute(
                """INSERT INTO plan_buchung_protokoll (buchung_id, datum_umwandlung, status)
                   VALUES (?, ?, 'geloescht')""",
                (z["id"], zeit.heute().isoformat()),
            )
        conn.execute(
            "DELETE FROM buchungen WHERE wiederkehrend_id = ? AND datum >= ?",
            (row["wiederkehrend_id"], row["datum"]),
        )
        conn.execute(
            "UPDATE wiederkehrende_buchungen SET aktiv = 0 WHERE id = ?",
            (row["wiederkehrend_id"],),
        )
        anzahl = len(zukuenftige)
    else:
        conn.execute(
            """INSERT INTO plan_buchung_protokoll (buchung_id, datum_umwandlung, status)
               VALUES (?, ?, 'geloescht')""",
            (buchung_id, zeit.heute().isoformat()),
        )
        conn.execute("DELETE FROM buchungen WHERE id = ?", (buchung_id,))
        anzahl = 1

    conn.commit()
    return anzahl

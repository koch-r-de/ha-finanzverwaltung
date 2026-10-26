"""
Buchungsengine: Konten, Kategorien, Buchungen und Saldo-Berechnung.

Fachliche Kernregel (Saldo-Korrektur):
Eine Saldo-Korrektur wirkt fix ab ihrem Datum. Wird später eine
Ist-Buchung VOR einer bestehenden Korrektur nachgetragen, ändert das
den Saldo AB dem Korrekturdatum nicht - die Korrektur bleibt die
Basis. Buchungen vor der jüngsten (zum Stichtag gültigen) Korrektur
fließen daher nicht mehr in die Berechnung ein.

Übertragungen: gespeichert als eine Zeile (konto_id = Quelle,
zielkonto_id = Ziel, betrag = positiver Übertragungsbetrag). Für die
Saldo-Berechnung wirkt das wie ein Abgang bei der Quelle und ein
Zugang beim Ziel; ein "Gegenbuchung"-Effekt ergibt sich also direkt
aus der Abfrage, ohne eine zweite Zeile physisch zu duplizieren.
"""
import sqlite3
from datetime import date
from typing import Optional
from . import zeit


def _iso(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else d


# ─── Konten ──────────────────────────────────────────────────────────

def konto_anlegen(conn, name: str, typ: str, eroeffnungsdatum: date,
                   person_id: Optional[int] = None, in_gesamtsaldo: bool = True,
                   farbe: Optional[str] = None) -> int:
    cur = conn.execute(
        "INSERT INTO konten (name, typ, eroeffnungsdatum, person_id, in_gesamtsaldo, farbe) VALUES (?, ?, ?, ?, ?, ?)",
        (name, typ, _iso(eroeffnungsdatum), person_id, int(in_gesamtsaldo), farbe or None),
    )
    conn.commit()
    return cur.lastrowid


def konto_bearbeiten(conn, konto_id: int, **felder) -> None:
    erlaubt = {"name", "typ", "eroeffnungsdatum", "aktiv", "person_id", "in_gesamtsaldo", "farbe"}
    setzen = {k: v for k, v in felder.items() if k in erlaubt}
    if not setzen:
        return
    klauseln = ", ".join(f"{k} = ?" for k in setzen)
    conn.execute(f"UPDATE konten SET {klauseln} WHERE id = ?", (*setzen.values(), konto_id))
    conn.commit()


def konto_loeschen(conn, konto_id: int) -> None:
    """Konten werden deaktiviert statt hart gelöscht, um Buchungshistorie zu erhalten."""
    conn.execute("UPDATE konten SET aktiv = 0 WHERE id = ?", (konto_id,))
    conn.commit()


def konten_liste(conn, nur_aktive: bool = True, person_id: Optional[int] = None):
    bedingungen = []
    params: list = []
    if nur_aktive:
        bedingungen.append("aktiv = 1")
    if person_id is not None:
        bedingungen.append("person_id = ?")
        params.append(person_id)
    where = f"WHERE {' AND '.join(bedingungen)}" if bedingungen else ""
    return conn.execute(f"SELECT * FROM konten {where} ORDER BY name", params).fetchall()


# ─── Kategorien ─────────────────────────────────────────────────────

def umbuchung_kategorie_id(conn) -> int:
    """Auflösung über den stabilen system_key, NIE über eine feste ID."""
    row = conn.execute("SELECT id FROM kategorien WHERE system_key = 'umbuchung'").fetchone()
    if row is None:
        raise ValueError("System-Kategorie 'Umbuchung' fehlt - Migration nicht gelaufen?")
    return row["id"]


def kategorie_anlegen(conn, name: str, parent_id: Optional[int] = None, typ: Optional[str] = None) -> int:
    """Ohne ausdrücklichen Typ wird er vom obersten Knoten der Elternkette
    geerbt (siehe db.typ_vom_wurzelknoten)."""
    from .db import typ_vom_wurzelknoten
    if typ is None:
        typ = typ_vom_wurzelknoten(conn, parent_id)
    cur = conn.execute(
        "INSERT INTO kategorien (name, parent_id, typ) VALUES (?, ?, ?)", (name, parent_id, typ)
    )
    conn.commit()
    return cur.lastrowid


def kategorie_bearbeiten(conn, kategorie_id: int, name: str, parent_id: Optional[int],
                          typ: Optional[str] = None, siri_favorit: Optional[bool] = None) -> None:
    """Von der Fachlogik referenzierte System-Kategorien sind - genau wie
    beim Löschen - vor Umbenennen/Verschieben geschützt (siehe
    kategorie_ist_system)."""
    if kategorie_ist_system(conn, kategorie_id):
        raise ValueError("Diese Kategorie ist fest vorgegeben und kann nicht geändert werden.")
    from .db import typ_vom_wurzelknoten
    if typ is None:
        typ = typ_vom_wurzelknoten(conn, parent_id)
    if siri_favorit is None:
        conn.execute("UPDATE kategorien SET name = ?, parent_id = ?, typ = ? WHERE id = ?",
                     (name, parent_id, typ, kategorie_id))
    else:
        conn.execute("UPDATE kategorien SET name = ?, parent_id = ?, typ = ?, siri_favorit = ? WHERE id = ?",
                     (name, parent_id, typ, int(siri_favorit), kategorie_id))
    conn.commit()


def siri_favoriten(conn):
    return conn.execute(
        "SELECT id, name, typ FROM kategorien WHERE siri_favorit = 1 ORDER BY name"
    ).fetchall()


def siri_favorit_setzen(conn, kategorie_id: int, aktiv: bool) -> None:
    # Kein Limit mehr - beliebig viele Kategorien können als Favorit
    # markiert werden.
    conn.execute("UPDATE kategorien SET siri_favorit = ? WHERE id = ?", (int(aktiv), kategorie_id))
    conn.commit()


def kategorie_ist_system(conn, kategorie_id: int) -> bool:
    row = conn.execute("SELECT system_key FROM kategorien WHERE id = ?", (kategorie_id,)).fetchone()
    return bool(row and row["system_key"])


def kategorie_loeschen(conn, kategorie_id: int) -> None:
    """Von der Fachlogik referenzierte System-Kategorien sind geschützt.
    Kategorien mit Unterkategorien werden ebenfalls abgelehnt, statt sie
    per ON DELETE CASCADE (siehe schema.sql) still mitzulöschen - sonst
    verschwindet ein ganzer Teilbaum ohne erkennbare Warnung. Ist die
    Kategorie noch an Buchungen/Vorlagen/Verträgen hängt, verhindert der
    FK-Constraint das Löschen ohnehin (PRAGMA foreign_keys = ON) - das
    wird hier nur in eine verständliche Fehlermeldung übersetzt."""
    if kategorie_ist_system(conn, kategorie_id):
        raise ValueError("Diese Kategorie ist fest vorgegeben und kann nicht gelöscht werden.")
    hat_kinder = conn.execute(
        "SELECT 1 FROM kategorien WHERE parent_id = ? LIMIT 1", (kategorie_id,)
    ).fetchone()
    if hat_kinder:
        raise ValueError("Diese Kategorie hat Unterkategorien und kann nicht gelöscht werden, "
                          "solange diese noch existieren.")
    try:
        conn.execute("DELETE FROM kategorien WHERE id = ?", (kategorie_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError("Diese Kategorie wird noch verwendet (z. B. von Buchungen, wiederkehrenden "
                          "Vorlagen oder Altersvorsorge-Verträgen) und kann nicht gelöscht werden.")


def kategorien_baum(conn):
    """Alle Kategorien als flache Liste mit parent_id - der Aufbau des Baums erfolgt im Frontend."""
    return conn.execute("SELECT * FROM kategorien ORDER BY name").fetchall()


# ─── Buchungen ──────────────────────────────────────────────────────

def vorzeichen_anwenden(conn, kategorie_id: int, betrag: float) -> float:
    """
    Leitet das Vorzeichen aus dem Kategorie-Typ ab: Ausgabe-Kategorien
    werden immer negativ, Einnahme-Kategorien immer positiv gebucht. Der
    Anwender gibt den Betrag also stets positiv ein - damit ist die
    häufigste Fehlerquelle (Ausgabe versehentlich positiv erfasst und
    dadurch saldo- und cashflow-wirksam falsch) konstruktiv ausgeschlossen.
    Kategorien ohne Typ (systemseitig neutral) bleiben unangetastet.
    """
    row = conn.execute("SELECT typ FROM kategorien WHERE id = ?", (kategorie_id,)).fetchone()
    if row is None or row["typ"] is None:
        return betrag
    return -abs(betrag) if row["typ"] == "ausgabe" else abs(betrag)


def sparziel_pruefen(conn, typ: str, konto_id: Optional[int], zielkonto_id: Optional[int],
                     sparziel_id: Optional[int]) -> Optional[str]:
    """
    Regel seit v2.0: Ein Sparziel darf nur an einer Übertragung hängen, deren
    Quelle oder Ziel das Trägerkonto des Sparziels ist (Ziel = Einzahlung,
    Quelle = Entnahme). Ist- und Plan-Buchungen tragen kein Sparziel.
    Liefert eine Fehlermeldung oder None. Gilt für Buchungen, Vorlagen,
    Import und Schnellbuchung gleichermaßen.
    """
    if not sparziel_id:
        return None
    if typ != "Uebertragung":
        return "Ein Sparziel ist nur bei Übertragungen möglich."
    sz = conn.execute("SELECT name, konto_id, typ FROM budgets WHERE id = ?", (sparziel_id,)).fetchone()
    if sz is None or sz["typ"] != "sparziel":
        return "Das Sparziel existiert nicht."
    if sz["konto_id"] is None:
        return f"Das Sparziel „{sz['name']}“ hat kein Trägerkonto."
    if sz["konto_id"] not in (konto_id, zielkonto_id):
        traeger = conn.execute("SELECT name FROM konten WHERE id = ?", (sz["konto_id"],)).fetchone()
        return (f"Das Sparziel „{sz['name']}“ liegt auf dem Konto „{traeger['name'] if traeger else '?'}“. "
                "Die Übertragung muss von diesem Konto (Entnahme) oder auf dieses Konto (Einzahlung) gehen.")
    return None


def buchung_anlegen(conn, *, konto_id: int, datum: date, betrag: float, kategorie_id: int,
                     typ: str, beschreibung: str = None, zielkonto_id: int = None,
                     ziel_darlehen_id: int = None, wiederkehrend_id: int = None,
                     sparziel_id: int = None, inflationsflag: bool = False,
                     vorzeichen_ableiten: bool = True) -> int:
    if typ not in ("Ist", "Plan", "Uebertragung"):
        raise ValueError(f"Unbekannter Buchungstyp: {typ}")
    if typ == "Uebertragung":
        if not zielkonto_id:
            raise ValueError("Bei Übertragungen ist ein Zielkonto Pflicht.")
        # Übertragungen bekommen immer die feste Kategorie "Umbuchung" und
        # werden ohne Vorzeichen als Betrag (Soll Quellkonto / Haben
        # Zielkonto) gebucht - siehe Modul-Docstring.
        kategorie_id = umbuchung_kategorie_id(conn)
        betrag = abs(betrag)
    else:
        # Zielkonto gibt es nur bei Übertragungen, wie in buchung_bearbeiten
        # (seit 2.6.1, Befund P: das Formular schickte das verborgene Feld mit).
        zielkonto_id = None
        if vorzeichen_ableiten:
            betrag = vorzeichen_anwenden(conn, kategorie_id, betrag)

    cur = conn.execute(
        """INSERT INTO buchungen
           (konto_id, zielkonto_id, ziel_darlehen_id, sparziel_id, datum, betrag,
            kategorie_id, typ, beschreibung, wiederkehrend_id, inflationsflag)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (konto_id, zielkonto_id, ziel_darlehen_id, sparziel_id, _iso(datum), betrag,
         kategorie_id, typ, beschreibung, wiederkehrend_id, int(inflationsflag)),
    )
    conn.commit()
    return cur.lastrowid


def buchung_loeschen(conn, buchung_id: int) -> None:
    conn.execute("DELETE FROM buchungen WHERE id = ?", (buchung_id,))
    conn.commit()


def saldo_korrektur_anlegen(conn, *, konto_id: int, datum: date, saldo: float,
                             kommentar: str = None) -> int:
    cur = conn.execute(
        "INSERT INTO saldo_korrekturen (konto_id, datum, saldo, kommentar) VALUES (?, ?, ?, ?)",
        (konto_id, _iso(datum), saldo, kommentar),
    )
    conn.commit()
    return cur.lastrowid


def _summe(conn, spalte: str, konto_id: int, typen: tuple, ab_iso: str, bis_iso: str) -> float:
    platzhalter = ",".join("?" * len(typen))
    row = conn.execute(
        f"""SELECT COALESCE(SUM(betrag), 0) FROM buchungen
            WHERE {spalte} = ? AND typ IN ({platzhalter}) AND datum >= ? AND datum <= ?""",
        (konto_id, *typen, ab_iso, bis_iso),
    ).fetchone()
    return row[0]


def saldo(conn, konto_id: int, stichtag: Optional[date] = None, inkl_plan: bool = False) -> float:
    """
    Saldo eines Kontos zu einem Stichtag (Standard: heute) - siehe
    Modul-Docstring zur Saldo-Korrektur-Regel.

    inkl_plan=False (Standard): nur tatsächlich gebuchte Ist-Buchungen -
        das ist der "echte", aktuelle Kontostand.
    inkl_plan=True: zusätzlich bereits erzeugte Plan-Buchungen bis zum
        Stichtag - für Prognosen (Saldo-Verlauf), NICHT für den
        angezeigten "aktuellen Saldo" einer Kontokarte verwenden.
    """
    stichtag = stichtag or zeit.heute()
    bis_iso = _iso(stichtag)
    typen = ("Ist", "Plan") if inkl_plan else ("Ist",)

    korrektur = conn.execute(
        """SELECT datum, saldo FROM saldo_korrekturen
           WHERE konto_id = ? AND datum <= ?
           ORDER BY datum DESC LIMIT 1""",
        (konto_id, bis_iso),
    ).fetchone()

    if korrektur:
        ab_iso = korrektur["datum"]
        basis_saldo = korrektur["saldo"]
    else:
        ab_iso = "0001-01-01"
        basis_saldo = 0.0

    ist = _summe(conn, "konto_id", konto_id, typen, ab_iso, bis_iso)
    abgang = _summe(conn, "konto_id", konto_id, ("Uebertragung",), ab_iso, bis_iso)
    zugang = _summe(conn, "zielkonto_id", konto_id, ("Uebertragung",), ab_iso, bis_iso)

    return round(basis_saldo + ist - abgang + zugang, 2)


def summe_kategorie(conn, konto_id: int, kategorie_id: int, bis: date, inkl_plan: bool = True) -> float:
    """
    Kumulierte Summe EINER Kategorie auf einem Konto bis einschließlich
    eines Stichtags - anders als saldo() bewusst OHNE Saldo-Korrektur-
    Basis, da eine Kategorie-Teilsumme kein "Kontostand" im eigentlichen
    Sinn ist, sondern eine reine Teilmenge der Buchungen. Grundlage für
    den kategorie-gefilterten Saldo-Verlauf in den Auswertungen (bewusste
    Abweichung von der echten Kontostand-Semantik, siehe
    auswertungen.saldo_verlauf).
    """
    typen = ("Ist", "Plan") if inkl_plan else ("Ist",)
    platzhalter = ",".join("?" * len(typen))
    row = conn.execute(
        f"""SELECT COALESCE(SUM(betrag), 0) FROM buchungen
            WHERE konto_id = ? AND kategorie_id = ? AND typ IN ({platzhalter}) AND datum <= ?""",
        (konto_id, kategorie_id, *typen, _iso(bis)),
    ).fetchone()
    return round(row[0], 2)


def sql_in(spalte: str, menge, bedingungen: list, params: list) -> None:
    """Mehrfachfilter (seit v2.3): menge None = kein Filter, leere Menge =
    nichts, sonst spalte IN (...)."""
    if menge is None:
        return
    if not menge:
        bedingungen.append("0")
        return
    bedingungen.append(f"{spalte} IN ({','.join('?' * len(menge))})")
    params.extend(sorted(menge))


def cashflow(conn, von: date, bis: date, inkl_plan: bool = False,
             konto_id: Optional[int] = None, kategorie_id: Optional[int] = None,
             person_id: Optional[int] = None, konto_ids=None, kategorie_ids=None):
    """
    Einnahmen/Ausgaben gruppiert nach Monat. Übertragungen werden
    ignoriert (kein Cashflow-Effekt). inkl_plan=True zieht zusätzlich
    bereits erzeugte Plan-Buchungen heran - für Prognosen. konto_id,
    kategorie_id und person_id filtern optional auf ein einzelnes Konto,
    eine einzelne Kategorie bzw. eine Person (über das Konto, siehe
    personen.py-Modul-Docstring) - für die entsprechenden
    Auswertungs-Filter.
    """
    typen = ("Ist", "Plan") if inkl_plan else ("Ist",)
    platzhalter = ",".join("?" * len(typen))
    bedingungen = [f"typ IN ({platzhalter})", "datum >= ?", "datum <= ?"]
    params: list = [*typen, _iso(von), _iso(bis)]
    if konto_id is not None:
        bedingungen.append("konto_id = ?")
        params.append(konto_id)
    if kategorie_id is not None:
        bedingungen.append("kategorie_id = ?")
        params.append(kategorie_id)
    if person_id is not None:
        bedingungen.append("konto_id IN (SELECT id FROM konten WHERE person_id = ?)")
        params.append(person_id)
    sql_in("konto_id", konto_ids, bedingungen, params)
    sql_in("kategorie_id", kategorie_ids, bedingungen, params)
    rows = conn.execute(
        f"""SELECT strftime('%Y-%m', datum) AS monat,
                  SUM(CASE WHEN betrag > 0 THEN betrag ELSE 0 END) AS einnahmen,
                  SUM(CASE WHEN betrag < 0 THEN -betrag ELSE 0 END) AS ausgaben
           FROM buchungen
           WHERE {' AND '.join(bedingungen)}
           GROUP BY monat ORDER BY monat""",
        params,
    ).fetchall()
    return rows


# Automatisch erzeugte Buchungen (Herkunfts-Filter): Vorlagen, Darlehensraten
# (nur Zins/Tilgung - Auszahlungen und Sondertilgungen löst der Anwender
# selbst aus) und Altersvorsorge. Bei jeder neuen automatischen Quelle hier
# ergänzen.
AUTOMATISCH_SQL = """(wiederkehrend_id IS NOT NULL
    OR ziel_altersvorsorge_id IS NOT NULL
    OR (ziel_darlehen_id IS NOT NULL AND kategorie_id IN
        (SELECT id FROM kategorien WHERE system_key IN ('darlehen_zinsen', 'darlehen_tilgung'))))"""


def buchungen_liste(conn, konto_id: Optional[int] = None, von: Optional[date] = None,
                     bis: Optional[date] = None, typ: Optional[str] = None,
                     ziel_darlehen_id: Optional[int] = None,
                     herkunft: Optional[str] = None,
                     kategorie_id: Optional[int] = None,
                     person_id: Optional[int] = None):
    """
    herkunft filtert nach der Entstehung einer Buchung:
      'manuell'       - vom Anwender selbst ausgelöst (auch Darlehens-
                        Auszahlungen und Sondertilgungen, seit v1.8)
      'wiederkehrend' - automatisch entstanden: aus einer wiederkehrenden
                        Vorlage, als Darlehensrate (Zinsen/Tilgung) oder aus
                        einem Altersvorsorge-Vertrag (Altersvorsorge seit v1.8,
                        vorher fälschlich unter 'manuell')
      None            - alles
    Das ist unabhängig vom Buchungstyp: eine aus einer Vorlage erzeugte
    Buchung ist technisch eine ganz normale Ist-Buchung, soll in der
    Übersicht aber unterscheidbar bleiben.

    person_id filtert über das (Quell-)Konto: Buchungen selbst tragen
    keine eigene person_id, sondern erben die Zuordnung von ihrem Konto
    (siehe personen.py-Modul-Docstring).
    """
    """
    Buchungen im Zeitraum. Bei Angabe eines Kontos werden auch eingehende
    Übertragungen (Konto als Zielkonto) mit aufgeführt. Bei Angabe von
    ziel_darlehen_id werden nur die Zahlungen (Zinsen/Tilgung/Sondertilgung/
    Auszahlung) dieses Darlehens geliefert.
    """
    bedingungen = []
    params: list = []

    if konto_id is not None:
        bedingungen.append("(konto_id = ? OR zielkonto_id = ?)")
        params += [konto_id, konto_id]
    if von is not None:
        bedingungen.append("datum >= ?")
        params.append(_iso(von))
    if bis is not None:
        bedingungen.append("datum <= ?")
        params.append(_iso(bis))
    if typ is not None:
        bedingungen.append("typ = ?")
        params.append(typ)
    if ziel_darlehen_id is not None:
        bedingungen.append("ziel_darlehen_id = ?")
        params.append(ziel_darlehen_id)
    if herkunft == "manuell":
        bedingungen.append(f"NOT {AUTOMATISCH_SQL}")
    elif herkunft == "wiederkehrend":
        bedingungen.append(AUTOMATISCH_SQL)
    if kategorie_id is not None:
        bedingungen.append("kategorie_id = ?")
        params.append(kategorie_id)
    if person_id is not None:
        bedingungen.append(
            "konto_id IN (SELECT id FROM konten WHERE person_id = ?)"
        )
        params.append(person_id)

    where = f"WHERE {' AND '.join(bedingungen)}" if bedingungen else ""
    return conn.execute(
        f"SELECT * FROM buchungen {where} ORDER BY datum, id", params
    ).fetchall()


def buchungen_suchen(conn, *, text: str = None, betrag_von: float = None,
                      betrag_bis: float = None, von: date = None, bis: date = None,
                      konto_id: int = None, kategorie_id: int = None,
                      inkl_unterkategorien: bool = True, typ: str = None,
                      person_id: int = None,
                      limit: int = 500):
    """
    Volltext- und Feldsuche über alle Buchungen (Ist, Plan und
    Übertragungen). Der Betragsvergleich läuft über den Absolutbetrag,
    damit man 1084 findet, ohne das Vorzeichen zu kennen.
    """
    bedingungen, params = [], []

    if text:
        bedingungen.append("(b.beschreibung LIKE ? OR k.name LIKE ?)")
        params += [f"%{text}%", f"%{text}%"]
    if betrag_von is not None:
        bedingungen.append("ABS(b.betrag) >= ?")
        params.append(abs(betrag_von))
    if betrag_bis is not None:
        bedingungen.append("ABS(b.betrag) <= ?")
        params.append(abs(betrag_bis))
    if von is not None:
        bedingungen.append("b.datum >= ?")
        params.append(_iso(von))
    if bis is not None:
        bedingungen.append("b.datum <= ?")
        params.append(_iso(bis))
    if konto_id is not None:
        bedingungen.append("(b.konto_id = ? OR b.zielkonto_id = ?)")
        params += [konto_id, konto_id]
    if typ:
        bedingungen.append("b.typ = ?")
        params.append(typ)
    if kategorie_id is not None:
        ids = [kategorie_id]
        if inkl_unterkategorien:
            rand = [kategorie_id]
            while rand:
                ph = ",".join("?" * len(rand))
                kinder = [r["id"] for r in conn.execute(
                    f"SELECT id FROM kategorien WHERE parent_id IN ({ph})", rand).fetchall()]
                ids += kinder
                rand = kinder
        ph = ",".join("?" * len(ids))
        bedingungen.append(f"b.kategorie_id IN ({ph})")
        params += ids
    if person_id is not None:
        bedingungen.append("ko.person_id = ?")
        params.append(person_id)

    where = f"WHERE {' AND '.join(bedingungen)}" if bedingungen else ""
    rows = conn.execute(
        f"""SELECT b.*, k.name AS kategorie_name, ko.name AS konto_name
            FROM buchungen b
            LEFT JOIN kategorien k ON k.id = b.kategorie_id
            LEFT JOIN konten ko ON ko.id = b.konto_id
            {where} ORDER BY b.datum DESC, b.id DESC LIMIT ?""",
        [*params, limit],
    ).fetchall()

    treffer = [dict(r) for r in rows]
    summe = round(sum(r["betrag"] for r in treffer), 2)
    return {"treffer": treffer, "anzahl": len(treffer), "summe": summe}


def vorzeichen_korrigieren(conn, buchung_ids: list[int]) -> int:
    """Dreht das Vorzeichen der angegebenen Buchungen passend zum Kategorie-Typ."""
    anzahl = 0
    for bid in buchung_ids:
        row = conn.execute(
            """SELECT b.betrag, k.typ FROM buchungen b JOIN kategorien k ON k.id = b.kategorie_id
               WHERE b.id = ?""", (bid,)).fetchone()
        if row is None or row["typ"] is None:
            continue
        neu = -abs(row["betrag"]) if row["typ"] == "ausgabe" else abs(row["betrag"])
        if neu != row["betrag"]:
            conn.execute("UPDATE buchungen SET betrag = ? WHERE id = ?", (neu, bid))
            anzahl += 1
    conn.commit()
    return anzahl


def vorlagen_vorzeichen_korrigieren(conn, vorlage_ids: list[int]) -> int:
    anzahl = 0
    for vid in vorlage_ids:
        row = conn.execute(
            """SELECT w.betrag, k.typ FROM wiederkehrende_buchungen w
               JOIN kategorien k ON k.id = w.kategorie_id WHERE w.id = ?""", (vid,)).fetchone()
        if row is None or row["typ"] is None:
            continue
        neu = -abs(row["betrag"]) if row["typ"] == "ausgabe" else abs(row["betrag"])
        if neu != row["betrag"]:
            conn.execute("UPDATE wiederkehrende_buchungen SET betrag = ? WHERE id = ?", (neu, vid))
            anzahl += 1
    conn.commit()
    return anzahl


# ─── Buchung bearbeiten ─────────────────────────────────────────────

def buchung_bearbeiten(conn, buchung_id: int, *, konto_id: int, datum: date, betrag: float,
                        kategorie_id: int, typ: str, beschreibung: str = None,
                        zielkonto_id: int = None, sparziel_id: int = None) -> None:
    """
    Ändert eine bestehende Buchung. Vorzeichen wird wie beim Anlegen aus
    dem Kategorie-Typ abgeleitet, Übertragungen bekommen weiterhin
    zwingend die Kategorie 'Umbuchung' und einen Betrag ohne Vorzeichen.
    """
    if typ not in ("Ist", "Plan", "Uebertragung"):
        raise ValueError(f"Unbekannter Buchungstyp: {typ}")
    if typ == "Uebertragung":
        if not zielkonto_id:
            raise ValueError("Bei Übertragungen ist ein Zielkonto Pflicht.")
        kategorie_id = umbuchung_kategorie_id(conn)
        betrag = abs(betrag)
    else:
        zielkonto_id = None
        betrag = vorzeichen_anwenden(conn, kategorie_id, betrag)

    conn.execute(
        """UPDATE buchungen SET konto_id = ?, zielkonto_id = ?, sparziel_id = ?, datum = ?,
           betrag = ?, kategorie_id = ?, typ = ?, beschreibung = ? WHERE id = ?""",
        (konto_id, zielkonto_id, sparziel_id, _iso(datum), betrag, kategorie_id, typ,
         beschreibung, buchung_id),
    )
    conn.commit()


# ─── Automatische Kategorisierung ───────────────────────────────────

def kategorie_vorschlagen(conn, beschreibung: str) -> Optional[int]:
    """
    Sucht die erste passende Textregel (nach Priorität) für eine
    Beschreibung und liefert die zugehörige Kategorie. Reine
    Teilstring-Suche, Groß-/Kleinschreibung wird ignoriert.
    """
    if not beschreibung:
        return None
    text = beschreibung.lower()
    for r in conn.execute(
        "SELECT muster, kategorie_id FROM kategorie_regeln WHERE aktiv = 1 ORDER BY prioritaet, id"
    ).fetchall():
        if r["muster"] and r["muster"].lower() in text:
            return r["kategorie_id"]
    return None


def regel_anlegen(conn, muster: str, kategorie_id: int, prioritaet: int = 100) -> int:
    cur = conn.execute(
        "INSERT INTO kategorie_regeln (muster, kategorie_id, prioritaet) VALUES (?, ?, ?)",
        (muster, kategorie_id, prioritaet),
    )
    conn.commit()
    return cur.lastrowid


def regeln_liste(conn):
    return conn.execute(
        """SELECT r.*, k.name AS kategorie_name FROM kategorie_regeln r
           LEFT JOIN kategorien k ON k.id = r.kategorie_id
           ORDER BY r.prioritaet, r.id"""
    ).fetchall()


def regel_loeschen(conn, regel_id: int) -> None:
    conn.execute("DELETE FROM kategorie_regeln WHERE id = ?", (regel_id,))
    conn.commit()


# ─── Duplikat-Prüfung ───────────────────────────────────────────────

def moegliches_duplikat(conn, konto_id: int, datum: date, betrag: float,
                         ausser_id: Optional[int] = None) -> Optional[dict]:
    """
    Sucht eine bereits vorhandene Buchung am selben Tag, auf demselben
    Konto, mit demselben Betrag. Reiner Hinweis - kein Hard-Block, da
    doppelte Beträge am selben Tag durchaus legitim sein können.
    """
    sql = """SELECT id, beschreibung, betrag, datum FROM buchungen
             WHERE konto_id = ? AND datum = ? AND ABS(ABS(betrag) - ?) < 0.005"""
    params = [konto_id, _iso(datum), abs(betrag)]
    if ausser_id is not None:
        sql += " AND id != ?"
        params.append(ausser_id)
    row = conn.execute(sql + " LIMIT 1", params).fetchone()
    return dict(row) if row else None

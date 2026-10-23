"""
Daten zurücksetzen (Administration, seit v1.8).

Löscht ausgewählte Datenarten dauerhaft. Absicherung in drei Stufen:
  1. Vorschau: Anzahl je Datenart wird angezeigt (Schritt 1 im Dialog).
  2. Zufällige Bestätigungsphrase: wird serverseitig erzeugt, ist an genau
     diese Auswahl gebunden, nur begrenzt gültig und einmalig verwendbar -
     eine Prüfung allein im Browser wäre umgehbar.
  3. Vor dem Löschen wird automatisch ein Backup mit Beschreibung
     ("vor Löschung von ...") angelegt (siehe backup.backup_erstellen).

Datenarten (Schlüssel -> Wirkung):
  konten_leeren    Alle Buchungen (Ist, Plan, Übertragungen) und Saldo-
                   Korrekturen der gewählten Konten; die Konten bleiben.
  konten_loeschen  Gewählte Konten werden entfernt. Teilauswahl: alles, was
                   an ihnen hängt (Buchungen, Vorlagen inkl. Zielkonto von
                   Umbuchungs-Vorlagen - seit v1.10; würden Quell- und Zielkonto
                   gleich, wird die Vorlage deaktiviert -, Altersvorsorge,
                   Darlehens-Zahlungskonto, Sparziel-Trägerkonto), wird auf
                   ein Zielkonto umgestellt. Saldo-Korrekturen der gelöschten
                   Konten werden NICHT übernommen (bewusst, v1.8) - die Summe der
                   Kontostände kann sich dadurch ändern; die Vorschau beziffert
                   die Änderung. Alle Konten: sämtliche Buchungen werden
                   mitgelöscht.
  ist_buchungen    Alle Ist-Buchungen bis einschließlich eines Stichtags (Standard
                   heute, auch automatisch erzeugte) sowie alle Übertragungen
                   bis zu diesem Datum - Übertragungen wirken auf beide Konten.
  plan_buchungen   Alle Plan-Buchungen, seit v1.10 zusätzlich per "Anpassen"
                   verschobene Übertragungen (aus Umbuchungs-Vorlagen) mit
                   künftigem Datum - sie behalten beim Anpassen ihren Typ.
  darlehen         Alle Darlehen samt Auszahlungen; Buchungen bleiben und
                   werden vom Darlehen gelöst.
  altersvorsorge   Alle Verträge; Buchungen bleiben und werden gelöst.
  wiederkehrend    Alle Vorlagen; Buchungen bleiben und werden gelöst.

Gelöschte automatische Ist-Buchungen entstehen NICHT neu: Vorlagen,
Darlehen und Altersvorsorge-Verträge merken sich seit v1.8, bis wann sie
bereits gebucht haben (erzeugt_bis, siehe wiederkehrend.py). Bestehen die
Quellen weiter, buchen sie aber künftige Termine wie gewohnt - darauf weist
die Vorschau bei "Konten leeren" hin.

Plan-Buchungen-Protokoll: Einträge, deren Buchung gelöscht wurde, werden
mit entfernt (außer Einträgen mit Status "geloescht", die per Definition
auf eine nicht mehr vorhandene Buchung verweisen).
"""
import hashlib
import hmac
import json
import secrets
import time
from datetime import date
from typing import Optional

from . import buchungen as buchungen_modul
from . import zeit

# Reihenfolge = Ausführungsreihenfolge. Konten löschen steht zuletzt, damit
# Buchungen, Vorlagen und Verträge vorher bereits bereinigt sind.
AUSFUEHRUNGS_REIHENFOLGE = [
    "ist_buchungen", "plan_buchungen", "konten_leeren",
    "wiederkehrend", "altersvorsorge", "darlehen", "konten_loeschen",
]

BEZEICHNUNG = {
    "konten_leeren": "Konten leeren",
    "konten_loeschen": "Konten löschen",
    "ist_buchungen": "Ist-Buchungen",
    "plan_buchungen": "Plan-Buchungen",
    "darlehen": "Darlehen",
    "altersvorsorge": "Altersvorsorge",
    "wiederkehrend": "Wiederkehrende Buchungen",
}

_PHRASEN_WOERTER = [
    "birke", "falke", "granit", "kupfer", "nebel", "tulpe", "anker", "lawine",
    "marmor", "wacholder", "sturm", "kiesel", "fichte", "bernstein", "delfin",
    "kastanie", "orkan", "topas", "zeder", "amsel", "wiese", "leuchtturm",
    "pergament", "rauch", "schiefer", "quelle", "hafen", "distel",
]
_TOKEN_GUELTIG_SEKUNDEN = 600
_MAX_FEHLVERSUCHE = 5
_TOKENS: dict[str, dict] = {}


class ZuruecksetzenFehler(ValueError):
    """Fachlicher Fehler (ungültige Auswahl, blockierte Kombination, falsche Phrase)."""


# ─── Hilfsfunktionen ─────────────────────────────────────────────────

def _platzhalter(ids) -> str:
    return ",".join("?" * len(ids))


def _zahl(conn, sql: str, params=()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def _id_menge(conn, sql: str, params=()) -> set[int]:
    return {r[0] for r in conn.execute(sql, params).fetchall()}


def _plan_ids(conn) -> set[int]:
    """Plan-Buchungen plus per "Anpassen" verschobene Übertragungen mit
    künftigem Datum (seit v1.10, siehe plan_buchungen.ablehnen_anpassen)."""
    return _id_menge(conn, "SELECT id FROM buchungen WHERE typ = 'Plan'") | _angepasste_uebertragungen(conn)


def _angepasste_uebertragungen(conn) -> set[int]:
    return _id_menge(
        conn,
        """SELECT id FROM buchungen WHERE typ = 'Uebertragung' AND datum > ?
             AND id IN (SELECT buchung_id FROM plan_buchung_protokoll WHERE status = 'angepasst')""",
        (zeit.heute().isoformat(),))


def uebersicht(conn) -> dict:
    """Aktuelle Gesamtanzahlen je Datenart (für die Anzeige neben der Auswahl)."""
    return {
        "konten": _zahl(conn, "SELECT COUNT(*) FROM konten"),
        "ist_buchungen": _zahl(conn, "SELECT COUNT(*) FROM buchungen WHERE typ = 'Ist'"),
        "plan_buchungen": len(_plan_ids(conn)),
        "buchungen_gesamt": _zahl(conn, "SELECT COUNT(*) FROM buchungen"),
        "darlehen": _zahl(conn, "SELECT COUNT(*) FROM darlehen"),
        "altersvorsorge": _zahl(conn, "SELECT COUNT(*) FROM altersvorsorge"),
        "wiederkehrend": _zahl(conn, "SELECT COUNT(*) FROM wiederkehrende_buchungen"),
    }


# ─── Auswahl prüfen und normalisieren ────────────────────────────────

def normalisieren(conn, auswahl: dict) -> dict:
    """
    Prüft die Roh-Auswahl aus der Oberfläche und liefert eine
    kanonische Form: {"arten": [...], "leeren": [ids], "loeschen": [ids],
    "ziel": id|None}. Wirft ZuruecksetzenFehler bei ungültiger Auswahl.
    """
    gewaehlt = set(auswahl.get("arten") or [])
    unbekannt = gewaehlt - set(BEZEICHNUNG)
    if unbekannt:
        raise ZuruecksetzenFehler(f"Unbekannte Datenart: {', '.join(sorted(unbekannt))}")
    arten = [a for a in AUSFUEHRUNGS_REIHENFOLGE if a in gewaehlt]
    if not arten:
        raise ZuruecksetzenFehler("Es ist keine Datenart ausgewählt.")

    vorhanden = _id_menge(conn, "SELECT id FROM konten")

    def konto_ids(schluessel: str, art: str) -> list[int]:
        if art not in arten:
            return []
        ids = sorted({int(i) for i in (auswahl.get(schluessel) or [])})
        if not ids:
            raise ZuruecksetzenFehler(f"Für „{BEZEICHNUNG[art]}“ ist kein Konto ausgewählt.")
        if set(ids) - vorhanden:
            raise ZuruecksetzenFehler("Ein ausgewähltes Konto existiert nicht (mehr). Bitte Seite neu laden.")
        return ids

    leeren = konto_ids("konten_leeren_ids", "konten_leeren")
    loeschen = konto_ids("konten_loeschen_ids", "konten_loeschen")

    ziel = auswahl.get("ziel_konto_id")
    ziel = int(ziel) if ziel not in (None, "", 0) else None

    ist_bis = None
    if "ist_buchungen" in arten:
        try:
            ist_bis = date.fromisoformat(str(auswahl.get("ist_bis") or zeit.heute().isoformat())).isoformat()
        except ValueError:
            raise ZuruecksetzenFehler("Ungültiges Datum für „Ist-Buchungen bis einschließlich“.")
    return {"arten": arten, "leeren": leeren, "loeschen": loeschen, "ziel": ziel, "ist_bis": ist_bis}


def _datum_de(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


def _euro_de(betrag: float) -> str:
    text = f"{betrag:+,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def _alle_konten_modus(conn, norm: dict) -> bool:
    return bool(norm["loeschen"]) and set(norm["loeschen"]) == _id_menge(conn, "SELECT id FROM konten")


# ─── Vorschau ────────────────────────────────────────────────────────

def vorschau(conn, norm: dict) -> dict:
    """
    Zählt je gewählter Datenart, was gelöscht bzw. verändert würde, und
    meldet blockierende Probleme. Verändert nichts. Die Anzahlen gelten je
    Datenart einzeln; überschneiden sich Auswahlen (z. B. Ist-Buchungen und
    Konten leeren), wird eine Buchung trotzdem nur einmal gelöscht - das
    zeigt die Zeile "Buchungen insgesamt" ohne Doppelzählung.
    """
    arten = norm["arten"]
    zeilen: list[dict] = []
    warnungen: list[str] = []
    blockiert: list[str] = []
    buchungs_ids: set[int] = set()
    ziel_erforderlich = False
    ziel_kandidaten: list[dict] = []
    alle_konten = _alle_konten_modus(conn, norm)

    for art in arten:
        if art == "ist_buchungen":
            bis = norm["ist_bis"]
            ids = _id_menge(conn, "SELECT id FROM buchungen WHERE typ = 'Ist' AND datum <= ?", (bis,))
            uebertragungen = _id_menge(
                conn, "SELECT id FROM buchungen WHERE typ = 'Uebertragung' AND datum <= ?", (bis,))
            buchungs_ids |= ids | uebertragungen
            zeile = {"art": art, "titel": f"{BEZEICHNUNG[art]} bis einschließlich {_datum_de(bis)}",
                     "anzahl": len(ids), "einheit": "Buchungen",
                     "zusatz": [{"label": "Übertragungen bis zu diesem Datum (werden mitgelöscht)",
                                 "anzahl": len(uebertragungen)}]}
            if uebertragungen:
                warnungen.append(
                    f"Mit den Ist-Buchungen werden auch {len(uebertragungen)} Übertragungen bis einschließlich "
                    f"{_datum_de(bis)} gelöscht. Eine Übertragung wirkt auf beide beteiligten Konten - "
                    "Quell- und Zielkonto ändern dadurch ihren Saldo.")
            zeilen.append(zeile)

        elif art == "plan_buchungen":
            ids = _plan_ids(conn)
            angepasst = _angepasste_uebertragungen(conn)
            buchungs_ids |= ids
            zusatz = []
            if angepasst:
                zusatz.append({"label": "davon per „Anpassen“ verschobene Übertragungen mit künftigem Datum",
                               "anzahl": len(angepasst)})
            zeilen.append({"art": art, "titel": BEZEICHNUNG[art], "anzahl": len(ids),
                           "einheit": "Buchungen", "zusatz": zusatz})

        elif art == "konten_leeren":
            ids = norm["leeren"]
            ph = _platzhalter(ids)
            b = _id_menge(conn, f"SELECT id FROM buchungen WHERE konto_id IN ({ph}) OR zielkonto_id IN ({ph})",
                          (*ids, *ids))
            buchungs_ids |= b
            korrekturen = _zahl(conn, f"SELECT COUNT(*) FROM saldo_korrekturen WHERE konto_id IN ({ph})", ids)
            uebertragungen_fremd = _zahl(
                conn,
                f"""SELECT COUNT(*) FROM buchungen WHERE typ = 'Uebertragung' AND
                    ((konto_id IN ({ph}) AND zielkonto_id NOT IN ({ph}))
                     OR (zielkonto_id IN ({ph}) AND konto_id NOT IN ({ph})))""",
                (*ids, *ids, *ids, *ids))
            zusatz = [{"label": "Buchungen (Ist, Plan, Übertragungen)", "anzahl": len(b)},
                      {"label": "Saldo-Korrekturen", "anzahl": korrekturen}]
            if uebertragungen_fremd:
                zusatz.append({"label": "davon Übertragungen zu/von nicht gewählten Konten "
                                        "(ändern dort den Saldo)", "anzahl": uebertragungen_fremd})
            quellen = _verbleibende_quellen(conn, arten, ids)
            if quellen:
                warnungen.append(
                    f"An den geleerten Konten hängen noch {quellen}. Bereits gelöschte Buchungen entstehen "
                    "nicht neu, künftige Termine werden aber weiterhin gebucht - die Konten stehen nur bis "
                    "zum nächsten fälligen Termin auf 0 €. Soll das nicht passieren, die jeweilige Datenart "
                    "zusätzlich löschen.")
            zeilen.append({"art": art, "titel": BEZEICHNUNG[art], "anzahl": len(ids),
                           "einheit": "Konten", "zusatz": zusatz,
                           "namen": _konto_namen(conn, ids)})

        elif art == "wiederkehrend":
            gebunden = _zahl(conn, "SELECT COUNT(*) FROM buchungen WHERE wiederkehrend_id IS NOT NULL")
            zeilen.append({"art": art, "titel": BEZEICHNUNG[art],
                           "anzahl": _zahl(conn, "SELECT COUNT(*) FROM wiederkehrende_buchungen"),
                           "einheit": "Vorlagen",
                           "zusatz": [{"label": "Buchungen werden von der Vorlage gelöst (bleiben bestehen)",
                                       "anzahl": gebunden}]})

        elif art == "altersvorsorge":
            gebunden = _zahl(conn, "SELECT COUNT(*) FROM buchungen WHERE ziel_altersvorsorge_id IS NOT NULL")
            zeilen.append({"art": art, "titel": BEZEICHNUNG[art],
                           "anzahl": _zahl(conn, "SELECT COUNT(*) FROM altersvorsorge"),
                           "einheit": "Verträge",
                           "zusatz": [{"label": "Buchungen werden vom Vertrag gelöst (bleiben bestehen)",
                                       "anzahl": gebunden}]})

        elif art == "darlehen":
            gebunden = _zahl(conn, "SELECT COUNT(*) FROM buchungen WHERE ziel_darlehen_id IS NOT NULL")
            zeilen.append({"art": art, "titel": BEZEICHNUNG[art],
                           "anzahl": _zahl(conn, "SELECT COUNT(*) FROM darlehen"),
                           "einheit": "Darlehen",
                           "zusatz": [{"label": "Auszahlungen (werden mitgelöscht)",
                                       "anzahl": _zahl(conn, "SELECT COUNT(*) FROM darlehen_auszahlungen")},
                                      {"label": "Buchungen werden vom Darlehen gelöst (bleiben bestehen)",
                                       "anzahl": gebunden}]})

        elif art == "konten_loeschen":
            ids = norm["loeschen"]
            ph = _platzhalter(ids)
            korrekturen = _zahl(conn, f"SELECT COUNT(*) FROM saldo_korrekturen WHERE konto_id IN ({ph})", ids)
            namen = _konto_namen(conn, ids)
            if alle_konten:
                alle = _id_menge(conn, "SELECT id FROM buchungen")
                buchungs_ids |= alle
                zusatz = [{"label": "Buchungen werden mitgelöscht (Ist, Plan, Übertragungen)", "anzahl": len(alle)},
                          {"label": "Saldo-Korrekturen", "anzahl": korrekturen},
                          {"label": "Darlehen verlieren ihr Zahlungskonto",
                           "anzahl": _zahl(conn, "SELECT COUNT(*) FROM darlehen WHERE zahlungskonto_id IS NOT NULL")},
                          {"label": "Sparziele verlieren ihr Trägerkonto",
                           "anzahl": _zahl(conn, "SELECT COUNT(*) FROM budgets WHERE konto_id IS NOT NULL")}]
                warnungen.append(
                    "ACHTUNG: Es werden ALLE Konten gelöscht. Damit werden auch ALLE zugehörigen "
                    "Buchungen (Ist, Plan, Übertragungen) und Saldo-Korrekturen unwiderruflich gelöscht.")
                for tabelle, art_key, text in (
                        ("wiederkehrende_buchungen", "wiederkehrend", "wiederkehrende Vorlagen"),
                        ("altersvorsorge", "altersvorsorge", "Altersvorsorge-Verträge")):
                    n = _zahl(conn, f"SELECT COUNT(*) FROM {tabelle}")
                    if n and art_key not in arten:
                        blockiert.append(
                            f"Es existieren noch {text} (Anzahl: {n}). Sie benötigen zwingend ein Konto und "
                            f"müssen beim Löschen aller Konten mitgelöscht werden. Bitte „{BEZEICHNUNG[art_key]}“ "
                            "ebenfalls auswählen.")
            else:
                ziel_erforderlich = True
                ziel_kandidaten = [
                    {"id": r["id"], "name": r["name"], "aktiv": bool(r["aktiv"])}
                    for r in conn.execute(
                        f"SELECT id, name, aktiv FROM konten WHERE id NOT IN ({ph}) ORDER BY aktiv DESC, name",
                        ids).fetchall()]
                ziel = norm["ziel"]
                if ziel is not None and ziel not in {k["id"] for k in ziel_kandidaten}:
                    blockiert.append("Das Zielkonto ist ungültig oder gehört selbst zu den gelöschten Konten.")
                    ziel = None
                betroffen = _id_menge(conn, f"SELECT id FROM buchungen WHERE konto_id IN ({ph}) OR zielkonto_id IN ({ph})",
                                      (*ids, *ids))
                zusatz = [{"label": "Buchungen werden auf das Zielkonto umgebucht", "anzahl": len(betroffen)}]
                if ziel is not None:
                    selbst = _selbst_uebertragungen(conn, ids, ziel)
                    zusatz[0]["anzahl"] = len(betroffen) - len(selbst)
                    buchungs_ids |= selbst
                    zusatz.append({"label": "Übertragungen entfallen (würden Quell- und Zielkonto "
                                            "gleichsetzen)", "anzahl": len(selbst)})
                    deaktiv = _umbuchungen_deaktiviert(conn, ids, ziel)
                    if deaktiv:
                        zusatz.append({"label": "Umbuchungs-Vorlagen werden deaktiviert (Quell- und Zielkonto "
                                                "wären gleich, nicht gelöscht)", "anzahl": deaktiv})
                        warnungen.append(
                            f"{deaktiv} aktive Umbuchungs-Vorlage(n) würden nach dem Umstellen vom Zielkonto auf "
                            "sich selbst umbuchen. Sie werden deaktiviert, nicht gelöscht.")
                    differenz = _saldo_auswirkung(conn, ids, ziel)
                    if abs(differenz) >= 0.005:
                        warnungen.append(
                            "Die Summe der Kontostände von Zielkonto und gelöschten Konten ändert sich durch "
                            f"die Zusammenführung um {_euro_de(differenz)}. Ursache: Saldo-Korrekturen der "
                            "gelöschten Konten werden nicht übernommen, und umgebuchte Buchungen, die vor der "
                            "jüngsten Saldo-Korrektur des Zielkontos liegen, zählen dort nicht mit.")
                zusatz += [
                    {"label": "Saldo-Korrekturen (werden gelöscht, nicht übertragen)", "anzahl": korrekturen},
                    {"label": "Wiederkehrende Vorlagen werden umgestellt (Konto oder Zielkonto)",
                     "anzahl": _zahl(conn, f"SELECT COUNT(*) FROM wiederkehrende_buchungen "
                                           f"WHERE konto_id IN ({ph}) OR zielkonto_id IN ({ph})", (*ids, *ids))},
                    {"label": "Altersvorsorge-Verträge werden umgestellt",
                     "anzahl": _zahl(conn, f"SELECT COUNT(*) FROM altersvorsorge WHERE zahlungskonto_id IN ({ph})", ids)},
                    {"label": "Darlehen (Zahlungskonto) werden umgestellt",
                     "anzahl": _zahl(conn, f"SELECT COUNT(*) FROM darlehen WHERE zahlungskonto_id IN ({ph})", ids)},
                    {"label": "Sparziele (Trägerkonto) werden umgestellt",
                     "anzahl": _zahl(conn, f"SELECT COUNT(*) FROM budgets WHERE konto_id IN ({ph})", ids)},
                ]
            zeilen.append({"art": art, "titel": BEZEICHNUNG[art], "anzahl": len(ids),
                           "einheit": "Konten", "zusatz": zusatz, "namen": namen})

    gesamt = None
    if any(a in arten for a in ("ist_buchungen", "plan_buchungen", "konten_leeren")) or alle_konten \
            or "konten_loeschen" in arten:
        gesamt = len(buchungs_ids)

    ziel_fehlt = ziel_erforderlich and norm["ziel"] is None
    bereit = not blockiert and not ziel_fehlt
    return {
        "zeilen": zeilen, "buchungen_geloescht_gesamt": gesamt, "warnungen": warnungen,
        "blockiert": blockiert, "alle_konten": alle_konten,
        "ziel_erforderlich": ziel_erforderlich, "ziel_kandidaten": ziel_kandidaten,
        "bereit": bereit, "backup_beschreibung": backup_beschreibung(conn, norm),
    }


def _konto_namen(conn, ids) -> list[str]:
    return [r["name"] for r in conn.execute(
        f"SELECT name FROM konten WHERE id IN ({_platzhalter(ids)}) ORDER BY name", list(ids)).fetchall()]


def _selbst_uebertragungen(conn, ids, ziel: int) -> set[int]:
    """Übertragungen, die nach dem Umstellen auf das Zielkonto von A nach A
    gingen (beide Seiten gehören zu gelöschten Konten bzw. dem Zielkonto)."""
    ph = _platzhalter(ids)
    return _id_menge(
        conn,
        f"""SELECT id FROM buchungen
            WHERE typ = 'Uebertragung' AND zielkonto_id IS NOT NULL
              AND (konto_id IN ({ph}) OR zielkonto_id IN ({ph}))
              AND (CASE WHEN konto_id IN ({ph}) THEN ? ELSE konto_id END)
                = (CASE WHEN zielkonto_id IN ({ph}) THEN ? ELSE zielkonto_id END)""",
        (*ids, *ids, *ids, ziel, *ids, ziel))


def _umbuchungen_deaktiviert(conn, ids, ziel: int) -> int:
    """Aktive Umbuchungs-Vorlagen, deren Quell- und Zielkonto nach dem
    Umstellen auf `ziel` gleich wären (seit v1.10)."""
    ph = _platzhalter(ids)
    return _zahl(
        conn,
        f"""SELECT COUNT(*) FROM wiederkehrende_buchungen
            WHERE aktiv = 1 AND zielkonto_id IS NOT NULL
              AND (konto_id IN ({ph}) OR zielkonto_id IN ({ph}))
              AND (CASE WHEN konto_id IN ({ph}) THEN ? ELSE konto_id END)
                = (CASE WHEN zielkonto_id IN ({ph}) THEN ? ELSE zielkonto_id END)""",
        (*ids, *ids, *ids, ziel, *ids, ziel))


def _verbleibende_quellen(conn, arten: list[str], konto_ids) -> str:
    """Textliche Aufzählung der Vorlagen/Darlehen/Verträge, die an den Konten
    hängen und nicht mitgelöscht werden ("" wenn keine)."""
    ph = _platzhalter(konto_ids)
    teile = []
    for art, sql, einzahl, mehrzahl in (
            ("wiederkehrend", f"SELECT COUNT(*) FROM wiederkehrende_buchungen WHERE aktiv = 1 "
                              f"AND (konto_id IN ({ph}) OR zielkonto_id IN ({ph}))",
             "aktive wiederkehrende Vorlage", "aktive wiederkehrende Vorlagen"),
            ("darlehen", f"SELECT COUNT(*) FROM darlehen WHERE zahlungskonto_id IN ({ph})",
             "Darlehen", "Darlehen"),
            ("altersvorsorge", f"SELECT COUNT(*) FROM altersvorsorge WHERE aktiv = 1 AND zahlungskonto_id IN ({ph})",
             "aktiver Altersvorsorge-Vertrag", "aktive Altersvorsorge-Verträge")):
        if art not in arten:
            n = _zahl(conn, sql, [*konto_ids] * sql.count(f"IN ({ph})"))
            if n:
                teile.append(f"{n} {einzahl if n == 1 else mehrzahl}")
    return ", ".join(teile)


def _saldo_auswirkung(conn, ids, ziel: int) -> float:
    """Simuliert die Zusammenführung in einem Savepoint und liefert die
    Änderung der Summe der Kontostände (Zielkonto + gelöschte Konten)."""
    vorher = sum(buchungen_modul.saldo(conn, k) for k in [*ids, ziel])
    conn.execute("SAVEPOINT zuruecksetzen_simulation")
    try:
        _konten_umstellen(conn, ids, ziel)
        nachher = buchungen_modul.saldo(conn, ziel)
    finally:
        conn.execute("ROLLBACK TO zuruecksetzen_simulation")
        conn.execute("RELEASE zuruecksetzen_simulation")
    return round(nachher - vorher, 2)


def backup_beschreibung(conn, norm: dict) -> str:
    teile = []
    for art in norm["arten"]:
        text = BEZEICHNUNG[art]
        if art == "ist_buchungen":
            text += f" bis {_datum_de(norm['ist_bis'])} inkl. Übertragungen"
        elif art == "konten_leeren":
            text += f" ({', '.join(_konto_namen(conn, norm['leeren']))})"
        elif art == "konten_loeschen":
            text += f" ({', '.join(_konto_namen(conn, norm['loeschen']))})"
        teile.append(text)
    return "vor Löschung von: " + ", ".join(teile)


# ─── Bestätigungsphrase (serverseitig, einmalig) ─────────────────────

def _auswahl_hash(norm: dict) -> str:
    return hashlib.sha256(json.dumps(norm, sort_keys=True).encode()).hexdigest()


def phrase_ausstellen(norm: dict) -> tuple[str, str]:
    """Erzeugt (token, phrase) - die Phrase wechselt bei jedem Aufruf."""
    jetzt = time.time()
    for t in [t for t, v in _TOKENS.items() if v["bis"] < jetzt]:
        del _TOKENS[t]
    phrase = f"{secrets.choice(_PHRASEN_WOERTER)}-{secrets.choice(_PHRASEN_WOERTER)}-{secrets.randbelow(900) + 100}"
    token = secrets.token_urlsafe(16)
    _TOKENS[token] = {"hash": _auswahl_hash(norm), "phrase": phrase,
                      "bis": jetzt + _TOKEN_GUELTIG_SEKUNDEN, "fehlversuche": 0}
    return token, phrase


def phrase_pruefen(token: Optional[str], phrase: Optional[str], norm: dict) -> None:
    eintrag = _TOKENS.get(token or "")
    if eintrag is None or eintrag["bis"] < time.time():
        _TOKENS.pop(token or "", None)
        raise ZuruecksetzenFehler("Die Bestätigung ist abgelaufen. Bitte den Vorgang neu starten.")
    if not hmac.compare_digest(eintrag["hash"], _auswahl_hash(norm)):
        raise ZuruecksetzenFehler("Die Auswahl hat sich seit der Bestätigung geändert. Bitte neu starten.")
    if not hmac.compare_digest((phrase or "").strip().lower(), eintrag["phrase"]):
        eintrag["fehlversuche"] += 1
        if eintrag["fehlversuche"] >= _MAX_FEHLVERSUCHE:
            _TOKENS.pop(token, None)
            raise ZuruecksetzenFehler("Zu viele falsche Eingaben. Bitte den Vorgang neu starten.")
        raise ZuruecksetzenFehler("Die eingegebene Phrase stimmt nicht.")
    del _TOKENS[token]  # einmalig verwendbar


# ─── Ausführen ───────────────────────────────────────────────────────

def ausfuehren(conn, norm: dict) -> dict:
    """
    Führt das Löschen in EINER Transaktion aus (alles oder nichts). Das
    Backup muss der Aufrufer vorher erstellt haben. Gibt die Vorschau-
    Zahlen zurück, die unmittelbar vor dem Löschen ermittelt wurden.
    """
    info = vorschau(conn, norm)
    if not info["bereit"]:
        raise ZuruecksetzenFehler(" ".join(info["blockiert"]) or "Es ist noch ein Zielkonto zu wählen.")

    arten = norm["arten"]
    try:
        if "ist_buchungen" in arten:
            conn.execute("DELETE FROM buchungen WHERE typ IN ('Ist', 'Uebertragung') AND datum <= ?",
                         (norm["ist_bis"],))
        if "plan_buchungen" in arten:
            plan = _plan_ids(conn)
            if plan:
                conn.execute(f"DELETE FROM buchungen WHERE id IN ({_platzhalter(plan)})", list(plan))
        if "konten_leeren" in arten:
            ids = norm["leeren"]
            ph = _platzhalter(ids)
            conn.execute(f"DELETE FROM buchungen WHERE konto_id IN ({ph}) OR zielkonto_id IN ({ph})", (*ids, *ids))
            conn.execute(f"DELETE FROM saldo_korrekturen WHERE konto_id IN ({ph})", ids)
        if "wiederkehrend" in arten:
            conn.execute("UPDATE buchungen SET wiederkehrend_id = NULL WHERE wiederkehrend_id IS NOT NULL")
            conn.execute("DELETE FROM wiederkehrende_buchungen")
        if "altersvorsorge" in arten:
            conn.execute("UPDATE buchungen SET ziel_altersvorsorge_id = NULL WHERE ziel_altersvorsorge_id IS NOT NULL")
            conn.execute("DELETE FROM altersvorsorge")
        if "darlehen" in arten:
            conn.execute("UPDATE buchungen SET ziel_darlehen_id = NULL WHERE ziel_darlehen_id IS NOT NULL")
            conn.execute("UPDATE wiederkehrende_buchungen SET darlehen_id = NULL WHERE darlehen_id IS NOT NULL")
            conn.execute("DELETE FROM darlehen_auszahlungen")
            conn.execute("DELETE FROM darlehen")
        if "konten_loeschen" in arten:
            _konten_loeschen(conn, norm, info["alle_konten"])
        if any(a in arten for a in ("ist_buchungen", "plan_buchungen", "konten_leeren", "konten_loeschen")):
            # Protokolleinträge ohne Buchung wären leere Zeilen; "geloescht"-
            # Einträge verweisen schon immer auf nicht mehr vorhandene Buchungen.
            conn.execute("""DELETE FROM plan_buchung_protokoll
                            WHERE status != 'geloescht' AND buchung_id NOT IN (SELECT id FROM buchungen)""")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return info


def _konten_loeschen(conn, norm: dict, alle_konten: bool) -> None:
    ids = norm["loeschen"]
    ph = _platzhalter(ids)
    if alle_konten:
        for tabelle, text in (("wiederkehrende_buchungen", "Vorlagen"), ("altersvorsorge", "Altersvorsorge-Verträge")):
            if _zahl(conn, f"SELECT COUNT(*) FROM {tabelle}"):
                raise ZuruecksetzenFehler(f"Es existieren noch {text}, die ein Konto benötigen.")
        conn.execute("DELETE FROM buchungen")
        conn.execute("DELETE FROM saldo_korrekturen")
        conn.execute("UPDATE darlehen SET zahlungskonto_id = NULL")
        conn.execute("UPDATE budgets SET konto_id = NULL")
        conn.execute("DELETE FROM konten")
        conn.execute("UPDATE einstellungen SET value = '' WHERE key = 'siri_standardkonto'")
        return

    _konten_umstellen(conn, ids, norm["ziel"])


def _konten_umstellen(conn, ids, ziel: int) -> None:
    """Teilauswahl: alles von den Konten `ids` auf `ziel` umstellen und die
    Konten löschen. Auch von der Vorschau (in einem Savepoint) genutzt."""
    ph = _platzhalter(ids)
    # Reihenfolge wichtig: erst Selbst-Übertragungen entfernen (solange die
    # alten Konto-IDs noch an den Zeilen hängen), dann umstellen.
    selbst = _selbst_uebertragungen(conn, ids, ziel)
    if selbst:
        conn.execute(f"DELETE FROM buchungen WHERE id IN ({_platzhalter(selbst)})", list(selbst))
    conn.execute(f"UPDATE buchungen SET konto_id = ? WHERE konto_id IN ({ph})", (ziel, *ids))
    conn.execute(f"UPDATE buchungen SET zielkonto_id = ? WHERE zielkonto_id IN ({ph})", (ziel, *ids))
    conn.execute(f"UPDATE wiederkehrende_buchungen SET konto_id = ? WHERE konto_id IN ({ph})", (ziel, *ids))
    # Seit v1.10: Zielkonto der Umbuchungs-Vorlagen; wären Quelle und Ziel
    # danach gleich, wird die Vorlage deaktiviert (nicht gelöscht).
    conn.execute(f"UPDATE wiederkehrende_buchungen SET zielkonto_id = ? WHERE zielkonto_id IN ({ph})", (ziel, *ids))
    conn.execute("UPDATE wiederkehrende_buchungen SET aktiv = 0 WHERE zielkonto_id IS NOT NULL AND zielkonto_id = konto_id")
    conn.execute(f"UPDATE altersvorsorge SET zahlungskonto_id = ? WHERE zahlungskonto_id IN ({ph})", (ziel, *ids))
    conn.execute(f"UPDATE darlehen SET zahlungskonto_id = ? WHERE zahlungskonto_id IN ({ph})", (ziel, *ids))
    conn.execute(f"UPDATE budgets SET konto_id = ? WHERE konto_id IN ({ph})", (ziel, *ids))
    conn.execute(f"DELETE FROM saldo_korrekturen WHERE konto_id IN ({ph})", ids)
    conn.execute(f"DELETE FROM konten WHERE id IN ({ph})", ids)
    # Standardkonto der Siri-Schnellbuchung (als Text gespeichert)
    conn.execute(
        f"UPDATE einstellungen SET value = ? WHERE key = 'siri_standardkonto' AND value IN ({ph})",
        (str(ziel), *[str(i) for i in ids]))

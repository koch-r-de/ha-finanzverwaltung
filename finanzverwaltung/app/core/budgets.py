"""
Budget-Modul: Perioden, Verbrauch, Ampel, Übertrag, Prognose, Historie
und Sparziele.

Fachliche Festlegungen (aus dem Sparring):
  - Verbrauch wird je AKTUELLER Periode betrachtet und mit jeder neuen
    Periode zurückgesetzt.
  - Ampel wird aus den Warnschwellen abgeleitet: ab der niedrigsten
    Schwelle gelb, ab 100 % rot. Liegt die Schwelle über dem Budget,
    springt die Ampel direkt von grün auf rot.
  - Übertrag: 'letzte'    -> Rest der Vorperiode wird einmalig
                             aufgeschlagen.
              'kumuliert' -> alle Perioden werden fortlaufend
                             zusammengerechnet (Sparschwein-Logik;
                             Überschreitungen werden mitgeschleppt).
  - Prognose: Verfahren B (Ist + noch geplante Buchungen der Periode) als
    Basis, automatischer Wechsel auf D (Fixkosten aus Plan-Buchungen +
    variabler Anteil aus dem Median der Vorperioden), sobald genügend
    Historie vorliegt. Die Schwelle ist über die Einstellung
    'prognose_min_perioden' administrierbar.
  - Sparziel: das SOLL wächst rechnerisch je Periode, das IST kommt aus
    Übertragungen, die dem Sparziel zugeordnet wurden. Das Trägerkonto
    wird gesplittet dargestellt (Kontostand = Sparziele + Rest, wobei der
    Rest negativ werden kann).
  - Übertrag-Deckel (seit v1.6.3): begrenzt einen positiven Übertrag nach
    oben, damit 'kumuliert' bei selten abgerufenen Budgets (z. B. Auto:
    Benzin monatlich, TÜV zweijährlich, unregelmäßige Reparaturen) nicht
    unbegrenzt wächst. Siehe verfuegbarer_betrag().
  - Inflationsfaktor (seit v1.6.3): rechnet den Periodenbetrag mit dem
    globalen Faktor aus den Einstellungen hoch. Siehe verfuegbarer_betrag().
  - Details-Verlauf (seit v1.6.4): eigene, kalendermonatsbasierte Historie
    (unabhängig von der Budget-Periodenlänge) für das Budgets-Details-Tab
    im Frontend - einzelnes Budget oder alle zusammen, siehe
    verlauf_je_monat().
"""
import json
from datetime import date, timedelta
from statistics import median
from typing import Optional

from dateutil.relativedelta import relativedelta
from . import zeit

STANDARD_WARNUNGEN = '[{"schwelle": 80, "typ": "Warnung"}]'


# ─── Perioden ────────────────────────────────────────────────────────

def _periodenlaenge(budget) -> relativedelta | timedelta:
    zeitraum = budget["zeitraum"]
    if zeitraum == "monatlich":
        return relativedelta(months=1)
    if zeitraum == "quartalsweise":
        return relativedelta(months=3)
    if zeitraum == "jaehrlich":
        return relativedelta(years=1)
    wert = budget["intervall_wert"] or 1
    einheit = budget["intervall_einheit"] or "monate"
    if einheit == "tage":
        return timedelta(days=wert)
    if einheit == "wochen":
        return timedelta(weeks=wert)
    return relativedelta(months=wert)


def perioden(budget, bis: date) -> list[tuple[date, date]]:
    """Alle Perioden (von, bis_inklusive) vom Budget-Start bis 'bis'."""
    start = date.fromisoformat(budget["startdatum"])
    ende_budget = date.fromisoformat(budget["enddatum"]) if budget["enddatum"] else None
    laenge = _periodenlaenge(budget)

    ergebnis = []
    von = start
    while von <= bis:
        naechster = von + laenge
        periode_bis = naechster - timedelta(days=1)
        if ende_budget and periode_bis > ende_budget:
            periode_bis = ende_budget
        ergebnis.append((von, periode_bis))
        if ende_budget and naechster > ende_budget:
            break
        von = naechster
        if len(ergebnis) > 1000:  # Schutz gegen Fehlkonfiguration
            break
    return ergebnis


def aktuelle_periode(budget, stichtag: Optional[date] = None) -> Optional[tuple[date, date]]:
    stichtag = stichtag or zeit.heute()
    alle = perioden(budget, stichtag)
    return alle[-1] if alle else None


# ─── Kategorien / Verbrauch ──────────────────────────────────────────

def kategorie_ids(conn, kategorie_id: int, inkl_unterkategorien: bool) -> list[int]:
    """Kategorie plus - falls gewünscht - alle Unterkategorien beliebiger Tiefe."""
    if not inkl_unterkategorien:
        return [kategorie_id]
    ids = [kategorie_id]
    rand = [kategorie_id]
    while rand:
        platzhalter = ",".join("?" * len(rand))
        kinder = [r["id"] for r in conn.execute(
            f"SELECT id FROM kategorien WHERE parent_id IN ({platzhalter})", rand
        ).fetchall()]
        ids += kinder
        rand = kinder
    return ids


def _verbrauch(conn, budget, von: date, bis: date, nur_typ: Optional[str] = "Ist",
               nur_wiederkehrend: Optional[bool] = None) -> float:
    """
    Verbrauch im Zeitraum. Rückgabe immer positiv (also als 'verbrauchter
    Betrag'), unabhängig davon, ob die Buchungen negativ (Ausgabe) oder
    positiv (Einnahme) gespeichert sind. Umbuchungen fließen nicht ein.
    """
    ids = kategorie_ids(conn, budget["kategorie_id"], budget["inkl_unterkategorien"])
    if not ids:
        return 0.0
    platzhalter = ",".join("?" * len(ids))
    bedingungen = [f"kategorie_id IN ({platzhalter})", "datum >= ?", "datum <= ?",
                   "typ != 'Uebertragung'"]
    params = [*ids, von.isoformat(), bis.isoformat()]
    if nur_typ:
        bedingungen.append("typ = ?")
        params.append(nur_typ)
    if nur_wiederkehrend is True:
        bedingungen.append("wiederkehrend_id IS NOT NULL")
    elif nur_wiederkehrend is False:
        bedingungen.append("wiederkehrend_id IS NULL")

    row = conn.execute(
        f"SELECT COALESCE(SUM(ABS(betrag)), 0) FROM buchungen WHERE {' AND '.join(bedingungen)}",
        params,
    ).fetchone()
    return round(row[0], 2)


# ─── Sparziele ───────────────────────────────────────────────────────

def sparziel_stand(conn, budget, stichtag: Optional[date] = None) -> dict:
    """Soll (rechnerisch je Periode) und Ist (zugeordnete Übertragungen)."""
    stichtag = stichtag or zeit.heute()
    abgeschlossen = [p for p in perioden(budget, stichtag)]
    soll = round(budget["betrag"] * len(abgeschlossen), 2)
    if budget["zielbetrag"]:
        soll = min(soll, budget["zielbetrag"])

    # Seit v2.0: nur Übertragungen von/zum Trägerkonto, Entnahmen (Quelle =
    # Trägerkonto) zählen negativ. Bis 1.10 wurde jeder zugeordnete Betrag
    # positiv addiert - eine Entnahme erhöhte den Stand.
    row = conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN zielkonto_id = :t THEN betrag
                                    WHEN konto_id = :t THEN -betrag ELSE 0 END), 0)
           FROM buchungen
           WHERE sparziel_id = :id AND typ = 'Uebertragung' AND datum <= :bis""",
        {"t": budget["konto_id"], "id": budget["id"], "bis": stichtag.isoformat()},
    ).fetchone()
    ist = round(row[0], 2)
    return {"soll": soll, "ist": ist, "differenz": round(ist - soll, 2)}


def konto_aufteilung(conn, konto_id: int, stichtag: Optional[date] = None) -> dict:
    """
    Gesplittete Darstellung eines Kontos: Kontostand = Summe der Sparziele
    + Rest. Der Rest kann negativ werden - dann ist das Konto rechnerisch
    nicht mehr in der Lage, die reservierten Sparziele zu decken.
    """
    from . import buchungen as buchungen_modul

    stichtag = stichtag or zeit.heute()
    kontostand = buchungen_modul.saldo(conn, konto_id, stichtag)
    ziele = []
    summe = 0.0
    for b in conn.execute(
        "SELECT * FROM budgets WHERE typ = 'sparziel' AND konto_id = ? AND aktiv = 1", (konto_id,)
    ).fetchall():
        stand = sparziel_stand(conn, b, stichtag)
        ziele.append({"id": b["id"], "name": b["name"], "ist": stand["ist"],
                      "soll": stand["soll"], "zielbetrag": b["zielbetrag"]})
        summe += stand["ist"]
    return {"kontostand": kontostand, "sparziele": ziele,
            "sparziele_summe": round(summe, 2), "rest": round(kontostand - summe, 2)}


# ─── Ampel ───────────────────────────────────────────────────────────

def warnungen_lesen(budget) -> list[dict]:
    try:
        daten = json.loads(budget["warnungen"] or STANDARD_WARNUNGEN)
        return daten if isinstance(daten, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def ampel(budget, fortschritt_prozent: float) -> str:
    """
    Ampelfarbe aus den Warnschwellen abgeleitet: ab der niedrigsten
    Schwelle gelb, ab 100 % rot. Liegt die niedrigste Schwelle über dem
    Budget, gibt es kein Gelb - dann springt die Ampel direkt von grün
    auf rot.
    """
    if fortschritt_prozent >= 100:
        return "rot"
    schwellen = [w.get("schwelle") for w in warnungen_lesen(budget)
                 if isinstance(w.get("schwelle"), (int, float))]
    relevante = [s for s in schwellen if s < 100]
    if relevante and fortschritt_prozent >= min(relevante):
        return "gelb"
    return "gruen"


def ausgeloeste_warnungen(budget, fortschritt_prozent: float) -> list[dict]:
    return [w for w in warnungen_lesen(budget)
            if isinstance(w.get("schwelle"), (int, float)) and fortschritt_prozent >= w["schwelle"]]


# ─── Übertrag ────────────────────────────────────────────────────────

def verfuegbarer_betrag(conn, budget, stichtag: Optional[date] = None) -> dict:
    """
    Für die aktuelle Periode verfügbarer Betrag, inklusive Übertrag.
      - kein Übertrag : nur der Periodenbetrag
      - 'letzte'      : Periodenbetrag + Rest der unmittelbaren Vorperiode
      - 'kumuliert'   : alle Perioden fortlaufend zusammengerechnet

    Inflationsfaktor (seit v1.6.3): ist budget['inflationsflag'] gesetzt,
    wird der Periodenbetrag (basis) mit Zinseszins seit dem Startdatum bis
    zum Beginn der aktuellen Periode hochgerechnet (globaler Faktor aus
    den Einstellungen, siehe wiederkehrend.betrag_mit_inflation) - der
    Einfachheit halber gilt dieser eine hochgerechnete Betrag einheitlich
    auch für die Übertragsberechnung vergangener Perioden (keine
    rückwirkend unterschiedliche Hochrechnung je Periode).

    Deckel (seit v1.6.3): budget['uebertrag_deckel'] begrenzt einen
    POSITIVEN Übertrag nach oben (Puffer wächst nicht unbegrenzt, wenn
    ein Budget selten abgerufen wird). Ein negativer Übertrag (mitge-
    schleppte Überschreitung bei 'kumuliert') wird nicht gekappt.
    """
    stichtag = stichtag or zeit.heute()
    alle = perioden(budget, stichtag)
    basis = budget["betrag"]
    if alle and budget["inflationsflag"]:
        from . import wiederkehrend as wiederkehrend_modul
        aktuelle_von = alle[-1][0]
        startdatum = date.fromisoformat(budget["startdatum"])
        faktor = wiederkehrend_modul.globaler_inflationsfaktor(conn)
        basis = wiederkehrend_modul.betrag_mit_inflation(basis, aktuelle_von, faktor, heute=startdatum)

    if not alle:
        return {"basis": basis, "uebertrag": 0.0, "verfuegbar": basis}

    if not budget["uebertrag"] or len(alle) < 2:
        return {"basis": basis, "uebertrag": 0.0, "verfuegbar": basis}

    if budget["uebertrag_modus"] == "kumuliert":
        vergangene = alle[:-1]
        verbrauch_vergangen = sum(_verbrauch(conn, budget, v, b) for v, b in vergangene)
        uebertrag = round(basis * len(vergangene) - verbrauch_vergangen, 2)
    else:  # 'letzte'
        vor_von, vor_bis = alle[-2]
        uebertrag = round(basis - _verbrauch(conn, budget, vor_von, vor_bis), 2)

    deckel = budget["uebertrag_deckel"]
    if deckel is not None and uebertrag > deckel:
        uebertrag = round(deckel, 2)

    return {"basis": basis, "uebertrag": uebertrag, "verfuegbar": round(basis + uebertrag, 2)}


# ─── Prognose ────────────────────────────────────────────────────────

def _projizierte_fixkosten(conn, budget, ab: date, bis: date, inflation: bool = False) -> float:
    """
    Summe der noch anstehenden Fixkosten (wiederkehrende Buchungen +
    Darlehensraten) im Zeitraum [ab, bis] - seit v1.10 einschließlich 'ab'
    (Befund F: bis 1.9.1 fiel der Tag nach dem Stichtag heraus) -, die zu den Budget-Kategorien
    gehören - rein rechnerisch, ohne Plan-Buchungen aus der Datenbank
    zu lesen (die gibt es in der neuen Architektur nicht mehr).
    """
    from . import darlehensraten as darlehensraten_modul
    from . import wiederkehrend as wiederkehrend_modul

    if ab > bis:
        return 0.0
    ids = set(kategorie_ids(conn, budget["kategorie_id"], budget["inkl_unterkategorien"]))
    vorher = ab - timedelta(days=1)  # anstehende_* liefern (vorher, bis]
    feiertage = {date.fromisoformat(r["datum"]): r["name"]
                 for r in conn.execute("SELECT datum, name FROM feiertage").fetchall()}

    # Umbuchungs-Vorlagen (seit v1.10) zählen wie echte Übertragungen nicht.
    posten = wiederkehrend_modul.anstehende_termine(conn, feiertage, vorher, bis, inkl_umbuchungen=False,
                                                    inflation=inflation)
    posten += darlehensraten_modul.anstehende_raten(conn, feiertage, vorher, bis)
    return round(sum(abs(p["betrag"]) for p in posten if p["kategorie_id"] in ids), 2)


def prognose(conn, budget, stichtag: Optional[date] = None,
             min_perioden: int = 3, inflation: bool = False) -> dict:
    """
    Verfahren B: Ist-Verbrauch + noch geplante Buchungen der Restperiode.
    Verfahren D: zusätzlich variabler Anteil aus dem Median der
                 Vorperioden (nur nicht-wiederkehrende Buchungen),
                 anteilig auf die Restlaufzeit der Periode.
    D greift automatisch, sobald mindestens 'min_perioden' abgeschlossene
    Perioden vorliegen.
    """
    stichtag = stichtag or zeit.heute()
    periode = aktuelle_periode(budget, stichtag)
    if periode is None:
        return {"verfahren": "-", "erwartet": 0.0, "tage_bis_budget": None}
    von, bis = periode

    ist = _verbrauch(conn, budget, von, bis, nur_typ="Ist")
    # Noch offene Plan-Buchungen in der Restperiode (Fixkosten)
    ab = max(von, stichtag + timedelta(days=1))
    fix_offen = _projizierte_fixkosten(conn, budget, ab, bis, inflation) if ab <= bis else 0.0
    # Seit v1.10 (Befund B): gespeicherte Plan-Buchungen nach heute in der
    # laufenden Periode (manuell erfasst oder per "Anpassen" verschoben).
    if ab <= bis:
        fix_offen = round(fix_offen + _verbrauch(conn, budget, ab, bis, nur_typ="Plan"), 2)

    alle = perioden(budget, stichtag)
    vergangene = alle[:-1]
    verfahren = "B"
    variabel_rest = 0.0

    if len(vergangene) >= max(1, min_perioden):
        verfahren = "D"
        variable_historie = [_verbrauch(conn, budget, v, b, nur_typ="Ist", nur_wiederkehrend=False)
                             for v, b in vergangene[-12:]]
        if variable_historie:
            median_variabel = median(variable_historie)
            tage_gesamt = (bis - von).days + 1
            tage_offen = max(0, (bis - stichtag).days)
            anteil = tage_offen / tage_gesamt if tage_gesamt else 0
            variabel_rest = round(median_variabel * anteil, 2)

    erwartet = round(ist + fix_offen + variabel_rest, 2)

    # "Bei aktuellem Verbrauch erreichen Sie das Budget in X Tagen"
    verfuegbar = verfuegbarer_betrag(conn, budget, stichtag)["verfuegbar"]
    tage_bis_budget = None
    tage_vergangen = max(1, (stichtag - von).days + 1)
    tagesrate = ist / tage_vergangen
    if tagesrate > 0 and ist < verfuegbar:
        tage_bis_budget = int((verfuegbar - ist) / tagesrate)

    return {"verfahren": verfahren, "ist": ist, "fix_offen": fix_offen,
            "variabel_erwartet": variabel_rest, "erwartet": erwartet,
            "tage_bis_budget": tage_bis_budget}


# ─── Historie ────────────────────────────────────────────────────────

def historie(conn, budget, anzahl_perioden: int = 12,
             stichtag: Optional[date] = None) -> dict:
    """Verbrauch der letzten N Perioden (sofern verfügbar) inkl. Min/Max/Median."""
    stichtag = stichtag or zeit.heute()
    alle = perioden(budget, stichtag)
    ausschnitt = alle[-anzahl_perioden:] if anzahl_perioden else alle
    reihen = [{"von": v.isoformat(), "bis": b.isoformat(),
               "verbrauch": _verbrauch(conn, budget, v, b)} for v, b in ausschnitt]
    werte = [r["verbrauch"] for r in reihen]
    return {
        "perioden": reihen,
        "min": round(min(werte), 2) if werte else None,
        "max": round(max(werte), 2) if werte else None,
        "median": round(median(werte), 2) if werte else None,
        "anzahl_perioden": len(reihen),
    }


# ─── Details-Verlauf (kalendermonatsbasiert, seit v1.6.4) ────────────

def verlauf_je_monat(conn, kategorie_ids: list[int], von_monat: date, bis_monat: date,
                      heute: Optional[date] = None, inflation: bool = False) -> dict:
    """
    Verbrauch je Kalendermonat für eine Menge von Kategorien - Grundlage
    für das Budgets-Details-Diagramm (seit v1.6.4). Anders als historie()
    (welche die Perioden des jeweiligen Budgets nutzt) rechnet diese
    Funktion bewusst in Kalendermonaten, damit ein einzelnes Budget und
    'alle Budgets zusammen' auf derselben Zeitachse dargestellt werden
    können - unabhängig von Monats-/Quartals-/Jahres-Perioden der
    einzelnen Budgets.

    Bis einschließlich des aktuellen Monats werden echte Ist-/
    Plan-Buchungen herangezogen ('verbrauch'), danach die rein
    rechnerische Projektion aus wiederkehrenden Buchungen und
    Darlehensraten ('prognose') - analog zum echt/prognostiziert-Schnitt
    in auswertungen.cashflow_monatlich. Altersvorsorge-Beiträge fließen
    hier bewusst nicht ein (wie schon in _projizierte_fixkosten/prognose).
    von_monat/bis_monat müssen auf den jeweiligen Monatsersten normiert
    sein.
    """
    from . import darlehensraten as darlehensraten_modul
    from . import wiederkehrend as wiederkehrend_modul

    heute = heute or zeit.heute()
    heute_monat = date(heute.year, heute.month, 1)
    ids = set(kategorie_ids)

    monate = []
    m = von_monat
    while m <= bis_monat:
        monate.append(m)
        m += relativedelta(months=1)

    echt: dict = {}
    if ids and von_monat <= min(bis_monat, heute_monat):
        echt_bis = min(bis_monat, heute_monat) + relativedelta(months=1) - timedelta(days=1)
        platzhalter = ",".join("?" * len(ids))
        rows = conn.execute(
            f"""SELECT strftime('%Y-%m-01', datum) AS monat, SUM(ABS(betrag)) AS verbrauch
                FROM buchungen
                WHERE typ IN ('Ist','Plan') AND kategorie_id IN ({platzhalter})
                      AND datum >= ? AND datum <= ?
                GROUP BY monat""",
            [*ids, von_monat.isoformat(), echt_bis.isoformat()],
        ).fetchall()
        echt = {date.fromisoformat(r["monat"]): r["verbrauch"] for r in rows}

    prognose: dict = {}
    if ids and bis_monat >= heute_monat:
        ab = heute_monat + relativedelta(months=1)
        bis_projektion = bis_monat + relativedelta(months=1) - timedelta(days=1)
        feiertage = {date.fromisoformat(r["datum"]): r["name"]
                     for r in conn.execute("SELECT datum, name FROM feiertage").fetchall()}
        # anstehende_* liefern (von, bis]. Seit v2.0 ab heute: noch anstehende
        # Termine des laufenden Monats landen als heller "Prognose"-Aufsatz im
        # laufenden Monat (Punkt 1). Damit sind auch Termine am 1. des
        # Folgemonats enthalten (Befund E, v1.10).
        posten = wiederkehrend_modul.anstehende_termine(conn, feiertage, heute, bis_projektion,
                                                        inkl_umbuchungen=False, inflation=inflation)
        posten += darlehensraten_modul.anstehende_raten(conn, feiertage, heute, bis_projektion)
        for p in posten:
            if p["kategorie_id"] not in ids:
                continue
            pm = date.fromisoformat(p["datum"][:7] + "-01")
            prognose[pm] = round(prognose.get(pm, 0.0) + abs(p["betrag"]), 2)
        # Seit v1.10 (Befund B): gespeicherte Buchungen nach dem laufenden
        # Monat (manuelle Plan-Buchungen, per "Anpassen" verschobene) zählen
        # ebenfalls in ihrem Monat.
        platzhalter = ",".join("?" * len(ids))
        for r in conn.execute(
                f"""SELECT strftime('%Y-%m-01', datum) AS monat, SUM(ABS(betrag)) AS summe
                    FROM buchungen
                    WHERE typ IN ('Ist','Plan') AND kategorie_id IN ({platzhalter})
                          AND datum > ? AND datum <= ?
                    GROUP BY monat""",
                [*ids, (ab - timedelta(days=1)).isoformat(), bis_projektion.isoformat()]).fetchall():
            pm = date.fromisoformat(r["monat"])
            prognose[pm] = round(prognose.get(pm, 0.0) + r["summe"], 2)

    return {
        "monate": [m.strftime("%Y-%m") for m in monate],
        "verbrauch": [round(echt.get(m, 0.0), 2) if m <= heute_monat else None for m in monate],
        # laufender Monat: nur der Anteil anstehender Termine (Aufsatz zum Verbrauch)
        "prognose": [round(prognose.get(m, 0.0), 2) if m > heute_monat
                     else (round(prognose[m], 2) if m == heute_monat and prognose.get(m) else None)
                     for m in monate],
        "prognose_ab_monat": heute_monat.strftime("%Y-%m") if bis_monat >= heute_monat else None,
    }


# ─── Überschneidungen ────────────────────────────────────────────────

def ueberschneidungen(conn, budget) -> list[str]:
    """
    Weist auf andere Budgets hin, deren Kategoriemenge sich mit dieser
    überschneidet (z. B. Gruppenbudget auf 'Mobilität' plus eigenes
    Budget auf 'Kraftstoff'). Bewusst erlaubt - nur gekennzeichnet.
    """
    if budget["typ"] == "sparziel" or not budget["kategorie_id"]:
        return []
    eigene = set(kategorie_ids(conn, budget["kategorie_id"], budget["inkl_unterkategorien"]))
    hinweise = []
    for anderes in conn.execute(
        "SELECT * FROM budgets WHERE id != ? AND aktiv = 1 AND typ != 'sparziel'", (budget["id"],)
    ).fetchall():
        if not anderes["kategorie_id"]:
            continue
        fremde = set(kategorie_ids(conn, anderes["kategorie_id"], anderes["inkl_unterkategorien"]))
        if eigene & fremde:
            hinweise.append(anderes["name"])
    return hinweise


# ─── Gesamtstatus ────────────────────────────────────────────────────

def status(conn, budget, stichtag: Optional[date] = None,
           min_perioden: int = 3, historie_perioden: int = 12, inflation: bool = False) -> dict:
    stichtag = stichtag or zeit.heute()
    d = dict(budget)

    if budget["typ"] == "sparziel":
        stand = sparziel_stand(conn, budget, stichtag)
        zielbetrag = budget["zielbetrag"] or 0.0
        fortschritt = round(stand["ist"] / zielbetrag * 100, 1) if zielbetrag else 0.0
        d.update({
            "soll": stand["soll"], "verbrauch": stand["ist"],
            "differenz": stand["differenz"], "fortschritt": fortschritt,
            "restbetrag": round(zielbetrag - stand["ist"], 2) if zielbetrag else None,
            # Beim Sparziel ist "zu wenig angespart" der Warnfall, deshalb
            # wird die Ampel hier über die Soll-Erfüllung gebildet.
            "ampel": "gruen" if stand["differenz"] >= 0 else ("gelb" if stand["ist"] > 0 else "rot"),
            "verfahren": "-", "ueberschneidungen": [],
        })
        return d

    periode = aktuelle_periode(budget, stichtag)
    if periode is None:
        d.update({"verbrauch": 0.0, "fortschritt": 0.0, "restbetrag": budget["betrag"],
                  "ampel": "gruen", "ueberschneidungen": []})
        return d
    von, bis = periode

    verbrauch = _verbrauch(conn, budget, von, bis)
    verf = verfuegbarer_betrag(conn, budget, stichtag)
    fortschritt = round(verbrauch / verf["verfuegbar"] * 100, 1) if verf["verfuegbar"] else 0.0

    d.update({
        "periode_von": von.isoformat(), "periode_bis": bis.isoformat(),
        "verbrauch": verbrauch,
        "basis": verf["basis"], "uebertrag_betrag": verf["uebertrag"],
        "verfuegbar": verf["verfuegbar"],
        "restbetrag": round(verf["verfuegbar"] - verbrauch, 2),
        "fortschritt": fortschritt,
        "ampel": ampel(budget, fortschritt),
        "warnungen_aktiv": ausgeloeste_warnungen(budget, fortschritt),
        "prognose": prognose(conn, budget, stichtag, min_perioden, inflation),
        "historie": historie(conn, budget, historie_perioden, stichtag),
        "ueberschneidungen": ueberschneidungen(conn, budget),
    })
    return d

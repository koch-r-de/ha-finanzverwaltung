"""
Datenaufbereitung für die Auswertungen (Saldo-Verlauf, Cashflow,
Tilgungspläne) - liefert fertige Datensätze für die Chart.js-Diagramme
im Frontend. Zeithorizont ist frei wählbar (1-20 Jahre, Abschnitt 6).

Saldo-Prognose: Es werden keine Plan-Buchungen mehr im Voraus in der
Datenbank angelegt (siehe wiederkehrend.py). Die Grenze zwischen
"tatsächlich" und "prognostiziert" ist daher schlicht 'heute' - für
Monate ab heute wird der Effekt aktiver wiederkehrender Buchungen
(inkl. Dynamik) und laufender Darlehensraten (aus dem theoretischen
Tilgungsplan) rein rechnerisch aufaddiert, ohne dafür Zeilen in der
Datenbank anzulegen. Das funktioniert für beliebig lange Zeiträume
(1 bis 20 Jahre).

Bugfix v1.6.3: Die Prognose (saldo_verlauf/cashflow_monatlich) hatte den
Effekt aktiver Altersvorsorge-Beiträge/-Auszahlungen für Monate ab heute
komplett vergessen (nur wiederkehrende Buchungen und Darlehensraten
flossen ein) - dadurch war insbesondere der Altersvorsorge-Korridor im
Saldo-Verlauf verzerrt, da er nur den DELTA (voraussichtlich./.garantiert)
auf eine Basis ohne den garantierten Betrag aufaddierte. Siehe
_projektion_altersvorsorge().
"""
from datetime import date

from dateutil.relativedelta import relativedelta

from . import buchungen as buchungen_modul
from . import wiederkehrend as wiederkehrend_modul
from . import darlehensraten as darlehensraten_modul
from . import altersvorsorge as altersvorsorge_modul
from .darlehen import aus_db_zeile, berechne_tilgungsplan
from .feiertage import bank_kalender, vorheriger_werktag
from . import zeit


def _monatsanfang(d: date) -> date:
    return date(d.year, d.month, 1)


def _addieren(ergebnis: dict, monat: date, betrag: float, brutto: bool) -> None:
    """Netto je Monat (float) oder - mit brutto=True, seit v1.10 für den
    Cashflow (Befund G) - getrennt als [einnahmen, ausgaben] (beide positiv)."""
    if brutto:
        werte = ergebnis.setdefault(monat, [0.0, 0.0])
        if betrag >= 0:
            werte[0] += betrag
        else:
            werte[1] -= betrag
    else:
        ergebnis[monat] = ergebnis.get(monat, 0.0) + betrag


def _projektion_wiederkehrend(conn, feiertage: dict, heute: date, bis: date, konto_id: int = None,
                               kategorie_ids=None, person_id: int = None,
                               inkl_umbuchungen: bool = False, brutto: bool = False,
                               inflation: bool = False, konto_ids=None) -> dict:
    """Netto-Effekt je Monat aktiver wiederkehrender Buchungen mit
    Zahlungsdatum im Zeitraum (heute, bis] - rein rechnerisch, ohne DB-
    Schreibzugriff. Ohne konto_id kontoübergreifend (für den Cashflow, der
    nicht nach Konto aufschlüsselt). kategorie_id/person_id filtern optional
    auf Vorlagen einer einzelnen Kategorie bzw. Person (Vorlagen tragen eine
    eigene person_id, siehe personen.py-Modul-Docstring).

    Seit v1.10 (Befund D): Maßgeblich ist das tatsächliche Zahlungsdatum nach
    Werktagsverschiebung, und es zählen nur Termine NACH heute. Bis 1.9.1
    begann die Prognose am Monatsersten - im laufenden Monat bereits gebuchte
    Termine wurden dadurch im Saldo-Verlauf doppelt gezählt.

    Umbuchungen (seit v1.10) zählen nur mit inkl_umbuchungen=True, einem
    Konto und ohne Kategorie-Filter (Saldo-Verlauf): Abgang im Quell-, Zugang
    im Zielkonto. Cashflow & Co. lassen sie aus, wie echte Übertragungen.

    Seit v2.3 Mehrfachfilter: kategorie_ids und konto_ids sind Mengen
    (None = kein Filter). konto_id (einzeln) bleibt für den Saldo-Verlauf je
    Konto, weil nur dort Umbuchungen als Ab- und Zugang zählen."""
    ergebnis: dict = {}
    sql = "SELECT * FROM wiederkehrende_buchungen WHERE aktiv = 1"
    bedingungen, params = [], []
    if konto_id is not None:
        bedingungen.append("(konto_id = ? OR zielkonto_id = ?)")
        params += [konto_id, konto_id]
    buchungen_modul.sql_in("kategorie_id", kategorie_ids, bedingungen, params)
    buchungen_modul.sql_in("konto_id", konto_ids, bedingungen, params)
    if person_id is not None:
        bedingungen.append("person_id = ?")
        params.append(person_id)
    if bedingungen:
        sql += " AND " + " AND ".join(bedingungen)
    umbuchungen_zaehlen = inkl_umbuchungen and konto_id is not None and kategorie_ids is None
    # Schalter "Inflation einrechnen" (seit v2.0): nur Vorlagen mit Häkchen,
    # nur in der Projektion (zentral über betrag_mit_inflation).
    faktor = wiederkehrend_modul.globaler_inflationsfaktor(conn) if inflation else 0.0
    # Termine kurz nach 'bis' können per Werktagsverschiebung noch hineinfallen.
    termine_bis = bis + wiederkehrend_modul.VERSCHIEBUNG_PUFFER
    for vorlage in conn.execute(sql, params).fetchall():
        umbuchung = wiederkehrend_modul.ist_umbuchung(vorlage)
        if umbuchung and not umbuchungen_zaehlen:
            continue
        if not umbuchung and konto_id is not None and vorlage["konto_id"] != konto_id:
            continue
        for termin in wiederkehrend_modul.alle_termine(vorlage, termine_bis):
            verschoben = vorheriger_werktag(termin, feiertage)
            if verschoben <= heute or verschoben > bis:
                continue
            if umbuchung:
                betrag = abs(vorlage["betrag"])
                betrag = -betrag if vorlage["konto_id"] == konto_id else betrag
            else:
                betrag = wiederkehrend_modul.vorzeichen_anwenden(
                    conn, vorlage["kategorie_id"], wiederkehrend_modul.betrag_mit_dynamik(vorlage, termin)
                )
                if inflation and vorlage["inflationsflag"]:
                    betrag = wiederkehrend_modul.betrag_mit_inflation(betrag, verschoben, faktor, heute=heute)
            monat = _monatsanfang(verschoben)
            _addieren(ergebnis, monat, betrag, brutto)
    return ergebnis


def _projektion_altersvorsorge(conn, feiertage: dict, heute: date, bis: date, konto_ids=None,
                                kategorie_ids=None, brutto: bool = False, inflation: bool = False) -> dict:
    """
    Netto-Effekt je Monat aktiver Altersvorsorge-Beiträge/-Auszahlungen
    (garantierte Beträge, inkl. ggf. aktivem Inflationsfaktor) mit
    Zahlungsdatum im Zeitraum (heute, bis] - analog zu
    _projektion_wiederkehrend, nur für die Altersvorsorge (die ihre
    Terminberechnung in altersvorsorge.anstehende_termine hat). Fehlte bis
    v1.6.3 komplett in saldo_verlauf/cashflow_monatlich (Korridor-Bugfix);
    seit v1.10 ab heute statt ab Monatsanfang (Befund D).
    """
    ergebnis: dict = {}
    for b in altersvorsorge_modul.anstehende_termine(conn, feiertage, heute, bis, inflation=inflation):
        if konto_ids is not None and b["konto_id"] not in konto_ids:
            continue
        if kategorie_ids is not None and b.get("kategorie_id") not in kategorie_ids:
            continue
        monat = _monatsanfang(date.fromisoformat(b["datum"]))
        _addieren(ergebnis, monat, b["betrag"], brutto)
    return ergebnis


def _projektion_darlehensraten(conn, feiertage: dict, heute: date, bis: date, konto_ids=None,
                                kategorie_ids=None, brutto: bool = False) -> dict:
    """Netto-Effekt je Monat der Zins-/Tilgungszahlungen mit Zahlungsdatum
    im Zeitraum (heute, bis] - seit v1.10 über anstehende_raten (tatsächliches
    Zahlungsdatum, ab heute statt ab Monatsanfang, Befund D). Seit v2.3
    zählen die Raten auch mit Kategorie-Filter, wenn ihre Kategorie
    (Darlehens-Zinsen, Tilgung) gewählt ist."""
    ergebnis: dict = {}
    for b in darlehensraten_modul.anstehende_raten(conn, feiertage, heute, bis):
        if konto_ids is not None and b["konto_id"] not in konto_ids:
            continue
        if kategorie_ids is not None and b.get("kategorie_id") not in kategorie_ids:
            continue
        monat = _monatsanfang(date.fromisoformat(b["datum"]))
        _addieren(ergebnis, monat, b["betrag"], brutto)
    return ergebnis


def _feiertage(conn):
    """Kalender für die Verschiebung fälliger Termine (seit v2.6 TARGET)."""
    return bank_kalender()


def _monatsreihe(von: date, bis: date) -> list:
    monate = []
    m = date(von.year, von.month, 1)
    while m <= bis:
        monate.append(m)
        m += relativedelta(months=1)
    return monate


def kategorie_gruppen(conn, kategorie_ids) -> list[dict]:
    """
    Fasst eine Kategorie-Auswahl (seit v2.3, Menge einzeln gewählter
    Knoten) zu Gruppen für den Saldo-Verlauf zusammen: Jeder gewählte Knoten,
    dessen Oberkategorie nicht gewählt ist, bildet eine Gruppe mit allen
    gewählten Nachfahren, die über gewählte Knoten erreichbar sind. Eine voll
    gewählte Oberkategorie ist damit genau eine Gruppe. Name = Pfad ohne die
    Wurzel (z. B. „Mobilität › Kraftstoff“), bei einer Wurzel deren Name.
    „(teilweise)“ markiert eine Gruppe, deren Nachfahren nicht alle gewählt sind.
    """
    rows = conn.execute("SELECT id, parent_id, name FROM kategorien").fetchall()
    eltern = {r["id"]: r["parent_id"] for r in rows}
    namen = {r["id"]: r["name"] for r in rows}
    kinder: dict = {}
    for r in rows:
        kinder.setdefault(r["parent_id"], []).append(r["id"])
    gewaehlt = set(kategorie_ids)

    def pfad(kid):
        teile = []
        while kid is not None:
            teile.append(namen[kid])
            kid = eltern[kid]
        teile.reverse()
        return " › ".join(teile[1:]) if len(teile) > 1 else teile[0]

    def nachfahren(kid):
        alle = []
        for k in kinder.get(kid, []):
            alle.append(k)
            alle += nachfahren(k)
        return alle

    gruppen = []
    for kid in sorted(gewaehlt, key=lambda k: pfad(k).casefold()):
        if kid not in namen or eltern.get(kid) in gewaehlt:
            continue
        mitglieder, offen = {kid}, [kid]
        while offen:
            for k in kinder.get(offen.pop(), []):
                if k in gewaehlt:
                    mitglieder.add(k)
                    offen.append(k)
        voll = all(k in gewaehlt for k in nachfahren(kid))
        gruppen.append({"kategorie_id": kid, "name": pfad(kid) + ("" if voll else " (teilweise)"),
                        "ids": mitglieder})
    return gruppen


def _restschuld_heute(conn, heute: date, feiertage: dict) -> float:
    """Summe der aktuellen Restschulden: Stand nach dem letzten Termin, dessen
    Zahlungstag (Werktagsverschiebung) bis heute liegt - wie die Kennzahl
    „Restschuld heute“ im Reiter Darlehen (vertragsauswertung)."""
    summe = 0.0
    for row in conn.execute("SELECT * FROM darlehen").fetchall():
        plan = [z for z in darlehensraten_modul.tilgungsplan_laden(conn, row)
                if vorheriger_werktag(z.datum, feiertage) <= heute]
        if plan:
            summe += plan[-1].restschuld
    return round(summe, 2)


def saldo_verlauf(conn, von: date, bis: date, konto_ids=None, inkl_darlehen: bool = True,
                   kategorie_ids=None, inflation: bool = False):
    """
    Monatlicher Saldo-Verlauf je Konto (gestapeltes Flächendiagramm im
    Frontend) sowie optional die Restschuld-Linien der Darlehen.

    Seit v2.3 Mehrfachfilter: konto_ids und kategorie_ids sind Mengen
    (None = kein Filter). Mit Kategorie-Filter ändert sich die Semantik
    bewusst: statt des Kontostands je Konto kommt je Kategorie-Gruppe (siehe
    kategorie_gruppen) die kumulierte Summe über alle gewählten Konten
    (Start bei 0, ohne Saldo-Korrekturen, ohne Restschuld-Linien). Bis 2.2
    gab es dafür nur eine einzelne Kategorie, aufgeteilt je Konto.

    stand_heute liefert die Grundlage der Kennzahlen-Kacheln: Summe der
    Kontostände heute (wie auf der Startseite) und die heutige Restschuld.
    """
    konten = buchungen_modul.konten_liste(conn, nur_aktive=True)
    if konto_ids is not None:
        konten = [k for k in konten if k["id"] in konto_ids]

    monate = _monatsreihe(von, bis)
    heute = zeit.heute()
    heute_monat = _monatsanfang(heute)
    feiertage = _feiertage(conn)
    prognose_ab = next((i for i, mo in enumerate(monate) if mo >= heute_monat), len(monate))

    def _kumuliert(projektion: dict, monat: date) -> float:
        return sum(v for k, v in projektion.items() if k <= monat)

    if kategorie_ids is not None:
        ids_konten = {k["id"] for k in konten}
        serien = []
        for gruppe in kategorie_gruppen(conn, kategorie_ids):
            bedingungen = ["typ IN ('Ist', 'Plan')", "datum <= ?"]
            params: list = [bis.isoformat()]
            buchungen_modul.sql_in("konto_id", ids_konten, bedingungen, params)
            buchungen_modul.sql_in("kategorie_id", gruppe["ids"], bedingungen, params)
            je_monat = {date.fromisoformat(r[0] + "-01"): r[1] for r in conn.execute(
                f"SELECT strftime('%Y-%m', datum), SUM(betrag) FROM buchungen WHERE {' AND '.join(bedingungen)} "
                "GROUP BY 1", params).fetchall()}
            proj = [{}, {}, {}]
            if bis >= heute:
                proj = [
                    _projektion_wiederkehrend(conn, feiertage, heute, bis, kategorie_ids=gruppe["ids"],
                                              konto_ids=ids_konten, inflation=inflation),
                    _projektion_altersvorsorge(conn, feiertage, heute, bis, ids_konten, gruppe["ids"],
                                               inflation=inflation),
                    _projektion_darlehensraten(conn, feiertage, heute, bis, ids_konten, gruppe["ids"]),
                ]
            werte = []
            for i, monat in enumerate(monate):
                wert = sum(v for k, v in je_monat.items() if k <= monat)
                if i >= prognose_ab:
                    wert += sum(_kumuliert(p, monat) for p in proj)
                werte.append(round(wert, 2))
            serien.append({"kategorie_id": gruppe["kategorie_id"], "name": gruppe["name"], "werte": werte})
        return {"monate": [mo.isoformat() for mo in monate], "prognose_ab_index": prognose_ab,
                "modus": "kategorien", "kategorien": serien, "konten": [], "darlehen": [],
                "stand_heute": None}

    konten_serien = []
    for konto in konten:
        werte = []
        projektion_wk = projektion_av = projektion_dl = None
        for monat in monate:
            stichtag = min(monat + relativedelta(months=1) - relativedelta(days=1), bis)
            # Gespeicherte Buchungen bis zum Monatsende - seit v1.10 auch in
            # Prognosemonaten (Befund B): manuelle Plan-Buchungen, künftige
            # Übertragungen und per "Anpassen" verschobene Buchungen zählen
            # damit in ihrem Monat.
            wert = buchungen_modul.saldo(conn, konto["id"], stichtag, inkl_plan=True)
            if monat >= heute_monat:
                # Ab dem laufenden Monat (seit v2.0, vorher erst ab dem
                # Folgemonat) zusätzlich die rechnerische Prognose aller
                # Termine nach heute - der laufende Monat zeigt damit den
                # erwarteten Monatsend-Stand.
                if projektion_wk is None:
                    projektion_wk = _projektion_wiederkehrend(conn, feiertage, heute, bis, konto["id"],
                                                              inkl_umbuchungen=True, inflation=inflation)
                    projektion_av = _projektion_altersvorsorge(conn, feiertage, heute, bis,
                                                                {konto["id"]}, inflation=inflation)
                    projektion_dl = _projektion_darlehensraten(conn, feiertage, heute, bis, {konto["id"]})
                effekt = _kumuliert(projektion_wk, monat) + _kumuliert(projektion_av, monat) + \
                    _kumuliert(projektion_dl, monat)
                wert = round(wert + effekt, 2)
            werte.append(wert)
        konten_serien.append({"konto_id": konto["id"], "name": konto["name"],
                               "farbe": konto["farbe"], "werte": werte})

    darlehen_serien = []
    if inkl_darlehen:
        for row in conn.execute("SELECT * FROM darlehen").fetchall():
            plan = {z.datum: z.restschuld for z in darlehensraten_modul.tilgungsplan_laden(conn, row)}
            werte = [-plan.get(monat, 0.0) for monat in monate]
            darlehen_serien.append({"name": f"{row['bezeichnung']} (Restschuld)", "werte": werte})

    return {
        "monate": [mo.isoformat() for mo in monate],
        # seit v2.0 ab dem laufenden Monat (enthält anstehende Termine)
        "prognose_ab_index": prognose_ab,
        "modus": "konten",
        "konten": konten_serien,
        "darlehen": darlehen_serien,
        "stand_heute": {
            "konten": round(sum(buchungen_modul.saldo(conn, k["id"]) for k in konten), 2),
            "restschuld": _restschuld_heute(conn, heute, feiertage) if inkl_darlehen else 0.0,
        },
    }


def cashflow_monatlich(conn, von: date, bis: date, konto_ids=None, kategorie_ids=None,
                        person_id: int = None, inflation: bool = False):
    """
    konto_id/kategorie_id/person_id filtern optional (Kategorie/Konto
    identisch zum Saldo-Verlauf, siehe dort; person_id zusätzlich für die
    Jahresübersicht - siehe personen.py-Modul-Docstring). Anders als beim
    Saldo-Verlauf ändert ein Kategorie- oder Personen-Filter hier nichts
    an der grundsätzlichen Semantik - Cashflow ist ohnehin eine Summe
    über einen Zeitraum, kein kumulierter Kontostand. Darlehensraten
    fließen nur ein, wenn kein Personen-Filter aktiv ist (Zins/Tilgung
    sind in der Projektion nicht personen-aufgeschlüsselt). Seit v2.3
    Mehrfachfilter (Mengen, None = kein Filter); mit Kategorie-Filter
    zählen die Raten, wenn ihre Kategorie gewählt ist.
    """
    heute = zeit.heute()
    heute_monat = _monatsanfang(heute)

    # Seit v1.10 (Befund B) über den ganzen Zeitraum: auch gespeicherte
    # Buchungen nach dem laufenden Monat (manuelle Plan-Buchungen, per
    # "Anpassen" verschobene) zählen in ihrem Monat. Übertragungen bleiben
    # wie bisher außen vor (buchungen.cashflow liest nur Ist/Plan).
    rows = buchungen_modul.cashflow(conn, von, bis,
                                     inkl_plan=True, konto_ids=konto_ids, kategorie_ids=kategorie_ids,
                                     person_id=person_id)
    einnahmen = {date.fromisoformat(r["monat"] + "-01"): r["einnahmen"] for r in rows}
    ausgaben = {date.fromisoformat(r["monat"] + "-01"): r["ausgaben"] for r in rows}

    einnahmen_anstehend: dict = {}
    ausgaben_anstehend: dict = {}
    if bis >= heute:
        feiertage = _feiertage(conn)
        # brutto=True: Einnahmen und Ausgaben getrennt (seit v1.10, Befund G -
        # bis 1.9.1 wurden Prognosemonate saldiert, z. B. Einnahmen 905 €,
        # Ausgaben 0 € statt 2.800 € / 1.895 €).
        proj_wk = _projektion_wiederkehrend(conn, feiertage, heute, bis, kategorie_ids=kategorie_ids,
                                            person_id=person_id, brutto=True, inflation=inflation,
                                            konto_ids=konto_ids)
        # Altersvorsorge kennt (anders als wiederkehrende Buchungen) keinen
        # eigenen Personen-Filter in anstehende_termine - bei aktivem
        # person_id-Filter bleibt sie deshalb konsistent zu den
        # Darlehensraten außen vor (siehe deren Kommentar unten).
        if person_id is not None:
            proj_av = {}
        else:
            proj_av = _projektion_altersvorsorge(conn, feiertage, heute, bis, konto_ids, kategorie_ids, brutto=True,
                                                 inflation=inflation)
        proj_dl = {} if person_id is not None else \
            _projektion_darlehensraten(conn, feiertage, heute, bis, konto_ids, kategorie_ids, brutto=True)
        # Seit v2.0 ab dem laufenden Monat: dessen noch anstehende Termine
        # (nach heute) zählen mit und werden zusätzlich getrennt geliefert,
        # damit das Diagramm sie hell absetzen kann.
        m = heute_monat
        while m <= bis:
            for proj in (proj_wk, proj_av, proj_dl):
                ein, aus = proj.get(m, (0.0, 0.0))
                einnahmen[m] = einnahmen.get(m, 0.0) + ein
                ausgaben[m] = ausgaben.get(m, 0.0) + aus
                if m == heute_monat:
                    einnahmen_anstehend[m] = einnahmen_anstehend.get(m, 0.0) + ein
                    ausgaben_anstehend[m] = ausgaben_anstehend.get(m, 0.0) + aus
            m += relativedelta(months=1)

    # Lückenlose Monatsreihe von 'von' bis 'bis' - Monate ganz ohne
    # Buchung tauchen in obigen Dictionaries gar nicht erst auf und
    # müssen explizit mit 0 aufgefüllt werden (sonst entstehen Lücken
    # in der x-Achse des Diagramms).
    alle_monate = []
    m = _monatsanfang(von)
    while m <= bis:
        alle_monate.append(m)
        m += relativedelta(months=1)

    return {
        "monate": [m.strftime("%Y-%m") for m in alle_monate],
        "einnahmen": [round(einnahmen.get(m, 0.0), 2) for m in alle_monate],
        "ausgaben": [round(ausgaben.get(m, 0.0), 2) for m in alle_monate],
        # Anteil noch anstehender Termine im laufenden Monat (in den Summen enthalten)
        "einnahmen_anstehend": [round(einnahmen_anstehend.get(m, 0.0), 2) for m in alle_monate],
        "ausgaben_anstehend": [round(ausgaben_anstehend.get(m, 0.0), 2) for m in alle_monate],
        "laufender_monat": heute_monat.strftime("%Y-%m"),
    }


def tilgungsplan_fuer_darlehen(conn, darlehen_id: int):
    row = conn.execute("SELECT * FROM darlehen WHERE id = ?", (darlehen_id,)).fetchone()
    if row is None:
        raise ValueError("Darlehen nicht gefunden.")
    plan = darlehensraten_modul.tilgungsplan_laden(conn, row)
    return [
        {"datum": z.datum.isoformat(), "phase": z.phase, "zinssatz": z.zinssatz,
         "zinsen": z.zinsen, "tilgung": z.tilgung, "sondertilgung": z.sondertilgung,
         "rate": z.rate, "restschuld": z.restschuld}
        for z in plan
    ]


def inflationsbereinigt(betrag: float, jahre: float, inflationsfaktor_prozent: float) -> float:
    """Reine Anzeige-Umrechnung (siehe Fachkonzept 3.3/8.1) - wirkt sich
    NICHT auf gespeicherte Buchungen aus, nur auf die Darstellung."""
    return round(betrag * (1 + inflationsfaktor_prozent / 100) ** jahre, 2)


def jahresuebersicht(conn, von: date, bis: date, konto_ids=None, kategorie_ids=None,
                      person_id: int = None, inflation: bool = False) -> dict:
    """
    Monatsweise Übersicht eines Zwölf-Monats-Zeitraums: Einnahmen, Ausgaben
    und Saldo je Monat plus Gesamtsumme. Nutzt dieselbe Logik wie der
    Cashflow (Ist bis heute, danach rechnerische Prognose), sodass auch
    laufende/künftige Zeiträume sinnvoll dargestellt werden. konto_id/
    kategorie_id/person_id filtern optional - identisch zu den
    Auswertungen (siehe cashflow_monatlich), für konsistente Filter.

    Seit v1.6.3 nimmt die Funktion 'von'/'bis' statt eines Kalenderjahres
    entgegen, damit der Aufrufer (main.py) sowohl den klassischen
    Kalenderjahr-Modus als auch "rollierend 12 Monate" (neuer Standard,
    endet im aktuellen Monat) darstellen kann - die Berechnung selbst ist
    in beiden Fällen identisch, nur der Zeitraum unterscheidet sich.
    """
    cf = cashflow_monatlich(conn, von, bis, konto_ids=konto_ids, kategorie_ids=kategorie_ids,
                            person_id=person_id, inflation=inflation)

    monate = []
    for i, monat in enumerate(cf["monate"]):
        einnahmen = cf["einnahmen"][i]
        ausgaben = cf["ausgaben"][i]
        monate.append({
            "monat": monat,
            "einnahmen": einnahmen,
            "ausgaben": ausgaben,
            "saldo": round(einnahmen - ausgaben, 2),
            # seit v2.0: im laufenden Monat enthaltener Anteil anstehender Termine
            "anstehend": round(cf["einnahmen_anstehend"][i] + cf["ausgaben_anstehend"][i], 2),
        })

    summe_einnahmen = round(sum(m["einnahmen"] for m in monate), 2)
    summe_ausgaben = round(sum(m["ausgaben"] for m in monate), 2)
    heute = zeit.heute()
    heute_monat = heute.strftime("%Y-%m")

    return {
        "von": von.isoformat(),
        "bis": bis.isoformat(),
        "monate": monate,
        "summe_einnahmen": summe_einnahmen,
        "summe_ausgaben": summe_ausgaben,
        "summe_saldo": round(summe_einnahmen - summe_ausgaben, 2),
        "durchschnitt_saldo": round((summe_einnahmen - summe_ausgaben) / max(1, len(monate)), 2),
        "prognose_ab_monat": heute_monat if any(m["monat"] == heute_monat for m in monate) else None,
    }


def jahresuebersicht_kategorien(conn, von: date, bis: date, konto_ids=None, kategorie_ids=None,
                                 person_id: int = None) -> list[dict]:
    """
    Summen je Kategorie EINE EBENE UNTERHALB der Wurzel (also den direkten
    Kindern von 'Einnahmen'/'Ausgaben', z. B. 'Wohnen', 'Mobilität') für
    den Zeitraum (nur Ist-Buchungen, Umbuchungen ausgenommen) - für den
    Jahresrückblick. Bis v1.6.3 wurde hier auf die Wurzel selbst (also nur
    'Einnahmen'/'Ausgaben') gruppiert; seit v1.6.4 eine Ebene tiefer, für
    eine aussagekräftigere Aufschlüsselung. Eine Buchung, die (im
    Ausnahmefall) direkt auf der Wurzel selbst liegt, wird der Wurzel
    zugeordnet (Fallback). konto_ids/kategorie_ids (seit v2.3 Mengen)
    und person_id filtern optional - identisch zu den übrigen
    Jahresübersicht-Filtern (siehe jahresuebersicht). Ein Kategorie-Filter
    begrenzt die Buchungen, gruppiert wird weiterhin nach der Ebene-1-
    Kategorie der gewählten Buchungen. Seit v1.6.3 nimmt die
    Funktion 'von'/'bis' statt eines Kalenderjahres entgegen (siehe
    jahresuebersicht).
    """
    bedingungen = ["b.typ = 'Ist'", "b.datum BETWEEN ? AND ?", "kw.system_key IS NOT 'umbuchung'"]
    params: list = [von.isoformat(), bis.isoformat()]
    buchungen_modul.sql_in("b.konto_id", konto_ids, bedingungen, params)
    buchungen_modul.sql_in("b.kategorie_id", kategorie_ids, bedingungen, params)
    if person_id is not None:
        bedingungen.append("b.konto_id IN (SELECT id FROM konten WHERE person_id = ?)")
        params.append(person_id)
    rows = conn.execute(f"""
        WITH RECURSIVE ebene(id, ebene1_id, tiefe) AS (
            SELECT id, id, 0 FROM kategorien WHERE parent_id IS NULL
            UNION ALL
            SELECT k.id,
                   CASE WHEN e.tiefe = 0 THEN k.id ELSE e.ebene1_id END,
                   e.tiefe + 1
            FROM kategorien k JOIN ebene e ON k.parent_id = e.id
        )
        SELECT kw.name AS kategorie, COUNT(*) AS anzahl,
               ROUND(SUM(ABS(b.betrag)), 2) AS summe, kw.typ AS typ
        FROM buchungen b
        JOIN ebene e ON e.id = b.kategorie_id
        JOIN kategorien kw ON kw.id = e.ebene1_id
        WHERE {' AND '.join(bedingungen)}
        GROUP BY e.ebene1_id ORDER BY summe DESC
    """, params).fetchall()
    return [dict(r) for r in rows]


def _kategorie_wurzeln(conn) -> dict:
    """Bildet jede Kategorie-ID auf ihre Wurzelkategorie ab (wurzel_id, name,
    typ, system_key) - für die Python-seitige Gruppierung der "anstehenden"
    virtuellen Buchungen (wiederkehrend/Darlehensraten/Altersvorsorge), die
    nie in der Datenbank stehen und daher nicht per SQL gruppiert werden
    können (siehe kategorien_zeitraum). Neutrale Wurzeln (typ IS NULL, z.B.
    "Darlehen", "Umbuchung") sind bewusst mit dabei - der Aufrufer
    entscheidet, ob er sie ausschließt."""
    rows = conn.execute("""
        WITH RECURSIVE wurzel(id, wurzel_id) AS (
            SELECT id, id FROM kategorien WHERE parent_id IS NULL
            UNION ALL
            SELECT k.id, w.wurzel_id FROM kategorien k JOIN wurzel w ON k.parent_id = w.id
        )
        SELECT w.id AS kategorie_id, kw.id AS wurzel_id, kw.name AS name,
               kw.typ AS typ, kw.system_key AS system_key
        FROM wurzel w JOIN kategorien kw ON kw.id = w.wurzel_id
    """).fetchall()
    return {r["kategorie_id"]: {"wurzel_id": r["wurzel_id"], "name": r["name"],
                                 "typ": r["typ"], "system_key": r["system_key"]} for r in rows}


def _kategorie_info(conn) -> dict:
    """Jede Kategorie mit ihrem direkten Elternknoten und Namen - Grundlage
    für die "intelligente" Ein-Ebene-Gruppierung in kategorien_zeitraum
    (dort steht auch die Begründung)."""
    rows = conn.execute("SELECT id, parent_id, name FROM kategorien").fetchall()
    return {r["id"]: {"parent_id": r["parent_id"], "name": r["name"]} for r in rows}


def kategorien_zeitraum(conn, von: date, bis: date, konto_ids=None,
                         kategorie_ids=None, inflation: bool = False) -> list[dict]:
    """
    "Intelligente" Gruppierung für das Auswertungen-Diagramm "Kategorien" -
    bewusst NICHT nach Wurzelkategorie (nur "Einnahmen"/"Ausgaben", zu grob),
    sondern granularer: Ausgangspunkt ist jede granulare Kategorie, auf die
    im Zeitraum direkt gebucht wurde. Hat ihre direkte Oberkategorie
    ebenfalls mindestens eine eigene, zu den Filterkriterien passende
    Buchung, gilt diese Oberkategorie offenbar selbst als vom Nutzer
    genutzte Sammelkategorie (z. B. "Wohnen" mit eigenen Buchungen NEBEN
    "Miete"/"Nebenkosten") - dann wird auf sie hochgruppiert und
    aufsummiert. Andernfalls bleibt die granulare Kategorie ihr eigenes
    Segment (z. B. "Kraftstoff"/"KFZ-Unterhalt"/"ÖPNV" einzeln, solange
    "Mobilität" selbst nicht direkt bebucht ist). Geprüft wird nur EIN
    Elternschritt (kein rekursives Hochgruppieren bis zur Wurzel) - das
    verhindert genau das alte, zu grobe Nur-Einnahmen/Ausgaben-Verhalten.

    Umbuchungen sowie die fachlich neutralen Wurzeln (typ IS NULL, z. B.
    "Darlehen") bleiben außen vor, da sich für sie keine Einnahme/Ausgabe-
    Einordnung treffen lässt (Zins/Tilgung landen dadurch nicht fälschlich
    bei "Ausgaben").

    Wie schon zuvor wird der Teil des Zeitraums nach "heute" zusätzlich rein
    rechnerisch aus den anstehenden wiederkehrenden Buchungen,
    Darlehensraten und Altersvorsorge-Terminen ergänzt (analog zu
    saldo_verlauf/cashflow_monatlich) - ohne das wäre das Diagramm beim
    (standardmäßig zukunftsgerichteten) Zeithorizont der Auswertungen-Seite
    immer leer, weil dort nie echte Ist-Buchungen liegen.
    """
    # Seit v1.10 (Befund B) auch Plan-Buchungen - Übertragungen weiterhin nicht.
    bedingungen = ["b.typ IN ('Ist', 'Plan')", "b.datum BETWEEN ? AND ?"]
    params: list = [von.isoformat(), bis.isoformat()]
    buchungen_modul.sql_in("b.konto_id", konto_ids, bedingungen, params)
    buchungen_modul.sql_in("b.kategorie_id", kategorie_ids, bedingungen, params)
    echte = conn.execute(f"""
        SELECT b.kategorie_id AS kategorie_id, b.betrag AS betrag
        FROM buchungen b
        WHERE {' AND '.join(bedingungen)}
    """, params).fetchall()
    alle_buchungen = [{"kategorie_id": r["kategorie_id"], "betrag": r["betrag"]} for r in echte]

    heute = zeit.heute()
    if bis > heute:
        ab = max(heute, von - relativedelta(days=1))
        if ab < bis:
            feiertage = bank_kalender()
            anstehend = wiederkehrend_modul.anstehende_termine(conn, feiertage, ab, bis,
                                                                inkl_umbuchungen=False, inflation=inflation)
            anstehend += darlehensraten_modul.anstehende_raten(conn, feiertage, ab, bis)
            anstehend += altersvorsorge_modul.anstehende_termine(conn, feiertage, ab, bis, inflation=inflation)
            if konto_ids is not None:
                anstehend = [b for b in anstehend if b["konto_id"] in konto_ids]
            if kategorie_ids is not None:
                anstehend = [b for b in anstehend if b.get("kategorie_id") in kategorie_ids]
            alle_buchungen += [{"kategorie_id": b.get("kategorie_id"), "betrag": b["betrag"]} for b in anstehend]

    wurzeln = _kategorie_wurzeln(conn)
    kategorie_info = _kategorie_info(conn)

    # Nur Buchungen mit fachlich einordenbarer Kategorie (Einnahme/Ausgabe)
    # berücksichtigen - Umbuchungen und die neutralen Wurzeln (Darlehen)
    # fallen automatisch raus, da ihr Wurzel-Typ NULL ist.
    gefiltert = [
        b for b in alle_buchungen
        if (info := wurzeln.get(b["kategorie_id"])) is not None
        and info["typ"] is not None and info["system_key"] != "umbuchung"
    ]
    bebuchte_ids = {b["kategorie_id"] for b in gefiltert}

    ergebnis: dict = {}
    for b in gefiltert:
        kid = b["kategorie_id"]
        eltern_id = kategorie_info.get(kid, {}).get("parent_id")
        bucket_id = eltern_id if (eltern_id is not None and eltern_id in bebuchte_ids) else kid
        eintrag = ergebnis.setdefault(bucket_id, {
            "kategorie": kategorie_info.get(bucket_id, {}).get("name", "?"),
            "anzahl": 0, "summe": 0.0, "typ": wurzeln[bucket_id]["typ"],
        })
        eintrag["anzahl"] += 1
        eintrag["summe"] += abs(b["betrag"])

    ergebnis_liste = [
        {"kategorie": e["kategorie"], "anzahl": e["anzahl"], "summe": round(e["summe"], 2), "typ": e["typ"]}
        for e in ergebnis.values()
    ]
    ergebnis_liste.sort(key=lambda e: e["summe"], reverse=True)
    return ergebnis_liste

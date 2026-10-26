"""
Auswertungen je Vertragsart (seit v1.9): eigene Tabs "Darlehen" und
"Altersvorsorge" im Bereich Auswertungen.

Grundsätze
  - Vergangenheit (bis heute) aus den gebuchten Zahlungen, Zukunft aus dem
    rechnerischen Plan (Tilgungsplan bzw. altersvorsorge.anstehende_termine),
    ohne die Datenbank zu befüllen - gleiche Grenze "heute" wie überall.
  - Zuordnung zu Jahren nach dem tatsächlichen Zahlungsdatum (nach
    Werktagsverschiebung), wie bei den Generatoren. Eine Rate vom 1.1. kann
    so auf den 31.12. des Vorjahres fallen - das entspricht dem echten
    Geldfluss.
  - Ein Darlehen ohne Zahlungskonto hat keine Buchungen; dann stammt auch
    "bisher" aus dem Tilgungsplan.
  - Gebuchte Sondertilgungen senken die Restschuld im Plan ab ihrem Monat
    (seit v1.9.1); künftige sind unbekannt und fließen nicht ein.
"""
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

from . import altersvorsorge as altersvorsorge_modul
from .darlehensraten import tilgungsplan_laden
from .db import kategorie_id
from .feiertage import bank_kalender, vorheriger_werktag
from . import zeit

HORIZONT_JAHRE = altersvorsorge_modul.ROLLIERENDER_HORIZONT_JAHRE


def _r(x: float) -> float:
    return round(x or 0.0, 2)


def _feiertage(conn):
    """Kalender für die Verschiebung fälliger Termine (seit v2.6 TARGET)."""
    return bank_kalender()


def _im_zeitraum(jahr: int, von: Optional[date], bis: Optional[date]) -> bool:
    return (von is None or jahr >= von.year) and (bis is None or jahr <= bis.year)


# ─── Darlehen ────────────────────────────────────────────────────────

def _darlehen_einzeln(conn, row, heute: date, feiertage: dict, kat: dict) -> dict:
    auszahlungen = conn.execute(
        "SELECT datum, betrag FROM darlehen_auszahlungen WHERE darlehen_id = ?", (row["id"],)).fetchall()
    plan = tilgungsplan_laden(conn, row)   # inkl. gebuchter Sondertilgungen (seit v1.9.1)
    ausgezahlt = sum(a["betrag"] for a in auszahlungen)

    jahre: dict = {}   # jahr -> {zinsen, tilgung, sondertilgung, prognose_anteil}

    def jahr_eintrag(j):
        return jahre.setdefault(j, {"zinsen": 0.0, "tilgung": 0.0, "sondertilgung": 0.0, "prognose": False})

    bisher = {"zinsen": 0.0, "tilgung": 0.0, "sondertilgung": 0.0}
    kuenftig = {"zinsen": 0.0, "tilgung": 0.0}

    # Vergangenheit: gebuchte Zahlungen (nur bei Zahlungskonto vorhanden)
    if row["zahlungskonto_id"]:
        for b in conn.execute(
                """SELECT datum, betrag, kategorie_id FROM buchungen
                   WHERE ziel_darlehen_id = ? AND typ = 'Ist' AND datum <= ?""",
                (row["id"], heute.isoformat())).fetchall():
            art = kat.get(b["kategorie_id"])
            if art is None:
                continue          # z. B. Auszahlung - keine Zahlung an die Bank
            betrag = abs(b["betrag"])
            jahr_eintrag(int(b["datum"][:4]))[art] += betrag
            bisher[art] += betrag
    else:
        # Kein Zahlungskonto -> keine Buchungen: "bisher" aus dem Plan
        # (Sondertilgungen ohne Konto gibt es nicht, siehe Sondertilgung-Endpunkt)
        for z in plan:
            termin = vorheriger_werktag(z.datum, feiertage)
            if termin <= heute:
                e = jahr_eintrag(termin.year)
                e["zinsen"] += z.zinsen; e["tilgung"] += z.tilgung
                bisher["zinsen"] += z.zinsen; bisher["tilgung"] += z.tilgung

    # Zukunft: Tilgungsplan ab dem ersten Termin nach heute
    restschuld_heute = 0.0
    restschuld_ende_zinsbindung = None
    ende_zinsbindung = date.fromisoformat(row["ende_zinsbindung"])
    restschuld_jahresende: dict = {}
    for z in plan:
        termin = vorheriger_werktag(z.datum, feiertage)
        restschuld_jahresende[z.datum.year] = z.restschuld
        if z.datum < ende_zinsbindung:
            restschuld_ende_zinsbindung = z.restschuld
        if termin <= heute:
            restschuld_heute = z.restschuld
            continue
        e = jahr_eintrag(termin.year)
        e["zinsen"] += z.zinsen; e["tilgung"] += z.tilgung; e["prognose"] = True
        kuenftig["zinsen"] += z.zinsen; kuenftig["tilgung"] += z.tilgung

    restschuld_ende = plan[-1].restschuld if plan else 0.0
    summe = row["darlehenssumme"] if "darlehenssumme" in row.keys() else None
    return {
        "id": row["id"], "bezeichnung": row["bezeichnung"],
        "darlehenssumme": summe, "ausgezahlt": _r(ausgezahlt),
        "nicht_ausgezahlt": _r(summe - ausgezahlt) if summe is not None else None,
        "bisher": {k: _r(v) for k, v in {**bisher, "raten": bisher["zinsen"] + bisher["tilgung"]}.items()},
        "gesamt": {
            "zinsen": _r(bisher["zinsen"] + kuenftig["zinsen"]),
            "tilgung": _r(bisher["tilgung"] + kuenftig["tilgung"]),
            "sondertilgung": _r(bisher["sondertilgung"]),
            "raten": _r(bisher["zinsen"] + bisher["tilgung"] + kuenftig["zinsen"] + kuenftig["tilgung"]),
        },
        "zinsen_kuenftig": _r(kuenftig["zinsen"]),
        "restschuld_heute": _r(restschuld_heute),
        "restschuld_ende_zinsbindung": _r(restschuld_ende_zinsbindung or 0.0),
        "ende_zinsbindung": row["ende_zinsbindung"],
        "laufzeitende": (date.fromisoformat(row["zinsbeginn"]) + relativedelta(years=row["laufzeit_jahre"])).isoformat(),
        "restschuld_laufzeitende": _r(restschuld_ende),
        "_jahre": jahre, "_restschuld_jahresende": restschuld_jahresende,
        "_verlauf": [(z.datum, z.restschuld) for z in plan],
    }


def darlehen_auswertung(conn, darlehen_id: Optional[int] = None, von: Optional[date] = None,
                        bis: Optional[date] = None, heute: Optional[date] = None) -> dict:
    heute = heute or zeit.heute()
    feiertage = _feiertage(conn)
    kat = {kategorie_id(conn, "darlehen_zinsen"): "zinsen", kategorie_id(conn, "darlehen_tilgung"): "tilgung",
           kategorie_id(conn, "darlehen_sondertilgung"): "sondertilgung"}
    sql = "SELECT * FROM darlehen" + (" WHERE id = ?" if darlehen_id else "") + " ORDER BY bezeichnung"
    einzeln = [_darlehen_einzeln(conn, r, heute, feiertage, kat)
               for r in conn.execute(sql, (darlehen_id,) if darlehen_id else ()).fetchall()]

    # Jahrestabelle (summiert über die Auswahl)
    alle_jahre = sorted({j for d in einzeln for j in d["_jahre"]} | {j for d in einzeln for j in d["_restschuld_jahresende"]})
    jahre = []
    for j in alle_jahre:
        if not _im_zeitraum(j, von, bis):
            continue
        z = sum(d["_jahre"].get(j, {}).get("zinsen", 0) for d in einzeln)
        t = sum(d["_jahre"].get(j, {}).get("tilgung", 0) for d in einzeln)
        s = sum(d["_jahre"].get(j, {}).get("sondertilgung", 0) for d in einzeln)
        rs = 0.0
        for d in einzeln:
            # Restschuld zum Jahresende: letzter Planwert bis einschließlich Jahr j
            werte = [v for jj, v in d["_restschuld_jahresende"].items() if jj <= j]
            rs += werte[-1] if werte else 0.0
        jahre.append({"jahr": j, "zinsen": _r(z), "tilgung": _r(t), "sondertilgung": _r(s), "rate": _r(z + t),
                      "restschuld": _r(rs),
                      "prognose": "voll" if j > heute.year else ("teilweise" if j == heute.year else "")})

    # Restschuld-Verlauf je Darlehen (Monate)
    monate = sorted({m for d in einzeln for m, _ in d["_verlauf"]
                     if (von is None or m >= date(von.year, von.month, 1)) and (bis is None or m <= bis)})
    reihen = []
    for d in einzeln:
        plan = dict(d["_verlauf"])
        erster = min(plan) if plan else None
        werte = []
        letzter = 0.0
        for m in monate:
            if m in plan:
                letzter = plan[m]
            werte.append(_r(letzter) if erster and m >= erster else 0.0)
        reihen.append({"name": d["bezeichnung"], "werte": werte, "ende_zinsbindung": d["ende_zinsbindung"][:7]})

    def summe(feld, unterfeld=None):
        werte = [(d[feld][unterfeld] if unterfeld else d[feld]) for d in einzeln]
        werte = [w for w in werte if w is not None]
        return _r(sum(werte)) if werte else None

    summenzeile = {
        "bezeichnung": "Summe", "darlehenssumme": summe("darlehenssumme"), "ausgezahlt": summe("ausgezahlt"),
        "nicht_ausgezahlt": summe("nicht_ausgezahlt"),
        "bisher": {k: summe("bisher", k) for k in ("zinsen", "tilgung", "sondertilgung", "raten")},
        "gesamt": {k: summe("gesamt", k) for k in ("zinsen", "tilgung", "sondertilgung", "raten")},
        "restschuld_heute": summe("restschuld_heute"), "restschuld_laufzeitende": summe("restschuld_laufzeitende"),
    }
    oeffentlich = [{k: v for k, v in d.items() if not k.startswith("_")} for d in einzeln]
    return {
        "kennzahlen": {
            "restschuld_heute": summenzeile["restschuld_heute"] or 0.0,
            "restschuld_ende_zinsbindung": summe("restschuld_ende_zinsbindung") or 0.0,
            "zinsen_bisher": summenzeile["bisher"]["zinsen"] or 0.0,
            "tilgung_bisher": _r((summenzeile["bisher"]["tilgung"] or 0) + (summenzeile["bisher"]["sondertilgung"] or 0)),
            "zinsen_kuenftig": summe("zinsen_kuenftig") or 0.0,
            "restschuld_laufzeitende": summenzeile["restschuld_laufzeitende"] or 0.0,
        },
        "jahre": jahre,
        "verlauf": {"monate": [m.strftime("%Y-%m") for m in monate], "reihen": reihen},
        "darlehen": oeffentlich,
        "summe": summenzeile if len(oeffentlich) > 1 else None,
    }


# ─── Altersvorsorge ──────────────────────────────────────────────────

def altersvorsorge_auswertung(conn, av_id: Optional[int] = None, von: Optional[date] = None,
                              bis: Optional[date] = None, heute: Optional[date] = None,
                              inflation: bool = False) -> dict:
    heute = heute or zeit.heute()
    feiertage = _feiertage(conn)
    horizont = heute + relativedelta(years=HORIZONT_JAHRE)
    sql = "SELECT * FROM altersvorsorge" + (" WHERE id = ?" if av_id else "")
    vertraege = conn.execute(sql, (av_id,) if av_id else ()).fetchall()
    ids = [v["id"] for v in vertraege]

    jahre: dict = {}

    def eintrag(j):
        return jahre.setdefault(j, {"beitraege": 0.0, "ausz_g": 0.0, "ausz_v": 0.0, "prognose": False})

    beitraege_bisher = beitraege_kuenftig = 0.0
    if ids:
        ph = ",".join("?" * len(ids))
        for b in conn.execute(
                f"""SELECT datum, betrag FROM buchungen
                    WHERE ziel_altersvorsorge_id IN ({ph}) AND typ = 'Ist' AND datum <= ?""",
                (*ids, heute.isoformat())).fetchall():
            e = eintrag(int(b["datum"][:4]))
            if b["betrag"] < 0:
                e["beitraege"] += abs(b["betrag"]); beitraege_bisher += abs(b["betrag"])
            else:
                # vergangene Auszahlungen sind real -> garantiert = voraussichtlich
                e["ausz_g"] += b["betrag"]; e["ausz_v"] += b["betrag"]

    # Zukunft: garantierte Termine (inkl. ggf. Inflationsfaktor) + Korridor
    for t in altersvorsorge_modul.anstehende_termine(conn, feiertage, heute, horizont, id_filter=av_id,
                                                         inflation=inflation):
        e = eintrag(int(t["datum"][:4])); e["prognose"] = True
        if t["betrag"] < 0:
            e["beitraege"] += abs(t["betrag"]); beitraege_kuenftig += abs(t["betrag"])
        else:
            e["ausz_g"] += t["betrag"]; e["ausz_v"] += t["betrag"]
    for monat, delta in altersvorsorge_modul.korridor_projektion(conn, heute, horizont, id_filter=av_id,
                                                                         inflation=inflation).items():
        e = eintrag(monat.year); e["prognose"] = True
        e["ausz_v"] += delta

    zeilen = []
    kum_g = kum_v = 0.0
    break_even = {"garantiert": None, "voraussichtlich": None}
    for j in sorted(jahre):
        e = jahre[j]
        kum_g += e["ausz_g"] - e["beitraege"]
        kum_v += e["ausz_v"] - e["beitraege"]
        for schluessel, kum in (("garantiert", kum_g), ("voraussichtlich", kum_v)):
            if break_even[schluessel] is None and kum >= 0 and (e["ausz_g"] > 0 or e["ausz_v"] > 0):
                break_even[schluessel] = j
        if _im_zeitraum(j, von, bis):
            zeilen.append({"jahr": j, "beitraege": _r(e["beitraege"]), "auszahlung_garantiert": _r(e["ausz_g"]),
                           "auszahlung_voraussichtlich": _r(e["ausz_v"]),
                           "kumuliert_garantiert": _r(kum_g), "kumuliert_voraussichtlich": _r(kum_v),
                           "prognose": "voll" if j > heute.year else ("teilweise" if j == heute.year else "")})

    aktiv = [v for v in vertraege if v["aktiv"]]
    rente = [v for v in aktiv if v["auszahlungsart"] == "rente"]
    einmal = [v for v in aktiv if v["auszahlungsart"] == "einmalzahlung"]
    rueckkauf = [v for v in aktiv if v["rueckkaufswert"] is not None]
    grenze_veraltet = heute - relativedelta(months=14)
    return {
        "kennzahlen": {
            "beitraege_bisher": _r(beitraege_bisher),
            "beitraege_kuenftig": _r(beitraege_kuenftig),
            "rente_monatlich_garantiert": _r(sum(v["rente_garantiert_betrag"] or 0 for v in rente)),
            "rente_monatlich_voraussichtlich": _r(sum((v["rente_voraussichtlich_betrag"] or v["rente_garantiert_betrag"] or 0) for v in rente)),
            "einmalzahlung_garantiert": _r(sum(v["einmalzahlung_garantiert_betrag"] or 0 for v in einmal)),
            "einmalzahlung_voraussichtlich": _r(sum((v["einmalzahlung_voraussichtlich_betrag"] or v["einmalzahlung_garantiert_betrag"] or 0) for v in einmal)),
            "rueckkaufswert": _r(sum(v["rueckkaufswert"] for v in rueckkauf)) if rueckkauf else None,
            "rueckkaufswert_stand": min((v["stand_datum"] for v in rueckkauf), default=None),
            "veraltet": [v["bezeichnung"] for v in aktiv if date.fromisoformat(v["stand_datum"]) < grenze_veraltet],
        },
        "break_even": break_even,
        "horizont_bis": horizont.isoformat(),
        "jahre": zeilen,
    }

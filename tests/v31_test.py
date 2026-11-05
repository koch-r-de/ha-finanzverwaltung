"""Fachliche Tests 3.1: Saldo-Korrektur als Buchung (#12) und Befund AA
(Sperre der Kategorie „Umbuchung“ an allen Wegen).

Aufruf: python3 tests/v31_test.py <code> <quelle> <ziel> [<code_vorversion>]
<quelle> ist daten/v21 (zwei alte Saldo-Korrekturen). Vor dem Start legt der
Test weitere Altfälle in die Kopie: zwei Korrekturen am selben Tag, eine mit
Differenz 0, eine eigene Hauptkategorie „Anfangsbestand“ mit Buchung.
<code_vorversion> (Ordner finanzverwaltung/ von 3.0) dient der Gegenprobe:
dort sind die neuen Prüfungen nicht erfüllt.
"""
import io, os, shutil, sqlite3, subprocess, sys, json
from datetime import date, timedelta
code, quelle, ziel = sys.argv[1], sys.argv[2], sys.argv[3]
code_alt = sys.argv[4] if len(sys.argv) > 4 else None
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
DB = os.path.join(ziel, "finanzdaten.db")

ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""))

# ═══ Altdaten wie in 3.0 ═══
con = sqlite3.connect(DB)
konten = dict(con.execute("SELECT name, id FROM konten"))
GIRO, GIRO2, KK, TG = konten["Girokonto"], konten["Girokonto Partnerin"], konten["Kreditkarte"], konten["Tagesgeld"]
con.executemany("INSERT INTO saldo_korrekturen (konto_id, datum, saldo, kommentar) VALUES (?, ?, ?, ?)", [
    (TG, "2026-06-30", 11000, "erste am Tag"), (TG, "2026-06-30", 11500, "zweite am Tag"),
])
con.commit()


def salden_30(c, k, tage):
    """Ist-Saldo nach der Regel von 3.0, unabhängig vom Programmcode (Fixpunkt,
    bei mehreren Korrekturen am selben Tag die zuerst angelegte, Befund AB)."""
    erg = {}
    for t in tage:
        f = c.execute("SELECT datum, saldo FROM saldo_korrekturen WHERE konto_id = ? AND datum <= ? "
                      "ORDER BY datum DESC, id LIMIT 1", (k, t)).fetchone()
        ab, basis = f if f else ("0001-01-01", 0.0)
        s = c.execute("""SELECT COALESCE(SUM(CASE WHEN typ = 'Ist' AND konto_id = :k THEN betrag
                             WHEN typ = 'Uebertragung' AND konto_id = :k THEN -betrag
                             WHEN typ = 'Uebertragung' AND zielkonto_id = :k THEN betrag ELSE 0 END), 0)
                         FROM buchungen WHERE datum >= :ab AND datum <= :t""", {"k": k, "ab": ab, "t": t}).fetchone()[0]
        erg[t] = round(basis + s, 2)
    return erg


TAGE = {k: sorted({r[0] for r in con.execute("SELECT datum FROM buchungen WHERE konto_id = ? OR zielkonto_id = ?", (k, k))}
                  | {r[0] for r in con.execute("SELECT datum FROM saldo_korrekturen WHERE konto_id = ?", (k,))})
        for k in konten.values()}
VORHER = {k: salden_30(con, k, TAGE[k]) for k in konten.values()}
# Differenz 0: Korrektur auf genau den Stand, den die Kreditkarte vor den
# Buchungen ihres letzten Buchungstags ohnehin hat (alte Regel: Stand vor den
# Buchungen des Tages)
tag_kk = TAGE[KK][-1]
vortag_kk = (date.fromisoformat(tag_kk) - timedelta(days=1)).isoformat()
con.execute("INSERT INTO saldo_korrekturen (konto_id, datum, saldo, kommentar) VALUES (?, ?, ?, 'gleich')",
            (KK, tag_kk, salden_30(con, KK, [vortag_kk])[vortag_kk]))
VORHER[KK] = salden_30(con, KK, TAGE[KK])
# Eigene Hauptkategorie „Anfangsbestand“ mit einer Buchung (wird übernommen)
eigen = con.execute("INSERT INTO kategorien (name, parent_id, typ) VALUES ('Anfangsbestand', NULL, 'einnahme')").lastrowid
con.execute("INSERT INTO buchungen (konto_id, datum, betrag, kategorie_id, typ, beschreibung) "
            "VALUES (?, '2025-01-02', 50, ?, 'Ist', 'eigener Anfangsbestand')", (GIRO2, eigen))
con.commit()
VORHER[GIRO2] = salden_30(con, GIRO2, sorted(set(TAGE[GIRO2]) | {"2025-01-02"}))
TAGE[GIRO2] = sorted(VORHER[GIRO2])
MAX_ID = con.execute("SELECT MAX(id) FROM buchungen").fetchone()[0]
con.close()

os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from app.main import app
import app.main as api
from app.core import zeit, db as db_modul

HEUTE = zeit.heute()

def ok(r):
    assert r.status_code < 300, (r.status_code, r.text)
    return r.json()

def salden_neu(c, k, tage, korr_ids):
    """Wie salden_30, ohne Fixpunkt. Ohne die Termine, die der Start nach der
    Umstellung neu bucht (nur bisherige Buchungen und die Korrekturbuchungen)."""
    ph = ",".join("?" * len(korr_ids))
    return {t: round(c.execute(f"""SELECT COALESCE(SUM(CASE WHEN typ = 'Ist' AND konto_id = ? THEN betrag
                             WHEN typ = 'Uebertragung' AND konto_id = ? THEN -betrag
                             WHEN typ = 'Uebertragung' AND zielkonto_id = ? THEN betrag ELSE 0 END), 0)
                         FROM buchungen WHERE datum <= ? AND (id <= ? OR kategorie_id IN ({ph}))""",
                               (k, k, k, t, MAX_ID, *korr_ids)).fetchone()[0], 2) for t in tage}

with TestClient(app) as c:
    # ═══ A. Migration ═══
    mig = ok(c.get("/api/start-status"))["migration"]
    m = " | ".join(mig)
    print("   Migration:", *mig, sep="\n     ")
    d = sqlite3.connect(DB); d.row_factory = sqlite3.Row
    kat = {r["system_key"]: r["id"] for r in d.execute("SELECT id, system_key FROM kategorien WHERE system_key IS NOT NULL")}
    KORR, AB, UMB = kat["korrekturbuchung"], kat["anfangsbestand"], kat["umbuchung"]
    pruef("A1 Systemkategorien neutral, eigene „Anfangsbestand“ übernommen und neutral",
          AB == eigen and d.execute("SELECT COUNT(*) FROM kategorien WHERE system_key IN ('korrekturbuchung', 'anfangsbestand') "
                                    "AND typ IS NULL AND parent_id IS NULL").fetchone()[0] == 2
          and "Eigene Kategorie „Anfangsbestand“ als feste Kategorie übernommen (1 Buchung(en)" in m, m)
    pruef("A2 Backup vor der Umstellung, Tabelle entfernt, Merker gesetzt",
          "Backup vor der Umstellung der Saldo-Korrekturen" in m
          and not d.execute("SELECT 1 FROM sqlite_master WHERE name = 'saldo_korrekturen'").fetchone()
          and d.execute("SELECT value FROM einstellungen WHERE key = 'migration_saldo_korrekturen_v31_erledigt'").fetchone()[0] == "1")
    bu = lambda k: [dict(r) for r in d.execute("SELECT * FROM buchungen WHERE konto_id = ? AND kategorie_id IN (?, ?) "
                                               "ORDER BY datum, id", (k, KORR, AB))]
    tg, gi, kk, g2 = bu(TG), bu(GIRO), bu(KK), bu(GIRO2)
    pruef("A3 Früheste ohne Buchungen davor wird Anfangsbestand (Tagesgeld 31.12.2025, 10.000 €)",
          tg[0]["kategorie_id"] == AB and tg[0]["datum"] == "2025-12-31" and tg[0]["betrag"] == 10000
          and tg[0]["beschreibung"] == "Anfangsbestand 10.000,00 €", tg[:1])
    pruef("A4 Korrektur mit früheren Buchungen wird Korrekturbuchung (Girokonto), kein Anfangsbestand",
          len(gi) == 1 and gi[0]["kategorie_id"] == KORR and gi[0]["beschreibung"].startswith("Saldo-Korrektur auf 4.200,00 €"), gi)
    pruef("A5 Zwei am selben Tag: erste K1 - Vortag, zweite K2 - K1 (500 €), Kommentar angehängt",
          [x["kategorie_id"] for x in tg[1:]] == [KORR, KORR] and tg[2]["betrag"] == 500
          and tg[2]["beschreibung"] == "Saldo-Korrektur auf 11.500,00 € – zweite am Tag", tg[1:])
    pruef("A6 Differenz 0: keine Buchung, Schritt genannt", not kk and "„Kreditkarte“" in m and "Differenz 0, keine Buchung" in m, kk)
    pruef("A7 Konto ohne Korrektur unverändert, eigener Anfangsbestand bleibt die einzige Buchung dort",
          [x["beschreibung"] for x in g2] == ["eigener Anfangsbestand"], g2)
    nachher = {k: salden_neu(d, k, TAGE[k], (KORR, AB)) for k in konten.values()}
    abw = {k: [(t, VORHER[k][t], nachher[k][t]) for t in TAGE[k] if VORHER[k][t] != nachher[k][t]] for k in konten.values()}
    pruef("A8 Pflicht: Ist-Saldo jedes Kontos an jedem Tag gleich, außer Tagesgeld ab dem Doppel-Tag",
          all(not abw[k] for k in konten.values() if k != TG)
          and abw[TG] and all(t >= "2026-06-30" and round(n - v, 2) == 500 for t, v, n in abw[TG]), abw)
    pruef("A9 Start-Status nennt die Abweichung mit Datum und Betrag und die Prüfung der übrigen Konten",
          "Abweichung „Tagesgeld“: Ist-Saldo ab dem 30.06.2026 um 500,00 €" in m
          and "Prüfung: Ist-Saldo der übrigen Konten" in m, m)
    with TestClient(app) as c2:
        pruef("A10 Zweiter Start ohne erneute Umstellung", not ok(c2.get("/api/start-status"))["migration"])
    d.close()

    # ═══ B. Neue Saldo-Korrektur ═══
    v = lambda **p: c.get("/api/saldo-korrekturen/vorschau", params=p)
    post = lambda **p: c.post("/api/saldo-korrekturen", json=p)
    saldo = lambda k: next(x["saldo"] for x in ok(c.get("/api/konten")) if x["id"] == k)
    morgen = (HEUTE + timedelta(days=1)).isoformat()
    r = post(konto_id=GIRO, datum=morgen, saldo=1)
    pruef("B1 Zukunftsdatum abgelehnt (422), auch in der Vorschau",
          r.status_code == 422 and "Zukunft" in r.text and v(konto_id=GIRO, datum=morgen, saldo=1).status_code == 422, r.text)
    s0 = saldo(GIRO)
    r = post(konto_id=GIRO, datum=HEUTE.isoformat(), saldo=s0)
    pruef("B2 Differenz 0: Vorschau 0, Buchen abgelehnt, nichts gebucht",
          ok(v(konto_id=GIRO, datum=HEUTE.isoformat(), saldo=s0))["differenz"] == 0 and r.status_code == 422
          and saldo(GIRO) == s0, r.text)
    lm = next(k["id"] for k in ok(c.get("/api/kategorien")) if k["name"] == "Lebensmittel/Verpflegung")
    gestern = (HEUTE - timedelta(days=1)).isoformat()
    ok(c.post("/api/buchungen", json={"konto_id": GIRO, "datum": gestern, "betrag": 40, "kategorie_id": lm, "beschreibung": "am Stichtag"}))
    s_g = ok(v(konto_id=GIRO, datum=gestern, saldo=1000))
    pruef("B3 Stichtag meint das Ende des Tages: Buchung des Tages ist im Saldo der App enthalten",
          s_g["saldo_app"] == round(s0 - 40, 2) and s_g["differenz"] == round(1000 - (s0 - 40), 2), s_g)
    r = post(konto_id=GIRO, datum=gestern, saldo=1000, differenz=s_g["differenz"] + 1)
    pruef("B4 Geänderte Differenz seit der Vorschau abgelehnt", r.status_code == 422 and "geändert" in r.text, r.text)
    k1 = ok(post(konto_id=GIRO, datum=gestern, saldo=1000, differenz=s_g["differenz"], kommentar="Auszug 12"))
    pruef("B5 Gebucht: Kategorie Korrekturbuchung, Beschreibung mit Kommentar, Saldo am Stichtag = Kontostand",
          ok(c.get(f"/api/buchungen/{k1['id']}"))["kategorie_id"] == KORR
          and k1["beschreibung"] == "Saldo-Korrektur auf 1.000,00 € – Auszug 12"
          and ok(v(konto_id=GIRO, datum=gestern, saldo=1000))["differenz"] == 0, k1)
    k2 = ok(post(konto_id=GIRO, datum=gestern, saldo=1100))
    pruef("B6 Zweite Korrektur am selben Tag bucht die Differenz zur ersten (100 €)",
          k2["betrag"] == 100 and ok(v(konto_id=GIRO, datum=gestern, saldo=1100))["differenz"] == 0, k2)
    ok(c.post("/api/buchungen", json={"konto_id": GIRO, "datum": gestern, "betrag": 10, "kategorie_id": lm}))
    pruef("B7 Später erfasste Buchung desselben Tages ändert den Endstand, Korrektur bleibt",
          ok(v(konto_id=GIRO, datum=gestern, saldo=1100))["differenz"] == 10
          and ok(c.get(f"/api/buchungen/{k2['id']}"))["betrag"] == 100)
    r = c.put(f"/api/buchungen/{k1['id']}", json={"konto_id": GIRO, "datum": gestern, "betrag": 5, "kategorie_id": KORR})
    r2 = c.put(f"/api/buchungen/{k1['id']}", json={"konto_id": GIRO, "datum": gestern, "betrag": 5, "kategorie_id": lm})
    pruef("B8 Korrekturbuchung nicht änderbar (Betrag, Kategorie)", r.status_code == 400 and r2.status_code == 400
          and "nicht ändern" in r.text, (r.text, r2.text))
    vor = saldo(GIRO)
    ok(c.delete(f"/api/buchungen/{k2['id']}"))
    pruef("B9 Löschen ändert den Saldo um den Betrag der Korrektur", round(vor - saldo(GIRO), 2) == 100, (vor, saldo(GIRO)))

    # Feld „Anfangsbestand“
    neu = ok(c.post("/api/konten", json={"name": "Konto 31", "typ": "Girokonto", "eroeffnungsdatum": "2026-02-01"}))["id"]
    i = ok(v(konto_id=neu))
    pruef("B10 Konto ohne Buchung: Feld sichtbar und vorbelegt, Eröffnungsdatum als Vorschlag",
          i["anfangsbestand_moeglich"] and i["anfangsbestand_vorbelegt"] and i["eroeffnungsdatum"] == "2026-02-01", i)
    ok(c.post("/api/buchungen", json={"konto_id": neu, "datum": "2027-12-01", "betrag": 5, "kategorie_id": lm, "typ": "Plan"}))
    pruef("B11 Plan-Buchung zählt nicht als Buchung (Feld bleibt vorbelegt)", ok(v(konto_id=neu))["anfangsbestand_vorbelegt"])
    ue = ok(c.post("/api/buchungen", json={"konto_id": GIRO, "zielkonto_id": neu, "datum": "2026-03-01", "betrag": 20,
                                         "typ": "Uebertragung"}))["id"]
    i = ok(v(konto_id=neu))
    pruef("B12 Übertragung als Ziel zählt: Feld sichtbar, nicht vorbelegt", i["anfangsbestand_moeglich"] and not i["anfangsbestand_vorbelegt"], i)
    a = ok(post(konto_id=neu, datum="2026-02-01", saldo=250, anfangsbestand=True))
    pruef("B13 Anfangsbestand mit Buchungen danach: Differenz zum Saldo am Stichtag, Kategorie Anfangsbestand",
          a["betrag"] == 250 and a["beschreibung"] == "Anfangsbestand 250,00 €"
          and ok(c.get(f"/api/buchungen/{a['id']}"))["kategorie_id"] == AB and saldo(neu) == 270, (a, saldo(neu)))
    i = ok(v(konto_id=neu)); r = post(konto_id=neu, datum="2026-02-01", saldo=300, anfangsbestand=True)
    pruef("B14 Zweiter Anfangsbestand: Feld weg, Buchen abgelehnt", not i["anfangsbestand_moeglich"]
          and r.status_code == 422 and "schon einen Anfangsbestand" in r.text, r.text)
    ok(c.delete(f"/api/buchungen/{a['id']}"))
    pruef("B15 Nach dem Löschen ist das Feld wieder da (nicht vorbelegt)",
          ok(v(konto_id=neu))["anfangsbestand_moeglich"] and not ok(v(konto_id=neu))["anfangsbestand_vorbelegt"])
    a = ok(post(konto_id=neu, datum="2026-02-01", saldo=250, anfangsbestand=True))
    kor = ok(post(konto_id=neu, datum="2026-03-15", saldo=300))  # Saldo 270 -> +30

    # Cashflow, Kategorien, Jahresübersicht, Budgets
    cf = ok(c.get(f"/api/auswertungen/cashflow?von=2026-02-01&bis=2026-03-31&konten={neu}"))
    pruef("B16 Cashflow zählt die Korrekturbuchung, aber nicht den Anfangsbestand",
          cf["einnahmen"] == [0.0, 30.0] and cf["ausgaben"] == [0.0, 0.0], cf)
    wurzel = next(k["id"] for k in ok(c.get("/api/kategorien")) if k["name"] == "Ausgaben")
    b = ok(c.post("/api/budgets", json={"name": "Alles", "typ": "ausgabe", "kategorie_id": wurzel, "betrag": 10,
                                        "inkl_unterkategorien": True, "zeitraum": "monatlich", "startdatum": "2026-03-01"}))["id"]
    vb0 = ok(c.get(f"/api/budgets/details/verlauf?budget_id={b}&von=2026-03&bis=2026-03"))
    ok(post(konto_id=neu, datum="2026-03-20", saldo=280))  # -20 als Ausgabe
    cf = ok(c.get(f"/api/auswertungen/cashflow?von=2026-03-01&bis=2026-03-31&konten={neu}"))
    pruef("B17 Negative Korrektur zählt als Ausgabe", cf["einnahmen"] == [30.0] and cf["ausgaben"] == [20.0], cf)
    vb1 = ok(c.get(f"/api/budgets/details/verlauf?budget_id={b}&von=2026-03&bis=2026-03"))
    pruef("B20 Budget „Ausgaben“ samt Unterkategorien zählt die negative Korrektur nicht", vb0 == vb1, (vb0, vb1))
    c.delete(f"/api/budgets/{b}")
    kz = ok(c.get(f"/api/auswertungen/kategorien?von=2025-01-01&bis={HEUTE.isoformat()}"))
    jk = ok(c.get("/api/auswertungen/jahresuebersicht?modus=kalenderjahr&jahr=2026"))
    namen = {x["kategorie"] for x in kz} | {x["kategorie"] for x in jk.get("kategorien", [])}
    pruef("B18 Kategorien-Auswertung und Jahresübersicht ohne Korrekturbuchung und Anfangsbestand",
          not namen & {"Korrekturbuchung", "Anfangsbestand"}, namen)
    for kid, n in ((KORR, "Korrekturbuchung"), (AB, "Anfangsbestand")):
        r = c.post("/api/budgets", json={"name": "B", "typ": "ausgabe", "kategorie_id": kid, "betrag": 10,
                                         "zeitraum": "monatlich", "startdatum": "2026-01-01"})
        pruef(f"B19 Kein Budget auf „{n}“ (422)", r.status_code == 422, r.text)
    kats = ok(c.get("/api/kategorien"))
    pruef("B21 /api/kategorien: beide gesperrt und als Korrektur markiert, Umbuchung gesperrt",
          all(k["gesperrt"] and k["korrektur"] for k in kats if k["id"] in (KORR, AB))
          and next(k for k in kats if k["id"] == UMB)["gesperrt"])

    # ═══ C. Sperre der Kategorien an allen Wegen (#12 und Befund AA) ═══
    for kid, n in ((KORR, "Korrekturbuchung"), (AB, "Anfangsbestand"), (UMB, "Umbuchung")):
        r = c.post("/api/buchungen", json={"konto_id": GIRO, "datum": gestern, "betrag": 5, "kategorie_id": kid})
        pruef(f"C1 Formular: „{n}“ abgelehnt", r.status_code == 400 and n in r.text, r.text)
        bid = ok(c.post("/api/buchungen", json={"konto_id": GIRO, "datum": gestern, "betrag": 5, "kategorie_id": lm}))["id"]
        r = c.put(f"/api/buchungen/{bid}", json={"konto_id": GIRO, "datum": gestern, "betrag": 5, "kategorie_id": kid})
        pruef(f"C2 Bearbeiten: Buchung nicht nach „{n}“ verschiebbar", r.status_code == 400, r.text)
        c.delete(f"/api/buchungen/{bid}")
        r = c.post("/api/wiederkehrend", json={"konto_id": GIRO, "betrag": 5, "kategorie_id": kid, "intervall": "monatlich",
                                              "tag_des_monats": 3, "startdatum": "2027-01-01"})
        pruef(f"C3 Vorlage: „{n}“ abgelehnt (422)", r.status_code == 422, r.text)
        r = c.post("/api/erfassen/buchung", json={"konto_id": GIRO, "datum": gestern, "betrag": 5, "kategorie_id": kid})
        pruef(f"C4 Schnellbuchung: „{n}“ abgelehnt", r.status_code == 400, r.text)
        r = c.post("/api/regeln", json={"muster": "x31", "kategorie_id": kid})
        pruef(f"C5 Kategorie-Regel: „{n}“ abgelehnt (422)", r.status_code == 422, r.text)
        r = c.put(f"/api/siri/favoriten/{kid}?aktiv=true")
        pruef(f"C6 Siri-Favorit: „{n}“ abgelehnt", r.status_code == 400, r.text)
        r = c.post("/api/siri/buchung", json={"betrag": 1, "konto": "Kreditkarte", "kategorie": n})
        pruef(f"C7 Siri: „{n}“ gilt als unbekannt", r.status_code == 400 and "nicht gefunden" in r.text, r.text)
        try:
            con_ = db_modul.verbindung()
            api._stapel_buchen(con_, {"quelle": "schnellbuchung", "konto_id": GIRO, "datum": gestern, "betrag": 5,
                                      "kategorie_id": kid, "typ": "Ist"})
            stapel = "gebucht"
        except Exception as e:   # stapel_abarbeiten legt den Eintrag dann in die Klärliste
            stapel = str(getattr(e, "detail", e))
        finally:
            con_.rollback(); con_.close()
        pruef(f"C8 Stapel: „{n}“ abgelehnt (Eintrag käme in die Klärliste)", stapel != "gebucht", stapel)
        con_ = sqlite3.connect(DB)
        eid = con_.execute("INSERT INTO klaerliste (quelle, erfasst_am, daten, grund) VALUES ('siri', '', '{}', 'Test')").lastrowid
        con_.commit(); con_.close()
        r = c.post(f"/api/klaerliste/{eid}/buchen", json={"konto_id": GIRO, "datum": gestern, "betrag": 5, "kategorie_id": kid})
        pruef(f"C9 Klärliste: „{n}“ abgelehnt, Eintrag bleibt", r.status_code == 400
              and any(x["id"] == eid for x in ok(c.get("/api/klaerliste"))), r.text)
        c.delete(f"/api/klaerliste/{eid}")
        av = {"bezeichnung": "AV31", "zahlungskonto_id": GIRO, "stand_datum": "2026-01-01", "hat_einzahlung": True,
              "beitrag_kategorie_id": kid, "beitrag_betrag": 10, "beitrag_intervall": "monatlich", "beitrag_tag_des_monats": 1,
              "beitrag_startdatum": "2027-01-01", "rentenbeginn": "2040-01-01", "auszahlungsart": "rente",
              "auszahlung_kategorie_id": lm, "rente_garantiert_betrag": 1}
        r = c.post("/api/altersvorsorge", json=av)
        pruef(f"C10 Altersvorsorge-Beitrag: „{n}“ abgelehnt (422)", r.status_code == 422, r.text)
    r = c.post("/api/kategorien", json={"name": "Unter", "parent_id": KORR})
    pruef("C11 Keine Unterkategorie unter „Korrekturbuchung“", r.status_code == 400, r.text)
    frei = ok(c.post("/api/kategorien", json={"name": "Frei31", "parent_id": None}))["id"]
    r = c.put(f"/api/kategorien/{frei}", json={"name": "Frei31", "parent_id": AB})
    r2 = c.put(f"/api/kategorien/{KORR}", json={"name": "Anders", "parent_id": None})
    r3 = c.delete(f"/api/kategorien/{AB}")
    pruef("C12 Kategorie nicht hineinschiebbar, feste weder änderbar noch löschbar",
          r.status_code == 400 and r2.status_code == 400 and r3.status_code == 400, (r.text, r2.text, r3.text))
    # Eine alte Regel auf eine gesperrte Kategorie (vor 3.1 möglich)
    con_ = sqlite3.connect(DB); con_.execute("INSERT INTO kategorie_regeln (muster, kategorie_id) VALUES ('altregel31', ?)", (KORR,))
    con_.commit(); con_.close()
    r = c.post("/api/buchungen", json={"konto_id": GIRO, "datum": gestern, "betrag": 5, "beschreibung": "altregel31"})
    pruef("C13 Alte Regel auf gesperrte Kategorie: Buchung darüber wird nicht in die gesperrte Kategorie gelegt", r.status_code == 400
          and "Kategorie fehlt" in r.text, r.text)
    vorher_umb = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM buchungen WHERE typ = 'Uebertragung'").fetchone()[0]
    ok(c.post("/api/buchungen", json={"konto_id": GIRO, "zielkonto_id": TG, "datum": gestern, "betrag": 3, "typ": "Uebertragung"}))
    pruef("C14 Übertragungen bekommen „Umbuchung“ weiter", sqlite3.connect(DB).execute(
        "SELECT COUNT(*) FROM buchungen WHERE typ = 'Uebertragung'").fetchone()[0] == vorher_umb + 1)

    # ═══ D. XLSX ═══
    def export():
        r = c.get("/api/admin/export"); assert r.status_code == 200, r.text
        return load_workbook(io.BytesIO(r.content))
    def hoch(wb):
        b = io.BytesIO(); wb.save(b)
        return ok(c.post("/api/admin/import/vorschau", files={"datei": ("t.xlsx", b.getvalue())}))
    def spalten(ws):
        return {ws.cell(1, i).value: i for i in range(1, ws.max_column + 1)}
    wb = export(); vx = hoch(wb)
    pruef("D1 Export unverändert hochladen: 0 Änderungen, 0 Fehler (Korrekturen bleiben in der Datei)",
          vx["aenderungen"] == 0 and vx["fehler"] == 0, vx)
    ws = wb["Buchungen"]; sp = spalten(ws)
    zeile = next(r for r in range(2, ws.max_row + 1) if ws.cell(r, sp["id"]).value == kor["id"])
    ws.cell(zeile, sp["betrag"], 99)
    neu_z = ws.max_row + 1
    for f, w in (("datum", HEUTE), ("konto", "Girokonto"), ("typ", "Ist"), ("betrag", 5), ("kategorie", "Korrekturbuchung")):
        ws.cell(neu_z, sp[f], w)
    andere = next(r for r in range(2, ws.max_row) if "Lebensmittel" in str(ws.cell(r, sp["kategorie"]).value))
    ws.cell(andere, sp["kategorie"], "Anfangsbestand")
    fehler = [f["hinweis"] for b in hoch(wb)["bereiche"] for f in b["fehler"]]
    pruef("D2 Ändern und Neuanlage von Korrekturen sowie Umhängen in „Anfangsbestand“ per Datei: Zeilenfehler",
          sum("nur löschen" in f for f in fehler) == 3, fehler)
    wb = export(); ws = wb["Buchungen"]; sp = spalten(ws)
    zeile = next(r for r in range(2, ws.max_row + 1) if ws.cell(r, sp["id"]).value == kor["id"])
    ws.cell(zeile, sp["aktion"], "löschen")
    vx = hoch(wb)
    pruef("D3 Löschen per Datei erlaubt, Ergebnis nennt den Saldo-Effekt",
          vx["fehler"] == 0 and vx["token"] and any("Der Saldo ändert sich ab dem 15.03.2026 um -30,00 €" in h
                                                    for h in vx["hinweise"]), vx["hinweise"])
    s_vor = saldo(neu)
    ok(c.post("/api/admin/import/ausfuehren", json={"token": vx["token"]}))
    pruef("D4 Nach dem Import ist die Korrektur weg, Saldo um 30 € kleiner", round(s_vor - saldo(neu), 2) == 30)

    # ═══ E. Daten zurücksetzen ═══
    z = ok(c.post("/api/admin/zuruecksetzen/vorschau", json={"arten": ["ist_buchungen"], "ist_bis": HEUTE.isoformat()}))
    zus = {x["label"]: x["anzahl"] for x in z["zeilen"][0]["zusatz"]}
    n_korr = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM buchungen WHERE kategorie_id IN (?, ?) AND datum <= ?",
                                         (KORR, AB, HEUTE.isoformat())).fetchone()[0]
    pruef("E1 Ist-Buchungen löschen: Vorschau nennt Korrekturen und Anfangsbestände", zus.get(
        "davon Saldo-Korrekturen und Anfangsbestände (werden mitgelöscht)") == n_korr and n_korr > 0, zus)
    z = ok(c.post("/api/admin/zuruecksetzen/vorschau", json={"arten": ["konten_loeschen"], "konten_loeschen_ids": [neu], "ziel_konto_id": TG}))
    zus = {x["label"]: x["anzahl"] for x in z["zeilen"][0]["zusatz"]}
    pruef("E2 Zusammenführen: Anfangsbestand wird Korrekturbuchung (Ziel hat schon einen), keine Saldowarnung",
          zus.get("Anfangsbestände werden zu Korrekturbuchungen (je Konto nur einer, zählen dann im Cashflow)") == 1
          and not any("Summe der Kontostände" in w for w in z["warnungen"]), (zus, z["warnungen"]))
    summe = saldo(neu) + saldo(TG)
    ok(c.post("/api/admin/zuruecksetzen/ausfuehren", json={"arten": ["konten_loeschen"], "konten_loeschen_ids": [neu],
                                                          "ziel_konto_id": TG, "token": z["token"], "phrase": z["phrase"]}))
    d = sqlite3.connect(DB)
    pruef("E3 Nach dem Zusammenführen: Summe gleich, Ziel hat genau einen Anfangsbestand, übernommener ist Korrektur",
          round(saldo(TG) - summe, 2) == 0
          and d.execute("SELECT COUNT(*) FROM buchungen WHERE konto_id = ? AND kategorie_id = ?", (TG, AB)).fetchone()[0] == 1
          and d.execute("SELECT kategorie_id FROM buchungen WHERE id = ?", (a["id"],)).fetchone()[0] == KORR,
          (saldo(TG), summe))
    d.close()

# ═══ F. Gegenprobe mit dem Code von 3.0 ═══
if code_alt:
    ordner = ziel + "_30"
    shutil.rmtree(ordner, ignore_errors=True); shutil.copytree(quelle, ordner)
    programm = (f"import json, sys\nsys.path.insert(0, {code_alt!r})\nfrom fastapi.testclient import TestClient\n"
                "from app.main import app\nwith TestClient(app) as c:\n"
                "    k = c.get('/api/kategorien').json(); umb = next(x['id'] for x in k if x['system_key'] == 'umbuchung')\n"
                "    g = c.get('/api/konten').json()[0]['id']\n"
                "    e = {'buchung': c.post('/api/buchungen', json={'konto_id': g, 'datum': '2026-10-01', 'betrag': 5, 'kategorie_id': umb}).status_code,\n"
                "         'regel': c.post('/api/regeln', json={'muster': 'x', 'kategorie_id': umb}).status_code,\n"
                "         'vorschau': c.get('/api/saldo-korrekturen/vorschau?konto_id=1').status_code}\n"
                "    print('ERGEBNIS ' + json.dumps(e))\n")
    r = subprocess.run([sys.executable, "-c", programm], env={**os.environ, "FINANZAPP_DATENVERZEICHNIS": ordner},
                       capture_output=True, text=True, timeout=300)
    e = json.loads(next(z for z in r.stdout.splitlines() if z.startswith("ERGEBNIS "))[9:]) if "ERGEBNIS " in r.stdout else {}
    pruef("F1 Gegenprobe 3.0: Buchung und Regel auf „Umbuchung“ gingen durch (Befund AA), keine Vorschau",
          e.get("buchung") == 200 and e.get("regel") == 200 and e.get("vorschau") in (404, 405), (e, r.stderr[-500:]))
    pruef("F2 Gegenprobe 3.0: Tabelle saldo_korrekturen bleibt, keine Korrekturkategorien",
          sqlite3.connect(os.path.join(ordner, "finanzdaten.db")).execute(
              "SELECT COUNT(*) FROM saldo_korrekturen").fetchone()[0] == 2
          and not sqlite3.connect(os.path.join(ordner, "finanzdaten.db")).execute(
              "SELECT 1 FROM kategorien WHERE system_key = 'korrekturbuchung'").fetchone())

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

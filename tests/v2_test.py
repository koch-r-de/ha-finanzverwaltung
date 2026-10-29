"""Fachliche Tests Version 2.0 (Punkte 1-5, Befund H, XLSX-Roundtrip)."""
import os, sys, shutil, io, sqlite3, re
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
quelle, ziel = sys.argv[2], sys.argv[3]
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
# künftige Saldo-Korrektur in die 1.10-Datenbank schreiben (Migrationstest Punkt 2)
db = sqlite3.connect(os.path.join(ziel, "finanzdaten.db"))
db.execute("INSERT INTO saldo_korrekturen (konto_id, datum, saldo, kommentar) VALUES (3, '2027-03-01', 99999, 'Test künftig')")
db.execute("INSERT INTO saldo_korrekturen (konto_id, datum, saldo, kommentar) VALUES (3, '2026-10-01', 10500, 'Test vergangen')")
db.commit(); db.close()
os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, sys.argv[1])
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from app.main import app
from app.core import zeit

HEUTE = zeit.heute()
ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""))
def ok(r):
    assert r.status_code < 300, (r.status_code, r.text)
    return r.json()

with TestClient(app) as c:
    st = ok(c.get("/api/start-status"))
    K = {k["name"]: k["id"] for k in ok(c.get("/api/konten?nur_aktive=false"))}
    KAT = {k["name"]: k["id"] for k in ok(c.get("/api/kategorien"))}
    giro, tg, giro2 = K["Girokonto"], K["Tagesgeld"], K["Girokonto Partnerin"]

    # ── Befund H ──
    pruef("H: Serverzeit in Europe/Berlin", st.get("zeitzone") == "Europe/Berlin" and st.get("serverzeit"), st.get("serverzeit"))
    pruef("H: zeit.heute() = Berliner Datum", zeit.jetzt().tzinfo is not None and str(zeit.ZEITZONE) == "Europe/Berlin")
    rest = [p for p in __import__("glob").glob(os.path.join(sys.argv[1], "app", "**", "*.py"), recursive=True)
            if p.endswith(".py") and not p.endswith("zeit.py") and re.search(r"date\.today\(\)|datetime\.now\(\)(?!\.astimezone)", open(p, encoding="utf-8").read())]
    pruef("H: kein date.today()/datetime.now() mehr im Code (außer Anzeige Container-Zone)", not rest, rest)

    # ── Punkt 2 ──
    mig = " ".join(st["migration"])
    pruef("P2: Migration löscht künftige Korrektur und nennt sie", "Künftig datierte Saldo-Korrektur gelöscht" in mig and "2027-03-01" in mig, st["migration"])
    with sqlite3.connect(os.path.join(ziel, "finanzdaten.db")) as d2:
        rest_k = d2.execute("SELECT datum FROM saldo_korrekturen WHERE kommentar LIKE 'Test%'").fetchall()
    pruef("P2: vergangene Korrektur bleibt", rest_k == [("2026-10-01",)], rest_k)
    with TestClient(app) as c2:
        pruef("P2: zweiter Start ohne erneute Migration", not any("Saldo-Korrektur" in m for m in ok(c2.get("/api/start-status"))["migration"]))
    morgen = (HEUTE + timedelta(days=1)).isoformat()
    r = c.post("/api/saldo-korrekturen", json={"konto_id": giro, "datum": morgen, "saldo": 1})
    pruef("P2: Korrektur mit Datum morgen -> 422", r.status_code == 422, r.text)
    r = c.post("/api/saldo-korrekturen", json={"konto_id": giro2, "datum": HEUTE.isoformat(), "saldo": -315})
    pruef("P2: Korrektur mit Datum heute erlaubt", r.status_code == 200, r.text)

    # ── Punkt 1 ──
    monatsende = (date(HEUTE.year, HEUTE.month, 1) + relativedelta(months=1) - timedelta(days=1))
    lfd = HEUTE.strftime("%Y-%m")
    # Befund V (3.0): Die Testdaten haben ihre letzte Einnahme am 28. (Gehalt).
    # Ab dann gäbe es im laufenden Monat keine anstehende Einnahme mehr. Eine
    # eigene Vorlage am letzten Bankarbeitstag des Monats hält die Prüfung
    # unabhängig vom Testtag. Ist heute schon dieser Tag, entfällt nur die
    # Forderung „anstehend > 0“.
    from app.core import feiertage as _ft
    letzter_bt = _ft.vorheriger_werktag(monatsende, _ft.bank_kalender())
    test_einnahme = None
    if letzter_bt > HEUTE:
        test_einnahme = ok(c.post("/api/wiederkehrend", json={"konto_id": giro, "betrag": 123, "kategorie_id": KAT["Gehalt & Lohn"],
            "intervall": "monatlich", "tag_des_monats": letzter_bt.day, "startdatum": letzter_bt.isoformat(),
            "enddatum": letzter_bt.isoformat(), "beschreibung": "Testeinnahme Monatsende"}))["id"]
    anst = [b for b in ok(c.get(f"/api/buchungen?inkl_anstehende=true&bis={monatsende.isoformat()}")) if b.get("virtuell")]
    anst_ein = round(sum(b["betrag"] for b in anst if b["betrag"] > 0 and b["typ"] != "Uebertragung"), 2)
    anst_aus = round(sum(-b["betrag"] for b in anst if b["betrag"] < 0 and b["typ"] != "Uebertragung"), 2)
    # Befund Y (3.0): ab dem Monatsersten, wie die gebuchten Einnahmen unten und
    # die Jahresübersicht. Ab heute fehlte nach dem 28. das schon gebuchte Gehalt.
    cf = ok(c.get(f"/api/auswertungen/cashflow?von={lfd}-01&bis={(HEUTE + relativedelta(months=3)).isoformat()}"))
    i = cf["monate"].index(lfd)
    pruef("P1: Cashflow liefert anstehenden Anteil des laufenden Monats",
          cf["einnahmen_anstehend"][i] == anst_ein and cf["ausgaben_anstehend"][i] == anst_aus and (anst_ein > 0 or test_einnahme is None),
          (cf["einnahmen_anstehend"][i], anst_ein, cf["ausgaben_anstehend"][i], anst_aus))
    pruef("P1: anstehender Anteil nur im laufenden Monat", all(v == 0 for j, v in enumerate(cf["einnahmen_anstehend"]) if j != i))
    gebucht_ein = sum(b["betrag"] for b in ok(c.get(f"/api/buchungen?von={lfd}-01&bis={monatsende.isoformat()}"))
                      if b["typ"] in ("Ist", "Plan") and b["betrag"] > 0)
    pruef("P1: Cashflow lfd. Monat = gebucht + anstehend", round(cf["einnahmen"][i], 2) == round(gebucht_ein + anst_ein, 2),
          (cf["einnahmen"][i], gebucht_ein, anst_ein))
    sv = ok(c.get(f"/api/auswertungen/saldo-verlauf?von={HEUTE.isoformat()}&bis={(HEUTE + relativedelta(months=2)).isoformat()}&konto_id={giro}"))
    saldo_heute = next(k["saldo"] for k in ok(c.get("/api/konten")) if k["id"] == giro)
    anst_giro = round(sum((b["betrag"] if b["typ"] != "Uebertragung" else (-b["betrag"] if b["konto_id"] == giro else b["betrag"]))
                          for b in anst if giro in (b["konto_id"], b.get("zielkonto_id"))), 2)
    pruef("P1: Saldo-Verlauf lfd. Monat = heutiger Saldo + anstehende Termine", round(sv["konten"][0]["werte"][0], 2) == round(saldo_heute + anst_giro, 2),
          (sv["konten"][0]["werte"][0], saldo_heute, anst_giro))
    pruef("P1: Prognose-Markierung ab laufendem Monat", sv["prognose_ab_index"] == 0, sv["prognose_ab_index"])
    jahr = ok(c.get("/api/auswertungen/jahresuebersicht"))
    lm = next(m for m in jahr["monate"] if m["monat"] == lfd)
    pruef("P1: Jahresübersicht lfd. Monat enthält anstehende Termine", lm["anstehend"] > 0 and lm["einnahmen"] == round(cf["einnahmen"][i], 2), lm)
    if test_einnahme:
        c.delete(f"/api/wiederkehrend/{test_einnahme}")
    # Budget-Details: Vorlage Lebensmittel am Monatsende
    letzter = monatsende if monatsende.weekday() < 5 else monatsende - timedelta(days=monatsende.weekday() - 4)
    vid = ok(c.post("/api/wiederkehrend", json={"konto_id": giro, "betrag": 77, "kategorie_id": KAT["Lebensmittel/Verpflegung"],
        "intervall": "monatlich", "tag_des_monats": letzter.day, "startdatum": letzter.isoformat(), "enddatum": letzter.isoformat(),
        "beschreibung": "Testeinkauf Monatsende"}))["id"]
    leb = next(b for b in ok(c.get("/api/budgets")) if b["name"] == "Lebensmittel")
    vb = ok(c.get(f"/api/budgets/details/verlauf?budget_id={leb['id']}"))
    j = vb["monate"].index(lfd)
    pruef("P1: Budget-Details: anstehender Termin als Aufsatz im lfd. Monat", vb["prognose"][j] == 77.0 and vb["verbrauch"][j] is not None, (vb["prognose"][j], vb["verbrauch"][j]))
    c.delete(f"/api/wiederkehrend/{vid}")

    # ── Punkt 3 ──
    v5 = (HEUTE + relativedelta(years=5)).isoformat()
    cf_n = ok(c.get(f"/api/auswertungen/cashflow?von={HEUTE.isoformat()}&bis={v5}"))
    cf_i = ok(c.get(f"/api/auswertungen/cashflow?von={HEUTE.isoformat()}&bis={v5}&inflation=true"))
    pruef("P3: Cashflow ohne Schalter nominal, mit Schalter höhere Ausgaben (Miete mit Häkchen)",
          cf_i["ausgaben"][-2] > cf_n["ausgaben"][-2] and cf_i["einnahmen"][-2] == cf_n["einnahmen"][-2],
          (cf_n["ausgaben"][-2], cf_i["ausgaben"][-2]))
    sv_n = ok(c.get(f"/api/auswertungen/saldo-verlauf?von={HEUTE.isoformat()}&bis={v5}&konto_id={giro}"))
    sv_i = ok(c.get(f"/api/auswertungen/saldo-verlauf?von={HEUTE.isoformat()}&bis={v5}&konto_id={giro}&inflation=true"))
    pruef("P3: Saldo-Verlauf mit Inflation niedriger (höhere Miete)", sv_i["konten"][0]["werte"][-1] < sv_n["konten"][0]["werte"][-1])
    b_n = [b for b in ok(c.get("/api/buchungen?inkl_anstehende=true")) if b.get("virtuell") and b["beschreibung"] == "Miete"]
    b_i = [b for b in ok(c.get("/api/buchungen?inkl_anstehende=true&inflation=true")) if b.get("virtuell") and b["beschreibung"] == "Miete"]
    pruef("P3: Buchungsliste: Miete nominal -950, mit Schalter hochgerechnet",
          all(b["betrag"] == -950 for b in b_n) and b_i[-1]["betrag"] < -950, (b_n[-1]["betrag"], b_i[-1]["betrag"]))
    kat_n = {k["kategorie"]: k["summe"] for k in ok(c.get(f"/api/auswertungen/kategorien?von={HEUTE.isoformat()}&bis={v5}"))}
    kat_i = {k["kategorie"]: k["summe"] for k in ok(c.get(f"/api/auswertungen/kategorien?von={HEUTE.isoformat()}&bis={v5}&inflation=true"))}
    pruef("P3: Kategorien-Diagramm Wohnen nur mit Schalter höher", kat_i["Wohnen"] > kat_n["Wohnen"], (kat_n.get("Wohnen"), kat_i.get("Wohnen")))
    jn = ok(c.get("/api/auswertungen/jahresuebersicht"))
    pruef("P3: Jahresübersicht akzeptiert Schalter", ok(c.get("/api/auswertungen/jahresuebersicht?inflation=true"))["summe_ausgaben"] >= jn["summe_ausgaben"])

    # ── Punkt 4 ──
    sz = ok(c.get("/api/sparziele"))[0]
    stand = lambda: next(b for b in ok(c.get("/api/budgets")) if b["id"] == sz["id"])["verbrauch"]
    s0 = stand()
    r = c.post("/api/buchungen", json={"konto_id": tg, "zielkonto_id": giro, "datum": HEUTE.isoformat(), "betrag": 100,
        "typ": "Uebertragung", "sparziel_id": sz["id"], "beschreibung": "Entnahme"})
    pruef("P4: Entnahme vom Trägerkonto erlaubt", r.status_code == 200, r.text)
    entnahme_id = r.json()["id"]
    pruef("P4: Entnahme senkt den Stand", round(stand() - s0, 2) == -100, (s0, stand()))
    r = c.post("/api/buchungen", json={"konto_id": giro, "datum": HEUTE.isoformat(), "betrag": 5, "kategorie_id": KAT["Lebensmittel/Verpflegung"],
        "typ": "Ist", "sparziel_id": sz["id"]})
    pruef("P4: Ist-Buchung mit Sparziel -> 422", r.status_code == 422, r.text)
    r = c.post("/api/buchungen", json={"konto_id": giro, "zielkonto_id": giro2, "datum": HEUTE.isoformat(), "betrag": 5,
        "typ": "Uebertragung", "sparziel_id": sz["id"]})
    pruef("P4: Übertragung ohne Trägerkonto mit Sparziel -> 422", r.status_code == 422 and "Tagesgeld" in r.text, r.text)
    r = c.post("/api/wiederkehrend", json={"konto_id": giro, "zielkonto_id": giro2, "betrag": 10, "intervall": "monatlich",
        "tag_des_monats": 1, "startdatum": "2027-01-01", "sparziel_id": sz["id"]})
    pruef("P4: Umbuchungs-Vorlage ohne Trägerkonto mit Sparziel -> 422", r.status_code == 422, r.text)
    bud = next(b for b in ok(c.get("/api/budgets")) if b["id"] == sz["id"])
    r = c.put(f"/api/budgets/{sz['id']}", json={"name": bud["name"], "typ": "sparziel", "konto_id": giro, "betrag": bud["betrag"],
        "zielbetrag": bud["zielbetrag"], "startdatum": bud["startdatum"], "zeitraum": bud["zeitraum"]})
    pruef("P4: Trägerkonto-Wechsel mit Zuordnungen -> 422", r.status_code == 422 and "Übertragung" in r.text, r.text)
    r = c.put(f"/api/budgets/{sz['id']}", json={"name": bud["name"] + " neu", "typ": "sparziel", "konto_id": tg, "betrag": bud["betrag"],
        "zielbetrag": bud["zielbetrag"], "startdatum": bud["startdatum"], "zeitraum": bud["zeitraum"]})
    pruef("P4: andere Änderungen am Sparziel weiter möglich", r.status_code == 200, r.text)
    with sqlite3.connect(os.path.join(ziel, "finanzdaten.db")) as d3:
        d3.execute(f"UPDATE buchungen SET sparziel_id = {sz['id']} WHERE beschreibung = 'Einkauf 0'")
    k = ok(c.get("/api/sparziele/konflikte"))
    pruef("P4: Prüfung findet Ist-Buchung mit Sparziel", len(k["buchungen"]) == 1 and k["buchungen"][0]["beschreibung"] == "Einkauf 0", k)
    pruef("P4: Unstimmige Zuordnung zählt nicht zum Stand", round(stand() - s0, 2) == -100)
    with TestClient(app) as c2:
        pruef("P4: Start-Status meldet Konflikt", ok(c2.get("/api/start-status"))["sparziel_konflikte"] == 1)
    r = ok(c.post("/api/sparziele/konflikte/loesen", json={"buchung_ids": [k["buchungen"][0]["id"], entnahme_id], "vorlage_ids": []}))
    pruef("P4: Lösen nur für echte Konflikte (Entnahme bleibt)", r["geloest"] == 1 and not ok(c.get("/api/sparziele/konflikte"))["buchungen"], r)

    # ── Punkt 5 ──
    av = ok(c.post("/api/altersvorsorge", json={"bezeichnung": "Test-AV", "zahlungskonto_id": giro, "stand_datum": "2026-01-01",
        "hat_einzahlung": True, "beitrag_kategorie_id": KAT["Altersvorsorge"], "beitrag_betrag": 100, "beitrag_intervall": "monatlich",
        "beitrag_tag_des_monats": 1, "beitrag_startdatum": "2026-01-01", "rentenbeginn": "2027-01-01", "auszahlungsart": "rente",
        "auszahlung_kategorie_id": KAT["Rente"], "rente_garantiert_betrag": 500}))["id"]
    def av_b():
        bs = [b for b in ok(c.get("/api/buchungen")) if b.get("ziel_altersvorsorge_id") == av]
        return sorted(b["datum"] for b in bs if b["betrag"] < 0), sorted(b["datum"] for b in bs if b["betrag"] > 0), bs
    beitr, renten, _ = av_b()
    pruef("P5: Ausgangslage 10 Beiträge, keine Rente", len(beitr) == 10 and not renten, (len(beitr), renten))
    # einen Beitrag (Aug) im Plan-Protokoll anpassen
    # Beitrag September (01.09.2026, Dienstag) im Plan-Protokoll anpassen
    sep = next(b for b in av_b()[2] if b["datum"] == "2026-09-01")
    ok(c.post(f"/api/plan-buchungen/{sep['id']}/ablehnen-anpassen?neues_datum=2026-09-14"))
    p = ok(c.get(f"/api/altersvorsorge/{av}/phasen-pruefung?rentenbeginn=2026-07-01"))
    pruef("P5: Vorschau vorverlegt: 3 löschen (Jul, Aug=31.07., Okt), 1 angepasst", p == {"loeschen": 3, "angepasst": 1}, p)
    a = ok(c.get(f"/api/altersvorsorge/{av}"))
    a.update(rentenbeginn="2026-07-01")
    body = {k2: a[k2] for k2 in ["bezeichnung", "anbieter", "zahlungskonto_id", "person_id", "stand_datum", "hat_einzahlung",
        "beitrag_kategorie_id", "beitrag_betrag", "beitrag_intervall", "beitrag_tag_des_monats", "beitrag_monat", "beitrag_startdatum",
        "beitrag_dynamik_aktiv", "rentenbeginn", "ende_datum", "auszahlungsart", "auszahlung_kategorie_id", "rente_garantiert_betrag"]}
    ok(c.put(f"/api/altersvorsorge/{av}?phasen_bereinigen=true", json=body))
    beitr, renten, _ = av_b()
    pruef("P5: danach 6 Beiträge + angepasster Aug, Renten Jul–Okt nachgebucht",
          len(beitr) == 7 and "2026-09-14" in beitr and len(renten) == 4, (beitr, renten))
    body["rentenbeginn"] = "2027-01-01"
    p = ok(c.get(f"/api/altersvorsorge/{av}/phasen-pruefung?rentenbeginn=2027-01-01"))
    pruef("P5: Vorschau nach hinten: 4 Renten löschen", p["loeschen"] == 4, p)
    ok(c.put(f"/api/altersvorsorge/{av}?phasen_bereinigen=true", json=body))
    beitr, renten, _ = av_b()
    pruef("P5: danach keine Rente, Beiträge Jul–Okt nachgebucht", not renten and len(beitr) == 10, (beitr, renten))
    with TestClient(app) as c2:
        n = len([b for b in ok(c2.get("/api/buchungen")) if b.get("ziel_altersvorsorge_id") == av])
    pruef("P5: Neustart ohne Duplikate", n == 10, n)
    # Einmalzahlung nach hinten
    ev = ok(c.post("/api/altersvorsorge", json={"bezeichnung": "Test-Einmal", "zahlungskonto_id": giro, "stand_datum": "2026-01-01",
        "hat_einzahlung": False, "rentenbeginn": "2026-03-02", "auszahlungsart": "einmalzahlung",
        "auszahlung_kategorie_id": KAT["Rente"], "einmalzahlung_garantiert_betrag": 5000}))["id"]
    e_body = {"bezeichnung": "Test-Einmal", "zahlungskonto_id": giro, "stand_datum": "2026-01-01", "hat_einzahlung": False,
              "rentenbeginn": "2026-05-04", "auszahlungsart": "einmalzahlung", "auszahlung_kategorie_id": KAT["Rente"],
              "einmalzahlung_garantiert_betrag": 5000}
    p = ok(c.get(f"/api/altersvorsorge/{ev}/phasen-pruefung?rentenbeginn=2026-05-04"))
    ok(c.put(f"/api/altersvorsorge/{ev}?phasen_bereinigen=true", json=e_body))
    eb = sorted(b["datum"] for b in ok(c.get("/api/buchungen")) if b.get("ziel_altersvorsorge_id") == ev)
    pruef("P5: Einmalzahlung verschoben: alte gelöscht, neue gebucht", p["loeschen"] == 1 and eb == ["2026-05-04"], (p, eb))

    # ── Roundtrip ──
    def export(q=""):
        r = c.get("/api/admin/export" + q)
        assert r.status_code == 200, r.text
        return load_workbook(io.BytesIO(r.content))
    def hoch(wb, name="t.xlsx"):
        b = io.BytesIO(); wb.save(b)
        return ok(c.post("/api/admin/import/vorschau", files={"datei": (name, b.getvalue())}))
    def spalten(ws):
        return {ws.cell(1, i).value: i for i in range(1, ws.max_column + 1)}
    def zeile_mit(ws, spalte, wert):
        sp = spalten(ws)[spalte]
        return next(r for r in range(2, ws.max_row + 1) if ws.cell(r, sp).value == wert)

    wb = export()
    v = hoch(wb)
    pruef("RT: Export unverändert hochladen = 0 Änderungen, 0 Fehler", v["aenderungen"] == 0 and v["fehler"] == 0 and v["token"] is None, v)
    wb2 = export("?von=2026-10-01&bis=2026-10-31")
    pruef("RT: Zeitraum-Export enthält nur Buchungen im Zeitraum",
          all(str(r[spalten(wb2["Buchungen"])["datum"] - 1])[:7] == "2026-10" for r in wb2["Buchungen"].iter_rows(min_row=2, values_only=True)))
    ws = wb["Buchungen"]; sp = spalten(ws)
    r_hotel = zeile_mit(ws, "beschreibung", "Hotel")
    ws.cell(r_hotel, sp["betrag"], -250)
    r_ek1 = zeile_mit(ws, "beschreibung", "Einkauf 1")
    ws.cell(r_ek1, sp["aktion"], "löschen")
    neu = ws.max_row + 1
    for k2, w2 in {"datum": date(2026, 10, 12), "konto": "Girokonto", "typ": "Ist", "betrag": 33.3,
                   "kategorie": "Ausgaben > Lebenshaltung > Lebensmittel/Verpflegung", "beschreibung": "RT neu"}.items():
        ws.cell(neu, sp[k2], w2)
    wk = wb["Konten"]; spk = spalten(wk)
    wk.cell(zeile_mit(wk, "name", "Kreditkarte"), spk["name"], "Kreditkarte Visa")
    wkat = wb["Kategorien"]; spc = spalten(wkat)
    wkat.cell(zeile_mit(wkat, "pfad", "Ausgaben > Lebenshaltung > Drogerie & Haushalt"), spc["name"], "Drogerie")
    v = hoch(wb)
    bt = {b["sheet"]: b for b in v["bereiche"]}
    pruef("RT: Vorschau zählt neu/geändert/gelöscht korrekt",
          (bt["Buchungen"]["neu"], bt["Buchungen"]["geaendert"], bt["Buchungen"]["geloescht"], bt["Konten"]["geaendert"], bt["Kategorien"]["geaendert"]) == (1, 1, 1, 1, 1)
          and v["fehler"] == 0 and v["token"], [(b["sheet"], b["neu"], b["geaendert"], b["geloescht"], b["fehler"]) for b in v["bereiche"]])
    vorher = len(ok(c.get("/api/buchungen")))
    pruef("RT: Vorschau verändert nichts", vorher == len(ok(c.get("/api/buchungen"))) and "Kreditkarte" in [k["name"] for k in ok(c.get("/api/konten"))])
    e = ok(c.post("/api/admin/import/ausfuehren", json={"token": v["token"]}))
    alle = ok(c.get("/api/buchungen"))
    pruef("RT: Übernahme ausgeführt mit Backup", e["uebernommen"] and e["backup"], e.get("meldung"))
    pruef("RT: Buchung geändert/gelöscht/neu", any(b["beschreibung"] == "Hotel" and b["betrag"] == -250 for b in alle)
          and not any(b["beschreibung"] == "Einkauf 1" for b in alle)
          and any(b["beschreibung"] == "RT neu" and b["betrag"] == -33.3 for b in alle))
    pruef("RT: Konto umbenannt, Kategorie umbenannt",
          "Kreditkarte Visa" in [k["name"] for k in ok(c.get("/api/konten"))] and "Drogerie" in [k["name"] for k in ok(c.get("/api/kategorien"))])
    r = c.post("/api/admin/import/ausfuehren", json={"token": v["token"]})
    pruef("RT: Token nur einmal verwendbar", r.status_code == 422)
    # Konflikt
    wb = export()
    hotel = next(b for b in ok(c.get("/api/buchungen")) if b["beschreibung"] == "Hotel")
    ok(c.put(f"/api/buchungen/{hotel['id']}", json={"konto_id": hotel["konto_id"], "datum": hotel["datum"], "betrag": 260,
        "kategorie_id": hotel["kategorie_id"], "typ": "Ist", "beschreibung": "Hotel"}))
    ws = wb["Buchungen"]; sp = spalten(ws)
    ws.cell(zeile_mit(ws, "beschreibung", "Hotel"), sp["betrag"], -270)
    ws.cell(zeile_mit(ws, "beschreibung", "Einkauf 2"), sp["betrag"], -1)
    v = hoch(wb)
    pruef("RT: Konflikt erkannt, kein Token, nichts übernommen", v["fehler"] == 1 and v["token"] is None
          and "Konflikt" in v["bereiche"][-1]["fehler"][0]["hinweis"], v["bereiche"][-1]["fehler"])
    # Fehlerfälle
    wb = export()
    wk = wb["Konten"]; spk = spalten(wk)
    wk.cell(zeile_mit(wk, "name", "Tagesgeld"), spk["aktion"], "löschen")
    ws = wb["Buchungen"]; sp = spalten(ws); n = ws.max_row + 1
    for k2, w2 in {"datum": "2026-10-12", "konto": "Giro", "betrag": 5, "kategorie": "Lebensmittel"}.items():
        ws.cell(n, sp[k2], w2)
    n += 1
    for k2, w2 in {"datum": "2026-10-12", "konto": "Girokonto", "typ": "Ist", "betrag": 5, "kategorie": "Lebensmittel", "sparziel": "Urlaub 2027 neu"}.items():
        ws.cell(n, sp[k2], w2)
    n += 1
    for k2, w2 in {"datum": "2026-10-12", "konto": "Girokonto", "betrag": 5, "kategorie": "Sonstige"}.items():
        ws.cell(n, sp[k2], w2)
    wbu = wb["Budget"]; spb = spalten(wbu)
    wbu.cell(zeile_mit(wbu, "name", "Urlaub 2027 neu"), spb["konto"], "Girokonto")
    v = hoch(wb)
    hinw = [f["hinweis"] for b in v["bereiche"] for f in b["fehler"]]
    print("   Fehlermeldungen:", hinw)
    pruef("RT: Konto löschen per Datei abgelehnt", any("nicht löschen" in h for h in hinw))
    pruef("RT: mehrdeutiges Konto gemeldet", any("mehrdeutig" in h and "Girokonto Partnerin" in h for h in hinw))
    pruef("RT: Sparziel an Ist-Buchung abgelehnt", any("nur bei Übertragungen" in h for h in hinw))
    pruef("RT: mehrdeutige Kategorie gemeldet", any("Sonstige" in h and "mehrdeutig" in h for h in hinw), hinw)
    pruef("RT: Trägerkonto-Sperre greift auch per Datei", any("Trägerkonto" in h for h in hinw))
    pruef("RT: bei Fehlern kein Token", v["token"] is None and v["fehler"] == 5, v["fehler"])
    # Rentenbeginn per Datei
    wb = export()
    wa = wb["Altersvorsorge"]; spa = spalten(wa)
    wa.cell(zeile_mit(wa, "bezeichnung", "Test-AV"), spa["rentenbeginn"], date(2026, 9, 1))
    v = hoch(wb)
    print("   AV-Fehler:", [f for b in v["bereiche"] for f in b["fehler"]])
    pruef("RT: Rentenbeginn per Datei: Hinweis mit Anzahl", any("Test-AV" in h and "1 automatisch" in h for h in v["hinweise"]), v["hinweise"])
    ok(c.post("/api/admin/import/ausfuehren", json={"token": v["token"]}))
    beitr, renten, _ = av_b()
    pruef("RT: Phasen per Datei bereinigt", renten == ["2026-09-01", "2026-10-01"] and len(beitr) == 9 and "2026-10-01" not in beitr, (beitr, renten))
    # alte Vorlage (ohne id) legt neu an
    vl = load_workbook(io.BytesIO(c.get("/api/admin/import-vorlage").content))
    pruef("RT: leere Vorlage hat alle Tabs und keine Daten", len(vl.sheetnames) == 11 and vl["Buchungen"].max_row == 1)
    from openpyxl import Workbook
    alt = Workbook(); w = alt.active; w.title = "Wiederkehrend"
    w.append(["konto", "person", "betrag", "kategorie", "beschreibung", "intervall", "tag_des_monats", "monat", "startdatum",
              "enddatum", "inflationsflag", "dynamik_aktiv", "dynamik_rhythmus_jahre", "dynamik_prozent", "dynamik_startjahr"])
    w.append(["Girokonto", "", "12", "Internet & Telefon", "Altformat", "monatlich", "3", "", "2027-01-01", "", "0", "0", "", "", ""])
    v = hoch(alt)
    pruef("RT: alte Vorlage ohne id legt neu an", v["bereiche"][0]["neu"] == 1 and v["fehler"] == 0, v)
    ok(c.post("/api/admin/import/ausfuehren", json={"token": v["token"]}))
    neu_v = next(x for x in ok(c.get("/api/wiederkehrend")) if x["beschreibung"] == "Altformat")
    pruef("RT: Vorzeichen bei Neuanlage abgeleitet", neu_v["betrag"] == -12)
    # CSV
    csvtext = "konto,datum,betrag,kategorie,beschreibung\nGirokonto,2026-10-11,7,Kraftstoff,CSV-Zeile\n"
    v = ok(c.post("/api/admin/import/vorschau", data={"art": "buchungen"}, files={"datei": ("b.csv", csvtext.encode("cp1252"))}))
    pruef("RT: CSV-Import mit Bereich", v["bereiche"][0]["neu"] == 1 and v["token"])
    # Löschen Darlehen / Vorlage / Kategorie in Benutzung
    wb = export()
    wkat = wb["Kategorien"]; spc = spalten(wkat)
    wkat.cell(zeile_mit(wkat, "name", "Kraftstoff"), spc["aktion"], "löschen")
    v = hoch(wb)
    print("   Kategorie-Löschen:", v["fehler"], [(b["sheet"], b["fehler"], b["details"]) for b in v["bereiche"] if b["fehler"] or b["details"]])
    pruef("RT: Kategorie in Benutzung nicht löschbar", v["fehler"] == 1 and any("verwendet" in f["hinweis"] for b in v["bereiche"] for f in b["fehler"]), v["fehler"])
    wb = export()
    wd = wb["Darlehen"]; spd = spalten(wd)
    wd.cell(zeile_mit(wd, "bezeichnung", "Hausfinanzierung"), spd["aktion"], "löschen")
    v = hoch(wb)
    pruef("RT: Darlehen löschen: Hinweis auf gelöste Buchungen", v["fehler"] == 0 and any("Hausfinanzierung" in h for h in v["hinweise"]), v["hinweise"])

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

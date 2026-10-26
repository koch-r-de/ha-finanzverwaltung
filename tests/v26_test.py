"""Fachliche Tests 2.6: Feiertagskalender wählbar.
Ostern, Buß- und Bettag, Gültigkeitsintervalle, jeder regionale Sonderfall,
Verschiebung nach TARGET, Migration einer Datenbank von vor 2.6,
Endpunkte (Auswahl, Liste, Fehlerfälle), Serienhinweise, Siri und Import.
Den Übergang von 2.5 ohne doppelte Termine prüft upgrade_test.py mit dem
echten Code der Vorversion.
Aufruf: python3 v26_test.py <code> <quelle> <ziel>   (Quelle: Datenbank von vor 2.6)"""
import io, os, sys, shutil, sqlite3
from datetime import date, timedelta
code, quelle, ziel = sys.argv[1], sys.argv[2], sys.argv[3]
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from app.main import app
from app.core import feiertage as f, startup, db as db_modul, zeit

ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""))
DB = os.path.join(ziel, "finanzdaten.db")
D = date.fromisoformat
def namen(region, tag):
    return f.feiertage_jahr(region, D(tag).year).get(D(tag))

# ─── Ostern und Buß- und Bettag ──────────────────────────────────────
OSTERN = {2000: "2000-04-23", 2008: "2008-03-23", 2011: "2011-04-24", 2019: "2019-04-21", 2024: "2024-03-31",
          2025: "2025-04-20", 2026: "2026-04-05", 2027: "2027-03-28", 2038: "2038-04-25", 2285: "2285-03-22"}
falsch = {j: f.ostersonntag(j).isoformat() for j, d in OSTERN.items() if f.ostersonntag(j).isoformat() != d}
pruef("Ostern: zehn Jahre, darunter die Extremtermine 22.03. (2285) und 25.04. (2038)", not falsch, falsch)
pruef("Bewegliche Feiertage 2026 aus Ostern: Karfreitag, Himmelfahrt, Pfingstmontag, Fronleichnam",
      namen("NW", "2026-04-03") == "Karfreitag" and namen("NW", "2026-05-14") == "Christi Himmelfahrt"
      and namen("NW", "2026-05-25") == "Pfingstmontag" and namen("NW", "2026-06-04") == "Fronleichnam")
BUB = {2024: "2024-11-20", 2025: "2025-11-19", 2026: "2026-11-18", 2028: "2028-11-22", 2033: "2033-11-16"}
falsch = {j: f.buss_und_bettag(j).isoformat() for j, d in BUB.items() if f.buss_und_bettag(j).isoformat() != d}
pruef("Buß- und Bettag: Mittwoch vor dem 23.11. (auch wenn der 23. selbst ein Mittwoch ist)", not falsch, falsch)

# ─── Anzahl je Region (2026) ─────────────────────────────────────────
ANZAHL_2026 = {"BW": 12, "BY_MH": 13, "BY_O": 12, "BY_A": 14, "BE": 10, "BB": 12, "HB": 10, "HH": 10, "HE": 10,
               "MV": 11, "NI": 10, "NW": 11, "RP": 11, "SL": 12, "SN": 11, "SN_F": 12, "ST": 11, "SH": 10,
               "TH": 11, "TH_F": 12}
abw = {r: len(f.feiertage_jahr(r, 2026)) for r in ANZAHL_2026 if len(f.feiertage_jahr(r, 2026)) != ANZAHL_2026[r]}
pruef("Anzahl der Feiertage 2026 je Region (alle 20 Einträge)", not abw and set(ANZAHL_2026) == set(f.REGION_NAMEN), abw)
pruef("Jede Regel hat Rechtsgrundlage und Status, Intervall [von, bis] gültig",
      all(r.rechtsgrundlage and r.status and 1900 <= r.von <= r.bis <= f.OFFEN for r in f.REGELN))
pruef("Jede Regel nennt nur bekannte Regionen", all(r.regionen <= set(f.REGION_NAMEN) | {f.TARGET} for r in f.REGELN))

# ─── Gültigkeitsintervalle ───────────────────────────────────────────
pruef("Frauentag Berlin ab 2019", namen("BE", "2018-03-08") is None and namen("BE", "2019-03-08") == "Frauentag")
pruef("Frauentag Mecklenburg-Vorpommern ab 2023", namen("MV", "2022-03-08") is None and namen("MV", "2023-03-08") == "Frauentag")
pruef("Weltkindertag Thüringen ab 2019", namen("TH", "2018-09-20") is None and namen("TH", "2019-09-20") == "Weltkindertag")
pruef("Reformationstag Niedersachsen: 2016 nein, 2017 einmalig, ab 2018 dauerhaft",
      namen("NI", "2016-10-31") is None and namen("NI", "2017-10-31") and namen("NI", "2018-10-31") == "Reformationstag")
pruef("Reformationstag NRW und Bayern nur 2017",
      namen("NW", "2017-10-31") and namen("NW", "2018-10-31") is None and namen("BY_O", "2017-10-31")
      and namen("BY_O", "2016-10-31") is None)
pruef("Reformationstag Sachsen-Anhalt durchgehend (auch 2017 nur einmal genannt)",
      namen("ST", "2016-10-31") == "Reformationstag" and namen("ST", "2017-10-31") == "Reformationstag")
pruef("Berlin: 8. Mai nur 2020 und 2025 (einmalig, von = bis)",
      namen("BE", "2020-05-08") and namen("BE", "2025-05-08") and namen("BE", "2021-05-08") is None
      and namen("BE", "2024-05-08") is None)
pruef("Berlin: 17. Juni nur 2028", namen("BE", "2028-06-17") and namen("BE", "2027-06-17") is None
      and namen("BE", "2029-06-17") is None)
pruef("Buß- und Bettag außerhalb Sachsens nur bis 1994", namen("NW", "1994-11-16") and namen("NW", "1995-11-22") is None
      and namen("SN", "1995-11-22") == "Buß- und Bettag")
pruef("TARGET: Schließtage erst ab 2002", not f.feiertage_jahr(f.TARGET, 2001) and len(f.feiertage_jahr(f.TARGET, 2002)) == 6)

# ─── Regionale Sonderfälle ───────────────────────────────────────────
pruef("Bayern – mit Mariä Himmelfahrt: 15.08. ja, Friedensfest nein",
      namen("BY_MH", "2026-08-15") == "Mariä Himmelfahrt" and namen("BY_MH", "2026-08-08") is None)
pruef("Bayern – ohne Mariä Himmelfahrt: 15.08. nein", namen("BY_O", "2026-08-15") is None)
pruef("Bayern – Stadt Augsburg: Friedensfest 08.08. und Mariä Himmelfahrt",
      namen("BY_A", "2026-08-08") == "Augsburger Friedensfest" and namen("BY_A", "2026-08-15") == "Mariä Himmelfahrt")
pruef("Alle Bayern-Einträge: Heilige Drei Könige, Fronleichnam, Allerheiligen",
      all(namen(r, "2026-01-06") and namen(r, "2026-06-04") and namen(r, "2026-11-01") for r in ("BY_MH", "BY_O", "BY_A")))
pruef("Sachsen: Fronleichnam nur im Eintrag „mit Fronleichnam“, Buß- und Bettag in beiden",
      namen("SN", "2026-06-04") is None and namen("SN_F", "2026-06-04") == "Fronleichnam"
      and namen("SN", "2026-11-18") and namen("SN_F", "2026-11-18"))
pruef("Thüringen: Fronleichnam nur im Eintrag „mit Fronleichnam“, Weltkindertag in beiden",
      namen("TH", "2026-06-04") is None and namen("TH_F", "2026-06-04") == "Fronleichnam"
      and namen("TH", "2026-09-20") and namen("TH_F", "2026-09-20"))
pruef("Mariä Himmelfahrt im Saarland", namen("SL", "2026-08-15") == "Mariä Himmelfahrt")
pruef("Brandenburg: Ostersonntag und Pfingstsonntag, NRW nicht",
      namen("BB", "2026-04-05") == "Ostersonntag" and namen("BB", "2026-05-24") == "Pfingstsonntag"
      and namen("NW", "2026-04-05") is None)
pruef("Feiertag an einem Sonntag wird markiert (Allerheiligen 01.11.2026)",
      D("2026-11-01").weekday() == 6 and f.datum_hinweis(D("2026-11-01"), "NW") is not None)
pruef("Unbekannte Region wird abgewiesen", not f.region_gueltig("XX") and not f.region_gueltig(""))
try:
    f.Kalender("XX"); pruef("Kalender mit unbekannter Region wirft Fehler", False)
except ValueError:
    pruef("Kalender mit unbekannter Region wirft Fehler", True)

# ─── Verschiebung nach TARGET ────────────────────────────────────────
bank = f.bank_kalender()
pruef("Verschiebung: Fronleichnam 2027 (Do) bleibt, NRW-Feiertage verschieben nicht mehr",
      f.vorheriger_werktag(D("2027-05-27"), bank) == D("2027-05-27")
      and f.vorheriger_werktag(D("2026-10-03"), bank) == D("2026-10-02"))   # Samstag -> Freitag
pruef("Verschiebung: Neujahr 2027 (Fr) -> 31.12.2026, Karfreitag 2027 -> 25.03.2027, 1. Mai 2028 (Mo) -> 28.04.2028",
      f.vorheriger_werktag(D("2027-01-01"), bank) == D("2026-12-31")
      and f.vorheriger_werktag(D("2027-03-26"), bank) == D("2027-03-25")
      and f.vorheriger_werktag(D("2028-05-01"), bank) == D("2028-04-28"))
pruef("Hinweistext mit Verschiebung", f.termin_hinweise([(D("2027-01-01"), D("2026-12-31"))], "NW")[0]["text"]
      == "01.01.2027 ist ein Feiertag (Neujahr), gebucht wird am 31.12.2026.")

# ─── Migration einer Datenbank von vor 2.6 ───────────────────────────
alt = sqlite3.connect(DB)
war_tabelle = alt.execute("SELECT 1 FROM sqlite_master WHERE name = 'feiertage'").fetchone()
buchungen_vorher = alt.execute("SELECT COUNT(*) FROM buchungen").fetchone()[0]
alt.close()

with TestClient(app) as c:
    st = c.get("/api/start-status").json()
    con = sqlite3.connect(DB)
    pruef("Migration: Quelle hatte die Tabelle feiertage, danach entfernt",
          war_tabelle and not con.execute("SELECT 1 FROM sqlite_master WHERE name = 'feiertage'").fetchone())
    pruef("Migration: Schritte im Start-Status",
          any("NRW" in s or "Nordrhein-Westfalen" in s for s in st["migration"])
          and any("feiertage" in s for s in st["migration"]), st["migration"])
    r = c.get("/api/feiertage/regionen").json()
    pruef("Regionen: 20 Einträge, nichts gewählt, Vorschlag NRW", len(r["regionen"]) == 20 and r["gewaehlt"] == ""
          and r["vorschlag"] == "NW", r)
    t = c.get("/api/feiertage?von_jahr=2026&bis_jahr=2026").json()
    pruef("Ohne gewählte Region: nur Bankfeiertage in der Liste",
          t["region"] == "" and len(t["tage"]) == 6 and all(x["feiertag"] is None for x in t["tage"]))
    pruef("Fehler: unbekanntes Bundesland 422", c.put("/api/feiertage/region", json={"kuerzel": "XX"}).status_code == 422)
    pruef("Fehler: leeres Bundesland 422", c.put("/api/feiertage/region", json={"kuerzel": ""}).status_code == 422)
    pruef("Fehler: Bundesland nicht über die allgemeine Einstellung setzbar",
          c.put("/api/admin/einstellungen/bundesland?value=NW").status_code == 422
          and c.put("/api/admin/einstellungen/bundesland_vorschlag?value=BE").status_code == 422)
    pruef("Fehler: Jahre vertauscht, Zeitraum zu lang, außerhalb 1900 bis 9998",
          c.get("/api/feiertage?von_jahr=2027&bis_jahr=2026").status_code == 422
          and c.get("/api/feiertage?von_jahr=2000&bis_jahr=2060").status_code == 422
          and c.get("/api/feiertage?von_jahr=1899&bis_jahr=1899").status_code == 422)
    a = c.put("/api/feiertage/region", json={"kuerzel": "NW"})
    r = c.get("/api/feiertage/regionen").json()
    pruef("Bundesland setzen: gewählt NRW, Vorschlag gelöscht", a.status_code == 200 and r["gewaehlt"] == "NW"
          and r["vorschlag"] == "")
    t = c.get("/api/feiertage?von_jahr=2026&bis_jahr=2027").json()
    pruef("Feiertagsliste NRW 2026 und 2027 mit fertigem Hinweistext",
          len(t["tage"]) == 22 and all(x["text"] for x in t["tage"])
          and {"datum": "2026-06-04", "feiertag": "Fronleichnam", "bankfeiertag": None,
               "text": "04.06.2026 ist ein Feiertag (Fronleichnam)."} in t["tage"])
    pruef("Bundesland ändert keine Buchung", con.execute("SELECT COUNT(*) FROM buchungen").fetchone()[0] >= buchungen_vorher)
    c.put("/api/feiertage/region", json={"kuerzel": "BY_A"})
    t = c.get("/api/feiertage?von_jahr=2026&bis_jahr=2026").json()
    pruef("Wechsel auf Augsburg wirkt sofort auf die Liste", any(x["datum"] == "2026-08-08" for x in t["tage"]))
    c.put("/api/feiertage/region", json={"kuerzel": "NW"})

    # Serienhinweise nach dem Speichern (nächste 12 Monate, relativ zu heute)
    heute = zeit.heute()
    neujahr = date(heute.year + 1, 1, 1)
    konten = c.get("/api/konten").json(); kid = konten[0]["id"]
    kat = {k["name"]: k["id"] for k in c.get("/api/kategorien").json()}
    v = c.post("/api/wiederkehrend", json={"konto_id": kid, "betrag": 10, "kategorie_id": kat["Lebensmittel/Verpflegung"],
        "beschreibung": "Feiertagsprobe", "intervall": "monatlich", "tag_des_monats": 1,
        "startdatum": heute.replace(day=1).isoformat()}).json()
    h = v.get("feiertagshinweise", [])
    pruef("Vorlage anlegen: Hinweis auf Neujahr mit Verschiebung auf den Werktag davor",
          any(x["feiertag_am"] == neujahr.isoformat() and x["verschoben_von"] == neujahr.isoformat() for x in h), h)
    pruef("Vorlage anlegen: nur Termine der nächsten 12 Monate",
          all(heute <= D(x["datum"]) <= heute + timedelta(days=366) for x in h) and len(h) <= 13, h)
    u = c.put(f"/api/wiederkehrend/{v['id']}", json={"konto_id": kid, "betrag": 10,
        "kategorie_id": kat["Lebensmittel/Verpflegung"], "beschreibung": "Feiertagsprobe", "intervall": "monatlich",
        "tag_des_monats": 15, "startdatum": heute.replace(day=1).isoformat()}).json()
    pruef("Vorlage ändern: Antwort enthält die Liste (ok + feiertagshinweise)",
          u.get("ok") and isinstance(u.get("feiertagshinweise"), list))
    dl = c.post("/api/darlehen", json={"bezeichnung": "Feiertagsdarlehen", "zinssatz": 3, "zinsbeginn": "2026-01-01",
        "tilgungsbeginn": "2026-02-01", "laufzeit_jahre": 10, "ende_zinsbindung": "2036-01-01",
        "anschlusszinssatz": 4, "raten_modus": "tilgungssatz", "tilgungssatz": 2, "darlehenssumme": 100000,
        "zahlungskonto_id": kid}).json()
    pruef("Darlehen anlegen: Antwort mit id und feiertagshinweise", dl.get("id") and isinstance(dl.get("feiertagshinweise"), list), dl)
    av = c.post("/api/altersvorsorge", json={"bezeichnung": "Feiertagsrente", "zahlungskonto_id": kid,
        "stand_datum": heute.isoformat(), "beitrag_kategorie_id": kat["Lebensmittel/Verpflegung"], "beitrag_betrag": 50,
        "beitrag_tag_des_monats": 1, "beitrag_startdatum": heute.replace(day=1).isoformat(), "rentenbeginn": "2050-01-01",
        "auszahlung_kategorie_id": kat["Rente"], "rente_garantiert_betrag": 100}).json()
    pruef("Altersvorsorge anlegen: Beitrag zum 1. meldet Neujahr",
          any(x["feiertag_am"] == neujahr.isoformat() for x in av.get("feiertagshinweise", [])), av)

    # Siri: zusätzliches Feld, „meldung“ unverändert
    s = c.post("/api/siri/buchung", json={"betrag": 5, "kategorie": "Lebensmittel/Verpflegung", "konto": konten[0]["name"],
                                          "datum": "2026-12-25"}).json()
    pruef("Siri: Hinweis am 1. Weihnachtstag, Meldung wie bisher",
          s["feiertagshinweis"] == "25.12.2026 ist ein Feiertag (1. Weihnachtstag)."
          and s["meldung"].endswith("gebucht.") and "Feiertag" not in s["meldung"], s)
    s = c.post("/api/siri/buchung", json={"betrag": 5, "kategorie": "Lebensmittel/Verpflegung", "konto": konten[0]["name"],
                                          "datum": "2026-12-22"}).json()
    pruef("Siri: an einem Werktag kein Hinweis (null)", "feiertagshinweis" in s and s["feiertagshinweis"] is None, s)

    # Import (CSV, Bereich Buchungen): Hinweis in der Vorschau, nur für neue/geänderte Daten
    csv_text = ("datum,konto,betrag,kategorie,beschreibung\n"
                f"2026-06-04,{konten[0]['name']},12,Lebensmittel/Verpflegung,Import am Fronleichnam\n"
                f"2026-06-05,{konten[0]['name']},13,Lebensmittel/Verpflegung,Import am Freitag\n")
    vs = c.post("/api/admin/import/vorschau", files={"datei": ("b.csv", io.BytesIO(csv_text.encode()), "text/csv")},
                data={"art": "buchungen"}).json()
    fh = vs.get("feiertagshinweise", [])
    pruef("Import: Vorschau nennt genau die Zeile am Feiertag", len(fh) == 1 and fh[0]["zeile"] == 2
          and fh[0]["text"] == "04.06.2026 ist ein Feiertag (Fronleichnam)." and not vs["fehler"], vs)
    pruef("Import: Vorschau speichert nichts",
          not con.execute("SELECT 1 FROM buchungen WHERE beschreibung = 'Import am Fronleichnam'").fetchone())
    ue = c.post("/api/admin/import/ausfuehren", json={"token": vs["token"]}).json()
    pruef("Import: Übernahme trotz Hinweis (nichts gesperrt)",
          ue.get("uebernommen") and con.execute("SELECT datum FROM buchungen WHERE beschreibung = 'Import am Fronleichnam'").fetchone()[0] == "2026-06-04", ue)

    # Manuelle Buchung an einem Feiertag wird nicht verschoben
    b = c.post("/api/buchungen", json={"konto_id": kid, "datum": "2026-12-25", "betrag": 7,
                                       "kategorie_id": kat["Lebensmittel/Verpflegung"], "typ": "Ist", "beschreibung": "Am Feiertag"})
    pruef("Manuelle Buchung am Feiertag bleibt auf dem Tag", b.status_code < 300 and
          con.execute("SELECT datum FROM buchungen WHERE id = ?", (b.json()["id"],)).fetchone()[0] == "2026-12-25")
    pruef("Endpunkt „Neu berechnen“ gibt es nicht mehr", c.post("/api/admin/feiertage/aktualisieren").status_code in (404, 405))
    con.close()

# ─── Generator: Fronleichnam 2027 wird nicht mehr vorgezogen ─────────
with TestClient(app) as c:
    konten = c.get("/api/konten").json(); kid = konten[0]["id"]
    kat = {k["name"]: k["id"] for k in c.get("/api/kategorien").json()}
    v27 = c.post("/api/wiederkehrend", json={"konto_id": kid, "betrag": 27, "kategorie_id": kat["Lebensmittel/Verpflegung"],
        "beschreibung": "Am 27.", "intervall": "monatlich", "tag_des_monats": 27, "startdatum": "2027-05-01"}).json()["id"]
startup.ausfuehren(date(2027, 5, 31))
con = sqlite3.connect(DB)
daten = [r[0] for r in con.execute("SELECT datum FROM buchungen WHERE wiederkehrend_id = ? ORDER BY datum", (v27,))]
pruef("Generator: Termin am Fronleichnam 2027 (Do) wird am 27.05. gebucht, nicht am Vortag", daten == ["2027-05-27"], daten)

con.close()

# ─── Neue Installation ───────────────────────────────────────────────
neu = ziel + "_neu"
shutil.rmtree(neu, ignore_errors=True); os.makedirs(neu)
import subprocess
r = subprocess.run([sys.executable, "-c", f"""
import os, sys, sqlite3
os.environ["FINANZAPP_DATENVERZEICHNIS"] = {neu!r}
sys.path.insert(0, {code!r})
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    r = c.get("/api/feiertage/regionen").json()
    st = c.get("/api/start-status").json()
con = sqlite3.connect(os.path.join({neu!r}, "finanzdaten.db"))
werte = dict(con.execute("SELECT key, value FROM einstellungen WHERE key IN ('bundesland', 'bundesland_vorschlag')"))
print(st["datenbank_neu_angelegt"], r["gewaehlt"] == "", r["vorschlag"] == "", werte.get("bundesland") == "" and werte.get("bundesland_vorschlag") == "",
      con.execute("SELECT 1 FROM sqlite_master WHERE name = 'feiertage'").fetchone() is None)
"""], capture_output=True, text=True)
pruef("Neue Installation: kein Bundesland, kein Vorschlag, keine Tabelle feiertage",
      r.stdout.strip().split("\n")[-1] == "True True True True True", r.stdout + r.stderr[-500:])
shutil.rmtree(neu, ignore_errors=True)

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

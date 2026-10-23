"""Fachliche Tests 2.1: Hilfe (Quelle, Anker, Hinweise, PDF, Bilder) und Feiertage."""
import os, re, sys, shutil, io, sqlite3, time
from datetime import date
code, quelle, ziel = sys.argv[1], sys.argv[2], sys.argv[3]
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from app.main import app
from app.core import hilfe, startup

ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""))
def ok(r):
    assert r.status_code < 300, (r.status_code, r.text[:300])
    return r

dockerfile = open(os.path.join(code, "Dockerfile"), encoding="utf-8").read()
version = re.search(r'ENV FINANZAPP_VERSION="([^"]+)"', dockerfile).group(1)
index = open(os.path.join(code, "app/static/index.html"), encoding="utf-8").read()
appjs = open(os.path.join(code, "app/static/app.js"), encoding="utf-8").read()
sb = open(os.path.join(code, "app/static/schnellbuchung.html"), encoding="utf-8").read()

with TestClient(app) as c:
    h = ok(c.get("/api/hilfe")).json()
    anker = {k["anker"] for k in h["kapitel"]}
    pruef("Hilfe: Kopfzeile nennt Programmversion = Dockerfile", h["version"] == version, (h["version"], version))
    meldungen = hilfe.pruefen(hilfe.laden(), version)
    pruef("Hilfe: Prüfung ohne Befund (Anker, Verweise, Bilder, Muster, keine Versionshinweise)", not meldungen, meldungen)
    oben = [k["titel"] for k in h["kapitel"] if k["ebene"] == 1]
    pruef("Hilfe: Aufbau Erste Schritte … Wie mache ich … Begriffe … Stichwortverzeichnis",
          oben[0] == "Erste Schritte" and oben[-3:] == ["Wie mache ich …?", "Begriffe von A bis Z", "Stichwortverzeichnis"], oben)
    pruef("Hilfe: Stichwortverzeichnis gefüllt und verweist nur auf vorhandene Kapitel",
          len(h["stichwortverzeichnis"]) > 100 and all(a in anker for e in h["stichwortverzeichnis"] for a in e["anker"]))
    ids_html = set(re.findall(r'data-hinweis="([^"]+)"', index)) | set(re.findall(r'data-hinweis-titel="([^"]+)"', index))
    ids_js = set(re.findall(r'hinweis(?:Html|Text)\("([^"]+)"\)', appjs))
    reset = re.findall(r'hinweis: "([^"]+)", anker: "([^"]+)"', appjs)
    ids_js |= {"zuruecksetzen." + r[0] for r in reset}
    fehlend = sorted((ids_html | ids_js) - set(h["hinweise"]))
    pruef("Hinweise: jede Hinweis-Stelle der App hat ihren Text in der Hilfedatei", not fehlend, fehlend)
    unbenutzt = sorted(set(h["hinweise"]) - ids_html - ids_js)
    pruef("Hinweise: kein Hinweis in der Hilfedatei ohne Verwendung", not unbenutzt, unbenutzt)
    sprung = set(re.findall(r'data-hilfe="([^"]+)"', index)) | set(re.findall(r'data-anker="([a-z0-9.\-]+)"', appjs)) \
        | {r[1] for r in reset} | set(re.findall(r'#hilfe:([a-z0-9.\-]+)', sb))
    pruef("„?“: alle Sprungziele existieren als Anker", sprung and sprung <= anker, sorted(sprung - anker))
    pruef("„?“: jede Ansicht hat ein „?“ im Seitenkopf",
          all(re.search(rf'<section id="abschnitt-{s}".*?<h1 data-hilfe=', index, re.S) for s in
              ["start", "konten", "buchungen", "wiederkehrend", "plan", "budgets", "darlehen", "altersvorsorge",
               "auswertungen", "jahr", "admin"]))
    pruef("Hinweise: keine festen Hinweistexte mit Versionsstand mehr in index.html", not re.search(r"[Ss]eit Version", index))
    t = time.time(); r = ok(c.get("/api/hilfe/pdf")); dauer1 = time.time() - t
    pruef("PDF: Antwort ist PDF zum Herunterladen", r.headers["content-type"] == "application/pdf"
          and "attachment" in r.headers.get("content-disposition", "") and r.content[:5] == b"%PDF-")
    from pypdf import PdfReader
    pdf = PdfReader(io.BytesIO(r.content))
    def zaehle(o):
        return sum(zaehle(x) if isinstance(x, list) else 1 for x in o)
    pruef("PDF: Lesezeichen für jedes Kapitel", zaehle(pdf.outline) == len(h["kapitel"]), (zaehle(pdf.outline), len(h["kapitel"])))
    text2 = pdf.pages[1].extract_text() + pdf.pages[2].extract_text()
    pruef("PDF: Inhaltsverzeichnis mit Seitenzahlen", "Inhalt" in text2 and "Erste Schritte" in text2 and len(re.findall(r"\.\s+\d+\s", text2)) > 30, text2[:200])
    seite5 = pdf.pages[5].extract_text()
    pruef("PDF: Kopfzeile mit Programmversion, Fußzeile mit Seitenzahl", f"Programmversion {version}" in seite5 and "Seite 6" in seite5)
    letzte = "".join(p.extract_text() for p in pdf.pages[-10:])
    pruef("PDF: Stichwortverzeichnis mit Seitenzahlen", "Stichwortverzeichnis" in letzte and "Trägerkonto" in letzte and len(re.findall(r"\.\s+\d+", letzte)) > 40)
    pruef("PDF: Bilder eingebettet", sum(len(p.images) for p in pdf.pages) >= 15)
    t = time.time(); ok(c.get("/api/hilfe/pdf")); dauer2 = time.time() - t
    pruef("PDF: zweiter Abruf aus dem Zwischenspeicher", dauer2 < dauer1 / 3, (round(dauer1, 2), round(dauer2, 2)))
    print(f"   PDF {len(r.content)//1024} KB, {len(pdf.pages)} Seiten, erzeugt in {dauer1:.1f} s")
    pruef("Bilder: werden ausgeliefert", c.get("/api/hilfe/bilder/konten.anlegen.png").status_code == 200)
    pruef("Bilder: kein Zugriff außerhalb des Bilderordners",
          c.get("/api/hilfe/bilder/..%2Fhilfe.md").status_code == 404 and c.get("/api/hilfe/bilder/fehlt.png").status_code == 404)

    # Feiertage: komplett neu, alte Jahre bleiben, veraltete Einträge verschwinden
    con = sqlite3.connect(os.path.join(ziel, "finanzdaten.db"))
    con.execute("INSERT INTO feiertage (datum, name) VALUES ('2026-07-07', 'Kein Feiertag')")
    con.execute("INSERT OR IGNORE INTO feiertage (datum, name) VALUES ('2024-12-25', '1. Weihnachtstag')")
    con.commit()
    anz = ok(c.post("/api/admin/feiertage/aktualisieren")).json()["anzahl"]
    rows = {r[0] for r in con.execute("SELECT datum FROM feiertage")}
    pruef("Feiertage: „Neu berechnen“ entfernt veraltete Einträge", "2026-07-07" not in rows)
    pruef("Feiertage: vergangene Jahre bleiben (ab ältestem Jahr neu berechnet)", "2024-12-25" in rows and "2024-04-01" in rows
          and anz == len(rows), (anz, len(rows)))
    pruef("Feiertage: 30 Jahre voraus", f"{date.today().year + 30}-12-26" in rows)
    con.execute("INSERT INTO feiertage (datum, name) VALUES ('2026-07-08', 'Kein Feiertag')"); con.commit()

with TestClient(app) as c:
    con = sqlite3.connect(os.path.join(ziel, "finanzdaten.db"))
    pruef("Feiertage: Programmstart berechnet neu", not con.execute("SELECT 1 FROM feiertage WHERE datum='2026-07-08'").fetchone())
    # Befund J: Nachholen eines Vorjahres-Termins nach Neujahr verschiebt auf den Werktag davor
    konten = ok(c.get("/api/konten")).json(); kat = {k["name"]: k["id"] for k in ok(c.get("/api/kategorien")).json()}
    v = ok(c.post("/api/wiederkehrend", json={"konto_id": konten[0]["id"], "betrag": 33, "kategorie_id": kat["Lebensmittel/Verpflegung"],
        "beschreibung": "Befund J", "intervall": "jaehrlich", "tag_des_monats": 25, "monat": 12, "startdatum": "2026-12-01"})).json()["id"]
startup.ausfuehren(date(2027, 1, 5))
con = sqlite3.connect(os.path.join(ziel, "finanzdaten.db"))
daten = [r[0] for r in con.execute("SELECT datum FROM buchungen WHERE wiederkehrend_id = ?", (v,))]
pruef("Befund J: Termin 25.12.2026 nach Neujahr nachgebucht auf 24.12.2026", daten == ["2026-12-24"], daten)

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

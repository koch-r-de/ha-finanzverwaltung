"""Fachliche Tests 2.6.3: Kategorie-Vorschlag aus der Beschreibung, den die
Schnellbuchung beim Tippen abfragt (GET /api/regeln/vorschlag).
Aufruf: python3 v263_test.py <code> <quelle> <ziel>"""
import os, sys, shutil
code, quelle, ziel = sys.argv[1], sys.argv[2], sys.argv[3]
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from app.main import app

ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""))

with TestClient(app) as c:
    kat = {k["name"]: k["id"] for k in c.get("/api/kategorien").json()}
    lm, kfz = kat["Lebensmittel/Verpflegung"], kat["Kraftstoff"]
    for r in c.get("/api/regeln").json():
        c.delete(f"/api/regeln/{r['id']}")
    c.post("/api/regeln", json={"muster": "Wochenmarkt", "kategorie_id": lm, "prioritaet": 100})
    c.post("/api/regeln", json={"muster": "markt", "kategorie_id": kfz, "prioritaet": 200})
    v = lambda t: c.get("/api/regeln/vorschlag", params={"beschreibung": t})
    pruef("Treffer ohne Groß- und Kleinschreibung", v("einkauf WOCHENMARKT").json()["kategorie_id"] == lm)
    pruef("Kleinere Priorität gewinnt bei mehreren Treffern", v("Wochenmarkt").json()["kategorie_id"] == lm)
    pruef("Weniger spezifische Regel greift, wenn nur sie passt", v("Baumarkt").json()["kategorie_id"] == kfz)
    pruef("Kein Treffer liefert null", v("Bäckerei").json()["kategorie_id"] is None)
    pruef("Leere Beschreibung liefert null, kein Fehler", v("").status_code == 200 and v("").json()["kategorie_id"] is None)
    pruef("Sonderzeichen und Umlaute ohne Fehler", v("Café & Co. ü/ß %").status_code == 200)
    # Server bleibt bei Buchung ohne Kategorie bei seiner Regel (Siri, Import)
    konto = c.get("/api/konten").json()[0]["id"]
    b = c.post("/api/buchungen", json={"konto_id": konto, "datum": "2026-10-20", "betrag": 3, "typ": "Ist", "beschreibung": "Wochenmarkt"}).json()
    pruef("Buchung ohne Kategorie: Server setzt sie aus der Regel", b["auto_kategorie"] == lm)
    f = c.post("/api/buchungen", json={"konto_id": konto, "datum": "2026-10-20", "betrag": 3, "typ": "Ist", "beschreibung": "Bäckerei"})
    pruef("Buchung ohne Kategorie und ohne Treffer: abgelehnt", f.status_code == 400)

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

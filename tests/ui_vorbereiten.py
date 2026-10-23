"""Bereitet eine Datenbank für die Oberflächentests vor (über die API, nicht per SQL):
30 Testvorlagen (Scrollbereich Wiederkehrend, ui21) und eine Ist-Buchung „UI-Konflikt“
mit unstimmiger Sparziel-Zuordnung (ui2). Aufruf: python3 ui_vorbereiten.py <code> <quelle> <ziel>"""
import os, sys, shutil, sqlite3
code, quelle, ziel = sys.argv[1:4]
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    konto = c.get("/api/konten").json()[0]["id"]
    kat = next(k["id"] for k in c.get("/api/kategorien").json() if k["name"] == "Lebensmittel/Verpflegung")
    for i in range(30):
        r = c.post("/api/wiederkehrend", json={"konto_id": konto, "betrag": 10 + i, "kategorie_id": kat,
                   "beschreibung": f"Testvorlage {i}", "intervall": "monatlich", "tag_des_monats": 28, "startdatum": "2027-06-01"})
        assert r.status_code < 300, r.text
    r = c.post("/api/buchungen", json={"konto_id": konto, "datum": "2026-10-05", "betrag": -20, "kategorie_id": kat,
               "typ": "Ist", "beschreibung": "UI-Konflikt"})
    assert r.status_code < 300, r.text
    bid = r.json()["id"]
con = sqlite3.connect(os.path.join(ziel, "finanzdaten.db"))
sz = con.execute("SELECT id FROM budgets WHERE typ = 'sparziel' ORDER BY id LIMIT 1").fetchone()[0]
con.execute("UPDATE buchungen SET sparziel_id = ? WHERE id = ?", (sz, bid)); con.commit()
print("vorbereitet:", ziel)

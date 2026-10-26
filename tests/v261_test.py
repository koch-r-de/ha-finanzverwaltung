"""Fachliche Tests 2.6.1: Befund P (Zielkonto bei Ist- und Plan-Buchungen).
Aufruf: python3 v261_test.py <code> <quelle> <ziel>   (Quelle: Datenbank von vor 2.6.1)"""
import os, sys, shutil, sqlite3
code, quelle, ziel = sys.argv[1], sys.argv[2], sys.argv[3]
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
DB = os.path.join(ziel, "finanzdaten.db")

ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""))

# Altdaten wie bis 2.6: zwei Ist-Buchungen und eine Plan-Buchung mit Zielkonto
con = sqlite3.connect(DB)
konten = [r[0] for r in con.execute("SELECT id FROM konten ORDER BY id")]
ids = [r[0] for r in con.execute("SELECT id FROM buchungen WHERE typ IN ('Ist', 'Plan') ORDER BY id LIMIT 3")]
con.executemany("UPDATE buchungen SET zielkonto_id = ? WHERE id = ?", [(konten[1], i) for i in ids])
uebertragungen = dict(con.execute("SELECT id, zielkonto_id FROM buchungen WHERE typ = 'Uebertragung'"))
con.commit(); con.close()

os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as c:
    st = c.get("/api/start-status").json()
    con = sqlite3.connect(DB)
    pruef("Korrektur: Schritt und Backup im Start-Status",
          any("Zielkonto bei 3 " in m for m in st["migration"]) and any("Backup vor der Korrektur" in m for m in st["migration"]),
          st["migration"])
    pruef("Korrektur: Backup in der Backup-Liste",
          any("Zielkonto" in (b.get("beschreibung") or "") for b in c.get("/api/admin/backups").json()))
    pruef("Korrektur: keine Ist- oder Plan-Buchung mehr mit Zielkonto",
          con.execute("SELECT COUNT(*) FROM buchungen WHERE typ <> 'Uebertragung' AND zielkonto_id IS NOT NULL").fetchone()[0] == 0)
    pruef("Korrektur: Übertragungen behalten ihr Zielkonto",
          dict(con.execute("SELECT id, zielkonto_id FROM buchungen WHERE typ = 'Uebertragung'")) == uebertragungen
          and all(uebertragungen.values()), uebertragungen)
    pruef("Korrektur: Merker gesetzt",
          con.execute("SELECT value FROM einstellungen WHERE key = 'korrektur_zielkonto_v261_erledigt'").fetchone()[0] == "1")

    kat = next(k["id"] for k in c.get("/api/kategorien").json() if k["name"] == "Lebensmittel/Verpflegung")
    def anlegen(typ, **mehr):
        return c.post("/api/buchungen", json={"konto_id": konten[0], "zielkonto_id": konten[1], "datum": "2026-10-20",
                                              "betrag": 3, "kategorie_id": kat, "typ": typ, "beschreibung": f"P {typ}", **mehr})
    ist, plan, ueb = anlegen("Ist"), anlegen("Plan"), anlegen("Uebertragung")
    zk = lambda r: con.execute("SELECT zielkonto_id FROM buchungen WHERE id = ?", (r.json()["id"],)).fetchone()[0]
    pruef("Anlegen: Ist mit mitgeschicktem Zielkonto speichert keines", ist.status_code < 300 and zk(ist) is None)
    pruef("Anlegen: Plan mit mitgeschicktem Zielkonto speichert keines", plan.status_code < 300 and zk(plan) is None)
    pruef("Anlegen: Übertragung behält das Zielkonto", ueb.status_code < 300 and zk(ueb) == konten[1])
    pruef("Anlegen: Übertragung ohne Zielkonto weiterhin abgelehnt",
          c.post("/api/buchungen", json={"konto_id": konten[0], "datum": "2026-10-20", "betrag": 3,
                                         "typ": "Uebertragung"}).status_code >= 400)
    liste_ziel = c.get(f"/api/buchungen?konto_id={konten[1]}").json()
    pruef("Kontofilter: Ist-Buchung erscheint nicht beim fremden Konto, die Übertragung schon",
          not any(b["beschreibung"] == "P Ist" for b in liste_ziel) and any(b["beschreibung"] == "P Uebertragung" for b in liste_ziel))
    con.close()

# Zweiter Start: nichts mehr zu tun
with TestClient(app) as c:
    st = c.get("/api/start-status").json()
    pruef("Zweiter Start: keine Korrektur mehr", not any("Zielkonto" in m for m in st["migration"]), st["migration"])

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

"""Upgrade-Test 1.9.1 -> 1.10: Migration, Start, Daten unverändert, neue Funktion nutzbar."""
import os, sys, shutil, sqlite3
quelle, ziel = sys.argv[2], sys.argv[3]
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)

def schnappschuss(pfad):
    c = sqlite3.connect(pfad); c.row_factory = sqlite3.Row
    daten = {}
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        spalten = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
        daten[t] = (spalten, [tuple(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY rowid")])
    c.close()
    return daten

vorher = schnappschuss(os.path.join(ziel, "finanzdaten.db"))
os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, sys.argv[1])
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    st = c.get("/api/start-status").json()
    print("Migration:", st["migration"])
    print("Konflikte:", st["vorzeichen_konflikte_buchungen"], st["vorzeichen_konflikte_vorlagen"],
          "neu wk/dl/av:", st["anzahl_neue_ist_buchungen_wiederkehrend"], st["anzahl_neue_ist_buchungen_darlehen"],
          st["anzahl_neue_ist_buchungen_altersvorsorge"])
    salden_api = {k["name"]: k["saldo"] for k in c.get("/api/konten").json()}
    wk = c.get("/api/wiederkehrend").json()
    assert all(v["kategorie_anzeige"] for v in wk)
nachher = schnappschuss(os.path.join(ziel, "finanzdaten.db"))
fehler = 0
for t, (spalten, zeilen) in vorher.items():
    sp2, z2 = nachher[t]
    idx = [sp2.index(s) for s in spalten]
    z2_alt = [tuple(r[i] for i in idx) for r in z2]
    neue = [s for s in sp2 if s not in spalten]
    if t in ("backups_log",):
        continue
    if z2_alt != zeilen:
        fehler += 1
        print("ABWEICHUNG in", t, len(zeilen), len(z2_alt))
        for a, b in zip(zeilen, z2_alt):
            if a != b: print("  vorher", a, "\n  nachher", b); break
    if neue:
        werte = {s: {r[sp2.index(s)] for r in z2} for s in neue}
        print(f"{t}: neue Spalten {neue} Werte {werte}")
print("Tabellen geprüft:", len(vorher), "Abweichungen:", fehler)
print("Salden:", salden_api)
# zweiter Start: idempotent
with TestClient(app) as c:
    st = c.get("/api/start-status").json()
    print("2. Start Migration:", st["migration"], "neu:", st["anzahl_neue_ist_buchungen_wiederkehrend"])
    # neue Funktion nutzbar
    konten = {k["name"]: k["id"] for k in c.get("/api/konten").json()}
    sz = c.get("/api/sparziele").json()[0]["id"]
    r = c.post("/api/wiederkehrend", json={"konto_id": konten["Girokonto"], "zielkonto_id": konten["Tagesgeld"], "betrag": 150,
        "intervall": "monatlich", "tag_des_monats": 3, "startdatum": "2026-09-01", "beschreibung": "Sparrate", "sparziel_id": sz})
    print("Umbuchungs-Vorlage:", r.status_code, r.json())
    neu = [b for b in c.get("/api/buchungen").json() if b["wiederkehrend_id"] == r.json()["id"]]
    print("erzeugt:", [(b["datum"], b["typ"], b["betrag"], b["konto_id"], b["zielkonto_id"], b["sparziel_id"]) for b in neu])
    print("Salden neu:", {k["name"]: k["saldo"] for k in c.get("/api/konten").json()})

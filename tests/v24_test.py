"""Fachliche Tests 2.4: Datenbank wiederherstellen (Upload und aus Backup), Befund N (eindeutige Backup-Namen)."""
import os, sys, shutil, sqlite3, io
code, quelle, ziel, fremd = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from app.main import app
from app.core import wiederherstellen, backup, db as db_modul

ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""))
DB = os.path.join(ziel, "finanzdaten.db")
BK = os.path.join(ziel, "Backups")
def zahl(pfad, sql):
    c = sqlite3.connect(pfad); w = c.execute(sql).fetchone()[0]; c.close(); return w
def hochladen(c, inhalt, name="test.db"):
    return c.post("/api/admin/wiederherstellen/hochladen", files={"datei": (name, io.BytesIO(inhalt), "application/octet-stream")})
staging = lambda: [f for f in os.listdir(os.path.join(BK, ".wiederherstellen")) if f.endswith(".db")] \
    if os.path.isdir(os.path.join(BK, ".wiederherstellen")) else []

with TestClient(app) as c:
    vorher_buchungen = zahl(DB, "SELECT COUNT(*) FROM buchungen")
    vorher_kat = zahl(DB, "SELECT COUNT(*) FROM kategorien")
    vorher_salden = {k["name"]: k["saldo"] for k in c.get("/api/konten").json()}
    c.post("/api/admin/backup")
    liste_vorher = [b["dateiname"] for b in c.get("/api/admin/backups").json()]

    # ── Prüfung der Datei ──
    r = hochladen(c, b"das ist keine Datenbank")
    pruef("Keine SQLite-Datei wird abgelehnt", r.status_code == 422 and "keine SQLite" in r.text, r.text)
    leer = os.path.join(ziel, "leer.db"); sqlite3.connect(leer).execute("CREATE TABLE x (a)").connection.commit()
    r = hochladen(c, open(leer, "rb").read())
    pruef("Fremde SQLite-Datenbank wird abgelehnt (Pflichttabellen fehlen)", r.status_code == 422 and "keine Datenbank dieses Programms" in r.text, r.text)
    roh = open(os.path.join(fremd, "finanzdaten.db"), "rb").read()
    r = hochladen(c, roh[: len(roh) // 2])
    pruef("Abgeschnittene Datei wird abgelehnt", r.status_code == 422, r.text)
    pruef("Abgelehnte Dateien bleiben nicht liegen, Datenbank unverändert",
          not staging() and zahl(DB, "SELECT COUNT(*) FROM buchungen") == vorher_buchungen, staging())
    alt_max = wiederherstellen.MAX_GROESSE; wiederherstellen.MAX_GROESSE = 1000
    r = hochladen(c, roh)
    wiederherstellen.MAX_GROESSE = alt_max
    pruef("Zu große Datei wird abgelehnt", r.status_code == 422 and "500 MB" in r.text and not staging(), r.text)

    # ── Upload einer älteren Datenbank (2.1) ──
    fremd_buchungen = zahl(os.path.join(fremd, "finanzdaten.db"), "SELECT COUNT(*) FROM buchungen")
    fremd_log = [r[0] for r in sqlite3.connect(os.path.join(fremd, "finanzdaten.db")).execute("SELECT dateiname FROM backups_log")]
    v = hochladen(c, roh, "alt.db").json()
    pruef("Prüfung liefert Kennzahlen von Datei und jetzigem Stand und eine Phrase",
          v["datei"]["buchungen"] == fremd_buchungen and v["aktuell"]["buchungen"] == vorher_buchungen
          and v["bezeichnung"] == "alt.db" and v["phrase"] and v["token"] and len(staging()) == 1, v)
    r = c.post("/api/admin/wiederherstellen/ausfuehren", json={"quelle": v["quelle"], "token": v["token"], "phrase": "falsch-falsch-1"})
    pruef("Falsche Phrase: abgelehnt, nichts geändert", r.status_code == 422 and zahl(DB, "SELECT COUNT(*) FROM buchungen") == vorher_buchungen)
    r = c.post("/api/admin/wiederherstellen/ausfuehren", json={"quelle": "backup:finanzdaten.db", "token": v["token"], "phrase": v["phrase"]})
    pruef("Phrase gilt nur für ihre Quelle", r.status_code == 422, r.text)
    r = c.post("/api/admin/wiederherstellen/ausfuehren", json={"quelle": v["quelle"], "token": v["token"], "phrase": v["phrase"]})
    e = r.json()
    pruef("Wiederherstellen erfolgreich", r.status_code == 200, r.text[:300])
    pruef("Backup „vor Wiederherstellung“ enthält den vorherigen Stand",
          os.path.exists(os.path.join(BK, e["backup_vorher"]))
          and zahl(os.path.join(BK, e["backup_vorher"]), "SELECT COUNT(*) FROM buchungen") == vorher_buchungen
          and zahl(os.path.join(BK, e["backup_vorher"]), "SELECT COUNT(*) FROM kategorien") == vorher_kat)
    pruef("Datei aus 2.1 beim Start angepasst (Kategorie-Umstellung 2.2), Start-Status aktualisiert",
          any("Darlehens-Zinsen" in m for m in e["start"]["migration"])
          and c.get("/api/start-status").json()["migration"] == e["start"]["migration"])
    fremd_max = zahl(os.path.join(fremd, "finanzdaten.db"), "SELECT MAX(id) FROM buchungen")
    pruef("Daten der Datei aktiv (alle Buchungen der Datei, dazu nur nachgeholte Termine)",
          zahl(DB, f"SELECT COUNT(*) FROM buchungen WHERE id <= {fremd_max}") == fremd_buchungen
          and e["kennzahlen"]["buchungen"] == fremd_buchungen + zahl(DB, f"SELECT COUNT(*) FROM buchungen WHERE id > {fremd_max}"),
          (e["kennzahlen"], fremd_buchungen))
    liste = [b["dateiname"] for b in c.get("/api/admin/backups").json()]
    pruef("Backup-Liste bleibt die der Installation (plus neue Backups), keine Einträge aus der Datei",
          set(liste_vorher) <= set(liste) and e["backup_vorher"] in liste
          and not (set(fremd_log) - set(liste_vorher)) & set(liste) and all(os.path.exists(os.path.join(BK, d)) for d in liste),
          (liste, fremd_log))
    neu = [d for d in liste if d not in liste_vorher]  # ältere Doppel stammen aus der Testdatenbank (alter Code)
    pruef("Befund N: Backups derselben Sekunde überschreiben sich nicht", len(neu) >= 2 and len(neu) == len(set(neu)), neu)
    pruef("Hochgeladene Datei danach entfernt", not staging(), staging())
    r = c.post("/api/admin/wiederherstellen/ausfuehren", json={"quelle": v["quelle"], "token": v["token"], "phrase": v["phrase"]})
    pruef("Phrase ist nur einmal gültig", r.status_code == 422, r.text)

    # ── Aus der Backup-Liste zurück auf den vorherigen Stand ──
    r = c.post("/api/admin/wiederherstellen/backup", json={"dateiname": "../finanzdaten.db"})
    pruef("Backup außerhalb der Liste wird abgelehnt", r.status_code == 422, r.text)
    r = c.post("/api/admin/wiederherstellen/backup", json={"dateiname": "gibt-es-nicht.db"})
    pruef("Unbekanntes Backup wird abgelehnt", r.status_code == 422, r.text)
    v2 = c.post("/api/admin/wiederherstellen/backup", json={"dateiname": e["backup_vorher"]}).json()
    r = c.post("/api/admin/wiederherstellen/ausfuehren", json={"quelle": v2["quelle"], "token": v2["token"], "phrase": v2["phrase"]})
    pruef("Backup aus der Liste wiederhergestellt", r.status_code == 200, r.text[:200])
    pruef("Vorheriger Stand wieder aktiv: Buchungen, Kategorien, Salden",
          zahl(DB, "SELECT COUNT(*) FROM buchungen") == vorher_buchungen and zahl(DB, "SELECT COUNT(*) FROM kategorien") == vorher_kat
          and {k["name"]: k["saldo"] for k in c.get("/api/konten").json()} == vorher_salden)
    pruef("Das eingespielte Backup bleibt in der Liste erhalten",
          os.path.exists(os.path.join(BK, e["backup_vorher"])) and e["backup_vorher"] in [b["dateiname"] for b in c.get("/api/admin/backups").json()])

    # ── Rückfall bei gescheitertem Start ──
    v3 = hochladen(c, roh, "alt.db").json()
    def kaputt():
        raise RuntimeError("Teststart scheitert")
    try:
        wiederherstellen.ausfuehren(v3["quelle"], v3["token"], v3["phrase"], kaputt)
        fehler = None
    except wiederherstellen.WiederherstellenFehler as x:
        fehler = str(x)
    pruef("Gescheiterter Start: Meldung und vorheriger Stand wieder aktiv",
          fehler and "vorherige Stand" in fehler and zahl(DB, "SELECT COUNT(*) FROM buchungen") == vorher_buchungen
          and zahl(DB, "SELECT COUNT(*) FROM kategorien") == vorher_kat, fehler)
    pruef("Nach dem Rückfall stimmt die Backup-Liste mit dem Ordner überein",
          all(os.path.exists(os.path.join(BK, b["dateiname"])) for b in c.get("/api/admin/backups").json()))

    # ── Befund N direkt ──
    conn = db_modul.verbindung()
    a = backup.backup_erstellen(conn, "manuell", beschreibung="Test A")
    b = backup.backup_erstellen(conn, "manuell", beschreibung="Test B")
    conn.close()
    pruef("Befund N: zwei Backups in derselben Sekunde bekommen verschiedene Namen", a != b
          and os.path.exists(os.path.join(BK, a)) and os.path.exists(os.path.join(BK, b)), (a, b))

# ── Befund O: automatische Backups nach Stichtag, je Stichtag genau eines ──
from datetime import date
from app.core import startup
erstellt = [startup.ausfuehren(t)["backup_erstellt"] for t in
            (date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 9), date(2026, 11, 15), date(2026, 11, 20), date(2026, 11, 30))]
pruef("Befund O: Ultimo-Backup des Vormonats nur beim ersten Start, nach Stichtag benannt",
      erstellt[0] == "finanzdaten_2026-10-31_automatisch_ultimo.db" and erstellt[1] is None and erstellt[2] is None, erstellt)
pruef("Befund O: Backups zum 15. und zum Ultimo je einmal",
      erstellt[3] == "finanzdaten_2026-11-15_automatisch_15.db" and erstellt[4] is None
      and erstellt[5] == "finanzdaten_2026-11-30_automatisch_ultimo.db", erstellt)

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

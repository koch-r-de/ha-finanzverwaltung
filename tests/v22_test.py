"""Fachliche Tests 2.2: Befund K (empfohlene Kategorien nur bei neuer DB) und Kategorie-Umstellung."""
import os, sys, shutil, sqlite3, tempfile
code, quelle, ziel = sys.argv[1], sys.argv[2], sys.argv[3]
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
DB = os.path.join(ziel, "finanzdaten.db")
ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""))

# ── Ausgangslage einer gewachsenen 2.1-Installation nachbauen ──
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
key = lambda k: c.execute("SELECT id FROM kategorien WHERE system_key = ?", (k,)).fetchone()[0]
name_id = lambda n, p: c.execute("SELECT id FROM kategorien WHERE name = ? AND parent_id = ?", (n, p)).fetchone()
ein, leb, vv, rente_fest = key("einnahmen"), key("ausgaben_lebenshaltung"), key("ausgaben_versicherung"), key("altersvorsorge_rente")
lm = name_id("Lebensmittel", leb)[0]
c.execute("INSERT INTO kategorien (name, parent_id, typ) VALUES ('Lebensmittel/Verpflegung', ?, 'ausgabe')", (leb,))
lv = c.execute("SELECT last_insert_rowid()").fetchone()[0]
c.execute("INSERT INTO kategorien (name, parent_id, typ) VALUES ('Rente', ?, 'einnahme')", (ein,))
rente_frei = c.execute("SELECT last_insert_rowid()").fetchone()[0]
c.execute("INSERT INTO kategorien (name, parent_id, typ) VALUES ('Versicherungen', ?, 'ausgabe')", (vv,))
c.execute("INSERT INTO kategorien (name, parent_id, typ) VALUES ('Haustier', ?, 'ausgabe')", (key("ausgaben"),))
c.execute("UPDATE kategorien SET siri_favorit = 1 WHERE id = ?", (lm,))
c.execute("INSERT INTO buchungen (konto_id, datum, betrag, kategorie_id, typ, beschreibung) VALUES (1, '2026-10-03', -25.5, ?, 'Ist', 'LV alt')", (lv,))
c.execute("INSERT INTO buchungen (konto_id, datum, betrag, kategorie_id, typ, beschreibung) VALUES (1, '2026-09-30', 410, ?, 'Ist', 'Rente frei')", (rente_frei,))
c.execute("""INSERT INTO wiederkehrende_buchungen (konto_id, betrag, kategorie_id, beschreibung, intervall, tag_des_monats, startdatum, aktiv)
             VALUES (1, 410, ?, 'Rente monatlich', 'monatlich', 30, '2027-01-01', 1)""", (rente_frei,))
c.execute("INSERT INTO kategorie_regeln (muster, kategorie_id, prioritaet) VALUES ('Markt', ?, 50)", (lm,))
c.commit()
vorher = {
    "lm": c.execute("SELECT COUNT(*), ROUND(SUM(betrag),2) FROM buchungen WHERE kategorie_id = ?", (lm,)).fetchone(),
    "lv": c.execute("SELECT COUNT(*), ROUND(SUM(betrag),2) FROM buchungen WHERE kategorie_id = ?", (lv,)).fetchone(),
    "budgets_lm": c.execute("SELECT COUNT(*) FROM budgets WHERE kategorie_id = ?", (lm,)).fetchone()[0],
    "regeln_lm": c.execute("SELECT COUNT(*) FROM kategorie_regeln WHERE kategorie_id = ?", (lm,)).fetchone()[0],
    "anzahl_kat": c.execute("SELECT COUNT(*) FROM kategorien").fetchone()[0],
}
c.close()

os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as cl:
    st = cl.get("/api/start-status").json()
    salden_nach = {k["name"]: k["saldo"] for k in cl.get("/api/konten").json()}
    mig = st["migration"]
    print("   Migration:", *mig, sep="\n     ")
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
pruef("Start-Status nennt Backup und jeden Umstellungsschritt",
      any("Backup vor der Kategorie-Umstellung" in m for m in mig) and any("Lebensmittel" in m for m in mig)
      and any("Rente" in m for m in mig) and any("Darlehens-Zinsen" in m for m in mig))
pruef("Backup „vor Kategorie-Umstellung 2.2“ angelegt und vorhanden",
      (r := c.execute("SELECT dateiname FROM backups_log WHERE beschreibung = 'vor Kategorie-Umstellung 2.2'").fetchone())
      and os.path.exists(os.path.join(ziel, "Backups", r[0])))
pruef("„Lebensmittel“ ist weg", not c.execute("SELECT 1 FROM kategorien WHERE id = ?", (lm,)).fetchone())
n_lv = c.execute("SELECT COUNT(*), ROUND(SUM(betrag),2) FROM buchungen WHERE kategorie_id = ?", (lv,)).fetchone()
pruef("Buchungen von „Lebensmittel“ hängen an „Lebensmittel/Verpflegung“ (Anzahl und Summe)",
      n_lv[0] == vorher["lm"][0] + vorher["lv"][0] and abs(n_lv[1] - (vorher["lm"][1] + vorher["lv"][1])) < 0.01, (n_lv, vorher))
pruef("Budgets und Regeln umgehängt", c.execute("SELECT COUNT(*) FROM budgets WHERE kategorie_id = ?", (lv,)).fetchone()[0] == vorher["budgets_lm"]
      and c.execute("SELECT COUNT(*) FROM kategorie_regeln WHERE kategorie_id = ?", (lv,)).fetchone()[0] == vorher["regeln_lm"])
pruef("Siri-Favorit übernommen", c.execute("SELECT siri_favorit FROM kategorien WHERE id = ?", (lv,)).fetchone()[0] == 1)
pruef("Feste „Rente“ direkt unter Einnahmen", c.execute("SELECT parent_id FROM kategorien WHERE id = ?", (rente_fest,)).fetchone()[0] == ein)
pruef("Freie „Rente“ zusammengeführt: Buchung und Vorlage hängen an der festen",
      not c.execute("SELECT 1 FROM kategorien WHERE id = ?", (rente_frei,)).fetchone()
      and c.execute("SELECT COUNT(*) FROM buchungen WHERE beschreibung = 'Rente frei' AND kategorie_id = ?", (rente_fest,)).fetchone()[0] == 1
      and c.execute("SELECT COUNT(*) FROM wiederkehrende_buchungen WHERE beschreibung = 'Rente monatlich' AND kategorie_id = ?", (rente_fest,)).fetchone()[0] == 1)
pruef("Genau eine „Rente“", c.execute("SELECT COUNT(*) FROM kategorien WHERE name = 'Rente'").fetchone()[0] == 1)
pruef("„Darlehens-Zinsen“ statt „Zinsen“", c.execute("SELECT name FROM kategorien WHERE system_key = 'darlehen_zinsen'").fetchone()[0] == "Darlehens-Zinsen")
pruef("„Versicherungen“ heißt „Sach-Versicherungen“", name_id("Sach-Versicherungen", vv) and not name_id("Versicherungen", vv))
neue = ["Arztkosten & Medikamente", "Futter", "Sonstiger Haustierbedarf", "Kleidung", "Steuern", "Wasser", "Heizung",
        "Renovierung", "Grundsteuer", "Zinsen & Kapitalerträge"]
pruef("Neue Kategorien angelegt, Haustier nicht doppelt",
      all(c.execute("SELECT COUNT(*) FROM kategorien WHERE name = ?", (n,)).fetchone()[0] == 1 for n in neue + ["Haustier"]))
haustier = c.execute("SELECT id FROM kategorien WHERE name = 'Haustier'").fetchone()[0]
pruef("Haustier-Unterkategorien hängen am vorhandenen „Haustier“",
      c.execute("SELECT COUNT(*) FROM kategorien WHERE parent_id = ?", (haustier,)).fetchone()[0] == 3)
pruef("„Zinsen & Kapitalerträge“ direkt unter Einnahmen, Typ Einnahme",
      tuple(c.execute("SELECT parent_id, typ FROM kategorien WHERE name = 'Zinsen & Kapitalerträge'").fetchone()) == (ein, "einnahme"))
pruef("Neue Kategorien haben den Typ der Oberkategorie",
      not c.execute("SELECT 1 FROM kategorien WHERE typ IS NULL AND name IN (%s)" % ",".join("?" * len(neue)), neue).fetchone())
c.close()

with TestClient(app) as cl:
    st2 = cl.get("/api/start-status").json()
    pruef("Zweiter Start ohne erneute Umstellung", not st2["migration"], st2["migration"])
    pruef("Salden unverändert durch die Umstellung", {k["name"]: k["saldo"] for k in cl.get("/api/konten").json()} == salden_nach)
    kats = {k["name"]: k for k in cl.get("/api/kategorien").json()}
    # Befund K: löschen und umbenennen bleibt dauerhaft
    r = cl.delete(f"/api/kategorien/{kats['ÖPNV']['id']}")
    strom = kats["Strom"]
    r2 = cl.put(f"/api/kategorien/{strom['id']}", json={"name": "Energie", "parent_id": strom["parent_id"]})
    pruef("Befund K: ÖPNV gelöscht, Strom umbenannt", r.status_code == 200 and r2.status_code == 200, (r.text, r2.text))
with TestClient(app) as cl:
    namen = [k["name"] for k in cl.get("/api/kategorien").json()]
    pruef("Befund K: nach Neustart kein neues „ÖPNV“ und kein neues „Strom“", "ÖPNV" not in namen and "Strom" not in namen and "Energie" in namen)

# ── Neue, leere Datenbank ──
leer = tempfile.mkdtemp()
import importlib
os.environ["FINANZAPP_DATENVERZEICHNIS"] = leer
import app.core.db as dbm
dbm.DB_PFAD = dbm.Path(leer) / "finanzdaten.db"; dbm.BACKUP_VERZEICHNIS = dbm.Path(leer) / "Backups"
import app.core.backup as bk
bk.DB_PFAD = dbm.DB_PFAD; bk.BACKUP_VERZEICHNIS = dbm.BACKUP_VERZEICHNIS
erg = dbm.initialisieren()
c = sqlite3.connect(dbm.DB_PFAD); c.row_factory = sqlite3.Row
frei = {r["name"]: r["p"] for r in c.execute(
    "SELECT k.name, p.name AS p FROM kategorien k JOIN kategorien p ON p.id = k.parent_id WHERE k.system_key IS NULL")}
soll = {n: None for n, _ in dbm.EMPFOHLENE_KATEGORIEN}
pruef("Neue DB: genau die empfohlene Liste (inkl. KFZ-Unterhalt, Lebensmittel/Verpflegung, Steuern)",
      set(frei) == set(soll) and "KFZ-Unterhalt" in frei and "Lebensmittel" not in frei, sorted(set(frei) ^ set(soll)))
pruef("Neue DB: keine persönlichen Kategorien (Haustier, Grundsteuer)", "Haustier" not in frei and "Grundsteuer" not in frei)
pruef("Neue DB: Rente unter Einnahmen, Darlehens-Zinsen",
      c.execute("SELECT p.system_key FROM kategorien k JOIN kategorien p ON p.id = k.parent_id WHERE k.system_key = 'altersvorsorge_rente'").fetchone()[0] == "einnahmen"
      and c.execute("SELECT name FROM kategorien WHERE system_key = 'darlehen_zinsen'").fetchone()[0] == "Darlehens-Zinsen")
pruef("Neue DB: Umstellung als erledigt gemerkt, kein Backup",
      c.execute("SELECT value FROM einstellungen WHERE key = 'migration_kategorien_v22_erledigt'").fetchone()[0] == "1"
      and not c.execute("SELECT 1 FROM backups_log").fetchone())
pruef("Neue DB: alle Kategorien mit Typ (außer Darlehen/Umbuchung)",
      not c.execute("SELECT 1 FROM kategorien WHERE typ IS NULL AND system_key NOT IN ('darlehen','umbuchung')").fetchone())

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

"""Upgrade-Test: eine Datenbank erst mit dem Code der Vorversion hochziehen,
dann mit dem neuen Code starten und alle Tabellen vergleichen.

Aufruf (aus dem Wurzelordner):
  python3 tests/upgrade_test.py <code_neu> <quelle> <ziel> <code_alt>
  <code_neu>, <code_alt>: Ordner finanzverwaltung/ der beiden Stände, den alten
  zum Beispiel per „git worktree add ../fv-alt <commit>“.
Umgebung (optional): UPGRADE_ZEIT_ALT, UPGRADE_ZEIT_NEU als ISO-Zeitpunkt,
damit friert FINANZAPP_FESTE_ZEIT die Uhr der beiden Läufe ein.

Geprüft wird:
- Start mit dem neuen Code ohne Fehler, Migrationsschritte im Start-Status
- bestehende Zeilen aller Tabellen unverändert (neue Spalten und neue Zeilen
  erlaubt, entfernte Tabellen werden genannt)
- zweiter Start: keine Migration, keine neuen Buchungen
- 2.6.1: Befund P, Zielkonto bei Ist/Plan geleert, Übertragungen unverändert
- 2.6: Tabelle feiertage entfernt, NRW als Vorschlag, Umstellungstag gemerkt,
  keine doppelten Termine für Termine, die die Vorversion nach NRW vorgezogen
  gebucht hat (Übergang), danach Bundesland wählbar und Hinweise nutzbar
"""
import json, os, shutil, sqlite3, subprocess, sys

ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""))

ENTFERNT_ERLAUBT = {"feiertage"}          # seit 2.6 berechnet statt gespeichert
NUR_ZUWACHS = {"buchungen", "plan_buchung_protokoll", "backups_log"}   # neue Zeilen durch Generatoren/Backups


def schnappschuss(pfad):
    c = sqlite3.connect(pfad)
    daten = {}
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        spalten = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
        daten[t] = (spalten, [tuple(r) for r in c.execute(f"SELECT rowid, * FROM {t} ORDER BY rowid")])
    c.close()
    return daten


def lauf(code, ordner, zeit, skript):
    """Startet den Code in einem eigenen Prozess (TestClient) und führt `skript` mit `c` aus."""
    env = {**os.environ, "FINANZAPP_DATENVERZEICHNIS": ordner}
    if zeit:
        env["FINANZAPP_FESTE_ZEIT"] = zeit
    else:
        env.pop("FINANZAPP_FESTE_ZEIT", None)
    programm = ("import json, sys\nsys.path.insert(0, %r)\nfrom fastapi.testclient import TestClient\n"
                "from app.main import app\nERG = {}\nwith TestClient(app) as c:\n" % code
                + "".join("    " + z + "\n" for z in skript.strip().splitlines())
                + "print('ERGEBNIS ' + json.dumps(ERG, default=str))\n")
    r = subprocess.run([sys.executable, "-c", programm], env=env, capture_output=True, text=True, timeout=600)
    zeilen = [z for z in r.stdout.splitlines() if z.startswith("ERGEBNIS ")]
    if r.returncode or not zeilen:
        print(r.stdout[-2000:], r.stderr[-3000:])
        raise SystemExit("Lauf fehlgeschlagen")
    return json.loads(zeilen[-1][9:])


code_neu, quelle, ziel, code_alt = sys.argv[1:5]
zeit_alt = os.environ.get("UPGRADE_ZEIT_ALT", "")
zeit_neu = os.environ.get("UPGRADE_ZEIT_NEU", "")
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
DB = os.path.join(ziel, "finanzdaten.db")

# 1. Mit dem Code der Vorversion hochziehen (wie ein Anwender, der die Vorversion nutzt)
alt = lauf(code_alt, ziel, zeit_alt, """
st = c.get("/api/start-status").json()
ERG["version"] = st["version"]
ERG["salden"] = {k["name"]: k["saldo"] for k in c.get("/api/konten").json()}
# Befund P (bis 2.6): Ist-Buchung mit Zielkonto, wie sie das Formular anlegte
konten = c.get("/api/konten").json()
kat = next(k["id"] for k in c.get("/api/kategorien").json() if k["name"] == "Lebensmittel/Verpflegung")
ERG["befund_p"] = c.post("/api/buchungen", json={"konto_id": konten[0]["id"], "zielkonto_id": konten[1]["id"],
    "datum": "2026-10-20", "betrag": 4.5, "kategorie_id": kat, "typ": "Ist", "beschreibung": "Befund P"}).json()["id"]
ERG["uebertragung"] = c.post("/api/buchungen", json={"konto_id": konten[0]["id"], "zielkonto_id": konten[1]["id"],
    "datum": "2026-10-20", "betrag": 10, "typ": "Uebertragung", "beschreibung": "Echte Übertragung"}).json()["id"]
""")
print("Vorversion gestartet, Salden:", alt["salden"])
vorher = schnappschuss(DB)

# 2. Mit dem neuen Code starten
neu = lauf(code_neu, ziel, zeit_neu, """
st = c.get("/api/start-status").json()
ERG["migration"] = st["migration"]
ERG["neu"] = [st["anzahl_neue_ist_buchungen_wiederkehrend"], st["anzahl_neue_ist_buchungen_darlehen"],
              st["anzahl_neue_ist_buchungen_altersvorsorge"]]
ERG["regionen"] = c.get("/api/feiertage/regionen").json()
ERG["salden"] = {k["name"]: k["saldo"] for k in c.get("/api/konten").json()}
""")
print("Migration:", neu["migration"])
print("Neue Buchungen (Vorlagen, Darlehen, Altersvorsorge):", neu["neu"])
nachher = schnappschuss(DB)

pruef("Start mit dem neuen Code, Migrationsschritte im Start-Status", neu["migration"], neu)
abweichend, entfernt = [], []
for t, (spalten, zeilen) in vorher.items():
    if t not in nachher:
        entfernt.append(t)
        continue
    sp2, z2 = nachher[t]
    # rowid + alte Spalten; erzeugt_bis setzen die Generatoren bei jedem Start neu
    idx = [0] + [sp2.index(s) + 1 for s in spalten if s != "erzeugt_bis"]
    alt_spalten = {r[0]: tuple(r[i] for i in idx) for r in z2}
    alt_idx = [0] + [spalten.index(s) + 1 for s in spalten if s != "erzeugt_bis"]
    for r in zeilen:
        r = tuple(r[i] for i in alt_idx)
        if t == "einstellungen":
            continue   # Schlüssel/Wert: unten gesondert
        n = alt_spalten.get(r[0])
        if t == "buchungen" and n is not None:
            # Befund P (2.6.1): zielkonto_id bei Nicht-Übertragungen wird geleert, unten gesondert geprüft
            iz, it = spalten.index("zielkonto_id") + 1, spalten.index("typ") + 1
            if r[it] != "Uebertragung":
                r, n = r[:iz] + (None,) + r[iz + 1:], n[:iz] + (None,) + n[iz + 1:]
        if n != r:
            abweichend.append((t, r, alt_spalten.get(r[0])))
            break
    neue_zeilen = len(z2) - len(zeilen)
    if neue_zeilen and t not in NUR_ZUWACHS and t != "einstellungen":
        abweichend.append((t, f"{neue_zeilen} neue Zeilen"))
pruef("Bestehende Zeilen aller Tabellen unverändert (neue Spalten erlaubt)", not abweichend, abweichend[:3])
pruef("Entfernt höchstens die Tabelle feiertage (von 2.6 aus schon entfernt)", set(entfernt) <= ENTFERNT_ERLAUBT, entfernt)
e_vorher = {r[1]: r[2] for r in vorher["einstellungen"][1]}
e_nachher = {r[1]: r[2] for r in nachher["einstellungen"][1]}
pruef("Einstellungen: alle bisherigen Werte unverändert",
      all(e_nachher.get(k) == v for k, v in e_vorher.items()), {k: (v, e_nachher.get(k)) for k, v in e_vorher.items() if e_nachher.get(k) != v})
pruef("Einstellungen 2.6: Bundesland leer, Vorschlag NRW",
      e_nachher.get("bundesland") == "" and e_nachher.get("bundesland_vorschlag") == "NW",
      {k: e_nachher.get(k) for k in ("bundesland", "bundesland_vorschlag")})
pruef("Regionen-Endpunkt: nichts gewählt, Vorschlag NRW", neu["regionen"]["gewaehlt"] == "" and neu["regionen"]["vorschlag"] == "NW")

c = sqlite3.connect(DB)
falsch = c.execute("SELECT COUNT(*) FROM buchungen WHERE typ <> 'Uebertragung' AND zielkonto_id IS NOT NULL").fetchone()[0]
pruef("Befund P: kein Zielkonto mehr bei Ist- und Plan-Buchungen, echte Übertragung behält es",
      falsch == 0 and c.execute("SELECT zielkonto_id FROM buchungen WHERE id = ?", (alt["uebertragung"],)).fetchone()[0]
      and c.execute("SELECT zielkonto_id FROM buchungen WHERE id = ?", (alt["befund_p"],)).fetchone()[0] is None)
pruef("Befund P: Backup vor der Korrektur, Schritt im Start-Status",
      any("Zielkonto bei" in m for m in neu["migration"]) and any("Korrektur des Zielkontos" in m for m in neu["migration"]))
c.close()

# Übergang: kein Termin doppelt (gleiche Quelle, gleiche Kategorie, Abstand unter 5 Tagen)
c = sqlite3.connect(DB)
doppelt = c.execute("""
    SELECT a.id, b.id, a.datum, b.datum, a.beschreibung FROM buchungen a JOIN buchungen b
      ON a.id < b.id AND a.kategorie_id IS b.kategorie_id AND a.konto_id = b.konto_id
     AND COALESCE(a.wiederkehrend_id, -1) = COALESCE(b.wiederkehrend_id, -1)
     AND COALESCE(a.ziel_darlehen_id, -1) = COALESCE(b.ziel_darlehen_id, -1)
     AND COALESCE(a.ziel_altersvorsorge_id, -1) = COALESCE(b.ziel_altersvorsorge_id, -1)
     AND (a.wiederkehrend_id IS NOT NULL OR a.ziel_darlehen_id IS NOT NULL OR a.ziel_altersvorsorge_id IS NOT NULL)
     AND ABS(julianday(a.datum) - julianday(b.datum)) < 5""").fetchall()
pruef("Übergang: kein automatischer Termin doppelt gebucht", not doppelt, doppelt[:5])
neue_buchungen = [r for r in nachher["buchungen"][1] if r[0] not in {z[0] for z in vorher["buchungen"][1]}]
print("Neu gebuchte Termine:", [(r[nachher["buchungen"][0].index("datum") + 1], r[nachher["buchungen"][0].index("beschreibung") + 1])
                                 for r in neue_buchungen])
c.close()

# 3. Zweiter Start: nichts mehr zu tun, danach neue Funktion nutzbar
zweit = lauf(code_neu, ziel, zeit_neu, """
st = c.get("/api/start-status").json()
ERG["migration"] = st["migration"]
ERG["neu"] = [st["anzahl_neue_ist_buchungen_wiederkehrend"], st["anzahl_neue_ist_buchungen_darlehen"],
              st["anzahl_neue_ist_buchungen_altersvorsorge"]]
ERG["setzen"] = c.put("/api/feiertage/region", json={"kuerzel": "NW"}).status_code
ERG["liste"] = c.get("/api/feiertage?von_jahr=2027&bis_jahr=2027").json()
konto = c.get("/api/konten").json()[0]["name"]
ERG["siri"] = c.post("/api/siri/buchung", json={"betrag": 1, "kategorie": "Lebensmittel/Verpflegung", "konto": konto,
                                               "datum": "2027-11-01", "beschreibung": "Upgrade-Probe"}).json()
""")
pruef("Zweiter Start: keine Migration, keine neuen Buchungen", not zweit["migration"] and zweit["neu"] == [0, 0, 0], zweit)
pruef("Danach: Bundesland wählbar, Liste 2027 mit 11 NRW-Feiertagen",
      zweit["setzen"] == 200 and len([t for t in zweit["liste"]["tage"] if t["feiertag"]]) == 11)
pruef("Danach: Siri meldet Allerheiligen", zweit["siri"].get("feiertagshinweis") == "01.11.2027 ist ein Feiertag (Allerheiligen).",
      zweit["siri"])

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

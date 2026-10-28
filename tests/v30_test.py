"""Fachliche Tests 3.0: Sperre und Verschlüsselung (Issue #5).

Aufruf: python3 tests/v30_test.py <code> <quelle> <ziel> <code_vorversion>
<code_vorversion> ist der Ordner finanzverwaltung/ von 2.7 für die Gegenprobe
„ohne Schutz wie 2.7“ (alle_tests.py legt ihn per git archive an).

Die Uhr der Sperre wird über schutzdatei.uhr eingefroren. Herkunftsprüfung
steht auf „sperren“, die Clients melden sich mit den Adressen von Ingress
(172.30.32.2), Home Assistant (172.30.32.1) und einem fremden Add-on.
"""
import io, json, logging, os, shutil, sqlite3, subprocess, sys
code, quelle, ziel = sys.argv[1:4]
code_alt = sys.argv[4] if len(sys.argv) > 4 else None
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
os.environ["FINANZAPP_HERKUNFT_PRUEFEN"] = "sperren"
os.environ["FINANZAPP_SUPERVISOR_VERSION"] = "2026.10.5"   # Befund X: Gruppen-Header erst ab dieser Version echt
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from app.main import app
from app.core import db as db_modul, schutzdatei, tresor, schutz

ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""), flush=True)

# Protokoll mitschneiden (alles unter "app" und die Wurzel)
PROTOKOLL = []
class Mitschnitt(logging.Handler):
    def emit(self, r):
        PROTOKOLL.append(r.getMessage())
for name in ("app", ""):
    lg = logging.getLogger(name); lg.addHandler(Mitschnitt()); lg.setLevel(logging.INFO)

UHR = [1_900_000_000.0]
schutzdatei.uhr = lambda: UHR[0]
INGRESS, HA, FREMD = ("172.30.32.2", 40000), ("172.30.32.1", 40001), ("172.30.33.9", 40002)
A = {"X-Remote-User-Id": "id-ralf", "X-Remote-User-Name": "ralf", "X-Remote-User-Display-Name": "Ralf",
     "X-Remote-User-Groups": "system-admin,system-users"}
B = {"X-Remote-User-Id": "id-anna", "X-Remote-User-Name": "anna", "X-Remote-User-Groups": "system-users"}
C = {"X-Remote-User-Id": "id-carl", "X-Remote-User-Name": "carl", "X-Remote-User-Groups": "system-users"}
OHNE_GRUPPEN = {"X-Remote-User-Id": "id-ralf", "X-Remote-User-Name": "ralf"}
PASS = "Ein langer Satz als Passphrase 2026"
PASS2 = "Noch ein anderer langer Satz 2027"
DB = os.path.join(ziel, "finanzdaten.db")


def mit(kopf, token=None):
    return {**kopf, **({"X-Finanz-Sitzung": token} if token else {})}


def klartext_proben():
    c = sqlite3.connect(DB)
    proben = {r[0] for r in c.execute("SELECT name FROM konten")}
    proben |= {r[0] for r in c.execute("SELECT DISTINCT beschreibung FROM buchungen WHERE length(beschreibung) >= 5")}
    proben |= {r[0] for r in c.execute("SELECT name FROM budgets")}
    c.close()
    return {p for p in proben if p and len(p) >= 5}


def dateien(*teile):
    for wurzel in teile:
        p = os.path.join(ziel, wurzel)
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for d, _, namen in os.walk(p):
                for n in namen:
                    yield os.path.join(d, n)


def enthaelt(pfad, proben):
    inhalt = open(pfad, "rb").read()
    return sorted(p for p in proben if p.encode("utf-8") in inhalt)


def ist_klartext(pfad):
    with open(pfad, "rb") as f:
        return f.read(16) == b"SQLite format 3\x00"


# ═══ A. Ohne Schutz wie 2.7 (Gegenprobe mit dem Code der Vorversion) ═══

GEGENPROBE = """
# erstellt_am setzt die Datenbank beim Anlegen (Sekunde), sonst alles vergleichen
ohne = lambda x: [ohne(e) for e in x] if isinstance(x, list) else ({k: ohne(v) for k, v in x.items() if k != "erstellt_am"} if isinstance(x, dict) else x)
K = {"X-Remote-User-Id": "id-ralf", "X-Remote-User-Name": "ralf", "X-Remote-User-Groups": "system-admin"}
for p in ["/api/konten", "/api/konten?nur_aktive=false", "/api/kategorien", "/api/personen?nur_aktive=false",
          "/api/buchungen", "/api/buchungen?inkl_anstehende=true", "/api/wiederkehrend", "/api/budgets",
          "/api/sparziele", "/api/darlehen", "/api/altersvorsorge", "/api/regeln", "/api/siri/favoriten",
          "/api/admin/einstellungen", "/api/feiertage/regionen", "/api/feiertage?von_jahr=2027&bis_jahr=2027",
          "/api/auswertungen/saldo-verlauf?von=2026-01-01&bis=2027-12-31",
          "/api/auswertungen/cashflow?von=2026-01-01&bis=2027-12-31",
          "/api/auswertungen/kategorien?von=2026-01-01&bis=2027-12-31", "/api/auswertungen/jahresuebersicht",
          "/api/plan-buchungen/protokoll", "/api/vorzeichen/konflikte", "/api/admin/zuruecksetzen/uebersicht"]:
    r = c.get(p, headers=K)
    ERG[p] = [r.status_code, ohne(r.json())]
konto = c.get("/api/konten").json()[0]
kat = next(k["id"] for k in c.get("/api/kategorien").json() if k["name"] == "Lebensmittel/Verpflegung")
ERG["siri"] = c.post("/api/siri/buchung", headers=K, json={"betrag": 3.2, "konto": konto["name"],
                     "kategorie": "Lebensmittel/Verpflegung", "datum": "2026-10-20", "beschreibung": "Gegenprobe"}).json()
r = c.post("/api/buchungen", headers=K, json={"konto_id": konto["id"], "datum": "2026-10-21", "betrag": 7,
           "kategorie_id": kat, "beschreibung": "Gegenprobe 2"})
ERG["buchung"] = [r.status_code, r.json()]
ERG["konten_danach"] = c.get("/api/konten").json()
r = c.get("/api/admin/datenbank-herunterladen", headers=K)
ERG["download"] = [r.status_code, r.content[:16].hex()]
r = c.get("/api/admin/export", headers=K)
ERG["export"] = [r.status_code, r.headers.get("content-type"), r.content[:2].hex()]
r = c.get("/api/admin/import-vorlage", headers=K)
ERG["vorlage"] = [r.status_code, r.content[:2].hex()]
"""


def lauf(code_pfad, ordner, skript):
    env = {**os.environ, "FINANZAPP_DATENVERZEICHNIS": ordner, "FINANZAPP_HERKUNFT_PRUEFEN": "aus"}
    programm = ("import json, sys\nsys.path.insert(0, %r)\nfrom fastapi.testclient import TestClient\n"
                "from app.main import app\nERG = {}\nwith TestClient(app) as c:\n" % code_pfad
                + "".join("    " + z + "\n" for z in skript.strip().splitlines())
                + "print('ERGEBNIS ' + json.dumps(ERG, default=str))\n")
    r = subprocess.run([sys.executable, "-c", programm], env=env, capture_output=True, text=True, timeout=600)
    zeilen = [z for z in r.stdout.splitlines() if z.startswith("ERGEBNIS ")]
    if r.returncode or not zeilen:
        print(r.stdout[-2000:], r.stderr[-3000:])
        return None
    return json.loads(zeilen[-1][9:])


if code_alt:
    ordner_alt, ordner_neu = ziel + "_alt27", ziel + "_neu30"
    for o in (ordner_alt, ordner_neu):
        shutil.rmtree(o, ignore_errors=True); shutil.copytree(quelle, o)
    e_alt, e_neu = lauf(code_alt, ordner_alt, GEGENPROBE), lauf(code, ordner_neu, GEGENPROBE)
    unterschiede = [k for k in (e_alt or {}) if (e_neu or {}).get(k) != e_alt[k]]
    pruef(f"A1 Gegenprobe: ohne Schutz liefern {len(e_alt or {})} Abfragen und Buchungen dieselben Antworten wie 2.7",
          e_alt and e_neu and not unterschiede and len(e_alt) >= 28, unterschiede[:5])
    pruef("A2 Gegenprobe: ohne Schutz legt 3.0 keine Schutzdateien an, auch mit Benutzer-Headern",
          not any(os.path.exists(os.path.join(ordner_neu, n)) for n in ("schutz.json", "schutz_zaehler.json", "auszug.json", "stapel")))
else:
    pruef("A1 Gegenprobe mit 2.7: Code der Vorversion fehlt", False)

proben = klartext_proben()
pruef("A3 Testdaten: Klartext-Proben vorhanden", len(proben) >= 10, proben)
pruef("A4 Gegenprobe der Klartext-Prüfung: in der unverschlüsselten Datenbank (Stand 2.7) findet sie alle Proben",
      enthaelt(DB, proben) == sorted(proben))

# ═══ B. Verschlüsselung ═══

with TestClient(app, client=INGRESS) as c:
    ha = TestClient(app, client=HA)
    fremd = TestClient(app, client=FREMD)
    st = c.get("/api/schutz/status", headers=A).json()
    pruef("B1 Status: Sperre und Verschlüsselung aus", not st["sperre"]["aktiv"] and not st["verschluesselung"]["aktiv"], st)
    r = c.post("/api/schutz/verschluesselung/vorbereiten", headers=B, json={"passphrase": PASS, "wiederholung": PASS})
    pruef("B2 Einschalten ohne Adminrecht -> 403", r.status_code == 403, r.text)
    r = c.post("/api/schutz/verschluesselung/vorbereiten", headers=OHNE_GRUPPEN, json={"passphrase": PASS, "wiederholung": PASS})
    pruef("B3 Ohne X-Remote-User-Groups -> 403 mit Hinweis auf Supervisor 2026.10.5",
          r.status_code == 403 and "2026.10.5" in r.text, r.text)
    for version, name in (("2026.10.4", "2026.10.4"), ("", "unbekannt")):
        os.environ["FINANZAPP_SUPERVISOR_VERSION"] = version
        r = c.post("/api/schutz/verschluesselung/vorbereiten", headers=A, json={"passphrase": PASS, "wiederholung": PASS})
        pruef(f"B3x Befund X: Supervisor {name}, Gruppen-Header könnte gefälscht sein -> 403, kein Adminrecht",
              r.status_code == 403 and "2026.10.5" in r.text and not c.get("/api/schutz/verschluesselung", headers=A).json()["verwalten"],
              r.text)
    os.environ["FINANZAPP_SUPERVISOR_VERSION"] = "2026.10.5"
    r = c.post("/api/schutz/verschluesselung/vorbereiten", headers=A, json={"passphrase": PASS, "wiederholung": PASS})
    pruef("B4 Ohne vorherigen unverschlüsselten Download -> 422", r.status_code == 422 and "herunterladen" in r.text, r.text)
    c.get("/api/admin/datenbank-herunterladen", headers=A)
    r = c.post("/api/schutz/verschluesselung/vorbereiten", headers=A, json={"passphrase": "zu kurz", "wiederholung": "zu kurz"})
    pruef("B5 Passphrase unter 16 Zeichen -> 422", r.status_code == 422 and "16" in r.text, r.text)
    r = c.post("/api/schutz/verschluesselung/vorbereiten", headers=A, json={"passphrase": PASS, "wiederholung": PASS + "x"})
    pruef("B6 Passphrase-Wiederholung abweichend -> 422", r.status_code == 422, r.text)
    r = c.post("/api/schutz/verschluesselung/vorbereiten", headers=A,
               json={"passphrase": PASS, "wiederholung": PASS, "mindestlaenge": 40})
    pruef("B7 Eigene Mindestlänge 40 greift beim Einschalten", r.status_code == 422 and "40" in r.text, r.text)
    v = c.post("/api/schutz/verschluesselung/vorbereiten", headers=A, json={"passphrase": PASS, "wiederholung": PASS}).json()
    WH = v["wiederherstellungsschluessel"]
    falsch = WH[:-1] + ("A" if WH[-1] != "A" else "B")
    r = c.post("/api/schutz/verschluesselung/einschalten", headers=A,
               json={"kennung": v["kennung"], "getippt": falsch, "token": v["token"], "phrase": v["phrase"]})
    pruef("B8 Falsch abgetippter Wiederherstellungsschlüssel -> 422, nichts verändert",
          r.status_code == 422 and ist_klartext(DB) and not tresor.aktiv(), r.text)
    r = c.post("/api/schutz/verschluesselung/einschalten", headers=A,
               json={"kennung": v["kennung"], "getippt": WH, "token": v["token"], "phrase": "falsche-phrase-1"})
    pruef("B9 Falsche Bestätigungsphrase -> 422, nichts verändert", r.status_code == 422 and ist_klartext(DB), r.text)
    backups_vorher = len([p for p in dateien("Backups") if p.endswith(".db")])
    r = c.post("/api/schutz/verschluesselung/einschalten", headers=A,
               json={"kennung": v["kennung"], "getippt": WH.lower().replace("-", " "), "token": v["token"], "phrase": v["phrase"]})
    pruef("B10 Einschalten mit abgetipptem Schlüssel (klein, Leerzeichen) und Phrase", r.status_code == 200, r.text)
    schritte = r.json().get("schritte", [])
    pruef("B11 Jeder Schritt als Text: Backup, Prüfung mit Passphrase und Schlüssel, Tausch",
          any("Backup erstellt" in s for s in schritte) and any("Wiederherstellungsschlüssel geprüft" in s for s in schritte)
          and any("ersetzt" in s for s in schritte), schritte)
    pruef("B12 Schritte stehen auch im Protokoll", all(any(s in z for z in PROTOKOLL) for s in schritte))
    SCHLUESSEL = db_modul._SCHLUESSEL
    backups = [p for p in dateien("Backups") if p.endswith(".db")]
    pruef("B13 Datenbank und alle Backups verschlüsselt (kein SQLite-Kopf)",
          not ist_klartext(DB) and backups and all(not ist_klartext(p) for p in backups)
          and len(backups) == backups_vorher + 1, [os.path.basename(p) for p in backups])
    funde = {os.path.relpath(p, ziel): enthaelt(p, proben) for p in [DB] + backups}
    pruef("B14 Keine bekannten Klartexte in Datenbank und Backups", not any(funde.values()), {k: v for k, v in funde.items() if v})
    pruef("B15 Weiter nutzbar ohne Neustart", c.get("/api/konten", headers=A).status_code == 200)
    auszug = json.load(open(os.path.join(ziel, "auszug.json"), encoding="utf-8"))
    pruef("B16 Auszug: Konten, Kategorien, Sparziele, Bundesland, keine Buchungen und Regeln",
          set(auszug) == {"konten", "kategorien", "sparziele", "bundesland"} and len(auszug["konten"]) == 4)
    # neues Backup nach dem Einschalten
    c.post("/api/admin/backup", headers=A)
    neu = [p for p in dateien("Backups") if p.endswith(".db") and p not in backups]
    pruef("B17 Neues Backup nach dem Einschalten ist verschlüsselt", neu and all(not ist_klartext(p) for p in neu))
    # Änderung aktualisiert den Auszug
    r = c.post("/api/konten", headers=A, json={"name": "Bargeldkasse", "typ": "Bargeld", "eroeffnungsdatum": "2026-10-01"})
    auszug = json.load(open(os.path.join(ziel, "auszug.json"), encoding="utf-8"))
    pruef("B18 Neues Konto steht nach dem Speichern im Auszug", r.status_code == 200 and any(k["name"] == "Bargeldkasse" for k in auszug["konten"]), r.text)

# Neustart: zu
with TestClient(app, client=INGRESS) as c:
    ha = TestClient(app, client=HA)
    st = c.get("/api/schutz/status").json()
    pruef("B19 Nach Neustart: verschlüsselt und zu", st["verschluesselung"]["aktiv"] and st["verschluesselung"]["gesperrt"], st)
    pruef("B20 Nach Neustart: Daten-Endpunkte 423, Start-Status 423",
          c.get("/api/konten").status_code == 423 and c.get("/api/start-status").status_code == 423
          and c.get("/api/buchungen").json().get("schutz") == "passphrase")
    pruef("B21 Nach Neustart frei: Hilfe, Feiertage (Region aus dem Auszug), Status",
          c.get("/api/hilfe").status_code == 200 and c.get("/api/feiertage?von_jahr=2027").status_code == 200
          and c.get("/").status_code == 200)
    # Stapel
    r = ha.post("/api/siri/buchung", json={"betrag": 12.34, "konto": "Tagesgeld", "kategorie": "Lebensmittel/Verpflegung",
                                           "beschreibung": "Bäckerei Stapeltest"})
    pruef("B22 Siri gesperrt: vorgemerkt", r.status_code == 200 and r.json().get("vorgemerkt") and "Klärliste" not in r.json()["meldung"], r.text)
    r = ha.post("/api/siri/buchung", json={"betrag": 5, "konto": "Tagesgeld", "beschreibung": "ohne Kategorie"})
    pruef("B23 Siri gesperrt ohne Kategorie -> 400 (Kategorie Pflicht)", r.status_code == 400 and "Kategorie" in r.text, r.text)
    r = ha.post("/api/siri/buchung", json={"betrag": 6.5, "konto": "Giro", "kategorie": "Lebensmittel/Verpflegung",
                                           "beschreibung": "Mehrdeutig Stapeltest"})
    pruef("B24 Siri gesperrt, Konto mehrdeutig: angenommen, Hinweis auf Klärliste",
          r.status_code == 200 and "Klärliste" in r.json()["meldung"], r.text)
    sd = c.get("/api/erfassen/stammdaten").json()
    pruef("B25 Schnellbuchung gesperrt: Stammdaten aus dem Auszug", sd.get("vorgemerkt") and len(sd["konten"]) == 5, sd)
    giro = next(k["id"] for k in sd["konten"] if k["name"] == "Girokonto")
    lm = next(k["id"] for k in sd["kategorien"] if k["name"] == "Lebensmittel/Verpflegung")
    r = c.post("/api/erfassen/buchung", json={"konto_id": giro, "datum": "2026-10-27", "betrag": 8.9,
                                              "kategorie_id": lm, "beschreibung": "Wochenmarkt Stapeltest"})
    pruef("B26 Schnellbuchung gesperrt: vorgemerkt, Antwort ohne Daten", r.status_code == 200 and r.json()["vorgemerkt"]
          and set(r.json()) <= {"vorgemerkt", "feiertagshinweis"}, r.text)
    r = c.post("/api/erfassen/buchung", json={"konto_id": giro, "datum": "2026-10-27", "betrag": 1})
    pruef("B27 Schnellbuchung gesperrt ohne Kategorie -> 400", r.status_code == 400, r.text)
    pruef("B28 Keine Regeln gesperrt: Vorschlag leer", c.get("/api/erfassen/vorschlag?beschreibung=Miete").json()["kategorie_id"] is None)
    stapel = list(dateien("stapel"))
    stapel_proben = {"Bäckerei Stapeltest", "Mehrdeutig Stapeltest", "Wochenmarkt Stapeltest", "Tagesgeld", "Girokonto", "12.34"}
    pruef("B29 Stapel: drei Dateien, keine Klartexte darin",
          len(stapel) == 3 and not any(enthaelt(p, stapel_proben) for p in stapel), [enthaelt(p, stapel_proben) for p in stapel])

# Stapel über einen Neustart, dann falsche Passphrase mit eingefrorener Uhr
with TestClient(app, client=INGRESS) as c:
    pruef("B30 Stapel überdauert den Neustart", len(list(dateien("stapel"))) == 3)
    for i in range(4):
        r = c.post("/api/schutz/entsperren", json={"geheimnis": "falsch falsch falsch falsch"})
    r5 = c.post("/api/schutz/entsperren", json={"geheimnis": "falsch falsch falsch falsch"})
    r6 = c.post("/api/schutz/entsperren", json={"geheimnis": PASS})
    pruef("B31 Passphrase: nach 5 Fehlversuchen 1 Minute Wartezeit, auch die richtige wird abgewiesen",
          r.status_code == 401 and r5.status_code == 401 and r6.status_code == 422 and "1 Minute" in r6.text, (r5.text, r6.text))
    UHR[0] += 61
    r = c.post("/api/schutz/entsperren", json={"geheimnis": PASS})
    pruef("B32 Nach Ablauf der Wartezeit: entsperrt", r.status_code == 200, r.text)
    e = r.json()
    pruef("B33 Beim Entsperren: Programmstart nachgeholt, Stapel 2 gebucht, 1 in die Klärliste",
          "start" in e and e["stapel"] == {"gebucht": 2, "klaerliste": 1}, e.get("stapel"))
    pruef("B34 Stapel danach leer", not list(dateien("stapel")))
    texte = [b["beschreibung"] for b in c.get("/api/buchungen?von=2026-01-01&bis=2030-12-31").json()]
    pruef("B35 Gebuchte Stapel-Einträge in der Buchungsliste",
          "Bäckerei Stapeltest" in texte and "Wochenmarkt Stapeltest" in texte and "Mehrdeutig Stapeltest" not in texte)
    kl = c.get("/api/klaerliste").json()
    pruef("B36 Klärliste: Eintrag mit Grund „mehrdeutig“", len(kl) == 1 and "mehrdeutig" in kl[0]["grund"]
          and kl[0]["daten"]["beschreibung"] == "Mehrdeutig Stapeltest", kl)
    k = {x["name"]: x["id"] for x in c.get("/api/konten").json()}
    r = c.post(f"/api/klaerliste/{kl[0]['id']}/buchen", json={"konto_id": k["Girokonto"], "datum": "2026-10-27", "betrag": 6.5})
    pruef("B37 Klärliste buchen ohne Kategorie -> 400, Eintrag bleibt", r.status_code == 400 and len(c.get("/api/klaerliste").json()) == 1, r.text)
    lm = next(x["id"] for x in c.get("/api/kategorien").json() if x["name"] == "Lebensmittel/Verpflegung")
    r = c.post(f"/api/klaerliste/{kl[0]['id']}/buchen", json={"konto_id": k["Girokonto"], "datum": "2026-10-27",
               "betrag": 6.5, "kategorie_id": lm, "beschreibung": "Mehrdeutig Stapeltest"})
    pruef("B38 Klärliste buchen mit Korrektur: gebucht, Eintrag weg", r.status_code == 200 and not c.get("/api/klaerliste").json(), r.text)
    SCHLUESSEL = db_modul._SCHLUESSEL

# Absturz zwischen Buchen und Löschen der Stapel-Datei: nicht doppelt buchen
with TestClient(app, client=HA) as ha:
    ha.post("/api/siri/buchung", json={"betrag": 2.22, "konto": "Tagesgeld", "kategorie": "Lebensmittel/Verpflegung",
                                       "beschreibung": "Absturztest"})
    eintrag = next(dateien("stapel"))
    conn = db_modul.oeffnen(DB, SCHLUESSEL)
    conn.execute("INSERT INTO stapel_erledigt (kennung) VALUES (?)", (os.path.splitext(os.path.basename(eintrag))[0],))
    conn.commit(); conn.close()
    r = ha.post("/api/schutz/entsperren", json={"geheimnis": PASS})
    texte = [b["beschreibung"] for b in ha.get("/api/buchungen?von=2026-01-01&bis=2030-12-31").json()]
    pruef("B39 Bereits verarbeiteter Stapel-Eintrag wird nur entfernt, nicht doppelt gebucht",
          r.status_code == 200 and r.json()["stapel"]["gebucht"] == 0 and "Absturztest" not in texte and not list(dateien("stapel")), r.text)
    # Klärliste verwerfen
    ha.post("/api/schutz/abmelden")

# Passphrase ändern, Wiederherstellungsschlüssel, Download, Wiederherstellen, XLSX
with TestClient(app, client=INGRESS) as c:
    r = c.post("/api/schutz/entsperren", json={"geheimnis": WH, "neue_passphrase": "kurz", "wiederholung": "kurz"})
    pruef("B40 Neue Passphrase beim Entsperren zu kurz -> 422", r.status_code == 422, r.text)
    r = c.post("/api/schutz/entsperren", json={"geheimnis": PASS, "neue_passphrase": PASS2, "wiederholung": PASS2})
    pruef("B41 Neue Passphrase nur mit dem Wiederherstellungsschlüssel -> 422", r.status_code == 422, r.text)
    r = c.post("/api/schutz/entsperren", json={"geheimnis": PASS})
    pruef("B42 Entsperren mit Passphrase", r.status_code == 200, r.text)
    download_alt = c.get("/api/admin/datenbank-herunterladen", headers=A).content
    pruef("B43 Datenbank-Download verschlüsselt (.fvdb), ohne Klartexte",
          download_alt.startswith(b"FVDB1\n") and not [p for p in proben if p.encode() in download_alt])
    t = c.post("/api/admin/download", headers=A, json={"art": "datenbank"}).json()
    r1, r2 = c.get(f"/api/download/{t['ticket']}"), c.get(f"/api/download/{t['ticket']}")
    pruef("B44 Download über Ticket: verschlüsselt, Ticket nur einmal gültig",
          r1.status_code == 200 and r1.content.startswith(b"FVDB1\n") and r2.status_code == 404 and t["name"].endswith(".fvdb"))
    r = c.post("/api/admin/download", headers=A, json={"art": "datenbank_klartext", "token": "x", "phrase": "y"})
    pruef("B45 Unverschlüsselter Download ohne gültige Phrase -> 422", r.status_code == 422, r.text)
    p = c.post("/api/admin/klartext-phrase?art=datenbank", headers=A).json()
    t = c.post("/api/admin/download", headers=A, json={"art": "datenbank_klartext", "token": p["token"], "phrase": p["phrase"]}).json()
    klar = c.get(f"/api/download/{t['ticket']}").content
    pruef("B46 Unverschlüsselter Download mit Phrase: SQLite mit Klartext, Kopie danach gelöscht",
          klar.startswith(b"SQLite format 3\x00") and b"Girokonto" in klar and not list(dateien("Backups/.export")))
    pruef("B47 Unverschlüsselter Download steht im Protokoll", any("Unverschlüsselter Datenbank-Download" in z for z in PROTOKOLL))
    db_hash_vorher = open(DB, "rb").read()
    r = c.post("/api/schutz/verschluesselung/passphrase", headers=A, json={"geheimnis": "falsch falsch falsch falsch", "neu": PASS2, "wiederholung": PASS2})
    pruef("B48 Passphrase ändern mit falscher bisheriger -> 401", r.status_code == 401, r.text)
    r = c.post("/api/schutz/verschluesselung/passphrase", headers=A, json={"geheimnis": PASS, "neu": "zu kurz", "wiederholung": "zu kurz"})
    pruef("B49 Passphrase ändern zu kurz -> 422", r.status_code == 422, r.text)
    r = c.post("/api/schutz/verschluesselung/passphrase", headers=A, json={"geheimnis": PASS, "neu": PASS2, "wiederholung": PASS2})
    pruef("B50 Passphrase ändern: ok, Datenbankdatei bitgleich (nicht neu verschlüsselt)",
          r.status_code == 200 and open(DB, "rb").read() == db_hash_vorher, r.text)
    # XLSX
    r = c.get("/api/admin/export", headers=A)
    pruef("B51 Export per GET bei Verschlüsselung -> 409", r.status_code == 409, r.text)
    r = c.post("/api/admin/download", headers=A, json={"art": "export"})
    pruef("B52 Export ohne Excel-Kennwort -> 422", r.status_code == 422, r.text)
    r = c.post("/api/admin/download", headers=A, json={"art": "export", "kennwort": "x" * 20, "wiederholung": "y" * 20})
    pruef("B53 Excel-Kennwort-Wiederholung abweichend -> 422", r.status_code == 422, r.text)
    KW = "Excel Kennwort fuer den Test"
    t = c.post("/api/admin/download", headers=A, json={"art": "export", "kennwort": KW, "wiederholung": KW}).json()
    xlsx = c.get(f"/api/download/{t['ticket']}").content
    import msoffcrypto
    from openpyxl import load_workbook
    datei = msoffcrypto.OfficeFile(io.BytesIO(xlsx)); datei.load_key(password=KW); aus = io.BytesIO(); datei.decrypt(aus)
    wb = load_workbook(aus)
    pruef("B54 XLSX mit Kennwort: geschützt (OLE), ohne Klartext, mit Kennwort lesbar",
          xlsx[:4] == b"\xd0\xcf\x11\xe0" and b"Girokonto" not in xlsx and "Konten" in wb.sheetnames)
    r = c.post("/api/admin/import/vorschau", headers=A, files={"datei": ("x.xlsx", xlsx)})
    pruef("B55 Import der geschützten Datei ohne Kennwort -> 400", r.status_code == 400 and "Kennwort" in r.text, r.text)
    r = c.post("/api/admin/import/vorschau", headers=A, files={"datei": ("x.xlsx", xlsx)}, data={"kennwort": "falsch"})
    pruef("B56 Import mit falschem Kennwort -> 400", r.status_code == 400, r.text)
    r = c.post("/api/admin/import/vorschau", headers=A, files={"datei": ("x.xlsx", xlsx)}, data={"kennwort": KW})
    pruef("B57 Import mit Kennwort: Vorschau ohne Fehler und ohne Änderungen (Hin und zurück)",
          r.status_code == 200 and r.json()["fehler"] == 0 and r.json()["aenderungen"] == 0, r.text[:300])
    p = c.post("/api/admin/klartext-phrase?art=export", headers=A).json()
    t = c.post("/api/admin/download", headers=A, json={"art": "export_klartext", "token": p["token"], "phrase": p["phrase"]}).json()
    pruef("B58 Export unverschlüsselt mit Phrase (xlsx im Klartext)", c.get(f"/api/download/{t['ticket']}").content[:2] == b"PK")
    # Wiederherstellen aus der .fvdb (mit der Passphrase vom Zeitpunkt des Downloads)
    r = c.post("/api/admin/wiederherstellen/hochladen", headers=A, files={"datei": ("alt.fvdb", download_alt)})
    pruef("B59 Wiederherstellen .fvdb ohne Passphrase -> 422", r.status_code == 422 and "Passphrase" in r.text, r.text)
    r = c.post("/api/admin/wiederherstellen/hochladen", headers=A, files={"datei": ("alt.fvdb", download_alt)}, data={"geheimnis": "falsch falsch falsch"})
    pruef("B60 Wiederherstellen .fvdb mit falscher Passphrase -> 422", r.status_code == 422, r.text)
    r = c.post("/api/admin/wiederherstellen/hochladen", headers=A, files={"datei": ("alt.fvdb", download_alt)}, data={"geheimnis": PASS})
    pruef("B61 Wiederherstellen .fvdb mit der alten Passphrase: geprüft", r.status_code == 200 and r.json()["datei"]["konten"] == 5, r.text[:300])
    vorschau = r.json()
    staging = [f for f in dateien("Backups/.wiederherstellen")]
    pruef("B62 Zwischenablage der hochgeladenen Datei ist verschlüsselt", staging and all(not ist_klartext(f) for f in staging))
    r = c.post("/api/admin/wiederherstellen/ausfuehren", headers=A, json={"quelle": vorschau["quelle"], "token": vorschau["token"], "phrase": vorschau["phrase"]})
    pruef("B63 Wiederherstellen ausgeführt, Datenbank bleibt verschlüsselt und lesbar",
          r.status_code == 200 and not ist_klartext(DB) and c.get("/api/konten").status_code == 200, r.text[:300])
    r = c.post("/api/admin/wiederherstellen/hochladen", headers=A, files={"datei": ("klar.db", klar)})
    pruef("B64 Wiederherstellen einer unverschlüsselten Datei: angenommen und verschlüsselt abgelegt",
          r.status_code == 200 and all(not ist_klartext(f) for f in dateien("Backups/.wiederherstellen")), r.text[:200])
    bk = c.get("/api/admin/backups").json()[0]["dateiname"]
    r = c.post("/api/admin/wiederherstellen/backup", headers=A, json={"dateiname": bk})
    pruef("B65 Wiederherstellen aus einem verschlüsselten Backup: geprüft", r.status_code == 200 and r.json()["datei"]["konten"] >= 4, r.text[:200])
    r = c.post("/api/admin/wiederherstellen/hochladen", headers=A, files={"datei": ("alt.fvdb", download_alt)}, data={"geheimnis": WH})
    pruef("B66 .fvdb auch mit dem Wiederherstellungsschlüssel", r.status_code == 200, r.text[:200])

# Wiederherstellungsschlüssel beim Entsperren, alte Passphrase ungültig
with TestClient(app, client=INGRESS) as c:
    r = c.post("/api/schutz/entsperren", json={"geheimnis": PASS})
    pruef("B67 Nach dem Ändern: alte Passphrase abgewiesen", r.status_code == 401, r.text)
    r = c.post("/api/schutz/entsperren", json={"geheimnis": WH.replace("-", ""), "neue_passphrase": PASS, "wiederholung": PASS})
    pruef("B68 Passphrase vergessen: Wiederherstellungsschlüssel ohne Trennzeichen plus neue Passphrase", r.status_code == 200, r.text[:200])
with TestClient(app, client=INGRESS) as c:
    pruef("B69 Danach gilt die neue Passphrase", c.post("/api/schutz/entsperren", json={"geheimnis": PASS}).status_code == 200)
    ALLE_GEHEIMNISSE = [PASS, PASS2, WH, WH.replace("-", ""), KW, SCHLUESSEL.hex(), SCHLUESSEL.hex().upper()]
    roh = [SCHLUESSEL]
    funde = []
    for f in dateien("."):
        inhalt = open(f, "rb").read()
        for g in ALLE_GEHEIMNISSE:
            if g.encode() in inhalt:
                funde.append((os.path.relpath(f, ziel), g[:6]))
        if any(r in inhalt for r in roh):
            funde.append((os.path.relpath(f, ziel), "Datenschlüssel roh"))
    pruef("B70 Kein Schlüssel, keine Passphrase, kein Kennwort in irgendeiner Datei", not funde, funde)
    im_protokoll = [g[:6] for g in ALLE_GEHEIMNISSE if any(g in z for z in PROTOKOLL)]
    pruef("B71 Kein Schlüssel, keine Passphrase, kein Kennwort im Protokoll", not im_protokoll, im_protokoll)

# ═══ C. Sperre ═══

with TestClient(app, client=INGRESS) as c:
    ha = TestClient(app, client=HA)
    fremd = TestClient(app, client=FREMD)
    c.post("/api/schutz/entsperren", json={"geheimnis": PASS})
    eingabe = {"einstellungen": {"modus": "je_benutzer", "grenze": 10}, "art": "pin", "code": "135790", "wiederholung": "135790"}
    r = c.post("/api/schutz/sperre/vorbereiten", headers=B, json=eingabe)
    pruef("C1 Sperre einschalten ohne Adminrecht -> 403", r.status_code == 403, r.text)
    os.environ["FINANZAPP_HERKUNFT_PRUEFEN"] = "protokoll"
    r = c.post("/api/schutz/sperre/vorbereiten", headers=A, json=eingabe)
    os.environ["FINANZAPP_HERKUNFT_PRUEFEN"] = "sperren"
    pruef("C2 Sperre nur bei herkunft_pruefen = sperren (sonst 409)", r.status_code == 409 and "herkunft_pruefen" in r.text, r.text)
    r = c.post("/api/schutz/sperre/vorbereiten", headers=OHNE_GRUPPEN, json=eingabe)
    pruef("C3 Ohne X-Remote-User-Groups kein Adminrecht -> 403", r.status_code == 403, r.text)
    for name, e, wort in [("PIN 5 Ziffern", {"art": "pin", "code": "12345", "wiederholung": "12345"}, "6"),
                          ("PIN mit Buchstaben", {"art": "pin", "code": "12345a", "wiederholung": "12345a"}, "Ziffern"),
                          ("Passwort 7 Zeichen", {"art": "passwort", "code": "abcdefg", "wiederholung": "abcdefg"}, "8"),
                          ("Muster 4 Punkte", {"art": "muster", "code": "1-2-3-6", "wiederholung": "1-2-3-6"}, "5"),
                          ("Muster mit doppeltem Punkt", {"art": "muster", "code": "1-2-3-2-5", "wiederholung": "1-2-3-2-5"}, "höchstens"),
                          ("Wiederholung abweichend", {"art": "pin", "code": "135790", "wiederholung": "135791"}, "überein"),
                          ("Grenze 4", {**eingabe, "einstellungen": {"grenze": 4}}, "5 bis 20"),
                          ("Mindestlänge PIN unter 6", {**eingabe, "einstellungen": {"mindest": {"pin": 4}}}, "mindestens")]:
        r = c.post("/api/schutz/sperre/vorbereiten", headers=A, json={**eingabe, **e})
        pruef(f"C4 Abgewiesen: {name}", r.status_code == 422 and wort in r.text, r.text)
    r = c.post("/api/schutz/sperre/vorbereiten", headers=A, json={**eingabe, "einstellungen": {"modus": "je_benutzer", "grenze": 10, "mindest": {"pin": 8}}})
    pruef("C5 Erhöhte Mindestlänge PIN 8 greift", r.status_code == 422 and "8" in r.text, r.text)
    v = c.post("/api/schutz/sperre/vorbereiten", headers=A, json=eingabe).json()
    WHS = v["wiederherstellungsschluessel"]
    r = c.post("/api/schutz/sperre/einschalten", headers=A, json={"kennung": v["kennung"], "getippt": "AAAA"})
    pruef("C6 Einschalten mit falsch abgetipptem Schlüssel -> 422, Sperre aus", r.status_code == 422 and not schutz.aktiv(), r.text)
    r = c.post("/api/schutz/sperre/einschalten", headers=A, json={"kennung": v["kennung"], "getippt": WHS})
    TA = r.json().get("sitzung")
    pruef("C7 Sperre eingeschaltet, Sitzung für den Admin", r.status_code == 200 and TA and schutz.aktiv(), r.text)
    js = json.load(open(os.path.join(ziel, "schutz.json"), encoding="utf-8"))
    pruef("C8 schutz.json: Code nur als Argon2id-Hash, Wiederherstellungsschlüssel nur als Prüfsumme",
          js["sperre"]["benutzer"]["id-ralf"]["code"]["hash"].startswith("$argon2id$")
          and "135790" not in json.dumps(js) and WHS not in json.dumps(js) and WHS.replace("-", "") not in json.dumps(js))

    # C9: alle Endpunkte ohne Code abgewiesen (im Server, nicht nur in der Oberfläche)
    frei = {"/", "/schnellbuchung", "/api/hilfe", "/api/hilfe/pdf", "/api/feiertage", "/api/schutz/status",
            "/api/schutz/anmelden", "/api/schutz/erstcode", "/api/schutz/abmelden", "/api/schutz/wiederherstellen",
            "/api/schutz/entsperren", "/api/schutz/freigabe-passphrase", "/api/erfassen/stammdaten",
            "/api/erfassen/buchung", "/api/erfassen/vorschlag", "/api/siri/buchung", "/api/hilfe/bilder/{name}",
            "/api/download/{ticket}"}
    routen = [(m, r.path) for r in app.routes if hasattr(r, "methods") and r.path not in frei
              and not r.path.startswith(("/assets", "/docs", "/openapi", "/redoc")) for m in r.methods if m != "HEAD"]
    falsch = []
    for methode, pfad in routen:
        url = pfad.replace("{", "").replace("}", "")
        url = "/".join("1" if t in ("person_id", "konto_id", "kategorie_id", "buchung_id", "vorlage_id", "darlehen_id",
                                     "budget_id", "regel_id", "av_id", "eintrag_id", "benutzer_id") else t for t in url.split("/"))
        r = c.request(methode, url, headers=A, json={})
        if r.status_code != 401 or r.json().get("schutz") != "code":
            falsch.append((methode, pfad, r.status_code))
    pruef(f"C9 Alle {len(routen)} geschützten Endpunkte ohne Code -> 401", len(routen) > 100 and not falsch, falsch[:8])
    falsch = [(m, p) for m, p in routen[:40] if c.request(m, p.replace("{", "").replace("}", ""), headers=B, json={}).status_code != 403]
    pruef("C10 Nicht freigegebener Benutzer -> 403 (Stichprobe 40 Endpunkte)", not falsch, falsch[:5])
    pruef("C11 Ohne Benutzer-Header -> 403", c.get("/api/konten").status_code == 403)
    pruef("C12 Mit Sitzung erlaubt", c.get("/api/konten", headers=mit(A, TA)).status_code == 200)
    pruef("C13 Fremde Herkunft mit gefälschten Headern bleibt gesperrt (Herkunftsprüfung)",
          fremd.get("/api/konten", headers=mit(A, TA)).status_code == 403
          and "Home Assistant" in fremd.get("/api/konten", headers=mit(A, TA)).text)
    pruef("C14 Sitzung gilt nur für ihren Benutzer", c.get("/api/konten", headers=mit(B, TA)).status_code == 403)

    # Freigabeliste und erster Code
    r = c.get("/api/schutz/status", headers=B)  # Anna öffnet einmal
    r = c.post("/api/schutz/sperre/benutzer", headers=mit(A, TA), json={"id": "id-anna"})
    pruef("C15 Admin gibt Anna frei", r.status_code == 200, r.text)
    st = c.get("/api/schutz/status", headers=B).json()["sperre"]
    pruef("C16 Anna: freigegeben, noch kein Code", st["freigegeben"] and not st["code_gesetzt"], st)
    pruef("C17 Anna ohne Code -> 401", c.get("/api/konten", headers=B).status_code == 401)
    r = c.post("/api/schutz/erstcode", headers=B, json={"art": "muster", "code": "1-5-9-6-3", "wiederholung": "1-5-9-6-3"})
    TB = r.json().get("sitzung")
    pruef("C18 Anna legt ihr Muster fest und ist angemeldet", r.status_code == 200 and c.get("/api/konten", headers=mit(B, TB)).status_code == 200, r.text)
    r = c.post("/api/schutz/erstcode", headers=B, json={"art": "pin", "code": "246802", "wiederholung": "246802"})
    pruef("C19 Erster Code nur einmal -> 409", r.status_code == 409, r.text)
    r = c.put("/api/schutz/sperre", headers=mit(B, TB), json={"auto_minuten": 10})
    pruef("C20 Nicht-Admin darf Einstellungen nicht ändern -> 403", r.status_code == 403, r.text)
    r = c.put("/api/schutz/sperre", headers=A, json={"auto_minuten": 10})
    pruef("C21 Admin ohne Sitzung -> 401", r.status_code == 401, r.text)

    # Fehlversuche mit eingefrorener Uhr (Grenze 10)
    def anmelden(code):
        return c.post("/api/schutz/anmelden", headers=B, json={"code": code})
    codes = [anmelden("1-2-3-4-5").status_code for _ in range(4)]
    r5 = anmelden("1-2-3-4-5")
    pruef("C22 Fehlversuche 1 bis 4 ohne Wartezeit, der 5. löst 1 Minute aus",
          codes == [401] * 4 and r5.status_code == 401 and "1 Minute" in r5.text, (codes, r5.text))
    r = anmelden("1-5-9-6-3")
    pruef("C23 Während der Wartezeit auch der richtige Code -> 429 (zählt nicht)", r.status_code == 429, r.text)
    UHR[0] += 59
    pruef("C24 Nach 59 Sekunden noch gesperrt", anmelden("1-5-9-6-3").status_code == 429)
    erwartet = [2, 4, 8, 16]
    gemessen = []
    for minuten in erwartet:
        UHR[0] += 2 + (minuten // 2) * 60
        r = anmelden("9-8-7-6-5")
        gemessen.append(schutz.fehlversuche("id-anna")["warten"])
    pruef("C25 Wartezeit verdoppelt sich: 2, 4, 8, 16 Minuten", [round(w / 60) for w in gemessen] == erwartet, gemessen)
    UHR[0] += 16 * 60 + 1
    r = anmelden("9-8-7-6-5")
    pruef("C26 Nach dem 10. Fehlversuch: gesperrt bis Freigabe (423)", r.status_code == 423 and schutz.fehlversuche("id-anna")["dauerhaft"], r.text)
    UHR[0] += 7200
    r = anmelden("1-5-9-6-3")
    pruef("C27 Auch nach 2 Stunden und mit richtigem Code gesperrt", r.status_code == 423, r.text)
    r = c.post("/api/schutz/sperre/benutzer/id-anna/entsperren", headers=mit(B, TB))
    pruef("C28 Selbst freigeben geht nicht", r.status_code in (401, 422), r.text)
    TA = c.post("/api/schutz/anmelden", headers=A, json={"code": "135790"}).json()["sitzung"]
    r = c.post("/api/schutz/sperre/benutzer/id-anna/entsperren", headers=mit(A, TA))
    r2 = anmelden("1-5-9-6-3")
    pruef("C29 Freigabe durch anderen Benutzer, danach richtiger Code ok", r.status_code == 200 and r2.status_code == 200, (r.text, r2.text))
    # Wiederherstellungsschlüssel der Sperre
    for _ in range(10):
        UHR[0] += 3601
        anmelden("2-2-2-2-2")
    pruef("C30 Wieder gesperrt bis Freigabe", schutz.fehlversuche("id-anna")["dauerhaft"])
    r = c.post("/api/schutz/wiederherstellen", headers=B, json={"schluessel": "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567"})
    pruef("C31 Falscher Wiederherstellungsschlüssel der Sperre -> 401", r.status_code == 401, r.text)
    r = c.post("/api/schutz/wiederherstellen", headers=B, json={"schluessel": WHS.lower()})
    pruef("C32 Wiederherstellungsschlüssel der Sperre hebt die Sperre auf",
          r.status_code == 200 and not schutz.fehlversuche("id-anna")["dauerhaft"], r.text)
    # Freigabe mit der Passphrase
    for _ in range(10):
        UHR[0] += 3601
        anmelden("2-2-2-2-2")
    r = c.post("/api/schutz/freigabe-passphrase", headers=B, json={"passphrase": "falsch falsch falsch falsch"})
    r2 = c.post("/api/schutz/freigabe-passphrase", headers=B, json={"passphrase": PASS})
    pruef("C33 Freigabe mit der Passphrase der Verschlüsselung (falsch 401, richtig 200)",
          r.status_code == 401 and r2.status_code == 200 and not schutz.fehlversuche("id-anna")["dauerhaft"], (r.text, r2.text))
    # Wartezeit höchstens 1 Stunde, ohne Limit
    TA = c.post("/api/schutz/anmelden", headers=A, json={"code": "135790"}).json()["sitzung"]
    r = c.put("/api/schutz/sperre", headers=mit(A, TA), json={"grenze": 0})
    for _ in range(12):
        UHR[0] += 3601
        anmelden("2-2-2-2-2")
    st = schutz.fehlversuche("id-anna")
    pruef("C34 Ohne Limit: nach 12 Fehlversuchen keine Sperre bis Freigabe, Wartezeit gedeckelt auf 1 Stunde",
          r.status_code == 200 and not st["dauerhaft"] and st["warten"] == 3600, (r.text, st))
    UHR[0] += 3601
    TB = anmelden("1-5-9-6-3").json()["sitzung"]
    # Sitzung verfällt nach Untätigkeit (5 Minuten)
    TA = c.post("/api/schutz/anmelden", headers=A, json={"code": "135790"}).json()["sitzung"]
    UHR[0] += 299
    ok1 = c.get("/api/konten", headers=mit(A, TA)).status_code
    UHR[0] += 299
    ok2 = c.get("/api/konten", headers=mit(A, TA)).status_code
    UHR[0] += 301
    weg = c.get("/api/konten", headers=mit(A, TA)).status_code
    pruef("C35 Sitzung: Anfragen verlängern, nach 5 Minuten Untätigkeit 401", (ok1, ok2, weg) == (200, 200, 401), (ok1, ok2, weg))
    TA = c.post("/api/schutz/anmelden", headers=A, json={"code": "135790"}).json()["sitzung"]
    c.post("/api/schutz/abmelden", headers=mit(A, TA))
    pruef("C36 Abmelden beendet die Sitzung", c.get("/api/konten", headers=mit(A, TA)).status_code == 401)
    # Schnellbuchung „ohne Code nur erfassen“
    sd = c.get("/api/erfassen/stammdaten", headers=B)
    giro = next(k["id"] for k in sd.json()["konten"] if k["name"] == "Girokonto")
    lm = next(k["id"] for k in sd.json()["kategorien"] if k["name"] == "Lebensmittel/Verpflegung")
    r = c.post("/api/erfassen/buchung", headers=B, json={"konto_id": giro, "datum": "2026-10-28", "betrag": 3, "kategorie_id": lm,
                                                          "beschreibung": "Erfasst ohne Code"})
    pruef("C37 Nur erfassen ohne Code: Stammdaten und Buchung erlaubt, Antwort ohne Doppelbuchungs-Hinweis",
          sd.status_code == 200 and r.status_code == 200 and not r.json()["vorgemerkt"] and "duplikat" not in r.json(), r.text)
    pruef("C38 Nur erfassen ohne Code: Buchungsliste bleibt gesperrt", c.get("/api/buchungen", headers=B).status_code == 401)
    pruef("C39 Nicht freigegebener Benutzer darf auch nicht erfassen", c.get("/api/erfassen/stammdaten", headers=C).status_code == 403)
    TA = c.post("/api/schutz/anmelden", headers=A, json={"code": "135790"}).json()["sitzung"]
    c.put("/api/schutz/sperre", headers=mit(A, TA), json={"schnellbuchung": "mit_code"})
    pruef("C40 Schnellbuchung „immer mit Code“: erfassen ohne Code -> 401",
          c.post("/api/erfassen/buchung", headers=B, json={"konto_id": giro, "datum": "2026-10-28", "betrag": 3, "kategorie_id": lm}).status_code == 401)
    c.put("/api/schutz/sperre", headers=mit(A, TA), json={"schnellbuchung": "nur_erfassen"})
    # Siri bei Sperre
    r = c.post("/api/siri/buchung", json={"betrag": 1, "konto": "Girokonto", "kategorie": "Lebensmittel/Verpflegung"})
    pruef("C41 Siri über Ingress bei Sperre -> 403 (nur von Home Assistant)", r.status_code == 403, r.text)
    r = ha.post("/api/siri/buchung", json={"betrag": 4.2, "konto": "Girokonto", "kategorie": "Lebensmittel/Verpflegung"})
    pruef("C42 Siri von Home Assistant: gebucht, Antwort nur mit Betrag",
          r.status_code == 200 and r.json()["meldung"] == "4.20 Euro gebucht." and "Girokonto" not in r.text and "Lebensmittel" not in r.text, r.text)
    r = ha.post("/api/siri/buchung", json={"betrag": 1, "konto": "Giro", "kategorie": "Lebensmittel/Verpflegung"})
    pruef("C43 Siri mehrdeutig bei Sperre: Fehler ohne gespeicherte Namen", r.status_code == 400 and "Partnerin" not in r.text, r.text)
    # Code ändern
    r = c.post("/api/schutz/sperre/code", headers=mit(B, TB), json={"alter_code": "1-1-1", "art": "pin", "code": "864209", "wiederholung": "864209"})
    pruef("C44 Code ändern mit falschem bisherigen Code -> 401", r.status_code == 401, r.text)
    TB = anmelden("1-5-9-6-3").json()["sitzung"]
    r = c.post("/api/schutz/sperre/code", headers=mit(B, TB), json={"alter_code": "1-5-9-6-3", "art": "pin", "code": "864209", "wiederholung": "864209"})
    pruef("C45 Code ändern auf PIN, danach Anmeldung mit PIN", r.status_code == 200 and anmelden("864209").status_code == 200, r.text)
    # Uebersicht ohne Hashes
    u = c.get("/api/schutz/sperre", headers=mit(A, TA)).json()
    pruef("C46 Übersicht der Administration ohne Hashes", "$argon2" not in json.dumps(u) and len(u["benutzer"]) == 2 and u["verwalten"])

# Neustart: Sitzungen weg, Sperre und Verschlüsselung zusammen
with TestClient(app, client=INGRESS) as c:
    pruef("D1 Nach Neustart: alte Sitzung ungültig", c.get("/api/konten", headers=mit(A, TA)).status_code in (401, 423))
    st = c.get("/api/schutz/status", headers=A).json()
    pruef("D2 Status: Sperre an, Datenbank zu", st["sperre"]["aktiv"] and st["verschluesselung"]["gesperrt"], st)
    r = c.post("/api/schutz/entsperren", headers=C, json={"geheimnis": PASS})
    pruef("D3 Nicht freigegebener Benutzer darf nicht entsperren -> 403", r.status_code == 403 and tresor.gesperrt(), r.text)
    sd = c.get("/api/erfassen/stammdaten", headers=B)
    pruef("D4 Zu und gesperrt: Schnellbuchung erfasst aus dem Auszug", sd.status_code == 200 and sd.json()["vorgemerkt"])
    r = c.post("/api/schutz/entsperren", headers=B, json={"geheimnis": PASS})
    TB = r.json().get("sitzung")
    pruef("D5 Passphrase entsperrt Datenbank und Sperre zugleich", r.status_code == 200 and TB
          and c.get("/api/konten", headers=mit(B, TB)).status_code == 200, r.text[:200])
    TA = c.post("/api/schutz/anmelden", headers=A, json={"code": "135790"}).json()["sitzung"]
    r = c.post("/api/schutz/sperre/ausschalten", headers=mit(A, TA), json={"code": "000000"})
    pruef("D6 Sperre ausschalten mit falschem Code -> 401", r.status_code == 401, r.text)
    r = c.post("/api/schutz/sperre/ausschalten", headers=mit(A, TA), json={"code": "135790"})
    pruef("D7 Sperre ausgeschaltet, Zugriff wieder ohne Code", r.status_code == 200 and c.get("/api/konten").status_code == 200, r.text)
    # Verschlüsselung ausschalten
    zahlen_vorher = {k["name"]: k["saldo"] for k in c.get("/api/konten").json()}
    p = c.post("/api/schutz/verschluesselung/ausschalten-phrase", headers=A).json()
    r = c.post("/api/schutz/verschluesselung/ausschalten", headers=A, json={"geheimnis": PASS, "token": p["token"], "phrase": "falsch"})
    pruef("D8 Ausschalten mit falscher Phrase -> 422", r.status_code == 422 and not ist_klartext(DB), r.text)
    p = c.post("/api/schutz/verschluesselung/ausschalten-phrase", headers=A).json()
    r = c.post("/api/schutz/verschluesselung/ausschalten", headers=A, json={"geheimnis": "falsch falsch falsch falsch", "token": p["token"], "phrase": p["phrase"]})
    pruef("D9 Ausschalten mit falscher Passphrase -> 401", r.status_code == 401 and not ist_klartext(DB), r.text)
    UHR[0] += 120
    p = c.post("/api/schutz/verschluesselung/ausschalten-phrase", headers=A).json()
    r = c.post("/api/schutz/verschluesselung/ausschalten", headers=A, json={"geheimnis": PASS, "token": p["token"], "phrase": p["phrase"]})
    pruef("D10 Ausschalten: Datenbank und Backups unverschlüsselt, Schlüssel, Auszug und Stapel entfernt",
          r.status_code == 200 and ist_klartext(DB) and all(ist_klartext(f) for f in dateien("Backups") if f.endswith(".db"))
          and "verschluesselung" not in json.load(open(os.path.join(ziel, "schutz.json")))
          and not os.path.exists(os.path.join(ziel, "auszug.json")), r.text[:300])
    pruef("D11 Daten nach dem Ausschalten unverändert", {k["name"]: k["saldo"] for k in c.get("/api/konten").json()} == zahlen_vorher)
with TestClient(app, client=INGRESS) as c:
    st = c.get("/api/schutz/status").json()
    pruef("D12 Nach Neustart offen, kein Schutz aktiv", not st["sperre"]["aktiv"] and not st["verschluesselung"]["aktiv"]
          and c.get("/api/konten").status_code == 200, st)

# Befund X: Supervisor-Version über die Schnittstelle lesen (Antwort nachgestellt)
from unittest import mock
del os.environ["FINANZAPP_SUPERVISOR_VERSION"]
schutz._SUPERVISOR.update(version=None, geprueft=0.0)
pruef("X1 Ohne SUPERVISOR_TOKEN: Version unbekannt, Header nicht vertrauenswürdig",
      schutz.supervisor_version() is None and not schutz.gruppen_vertrauenswuerdig())
class Antwort(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass
gesehen = []
def abfrage(anfrage, timeout):
    gesehen.append((anfrage.full_url, anfrage.get_header("Authorization")))
    return Antwort(json.dumps({"result": "ok", "data": {"version": "2026.11.0"}}).encode())
os.environ["SUPERVISOR_TOKEN"] = "testtoken"
schutz._SUPERVISOR.update(version=None, geprueft=0.0)
with mock.patch("urllib.request.urlopen", abfrage):
    v = schutz.supervisor_version()
pruef("X2 Version über GET http://supervisor/supervisor/info mit Token gelesen, 2026.11.0 gilt als vertrauenswürdig",
      v == "2026.11.0" and gesehen == [("http://supervisor/supervisor/info", "Bearer testtoken")] and schutz.gruppen_vertrauenswuerdig(), gesehen)
schutz._SUPERVISOR.update(version=None, geprueft=0.0)
with mock.patch("urllib.request.urlopen", lambda a, timeout: Antwort(json.dumps({"data": {"version": "2026.10.4"}}).encode())):
    pruef("X3 Supervisor 2026.10.4: nicht vertrauenswürdig", not schutz.gruppen_vertrauenswuerdig())
schutz._SUPERVISOR.update(version=None, geprueft=0.0)
def kaputt(a, timeout): raise OSError("nicht erreichbar")
with mock.patch("urllib.request.urlopen", kaputt):
    pruef("X4 Supervisor nicht erreichbar: nicht vertrauenswürdig", not schutz.gruppen_vertrauenswuerdig())
del os.environ["SUPERVISOR_TOKEN"]

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

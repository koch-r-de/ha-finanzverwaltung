"""Fachliche Tests 2.6.2: Befund Q (Herkunftsprüfung im internen Netz) und
Hilfe-Unterkapitel „Feiertage und Buchungstermine“.
Aufruf: python3 v262_test.py <code> <quelle> <ziel>"""
import os, sys, shutil, logging
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

protokoll = []
class Sammler(logging.Handler):
    def emit(self, r): protokoll.append(r.getMessage())
logging.getLogger("app.zugriff").addHandler(Sammler()); logging.getLogger("app.zugriff").setLevel(logging.INFO)

def client(ip):
    return TestClient(app, client=(ip, 40000))

INGRESS, KERN, FREMD = "172.30.32.2", "172.30.32.1", "172.30.33.5"

# Modus aus (Standard ohne Umgebungsvariable, Desktop und Tests)
os.environ.pop("FINANZAPP_HERKUNFT_PRUEFEN", None)
with client(FREMD) as c:
    pruef("Modus aus: fremde Herkunft erlaubt, nichts protokolliert", c.get("/api/konten").status_code == 200 and not protokoll)

# Modus protokoll: nichts sperren, jede neue Adresse einmal mitschreiben
os.environ["FINANZAPP_HERKUNFT_PRUEFEN"] = "protokoll"
with client(FREMD) as c:
    a = c.get("/api/konten").status_code; c.get("/api/kategorien")
with client(KERN) as c:
    b = c.get("/api/konten").status_code
pruef("Modus protokoll: fremde Herkunft weiter erlaubt", a == 200 and b == 200)
pruef("Modus protokoll: je Adresse genau eine Zeile, mit „wäre gesperrt“ bzw. „erlaubt“",
      sum(FREMD in z for z in protokoll) == 1 and any(FREMD in z and "wäre gesperrt" in z for z in protokoll)
      and any(KERN in z and "erlaubt" in z for z in protokoll), protokoll)

# Modus sperren
os.environ["FINANZAPP_HERKUNFT_PRUEFEN"] = "sperren"
with client(INGRESS) as c:
    pruef("Modus sperren: Ingress (172.30.32.2) darf Oberfläche und API",
          c.get("/").status_code == 200 and c.get("/api/konten").status_code == 200)
with client(INGRESS) as c:
    KONTO = c.get("/api/konten").json()[0]["name"]
SIRI = lambda text: {"betrag": 1, "kategorie": "Lebensmittel/Verpflegung", "konto": KONTO, "beschreibung": text}
with client(KERN) as c:
    s = c.post("/api/siri/buchung", json=SIRI("Siri über HA"))
    pruef("Modus sperren: Home Assistant selbst (172.30.32.1) darf Siri buchen", s.status_code == 200, s.text[:200])
with client("127.0.0.1") as c:
    pruef("Modus sperren: lokaler Aufruf erlaubt", c.get("/api/start-status").status_code == 200)
with client(FREMD) as c:
    r1, r2 = c.get("/api/konten"), c.post("/api/siri/buchung", json=SIRI("Gesperrt"))
    r3 = c.get("/schnellbuchung")
pruef("Modus sperren: anderes Add-on bekommt 403 auf API, Schreibzugriff und Seiten",
      r1.status_code == 403 and r2.status_code == 403 and r3.status_code == 403
      and r1.json()["detail"] == "Zugriff nur über Home Assistant.")
with client(INGRESS) as c:
    texte = [b["beschreibung"] for b in c.get("/api/buchungen").json()]
    pruef("Modus sperren: gesperrte Buchung nicht angelegt, die über Home Assistant schon",
          "Gesperrt" not in texte and "Siri über HA" in texte)
os.environ["FINANZAPP_HERKUNFT_PRUEFEN"] = "unbekannt"
with client(FREMD) as c:
    pruef("Unbekannter Modus wirkt wie aus (keine Sperre ohne gültige Option)", c.get("/api/konten").status_code == 200)
os.environ.pop("FINANZAPP_HERKUNFT_PRUEFEN", None)

# Hilfe: eigenes Unterkapitel zur Feiertagslogik
with TestClient(app) as c:
    h = c.get("/api/hilfe").json()
    k = {x["anker"]: x for x in h["kapitel"]}
    t = k.get("admin.feiertage-termine", {}).get("text", "")
    pruef("Hilfe: Unterkapitel „Feiertage und Buchungstermine“ mit Bankfeiertagen und Beispiel",
          "Bankfeiertage" in t and "Fronleichnam" in t and "Werktag davor" in t)
    pruef("Hilfe: Kapitel „Feiertage“ verweist darauf, Doppeltes entfernt",
          'href="#admin.feiertage-termine"' in k["admin.feiertage"]["html"]
          and "sperren nichts" not in k["admin.feiertage"]["text"])

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

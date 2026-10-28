"""Messung 3.0: Dauer von Einschalten, Entsperren und Abfragen mit und ohne
Verschlüsselung. Keine Testreihe, nur Zahlen für DOCS.md.

Aufruf: python3 tests/v30_messung.py <code> <quelle> <ziel> [buchungen]
Ergänzt die Datenbank um erfundene Buchungen (Vorgabe 20 000), misst jede
Abfrage fünfmal und nennt den Median.
"""
import os, random, shutil, sqlite3, statistics, sys, time
code, quelle, ziel = sys.argv[1:4]
anzahl = int(sys.argv[4]) if len(sys.argv) > 4 else 20000
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
os.environ["FINANZAPP_HERKUNFT_PRUEFEN"] = "aus"
os.environ["FINANZAPP_SUPERVISOR_VERSION"] = "2026.10.5"
c = sqlite3.connect(os.path.join(ziel, "finanzdaten.db"))
konten = [r[0] for r in c.execute("SELECT id FROM konten")]
kats = [r[0] for r in c.execute("SELECT id FROM kategorien WHERE typ = 'ausgabe'")]
zufall = random.Random(1)
c.executemany("INSERT INTO buchungen (konto_id, datum, betrag, kategorie_id, typ, beschreibung) VALUES (?, ?, ?, ?, 'Ist', ?)",
              [(zufall.choice(konten), f"{zufall.randint(2016, 2026)}-{zufall.randint(1, 12):02d}-{zufall.randint(1, 28):02d}",
                -round(zufall.uniform(1, 200), 2), zufall.choice(kats), f"Messbuchung {i}") for i in range(anzahl)])
c.commit(); c.close()
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from app.main import app

A = {"X-Remote-User-Id": "m", "X-Remote-User-Name": "m", "X-Remote-User-Groups": "system-admin"}
PASS = "Messung mit einer langen Passphrase"
ABFRAGEN = ["/api/konten", "/api/buchungen?von=2026-01-01&bis=2026-12-31",
            "/api/auswertungen/saldo-verlauf?von=2025-11-01&bis=2027-10-31",
            "/api/auswertungen/cashflow?von=2016-01-01&bis=2026-12-31", "/api/auswertungen/jahresuebersicht",
            "/api/budgets"]


def messen(cl, pfad):
    zeiten = []
    for _ in range(5):
        t = time.perf_counter(); r = cl.get(pfad); zeiten.append(time.perf_counter() - t)
        assert r.status_code == 200, (pfad, r.status_code)
    return statistics.median(zeiten) * 1000


with TestClient(app) as cl:
    ohne = {p: messen(cl, p) for p in ABFRAGEN}
    cl.get("/api/admin/datenbank-herunterladen")
    t = time.perf_counter()
    v = cl.post("/api/schutz/verschluesselung/vorbereiten", headers=A, json={"passphrase": PASS, "wiederholung": PASS}).json()
    vorbereiten = time.perf_counter() - t
    t = time.perf_counter()
    r = cl.post("/api/schutz/verschluesselung/einschalten", headers=A, json={"kennung": v["kennung"],
                "getippt": v["wiederherstellungsschluessel"], "token": v["token"], "phrase": v["phrase"]})
    einschalten = time.perf_counter() - t
    assert r.status_code == 200, r.text
with TestClient(app) as cl:
    t = time.perf_counter()
    r = cl.post("/api/schutz/entsperren", json={"geheimnis": PASS})
    entsperren = time.perf_counter() - t
    assert r.status_code == 200, r.text
    mit = {p: messen(cl, p) for p in ABFRAGEN}
from app.core import tresor
t = time.perf_counter(); tresor.mit_passphrase_oeffnen(tresor.einstellungen()["datenschluessel_passphrase"], PASS)
argon = time.perf_counter() - t
groesse = os.path.getsize(os.path.join(ziel, "finanzdaten.db")) / 1e6

print(f"Datenbank: {anzahl} zusätzliche Buchungen, {groesse:.1f} MB")
print(f"Argon2id (t=3, 64 MiB, p=4) allein: {argon * 1000:.0f} ms")
print(f"Vorbereiten (Schlüssel erzeugen, einmal Argon2id): {vorbereiten * 1000:.0f} ms")
print(f"Einschalten (Backup, Kopien, Prüfungen, Tausch): {einschalten * 1000:.0f} ms")
print(f"Entsperren (Argon2id, Programmstart, Stapel, Auszug): {entsperren * 1000:.0f} ms")
print("Abfrage | ohne Verschlüsselung (ms) | mit (ms) | Faktor")
for p in ABFRAGEN:
    print(f"{p} | {ohne[p]:.1f} | {mit[p]:.1f} | {mit[p] / ohne[p]:.2f}")

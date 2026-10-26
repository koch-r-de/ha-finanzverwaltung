"""Oberflächentest 2.4 (Playwright, Server auf 8935): Datenbank wiederherstellen. Argument: Pfad einer 2.1-Datenbank."""
import os, sys, sqlite3
from playwright.sync_api import sync_playwright
BASIS = "http://localhost:8935/"
FREMD = sys.argv[1]
import os
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ausgabe", "bilder", "ui24") + "/"
os.makedirs(SHOTS, exist_ok=True)
ERG = []
def pruef(n, b, info=""):
    ERG.append((n, bool(b))); print(("OK   " if b else "FEHL ") + n + (f"  [{info}]" if info and not b else ""))

fremd_buchungen = sqlite3.connect(FREMD).execute("SELECT COUNT(*) FROM buchungen").fetchone()[0]
import tempfile
kaputt = tempfile.mktemp(suffix=".db")

open(kaputt, "wb").write(b"keine Datenbank")

with sync_playwright() as p:
    br = p.chromium.launch(env={**os.environ, "LANG": "de_DE.UTF-8", "LANGUAGE": "de"})
    page = br.new_context(timezone_id="Europe/Berlin", locale="de-DE", viewport={"width": 1400, "height": 1000}).new_page()
    fehler, dialoge = [], []
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.on("console", lambda m: fehler.append(m.text) if m.type == "error" else None)
    page.on("dialog", lambda d: (dialoge.append(d.message), d.dismiss()))
    page.goto(BASIS); page.wait_for_timeout(1500)
    page.click('.nav-eintrag[data-ziel="admin"]'); page.wait_for_timeout(1200)
    page.click('[data-admin-tab="system"]'); page.wait_for_timeout(600)
    page.evaluate("document.getElementById('admin-wiederherstellen-block').open = true;"
                  "document.getElementById('backup-jetzt').closest('details').open = true")
    vorher = page.evaluate("fetch('api/konten').then(r => r.json())")

    pruef("Block „Datenbank wiederherstellen“ mit Hinweistext und „?“",
          "Ersetzt alle Daten" in page.inner_text("#admin-wiederherstellen-block")
          and page.locator('#admin-wiederherstellen-block h2[data-hilfe="admin.wiederherstellen"]').count() == 1)
    pruef("„Prüfen“ erst nach Dateiauswahl aktiv", page.is_disabled("#wh-pruefen"))

    page.set_input_files("#wh-datei-feld", kaputt)
    page.click("#wh-pruefen"); page.wait_for_timeout(1200)
    pruef("Ungültige Datei: Meldung im Block, kein Fenster",
          "keine SQLite" in page.inner_text("#wh-status") and not page.is_visible("#wh-dialog"), page.inner_text("#wh-status"))

    page.set_input_files("#wh-datei-feld", FREMD)
    pruef("Dateiname wird angezeigt", page.inner_text("#wh-datei-name") == os.path.basename(FREMD))
    page.click("#wh-pruefen"); page.wait_for_timeout(1500)
    inhalt = page.inner_text("#wh-dialog")
    pruef("Fenster zeigt jetzt und Datei nebeneinander, Datum deutsch",
          page.is_visible("#wh-dialog") and "Aus der Datei".upper() in inhalt.upper() and str(fremd_buchungen) in inhalt
          and "Letzte Ist-Buchung" in inhalt and ".2026" in inhalt, inhalt[:300])
    pruef("„Jetzt wiederherstellen“ erst nach richtiger Phrase", page.is_disabled("#wh-ausfuehren"))
    page.screenshot(path=SHOTS + "dialog.png")
    phrase = page.inner_text("#wh-dialog .reset-phrase").strip()
    page.fill("#wh-phrase-eingabe", "falsch")
    pruef("Falsche Phrase: Knopf bleibt aus", page.is_disabled("#wh-ausfuehren"))
    page.fill("#wh-phrase-eingabe", phrase.upper())
    pruef("Phrase ohne Groß-/Kleinschreibung: Knopf aktiv", page.is_enabled("#wh-ausfuehren"))
    page.click("#wh-ausfuehren"); page.wait_for_timeout(2500)
    inhalt = page.inner_text("#wh-dialog")
    pruef("Erfolg: Backup des vorherigen Stands genannt, Anpassungen gelistet",
          "Wiederhergestellt" in inhalt and "vorherige Stand" in inhalt and "Darlehens-Zinsen" in inhalt, inhalt[:400])
    page.click("#wh-neu-laden"); page.wait_for_timeout(2000)
    # Seit 2.6: die eingespielte Datenbank ist von 2.1, also ohne Bundesland
    pruef("Nach Wiederherstellen einer alten Datenbank: Bundesland-Abfrage mit NRW vorbelegt",
          page.is_visible("#bundesland-dialog") and page.input_value("#bundesland-auswahl") == "NW")
    page.click('#form-bundesland button[type="submit"]'); page.wait_for_timeout(600)
    nachher = page.evaluate("fetch('api/konten').then(r => r.json())")
    pruef("Nach „Seite neu laden“: Daten der Datei aktiv",
          page.evaluate("fetch('api/admin/wiederherstellen/backup', {method:'POST'}).then(r => r.status)") == 422
          and len(nachher) >= 1 and page.evaluate("fetch('api/buchungen').then(r => r.json()).then(l => l.length)") >= 1)

    # Aus der Backup-Liste zurück
    page.click('.nav-eintrag[data-ziel="admin"]'); page.wait_for_timeout(1000)
    page.click('[data-admin-tab="system"]'); page.wait_for_timeout(600)
    page.evaluate("document.getElementById('backup-jetzt').closest('details').open = true")
    zeile = page.locator("#backups-tabelle tr", has_text="vor Wiederherstellung").first
    pruef("Backup-Liste: Eintrag „vor Wiederherstellung“ mit Knopf „Wiederherstellen“",
          zeile.count() == 1 and zeile.locator("[data-wh-backup]").count() == 1)
    zeile.locator("[data-wh-backup]").click(); page.wait_for_timeout(1200)
    pruef("Fenster für das Backup geöffnet", page.is_visible("#wh-dialog") and "vor" not in page.inner_text("#wh-dialog h2"))
    page.click("#wh-abbrechen"); page.wait_for_timeout(300)
    pruef("„Abbrechen“ schließt ohne Änderung", not page.is_visible("#wh-dialog"))
    zeile.locator("[data-wh-backup]").click(); page.wait_for_timeout(1200)
    page.fill("#wh-phrase-eingabe", page.inner_text("#wh-dialog .reset-phrase").strip())
    page.click("#wh-ausfuehren"); page.wait_for_timeout(2500)
    page.click("#wh-neu-laden"); page.wait_for_timeout(2000)
    zurueck = page.evaluate("fetch('api/konten').then(r => r.json())")
    pruef("Backup eingespielt: Salden wie vor dem ersten Wiederherstellen",
          {k["name"]: k["saldo"] for k in zurueck} == {k["name"]: k["saldo"] for k in vorher})
    echte = [f for f in fehler if "status of 422" not in f]  # 422 = gewollt abgelehnte Datei bzw. Testanfrage
    pruef("Keine Browser-Dialoge, keine JavaScript-Fehler", not dialoge and not echte, (dialoge, echte))

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

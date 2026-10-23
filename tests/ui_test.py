import re, sys
from datetime import date
from playwright.sync_api import sync_playwright
BASIS = "http://localhost:8935/"
import os
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ausgabe", "bilder", "ui") + "/"
import os; os.makedirs(SHOTS, exist_ok=True)
ERG = []
def pruef(n, b, info=""):
    ERG.append((n, bool(b))); print(("OK   " if b else "FEHL ") + n + (f"  [{info}]" if info and not b else ""))

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(timezone_id="Europe/Berlin", viewport={"width": 1400, "height": 1000})
    page = ctx.new_page()
    fehler = []
    page.on("console", lambda m: fehler.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.goto(BASIS); page.wait_for_timeout(1200)
    heute = page.evaluate("heuteISO()")
    pruef("heuteISO = lokales Datum", heute == date.today().isoformat(), heute)

    def gehe(ziel):
        page.click(f'.nav-eintrag[data-ziel="{ziel}"]'); page.wait_for_timeout(800)

    # Konten / Saldo-Korrektur
    gehe("konten")
    f = page.locator('#form-saldo-korrektur [name="datum"]')
    pruef("Saldo-Korrektur Datum vorbelegt", f.input_value() == heute, f.input_value())
    f.fill("2026-10-01")
    page.fill('#form-saldo-korrektur [name="saldo"]', "-315")
    page.select_option('#form-saldo-korrektur [name="konto_id"]', label="Girokonto Partnerin")
    page.click('#form-saldo-korrektur button[type="submit"]'); page.wait_for_timeout(800)
    pruef("Saldo-Korrektur Datum nach Absenden wieder heute", f.input_value() == heute, f.input_value())

    # Buchungen
    gehe("buchungen")
    pruef("Buchungsformular Datum vorbelegt", page.locator('#form-buchung [name="datum"]').input_value() == heute)
    page.select_option("#buchungen-filter-herkunft", "")
    page.wait_for_timeout(700)
    txt = page.locator("#buchungen-tabelle").inner_text()
    pruef("Buchungsliste: Übertragung Quelle → Ziel", "Girokonto → Tagesgeld" in txt)
    page.select_option("#buchungen-filter-herkunft", "anstehend"); page.wait_for_timeout(700)
    page.screenshot(path=SHOTS + "buchungen_anstehend.png", full_page=False)

    # Wiederkehrend
    gehe("wiederkehrend")
    opts = page.locator('#form-wiederkehrend [name="kategorie_id"] option').all_inner_texts()
    pruef("Kategorie Umbuchung im Vorlagen-Formular ausgeblendet", not any("Umbuchung" in o for o in opts))
    pruef("Zielkonto-Feld initial verborgen", not page.locator("#wk-zielkonto-feld").is_visible())
    page.select_option("#wk-art", "umbuchung")
    pruef("Umbuchung: Zielkonto/Sparziel sichtbar, Kategorie/Inflation verborgen",
          page.locator("#wk-zielkonto-feld").is_visible() and page.locator("#wk-sparziel-feld").is_visible()
          and not page.locator("#wk-kategorie-feld").is_visible() and not page.locator("#wk-inflation-feld").is_visible())
    page.select_option('#form-wiederkehrend [name="konto_id"]', label="Girokonto")
    page.select_option('#form-wiederkehrend [name="zielkonto_id"]', label="Girokonto")
    page.fill('#form-wiederkehrend [name="betrag"]', "75")
    page.fill('#form-wiederkehrend [name="beschreibung"]', "UI Umbuchung")
    page.fill('#form-wiederkehrend [name="startdatum"]', "2026-11-01")
    page.click("#wk-submit"); page.wait_for_timeout(500)
    pruef("Ziel = Quelle: Meldung", "unterscheiden" in page.locator("#wk-meldung").inner_text())
    page.select_option('#form-wiederkehrend [name="zielkonto_id"]', label="Tagesgeld")
    page.select_option('#form-wiederkehrend [name="sparziel_id"]', label="Urlaub 2027")
    page.click("#wk-submit"); page.wait_for_timeout(900)
    zeile = page.locator("#wiederkehrend-tabelle tr", has_text="UI Umbuchung")
    pruef("Tabelle: Umbuchung → Tagesgeld + Sparziel", "Umbuchung → Tagesgeld" in zeile.inner_text() and "Urlaub 2027" in zeile.inner_text(), zeile.inner_text())
    pruef("Formular nach Anlegen zurück auf Buchung", page.locator("#wk-art").input_value() == "buchung" and page.locator("#wk-kategorie-feld").is_visible())
    # Konto-Filter trifft Zielkonto
    page.select_option("#wk-filter-konto", label="Tagesgeld"); page.wait_for_timeout(500)
    pruef("Konto-Filter trifft Zielkonto", "UI Umbuchung" in page.locator("#wiederkehrend-tabelle").inner_text())
    page.select_option("#wk-filter-konto", ""); page.wait_for_timeout(400)
    # Ändern der Umbuchung lädt Art + Ziel
    zeile.locator("button", has_text="Ändern").click(); page.wait_for_timeout(500)
    pruef("Ändern lädt Umbuchung", page.locator("#wk-art").input_value() == "umbuchung"
          and page.locator('#form-wiederkehrend [name="zielkonto_id"] option:checked').inner_text() == "Tagesgeld")
    page.click("#wk-verwerfen"); page.wait_for_timeout(300)
    # Miete (Inflation) ändern und speichern -> Inflation bleibt, keine Dynamik
    miete = page.locator("#wiederkehrend-tabelle tr", has_text="Miete")
    miete.locator("button", has_text="Ändern").click(); page.wait_for_timeout(500)
    page.fill('#form-wiederkehrend [name="beschreibung"]', "Miete")
    page.click("#wk-submit"); page.wait_for_timeout(900)
    zt = page.locator("#wiederkehrend-tabelle tr", has_text="Miete").inner_text()
    pruef("Speichern über Formular: Infl. ja, Dynamik –", "\tja\t" in zt and "Wert fehlt" not in zt, zt)
    page.screenshot(path=SHOTS + "wiederkehrend.png", full_page=True)

    # Plan-Protokoll
    gehe("plan"); page.screenshot(path=SHOTS + "plan.png")

    # Auswertungen
    gehe("auswertungen"); page.wait_for_timeout(1500)
    page.screenshot(path=SHOTS + "auswertungen.png", full_page=True)
    gehe("budgets"); page.wait_for_timeout(1000)
    gehe("jahresuebersicht") if page.locator('.nav-eintrag[data-ziel="jahresuebersicht"]').count() else None

    # Admin -> Kategorien-Namensfeld
    gehe("admin"); page.wait_for_timeout(500)
    feld = page.locator('#form-kategorie input[name="name"]')
    attrs = feld.evaluate("f => [f.getAttribute('autocomplete'), f.hasAttribute('data-1p-ignore'), f.getAttribute('data-lpignore'), f.hasAttribute('data-bwignore'), f.getAttribute('data-form-type')]")
    pruef("Kategorie-Name: Passwort-Manager-Attribute", attrs == ["off", True, "true", True, "other"], attrs)
    pruef("Keine Konsolenfehler", not fehler, fehler)
    ctx.close()

    # Uhrzeit 00:30 deutscher Zeit (UTC noch Vortag)
    ctx = br.new_context(timezone_id="Europe/Berlin")
    page = ctx.new_page()
    page.clock.install(time="2026-10-14T00:30:00+02:00")
    page.goto(BASIS); page.wait_for_timeout(1000)
    pruef("00:30 Uhr: heuteISO lokal (14.10.)", page.evaluate("heuteISO()") == "2026-10-14", page.evaluate("heuteISO()"))
    pruef("00:30 Uhr: alter Weg hätte Vortag geliefert", page.evaluate("new Date().toISOString().slice(0,10)") == "2026-10-13")
    page.goto(BASIS + "schnellbuchung"); page.wait_for_timeout(1000)
    pruef("Schnellbuchung 00:30 Uhr: Datum lokal", page.locator("#sb-datum-feld").input_value() == "2026-10-14",
          page.locator("#sb-datum-feld").input_value())
    ctx.close(); br.close()
fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

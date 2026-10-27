"""Oberflächentest 2.6 (Playwright, Server auf 8935): Feiertagskalender wählbar.
Datenbank von vor 2.6 OHNE vorbelegtes Bundesland (alle_tests: OHNE_VORBELEGUNG).
Bundesland-Abfrage beim Start, Einstellung in der Administration, Hinweise an
Datumsfeldern, Symbol in der Buchungsliste, Serienhinweis, Datumsdialog im
Plan-Protokoll, erste Auszahlung im Dialog, Schnellbuchung und Import."""
import os, sys, tempfile
from playwright.sync_api import sync_playwright
BASIS = "http://localhost:8935/"
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ausgabe", "bilder", "ui26") + "/"
os.makedirs(SHOTS, exist_ok=True)
ERG = []
def pruef(n, b, info=""):
    ERG.append((n, bool(b))); print(("OK   " if b else "FEHL ") + n + (f"  [{info}]" if info and not b else ""))

with sync_playwright() as p:
    br = p.chromium.launch(env={**os.environ, "LANG": "de_DE.UTF-8", "LANGUAGE": "de"})
    page = br.new_context(timezone_id="Europe/Berlin", locale="de-DE", viewport={"width": 1400, "height": 1000}).new_page()
    fehler, dialoge = [], []
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.on("console", lambda m: fehler.append(m.text) if m.type == "error" else None)
    page.on("dialog", lambda d: (dialoge.append(d.message), d.dismiss()))
    def gehe(ziel):
        page.click(f'.nav-eintrag[data-ziel="{ziel}"]'); page.wait_for_timeout(800)
    def hinweis_bei(selektor):
        h = page.locator(f"{selektor} ~ .feiertag-hinweis")
        return h.inner_text() if h.count() and h.is_visible() else ""

    # ─── Bundesland-Abfrage beim ersten Start nach dem Update ──────────
    page.goto(BASIS); page.wait_for_timeout(1500)
    pruef("Start: Dialog „Bundesland wählen“ erscheint, NRW vorbelegt, Hinweistext aus der Hilfe",
          page.is_visible("#bundesland-dialog") and page.input_value("#bundesland-auswahl") == "NW"
          and "Bundesland" in page.inner_text("#bundesland-dialog .hinweis"))
    pruef("Auswahl enthält 20 Einträge, darunter die Sonderfälle",
          page.locator("#bundesland-auswahl option").count() == 20
          and page.locator("#bundesland-auswahl option", has_text="Bayern – Stadt Augsburg").count() == 1
          and page.locator("#bundesland-auswahl option", has_text="Thüringen – mit Fronleichnam").count() == 1)
    page.screenshot(path=SHOTS + "01_bundesland_dialog.png")
    page.keyboard.press("Escape"); page.wait_for_timeout(300)
    pruef("Pflichtangabe: Escape schließt den Dialog nicht", page.is_visible("#bundesland-dialog"))
    page.click('#form-bundesland button[type="submit"]'); page.wait_for_timeout(700)
    pruef("„Übernehmen“ speichert und schließt",
          not page.is_visible("#bundesland-dialog")
          and page.evaluate("fetch('api/feiertage/regionen').then(r => r.json()).then(r => r.gewaehlt)") == "NW")
    page.reload(); page.wait_for_timeout(1500)
    pruef("Nach dem Neuladen kein Dialog mehr", not page.is_visible("#bundesland-dialog"))

    # ─── Administration: Bundesland ändern ──────────────────────────────
    gehe("admin")
    page.click('[data-admin-tab="stammdaten"]'); page.wait_for_timeout(400)
    page.evaluate("document.getElementById('form-feiertage-region').closest('details').open = true")
    page.wait_for_timeout(300)
    block = page.locator("#form-feiertage-region").locator("xpath=ancestor::details")
    pruef("Admin: Block „Feiertage“ mit Auswahl (NRW), Hinweis und Liste des Jahres",
          page.input_value("#feiertage-region") == "NW" and "ändern sich nicht" in block.inner_text()
          and page.locator("#feiertage-liste tbody tr").count() == 11, page.locator("#feiertage-liste tbody tr").count())
    pruef("Admin: Knopf „Neu berechnen“ entfällt", page.locator("#feiertage-aktualisieren").count() == 0)
    page.select_option("#feiertage-region", "BY_A")
    page.click('#form-feiertage-region button[type="submit"]'); page.wait_for_timeout(800)
    pruef("Admin: Wechsel auf Augsburg gespeichert, Friedensfest in der Liste",
          "Bayern – Stadt Augsburg" in page.inner_text("#feiertage-status")
          and "Augsburger Friedensfest" in page.inner_text("#feiertage-liste"))
    page.screenshot(path=SHOTS + "02_admin_feiertage.png")
    page.select_option("#feiertage-region", "NW")
    page.click('#form-feiertage-region button[type="submit"]'); page.wait_for_timeout(800)

    # ─── Buchungen: Hinweis am Datumsfeld, Symbol in der Liste ──────────
    gehe("buchungen")
    feld = '#form-buchung [name="datum"]'
    page.fill(feld, "2026-12-25"); page.wait_for_timeout(400)
    pruef("Buchung: Hinweis unter dem Datum am 1. Weihnachtstag",
          hinweis_bei(feld) == "25.12.2026 ist ein Feiertag (1. Weihnachtstag).", hinweis_bei(feld))
    page.fill(feld, "2026-06-04"); page.wait_for_timeout(400)
    pruef("Buchung: regionaler Feiertag (Fronleichnam NRW)", "Fronleichnam" in hinweis_bei(feld))
    page.fill(feld, "2026-12-22"); page.wait_for_timeout(400)
    pruef("Buchung: Werktag ohne Hinweis", hinweis_bei(feld) == "")
    page.fill(feld, "2026-10-03")
    page.fill('#form-buchung [name="betrag"]', "9,99".replace(",", "."))
    page.fill('#form-buchung [name="beschreibung"]', "UI26 Einheitstag")
    page.click("#buchung-submit"); page.wait_for_timeout(1200)
    zeile = page.locator("#buchungen-tabelle tr", has_text="UI26 Einheitstag")
    marke = zeile.locator(".feiertag-marke")
    pruef("Buchung am Feiertag wird gespeichert (nichts gesperrt) und in der Liste markiert",
          zeile.count() == 1 and marke.count() == 1
          and marke.get_attribute("title") == "03.10.2026 ist ein Feiertag (Tag der Deutschen Einheit).")
    pruef("Befund P (2.6.1): Ist-Buchung aus dem Formular ohne Zielkonto (kein „→“ in der Spalte Konto)",
          zeile.count() == 1 and "→" not in zeile.locator("td").nth(1).inner_text())
    pruef("Nach dem Buchen: Hinweis passt zum zurückgesetzten Datum (heute)",
          page.input_value(feld) != "2026-10-03" and "03.10.2026" not in hinweis_bei(feld))
    page.select_option("#buchungen-filter-herkunft", "anstehend"); page.wait_for_timeout(1200)
    pruef("Buchungsliste mit Vorschau: anstehende Termine werden ebenfalls markiert (Symbol je Feiertagsdatum)",
          page.locator("#buchungen-tabelle .feiertag-marke").count() >= 1)
    page.locator("#buchungen-tabelle tr", has_text="UI26 Einheitstag").scroll_into_view_if_needed()
    page.screenshot(path=SHOTS + "03_buchungen.png")

    # ─── Konten: Saldo-Korrektur ────────────────────────────────────────
    gehe("konten")
    feld = '#form-saldo-korrektur [name="datum"]'
    page.fill(feld, "2026-10-03"); page.wait_for_timeout(400)
    pruef("Saldo-Korrektur: Hinweis am Datumsfeld", "Tag der Deutschen Einheit" in hinweis_bei(feld))

    # ─── Vorlage: Serienhinweis nach dem Speichern ──────────────────────
    gehe("wiederkehrend")
    f = "#form-wiederkehrend "
    page.fill(f + '[name="betrag"]', "11")
    page.select_option(f + '[name="kategorie_id"]', label=page.locator(f + '[name="kategorie_id"] option', has_text="Lebensmittel").first.inner_text())
    page.fill(f + '[name="beschreibung"]', "UI26 Serie")
    page.fill(f + '[name="tag_des_monats"]', "1")
    page.fill(f + '[name="startdatum"]', page.evaluate("datumISO(new Date(new Date().getFullYear(), new Date().getMonth(), 1))"))
    page.click("#wk-submit"); page.wait_for_timeout(1200)
    serie = page.inner_text("#wk-feiertage") if page.is_visible("#wk-feiertage") else ""
    jahr = page.evaluate("new Date().getFullYear() + 1")
    pruef("Vorlage: Hinweis zu den Terminen der nächsten 12 Monate, Neujahr mit Verschiebung",
          "nächsten 12 Monate" in serie and f"01.01.{jahr} ist ein Feiertag (Neujahr), gebucht wird am" in serie, serie[:300])
    page.screenshot(path=SHOTS + "04_vorlage_serie.png")

    # ─── Plan-Protokoll: Dialog statt prompt() ──────────────────────────
    gehe("plan")
    knopf = page.locator("#plan-protokoll-tabelle button", has_text="Datum ändern").first
    pruef("Plan-Protokoll: Knopf „Datum ändern“ vorhanden", knopf.count() == 1)
    knopf.click(); page.wait_for_timeout(500)
    dfeld = '#form-datum-dialog [name="datum"]'
    pruef("Plan-Protokoll: Dialog mit vorbelegtem Datum statt Browser-Abfrage",
          page.is_visible("#datum-dialog") and len(page.input_value(dfeld)) == 10 and not dialoge)
    page.fill(dfeld, "2026-11-01"); page.wait_for_timeout(400)
    pruef("Plan-Protokoll: Hinweis im Dialog, auch für einen Feiertag am Sonntag",
          "01.11.2026 ist ein Feiertag (Allerheiligen)." == hinweis_bei(dfeld), hinweis_bei(dfeld))
    page.screenshot(path=SHOTS + "05_datum_dialog.png")
    vorher = page.inner_text("#plan-protokoll-tabelle")
    page.click("#datum-dialog-abbrechen"); page.wait_for_timeout(500)
    pruef("Plan-Protokoll: „Abbrechen“ ändert nichts", not page.is_visible("#datum-dialog")
          and page.inner_text("#plan-protokoll-tabelle") == vorher)
    knopf.click(); page.wait_for_timeout(400)
    page.keyboard.press("Escape"); page.wait_for_timeout(300)
    pruef("Plan-Protokoll: Escape schließt ohne Änderung", not page.is_visible("#datum-dialog")
          and page.inner_text("#plan-protokoll-tabelle") == vorher)

    # ─── Darlehen: erste Auszahlung im Dialog ───────────────────────────
    gehe("darlehen")
    f = "#form-darlehen "
    for name, wert in [("bezeichnung", "UI26 Darlehen"), ("darlehenssumme", "50000"), ("zinssatz", "3"),
                       ("zinsbeginn", "2026-12-24"), ("tilgungsbeginn", "2027-01-30"), ("laufzeit_jahre", "10"),
                       ("ende_zinsbindung", "2036-12-30"), ("anschlusszinssatz", "4"), ("feste_rate", "500")]:
        page.fill(f + f'[name="{name}"]', wert)
    page.click("#darlehen-submit"); page.wait_for_timeout(1500)
    dlg = page.locator("#darlehen-dialog")
    pruef("Darlehen anlegen: Fenster „Erste Auszahlung“ statt Browser-Abfrage, Datum = Zinsbeginn",
          dlg.is_visible() and "Erste Auszahlung" in dlg.inner_text()
          and page.input_value('#form-darlehen-dialog [name="datum"]') == "2026-12-24" and not dialoge)
    page.fill('#form-darlehen-dialog [name="datum"]', "2026-12-25"); page.wait_for_timeout(400)
    pruef("Erste Auszahlung: Hinweis am Datumsfeld", "1. Weihnachtstag" in hinweis_bei('#form-darlehen-dialog [name="datum"]'))
    page.screenshot(path=SHOTS + "06_erste_auszahlung.png")
    page.click("#darlehen-dialog-abbrechen"); page.wait_for_timeout(500)
    pruef("Erste Auszahlung: „Überspringen“ schließt, Darlehen bleibt angelegt",
          not dlg.is_visible() and "UI26 DARLEHEN" in page.inner_text("#abschnitt-darlehen").upper())

    # ─── Import-Vorschau ───────────────────────────────────────────────
    gehe("admin")
    page.click('[data-admin-tab="stammdaten"]'); page.wait_for_timeout(400)
    page.evaluate("document.getElementById('form-import').closest('details').open = true")
    konto = page.evaluate("fetch('api/konten').then(r => r.json()).then(l => l[0].name)")
    pfad = tempfile.mktemp(suffix=".csv")
    open(pfad, "w", encoding="utf-8").write(f"datum,konto,betrag,kategorie,beschreibung\n2026-12-26,{konto},5,Lebensmittel/Verpflegung,UI26 Import\n")
    page.select_option('#form-import [name="art"]', "buchungen")
    page.set_input_files("#import-datei-feld", pfad)
    page.click("#import-pruefen"); page.wait_for_timeout(1500)
    ergebnis = page.inner_text("#import-ergebnis")
    pruef("Import-Vorschau: Feiertagshinweis zur Zeile", "Zeile 2" in ergebnis and "2. Weihnachtstag" in ergebnis, ergebnis[:400])
    page.click("#import-verwerfen"); page.wait_for_timeout(300)

    # ─── Schnellbuchung ────────────────────────────────────────────────
    page.goto(BASIS + "schnellbuchung"); page.wait_for_timeout(1200)
    # seit 2.6.3 sind alle Felder ohne Aufklappen sichtbar
    page.fill("#sb-datum-feld", "2026-12-25"); page.wait_for_timeout(500)
    pruef("Schnellbuchung: Hinweis unter „Datum“", page.is_visible("#sb-feiertag")
          and page.inner_text("#sb-feiertag") == "25.12.2026 ist ein Feiertag (1. Weihnachtstag).")
    page.fill("#sb-datum-feld", "2026-12-22"); page.wait_for_timeout(500)
    pruef("Schnellbuchung: kein Hinweis an einem Werktag", not page.is_visible("#sb-feiertag"))
    page.fill("#sb-datum-feld", "2026-12-25"); page.wait_for_timeout(300)
    page.screenshot(path=SHOTS + "07_schnellbuchung.png")

    # ─── Schmale Ansicht ───────────────────────────────────────────────
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASIS); page.wait_for_timeout(1200)
    page.evaluate("document.querySelector('.nav-eintrag[data-ziel=\"buchungen\"]').click()"); page.wait_for_timeout(800)
    page.fill('#form-buchung [name="datum"]', "2026-12-25"); page.wait_for_timeout(400)
    breite = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    pruef("Schmal (390 px): Hinweis sichtbar, kein waagrechtes Scrollen durch den Hinweis",
          "1. Weihnachtstag" in hinweis_bei('#form-buchung [name="datum"]') and breite)
    page.screenshot(path=SHOTS + "08_schmal.png")

    pruef("Keine Browser-Dialoge, keine JavaScript-Fehler", not dialoge and not fehler, (dialoge, fehler))

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

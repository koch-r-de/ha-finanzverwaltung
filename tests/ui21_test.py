"""Oberflächentest 2.1 (Playwright, Server auf 8935): Hilfe, „?“, Zurück, Suche, Hinweise, Wiederkehrend, Schrift."""
from playwright.sync_api import sync_playwright
BASIS = "http://localhost:8935/"
import os
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ausgabe", "bilder", "ui21") + "/"
import os; os.makedirs(SHOTS, exist_ok=True)
ERG = []
def pruef(n, b, info=""):
    ERG.append((n, bool(b))); print(("OK   " if b else "FEHL ") + n + (f"  [{info}]" if info and not b else ""))

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(timezone_id="Europe/Berlin", viewport={"width": 1400, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    fehler, dialoge = [], []
    page.on("console", lambda m: fehler.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.on("dialog", lambda d: (dialoge.append(d.message), d.accept()))
    page.goto(BASIS); page.wait_for_timeout(1500)
    hilfe = page.request.get(BASIS + "api/hilfe").json()
    def gehe(z): page.click(f'.nav-eintrag[data-ziel="{z}"]'); page.wait_for_timeout(900)
    def scroll(): return page.evaluate("document.querySelector('.hauptbereich').scrollTop")

    # Seitenleiste
    unten = page.locator(".nav-liste-admin .nav-eintrag").all_inner_texts()
    pruef("Seitenleiste: „Hilfe“ fest über „Administration“", [t.strip() for t in unten] == ["Hilfe", "Administration"], unten)
    gehe("admin"); page.click('[data-admin-tab="system"]'); page.wait_for_timeout(500)
    page.evaluate("document.getElementById('reihenfolge-editor').closest('details').open = true"); page.wait_for_timeout(300)
    editor = page.locator("#reihenfolge-editor").inner_text()
    menue_hinweis = page.locator('[data-hinweis="admin.menue"]').inner_text()
    pruef("Menü-Reihenfolge: Hilfe nicht verschiebbar, Hinweistext nennt Hilfe",
          "Hilfe" not in editor and "„Hilfe“ und „Administration“" in menue_hinweis, menue_hinweis)

    # Schrift der Administration wie Seitenleiste
    nav = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('.nav-eintrag')); return [s.fontFamily, s.fontSize]; })()")
    h2 = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('#abschnitt-admin details.block > summary h2')); return [s.fontFamily, s.fontSize]; })()")
    tab = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('#abschnitt-admin .admin-tab-knopf')); return [s.fontFamily, s.fontSize]; })()")
    pruef("Administration: Blocküberschriften und Tabs in Schrift und Größe der Seitenleiste", nav == h2 == tab, (nav, h2, tab))
    andere = page.evaluate("getComputedStyle(document.querySelector('.budget-tab-knopf')).fontFamily")
    pruef("Andere Seiten unverändert (Budget-Tabs serif)", andere != nav, andere)

    # Hinweise aus der Hilfedatei
    gehe("konten")
    soll = hilfe["hinweise"]["konten.saldo-korrektur"]["html"]
    ist = page.locator('[data-hinweis="konten.saldo-korrektur"]').inner_html()
    pruef("Hinweistext in der App wortgleich aus der Hilfedatei", ist.strip() == soll.strip(), (ist, soll))
    gehe("auswertungen")
    titel = page.locator("label.inflations-schalter").first.get_attribute("title")
    pruef("Tooltip „Inflation einrechnen“ aus der Hilfedatei", titel and titel.startswith("Rechnet Posten mit Inflations-Häkchen"), titel)

    # „?“ in jedem Seitenkopf, Sprung und Zurück
    for z in ["start", "konten", "buchungen", "wiederkehrend", "plan", "budgets", "darlehen", "altersvorsorge",
              "auswertungen", "jahr", "admin"]:
        gehe(z)
        if not page.locator(f"#abschnitt-{z} .kopfzeile h1 .hilfe-sprung").is_visible():
            pruef(f"„?“ im Seitenkopf von {z}", False)
    pruef("„?“ im Seitenkopf jeder Ansicht sichtbar", all(o for n, o in ERG if n.startswith("„?“ im Seitenkopf von")))
    gehe("buchungen")
    page.evaluate("document.querySelector('.hauptbereich').scrollTop = 400"); page.wait_for_timeout(200)
    vorher = scroll()
    page.locator('h2[data-hilfe="buchungen.liste"] .hilfe-sprung').click(); page.wait_for_timeout(900)
    aktiv = page.evaluate("aktiverAbschnitt()")
    kap = page.locator("#hilfe-k-buchungen\\.liste")
    box = kap.bounding_box()
    pruef("„?“ am Block öffnet die Hilfe beim passenden Kapitel", aktiv == "hilfe" and box and 0 <= box["y"] < 300, (aktiv, box))
    pruef("Kopf der Hilfe mit „Zurück“ bleibt sichtbar", page.locator("#hilfe-zurueck").is_visible())
    page.screenshot(path=SHOTS + "hilfe_sprung.png")
    page.click("#hilfe-zurueck"); page.wait_for_timeout(1000)
    pruef("„Zurück“ führt zur Ansicht und Stelle zurück", page.evaluate("aktiverAbschnitt()") == "buchungen" and abs(scroll() - vorher) < 5,
          (page.evaluate("aktiverAbschnitt()"), vorher, scroll()))
    # „?“ in aufklappbarem Admin-Block klappt nicht um
    gehe("admin"); page.click('[data-admin-tab="stammdaten"]'); page.wait_for_timeout(300)
    det = page.locator('#admin-sparziele-block')
    offen_vorher = det.evaluate("d => d.open")
    det.locator(".hilfe-sprung").click(); page.wait_for_timeout(700)
    pruef("„?“ im Admin-Block springt ohne Auf-/Zuklappen", page.evaluate("aktiverAbschnitt()") == "hilfe"
          and det.evaluate("d => d.open") == offen_vorher)
    page.click("#hilfe-zurueck"); page.wait_for_timeout(700)

    # Daten zurücksetzen: Kurztext + Sprung
    page.click('[data-admin-tab="zuruecksetzen"]'); page.wait_for_timeout(800)
    karte = page.locator('.reset-karte[data-art="konten_loeschen"]')
    karte.locator(".hilfe-knopf").click(); page.wait_for_timeout(200)
    kurz = karte.locator(".hilfetext").inner_text()
    pruef("Zurücksetzen: „?“ zeigt Kurztext aus der Hilfe", kurz.startswith("Entfernt die gewählten Konten") and "Mehr in der Hilfe" in kurz, kurz)
    karte.locator(".hilfe-link").click(); page.wait_for_timeout(800)
    pruef("Zurücksetzen: „Mehr in der Hilfe“ springt ins Kapitel",
          page.locator("#hilfe-k-zuruecksetzen\\.konten-loeschen").bounding_box()["y"] < 300)
    page.click("#hilfe-zurueck"); page.wait_for_timeout(700)
    pruef("Zurück landet wieder im Tab „Daten zurücksetzen“", page.locator('[data-admin-tab-inhalt="zuruecksetzen"]').is_visible())

    # Budgets: Prognose-„?“
    gehe("budgets"); page.click('[data-budget-tab="uebersicht"]'); page.wait_for_timeout(800)
    klein = page.locator(".hilfe-sprung-klein").first
    pruef("Budgets: Prognose-„?“ mit Text aus der Hilfe", klein.count() and "Fix-Prognose" in (klein.get_attribute("title") or ""))
    klein.click(); page.wait_for_timeout(700)
    pruef("Budgets: Prognose-„?“ springt zu „Übersicht und Ampel“",
          page.locator("#hilfe-k-budgets\\.uebersicht").bounding_box()["y"] < 300)

    # Hilfe-Ansicht: Inhaltsverzeichnis, Suche, Verweise, Bilder, PDF
    gehe("hilfe")
    pruef("Hilfe: Inhaltsverzeichnis mit allen Kapiteln", page.locator("#hilfe-inhalt a").count() == len(hilfe["kapitel"]))
    page.locator('#hilfe-inhalt a[data-anker="admin.feiertage"]').click(); page.wait_for_timeout(500)
    pruef("Hilfe: Inhaltsverzeichnis springt zum Kapitel", page.locator("#hilfe-k-admin\\.feiertage").bounding_box()["y"] < 300)
    page.locator("#hilfe-k-admin\\.feiertage a", has_text="Wann wird gebucht?").click(); page.wait_for_timeout(500)
    pruef("Hilfe: Verweis „Siehe auch“ springt", page.locator("#hilfe-k-wiederkehrend\\.automatik").bounding_box()["y"] < 300)
    page.fill("#hilfe-suche", "Trägerkonto Entnahme"); page.wait_for_timeout(600)
    treffer = page.locator(".hilfe-treffer")
    pruef("Suche: Treffer mit Auszug und Markierung", treffer.count() >= 1 and page.locator(".hilfe-auszug mark").count() >= 1,
          treffer.count())
    page.screenshot(path=SHOTS + "hilfe_suche.png")
    treffer.first.locator("a").click(); page.wait_for_timeout(600)
    pruef("Suche: Klick auf Treffer zeigt Kapitel", page.input_value("#hilfe-suche") == "" and page.locator("#hilfe-text section").count() > 50)
    page.fill("#hilfe-suche", "xyzunbekannt"); page.wait_for_timeout(600)
    pruef("Suche: kein Treffer wird gemeldet", "Keine Treffer" in page.locator("#hilfe-text").inner_text())
    page.fill("#hilfe-suche", ""); page.wait_for_timeout(500)
    page.locator('#hilfe-inhalt a[data-anker="konten.anlegen"]').click(); page.wait_for_timeout(800)
    img = page.locator("#hilfe-k-konten\\.anlegen img")
    pruef("Hilfe: Bildschirmfoto geladen", img.count() == 1 and img.evaluate("i => i.complete && i.naturalWidth > 100"))
    pruef("Hilfe: Programmversion im Kopf", "programmversion" in page.locator("#hilfe-version").inner_text().lower())
    sv = page.locator("#hilfe-k-stichwortverzeichnis .hilfe-stichwort")
    pruef("Hilfe: Stichwortverzeichnis mit Verweisen", sv.count() == len(hilfe["stichwortverzeichnis"]))
    with page.expect_download() as dl:
        page.click("#hilfe-pdf")
    pruef("Hilfe: „PDF-Handbuch“ lädt ein PDF herunter", dl.value.suggested_filename.endswith(".pdf"), dl.value.suggested_filename)

    # Wiederkehrend: Dynamik-Spalte weg, Formular bleibt oben, Tabelle scrollt
    gehe("wiederkehrend")
    kopf = page.locator("#abschnitt-wiederkehrend thead th").all_inner_texts()
    pruef("Wiederkehrend: Spalte „Dynamik“ ausgeblendet", not any("Dynamik" in k for k in kopf), kopf)
    rahmen = page.locator(".wk-tabelle-rahmen")
    pruef("Wiederkehrend: Vorlagen-Tabelle scrollt für sich", rahmen.evaluate("r => r.scrollHeight > r.clientHeight"),
          rahmen.evaluate("r => [r.scrollHeight, r.clientHeight]"))
    rahmen.evaluate("r => r.scrollTop = r.scrollHeight")
    page.wait_for_timeout(300)
    page.locator("#wiederkehrend-tabelle tr").last.locator("button", has_text="Ändern").click(); page.wait_for_timeout(500)
    fbox = page.locator("#form-wiederkehrend").bounding_box()
    pruef("Wiederkehrend: „Neue Vorlage“ bleibt beim Ändern oben sichtbar", fbox["y"] >= 0 and fbox["y"] < 200 and scroll() == 0,
          (fbox, scroll()))
    pruef("Wiederkehrend: Tabellenkopf bleibt beim Scrollen stehen",
          page.locator(".wk-tabelle-rahmen thead th").first.bounding_box()["y"] >= rahmen.bounding_box()["y"] - 1)
    page.screenshot(path=SHOTS + "wiederkehrend.png")
    page.click("#wk-verwerfen")

    # Schnellbuchung: „?“ führt in die Hilfe
    page.goto(BASIS + "schnellbuchung"); page.wait_for_timeout(800)
    page.click(".sb-hilfe"); page.wait_for_timeout(2500)
    pruef("Schnellbuchung: „?“ öffnet die Hilfe beim Kapitel", page.evaluate("aktiverAbschnitt()") == "hilfe"
          and page.locator("#hilfe-k-schnellbuchung\\.nutzen").bounding_box()["y"] < 300)

    # Kategorie ändern bleibt Umbenennung
    page.goto(BASIS); page.wait_for_timeout(1200); gehe("admin")
    page.evaluate("document.getElementById('form-kategorie').closest('details').open = true"); page.wait_for_timeout(300)
    n0 = len(page.request.get(BASIS + "api/kategorien").json())
    page.locator("#kategorien-baum > div", has_text="Kraftstoff").first.locator("button", has_text="Ändern").click(); page.wait_for_timeout(500)
    titel_k = page.locator("#kategorie-form-titel").inner_text()
    page.fill('#form-kategorie input[name="name"]', "Sprit"); page.click("#kategorie-submit"); page.wait_for_timeout(800)
    ks = page.request.get(BASIS + "api/kategorien").json()
    pruef("Kategorie ändern: Umbenennung, keine neue Kategorie", titel_k == "Kategorie ändern" and len(ks) == n0
          and "Sprit" in [k["name"] for k in ks] and "Kraftstoff" not in [k["name"] for k in ks])
    pruef("Keine Konsolenfehler", not fehler, fehler)
    ctx.close(); br.close()
fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

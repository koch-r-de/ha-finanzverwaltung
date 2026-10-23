"""Oberflächentest 2.3 (Playwright, Server auf 8935): Mehrfachauswahl, automatisches Laden, Filter merken,
Diagramm-Grundstil, Saldo, Cashflow-Verdichtung, Kacheln, Kategorien-Rangliste, Jahresübersicht."""
import os, re
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright
BASIS = "http://localhost:8935/"
import os
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ausgabe", "bilder", "ui23") + "/"
os.makedirs(SHOTS, exist_ok=True)
ERG = []
def pruef(n, b, info=""):
    ERG.append((n, bool(b))); print(("OK   " if b else "FEHL ") + n + (f"  [{info}]" if info and not b else ""))

with sync_playwright() as p:
    br = p.chromium.launch(env={**os.environ, "LANG": "de_DE.UTF-8", "LANGUAGE": "de"})
    ctx = br.new_context(timezone_id="Europe/Berlin", locale="de-DE", viewport={"width": 1400, "height": 1000})
    page = ctx.new_page()
    fehler, anfragen = [], []
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.on("console", lambda m: fehler.append(m.text) if m.type == "error" else None)
    page.on("request", lambda r: anfragen.append(r.url))
    page.goto(BASIS); page.wait_for_timeout(1500)
    def gehe(ziel):
        page.click(f'.nav-eintrag[data-ziel="{ziel}"]'); page.wait_for_timeout(1500)
    def letzte(pfad):
        treffer = [u for u in anfragen if pfad in u]
        return parse_qs(urlparse(treffer[-1]).query) if treffer else None

    gehe("auswertungen")
    pruef("Kein Knopf „Aktualisieren“ mehr", page.locator("#auswertung-aktualisieren").count() == 0)
    pruef("Grundstil: gemeinsamer Tooltip je Monat (index), Punkte als Legende",
          page.evaluate("Chart.defaults.interaction.mode === 'index' && Chart.defaults.plugins.legend.labels.usePointStyle"))
    ticks = page.evaluate("CHART_SALDO.scales.x.ticks.map(t => t.label)")
    pruef("Grundstil: Achse mit Monatsnamen („Okt 26“) statt ISO-Datum",
          ticks and all(re.fullmatch(r"(Jan|Feb|Mär|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez) \d\d", t) for t in ticks), ticks[:4])
    pruef("Grundstil: keine senkrechten Rasterlinien", page.evaluate("CHART_SALDO.options.scales.x.grid.display") is False)
    seg = page.locator('.segment[data-segment-fuer="auswertung-horizont"] button').all_inner_texts()
    pruef("Zeithorizont als Umschaltknöpfe 1 J … Frei, 5 J aktiv",
          seg == ["1 J", "5 J", "10 J", "20 J", "30 J", "Frei"]
          and page.locator('.segment[data-segment-fuer="auswertung-horizont"] button.an').inner_text() == "5 J", seg)

    # Kacheln
    kacheln = page.locator("#auswertung-kacheln .karte .etikett").all_inner_texts()
    pruef("Vier Kacheln: Nettovermögen heute, am Horizontende, Ø Überschuss, Sparquote",
          len(kacheln) == 4 and kacheln[0].upper().startswith("NETTOVERMÖGEN HEUTE") and "Ø ÜBERSCHUSS" in kacheln[2].upper()
          and kacheln[3].upper() == "SPARQUOTE", kacheln)
    st = page.evaluate("fetch('api/auswertungen/saldo-verlauf?von=' + auswertungZeitraum().von + '&bis=' + auswertungZeitraum().bis).then(r => r.json())")
    erwartet = (st["stand_heute"]["konten"] - st["stand_heute"]["restschuld"]) / 1000
    wert = page.locator("#auswertung-kacheln .karte .betrag").first.inner_text()
    pruef("Kachel Nettovermögen heute = Konten minus Restschuld (k€)",
          wert.replace(" ", " ") == f"{erwartet:.1f}".replace(".", ",").replace(",0", "") + " k€"
          or wert.startswith(f"{erwartet:.1f}".replace(".", ",")), (wert, erwartet))
    page.uncheck("#auswertung-inkl-darlehen"); page.wait_for_timeout(1500)
    pruef("Ohne „inkl. Darlehen“: Kachel heißt „Vermögen heute“, Linie „Summe der Konten“",
          page.locator("#auswertung-kacheln .karte .etikett").first.inner_text().upper() == "VERMÖGEN HEUTE"
          and page.evaluate("CHART_SALDO.data.datasets[0].label") == "Summe der Konten")
    page.check("#auswertung-inkl-darlehen"); page.wait_for_timeout(1500)

    # Saldo-Verlauf
    ds = page.evaluate("CHART_SALDO.data.datasets.map(d => [d.label, d.stack, d.fill, !!d.borderDash])")
    pruef("Saldo: Nettovermögen-Linie, deckende Konten-Flächen, Restschuld gestrichelt ohne Fläche",
          ds[0][0] == "Nettovermögen" and ds[0][2] is False and all(d[2] for d in ds if d[1] == "konten")
          and any("Restschuld" in d[0] and d[3] and d[2] is False for d in ds), ds)

    # Cashflow-Verdichtung
    cf = page.evaluate("[CHART_CASHFLOW.data.labels, CHART_CASHFLOW.data.datasets.map(d => [d.label, d.type, d.stack, d.data.reduce((a,b)=>a+(b||0),0)])]")
    pruef("Cashflow 5 J: je Quartal", all(re.fullmatch(r"Q[1-4] \d\d", l) for l in cf[0]), cf[0][:3])
    aus = next(d for d in cf[1] if d[0] == "Ausgaben")
    pruef("Cashflow: Ausgaben nach unten, Überschuss als Linie, ein gemeinsamer Stapel",
          aus[3] < 0 and any(d[0] == "Überschuss" and d[1] == "line" for d in cf[1])
          and len({d[2] for d in cf[1] if d[1] == "bar"}) == 1, cf[1])
    pruef("Cashflow: anstehender Anteil des laufenden Monats vorhanden",
          any("anstehend" in d[0] and d[3] != 0 for d in cf[1]), cf[1])
    page.click('.segment[data-segment-fuer="auswertung-horizont"] button:has-text("1 J")'); page.wait_for_timeout(1500)
    labels = page.evaluate("CHART_CASHFLOW.data.labels")
    pruef("Cashflow 1 J: je Monat", all(re.fullmatch(r"\d{4}-\d\d", l) for l in labels) and "je Monat" in page.inner_text("#cashflow-unter"))
    page.click('.segment[data-segment-fuer="auswertung-horizont"] button:has-text("30 J")'); page.wait_for_timeout(2500)
    labels = page.evaluate("CHART_CASHFLOW.data.labels")
    pruef("Cashflow 30 J: je Jahr", all(re.fullmatch(r"\d{4}", l) for l in labels), labels[:3])
    q = letzte("/auswertungen/saldo-verlauf")
    pruef("Zeithorizont-Knopf lädt sofort neu (bis = heute + 30 Jahre)", q and int(q["bis"][0][:4]) - int(q["von"][0][:4]) == 30, q)
    page.click('.segment[data-segment-fuer="auswertung-horizont"] button:has-text("5 J")'); page.wait_for_timeout(1500)

    # Kategorien-Rangliste
    kat = page.evaluate("[CHART_KATEGORIEN.options.indexAxis, CHART_KATEGORIEN.data.datasets[0].label, CHART_KATEGORIEN.data.datasets[0].data]")
    pruef("Kategorien: horizontale Rangliste der Ausgaben, absteigend sortiert",
          kat[0] == "y" and kat[1] == "Ausgaben" and kat[2] == sorted(kat[2], reverse=True), kat)
    page.click('#kategorien-seite button[data-wert="einnahme"]'); page.wait_for_timeout(400)
    pruef("Kategorien: Umschalten auf Einnahmen ohne neue Anfrage",
          page.evaluate("CHART_KATEGORIEN.data.datasets[0].label") == "Einnahmen")
    page.click('#kategorien-seite button[data-wert="ausgabe"]'); page.wait_for_timeout(300)

    # Konten-Mehrfachauswahl
    page.click("#auswertung-konten .mehrfach-knopf"); page.wait_for_timeout(300)
    zeilen = page.locator("#auswertung-konten .mehrfach-zeile")
    pruef("Konten-Liste mit Häkchen, „Alle“ und „Keine“, alle gewählt",
          zeilen.count() >= 2 and page.locator('#auswertung-konten [data-aktion="alle"]').count() == 1
          and all(cb.is_checked() for cb in page.locator("#auswertung-konten .mehrfach-zeile input").all()))
    anfragen.clear()
    page.click('#auswertung-konten [data-aktion="keine"]'); page.wait_for_timeout(1000)
    pruef("„Keine“: Hinweis statt Diagrammen, keine Anfrage",
          page.is_visible("#auswertung-leer") and not page.is_visible("#auswertung-inhalt")
          and not any("saldo-verlauf" in u for u in anfragen), page.inner_text("#auswertung-leer"))
    ids = page.evaluate("[...document.querySelectorAll('#auswertung-konten .mehrfach-zeile input')].map(i => i.dataset.id)")
    zeilen.nth(0).locator("input").check(); zeilen.nth(1).locator("input").check(); page.wait_for_timeout(1300)
    q = letzte("/auswertungen/saldo-verlauf")
    pruef("Zwei Konten gewählt: Diagramme laden sofort mit konten=", q and sorted(q["konten"][0].split(",")) == sorted(ids[:2]), q)
    pruef("Saldo zeigt nur die zwei gewählten Konten",
          page.evaluate("CHART_SALDO.data.datasets.filter(d => d.stack === 'konten').length") == 2)
    page.keyboard.press("Escape"); page.wait_for_timeout(300)
    chips = page.locator("#auswertung-konten .mehrfach-chip").all_inner_texts()
    pruef("Feld zeigt die gewählten Konten als Schilder", len(chips) == 2, chips)

    # Kategorien-Baum
    page.click("#auswertung-kategorien .mehrfach-knopf"); page.wait_for_timeout(300)
    page.click('#auswertung-kategorien [data-aktion="keine"]')
    wz = page.locator("#auswertung-kategorien .mehrfach-zeile", has_text="Wohnen").first
    wz.locator("input").check(); page.wait_for_timeout(200)
    wohn_kinder = page.evaluate("""() => { const w = KATEGORIEN.find(k => k.name === 'Wohnen');
        return KATEGORIEN.filter(k => k.parent_id === w.id).map(k => String(k.id)); }""")
    pruef("Haken an Oberkategorie setzt alle Unterkategorien",
          all(page.locator(f'#auswertung-kategorien input[data-id="{i}"]').is_checked() for i in wohn_kinder) and wohn_kinder)
    page.locator(f'#auswertung-kategorien input[data-id="{wohn_kinder[0]}"]').uncheck(); page.wait_for_timeout(200)
    pruef("Eine Unterkategorie abgewählt: Oberkategorie zeigt „–“",
          wz.locator("input").evaluate("i => i.indeterminate && !i.checked"))
    anfragen.clear()
    page.wait_for_timeout(600)
    pruef("Kategorien laden erst beim Schließen", not any("saldo-verlauf" in u for u in anfragen))
    page.fill("#auswertung-kategorien .mehrfach-suche", "kraft"); page.wait_for_timeout(200)
    sichtbar = [t.strip() for t in page.locator("#auswertung-kategorien .mehrfach-zeile:visible").all_inner_texts()]
    pruef("Suchfeld zeigt Treffer samt Oberkategorien", "Kraftstoff" in sichtbar and "Wohnen" not in sichtbar, sichtbar)
    page.locator("#auswertung-kategorien .mehrfach-zeile", has_text="Kraftstoff").locator("input").check()
    page.mouse.click(700, 40); page.wait_for_timeout(1800)
    q = letzte("/auswertungen/saldo-verlauf")
    namen = page.evaluate("CHART_SALDO.data.datasets.map(d => d.label)")
    pruef("Nach dem Schließen: Anfrage mit kategorien=, Saldo je Kategorie mit Summe",
          q and "kategorien" in q and namen[0] == "Summe" and "Wohnen (teilweise)" in namen
          and any("Kraftstoff" in n for n in namen), (q, namen))
    pruef("Hinweis zum Kategorie-Filter sichtbar, Kacheln zeigen Einnahmen/Ausgaben im Zeitraum",
          page.is_visible("#auswertung-kategorie-hinweis")
          and page.locator("#auswertung-kacheln .karte .etikett").first.inner_text().upper() == "EINNAHMEN IM ZEITRAUM")
    page.screenshot(path=SHOTS + "ui23_kategorien.png", full_page=True)

    # Filter merken
    gespeichert = page.evaluate("JSON.parse(localStorage.getItem('finanzapp.filter.auswertungen'))")
    pruef("Filter im Browser gespeichert", gespeichert and len(gespeichert["konten"]) == 2 and gespeichert["kategorien"], gespeichert)
    page.reload(); page.wait_for_timeout(1500); gehe("auswertungen")
    pruef("Nach Neuladen: Auswahl wiederhergestellt",
          len(page.locator("#auswertung-konten .mehrfach-chip").all_inner_texts()) == 2
          and "kategorien" in (letzte("/auswertungen/saldo-verlauf") or {}))
    page.click("#auswertung-konten .mehrfach-knopf"); page.click('#auswertung-konten [data-aktion="alle"]'); page.keyboard.press("Escape")
    page.click("#auswertung-kategorien .mehrfach-knopf"); page.click('#auswertung-kategorien [data-aktion="alle"]'); page.keyboard.press("Escape")
    page.wait_for_timeout(1500)
    q = letzte("/auswertungen/saldo-verlauf")
    pruef("„Alle“: Anfrage ohne Filter, Speicher meldet alle",
          q and "konten" not in q and "kategorien" not in q
          and page.evaluate("JSON.parse(localStorage.getItem('finanzapp.filter.auswertungen')).konten") is None, q)

    # Jahresübersicht
    gehe("jahr")
    pruef("Jahresübersicht: Mehrfachauswahl für Konten und Kategorien",
          page.locator("#jahr-filter-konten .mehrfach-knopf").count() == 1 and page.locator("#jahr-filter-kategorien .mehrfach-knopf").count() == 1)
    page.click("#jahr-filter-konten .mehrfach-knopf")
    page.locator("#jahr-filter-konten .mehrfach-zeile").nth(0).locator("input").uncheck(); page.wait_for_timeout(1300)
    q = letzte("/auswertungen/jahresuebersicht")
    pruef("Jahresübersicht lädt mit konten=", q and "konten" in q, q)
    pruef("Jahresübersicht: Tabelle „Nach Hauptkategorie“ unberührt",
          page.locator("#jahr-kategorien tr").count() >= 1 and page.locator("#jahr-kategorien .mehrfach-knopf").count() == 0)
    page.keyboard.press("Escape")
    pruef("Keine JavaScript-Fehler", not fehler, fehler)

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

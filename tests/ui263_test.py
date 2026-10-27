"""Oberflächentest 2.6.3 (Playwright, Server auf 8935): Schnellbuchung.
Issue #4 (Eingabetaste bucht sofort), Befund R (Kategorie ohne leere Option),
alle Felder sichtbar, Beschreibung vor Kategorie, Vorauswahl der Kategorie
aus den Regeln, Meldung oben. iPhone-Ansicht."""
import json, os, urllib.request
from playwright.sync_api import sync_playwright
BASIS = "http://localhost:8935/"
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ausgabe", "bilder", "ui263") + "/"
os.makedirs(SHOTS, exist_ok=True)
ERG = []
def pruef(n, b, info=""):
    ERG.append((n, bool(b))); print(("OK   " if b else "FEHL ") + n + (f"  [{info}]" if info and not b else ""))

def holen(pfad):
    return json.load(urllib.request.urlopen(BASIS + "api" + pfad))
def senden(pfad, daten):
    return json.load(urllib.request.urlopen(urllib.request.Request(BASIS + "api" + pfad, data=json.dumps(daten).encode(),
                                                                    headers={"Content-Type": "application/json"})))
kat = {k["name"]: k["id"] for k in holen("/kategorien")}
for r in holen("/regeln"):
    urllib.request.urlopen(urllib.request.Request(BASIS + f"api/regeln/{r['id']}", method="DELETE"))
senden("/regeln", {"muster": "wochenmarkt", "kategorie_id": kat["Lebensmittel/Verpflegung"]})
anzahl = lambda: len(holen("/buchungen?herkunft=manuell"))

with sync_playwright() as p:
    br = p.chromium.launch(env={**os.environ, "LANG": "de_DE.UTF-8", "LANGUAGE": "de"})
    ctx = br.new_context(**p.devices["iPhone 13"], locale="de-DE", timezone_id="Europe/Berlin")
    page = ctx.new_page()
    fehler, dialoge = [], []
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.on("console", lambda m: fehler.append(m.text) if m.type == "error" else None)
    page.on("dialog", lambda d: (dialoge.append(d.message), d.dismiss()))
    page.goto(BASIS + "schnellbuchung"); page.wait_for_timeout(1500)

    # Alle Felder sichtbar, Reihenfolge
    sichtbar = all(page.is_visible(s) for s in ("#sb-betrag", "#sb-konto", "#sb-beschreibung", "#sb-kategorie", "#sb-typ", "#sb-datum-feld"))
    pruef("Alle Felder ohne Aufklappen sichtbar, „Weitere Angaben“ entfällt",
          sichtbar and page.locator("#sb-details-schalter").count() == 0)
    y = lambda s: page.locator(s).bounding_box()["y"]
    pruef("Reihenfolge: Betrag, Konto, Beschreibung, Kategorie, dann Typ und Datum",
          y("#sb-betrag") < y("#sb-konto") < y("#sb-beschreibung") < y("#sb-kategorie") < y("#sb-typ")
          and abs(y("#sb-typ") - y("#sb-datum-feld")) < 5)
    breite = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    pruef("Kein waagrechtes Scrollen in der iPhone-Ansicht", breite)
    pruef("Befund R: Kategorie startet mit „– bitte wählen –“", page.input_value("#sb-kategorie") == ""
          and page.locator("#sb-kategorie option").first.inner_text() == "– bitte wählen –")
    pruef("Zielkonto und Sparziel nur bei Übertragung", not page.is_visible("#sb-zielkonto"))
    page.screenshot(path=SHOTS + "01_start.png", full_page=True)

    # Issue #4: Eingabetaste bucht nicht
    vorher = anzahl()
    page.tap("#sb-betrag"); page.keyboard.type("12,50"); page.keyboard.press("Enter"); page.wait_for_timeout(600)
    pruef("Issue #4: Eingabetaste im Betrag bucht nicht und leert nichts",
          anzahl() == vorher and page.input_value("#sb-betrag") == "12,50")
    pruef("Issue #4: Eingabetaste springt ins nächste Feld (Konto)", page.evaluate("document.activeElement.id") == "sb-konto")
    page.focus("#sb-beschreibung"); page.keyboard.type("Bäckerei"); page.keyboard.press("Enter"); page.wait_for_timeout(600)
    pruef("Issue #4: Eingabetaste in der Beschreibung bucht nicht, springt zur Kategorie",
          anzahl() == vorher and page.evaluate("document.activeElement.id") == "sb-kategorie")

    # Ohne Kategorie keine Buchung
    page.click("#sb-speichern"); page.wait_for_timeout(600)
    pruef("Ohne Regel-Treffer und ohne Wahl: keine Buchung, Warnung oben, Fokus auf Kategorie",
          anzahl() == vorher and "Kategorie" in page.inner_text("#sb-meldung")
          and page.evaluate("document.activeElement.id") == "sb-kategorie"
          and y("#sb-meldung") < y("#sb-betrag"))

    # Vorauswahl aus der Regel
    page.fill("#sb-beschreibung", "Einkauf Wochenmarkt"); page.wait_for_timeout(800)
    pruef("Vorauswahl: Regel setzt die Kategorie beim Tippen, „automatisch erkannt“ sichtbar",
          page.input_value("#sb-kategorie") == str(kat["Lebensmittel/Verpflegung"]) and page.is_visible("#sb-kategorie-auto"))
    pruef("Warnung verschwindet bei der nächsten Eingabe", page.inner_text("#sb-meldung") == "")
    page.screenshot(path=SHOTS + "02_vorauswahl.png", full_page=True)
    page.fill("#sb-beschreibung", "Einkauf Baumarkt"); page.wait_for_timeout(800)
    pruef("Vorauswahl: ohne Treffer fällt die automatische Kategorie zurück auf „bitte wählen“",
          page.input_value("#sb-kategorie") == "" and not page.is_visible("#sb-kategorie-auto"))
    eigene = str(kat["Kraftstoff"])
    page.select_option("#sb-kategorie", eigene)
    page.fill("#sb-beschreibung", "Wochenmarkt Käse"); page.wait_for_timeout(800)
    pruef("Vorrang: eigene Wahl bleibt trotz Regel-Treffer", page.input_value("#sb-kategorie") == eigene
          and not page.is_visible("#sb-kategorie-auto"))
    page.select_option("#sb-kategorie", ""); page.wait_for_timeout(800)
    pruef("„– bitte wählen –“ gibt die Kategorie wieder für die Regel frei",
          page.input_value("#sb-kategorie") == str(kat["Lebensmittel/Verpflegung"]))

    # Buchen über den Knopf
    page.click("#sb-speichern-weiter"); page.wait_for_timeout(1000)
    letzte = max(holen("/buchungen?herkunft=manuell"), key=lambda b: b["id"])
    pruef("„Speichern & weiter“ bucht Betrag, Beschreibung und Kategorie",
          anzahl() == vorher + 1 and letzte["betrag"] == -12.5 and letzte["beschreibung"] == "Wochenmarkt Käse"
          and letzte["kategorie_id"] == kat["Lebensmittel/Verpflegung"] and letzte["zielkonto_id"] is None, letzte)
    pruef("Danach: Meldung „Gebucht“ oben sichtbar, Betrag leer, Kategorie zurück, Fokus im Betrag",
          "Gebucht" in page.inner_text("#sb-meldung") and page.is_visible("#sb-meldung")
          and page.input_value("#sb-betrag") == "" and page.input_value("#sb-kategorie") == ""
          and page.evaluate("document.activeElement.id") == "sb-betrag")
    page.wait_for_timeout(8500)
    pruef("Meldung bleibt auch nach 8 Sekunden stehen", "Gebucht" in page.inner_text("#sb-meldung"))
    page.keyboard.type("3"); page.wait_for_timeout(200)
    pruef("Meldung verschwindet mit dem nächsten Betrag", page.inner_text("#sb-meldung") == "")

    # Übertragung braucht keine Kategorie
    page.select_option("#sb-typ", "Uebertragung"); page.wait_for_timeout(300)
    konten = holen("/konten")
    page.select_option("#sb-zielkonto", str(konten[1]["id"]))
    page.click("#sb-speichern"); page.wait_for_timeout(1000)
    letzte = max(holen("/buchungen?herkunft=manuell"), key=lambda b: b["id"])
    pruef("Übertragung ohne Kategorie wird gebucht, mit Zielkonto",
          letzte["typ"] == "Uebertragung" and letzte["zielkonto_id"] == konten[1]["id"], letzte)
    page.screenshot(path=SHOTS + "03_uebertragung.png", full_page=True)

    pruef("Keine Browser-Dialoge, keine JavaScript-Fehler", not dialoge and not fehler, (dialoge, fehler))

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

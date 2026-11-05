"""Oberflächentest 3.1 (Playwright, Server auf 8935): Saldo-Korrektur als
Buchung (#12) und gesperrte Kategorien (Befund AA).

Geprüft: Feld „Anfangsbestand“ je nach Konto, Vorschau der Differenz vor dem
Buchen, Differenz 0, kein Zukunftsdatum, Korrektur in der Buchungsliste ohne
„Ändern“ und mit Rückfrage samt Saldofolge beim Löschen, Auswahlfelder ohne
gesperrte Kategorien (Filter der Buchungsliste mit), Schnellbuchung direkt und
eingebettet wie im Panel der Integration, keine Konsolenfehler."""
import functools, http.server, os, shutil, sys, tempfile, threading
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

BASIS = "http://localhost:8935/"
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(WURZEL, "tests", "ausgabe", "bilder", "ui31") + "/"
os.makedirs(SHOTS, exist_ok=True)
ERG = []
def pruef(n, b, info=""):
    ERG.append((n, bool(b))); print(("OK   " if b else "FEHL ") + n + (f"  [{info}]" if info and not b else ""))

GESPERRT = {"Umbuchung", "Korrekturbuchung", "Anfangsbestand"}
HEUTE = date.today()

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(timezone_id="Europe/Berlin", viewport={"width": 1400, "height": 1000})
    page = ctx.new_page()
    fehler, dialoge = [], []
    page.on("console", lambda m: fehler.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: fehler.append(str(e)))
    antwort = {"ja": True}
    def dialog(d):
        dialoge.append(d.message)
        d.accept() if antwort["ja"] else d.dismiss()
    page.on("dialog", dialog)
    page.goto(BASIS); page.wait_for_timeout(1500)
    def gehe(ziel):
        page.click(f'.nav-eintrag[data-ziel="{ziel}"]'); page.wait_for_timeout(900)
    api = lambda pfad: page.request.get(BASIS + "api/" + pfad).json()
    def optionen(selektor, seite=None):
        texte = (seite or page).eval_on_selector_all(f"{selektor} option", "os => os.map(o => o.textContent)")
        return [o.strip().lstrip("— ").strip() for o in texte]

    # ─── Konten: Feld „Anfangsbestand“ ──────────────────────────────
    r = page.request.post(BASIS + "api/konten", data={"name": "UI-Neu", "typ": "Girokonto", "eroeffnungsdatum": "2026-03-01"})
    neu = r.json()["id"]
    gehe("konten")
    f = "#form-saldo-korrektur"
    page.select_option(f'{f} [name="konto_id"]', str(neu)); page.wait_for_timeout(600)
    pruef("Konto ohne Buchung: „Anfangsbestand“ sichtbar, angehakt, Datum = Eröffnung",
          page.is_visible("#sk-anfangsbestand-feld") and page.is_checked(f'{f} [name="anfangsbestand"]')
          and page.input_value(f'{f} [name="datum"]') == "2026-03-01")
    page.uncheck(f'{f} [name="anfangsbestand"]'); page.wait_for_timeout(200)
    pruef("Haken weg: Datum springt auf heute", page.input_value(f'{f} [name="datum"]') == HEUTE.isoformat())
    page.check(f'{f} [name="anfangsbestand"]')
    pruef("Datumsfeld lässt keine Zukunft zu (max = heute)",
          page.get_attribute(f'{f} [name="datum"]', "max") == HEUTE.isoformat())
    page.fill(f'{f} [name="saldo"]', "321.5")
    page.click(f'{f} button[type="submit"]'); page.wait_for_timeout(700)
    text = page.inner_text("#sk-vorschau-text")
    pruef("Vorschau nennt Saldo der App, Kontostand und Differenz als Anfangsbestand, noch nichts gebucht",
          page.is_visible("#sk-vorschau") and "321,50" in text and "„Anfangsbestand“" in text
          and api("konten?nur_aktive=false") and next(k for k in api("konten") if k["id"] == neu)["saldo"] == 0, text)
    page.screenshot(path=SHOTS + "vorschau.png")
    page.click("#sk-buchen"); page.wait_for_timeout(900)
    pruef("Buchen: Saldo 321,50 €, Meldung, Feld „Anfangsbestand“ danach weg",
          next(k for k in api("konten") if k["id"] == neu)["saldo"] == 321.5
          and "Anfangsbestand 321,50" in page.inner_text("#sk-meldung") and not page.is_visible("#sk-anfangsbestand-feld"),
          page.inner_text("#sk-meldung"))
    giro = next(k for k in api("konten") if k["name"] == "Girokonto")
    page.select_option(f'{f} [name="konto_id"]', str(giro["id"])); page.wait_for_timeout(600)
    pruef("Konto mit Buchungen, ohne Anfangsbestand: Feld sichtbar, nicht angehakt",
          page.is_visible("#sk-anfangsbestand-feld") and not page.is_checked(f'{f} [name="anfangsbestand"]'))
    page.fill(f'{f} [name="datum"]', HEUTE.isoformat())
    page.fill(f'{f} [name="saldo"]', str(giro["saldo"]))
    page.click(f'{f} button[type="submit"]'); page.wait_for_timeout(700)
    pruef("Differenz 0: Hinweis, kein Knopf „Korrektur buchen“",
          "nichts gebucht" in page.inner_text("#sk-vorschau-text") and not page.is_visible("#sk-buchen"),
          (page.inner_text("#sk-vorschau-text"), page.inner_text("#sk-meldung"), giro["saldo"]))
    page.fill(f'{f} [name="saldo"]', "1234.56"); page.wait_for_timeout(200)
    pruef("Eingabe ändern verwirft die Vorschau", not page.is_visible("#sk-vorschau"))
    page.evaluate(f"document.querySelector('{f} [name=\"datum\"]').removeAttribute('max')")
    page.fill(f'{f} [name="datum"]', (HEUTE + timedelta(days=3)).isoformat())
    page.click(f'{f} button[type="submit"]'); page.wait_for_timeout(700)
    pruef("Zukunftsdatum: Fehlermeldung des Servers, keine Vorschau",
          "Zukunft" in page.inner_text("#sk-meldung") and not page.is_visible("#sk-vorschau"), page.inner_text("#sk-meldung"))
    page.fill(f'{f} [name="datum"]', HEUTE.isoformat())
    page.fill(f'{f} [name="kommentar"]', "Auszug Nr. 7")
    page.click(f'{f} button[type="submit"]'); page.wait_for_timeout(700)
    pruef("Vorschau Korrekturbuchung mit Differenz", "„Korrekturbuchung“" in page.inner_text("#sk-vorschau-text"))
    page.click("#sk-buchen"); page.wait_for_timeout(900)
    pruef("Korrektur gebucht: Saldo 1.234,56 €", next(k for k in api("konten") if k["id"] == giro["id"])["saldo"] == 1234.56)

    # ─── Buchungsliste: kein „Ändern“, Löschen mit Saldofolge ───────
    gehe("buchungen")
    zeile = page.locator("#buchungen-tabelle tr", has_text="Auszug Nr. 7")
    andere = page.locator("#buchungen-tabelle tr", has_text="Lebensmittel").first
    pruef("Buchungsliste: Korrektur ohne „Ändern“, mit „Löschen“, andere Buchungen mit „Ändern“",
          zeile.count() == 1 and zeile.locator("button", has_text="Ändern").count() == 0
          and zeile.locator("button", has_text="Löschen").count() == 1
          and andere.locator("button", has_text="Ändern").count() == 1)
    page.click("#suche-umschalten"); page.wait_for_timeout(300)
    page.select_option("#s-kategorie", label="Korrekturbuchung"); page.click("#s-suchen"); page.wait_for_timeout(900)
    pruef("Suche nach Kategorie „Korrekturbuchung“ findet die Korrektur",
          page.locator("#buchungen-tabelle tr", has_text="Auszug Nr. 7").count() == 1)
    page.click("#s-zuruecksetzen"); page.wait_for_timeout(900)
    zeile = page.locator("#buchungen-tabelle tr", has_text="Auszug Nr. 7")
    betrag = next(b for b in api("buchungen") if (b.get("beschreibung") or "").endswith("Auszug Nr. 7"))["betrag"]
    antwort["ja"] = False; dialoge.clear()
    zeile.locator("button", has_text="Löschen").click(); page.wait_for_timeout(800)
    pruef("Rückfrage nennt Datum und Saldofolge, Abbrechen lässt die Korrektur stehen",
          dialoge and "Saldo-Korrektur löschen?" in dialoge[0]
          and f"Der Saldo ändert sich ab dem {HEUTE.strftime('%d.%m.%Y')} um" in dialoge[0]
          and zeile.count() == 1, dialoge)
    antwort["ja"] = True; dialoge.clear()
    zeile.locator("button", has_text="Löschen").click(); page.wait_for_timeout(1200)
    pruef("Bestätigen löscht, Saldo zurück", zeile.count() == 0
          and next(k for k in api("konten") if k["id"] == giro["id"])["saldo"] == round(1234.56 - betrag, 2))
    z_ab = page.locator("#buchungen-tabelle tr", has_text="Anfangsbestand 321,50")
    dialoge.clear(); antwort["ja"] = False
    z_ab.locator("button", has_text="Löschen").click(); page.wait_for_timeout(600)
    pruef("Anfangsbestand: Rückfrage „Anfangsbestand löschen?“ mit -321,50 €",
          dialoge and dialoge[0].startswith("Anfangsbestand löschen?") and "-321,50" in dialoge[0], dialoge)
    antwort["ja"] = True
    lm = next(b for b in api("buchungen") if b["typ"] == "Ist" and b["betrag"] < 0 and b.get("wiederkehrend_id") is None)
    # normale Buchung: Rückfrage wie bisher
    dialoge.clear(); antwort["ja"] = False
    page.evaluate(f"loescheBuchung({lm['id']})"); page.wait_for_timeout(600)
    pruef("Andere Buchung: Rückfrage unverändert", dialoge == ["Buchung wirklich löschen?"], dialoge)
    antwort["ja"] = True

    # ─── Auswahlfelder ohne gesperrte Kategorien ────────────────────
    gehe("buchungen")
    pruef("Neue Buchung: keine gesperrte Kategorie wählbar", not set(optionen('#form-buchung [name="kategorie_id"]')) & GESPERRT)
    pruef("Filter der Buchungsliste: alle drei wählbar", GESPERRT <= set(optionen("#s-kategorie")))
    for abschnitt, sel in (("wiederkehrend", '#form-wiederkehrend [name="kategorie_id"]'),
                           ("budgets", '#form-budget [name="kategorie_id"]'),
                           ("altersvorsorge", '#form-altersvorsorge [name="beitrag_kategorie_id"]'),
                           ("altersvorsorge", '#form-altersvorsorge [name="auszahlung_kategorie_id"]'),
                           ("admin", '#form-regel [name="kategorie_id"]')):
        gehe(abschnitt)
        pruef(f"{sel}: keine gesperrte Kategorie", not set(optionen(sel)) & GESPERRT, optionen(sel))
    ober = optionen('#form-kategorie [name="parent_id"]')
    pruef("Oberkategorie: ohne „Korrekturbuchung“ und „Anfangsbestand“, „Umbuchung“ bleibt",
          "Umbuchung" in ober and not {"Korrekturbuchung", "Anfangsbestand"} & set(ober), ober)
    pruef("Kategorien-Baum zeigt beide als „fest vorgegeben“",
          all(page.locator("#kategorien-baum div", has_text=n).filter(has_text="fest vorgegeben").count() >= 1
              for n in ("Korrekturbuchung", "Anfangsbestand")))

    # ─── Schnellbuchung direkt ──────────────────────────────────────
    sb = ctx.new_page()
    sb.on("console", lambda m: fehler.append("SB: " + m.text) if m.type == "error" else None)
    sb.goto(BASIS + "schnellbuchung"); sb.wait_for_timeout(1500)
    sb_opt = optionen("#sb-kategorie", sb)
    pruef("Schnellbuchung: keine gesperrte Kategorie", len(sb_opt) > 5 and not set(sb_opt) & GESPERRT, sb_opt)
    sb.close()

    # ─── Schnellbuchung eingebettet wie im Panel (Lehre aus #4) ─────
    panel = os.path.join(WURZEL, "custom_components", "finanzverwaltung", "frontend", "schnellbuchung-panel.js")
    ordner = tempfile.mkdtemp()
    shutil.copy(panel, os.path.join(ordner, "panel.js"))
    quelltext = open(panel, encoding="utf-8").read()
    element = (__import__("re").search(r'const ELEMENT = "([^"]+)"', quelltext)
               or __import__("re").search(r'customElements\.define\("([^"]+)"', quelltext)).group(1)
    open(os.path.join(ordner, "seite.html"), "w", encoding="utf-8").write(f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0"><div id="inhalt" style="height:100vh"></div><script type="module">
const S = {{ gueltig: new Set(), nr: 0 }};
const neu = () => {{ const s = "s" + (++S.nr); S.gueltig.add(s); return {{ session: s }}; }};
const callWS = async (m) => {{
  if (m.type === "supervisor/ingress/session") return neu();
  if (m.type === "supervisor/ingress/validate_session") return S.gueltig.has(m.session) ? null : Promise.reject({{code: "x"}});
  if (m.type === "supervisor/api" && m.endpoint === "/addons/e396af1a_finanzverwaltung/info")
    return {{ slug: "e396af1a_finanzverwaltung", state: "started", ingress_url: "{BASIS}" }};
  if (m.type === "supervisor/api" && m.endpoint === "/ingress/session") return neu();
  return Promise.reject({{ code: "unknown_command" }});
}};
await import("./panel.js");
const el = document.createElement("{element}");
el.panel = {{ url_path: "finanzen-schnellbuchung", config: {{ kennung: "e396af1a_finanzverwaltung", _panel_custom: {{}} }} }};
el.hass = {{ callWS }};
document.getElementById("inhalt").appendChild(el);
</script></body></html>""")
    class Leise(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("localhost", 0), functools.partial(Leise, directory=ordner))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    eb = ctx.new_page()
    eb.goto(f"http://localhost:{srv.server_address[1]}/seite.html"); eb.wait_for_timeout(3000)
    rahmen = next((fr for fr in eb.frames if "schnellbuchung" in fr.url), None)
    eb_opt = optionen("#sb-kategorie", rahmen) if rahmen else []
    pruef("Schnellbuchung eingebettet: Kategorien geladen, keine gesperrte", len(eb_opt) > 5 and not set(eb_opt) & GESPERRT,
          (eb_opt[:8], [fr.url for fr in eb.frames]))
    eb.screenshot(path=SHOTS + "eingebettet.png")
    srv.shutdown(); eb.close()

    # Die abgelehnte Vorschau mit Zukunftsdatum (422) meldet der Browser selbst
    erwartet = [x for x in fehler if "status of 422" in x]
    pruef("Keine Konsolenfehler außer der gewollten Ablehnung (422)",
          len(erwartet) == 1 and not [x for x in fehler if x not in erwartet], fehler[:5])
    br.close()

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

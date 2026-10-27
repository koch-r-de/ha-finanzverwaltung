"""Oberflächentest 2.6.4 (Playwright, Server auf 8935): Seitenleisten-Panel der
Schnellbuchung (ha-integration/finanzen-schnellbuchung.js), Bezug Issue #4.

Home Assistant gibt dem Behälter eines eigenen Panels keine feste Höhe. Bis
2.6.3 fiel das iframe deshalb auf 150 Pixel zurück, sichtbar war nur „Betrag“.
Der Test baut die Einbettung mit drei Behältern nach (ohne Höhe, mit voller
Höhe, mit Kopfleiste darüber) und ersetzt die Supervisor-Abfrage durch eine
Attrappe, die auf den laufenden Server zeigt.
Optionales Argument: Pfad einer anderen Panel-Datei (Gegenprobe)."""
import functools, http.server, os, shutil, sys, tempfile, threading
from playwright.sync_api import sync_playwright

BASIS = "http://localhost:8935/"
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = sys.argv[1] if len(sys.argv) > 1 else os.path.join(WURZEL, "ha-integration", "finanzen-schnellbuchung.js")
SHOTS = os.path.join(WURZEL, "tests", "ausgabe", "bilder", "ui264") + "/"
os.makedirs(SHOTS, exist_ok=True)
ERG = []
def pruef(n, b, info=""):
    ERG.append((n, bool(b))); print(("OK   " if b else "FEHL ") + n + (f"  [{info}]" if info and not b else ""))

LAYOUTS = {
    "ohne_hoehe": "html,body{margin:0} .rahmen{display:flex} .oben{display:none}",
    "volle_hoehe": "html,body{margin:0;height:100%} .rahmen{display:flex;height:100%} .oben{display:none}",
    "kopfleiste": "html,body{margin:0} .oben{height:56px;background:#03a9f4} .rahmen{display:flex}",
}
SEITE = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{background:#fafafa} .seitenleiste{width:256px;background:#eee} .inhalt{flex:1;min-width:0} %s</style></head>
<body><div class="oben"></div><div class="rahmen"><div class="seitenleiste"></div><div class="inhalt" id="inhalt"></div></div>
<script type="module">
import "./panel.js";
const el = document.createElement("finanzen-schnellbuchung-panel");
document.getElementById("inhalt").appendChild(el);
el.hass = { callWS: async (m) => m.endpoint === "/addons"
  ? { addons: [{ slug: "test_finanzverwaltung", state: "started" }] }
  : (m.endpoint.includes("test_finanzverwaltung") ? { ingress_url: "%s" } : Promise.reject(new Error("nicht installiert"))) };
</script></body></html>"""

ordner = tempfile.mkdtemp()
shutil.copy(PANEL, os.path.join(ordner, "panel.js"))
for name, css in LAYOUTS.items():
    open(os.path.join(ordner, name + ".html"), "w", encoding="utf-8").write(SEITE % (css, BASIS))
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ordner)
handler.log_message = lambda *a: None
server = http.server.ThreadingHTTPServer(("localhost", 0), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
PORT = server.server_address[1]

with sync_playwright() as p:
    br = p.chromium.launch()
    for geraet, vp in (("Desktop", {"width": 1000, "height": 700}), ("iPhone", {"width": 390, "height": 844})):
        for name in LAYOUTS:
            page = br.new_page(viewport=vp)
            fehler = []
            page.on("pageerror", lambda e: fehler.append(str(e)))
            page.goto(f"http://localhost:{PORT}/{name}.html"); page.wait_for_timeout(2500)
            rahmen = page.evaluate("""(() => { const f = document.querySelector('finanzen-schnellbuchung-panel')
                .shadowRoot.querySelector('iframe'); const r = f.getBoundingClientRect(); return [r.top, r.height]; })()""")
            oben = 56 if name == "kopfleiste" else 0
            erwartet = vp["height"] - oben
            rollt = page.evaluate("document.documentElement.scrollHeight > window.innerHeight + 1")
            pruef(f"{geraet}, Behälter {name}: Schnellbuchung füllt die Höhe bis zum unteren Rand",
                  abs(rahmen[1] - erwartet) <= 1 and abs(rahmen[0] - oben) <= 1, (rahmen, erwartet))
            pruef(f"{geraet}, Behälter {name}: äußere Seite scrollt nicht", not rollt)
            frame = page.frames[1] if len(page.frames) > 1 else None
            if frame:
                sichtbar = frame.evaluate("""['sb-betrag','sb-konto','sb-beschreibung','sb-kategorie','sb-typ','sb-datum-feld','sb-speichern']
                    .every(id => { const r = document.getElementById(id).getBoundingClientRect();
                                   return r.height > 0 && r.bottom <= window.innerHeight; })""")
                pruef(f"{geraet}, Behälter {name}: alle Felder und „Speichern“ ohne Scrollen sichtbar", sichtbar)
            else:
                pruef(f"{geraet}, Behälter {name}: Schnellbuchung geladen", False)
            if name == "ohne_hoehe":
                page.screenshot(path=SHOTS + f"{geraet}_{name}.png")
            pruef(f"{geraet}, Behälter {name}: keine JavaScript-Fehler", not fehler, fehler)
            page.close()
    # Fenstergröße ändern: Höhe zieht nach
    page = br.new_page(viewport={"width": 1000, "height": 700})
    page.goto(f"http://localhost:{PORT}/ohne_hoehe.html"); page.wait_for_timeout(2500)
    page.set_viewport_size({"width": 1000, "height": 900}); page.wait_for_timeout(500)
    h = page.evaluate("document.querySelector('finanzen-schnellbuchung-panel').shadowRoot.querySelector('iframe').getBoundingClientRect().height")
    pruef("Fenster vergrößert: Höhe zieht nach", abs(h - 900) <= 1, h)
server.shutdown()
shutil.rmtree(ordner, ignore_errors=True)

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

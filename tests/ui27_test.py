"""Oberflächentest 2.7 (Playwright, Server auf 8935): Panel der Integration
custom_components/finanzverwaltung, eingebettet wie in Home Assistant.

Die Seite baut den Behälter von Home Assistant nach (Eigenschaften panel und
hass vor dem Einhängen) und ersetzt die WebSocket-Aufrufe durch eine Attrappe
mit Adminrecht oder ohne, neuer oder alter Version von HA Core. Geprüft:
volle Höhe und alle Felder (Issue #4), Kennung aus der Integration ohne
Adminrecht (Befund S), Ingress-Sitzung mit Verlängerung, Neuanlage und
Rückfall (Befund T), Fehlertexte.
Optionales Argument: Pfad einer anderen Panel-Datei (Gegenprobe)."""
import functools, http.server, os, re, shutil, sys, tempfile, threading
from playwright.sync_api import sync_playwright

BASIS = "http://localhost:8935/"
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    WURZEL, "custom_components", "finanzverwaltung", "frontend", "schnellbuchung-panel.js")
QUELLE = open(PANEL, encoding="utf-8").read()
ELEMENT = (re.search(r'const ELEMENT = "([^"]+)"', QUELLE) or re.search(r'customElements\.define\("([^"]+)"', QUELLE)).group(1)
SHOTS = os.path.join(WURZEL, "tests", "ausgabe", "bilder", "ui27") + "/"
os.makedirs(SHOTS, exist_ok=True)
ERG = []
def pruef(n, b, info=""):
    ERG.append((n, bool(b))); print(("OK   " if b else "FEHL ") + n + (f"  [{info}]" if info and not b else ""))

LAYOUTS = {
    "ohne_hoehe": "html,body{margin:0} .rahmen{display:flex} .oben{display:none}",
    "kopfleiste": "html,body{margin:0} .oben{height:56px;background:#03a9f4} .rahmen{display:flex}",
}
# Attrappe: admin (Liste erlaubt), alt (nur supervisor/api), kennung (aus der Integration)
SEITE = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{background:#fafafa} .seitenleiste{width:256px;background:#eee} .inhalt{flex:1;min-width:0} %(css)s</style></head>
<body><div class="oben"></div><div class="rahmen"><div class="seitenleiste"></div><div class="inhalt" id="inhalt"></div></div>
<script type="module">
const p = new URLSearchParams(location.search);
const admin = p.get("admin") !== "0", alt = p.get("alt") === "1", kennung = p.get("kennung") || null;
const S = window.stub = { aufrufe: [], gueltig: new Set(), nr: 0 };
const fehler = (code, message) => Promise.reject({ code, message });
const neueSitzung = () => { const s = "s" + (++S.nr); S.gueltig.add(s); return { session: s }; };
const callWS = async (m) => {
  S.aufrufe.push(m.type + " " + (m.endpoint || m.session || m.slug || ""));
  if (m.type === "supervisor/ingress/session") return alt ? fehler("unknown_command", "Unknown command.") : neueSitzung();
  if (m.type === "supervisor/ingress/validate_session") {
    if (alt) return fehler("unknown_command", "Unknown command.");
    return S.gueltig.has(m.session) ? null : fehler("unknown_error", "Session not valid");
  }
  if (m.type !== "supervisor/api") return fehler("unknown_command", "Unknown command.");
  if (m.endpoint === "/ingress/session") return neueSitzung();
  if (m.endpoint === "/ingress/validate_session")
    return S.gueltig.has(m.data && m.data.session) ? null : fehler("unknown_error", "Session not valid");
  if (m.endpoint === "/addons") return admin ? { addons: [{ slug: "e396af1a_finanzverwaltung", state: "started" }] }
                                             : fehler("unauthorized", "Unauthorized");
  if (m.endpoint === "/addons/e396af1a_finanzverwaltung/info")
    return { slug: "e396af1a_finanzverwaltung", state: "started", ingress_url: "%(basis)s" };
  return fehler("unknown_error", "App is not installed");
};
await import("./panel.js");
window.einhaengen = () => {
  const el = document.createElement("%(element)s");
  el.panel = { url_path: "finanzen-schnellbuchung", config: { kennung, _panel_custom: {} } };
  el.hass = { callWS };
  document.getElementById("inhalt").appendChild(el);
  return el;
};
window.el = window.einhaengen();
</script></body></html>"""

ordner = tempfile.mkdtemp()
shutil.copy(PANEL, os.path.join(ordner, "panel.js"))
for name, css in LAYOUTS.items():
    open(os.path.join(ordner, name + ".html"), "w", encoding="utf-8").write(
        SEITE % {"css": css, "basis": BASIS, "element": ELEMENT})
class Leise(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass
handler = functools.partial(Leise, directory=ordner)
server = http.server.ThreadingHTTPServer(("localhost", 0), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
ADRESSE = f"http://localhost:{server.server_address[1]}/"
KENNUNG = "kennung=e396af1a_finanzverwaltung"

def iframe_hoehe(page):
    return page.evaluate("""(() => { const f = window.el.shadowRoot.querySelector('iframe');
        if (!f) return null; const r = f.getBoundingClientRect(); return [r.top, r.height]; })()""")

def text(page):
    return page.evaluate("window.el.shadowRoot.textContent")

def aufrufe(page, art=""):
    return [a for a in page.evaluate("window.stub.aufrufe") if art in a]

def sitzungs_cookie(ctx):
    return [(c["value"], c["path"]) for c in ctx.cookies() if c["name"] == "ingress_session"]

with sync_playwright() as p:
    br = p.chromium.launch()

    # Issue #4: volle Höhe, alle Felder, ohne Adminrecht mit Kennung
    for geraet, vp in (("Desktop", {"width": 1000, "height": 700}), ("iPhone", {"width": 390, "height": 844})):
        for name in LAYOUTS:
            page = br.new_page(viewport=vp)
            fehler = []
            page.on("pageerror", lambda e: fehler.append(str(e)))
            page.goto(f"{ADRESSE}{name}.html?admin=0&{KENNUNG}"); page.wait_for_timeout(2500)
            oben = 56 if name == "kopfleiste" else 0
            r = iframe_hoehe(page)
            pruef(f"{geraet}, {name}: Schnellbuchung füllt die Höhe bis zum unteren Rand",
                  r and abs(r[1] - (vp["height"] - oben)) <= 1 and abs(r[0] - oben) <= 1, r)
            frame = page.frames[1] if len(page.frames) > 1 else None
            sichtbar = frame and frame.evaluate("""['sb-betrag','sb-konto','sb-beschreibung','sb-kategorie','sb-typ','sb-datum-feld','sb-speichern']
                .every(id => { const r = document.getElementById(id).getBoundingClientRect();
                               return r.height > 0 && r.bottom <= window.innerHeight; })""")
            pruef(f"{geraet}, {name}: alle Felder und „Speichern“ ohne Scrollen sichtbar", sichtbar)
            if name == "ohne_hoehe":
                page.screenshot(path=SHOTS + f"{geraet}.png")
            pruef(f"{geraet}, {name}: keine JavaScript-Fehler", not fehler, fehler)
            page.close()

    # Befund S: ohne Adminrecht
    ctx = br.new_context(); page = ctx.new_page()
    page.goto(f"{ADRESSE}ohne_hoehe.html?admin=0&{KENNUNG}"); page.wait_for_timeout(1500)
    pruef("Befund S: ohne Adminrecht lädt die Schnellbuchung mit der Kennung aus der Integration",
          iframe_hoehe(page) is not None and not aufrufe(page, "/addons "), aufrufe(page))
    ctx.close()
    ctx = br.new_context(); page = ctx.new_page()
    page.goto(f"{ADRESSE}ohne_hoehe.html?admin=0"); page.wait_for_timeout(1500)
    pruef("Ohne Kennung und ohne Adminrecht: verständliche Fehlermeldung mit Hinweis auf Neustart",
          iframe_hoehe(page) is None and "konnte nicht geladen werden" in text(page) and "neu" in text(page), text(page))
    ctx.close()
    ctx = br.new_context(); page = ctx.new_page()
    page.goto(f"{ADRESSE}ohne_hoehe.html?admin=1"); page.wait_for_timeout(1500)
    pruef("Ohne Kennung mit Adminrecht: Rückfall über die Add-on-Liste findet das Add-on", iframe_hoehe(page) is not None)
    ctx.close()

    # Befund T: Ingress-Sitzung
    ctx = br.new_context(); page = ctx.new_page()
    fehler = []
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.clock.install()
    page.goto(f"{ADRESSE}ohne_hoehe.html?admin=1&{KENNUNG}"); page.wait_for_timeout(1500)
    pruef("Befund T: beim Öffnen wird eine Ingress-Sitzung angelegt und als Cookie für /api/hassio_ingress/ gesetzt",
          aufrufe(page, "ingress/session") == ["supervisor/ingress/session e396af1a_finanzverwaltung"]
          and sitzungs_cookie(ctx) == [("s1", "/api/hassio_ingress/")], (aufrufe(page), sitzungs_cookie(ctx)))
    page.clock.run_for(61000); page.wait_for_timeout(200)
    pruef("Befund T: nach einer Minute wird die Sitzung verlängert",
          aufrufe(page, "validate_session") == ["supervisor/ingress/validate_session s1"], aufrufe(page))
    page.evaluate("window.stub.gueltig.clear()")
    page.clock.run_for(60000); page.wait_for_timeout(200)
    pruef("Befund T: abgelaufene Sitzung wird durch eine neue ersetzt, Cookie zieht nach",
          len(aufrufe(page, "ingress/session")) == 2 and sitzungs_cookie(ctx) == [("s2", "/api/hassio_ingress/")],
          (aufrufe(page), sitzungs_cookie(ctx)))
    page.evaluate("""Object.defineProperty(document, 'visibilityState', {value: 'visible', configurable: true});
                     document.dispatchEvent(new Event('visibilitychange'))"""); page.wait_for_timeout(200)
    pruef("Befund T: beim Zurückholen der App wird die Sitzung sofort geprüft",
          aufrufe(page, "validate_session")[-1:] == ["supervisor/ingress/validate_session s2"], aufrufe(page))
    page.evaluate("window.el.remove()")
    vorher = len(aufrufe(page))
    page.clock.run_for(180000); page.wait_for_timeout(200)
    pruef("Befund T: nach dem Verlassen des Panels keine weiteren Aufrufe", len(aufrufe(page)) == vorher, aufrufe(page))
    page.evaluate("document.getElementById('inhalt').appendChild(window.el)"); page.wait_for_timeout(300)
    pruef("Befund T: beim Zurückkehren wird sofort eine neue Sitzung angelegt",
          len(aufrufe(page, "ingress/session")) == 3 and sitzungs_cookie(ctx) == [("s3", "/api/hassio_ingress/")],
          (aufrufe(page), sitzungs_cookie(ctx)))
    pruef("Befund T: keine JavaScript-Fehler", not fehler, fehler)
    ctx.close()

    ctx = br.new_context(); page = ctx.new_page()
    page.goto(f"{ADRESSE}ohne_hoehe.html?admin=1&alt=1&{KENNUNG}"); page.wait_for_timeout(1500)
    pruef("Ältere Version von HA Core: Sitzung über supervisor/api, Schnellbuchung lädt",
          "supervisor/api /ingress/session" in aufrufe(page) and sitzungs_cookie(ctx) == [("s1", "/api/hassio_ingress/")]
          and iframe_hoehe(page) is not None, aufrufe(page))
    ctx.close()

    # Fenstergröße ändern: Höhe zieht nach
    page = br.new_page(viewport={"width": 1000, "height": 700})
    page.goto(f"{ADRESSE}ohne_hoehe.html?admin=0&{KENNUNG}"); page.wait_for_timeout(2000)
    page.set_viewport_size({"width": 1000, "height": 900}); page.wait_for_timeout(500)
    r = iframe_hoehe(page)
    pruef("Fenster vergrößert: Höhe zieht nach", r and abs(r[1] - 900) <= 1, r)
server.shutdown()
shutil.rmtree(ordner, ignore_errors=True)

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

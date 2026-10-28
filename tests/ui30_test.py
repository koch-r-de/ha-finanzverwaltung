"""Oberflächentest 3.0 (Playwright): Sperre und Verschlüsselung (Issue #5).

Aufruf: python3 tests/ui30_test.py <code> <datenordner>
Startet den Server selbst (Port 8935, herkunft_pruefen = sperren), weil die
Reihe Neustarts mit verschlüsselter Datenbank braucht. Die Ingress-Header
X-Remote-User-* setzt Playwright für jeden Kontext, so wie sie der Supervisor
setzen würde.

Abläufe: ohne Schutz wie bisher, Verschlüsselung einschalten mit Download,
Schlüssel und Phrase, geschützter Download und Export, Neustart mit
Passphrase, Schnellbuchung bei verschlossener Datenbank (vorgemerkt),
Klärliste, Sperre einschalten, Sperrbildschirm mit PIN, Fehlversuch,
automatische Sperre, zweiter Benutzer mit Muster, Schnellbuchung ohne Code,
iPhone-Ansicht, Ausschalten. Konsolenfehler werden gesammelt.
"""
import json, os, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright

code, ordner = (os.path.abspath(x) for x in sys.argv[1:3])
PORT = 8935
BASIS = f"http://localhost:{PORT}/"
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ausgabe", "bilder", "ui30") + "/"
os.makedirs(SHOTS, exist_ok=True)
DOWNLOADS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ausgabe", "ui30_downloads")
os.makedirs(DOWNLOADS, exist_ok=True)
ERG = []
def pruef(n, b, info=""):
    ERG.append((n, bool(b))); print(("OK   " if b else "FEHL ") + n + (f"  [{info}]" if info and not b else ""), flush=True)

A = {"X-Remote-User-Id": "id-ralf", "X-Remote-User-Name": "ralf", "X-Remote-User-Display-Name": "Ralf",
     "X-Remote-User-Groups": "system-admin,system-users"}
B = {"X-Remote-User-Id": "id-anna", "X-Remote-User-Name": "anna", "X-Remote-User-Display-Name": "Anna",
     "X-Remote-User-Groups": "system-users"}
PASS = "Unser Haus hat sieben Fenster 2026"
SERVER = [None]


def starten():
    env = {**os.environ, "FINANZAPP_DATENVERZEICHNIS": ordner, "FINANZAPP_PORT": str(PORT),
           "FINANZAPP_HERKUNFT_PRUEFEN": "sperren"}
    SERVER[0] = subprocess.Popen([sys.executable, "run.py"], cwd=code, env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            urllib.request.urlopen(BASIS + "api/schutz/status", timeout=1)
            return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("Server startet nicht")


def stoppen():
    if SERVER[0]:
        SERVER[0].terminate(); SERVER[0].wait(timeout=30); SERVER[0] = None


def neu_starten():
    stoppen(); starten()


def waehle(pg, selektor, text):
    """Option wählen, deren Text auf text endet (Unterkategorien haben „— “ davor)."""
    wert = pg.evaluate("([s, t]) => [...document.querySelector(s).options].find(o => o.textContent.trim().endsWith(t)).value",
                       [selektor, text])
    pg.select_option(selektor, wert)


def status(kopf=None):
    anfrage = urllib.request.Request(BASIS + "api/schutz/status", headers=kopf or {})
    return json.load(urllib.request.urlopen(anfrage))


starten()
try:
    with sync_playwright() as p:
        br = p.chromium.launch(env={**os.environ, "LANG": "de_DE.UTF-8", "LANGUAGE": "de"})
        fehler = []

        def kontext(kopf, **weitere):
            ctx = br.new_context(timezone_id="Europe/Berlin", locale="de-DE", accept_downloads=True,
                                 extra_http_headers=kopf, **({"viewport": {"width": 1400, "height": 1000}} | weitere))
            return ctx

        def seite(ctx):
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: fehler.append(str(e)))
            # Abgewiesene Anfragen meldet Chrome als „Failed to load resource“. Erwartet sind
            # 401/403/409/422/423/429 (Sperre, falsche Eingaben), alles andere ist ein Fehler.
            erwartet = ("401", "403", "409", "422", "423", "429")
            pg.on("console", lambda m: fehler.append(m.text) if m.type == "error" and not (
                m.text.startswith("Failed to load resource") and any(f"status of {c}" in m.text for c in erwartet)) else None)
            return pg

        ctx_a = kontext(A)
        page = seite(ctx_a)

        def gehe(ziel):
            page.click(f'.nav-eintrag[data-ziel="{ziel}"]'); page.wait_for_timeout(700)

        def sicherheit():
            gehe("admin")
            page.click('[data-admin-tab="sicherheit"]'); page.wait_for_timeout(500)
            page.evaluate("document.querySelectorAll('[data-admin-tab-inhalt=sicherheit] details').forEach(d => d.open = true)")
            page.wait_for_timeout(300)

        # ─── 1. Ohne Schutz wie bisher ─────────────────────────────────
        page.goto(BASIS); page.wait_for_timeout(1500)
        pruef("1 Ohne Schutz: Übersicht ohne Sperrbildschirm",
              page.is_visible("#abschnitt-start") and not page.is_visible("#schutz-schirm"))
        sicherheit()
        pruef("1 Reiter „Sicherheit“ mit Sperre und Verschlüsselung, beides ausgeschaltet, Klärliste verborgen",
              "ausgeschaltet" in page.inner_text("#sperre-inhalt") and "ausgeschaltet" in page.inner_text("#verschluesselung-inhalt")
              and not page.is_visible("#klaerliste-block"))
        pruef("1 Hinweistexte aus der Hilfe gefüllt",
              "Code" in page.inner_text('#sperre-block [data-hinweis="sicherheit.sperre"]')
              and "Passphrase" in page.inner_text('#verschluesselung-block [data-hinweis="sicherheit.verschluesselung"]'))
        page.screenshot(path=SHOTS + "01_sicherheit_aus.png", full_page=True)

        # ─── 2. Verschlüsselung einschalten ────────────────────────────
        page.fill('#form-vs-ein [name="passphrase"]', PASS)
        page.fill('#form-vs-ein [name="wiederholung"]', PASS)
        page.click('#form-vs-ein button[type="submit"]'); page.wait_for_timeout(600)
        pruef("2 Ohne vorherigen Download: Hinweis, kein Dialog",
              "herunterladen" in page.inner_text("#vs-fehler") and not page.is_visible("#schutz-dialog"))
        with page.expect_download() as d:
            page.click("#vs-download")
        dl = d.value
        pfad = os.path.join(DOWNLOADS, dl.suggested_filename); dl.save_as(pfad)
        pruef("2 Download unverschlüsselt (SQLite), Status „erledigt“",
              open(pfad, "rb").read(16) == b"SQLite format 3\x00" and "erledigt" in page.inner_text("#vs-download-status"))
        page.click('#form-vs-ein button[type="submit"]'); page.wait_for_timeout(1000)
        pruef("2 Dialog mit Wiederherstellungsschlüssel und Phrase", page.is_visible("#schutz-schluessel"))
        wh = page.inner_text("#schutz-schluessel").strip()
        phrase = page.inner_text("#schutz-dialog .reset-phrase").strip()
        page.screenshot(path=SHOTS + "02_schluessel.png")
        page.fill('#schutz-bestaetigen-form [name="getippt"]', "FALSCH")
        page.fill('#schutz-bestaetigen-form [name="phrase"]', phrase)
        page.click("#schutz-bestaetigen-los"); page.wait_for_timeout(800)
        pruef("2 Falsch abgetippt: Fehlermeldung, nicht verschlüsselt",
              "stimmt nicht" in page.inner_text("#schutz-bestaetigen-fehler") and not status()["verschluesselung"]["aktiv"])
        page.fill('#schutz-bestaetigen-form [name="getippt"]', wh)
        page.click("#schutz-bestaetigen-los"); page.wait_for_timeout(3000)
        text = page.inner_text("#schutz-dialog")
        pruef("2 Verschlüsselt: Schritte im Dialog", "Verschlüsselt" in text and "Backup erstellt" in text, text[:300])
        page.click("#schutz-dialog [data-schliessen]"); page.wait_for_timeout(500)
        pruef("2 Block zeigt „eingeschaltet“ und „Passphrase ändern“",
              "eingeschaltet" in page.inner_text("#verschluesselung-inhalt") and page.is_visible("#form-vs-pp"))

        # ─── 3. Geschützter Download und Export ────────────────────────
        page.click('[data-admin-tab="system"]'); page.wait_for_timeout(300)
        page.evaluate("document.querySelectorAll('[data-admin-tab-inhalt=system] details').forEach(d => d.open = true)")
        page.click("#db-herunterladen"); page.wait_for_timeout(500)
        pruef("3 Datenbank herunterladen: Auswahl verschlüsselt/unverschlüsselt", page.is_visible("#schutz-dl-form"))
        with page.expect_download() as d:
            page.click('#schutz-dl-form button[type="submit"]')
        pfad = os.path.join(DOWNLOADS, d.value.suggested_filename); d.value.save_as(pfad)
        pruef("3 Verschlüsselte Datei .fvdb", pfad.endswith(".fvdb") and open(pfad, "rb").read(6) == b"FVDB1\n", pfad)
        page.click('[data-admin-tab="stammdaten"]'); page.wait_for_timeout(300)
        page.evaluate("document.querySelectorAll('[data-admin-tab-inhalt=stammdaten] details').forEach(d => d.open = true)")
        page.click("#export-herunterladen"); page.wait_for_timeout(500)
        page.fill('#schutz-dl-form [name="kennwort"]', "kurz"); page.fill('#schutz-dl-form [name="wiederholung"]', "kurz")
        page.click('#schutz-dl-form button[type="submit"]'); page.wait_for_timeout(600)
        pruef("3 Export: zu kurzes Excel-Kennwort abgewiesen", "mindestens" in page.inner_text("#schutz-dl-fehler"))
        page.fill('#schutz-dl-form [name="kennwort"]', "Excel Kennwort mit Länge")
        page.fill('#schutz-dl-form [name="wiederholung"]', "Excel Kennwort mit Länge")
        with page.expect_download() as d:
            page.click('#schutz-dl-form button[type="submit"]')
        pfad = os.path.join(DOWNLOADS, d.value.suggested_filename); d.value.save_as(pfad)
        pruef("3 Export mit Kennwort: geschützte xlsx", pfad.endswith(".xlsx") and open(pfad, "rb").read(4) == b"\xd0\xcf\x11\xe0")
        page.screenshot(path=SHOTS + "03_export.png")

        # ─── 4. Neustart: Passphrase, Schnellbuchung vorgemerkt ────────
        neu_starten()
        sb = seite(ctx_a)
        sb.goto(BASIS + "schnellbuchung"); sb.wait_for_timeout(1500)
        pruef("4 Schnellbuchung bei verschlossener Datenbank: Hinweis, keine letzten Buchungen, kein Sperrbildschirm",
              "vorgemerkt" in sb.inner_text("#sb-modus") and not sb.is_visible("#sb-letzte") and not sb.is_visible("#schutz-schirm"))
        sb.fill("#sb-betrag", "7,80"); sb.fill("#sb-beschreibung", "UI30 Vorgemerkt")
        waehle(sb, "#sb-kategorie", "Lebensmittel/Verpflegung")
        sb.click("#sb-speichern"); sb.wait_for_timeout(800)
        pruef("4 Schnellbuchung: „Vorgemerkt“", "Vorgemerkt" in sb.inner_text("#sb-meldung"), sb.inner_text("#sb-meldung"))
        sb.screenshot(path=SHOTS + "04_schnellbuchung_vorgemerkt.png")
        urllib.request.urlopen(urllib.request.Request(BASIS + "api/siri/buchung", data=json.dumps(
            {"betrag": 3, "konto": "Giro", "kategorie": "Lebensmittel/Verpflegung", "beschreibung": "UI30 Mehrdeutig"}).encode(),
            headers={"Content-Type": "application/json"}))
        page.goto(BASIS); page.wait_for_timeout(1500)
        pruef("4 Hauptseite: Sperrbildschirm „Datenbank entsperren“, Inhalt verborgen",
              page.is_visible("#schutz-schirm") and "Datenbank entsperren" in page.inner_text("#schutz-karte")
              and not page.is_visible("#start-gesamtsaldo"))
        page.screenshot(path=SHOTS + "05_passphrase.png")
        page.fill('#schutz-pp-form [name="geheimnis"]', "falsche Passphrase hier")
        page.click('#schutz-pp-form button[type="submit"]'); page.wait_for_timeout(1500)
        pruef("4 Falsche Passphrase: Meldung, bleibt gesperrt", "stimmt nicht" in page.inner_text("#schutz-karte"))
        page.fill('#schutz-pp-form [name="geheimnis"]', PASS)
        page.click('#schutz-pp-form button[type="submit"]'); page.wait_for_timeout(2500)
        pruef("4 Richtige Passphrase: Übersicht, Fußzeile meldet gebuchte und geklärte Stapel-Einträge",
              not page.is_visible("#schutz-schirm") and page.is_visible("#start-gesamtsaldo")
              and "1 vorgemerkte Buchung(en) gebucht" in page.inner_text("#fuss-status")
              and "1 in der Klärliste" in page.inner_text("#fuss-status"), page.inner_text("#fuss-status"))

        # ─── 5. Klärliste ──────────────────────────────────────────────
        sicherheit()
        pruef("5 Klärliste sichtbar mit Grund", page.is_visible("#klaerliste-block") and "mehrdeutig" in page.inner_text("#klaerliste-inhalt"))
        page.click("[data-klaer-buchen]"); page.wait_for_timeout(600)
        page.select_option('#form-klaer [name="konto_id"]', label="Girokonto")
        page.click('#form-klaer button[type="submit"]'); page.wait_for_timeout(800)
        pruef("5 Klärliste buchen: Kategorie aus der Angabe vorbelegt, gebucht, Liste leer",
              "Keine offenen Einträge" in page.inner_text("#klaerliste-inhalt"), page.inner_text("#klaerliste-inhalt")[:200])

        # ─── 6. Sperre einschalten ─────────────────────────────────────
        page.select_option('#form-sperre-ein [name="art"]', "pin")
        page.fill('#form-sperre-ein [name="code"]', "13579")
        page.fill('#form-sperre-ein [name="wiederholung"]', "13579")
        page.click('#form-sperre-ein button[type="submit"]'); page.wait_for_timeout(600)
        pruef("6 PIN zu kurz: Fehlermeldung", "mindestens 6" in page.inner_text("#sperre-fehler"))
        page.fill('#form-sperre-ein [name="code"]', "135790")
        page.fill('#form-sperre-ein [name="wiederholung"]', "135790")
        page.fill('#form-sperre-ein [name="auto_minuten"]', "1")
        page.click('#form-sperre-ein button[type="submit"]'); page.wait_for_timeout(800)
        whs = page.inner_text("#schutz-schluessel").strip()
        page.fill('#schutz-bestaetigen-form [name="getippt"]', whs)
        page.click("#schutz-bestaetigen-los"); page.wait_for_timeout(800)
        pruef("6 Sperre eingeschaltet, Freigabeliste mit dir", "eingeschaltet" in page.inner_text("#sperre-inhalt")
              and "Ralf (du)" in page.inner_text("#sperre-benutzer") and not page.is_visible("#schutz-schirm"))
        page.screenshot(path=SHOTS + "06_sperre_an.png", full_page=True)

        # ─── 7. Sperrbildschirm ────────────────────────────────────────
        page.reload(); page.wait_for_timeout(1500)
        pruef("7 Neu laden: Sitzung im Tab bleibt (sessionStorage)", not page.is_visible("#schutz-schirm"))
        ctx_a2 = kontext(A)
        page = seite(ctx_a2)
        page.goto(BASIS); page.wait_for_timeout(1500)
        pruef("7 Neuer Tab: „Gesperrt“ mit PIN-Feld", page.is_visible("#schutz-code-form") and "Gesperrt" in page.inner_text("#schutz-karte"))
        page.screenshot(path=SHOTS + "07_gesperrt.png")
        page.fill('#schutz-code-form [name="code"]', "000000"); page.click('#schutz-code-form button[type="submit"]'); page.wait_for_timeout(800)
        pruef("7 Falscher Code: „Falscher Code.“", "Falscher Code" in page.inner_text("#schutz-karte"))
        page.fill('#schutz-code-form [name="code"]', "135790"); page.click('#schutz-code-form button[type="submit"]'); page.wait_for_timeout(1500)
        pruef("7 Richtiger Code: Übersicht", not page.is_visible("#schutz-schirm") and page.is_visible("#start-gesamtsaldo"))

        # ─── 8. Automatische Sperre (1 Minute, vorgespult) ────────────
        page.evaluate("SCHUTZ.letzte = Date.now() - 61000")
        page.wait_for_timeout(5600)
        pruef("8 Nach 1 Minute ohne Tätigkeit: Sperrbildschirm, Server-Sitzung beendet",
              page.is_visible("#schutz-code-form") and page.evaluate("SCHUTZ.sitzung") is None)
        page.fill('#schutz-code-form [name="code"]', "135790"); page.click('#schutz-code-form button[type="submit"]'); page.wait_for_timeout(1200)
        sicherheit()
        page.check('#form-sperre-einst [name="auto_hintergrund"]')
        page.fill('#form-sperre-einst [name="auto_minuten"]', "5")
        page.click('#form-sperre-einst button[type="submit"]'); page.wait_for_timeout(800)
        page.evaluate("""Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
                         document.dispatchEvent(new Event('visibilitychange'))""")
        page.wait_for_timeout(1000)
        pruef("8 Mit „auch im Hintergrund“: Tab verlassen sperrt sofort", page.is_visible("#schutz-code-form"))
        page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false})")
        page.fill('#schutz-code-form [name="code"]', "135790"); page.click('#schutz-code-form button[type="submit"]'); page.wait_for_timeout(1200)

        # ─── 9. Zweiter Benutzer mit Muster ────────────────────────────
        ctx_b = kontext(B)
        pb = seite(ctx_b)
        pb.goto(BASIS); pb.wait_for_timeout(1500)
        pruef("9 Anna (nicht freigegeben): „Kein Zugang“", "Kein Zugang" in pb.inner_text("#schutz-karte"))
        sicherheit()
        page.select_option("#sperre-bekannt", label="Anna")
        page.click("#sperre-hinzu"); page.wait_for_timeout(800)
        pruef("9 Admin gibt Anna frei", "Anna" in page.inner_text("#sperre-benutzer"))
        pb.click("#schutz-neu"); pb.wait_for_timeout(1200)
        pruef("9 Anna: „Eigenen Code festlegen“", "Eigenen Code festlegen" in pb.inner_text("#schutz-karte"))
        pb.select_option('#schutz-erst-form [name="art"]', "muster"); pb.wait_for_timeout(300)
        def muster(name, punkte):
            for n in punkte:
                pb.click(f'#schutz-erst-form [data-muster="{name}"] [data-punkt="{n}"]')
        muster("code", [1, 5, 9, 6, 3]); muster("wiederholung", [1, 5, 9, 6, 3])
        pb.screenshot(path=SHOTS + "09_muster.png")
        pb.click('#schutz-erst-form button[type="submit"]'); pb.wait_for_timeout(1500)
        pruef("9 Anna hat ihr Muster festgelegt und sieht die Übersicht", not pb.is_visible("#schutz-schirm") and pb.is_visible("#start-gesamtsaldo"))
        pb.evaluate("schutzSperren()"); pb.wait_for_timeout(1000)
        for n in [1, 5, 9, 6, 3]:
            pb.click(f'#schutz-code-form [data-punkt="{n}"]')
        pb.click('#schutz-code-form button[type="submit"]'); pb.wait_for_timeout(1500)
        pruef("9 Anna entsperrt mit dem Muster", not pb.is_visible("#schutz-schirm"))
        pb.click('.nav-eintrag[data-ziel="admin"]'); pb.wait_for_timeout(500)
        pb.click('[data-admin-tab="sicherheit"]'); pb.wait_for_timeout(800)
        pruef("9 Anna sieht keine Einstellungen und keinen Ausschalter",
              pb.locator("#form-sperre-einst").count() == 0 and pb.locator("#form-sperre-aus").count() == 0
              and pb.locator("#form-sperre-code").count() == 1)

        # ─── 10. Schnellbuchung ohne Code (iPhone) ─────────────────────
        ctx_bi = kontext(B, **p.devices["iPhone 13"])
        si = seite(ctx_bi)
        si.goto(BASIS + "schnellbuchung"); si.wait_for_timeout(1500)
        pruef("10 Schnellbuchung ohne Code: „nur erfasst“, keine letzten Buchungen",
              not si.is_visible("#schutz-schirm") and "Ohne Code" in si.inner_text("#sb-modus") and not si.is_visible("#sb-letzte"))
        si.fill("#sb-betrag", "2,50"); si.fill("#sb-beschreibung", "UI30 Ohne Code")
        waehle(si, "#sb-kategorie", "Lebensmittel/Verpflegung")
        si.click("#sb-speichern"); si.wait_for_timeout(800)
        pruef("10 Gebucht ohne Code", "Gebucht" in si.inner_text("#sb-meldung"), si.inner_text("#sb-meldung"))
        pruef("10 Kein waagrechtes Scrollen auf dem iPhone", si.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
        si.screenshot(path=SHOTS + "10_schnellbuchung_ohne_code.png")
        ctx_ai = kontext(A, **p.devices["iPhone 13"])
        sp = seite(ctx_ai)
        sp.goto(BASIS); sp.wait_for_timeout(1500)
        pruef("10 Sperrbildschirm auf dem iPhone ohne waagrechtes Scrollen",
              sp.is_visible("#schutz-code-form") and sp.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
        sp.screenshot(path=SHOTS + "11_iphone_gesperrt.png")

        # ─── 11. Ausschalten ───────────────────────────────────────────
        sicherheit()
        page.fill('#form-sperre-aus [name="code"]', "135790")
        page.click('#form-sperre-aus button[type="submit"]'); page.wait_for_timeout(1200)
        pruef("11 Sperre ausgeschaltet", "ausgeschaltet" in page.inner_text("#sperre-inhalt") and not status(A)["sperre"]["aktiv"])
        page.click("#vs-aus"); page.wait_for_timeout(600)
        phrase = page.inner_text("#schutz-dialog .reset-phrase").strip()
        page.fill('#form-vs-aus [name="geheimnis"]', PASS)
        page.fill('#form-vs-aus [name="phrase"]', phrase)
        page.click('#form-vs-aus button[type="submit"]'); page.wait_for_timeout(3000)
        pruef("11 Verschlüsselung ausgeschaltet, Schritte im Dialog",
              "Ausgeschaltet" in page.inner_text("#schutz-dialog") and not status()["verschluesselung"]["aktiv"])
        page.click("#vs-aus-ergebnis [data-schliessen]")
        neu_starten()
        page.goto(BASIS); page.wait_for_timeout(1500)
        pruef("11 Nach Neustart ohne Schutz: Übersicht direkt", not page.is_visible("#schutz-schirm") and page.is_visible("#start-gesamtsaldo"))
        pruef("Keine Konsolenfehler", not fehler, fehler[:5])
finally:
    stoppen()

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

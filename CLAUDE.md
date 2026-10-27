# CLAUDE.md

Hinweise für Claude Code (und Menschen) zur Arbeit an diesem Repository.
Sprache des Projekts ist Deutsch: Oberfläche, Hilfe, Dokumentation, Kommentare
und auch die Bezeichner im Code (`buchungen`, `saldo_verlauf`, `kategorie_ids`).
Neue Namen bitte ebenso deutsch wählen.

## Was das ist

Ein Haushaltsbuch als Home-Assistant-Add-on. Das Add-on liegt in
`finanzverwaltung/`, Home Assistant baut daraus ein Docker-Image
(`finanzverwaltung/Dockerfile`, Alpine mit Python 3.12) und zeigt die
Oberfläche per Ingress in der Seitenleiste. Alle Daten liegen in einer
SQLite-Datei unter `/data` im Container. Es gibt keine Cloud-Anbindung und
soll auch keine geben.

| Teil | Technik |
| --- | --- |
| Backend | FastAPI, eine Datei `app/main.py` mit allen Endpunkten unter `/api/...` |
| Fachlogik | `app/core/*.py`, je Bereich ein Modul (siehe unten) |
| Datenbank | SQLite, Schema in `app/schema.sql`, Migrationen in `app/core/db.py` |
| Frontend | `app/static/index.html`, `app.js`, `style.css`: Vanilla JS ohne Build-Kette, Chart.js 4 mitgeliefert |
| Hilfe | `app/hilfe/hilfe.md` (Markdown, eine Datei), daraus Hilfe-Ansicht, Hinweistexte und PDF-Handbuch |
| Tests | `tests/`, fachlich mit FastAPI-TestClient, Oberfläche mit Playwright |

## Lokal starten

```
cd finanzverwaltung
python3 -m pip install -r requirements-docker.txt
FINANZAPP_DATENVERZEICHNIS=/tmp/fv-daten python3 run.py   # http://localhost:8935
```

Ohne `FINANZAPP_DATENVERZEICHNIS` legt `run.py` die Datenbank im Ordner
`finanzverwaltung/` an und öffnet einen Browser (alter Desktop-Modus). Für die
Entwicklung immer ein eigenes Datenverzeichnis setzen. `FINANZAPP_FESTE_ZEIT`
(ISO-Zeitpunkt) friert die Uhr des Servers ein, gedacht nur für Werkzeuge.

## Fachliche Module (`app/core/`)

| Modul | Aufgabe |
| --- | --- |
| `db.py` | Pfade, Verbindung, `initialisieren()` mit allen Migrationen, feste Kategorien |
| `startup.py` | Programmstart: fällige Buchungen aus Vorlagen, Darlehen, Altersvorsorge, Plan → Ist, Backup |
| `buchungen.py` | Konten, Kategorien, Buchungen, Saldo, `sql_in()` für Mehrfachfilter |
| `wiederkehrend.py` | Vorlagen: Termine, Dynamik, Inflation, Erzeugung |
| `darlehen.py`, `darlehensraten.py` | Tilgungsplan und fällige Raten |
| `altersvorsorge.py` | Beiträge und Auszahlungen, Korridor garantiert/voraussichtlich |
| `budgets.py` | Perioden, Verbrauch, Ampel, Übertrag, Prognose, Sparziele |
| `auswertungen.py` | Saldo-Verlauf, Cashflow, Kategorien, Jahresübersicht |
| `vertragsauswertung.py` | Reiter „Darlehen“ und „Altersvorsorge“ der Auswertungen |
| `plan_buchungen.py` | Plan-Buchungen umwandeln, Protokoll |
| `zuruecksetzen.py` | „Daten zurücksetzen“ mit Bestätigungsphrase |
| `wiederherstellen.py` | Datenbank aus Datei oder Backup einspielen |
| `backup.py` | Backups zum 15. und Monatsende, manuelle Backups, Rotation (12) |
| `feiertage.py` | Regeltabelle aller Feiertage je Bundesland, TARGET-Bankkalender, `vorheriger_werktag()` |
| `zeit.py` | `heute()` und `jetzt()` in Europe/Berlin |
| `hilfe.py`, `hilfe_pdf.py` | Hilfedatei zerlegen und prüfen, PDF mit ReportLab |
| `../roundtrip.py` | XLSX-Export und -Import aller Bereiche |

## Regeln im Code

- **Datum und Uhrzeit** immer über `zeit.heute()` und `zeit.jetzt()`, nie
  `date.today()` oder `datetime.now()`. Ein Test prüft das.
- **Vorzeichen:** Ausgaben negativ, Einnahmen positiv. Eingegeben wird positiv,
  das Vorzeichen kommt aus dem Typ der Kategorie (Typ der obersten
  Oberkategorie). Neutrale Wurzeln: „Darlehen“, „Umbuchung“.
- **Buchungstypen:** `Ist`, `Plan`, `Uebertragung`. Übertragungen zwischen
  eigenen Konten zählen in keinem Cashflow und in keiner Kategorie.
- **Prognose:** Künftige Termine aus Vorlagen, Darlehen und Altersvorsorge
  werden gerechnet, nicht gespeichert. Gebucht wird erst beim Programmstart,
  wenn ein Termin fällig ist, verschoben auf den Werktag davor.
- **Feiertage:** Verschoben wird nur nach `feiertage.bank_kalender()`
  (Wochenende und TARGET-Schließtage). Das gewählte Bundesland dient nur der
  Markierung, nie der Berechnung. Neue Feiertage oder Gesetzesänderungen als
  neue Zeile in `feiertage.REGELN`, mit Rechtsgrundlage und Prüfstatus.
- **Feste Kategorien** immer über `system_key` auflösen, nie über eine ID.
- **Mehrfachfilter** (Konten, Kategorien) sind Mengen: `None` = kein Filter,
  leere Menge = nichts. API-Parameter `konten=1,3`, `kategorien=4,5`.
- **Sparziele** sind Budgets vom Typ `sparziel` mit Trägerkonto.

## Migrationen und Anwenderdaten

- Schemaänderungen in `schema.sql` und, für bestehende Datenbanken, in
  `db._migriere_schema()`. Jede Migration muss bei jedem Start gefahrlos
  erneut laufen können.
- Einmalige Datenänderungen laufen mit Merker in der Tabelle `einstellungen`
  (Muster: `_migriere_kategorien_v22`). Vorher ein Backup anlegen
  (`backup.backup_erstellen(..., beschreibung=...)`), jeden Schritt als Text
  zurückgeben. Die Schritte erscheinen im Start-Status und im Protokoll.
- Alles, was Daten löscht oder ersetzt, legt vorher ein Backup an und
  verlangt in der Oberfläche eine Bestätigungsphrase
  (`zuruecksetzen.phrase_ausstellen`).
- Eine Deinstallation des Add-ons löscht `/data`. Texte, die etwas anderes
  nahelegen, sind falsch.

## Frontend

- `api(pfad)` in `app.js` ruft `api/...` relativ auf (wegen Ingress), nie
  absolute Pfade.
- Diagramme: `diagrammGrundstil()` setzt die Chart.js-Vorgaben für die ganze
  App. Neue Diagramme brauchen keine eigene Achsen- oder Tooltip-Gestaltung.
- Mehrfachauswahl: Klasse `MehrfachAuswahl`, Filter im Browser über
  `filterLaden`/`filterSpeichern` (nur Bequemlichkeit, `localStorage` in try).
- Feste Hinweistexte stehen nicht im HTML, sondern in der Hilfedatei:
  `data-hinweis="id"` bzw. `data-hinweis-titel="id"` im HTML,
  `hinweisHtml("id")` im JS, Text als `<!-- hinweis: id -->` in `hilfe.md`.
- Jeder Block bekommt `data-hilfe="anker"` an der Überschrift, das „?“
  springt zum Kapitel.
- Nach Änderungen an `app.js` oder `style.css` die `?v=`-Nummer in
  `index.html` erhöhen (Cache).

## Hilfe pflegen

Jede Änderung am Programm zieht `app/hilfe/hilfe.md` im selben Arbeitsgang
nach. Regeln:

- Jedes Unterkapitel hat einen festen Anker (`<!-- kapitel: bereich.thema -->`),
  Stichworte (`<!-- stichworte: … -->`) und das Muster „Wofür?“, „So geht's“,
  „Gut zu wissen“, „Siehe auch“. Anker beim Umschreiben nicht ändern.
- Stil: Du-Anrede, kurze Sätze, Beschriftungen der Oberfläche wörtlich in
  „…“, keine Versionshinweise, keine Begründungen (die gehören in `DOCS.md`).
  Rechtliches oder Steuerliches nur als Vorschlag.
- Höchstens ein Bild je Unterkapitel. Bilder erzeugt
  `python3 werkzeuge/hilfe_bilder.py` mit Demo-Daten und fester Uhrzeit.
- Zweite Zeile der Datei: `Programmversion: X.Y`, gleich der Version im
  Dockerfile.
- Prüfen: `hilfe.pruefen(hilfe.laden(), "X.Y")` muss eine leere Liste liefern
  (in `finanzverwaltung/`: `python3 -c "from app.core import hilfe; print(hilfe.pruefen(hilfe.laden(), 'X.Y'))"`).

## Neue Version

Die Versionsnummer steht synchron in `config.yaml` (`version`), im
`Dockerfile` (`LABEL io.hass.version`, `ENV FINANZAPP_VERSION`,
`ENV FINANZAPP_VERSION_DATUM`) und in der zweiten Zeile von `hilfe.md`. Dazu
ein Abschnitt „Neu in Version X.Y“ in `DOCS.md` (mit Begründungen und
gefundenen Fehlern) und ein kurzer Eintrag in `CHANGELOG.md`. Home Assistant
erkennt ein Update nur an einer geänderten `version` in `config.yaml`.

## Testen

```
python3 tests/alle_tests.py            # alles, dauert einige Minuten
python3 tests/alle_tests.py --ohne-ui  # nur fachlich
```

Einrichtung und Testdaten: `tests/README.md`. Vor einer Änderung einmal alle
Reihen laufen lassen, danach wieder.

Die Testdaten stammen von Oktober 2026, mehrere Prüfungen rechnen aber mit dem
echten heutigen Datum. Schlägt eine Prüfung fehl, erst mit dem Code der
Vorversion gegenprüfen. Liegt es am Datum, die Tests bedarfsweise
aktualisieren: Erwartungen relativ zu heute formulieren (zum Beispiel
„nächster Werktag“ statt „morgen“, Monatsgrenzen aus dem Zeitraum ableiten)
oder die Testdatenbanken in `tests/daten/` mit aktuellem Datum neu erzeugen.
Dabei die Testdaten erfunden halten und keine echten Personendaten
übernehmen. Die Änderung im Commit und in `tests/README.md` vermerken.

Neue Funktionen bekommen eine eigene
Testreihe `vXY_test.py` (fachlich) und `uiXY_test.py` (Oberfläche), mit
Fehlerfällen, nicht nur dem Erfolgsweg. Bei Update-relevanten Änderungen
zusätzlich `upgrade_test.py` mit einer Datenbank der Vorversion (Aufruf in
`tests/README.md`). Oberflächenreihen starten mit gewähltem Bundesland,
sonst blockiert die Pflichtabfrage (`alle_tests.bundesland_vorbelegen`).

## Arbeitsweise

- Gezielt ändern statt Dateien neu zu schreiben.
- Unklare Fachlogik vor dem Bauen klären, nicht raten.
- Beim Bauen gefundene Fehler einzeln benennen („Befund“ mit Buchstaben,
  siehe `DOCS.md`) und getrennt von der eigentlichen Aufgabe beheben.
- Eine Prüfung auf Vorhandensein immer gegen genau das prüfen, was beim
  Anlegen geschrieben wird (Lehre aus Befund O).
- Filter auf Baumstrukturen beziehen sich auf Teilbäume (Lehre aus Befund M).
- Testerwartungen nie an Wochentag oder Monatsgrenze des Testtags koppeln.
  Schlägt ein alter Test fehl, erst mit dem Code der Vorversion gegenprüfen.
- Nichts doppelt pflegen: Hinweistexte nur in `hilfe.md`, Begründungen nur in
  `DOCS.md`.
- Seiten, die eingebettet laufen (Schnellbuchung im Panel aus
  `ha-integration/`), auch eingebettet testen (`ui264_test.py`, Lehre aus #4).
  Änderungen an `ha-integration/` erreichen den Anwender nicht über das
  Add-on-Update; Hilfe und README nennen dann den Kopierschritt.

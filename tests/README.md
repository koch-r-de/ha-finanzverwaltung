# Tests

## Einrichten

```
python3 -m pip install -r finanzverwaltung/requirements-docker.txt httpx pypdf playwright
python3 -m playwright install chromium
```

`httpx` braucht der TestClient von FastAPI, `pypdf` die Prüfung des
PDF-Handbuchs, `playwright` die Oberflächentests.

## Alle Tests ausführen

Aus dem Wurzelordner des Repositorys:

```
python3 tests/alle_tests.py            # fachliche Tests und Oberflächentests
python3 tests/alle_tests.py --ohne-ui  # nur fachliche Tests
```

Jede Reihe arbeitet auf einer Kopie einer Testdatenbank in `tests/ausgabe/`.
Protokolle und Bildschirmfotos der Oberflächentests landen ebenfalls dort.
Für die Oberflächentests startet das Skript den Server auf Port 8935.

## Testreihen

| Reihe | Inhalt | Testdatenbank |
| --- | --- | --- |
| `funktion_test.py` | Fachlogik bis 1.10 (Umbuchungen, Prognose, Budgets) | `daten/v191` |
| `v2_test.py` | 2.0: laufender Monat, Saldo-Korrekturen, Inflation, Sparziele, Rentenbeginn, XLSX-Roundtrip, Zeitzone | `daten/v191` |
| `v21_test.py` | 2.1: Hilfe, Hinweistexte, PDF, Feiertage | `daten/v20` |
| `v22_test.py` | 2.2: empfohlene Kategorien, Kategorie-Umstellung | `daten/v20` |
| `v23_test.py` | 2.3: Mehrfachfilter, Saldo je Kategorie, Kennzahlen | Ergebnis von `v2_test.py` |
| `v24_test.py` | 2.4: Datenbank wiederherstellen, Backup-Namen | `daten/v191`, eingespielt wird `daten/v21` |
| `v263_test.py` | 2.6.3: Kategorie-Vorschlag aus der Beschreibung (Schnittstelle der Schnellbuchung) | `daten/v21` |
| `v262_test.py` | 2.6.2: Befund Q (Herkunftsprüfung in allen Modi), Hilfe-Unterkapitel Feiertage | `daten/v21` |
| `v261_test.py` | 2.6.1: Befund P, Zielkonto nur bei Übertragungen, Datenkorrektur | `daten/v21` mit eingestreuten Altfehlern |
| `v26_test.py` | 2.6: Feiertage (Ostern, Intervalle, Sonderfälle, Verschiebung, Migration, Hinweise, Siri, Import) | `daten/v21` |
| `ui*_test.py` | Oberfläche der jeweiligen Version (Playwright) | `daten/v191`, ergänzt durch `ui_vorbereiten.py` |
| `ui264_test.py` | 2.6.4: Seitenleisten-Panel der Schnellbuchung eingebettet (Höhe in drei Behältern, Desktop und iPhone); optional Pfad einer anderen Panel-Datei für die Gegenprobe | `daten/v191` |
| `ui263_test.py` | 2.6.3: Schnellbuchung (Issue #4 Eingabetaste, Befund R, Vorauswahl der Kategorie, alle Felder sichtbar) | `daten/v191` |
| `ui26_test.py` | 2.6: Bundesland-Abfrage, Hinweise, Symbol in der Liste, Dialoge | `daten/v191` ohne gewähltes Bundesland |
| `upgrade_test.py` | Update einer Datenbank mit Vergleich aller Tabellen | beliebig, siehe unten |

Einzeln aufrufen: `python3 tests/v24_test.py finanzverwaltung <quelle> <ziel> [weitere]`.
`<quelle>` ist ein Ordner mit `finanzdaten.db`, `<ziel>` wird überschrieben.

## Testdatenbanken

`daten/v191` wurde mit Version 1.9.1 über die Schnittstelle angelegt (Personen,
vier Konten, Vorlagen, Sparziel, Darlehen, Altersvorsorge). `daten/v20` und
`daten/v21` sind dieselben Daten, mit 2.0 bzw. 2.1 hochgezogen. Die Daten sind
erfunden, Backup-Listen sind geleert.

`upgrade_test.py` prüft ein Update: erst mit dem Code der alten Version eine
Datenbank hochziehen, dann mit dem neuen Code, und alle Tabellen vergleichen.
Dafür braucht es einen Stand der alten Version, etwa aus einem älteren Commit:

```
git worktree add ../fv-alt <commit der Vorversion>
UPGRADE_ZEIT_ALT=2027-11-01T12:00:00 UPGRADE_ZEIT_NEU=2027-11-03T12:00:00 \
  python3 tests/upgrade_test.py finanzverwaltung tests/daten/v21 tests/ausgabe/upgrade ../fv-alt/finanzverwaltung
```

Die beiden Zeiten frieren die Uhr der Läufe ein. Für 2.6 prüft das Beispiel
den Übergang an Allerheiligen 2027: 2.5 bucht die Termine zum 01.11. am
29.10., 2.6 darf sie nicht noch einmal buchen.

Seit 2.6 setzt `alle_tests.py` für die Oberflächenreihen der Vorversionen das
Bundesland NRW in der kopierten Datenbank, weil sonst die Pflichtabfrage beim
Start alle Klicks verdeckt. `ui26_test.py` startet ohne diese Vorbelegung.

## Bekannte Grenze

Mehrere Prüfungen rechnen mit dem echten heutigen Datum, die Testdaten stammen
aber von Oktober 2026. Je weiter das zurückliegt, desto eher passen einzelne
Erwartungen nicht mehr (zum Beispiel Termine „ab 2027“). Schlägt eine Prüfung
fehl, zuerst mit dem Code der Vorversion gegenprüfen, ob es am Datum liegt.
Wenn ja, die betroffene Prüfung relativ zu heute formulieren oder die
Testdatenbanken mit aktuellem Datum neu erzeugen und das hier vermerken.

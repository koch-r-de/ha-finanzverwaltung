# Änderungen

Ausführlich zu jeder Version: DOCS.md, Abschnitte „Neu in Version …“.

## 2.7

- Neu: Die Schnellbuchung in der Seitenleiste ist eine Integration, die HACS installiert und aktualisiert. Kein Kopieren und kein Eintrag in der `configuration.yaml` mehr. Neue Adresse `/finanzen-schnellbuchung`, Umstieg siehe `ha-integration/README-HA-Integration.md`.
- Korrektur: Benutzer ohne Administratorrechte sahen bei einer Installation aus dem Repository nur eine Fehlermeldung (Befund S).
- Korrektur: Die Schnellbuchung in der Seitenleiste legte keine eigene Ingress-Sitzung an und konnte nach 15 Minuten „401: Unauthorized“ zeigen (Befund T).

## 2.6.4

- Korrektur: Die Schnellbuchung in der Seitenleiste von Home Assistant war nur 150 Pixel hoch, sichtbar war nur „Betrag“ (Issue #4). `finanzen-schnellbuchung.js` erneut nach `config/www` kopieren und `module_url` auf `?v=2.6.4` setzen.

## 2.6.3

- Korrektur: In der Schnellbuchung buchte die Eingabetaste sofort, der Betrag verschwand (Issue #4). Sie springt jetzt ins nächste Feld, die Meldung „Gebucht“ steht oben und bleibt.
- Korrektur: Die Schnellbuchung belegte die Kategorie still mit der ersten der Liste vor, Regeln griffen dort nie (Befund R).
- Schnellbuchung: alle Felder ohne Aufklappen sichtbar, Beschreibung vor Kategorie, Kategorie wird beim Tippen der Beschreibung über die Regeln vorausgewählt.

## 2.6.2

- Sicherheit: Herkunftsprüfung im internen Netz von Home Assistant, Option „Zugriff im internen Netz prüfen“ (Standard: nur protokollieren), andere Add-ons lassen sich damit aussperren (Befund Q).
- Hilfe: eigenes Unterkapitel „Feiertage und Buchungstermine“.

## 2.6.1

- Korrektur: „Neue Buchung“ speicherte bei Ist und Plan ein Zielkonto, Anzeige „A → B“ und falsche Treffer im Kontofilter (Befund P). Bestehende Buchungen werden einmalig korrigiert, mit Backup vorher.

## 2.6

- Feiertagskalender wählbar: Bundesland beim ersten Start (Pflicht), änderbar in der Administration, regionale Sonderfälle als eigene Einträge.
- Feiertage werden nur markiert: Hinweis an Datumsfeldern, nach dem Speichern von Vorlagen, Darlehen und Altersvorsorge, in der Import-Vorschau, in der Schnellbuchung und als „F“ in der Buchungsliste. Siri-Antwort mit Feld `feiertagshinweis`.
- Fällige Termine verschieben nur noch an Wochenenden und Bankfeiertagen (TARGET), nicht mehr an allen NRW-Feiertagen.
- Feiertage werden berechnet statt gespeichert, Tabelle `feiertage` und „Neu berechnen“ entfallen.
- „Datum ändern“ im Plan-Protokoll und die erste Auszahlung eines Darlehens als Dialog statt Browser-Abfrage.

## 2.5

- Veröffentlichung auf GitHub (GPL-3.0), installierbar als Repository in Home Assistant.
- armv7 entfällt, unterstützt werden amd64 und aarch64.
- Schnellbuchung in der Seitenleiste findet das Add-on auch bei Installation aus dem Repository.
- Dokumentation korrigiert: Eine Deinstallation löscht alle Daten, `/data` ist über Samba nicht erreichbar.

## 2.4

- Datenbank wiederherstellen: Datei hochladen oder Backup aus der Backup-Liste einspielen, mit Prüfung, Bestätigungsphrase und Backup vorher.
- Korrektur: Backups in derselben Sekunde überschrieben sich (Befund N).
- Korrektur: Das Ultimo-Backup des Vormonats entstand vom 1. bis 14. bei jedem Start neu und verdrängte ältere Backups (Befund O).

## 2.3

- Auswertungen und Jahresübersicht: Konten und Kategorien mehrfach wählbar, Kategorien als Baum mit Suchfeld, Oberkategorie schließt Unterkategorien ein (Befund M).
- Diagramme laden automatisch, der Browser merkt sich die Filter.
- Neu gestaltete Auswertungen: Kennzahlen-Kacheln, Saldo-Verlauf mit Nettovermögen, Cashflow nach Monat, Quartal oder Jahr, Kategorien als Rangliste, gemeinsamer Diagramm-Grundstil.

## 2.2

- Empfohlene Kategorien entstehen nur noch bei einer neuen Datenbank, Gelöschtes kommt nicht zurück (Befund K).
- Einmalige Kategorie-Umstellung mit Backup vorher (u. a. „Darlehens-Zinsen“, Rente unter Einnahmen, „Lebensmittel/Verpflegung“, neue Kategorien).
- Migrationsschritte stehen im Add-on-Protokoll (Befund L).

## 2.1

- Eingebaute Hilfe mit Suche, „?“-Sprüngen aus jeder Ansicht und PDF-Handbuch.
- Vorlagen-Tabelle scrollt für sich, Spalte „Dynamik“ entfällt.
- Feiertage werden bei jedem Start komplett neu berechnet (Befund J).

## 2.0

- Laufender Monat mit anstehenden Terminen in Cashflow, Jahresübersicht und Budgets.
- Saldo-Korrekturen nur bis heute, Schalter „Inflation einrechnen“, Sparziele nur an passenden Übertragungen.
- Rentenbeginn verschieben räumt Beiträge und Renten passend auf.
- Export und Import als XLSX-Roundtrip.
- Server rechnet fest mit deutscher Zeit.

## 1.10 und früher

- Wiederkehrende Umbuchungen, Korrekturen an Saldo-Verlauf, Cashflow-Prognose und Budgets (1.10).
- Weitere Versionen: siehe DOCS.md, Abschnitte „seit Version …“.

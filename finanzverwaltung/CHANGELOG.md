# Änderungen

Ausführlich zu jeder Version: DOCS.md, Abschnitte „Neu in Version …“.

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

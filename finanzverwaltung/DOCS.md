# Private Finanzverwaltung – Dokumentation

## Installation

In Home Assistant unter Einstellungen → Apps (früher Add-ons) → App-Store
→ Menü oben rechts → „Repositorys“ diese Adresse hinzufügen:

    https://github.com/koch-r-de/ha-finanzverwaltung

Danach erscheint „Private Finanzverwaltung“ im App-Store. Installieren,
starten, fertig. Unterstützt werden amd64 und aarch64 (z. B. Raspberry Pi
4/5 mit 64-Bit-Home-Assistant-OS).

Privates Projekt, kein Support, keine Gewähr. Fehlermeldungen und
Vorschläge gern als Issue auf GitHub, eine Antwort ist nicht zugesagt.

## Nutzung

Nach dem Start erscheint "Finanzen" in der Home-Assistant-Seitenleiste
(links). Ein Klick öffnet die Oberfläche direkt in Home Assistant –
Authentifizierung läuft über den bestehenden HA-Account, es ist kein
separates Passwort nötig. Das funktioniert genauso im Web-Browser wie
in der Companion-App auf iPhone/iPad/Android.

## Daten

Alle Daten liegen unter `/data` (dem persistenten Speicher des
Add-ons) in `finanzdaten.db`, Backups im Unterordner `Backups/`. Diese
Dateien sind Teil des normalen Home-Assistant-Backups (Einstellungen →
System → Backups), sofern "Finanzverwaltung" beim Erstellen des
Backups mit ausgewählt wird. Die Daten verlassen das Gerät nicht.

`/data` ist von außen (auch über die Samba-Freigabe) nicht erreichbar.
Zum Sichern und Zurückspielen dienen in der Administration „Datenbank
herunterladen“ und „Datenbank wiederherstellen“.

**Eine Deinstallation löscht `/data` und damit alle Daten.** Vorher immer
die Datenbank herunterladen.

## Log-Datei

Zusätzlich zum Log-Tab in Home Assistant (der nur einen begrenzten,
flüchtigen Ausschnitt zeigt) schreibt die App fortlaufend nach
`/data/logs/finanzapp.log`. Die Datei wird automatisch rotiert (max.
5 MB, die letzten 3 Dateien bleiben erhalten), wächst also nicht
unbegrenzt. Sie liegt wie die Datenbank in `/data` und ist damit nur aus
dem Add-on heraus erreichbar, etwa über ein Home-Assistant-Backup.

## Aktualisieren

Aus dem Repository installiert: im App-Store „Nach Updates suchen“, dann
bei der App „Aktualisieren“. Die Datenbank unter `/data` bleibt dabei
erhalten.

Als lokales Add-on (Ordner `finanzverwaltung/` unter `addons/` der
Samba-Freigabe): Ordner ersetzen, dann „Nach Updates suchen“ und
„Aktualisieren“. Nicht deinstallieren, das löscht die Daten.

Umzug vom lokalen Add-on auf die Installation aus dem Repository: siehe
„Neu in Version 2.4“, Abschnitt „Umzug in ein anderes Add-on“.

## Schnellbuchung

Unter `/schnellbuchung` liefert das Add-on eine mobiloptimierte
Eingabemaske: Betrag, Konto, Kategorie und Beschreibung immer sichtbar,
Buchungstyp/Datum/Zielkonto/Sparziel hinter "Weitere Angaben". Neben
"Speichern" gibt es "Speichern & weiter", das Konto und Kategorie
beibehält und nur Betrag und Beschreibung leert.

Komfortfunktionen: Das zuletzt genutzte Konto und die zuletzt genutzte
Kategorie werden im Browser gemerkt und vorbelegt. Im Betragsfeld darf
gerechnet werden ("12,50+8,30" ergibt 20,80). Existiert am selben Tag
auf demselben Konto bereits ein gleicher Betrag, erscheint ein Hinweis
auf ein mögliches Duplikat – ohne die Buchung zu blockieren.

Für einen eigenen Eintrag in der Home-Assistant-Seitenleiste und für
Siri-Kurzbefehle siehe `ha-integration/README-HA-Integration.md`.

## Automatische Kategorisierung

Im Admin-Bereich lassen sich Textregeln hinterlegen (z. B. "REWE" →
Lebensmittel). Wird eine Buchung ohne Kategorie erfasst, greift die
erste passende Regel nach Priorität. Groß-/Kleinschreibung spielt keine
Rolle, gesucht wird als Teilstring in der Beschreibung.

## Personen (seit Version 1.5, seit 1.6 auch bei Budgets/Darlehen)

Im Admin-Bereich lassen sich Personen anlegen (Name, optional eine
Farbe) - gedacht für die Trennung von Konten, wiederkehrenden Buchungen,
Altersvorsorge-Verträgen, Budgets und Darlehen bei gemeinsamer
Haushaltsführung. Die Zuordnung ist überall optional; ohne Zuordnung
bleibt ein Eintrag "ohne Person" und taucht in keinem Personen-Filter
unter. Buchungen selbst tragen keine eigene Personen-Zuordnung - sie
ergibt sich automatisch über das jeweilige Konto.

Konten-Übersicht, Wiederkehrend, Altersvorsorge, Budgets, Darlehen und
die Buchungen-Liste/-Suche besitzen dadurch je einen Personen-Filter
(Budgets und Darlehen seit Version 1.7 - vorher war der Filter nur im
Backend vorhanden, ohne Dropdown in der Oberfläche). Eine deaktivierte
(gelöschte) Person bleibt für die Namensauflösung bestehender Einträge
erhalten, erscheint aber nicht mehr in den Auswahllisten für neue
Zuordnungen.

## Konten (seit Version 1.6 änderbar)

Konten lassen sich nachträglich bearbeiten (Name, Typ, Eröffnungsdatum,
Person, Gesamtsaldo-Einschluss) - der "Ändern"-Knopf in der
Konten-Tabelle befüllt dasselbe Formular wie beim Anlegen. Über das
Häkchen "Im Gesamtsaldo" legt man je Konto fest, ob es in den
Gesamtsaldo auf der Startseite einfließt (z. B. sinnvoll, um ein reines
Verrechnungs- oder Fremdwährungskonto herauszurechnen). Der Gesamtsaldo
steht als erste, hervorgehobene Kennzahl ganz oben auf der Startseite.

Seit Version 1.6.2 lässt sich über das Häkchen "Eigene Farbe" je Konto
eine feste Farbe vergeben (Farbpunkt in der Konten-Tabelle, verwendet
im Saldo-Verlauf-Diagramm). Ohne eigene Farbe bleibt es bei der
automatischen Zuordnung aus der 14er-Palette.

## Darlehen (seit Version 1.7 änderbar)

Darlehen lassen sich nachträglich bearbeiten (alle Eckdaten inkl.
Zinssatz, Tilgungsbeginn, Laufzeit, Ratenmodus, Zahlungskonto und
Person) - der "Ändern"-Knopf auf der jeweiligen Darlehenskarte befüllt
dasselbe Formular wie beim Anlegen, ohne die Detailansicht (Tilgungsplan)
zu öffnen. Bereits erfasste Auszahlungen und Sondertilgungen bleiben
davon unberührt. Vorher ließ sich ein Darlehen nur anlegen, nicht mehr
ändern - insbesondere die Personen-Zuordnung war dadurch nachträglich nicht
korrigierbar.

Seit Version 1.9 hat jede Darlehenskarte zusätzlich die Knöpfe
"Auszahlung" und "Sondertilgung". Sie öffnen einen kleinen Dialog (Datum,
Betrag; bei der Sondertilgung zusätzlich das Konto, vorbelegt mit dem
Zahlungskonto). Eine Auszahlung wird auf dem Zahlungskonto gebucht; ist
keines hinterlegt, wird sie nur am Darlehen erfasst. Das frühere
Sondertilgungs-Formular in der Detailansicht ist entfallen. Neu ist außerdem
das Feld "Darlehenssumme" (vertraglich vereinbarter Betrag, Pflicht bei
neuen Darlehen); die Karte zeigt daraus den noch nicht ausgezahlten Rest.
Bestehende Darlehen bleiben ohne Summe, bis sie über "Ändern" nachgetragen
wird.

## Neu in Version 2.6

**Feiertagskalender wählbar:** Beim ersten Start fragt das Programm nach dem
Bundesland (Pflichtangabe, das Fenster lässt sich nicht wegklicken). Danach
ist es unter „Administration“, Reiter „Stammdaten“, Block „Feiertage“
änderbar, dort steht auch die Liste der Feiertage des laufenden Jahres.
Regionale Sonderfälle sind eigene Einträge, benannt nach dem Feiertag:
„Bayern – mit Mariä Himmelfahrt“, „Bayern – ohne Mariä Himmelfahrt“,
„Bayern – Stadt Augsburg“ (Friedensfest), „Sachsen – mit Fronleichnam“,
„Thüringen – mit Fronleichnam“. Gemeindegenaue Regeln bildet nur diese
Auswahl ab, es gibt keine Gemeindeliste. Schulferien und Gedenktage werden
nicht markiert.

**Nur markieren, nichts sperren:** Ein Hinweis erscheint unter dem Datumsfeld
im Buchungsformular, bei der Saldo-Korrektur, im neuen Dialog „Datum ändern“
des Plan-Protokolls, bei Auszahlung und Sondertilgung eines Darlehens und in
der Schnellbuchung. Nach dem Speichern einer Vorlage, eines Darlehens oder
einer Altersvorsorge nennt das Programm die Termine der nächsten 12 Monate,
die auf einen Feiertag fallen (Entscheidung: nach dem Speichern statt
Probelauf beim Ausfüllen, weil die Termine nur der Server rechnet). Die
Import-Vorschau nennt neue oder geänderte Zeilen an Feiertagen. Die
Buchungsliste markiert Feiertage mit einem kleinen „F“ (mit Namen beim
Darüberfahren), auch bei anstehenden Terminen. Auch Feiertage an einem
Sonntag werden markiert. Stammdaten, Fristen und Zeiträume (Kontoeröffnung,
Zinsbindung, Budget-Zeiträume, Filter, Export, „Ist bis“) bekommen keinen
Hinweis.

**Siri:** Die Antwort von `/api/siri/buchung` hat das zusätzliche Feld
`feiertagshinweis` (Text oder `null`). `meldung` bleibt unverändert, bestehende
Kurzbefehle sprechen also dasselbe wie bisher.

**Verschiebung fälliger Termine nach dem Bankkalender (Verhaltensänderung):**
Bis 2.5 verschob das Programm Termine aus Vorlagen, Darlehen und
Altersvorsorge an jedem NRW-Feiertag auf den Werktag davor. Seit 2.6
verschiebt es nur noch an Wochenenden und an den TARGET-Schließtagen der EZB
(Neujahr, Karfreitag, Ostermontag, 1. Mai, 25. und 26. Dezember, gültig ab
2002 laut Pressemitteilung der EZB vom 14.12.2000). Begründung: Ob eine
Zahlung verschoben wird, hängt vom Geschäftstag der Bank ab (§ 675n Abs. 1
BGB), nicht vom Wohnort, und SEPA-Zahlungen laufen über den TARGET-Kalender.
Das Bundesland ändert damit kein einziges Buchungs- oder Prognosedatum.
Folge für NRW: Termine an Fronleichnam, Christi Himmelfahrt, Pfingstmontag,
3. Oktober und Allerheiligen werden ab dem Update nicht mehr vorgezogen.
Bereits gebuchte Buchungen bleiben, wie sie sind. Ob die eigene Bank an
regionalen Feiertagen bucht, ist von Haus zu Haus verschieden (ungeprüft).
Unverändert gilt: verschoben wird auf den Werktag davor, auch wenn
Lastschriften in der Praxis meist am nächsten Geschäftstag belastet werden.

**Übergang ohne doppelte Termine:** Die Generatoren betrachten nur Termine,
deren ursprüngliches Datum erreicht ist, und setzen die Erzeugungsmarke
`erzeugt_bis` vorher auf heute. Ein Termin, den 2.5 nach NRW vorgezogen
gebucht hat (zum Beispiel am 01.11.2027 für Allerheiligen gebucht auf den
29.10.), liegt deshalb immer vor `erzeugt_bis` und wird nach dem Update
übersprungen. Ein eigener Abgleich mit dem alten NRW-Datum ist nicht nötig.
`tests/upgrade_test.py` weist das mit dem echten Code von 2.5 nach.

**Regeltabelle:** Feiertage stehen als eine Tabelle im Code
(`app/core/feiertage.py`, `REGELN`), eine Zeile je Feiertag mit Name, Regel
(festes Datum `MM-TT`, Abstand zum Ostersonntag oder Sonderregel Buß- und
Bettag = Mittwoch vor dem 23. November), Regionen, Gültigkeit [von, bis]
(offenes Ende 9999, einmalige Feiertage mit von = bis), Rechtsgrundlage und
Prüfstatus. Ostern rechnet die Gaußsche Osterformel ohne fremde Bibliothek.
„Von 1990“ heißt: gilt mindestens seit 1990, Früheres ist nicht abgebildet.
Ändert ein Land sein Gesetz, genügt eine neue Zeile und eine neue Version.
Die frühere Tabelle `feiertage` in SQLite (bei jedem Start gelöscht und neu
gefüllt) und der Knopf „Neu berechnen“ entfallen.

Rechtsgrundlagen (Recherche Oktober 2026, Landesgesetze überwiegend über
umwelt-online eingesehen, Bayern, NRW und Sachsen über die amtlichen
Portale):

| Land | Gesetz |
| --- | --- |
| BW | Feiertagsgesetz vom 08.05.1995, § 1 |
| BY | Feiertagsgesetz vom 21.05.1980, Art. 1 (Mariä Himmelfahrt Abs. 1 Nr. 2, Friedensfest Augsburg Abs. 2) |
| BE | Gesetz über die Sonn- und Feiertage vom 28.10.1954, § 1 (Frauentag und 8. Mai 2020: Änderungsgesetz vom 30.01.2019, 17. Juni 2028: § 1 Abs. 1 Nr. 11) |
| BB | Feiertagsgesetz vom 21.03.1991, § 2 (mit Ostersonntag und Pfingstsonntag) |
| HB | Gesetz über die Sonn- und Feiertage vom 12.11.1954, § 2 |
| HH | Feiertagsgesetz vom 16.10.1953, § 1 |
| HE | Hessisches Feiertagsgesetz vom 29.12.1971, § 1 |
| MV | Feiertagsgesetz vom 08.03.2002, § 2 |
| NI | Niedersächsisches Gesetz über die Feiertage vom 07.03.1995, § 2 |
| NW | Feiertagsgesetz NRW, § 2 |
| RP | Landesfeiertagsgesetz vom 15.07.1970, § 2 |
| SL | Gesetz Nr. 1040 vom 18.02.1976, § 2 |
| SN | Sächsisches Sonn- und Feiertagsgesetz vom 10.11.1992, § 1, Fronleichnam nach FronleichnamsVO vom 04.05.1993 |
| ST | Feiertagsgesetz Sachsen-Anhalt vom 25.08.2004, § 2 |
| SH | Sonn- und Feiertagsgesetz vom 28.06.2004, § 2 |
| TH | Thüringer Feier- und Gedenktagsgesetz vom 21.12.1994, § 2 (Fronleichnam per Rechtsverordnung nach Abs. 2) |

Als ungeprüft gekennzeichnet: Beginn des Frauentags in MV (2023, nur
Sekundärquelle), Fundstelle des 8. Mai 2025 in Berlin (Feiertag bestätigt),
Titel der Thüringer Fronleichnams-Verordnung, Zuordnung von Mariä
Himmelfahrt zur Stadt Augsburg, Einigungsvertrag Art. 2 Abs. 2 als
zusätzliche Grundlage des 3. Oktober, die einmaligen Regelungen zum
Reformationstag 2017, der Buß- und Bettag außerhalb Sachsens bis 1994, der
Beginn von Heilige Drei Könige in Sachsen-Anhalt und des Reformationstags in
den ostdeutschen Ländern. Bekannt, aber bewusst nicht markiert: Sachsen-Anhalt
hat zum 04.05.2026 den 8. Mai und den 17. Juni als Gedenktage eingeführt
(§ 2a FeiertG LSA), das sind keine Feiertage.

**Migration:** Datenbanken von vor 2.6 erkennt das Programm an der Tabelle
`feiertage`. Es hinterlegt dann NRW als Vorschlag (bisher fest NRW) und
entfernt die Tabelle ohne Backup, weil sie nur abgeleitete Werte enthielt.
Die Abfrage erscheint mit NRW vorbelegt und muss bestätigt werden. Das gilt
auch nach dem Einspielen eines alten Backups. Neue Einstellungen:
`bundesland`, `bundesland_vorschlag` (beide nur über
`/api/feiertage/region`, nicht über die allgemeine Einstellung änderbar).
Neue Endpunkte: `GET /api/feiertage/regionen`, `PUT /api/feiertage/region`,
`GET /api/feiertage?von_jahr=&bis_jahr=` (höchstens 60 Jahre).

**Dialoge statt Browser-Abfrage:** „Datum ändern“ im Plan-Protokoll und die
erste Auszahlung direkt nach dem Anlegen eines Darlehens nutzten
`prompt()` mit Freitext „YYYY-MM-DD“. Beides sind jetzt Dialoge mit
Datumsfeld (die erste Auszahlung nutzt den vorhandenen Auszahlungsdialog mit
„Überspringen“), damit der Feiertagshinweis erscheinen kann.

**Tests:** neue Reihen `v26_test.py` (Ostern, Buß- und Bettag,
Gültigkeitsintervalle, jeder Sonderfall, Anzahl je Region, Verschiebung,
Migration, Fehlerfälle der Endpunkte, Serienhinweise, Siri, Import) und
`ui26_test.py`. `upgrade_test.py` zieht eine Datenbank mit dem Code von 2.5
hoch und vergleicht nach dem Start mit 2.6 alle Tabellen. Die
Oberflächenreihen der Vorversionen starten mit gewähltem NRW, sonst würde
die Pflichtabfrage sie blockieren.

**Befund P (gefunden beim Oberflächentest, besteht seit mindestens 2.5):**
Das Formular „Neue Buchung“ schickt bei Typ „Ist“ und „Plan“ das Zielkonto
aus dem verborgenen Auswahlfeld mit, `buchung_anlegen()` speichert es
ungeprüft. Folgen: Anzeige „A → B“ in der Buchungsliste, Kontofilter und
Suche zeigen die Buchung zusätzlich beim fremden Konto, der Export füllt die
Spalte „zielkonto“. Salden und Auswertungen sind nicht betroffen. Behebung
vorgeschlagen, noch nicht freigegeben.

## Neu in Version 2.5

**Veröffentlichung auf GitHub:** Das Projekt liegt öffentlich unter
https://github.com/koch-r-de/ha-finanzverwaltung (Lizenz GPL-3.0) und
lässt sich in Home Assistant als Repository hinzufügen. Aufbau: das Add-on
im Ordner `finanzverwaltung/`, daneben `repository.yaml`, `tests/`,
`werkzeuge/`, `ha-integration/` und `CLAUDE.md` (Hinweise für die Arbeit mit
Claude Code). Am Programm ändert sich nichts.

**armv7 entfällt:** Angeboten werden nur noch amd64 und aarch64, armv7 war nie
getestet.

**Schnellbuchung in der Seitenleiste:** `finanzen-schnellbuchung.js` findet das
Add-on jetzt auch, wenn es aus einem Repository installiert ist (Kennung
`<kennung>_finanzverwaltung` statt `local_finanzverwaltung`).

**Dokumentation korrigiert:** Bis 2.4 stand hier, die Datenbank bleibe bei
einer Neuinstallation erhalten und die Log-Datei sei über Samba erreichbar.
Beides stimmt nicht: Eine Deinstallation löscht `/data`, und `/data` ist über
Samba nicht sichtbar.

## Neu in Version 2.4

**Datenbank wiederherstellen:** In der Administration, Reiter „System“, gibt
es den Block „Datenbank wiederherstellen“ zum Hochladen einer gesicherten
Datenbank (zum Beispiel aus „Datenbank herunterladen“, auch aus einem
anderen Add-on) und in der Backup-Liste je Zeile den Knopf
„Wiederherstellen“. Ablauf: Das Programm prüft die Datei (SQLite,
`integrity_check`, Pflichttabellen) und zeigt jetzigen Stand und Datei
nebeneinander (Konten, Buchungen, Kategorien, letzte Ist-Buchung, Größe).
Nach Eingabe der angezeigten Phrase legt es ein Backup „vor
Wiederherstellung …“ an, spielt die Datei ein und startet wie beim
Hochfahren (Umstellungen älterer Versionen, fällige Termine). Scheitert
dieser Start, ist der vorherige Stand sofort wieder aktiv. Die Backup-Liste
bleibt die der Installation, die Liste aus der eingespielten Datei wird
verworfen, weil sie Dateien einer anderen Installation beschreibt.
Hochgeladene Dateien liegen bis zur Bestätigung in
`Backups/.wiederherstellen` und werden nach einer Stunde verworfen.
Höchstgröße 500 MB.

**Umzug in ein anderes Add-on** (zum Beispiel bei Installation aus einem
Git-Repository statt als lokales Add-on): Im alten Add-on die Datenbank
herunterladen, das neue installieren und starten, dort die Datei unter
„Datenbank wiederherstellen“ einspielen, Konten und Salden prüfen. Erst dann
das alte Add-on entfernen. Ein Add-on aus einem Repository hat eine andere
Kennung als das lokale. Deshalb ändern sich der Rechnername für den
Siri-`rest_command` (statt `local-finanzverwaltung`) und die Ingress-Adresse
der Schnellbuchung in der Seitenleiste. Beides einmal anpassen.

**Befund N:** Backups mit Beschreibung heißen nach Datum und Uhrzeit auf die
Sekunde. Zwei Backups in derselben Sekunde überschrieben sich, etwa „vor
Wiederherstellung“ und das Backup der Kategorie-Umstellung beim Einspielen
einer 2.1-Datenbank. Seit 2.4 bekommt ein schon vorhandener Name `_2`, `_3` …

**Befund O:** Vom 1. bis 14. eines Monats entstand bei jedem Start erneut
das Ultimo-Backup des Vormonats, weil es nach dem Starttag benannt war und
die Prüfung es deshalb nicht fand. Häufige Neustarts drängten so ältere
Backups (etwa „vor Löschung“) aus den zwölf behaltenen. Seit 2.4 heißen
automatische Backups nach ihrem Stichtag (z. B.
`finanzdaten_2026-09-30_automatisch_ultimo.db`), die Prüfung sucht genau
diesen Tag. Nach dem Update entsteht einmalig ein weiteres Backup zum
letzten Stichtag, weil die alten Namen nicht passen.

## Neu in Version 2.3

**Mehrfachauswahl in Auswertungen und Jahresübersicht:** Konten und
Kategorien wählst du jetzt mit Häkchen, auch mehrere zugleich, jeweils mit
„Alle“ und „Keine“. Kategorien erscheinen als Baum mit Suchfeld. Ein Haken
an einer Oberkategorie setzt alle Unterkategorien, eine teilweise gewählte
Oberkategorie zeigt „–“. Bis 2.2 zählte bei einer Kategorie nur, was direkt
auf ihr gebucht war, Unterkategorien fehlten. Konten wirken sofort,
Kategorien beim Schließen der Liste. Ist nichts gewählt, erscheint ein
Hinweis statt der Diagramme. Den Knopf „Aktualisieren“ gibt es nicht mehr.
Der Browser merkt sich Zeithorizont, Einheit, Konten und Kategorien
(Auswertungen) sowie Konten und Kategorien (Jahresübersicht). Die
Schnittstelle nimmt dafür `konten=1,3` und `kategorien=4,5,6` an, die alten
Parameter `konto_id` und `kategorie_id` gelten weiter als Auswahl mit einem
Eintrag.

**Saldo-Verlauf:** Die Konten liegen als deckende Flächen übereinander, eine
dunkle Linie zeigt das Nettovermögen (Konten minus Restschuld, ohne
Darlehen oder ohne „inkl. Darlehen“ die Summe der Konten). Die Restschuld
bleibt eine gestrichelte Linie. Mit Kategorie-Filter ist jede gewählte
Kategorie eine eigene Fläche über alle gewählten Konten, eine voll gewählte
Oberkategorie ist eine Fläche, eine teilweise gewählte heißt
„(teilweise)“. Beginnt der Zeitraum in der Vergangenheit, markiert eine
Linie „heute“. Darlehens-Zinsen und Tilgung zählen jetzt auch mit
Kategorie-Filter, wenn ihre Kategorie gewählt ist.

**Cashflow:** bis 2 Jahre je Monat, bis 10 Jahre je Quartal, darüber je
Jahr. Ausgaben zeigen nach unten, eine Linie zeigt den Überschuss.

**Kennzahlen:** vier Kacheln über den Diagrammen: Vermögen heute und am
Ende des Zeitraums (mit „inkl. Darlehen“ als Nettovermögen), Ø Überschuss
je Monat mit kleinem Balkenverlauf und Sparquote, beide über den gewählten
Zeitraum. Mit Kategorie-Filter zeigen die ersten beiden Kacheln Einnahmen
und Ausgaben der gewählten Kategorien.

**Kategorien:** sortierte Rangliste mit Betrag und Anteil, umschaltbar
zwischen Ausgaben und Einnahmen, ab Platz 13 „Übrige“.

**Grundstil für alle Diagramme:** Achsen mit „Okt 26“ statt ISO-Datum und
ohne Schräglage, nur waagrechte blasse Rasterlinien, Legende oben rechts als
Punkte, ein gemeinsamer Tooltip je Monat, abgerundete Balken, geglättete
Linien ohne Überschwingen. Blöcke und Karten haben runde Ecken. Zeithorizont
und Einheit sind Umschaltknöpfe.

## Neu in Version 2.2

**Empfohlene Kategorien (Befund K):** Bis 2.1 legte das Programm die
empfohlenen Kategorien bei jedem Start neu an, sobald eine fehlte.
Gelöschte oder umbenannte Kategorien kamen dadurch zurück. Seit 2.2
entstehen sie nur noch beim Anlegen einer neuen Datenbank. Fest vorgegebene
Kategorien (Einnahmen, Ausgaben, Rente, Darlehen usw.) ergänzt das Programm
weiterhin bei jedem Start, falls sie fehlen.

**Kategorie-Umstellung:** Beim ersten Start von 2.2 stellt das Programm die
Kategorien einmalig um. Vorher legt es ein Backup an („vor
Kategorie-Umstellung 2.2“ in der Backup-Liste). Die Schritte:

- „Darlehen > Zinsen“ heißt „Darlehens-Zinsen“.
- Die feste „Rente“ steht direkt unter „Einnahmen“ (bisher unter „Sonstige
  Einkünfte“). Eine frei angelegte „Rente“ direkt unter „Einnahmen“ wird mit
  ihr zusammengeführt.
- „Lebensmittel“ geht in „Lebensmittel/Verpflegung“ auf. Gibt es beide,
  werden Buchungen, Vorlagen, Budgets und Regeln umgehängt und
  „Lebensmittel“ gelöscht. Sonst wird „Lebensmittel“ umbenannt.
- „Versicherungen“ unter „Versicherungen & Vorsorge“ heißt
  „Sach-Versicherungen“.
- Neu, falls nicht vorhanden: „Haustier“ mit „Arztkosten & Medikamente“,
  „Futter“ und „Sonstiger Haustierbedarf“, „Kleidung“, „Steuern“, „Wasser“,
  „Heizung“, „Renovierung“, „Grundsteuer“ und „Zinsen & Kapitalerträge“
  (direkt unter „Einnahmen“).

Beim Zusammenführen hängt das Programm alle Verweise um: Buchungen,
Vorlagen, Budgets, Regeln, Altersvorsorge-Verträge und Unterkategorien.
Ein Siri-Favorit bleibt erhalten. Namen werden ohne Groß- und
Kleinschreibung, Leerzeichen und Bindestriche verglichen, „KFZ Unterhalt“
und „KFZ-Unterhalt“ gelten also als gleich. Salden ändern sich nicht. Die
Umstellung läuft nur einmal (Merker in den Einstellungen).

**Protokoll (Befund L):** Jeder Migrationsschritt steht beim Start im
Add-on-Protokoll und in `logs/finanzapp.log`, Zeilen beginnen mit
„Migration:“.

**Neue Datenbank:** Die empfohlene Liste entspricht dem neuen
Kategorienbaum, unter anderem mit „Lebensmittel/Verpflegung“,
„KFZ-Unterhalt“, „Steuern“, „Steuerrückerstattung“ und „Zinsen &
Kapitalerträge“.

**Hinweis Siri und Import:** „Zinsen“ passt jetzt zu „Darlehens-Zinsen“ und
„Zinsen & Kapitalerträge“. Das Programm meldet dann „mehrdeutig“, der Name
muss vollständig genannt werden.

## Neu in Version 2.1

**Hilfe im Programm:** Der neue Menüpunkt „Hilfe“ steht fest über
„Administration“. Ein „?“ im Kopf jeder Ansicht und an den meisten Blöcken
springt zum passenden Kapitel, „Zurück“ führt wieder an die alte Stelle.
Die Hilfe hat ein Inhaltsverzeichnis, eine Volltextsuche mit Trefferauszug
und den Knopf „PDF-Handbuch“ (PDF mit Inhaltsverzeichnis, Seitenzahlen,
Lesezeichen und Stichwortverzeichnis).

Einzige Quelle ist `app/hilfe/hilfe.md`. Jedes Kapitel trägt einen festen
Anker als Kommentar (`<!-- kapitel: bereich.thema -->`), Stichworte stehen
in `<!-- stichworte: … -->`. Die festen Hinweistexte der Oberfläche stehen
markiert in derselben Datei (`<!-- hinweis: id -->` … `<!-- /hinweis -->`)
und werden von der App geladen, App und Hilfe sind dadurch wortgleich. Die
zweite Zeile nennt die Programmversion. Bildschirmfotos liegen in
`app/hilfe/bilder` und entstehen mit `werkzeuge/hilfe_bilder.py`
(Demo-Daten, feste Uhrzeit). Das PDF erzeugt der Server mit ReportLab und
der Schrift DejaVu (Alpine-Paket `font-dejavu`), neue Python-Pakete:
markdown-it-py, reportlab, pillow. Für diese gibt es fertige Pakete für
aarch64 und amd64. Auf armv7 müsste Pillow beim Bau kompiliert werden,
das ist ungetestet.

**Wiederkehrend:** Die Tabelle „Vorlagen“ scrollt für sich, das Formular
„Neue Vorlage“ bleibt dabei oben stehen, auch beim Ändern. Die Spalte
„Dynamik“ entfällt.

**Administration:** Blocküberschriften und Tabs nutzen Schriftart und
Schriftgröße der Seitenleiste.

**Feiertage:** Bei jedem Start werden die Feiertage komplett neu berechnet,
vom ältesten gespeicherten Jahr bis heute plus 30 Jahre. Veraltete Einträge
verschwinden, vergangene Jahre bleiben. „Neu berechnen“ macht dasselbe.
Behoben (Befund J): Die Generatoren kannten beim Start nur Feiertage ab dem
laufenden Jahr. Ein nach Neujahr nachgeholter Termin aus dem Vorjahr, etwa
am 25.12., wurde deshalb am Feiertag statt am Werktag davor gebucht.

## Neu in Version 2.0

**Laufender Monat:** Cashflow, Jahresübersicht und Budget-Details zeigen
den laufenden Monat vollständig: bereits gebuchte Beträge plus die bis
Monatsende noch anstehenden Termine (Vorlagen, Darlehensraten,
Altersvorsorge). Der anstehende Anteil ist im Diagramm hell auf den
gebuchten Anteil gesetzt. Der Saldo-Verlauf rechnet den laufenden Monat
bis Monatsende hoch, die Prognose-Markierung beginnt im laufenden Monat.

**Saldo-Korrekturen nur bis heute:** Ein Datum in der Zukunft ist nicht
mehr möglich (Datumsfeld und Server). Beim ersten Start von 2.0 werden
bereits vorhandene künftige Korrekturen einmalig gelöscht und im
Start-Status einzeln genannt.

**Schalter „Inflation einrechnen“:** Auf den Seiten Auswertungen (alle
Tabs), Jahresübersicht, Budgets und in der Buchungsliste (anstehende
Termine). Standard ist aus. Eingeschaltet werden nur Posten mit
Inflations-Häkchen (Vorlagen, Rentenauszahlungen) und nur in der
Prognose mit dem globalen Inflationsfaktor hochgerechnet, der
Altersvorsorge-Korridor eingeschlossen. Echte Buchungen bleiben
unverändert. **Bis 1.10 war die Hochrechnung immer aktiv**, die Prognosen
fallen daher ohne Schalter jetzt nominal (niedriger) aus.

**Sparziele:** Ein Sparziel lässt sich nur noch einer Übertragung
zuordnen, deren Quelle oder Ziel das Trägerkonto des Sparziels ist. Auf
das Trägerkonto zählt als Einzahlung, vom Trägerkonto als Entnahme
(mindert den Stand, bis 1.10 wurde sie fälschlich addiert). Ist- und
Plan-Buchungen tragen kein Sparziel. Trägerkonto und Typ eines Sparziels
lassen sich nicht ändern, solange Buchungen oder Vorlagen zugeordnet
sind. Ältere Zuordnungen, die nicht passen, zählen nicht zum Stand; der
Start-Bildschirm weist darauf hin, und unter Administration → Stammdaten
→ „Sparziele prüfen“ lassen sie sich einzeln lösen (die Buchung bleibt,
nur das Sparziel wird entfernt).

**Rentenbeginn verschieben:** Beim Ändern des Rentenbeginns einer
Altersvorsorge zeigt ein Dialog, wie viele automatisch erzeugte
Buchungen danach in der falschen Phase lägen (Beiträge ab dem neuen
Rentenbeginn, Renten davor, bei Einmalzahlung die Zahlung am alten
Datum). Nach Bestätigung werden sie gelöscht und fehlende Beiträge bzw.
Renten nachgebucht. Im Plan-Protokoll angepasste Buchungen bleiben stehen
und werden genannt.

**Zeitzone:** Der Server rechnet fest mit deutscher Zeit
(Europe/Berlin), unabhängig von der Zeitzone des Containers. Bis 1.10
konnte „heute“ für Generatoren und Prüfungen zwischen 0 und 1 Uhr (Sommer
2 Uhr) noch der Vortag sein. Die Serverzeit steht unter Administration →
System.

**Wochenend-Termine in Vorschauen:** Ein Termin, der auf ein Wochenende
oder einen Feiertag fällt und dadurch auf den letzten Werktag davor
rückt, erscheint jetzt auch dann in Vorschau und Prognose, wenn sein
ursprüngliches Datum knapp hinter dem Zeitraumende liegt (z. B. Termin
am Samstag, 1., Zahlung am Freitag davor).

**Export und Import (XLSX-Roundtrip):** siehe Abschnitt „Export und
Import“.

## Wiederkehrende Umbuchungen (seit Version 1.10)

Vorlagen können neben normalen Buchungen jetzt auch regelmäßige
Übertragungen zwischen eigenen Konten abbilden (z. B. monatliche Sparrate
vom Girokonto aufs Tagesgeld). Im Formular "Neue Vorlage" dazu die Art
"Umbuchung" wählen: statt der Kategorie erscheint das Zielkonto (muss sich
vom Konto unterscheiden), optional ein Sparziel. Der Betrag wird ohne
Vorzeichen eingegeben, Inflation und Dynamik gibt es bei Umbuchungen
nicht. Die Kategorie ist intern fest "Umbuchung"; bei normalen Vorlagen
ist sie deshalb nicht mehr auswählbar.

Bei Fälligkeit entsteht eine echte Übertragung (Abgang im Konto, Zugang im
Zielkonto, mit Eintrag im Plan-Buchungen-Protokoll). In Saldo-Verlauf und
Buchungsliste (auch bei den anstehenden Terminen) wirken Umbuchungen wie
manuelle Übertragungen; Cashflow, Jahresübersicht, Kategorien-Diagramm und
Budgets lassen sie aus. Die Tabelle "Vorlagen" zeigt in der Spalte
Kategorie "Umbuchung → Zielkonto", der Konto-Filter findet eine Umbuchung
auch über ihr Zielkonto. Eine Vorlage kann zwischen Buchung und Umbuchung
umgestellt werden; das wirkt nur auf künftige Termine.

"Anpassen" im Plan-Buchungen-Protokoll ändert bei einer Übertragung nur
das Datum (sie bleibt Übertragung). "Daten zurücksetzen → Plan-Buchungen"
löscht solche verschobenen Übertragungen mit künftigem Datum mit. "Konten
löschen" stellt auch das Zielkonto von Umbuchungs-Vorlagen um; wären Konto
und Zielkonto danach gleich, wird die Vorlage deaktiviert (nicht gelöscht)
und lässt sich erst nach Wahl eines anderen Zielkontos wieder aktivieren.

Datenimport, Tab "Wiederkehrend": neue optionale Spalten "zielkonto"
(gefüllt = Umbuchungs-Vorlage) und "sparziel". Bei einer Umbuchung muss die
Kategorie leer sein oder "Umbuchung" lauten, Inflation und Dynamik bleiben
leer bzw. 0, sonst meldet die Zeile einen Fehler. In diesem Tab müssen
Konto und Zielkonto eindeutig sein (exakter Name oder ein einziger
Teiltreffer, sonst Fehler mit den passenden Kandidaten).

## Korrekturen in Version 1.10

**Inflations-Häkchen bei Vorlagen:** Bis 1.9.1 hat das Vorlagen-Formular
bei jedem Anlegen oder Ändern eine leere Dynamik mitgeschickt. Folge: Das
Häkchen "Inflations-abhängig" ging verloren (Spalte "Infl." leer), und
beim nächsten Start wurde die Scheindynamik wieder entfernt. Behoben; der
Server lehnt eine Dynamik ohne Prozentwert jetzt ab. **Bereits verlorene
Häkchen lassen sich nicht automatisch wiederherstellen:** Bitte bei den
betroffenen Vorlagen "Inflations-abhängig" selbst wieder setzen.

**Heutiges Datum:** Vorbelegungen ("heute") nutzen das lokale Datum. Bis
1.9.1 lieferten sie zwischen 0 und 1 Uhr (Sommerzeit 2 Uhr) den Vortag,
in der Schnellbuchung wurde dann auf den Vortag gebucht. Neu vorbelegt mit
heute: Saldo-Korrektur und Buchungsformular (auch nach dem Absenden).

**Saldo-Verlauf:** Bereits gebuchte Termine des laufenden Monats wurden in
allen Folgemonaten doppelt gezählt (z. B. Vorlage am 5., heute der 13.:
Prognose um einen Betrag zu niedrig). Die Prognose beginnt jetzt nach
heute und ordnet Termine nach ihrem tatsächlichen Zahlungsdatum
(Werktagsverschiebung) dem Monat zu, wie die echten Buchungen. Dadurch
kann ein Termin am 1. eines Monats, der auf ein Wochenende fällt, im
Vormonat erscheinen.

**Künftige Plan-Buchungen:** Manuell erfasste oder per "Anpassen"
verschobene Buchungen nach dem laufenden Monat fehlten bisher in
Saldo-Verlauf, Cashflow, Kategorien-Diagramm, Budget-Details und
Budget-Fix-Prognose. Sie zählen jetzt in ihrem Monat.

**Cashflow-Prognose brutto:** Prognosemonate zeigen Einnahmen und Ausgaben
jetzt getrennt (bisher saldiert, z. B. Einnahmen 905 €, Ausgaben 0 €).
Betrifft auch die Jahresübersicht.

**Budgets:** Die Fix-Prognose zählt Termine von morgen mit, der
Details-Verlauf Termine am 1. des Folgemonats (beide fielen bisher heraus).

**Buchungsliste:** Übertragungen zeigen in der Spalte Konto "Quelle →
Ziel".

**Kategorien:** Das Namensfeld (Anlegen und Ändern) ist für
Passwort-Manager gesperrt.

## Tilgungsplan: Sondertilgungen und Ablösung (Korrektur in Version 1.9.1)

Gebuchte Sondertilgungen senken die Restschuld im Tilgungsplan ab ihrem
Monat - überall, wo der Plan verwendet wird (Automatik für Zins-/
Tilgungsbuchungen, Detail-Diagramm, Saldo-Verlauf, Prognose,
Darlehen-Auswertung). Bei fester Rate bleibt die Rate gleich, das Darlehen
ist dadurch früher getilgt. Vorher wurden Sondertilgungen zwar gebucht,
flossen aber nie in den Plan ein. Außerdem tilgt der Plan nie mehr als die
Restschuld: Die letzte Rate ist entsprechend kleiner, danach entstehen
keine Buchungen mehr (vorher lief die volle Rate nach der Ablösung als
Tilgung weiter). Bereits gebuchte Raten bleiben unverändert.

## Auswertungen: Darlehen und Altersvorsorge (seit Version 1.9)

Der Bereich Auswertungen hat die Tabs "Allgemein" (bisheriger Inhalt),
"Darlehen" und "Altersvorsorge". Bis heute stammen die Werte aus den
gebuchten Zahlungen, danach aus dem Tilgungsplan bzw. der rechnerischen
Altersvorsorge-Projektion (als Prognose gekennzeichnet). Die Zuordnung zu
Jahren folgt dem tatsächlichen Zahlungsdatum nach Werktagsverschiebung.
Der Zeitraum-Filter wirkt auf Diagramme und Jahrestabelle, nicht auf
Kennzahlen und die Tabelle je Darlehen.

Darlehen: Kennzahlen (Restschuld heute, Restschuld Ende Zinsbindung,
bisher gezahlte Zinsen und Tilgung, noch anfallende Zinsen, Restschuld
Laufzeitende), Restschuld-Verlauf je Darlehen mit Markierung des
Zinsbindungsendes, Zins/Tilgung/Sondertilgung je Jahr als Diagramm und
Tabelle, sowie eine Tabelle je Darlehen (Darlehenssumme, noch nicht
ausgezahlt, Spaltengruppen "bisher" und "gesamte Laufzeit", Restschuld
heute und am Laufzeitende) mit Summenzeile ab zwei Darlehen. Künftige
Sondertilgungen sind unbekannt und nicht in der Prognose enthalten.

Altersvorsorge: Kennzahlen (bisherige und künftige Beiträge, monatliche
Rente und Einmalzahlungen garantiert/voraussichtlich, Rückkaufswerte rein
informativ, Hinweis auf Standmitteilungen älter als 14 Monate), Beiträge und
Auszahlungen je Jahr (voraussichtlich als heller Aufsatz), kumulierter
Verlauf mit Nulldurchgang ("ab wann rechnet sich der Vertrag") und
Jahrestabelle.

## Rentenhorizont 30 Jahre (seit Version 1.9)

Ohne Ende-Datum wird eine Rente gleitend 30 Jahre (bis 1.8: 20 Jahre) über
den heutigen Tag hinaus geplant - überall: Buchungsliste, Saldo-Verlauf,
Cashflow, Korridor und Altersvorsorge-Auswertung. Ein echtes Ende-Datum
ersetzt die Schätzung. Passend dazu berechnet die App die Feiertage für das
laufende und 30 weitere Jahre.

## Datumsfelder (seit Version 1.9)

Alle Datumsfelder lassen nur noch vierstellige Jahreszahlen zu (der
Browser begrenzt die Eingabe; der Server lehnt Daten außerhalb 1900-9999
zusätzlich mit einer Meldung ab). Vorher waren fünfstellige Jahre möglich,
die im schlimmsten Fall beim nächsten Programmstart die Automatik
(Generatoren) zum Absturz gebracht hätten. Der Bereich "Einzahlung" bei
Altersvorsorge wird ohne Häkchen "Es gibt eigene Einzahlungen" jetzt ganz
ausgeblendet.

## Daten zurücksetzen (seit Version 1.8)

Unter Administration → "Daten zurücksetzen" lassen sich Datenarten
getrennt anwählen und dauerhaft löschen: Konten leeren, Konten löschen,
Ist-Buchungen, Plan-Buchungen, Darlehen, Altersvorsorge und wiederkehrende
Buchungen. Das Fragezeichen neben jeder Auswahl erklärt, was genau
gelöscht wird. Personen, Kategorien, Budgets und Einstellungen bleiben
unberührt (ein Sparziel verliert beim Löschen von Konten lediglich sein
Trägerkonto bzw. wird auf das Zielkonto umgestellt).

Ablauf: Auswahl, dann ein Dialog mit allen betroffenen Datenarten und der
jeweiligen Anzahl, danach eine zweite Bestätigung mit nochmaliger
Übersicht und einer zufälligen Phrase, die eingetippt werden muss. Die
Phrase wird vom Server erzeugt, ist nur zehn Minuten gültig, an genau diese
Auswahl gebunden und einmalig verwendbar. Unmittelbar vor dem Löschen legt
die Anwendung automatisch ein Backup an (Administration → System →
Backups, Spalte "Beschreibung", z. B. "vor Löschung von: Ist-Buchungen").
Schlägt das Backup fehl, wird nichts gelöscht. Das Löschen selbst läuft in
einer einzigen Transaktion: ganz oder gar nicht.

Konten leeren löscht alle Buchungen (Ist, Plan, Übertragungen) und
Saldo-Korrekturen der gewählten Konten (Kontenauswahl per Häkchen); die
Konten bleiben bestehen. Übertragungen zu nicht gewählten Konten werden
dabei mitgelöscht und ändern dort den Saldo. Hängen an einem geleerten
Konto noch Vorlagen, Darlehen oder Altersvorsorge-Verträge, buchen diese
künftige Termine weiterhin - das Konto steht dann nur bis zum nächsten
fälligen Termin auf 0 € (der Bestätigungsdialog weist darauf hin).

Ist-Buchungen werden bis einschließlich eines wählbaren Datums gelöscht
(voreingestellt: heute). Mit ihnen werden alle Übertragungen bis zu diesem
Datum gelöscht; eine Übertragung wirkt auf beide beteiligten Konten.
Spätere Ist-Buchungen bleiben bestehen.

Konten löschen: Bei einer Teilauswahl wird ein Zielkonto abgefragt, auf das
alle Buchungen, wiederkehrenden Vorlagen, Altersvorsorge-Verträge sowie
Zahlungs- und Trägerkonten von Darlehen und Sparzielen aller gelöschten
Konten gemeinsam umgestellt werden. Übertragungen, die dadurch von einem
Konto auf sich selbst laufen würden, entfallen. Saldo-Korrekturen der
gelöschten Konten werden bewusst nicht übernommen, sondern gelöscht. Die
Summe der Kontostände kann sich dadurch ändern - etwa wenn der
Anfangsbestand eines Kontos per Saldo-Korrektur gesetzt wurde oder wenn
umgebuchte Buchungen vor der jüngsten Saldo-Korrektur des Zielkontos liegen
(sie zählen dort nicht mit, siehe Saldo-Korrektur-Regel). Der
Bestätigungsdialog nennt den Betrag dieser Änderung vorab. Werden alle Konten gelöscht, werden auch
alle zugehörigen Buchungen (Ist, Plan, Übertragungen) und Saldo-Korrekturen
gelöscht; dafür müssen zusätzlich "Wiederkehrende Buchungen" und
"Altersvorsorge" ausgewählt sein, weil beide zwingend ein Konto brauchen.

Darlehen, Altersvorsorge und wiederkehrende Buchungen löschen nur die
Verträge bzw. Vorlagen; bereits erzeugte Buchungen bleiben bestehen und
werden von der Quelle gelöst.

Einträge im Plan-Buchungen-Protokoll, deren Buchung gelöscht wurde, werden
mit entfernt (Einträge mit Status "gelöscht" bleiben erhalten).

Gelöschte automatische Buchungen entstehen nicht neu (siehe "Erzeugungsmarke").

## Erzeugungsmarke für automatische Buchungen (seit Version 1.8)

Wiederkehrende Vorlagen, Darlehen und Altersvorsorge-Verträge merken sich,
bis zu welchem Datum ihre Ist-Buchungen bereits erzeugt wurden ("erzeugt
bis"). Termine bis zu diesem Datum werden nie erneut gebucht. Dadurch
entstehen keine Duplikate mehr, wenn eine automatische Buchung im
Plan-Buchungen-Protokoll angepasst (anderes Datum) oder verworfen wurde;
vorher legte der nächste Programmstart den ursprünglichen Termin neu an.
Außerdem bleibt eine angepasste Buchung seit 1.8 erhalten: Eine alte
Migration löschte bis dahin bei jedem Start alle Plan-Buchungen mit
Vorlagen- oder Darlehens-Bezug - also auch angepasste automatische
Buchungen. Sie läuft jetzt nur noch ein einziges Mal.

Rückwirkende Änderungen buchen gezielt nur das neu entstandene Zeitfenster
nach: ein vorverlegtes Startdatum einer Vorlage (neuer bis alter Start), ein
vorverlegter Zinsbeginn eines Darlehens, eine nachträglich erfasste
Auszahlung vor der bisher ersten (Monate, die bisher ohne Restschuld und
damit ohne Zinsbuchung waren), bei Altersvorsorge ein vorverlegter
Beitragsbeginn, eine neu aktivierte Einzahlung oder ein verschobener
Rentenbeginn (Zeitraum zwischen altem und neuem Datum). Weil in diesen
Fenstern vorher keine Buchungen existierten, können angepasste oder
verworfene Buchungen dadurch nicht zurückkommen.

Bestehende Quellen starten nach dem Update mit leerer Marke: Der erste Lauf
arbeitet noch wie bisher und schließt Lücken (etwa wenn die App einige Tage
nicht lief), danach greift die Marke. Eine deaktivierte Vorlage bucht
nicht; wird sie wieder aktiviert, holt sie die Termine der Pause nach (wie
bisher).

## Buchungsliste: Herkunft (angepasst in Version 1.8)

"Nur automatisch" zeigt alle automatisch entstandenen Buchungen: aus
wiederkehrenden Vorlagen, Darlehensraten (Zinsen/Tilgung) und - seit 1.8 -
auch aus Altersvorsorge-Verträgen (diese erschienen vorher fälschlich unter
"manuell"). Darlehens-Auszahlungen und Sondertilgungen löst der Anwender
selbst aus; sie zählen deshalb zu "manuell", die Herkunft-Spalte kennzeichnet
sie aber weiterhin als "Darlehen".

## Sidebar-Reihenfolge (seit Version 1.6)

Unter Administration → "Menü-Reihenfolge" lässt sich festlegen, in
welcher Reihenfolge die Menüpunkte in der linken Seitenleiste erscheinen
und wo Trennlinien zwischen Gruppen sitzen (Pfeil-Buttons zum
Verschieben, Häkchen "Trenner davor" je Eintrag). "Start" (ganz oben)
und "Administration" (ganz unten, inklusive Systemmeldung und
Versionsnummer samt Versionsdatum) sind fest und nicht Teil dieser
Liste. Die Administration-Abschnitte selbst sind zum besseren Überblick
initial eingeklappt.

Seit Version 1.6.1 ist die Administration zusätzlich in Tabs
unterteilt (seit 1.8 mit drittem Tab "Daten zurücksetzen"): "Stammdaten" (Personen, Kategorien, Inflationsfaktor,
Datenimport, automatische Kategorisierung, Siri &amp; Schnellbuchung,
Vorzeichen-Prüfung, Feiertage) und "System" (Menü-Reihenfolge, Farben, Backups).

## Auswertungen filtern

Saldo-Verlauf und Cashflow lassen sich zusätzlich nach Konto und
Kategorie einschränken, die Jahresübersicht zusätzlich auch nach
Person. Ist eine Kategorie ausgewählt, wechselt der Saldo-Verlauf von
"echtem Kontostand" auf die kumulierte Teilsumme dieser Kategorie
(Start bei 0) - Darlehens-Restschuld und -Raten werden dabei
ausgeblendet, da sie sich fachlich keiner einzelnen Kategorie oder
Person zuordnen lassen. Ein Hinweistext in der Oberfläche macht diesen
Semantikwechsel kenntlich.

Der Zeithorizont-Auswahl steht neben den festen Zeiträumen (1/5/10/20/30
Jahre) zusätzlich "Benutzerdefiniert" zur Verfügung, das ein von/bis-
Datumsfeld einblendet.

Der Saldo-Verlauf unterscheidet bis zu 14 Konten mit klar
unterscheidbaren Farben, bevor sich Farben wiederholen. Das Häkchen
"Altersvorsorge-Korridor" blendet zusätzlich eine gestrichelte Linie
ein, die zeigt, wie sich der Gesamtsaldo entwickeln würde, wenn ab jetzt
bei allen aktiven Altersvorsorge-Verträgen die "voraussichtlichen" statt
der "garantierten" Auszahlungsbeträge eintreten (nur bei aktivem
Kategorie-Filter ausgeblendet, da die Teilsumme dann kein echter
Kontostand mehr ist). Bugfix Version 1.6.3: Die Prognose für Monate ab
heute hatte den Effekt aktiver Altersvorsorge-Beiträge/-Auszahlungen
komplett übersehen (nur wiederkehrende Buchungen und Darlehensraten
flossen ein) - dadurch war insbesondere der Korridor verzerrt. Das
betraf Saldo-Verlauf und Cashflow gleichermaßen und ist behoben.

Die Einheit steht seit Version 1.6.3 standardmäßig auf k€ (statt €).

Ein Diagramm "Kategorien" zeigt einen einzelnen, mittig bei 0
beginnenden Balken: Einnahmen wachsen nach links, Ausgaben (invertiert,
als positive Werte) nach rechts, kumuliert über den gesamten gewählten
Zeitraum. Liegt ein Teil des Zeitraums in der Zukunft, fließen auch
anstehende (noch nicht gebuchte) wiederkehrende Buchungen,
Darlehensraten und Altersvorsorge-Termine mit ein - dieselbe Logik wie
bei Saldo-Verlauf und Cashflow. Kategorien ohne Einnahme/Ausgabe-
Einordnung (z. B. Darlehens-Zinsen/-Tilgung, Umbuchungen) bleiben außen
vor. Das Diagramm reagiert auf dieselben Zeitraum-/Konto-/Kategorie-
Filter wie die übrigen Diagramme dieser Seite.

Seit Version 1.6.2 gruppiert das Diagramm "intelligent" statt starr
nach Haupt- oder Unterkategorie: Ausgangspunkt ist jede Kategorie, auf
die im Zeitraum direkt gebucht wurde. Hat auch ihre direkte
Oberkategorie eine eigene, zu den Filtern passende Buchung, gilt diese
Oberkategorie offenbar selbst als genutzte Sammelkategorie - dann
werden beide zu einem Segment zusammengefasst (z. B. "Wohnen" mit
eigenen Buchungen neben "Strom"/"Nebenkosten"). Andernfalls bleibt die
Unterkategorie ihr eigenes Segment (z. B. "Kraftstoff"/"KFZ-Unterhalt"
einzeln, solange "Mobilität" selbst nicht direkt bebucht ist).

## Jahresübersicht: Zeitraum (seit Version 1.6.3)

Die Jahresübersicht lässt sich zwischen "Rollierend 12 Monate" (neuer
Standard - die letzten 12 Monate bis einschließlich des laufenden
Monats, unabhängig vom Kalenderjahr) und "Kalenderjahr" (bisheriges
Verhalten, mit Jahresauswahl) umschalten. Die Berechnung (Ist bis heute,
danach rechnerische Prognose) ist in beiden Modi identisch, nur der
betrachtete Zeitraum unterscheidet sich.

## Jahresübersicht: Nach Hauptkategorie (angepasst in Version 1.6.4)

Die Tabelle "Nach Hauptkategorie" gruppiert seit Version 1.6.4 eine
Ebene unterhalb von "Einnahmen"/"Ausgaben" (also z. B. "Wohnen",
"Mobilität", "Gehalt & Lohn" statt nur "Einnahmen"/"Ausgaben" insgesamt)
- das liefert eine aussagekräftigere Aufschlüsselung als zuvor. Sie
reagiert wie gehabt auf die Filter oben auf der Seite (Zeitraum, Konto,
Kategorie, Person).

## Budgets: Übersicht und Details in eigenen Tabs (seit Version 1.6.4)

Der Budgets-Bereich ist jetzt in drei Tabs unterteilt: "Neues Budget"
(das bisherige Anlage-/Bearbeiten-Formular), "Übersicht" und "Details".

"Übersicht" zeigt oben das Budget-Übersicht-Diagramm - jetzt als
Säulendiagramm (vorher horizontal, und vorher auf der
Auswertungen-Seite): eine Säule je aktivem Ausgabe-/Einnahme-Budget
(Sparziele ausgenommen), Höhe = Verbrauch in % des verfügbaren Betrags
der laufenden Periode (inklusive Übertrag), Farbe nach Ampelstatus.
Darunter folgt die Liste aller Budgets; der frühere "Details"-Knopf je
Budget-Karte ist entfallen (die Detailansicht lebt jetzt im eigenen
Tab), "Ändern"/"Löschen" sind rechtsbündig ausgerichtet.

"Details" bietet eine DropDown-Auswahl der Budget-Positionen (Standard:
"Alle" - alle aktiven Ausgabe-/Einnahme-Budgets zusammen). Das Diagramm
darunter rechnet - anders als die frühere periodenbasierte Historie -
in Kalendermonaten, damit "Alle" und ein einzelnes Budget auf derselben
Zeitachse vergleichbar sind: bei "Alle" wird je Kalendermonat über alle
Budget-Kategorien summiert. Bis einschließlich des aktuellen Monats
zeigt es echte Ist-/Plan-Buchungen, danach die rechnerische Prognose aus
wiederkehrenden Buchungen und Darlehensraten (heller dargestellt). Der
Zeitraum-Filter steht standardmäßig auf 25 Monate (die letzten 12, der
aktuelle und die kommenden 12 Monate), lässt sich aber auf einen
benutzerdefinierten Von-/Bis-Monat umstellen. Unterhalb des Diagramms
erscheint bei Auswahl eines einzelnen Budgets (nicht bei "Alle", da dort
fachlich uneindeutig wäre, welche Buchung zu welchem Budget gehört) die
Liste der zugehörigen Plan-/Ist-Buchungen im gewählten Zeitraum.

## Altersvorsorge: optionale Einzahlung (seit Version 1.5)

Nicht jede Altersvorsorge wird selbst bespart - bei arbeitgeber- oder
gehaltsfinanzierten Modellen (z. B. Direktzusage, Entgeltumwandlung
ohne eigenen Beitrag) gibt es aus Sicht des Haushalts keine Einzahlung,
nur eine spätere Auszahlung. Das Formular ist deshalb in zwei Blöcke
"Einzahlung" und "Auszahlung" getrennt; ein Häkchen "Es gibt eigene
Einzahlungen" (standardmäßig nicht gesetzt) schaltet die Beitragsfelder
frei. Ohne Häkchen entstehen ausschließlich Plan-/Ist-Buchungen für die
Auszahlungsphase. Neue Verträge schlagen für Beitrags- bzw.
Auszahlungs-Kategorie automatisch die mitgelieferten Kategorien
"Altersvorsorge" bzw. "Rente" vor.

## Altersvorsorge: Tabelle und Inflationsfaktor (seit Version 1.6.3)

Die Liste "Alle Altersvorsorgen" ist eine sortier- und filterbare
Tabelle (Filter nach Bezeichnung/Anbieter, Person, Status; Spaltenköpfe
zum Sortieren anklicken) statt einer Kartenliste. Das separate
Verlaufsdiagramm je Vertrag (inkl. Korridor-Schalter) entfällt - der
Altersvorsorge-Korridor lässt sich weiterhin zentral im Saldo-Verlauf
der Auswertungen einblenden.

Die Auszahlungsphase kennt jetzt ein Häkchen "Inflationsfaktor": ist es
gesetzt, werden die noch nicht fälligen (projizierten) Auszahlungs-
beträge in Buchungsliste, Kategorien-Diagramm, Saldo-Verlauf/Cashflow
und Budget-Prognose zinseszinsartig mit dem globalen Inflationsfaktor
(Administration → Stammdaten → "Inflationsfaktor") ab heute hochgerechnet.
Bereits real gebuchte Zahlungen bleiben davon unberührt - sie nutzen wie
gehabt immer den unveränderten garantierten Betrag. Dieselbe Checkbox
gab es bei wiederkehrenden Buchungen ("Inflations-abhängig") technisch
schon seit Version 1.4, war aber nie tatsächlich verdrahtet - das ist
mit Version 1.6.3 nachgeholt.

## Budgets: Inflationsfaktor, Übertrag-Deckel, Prognose-Bezeichnungen (seit Version 1.6.3)

Ein Häkchen "Inflationsfaktor" am Budget (nicht bei Sparzielen) rechnet
den Periodenbetrag mit dem globalen Inflationsfaktor seit dem
Startdatum des Budgets hoch - sinnvoll für langfristig laufende Budgets,
deren Betrag sonst über die Jahre real an Wert verliert.

Beim Übertrag "Fortlaufend ansparen" (kumuliert) lässt sich zusätzlich
ein optionaler "Deckel" (€) angeben: er begrenzt nur den positiven
Übertrag (den angesparten Puffer) nach oben, damit er bei selten
abgerufenen Budgets nicht unbegrenzt wächst - typisches Beispiel: ein
Auto-Budget von 250 €/Monat, das neben den laufenden Benzinkosten auch
den zweijährlichen TÜV und unregelmäßige Reparaturen aus demselben
Puffer bestreiten soll, aber nicht endlos weiterwächst, wenn lange
nichts anfällt. Eine mitgeschleppte Überschreitung (negativer Übertrag)
wird davon nicht gekappt. Ist ein Puffer aktiv, zeigt die Budget-Karte
zusätzlich "Puffer X von max. Y" an.

Die bisherigen Prognose-Bezeichnungen "Verfahren B"/"Verfahren D" heißen
jetzt "Fix-Prognose" (Ist-Verbrauch plus bereits bekannte, noch offene
feste Buchungen - keine Schätzung) bzw. "Trend-Prognose" (zusätzlich ein
geschätzter Anteil aus dem Median der bisherigen Perioden, sobald genug
Historie vorliegt) - ein kleines "?"-Symbol daneben erklärt den
Unterschied.

Die Kategorie-Auswahl im Budget-Formular schränkt sich automatisch auf
zum gewählten Typ (Einnahme/Ausgabe) passende Kategorien ein.

## Kategorien bearbeiten (seit Version 1.6.2)

Im Admin-Bereich unter "Kategorien" lassen sich selbst angelegte
Kategorien nachträglich umbenennen, verschieben (Oberkategorie ändern)
und löschen - der "Ändern"-Knopf befüllt dasselbe Formular wie beim
Anlegen. Fest vorgegebene, von der Fachlogik verwendete Kategorien
(Einnahmen, Ausgaben, Altersvorsorge, Rente, die Darlehens-Kategorien
sowie Umbuchung) sind als "fest vorgegeben" gekennzeichnet und lassen
sich weder ändern noch löschen. Eine Kategorie mit Unterkategorien oder
mit noch vorhandenen Buchungen/Vorlagen/Verträgen lässt sich ebenfalls
nicht löschen - die Oberfläche meldet den Grund.

## GUI-Farben (seit Version 1.6.2)

Unter Administration → System → "Farben" lassen sich die grundlegenden
Farben der Oberfläche anpassen (Sidebar/Buttons, Akzentfarbe,
positive/negative Beträge, Hintergrund). Nicht angepasste Zwischentöne
(z. B. der dunklere Sidebar-Farbverlauf) werden automatisch aus der
gewählten Farbe abgeleitet. Die Änderung wirkt sofort und für alle
Geräte, die die Seite neu laden; "Auf Standard zurücksetzen" stellt die
eingebaute Farbgebung wieder her.

## Kategorie-Typen und Vorzeichen

Neue Kategorien erben Einnahme/Ausgabe automatisch vom obersten Knoten
ihrer Elternkette – eine Unterkategorie von "Ausgaben" wird also über
beliebig viele Ebenen hinweg zur Ausgabe. Unterhalb der systemseitig
neutralen Knoten "Darlehen" und "Umbuchung" bleibt der Typ bewusst leer,
dort ergibt ein Vorzeichen-Erbe fachlich keinen Sinn.

Bei wiederkehrenden Vorlagen wird das Vorzeichen seit Version 1.4 sofort
beim Anlegen bzw. Ändern aus dem Kategorietyp abgeleitet (nicht erst
beim nächsten Programmstart). Bereits gebuchte Ist-Buchungen bleiben
davon unberührt und verlangen weiterhin eine ausdrückliche Bestätigung
über Admin → "Vorzeichen prüfen".

## Export und Import (seit Version 2.0)

Unter Administration → Stammdaten → „Export & Import (XLSX)“ lädt
„Export herunterladen“ den aktuellen Datenbestand als xlsx-Datei: je
ein Tab für Personen, Konten, Kategorien, Regeln, Budget, Darlehen,
Darlehen-Auszahlungen, Altersvorsorge, Wiederkehrend und Buchungen
(Buchungen optional nur für einen Zeitraum). Die Datei lässt sich
bearbeiten und wieder hochladen. Das ist der einzige Importweg; der
bisherige reine Neuanlage-Import entfällt.

Ändern: Werte in der Zeile überschreiben. Neu: Zeile ohne id anfügen.
Löschen: in der Spalte „aktion“ löschen eintragen. Zeilen, die in der
Datei fehlen, bleiben unverändert. Konten lassen sich per Datei nicht
löschen (dafür Daten zurücksetzen), Personen werden deaktiviert, eine
Kategorie in Benutzung bleibt stehen (Fehler). Kategorien stehen als
vollständiger Pfad („Ausgaben > Wohnen > Strom“) in der Datei; beim
Hochladen genügt auch ein eindeutiger Name. Konten, Personen, Sparziele
und Darlehen werden über den Namen oder einen eindeutigen Namensteil
aufgelöst, Mehrdeutiges ist ein Fehler. Grau hinterlegte Spalten dienen
nur zur Information.

Nach dem Hochladen zeigt die App zuerst eine Vorschau (neu, geändert,
gelöscht, unverändert, Fehler je Tab sowie die einzelnen Änderungen).
Enthält die Datei einen Fehler, wird nichts übernommen. „Übernehmen“
legt vorher ein Backup an und führt dann alles in einem Schritt aus. Die
verborgene Spalte _pruefwert erkennt, ob ein Eintrag nach dem Export in
der App geändert wurde; dann meldet die Zeile einen Konflikt und die
Datei muss neu exportiert werden. Eine Vorschau bleibt 10 Minuten gültig.

Ändert die Datei den Rentenbeginn einer Altersvorsorge, gilt dasselbe wie
im Formular: Buchungen in der falschen Phase werden gelöscht (die
Vorschau nennt die Anzahl), betroffene Zeilen im Tab Buchungen werden als
„entfällt“ übersprungen.

Ältere Vorlagen ohne Spalte id funktionieren weiter und legen nur neu
an. Für eine CSV-Datei (genau ein Bereich) muss der Bereich beim
Hochladen gewählt werden. Zahlen dürfen deutsch (1.234,56) oder englisch
(1234.56) geschrieben sein.

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

Seit 3.0 liegen dort je nach Schutz zusätzlich `schutz.json` (Hashes und
verpackte Schlüssel von Sperre und Verschlüsselung), `schutz_zaehler.json`
(Fehlversuche), `auszug.json` (Namen von Konten, Kategorien, Sparzielen bei
eingeschalteter Verschlüsselung) und der Ordner `stapel/` (vorgemerkte
Buchungen, verschlüsselt). Ohne `schutz.json` lässt sich eine verschlüsselte
`finanzdaten.db` nur mit einem verschlüsselten Download (.fvdb) und der
Passphrase oder dem Wiederherstellungsschlüssel wieder öffnen.

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
Eingabemaske. Alle Felder sind ohne Aufklappen sichtbar, in der Reihenfolge
Betrag, Konto, Beschreibung, Kategorie, dann Buchungstyp und Datum
nebeneinander. Zielkonto und Sparziel erscheinen nur bei einer Übertragung.
Beim Tippen der Beschreibung wählt die Seite die Kategorie über die
Kategorisierungsregeln vor, eine selbst gewählte Kategorie hat Vorrang. Ohne
Kategorie bucht die Seite nicht, außer bei einer Übertragung. Die Eingabetaste
springt ins nächste Feld, gebucht wird nur mit "Speichern" oder "Speichern &
weiter". Beide leeren danach Betrag, Beschreibung und Kategorie, "Speichern &
weiter" setzt den Cursor zurück in den Betrag. Die Meldung "Gebucht" steht
oberhalb des Formulars und bleibt bis zum nächsten Betrag (Begründungen in
„Neu in Version 2.6.3“).

Komfortfunktionen: Das zuletzt genutzte Konto wird im Browser gemerkt und
vorbelegt. Im Betragsfeld darf gerechnet werden ("12,50+8,30" ergibt 20,80).
Existiert am selben Tag auf demselben Konto bereits ein gleicher Betrag,
erscheint ein Hinweis auf ein mögliches Duplikat, ohne die Buchung zu
blockieren. Ist das Datum ein Feiertag, steht ein Hinweis unter dem Feld.

Für einen eigenen Eintrag in der Home-Assistant-Seitenleiste (seit 2.7 als
Integration über HACS) und für Siri-Kurzbefehle siehe
`ha-integration/README-HA-Integration.md`.

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

## Neu in Version 3.0

**Sperre und Verschlüsselung (Issue #5, Wunsch des Anwenders):** Zwei
Schutzfunktionen, unabhängig voneinander ein- und ausschaltbar in der
Administration, Reiter „Sicherheit“. Beide sind nach dem Update aus. Ohne
beides verhält sich 3.0 wie 2.7 (Nachweis unten). Schutzziele laut Planung:
Mitnutzer am Gerät, andere Home-Assistant-Benutzer, Diebstahl oder Verlust des
Geräts. Nicht Ziel: Administratoren mit Zugang zum Terminal, solange die
Datenbank entsperrt ist.

*Wer ändern darf.* Nur Administratoren von Home Assistant, bei eingeschalteter
Sperre zusätzlich nur freigegebene mit gültiger Anmeldung. Das Adminrecht
kommt aus dem Header `X-Remote-User-Groups` mit der Gruppe `system-admin`
(`HOMEASSISTANT_GROUP_ID_ADMIN` in `supervisor/const.py`). Den Header setzt
der Supervisor erst seit Commit 3fbb083b vom 21.10.2026 (PR #7398), enthalten
ab Tag 2026.10.5. Ob diese Version schon im stabilen Kanal ist, war beim Bau
nicht sicher. Der Header fehlt auch, wenn der Supervisor die Gruppen nicht
kennt (Sitzung angelegt, während Core nicht erreichbar war). Fehlt er, gilt
der Benutzer nicht als Admin, die Einstellungen sind nur lesbar und nennen den
Grund. Eine Abfrage bei Core als Ersatz wurde verworfen, weil das Add-on dafür
Adminrechte bei Core bräuchte, genau das, was PR #7398 vermeiden will. Die
Benutzerkennung kommt aus `X-Remote-User-Id`, `X-Remote-User-Name` und
`X-Remote-User-Display-Name`. Der Supervisor ersetzt diese Header immer, ein
Browser kann sie nicht unterschieben (`_init_header` in
`supervisor/api/ingress.py`). Das gilt nur über Ingress. Deshalb lässt sich die
Sperre nur einschalten, wenn `herkunft_pruefen` auf `sperren` steht (Befund Q).
Die Schutzeinstellungen stehen in `/data/schutz.json`, nicht in den
Add-on-Optionen und nicht in der Datenbank, weil sie vor dem Entsperren lesbar
sein müssen. Darin stehen nur Hashes und verpackte Schlüssel.

*Sperre.* `SchutzMiddleware` in `main.py` prüft jede Anfrage im Server. Frei
sind nur die Seiten, Skripte, Hilfe, Feiertagsliste und die Endpunkte zum
Anmelden und Entsperren. Ohne gültige Sitzung kommt 401 mit `schutz=code`,
für Benutzer außerhalb der Freigabeliste 403. Der Code ist PIN, Passwort oder
Muster auf einem 3×3-Raster, gespeichert als Argon2id-Hash von `art:code`
(`argon2-cffi`, Standardwerte). Mindestlängen PIN 6, Passwort 8, Muster 5
Punkte, in der Administration erhöhbar, nie niedriger. Nach dem richtigen Code
gibt es ein zufälliges Token (24 Byte), das der Browser im Header
`X-Finanz-Sitzung` mitschickt. Es liegt nur im Arbeitsspeicher des Servers und
im `sessionStorage` des Tabs. Ein Cookie wurde verworfen: Mit dem Pfad `/` hätte
der Supervisor es an alle anderen Add-ons weitergereicht, die über Ingress
aufgerufen werden. Fehlversuche: ab dem 5. Fehlversuch 1 Minute Wartezeit,
verdoppelnd bis höchstens 1 Stunde, nach 5 bis 20 Fehlversuchen (einstellbar)
oder nie die Sperre bis zur Freigabe. Die Zähler stehen in
`schutz_zaehler.json` und überdauern Neustarts. Versuche während der
Wartezeit zählen nicht. Freigabe durch einen anderen freigegebenen Benutzer,
mit der Passphrase der Verschlüsselung oder mit dem Wiederherstellungsschlüssel
der Sperre. Eine Add-on-Option zum Zurücksetzen wurde verworfen (Entscheidung
41). Damit ein einzelner Benutzer ohne Verschlüsselung nicht dauerhaft
aussperrt ist, erzeugt das Einschalten der Sperre einen eigenen
Wiederherstellungsschlüssel (160 Bit), gespeichert nur als SHA-256 mit Salz.
Weitere Benutzer öffnen die Finanzverwaltung einmal, erscheinen dann in der
Auswahl und legen nach der Freigabe ihren Code selbst fest. Bekannte Benutzer
merkt sich das Programm nur bei eingeschalteter Sperre, ohne Sperre legt 3.0
keine Datei an. Automatische Sperre nach Untätigkeit, Vorgabe 5 Minuten, im
Browser über Tippen, Klicken und Tasten gemessen, im Server über die letzte
Anfrage. Bei Tätigkeit ohne Anfrage hält `/api/schutz/puls` die Sitzung höchstens
einmal je Minute. Wahlweise sperrt auch das Verlassen des Tabs oder der App
(`visibilitychange`).

Schnellbuchung „ohne Code nur erfassen“: eigene Endpunkte unter
`/api/erfassen/`, Antwort ohne gespeicherte Daten, keine letzten Buchungen,
kein Hinweis auf mögliche Doppelbuchungen. Siri bei Sperre: nur von
172.30.32.1 (Home Assistant), Antwort nur „Betrag Euro gebucht.“, Fehler ohne
gespeicherte Namen (Entscheidung 45).

*Verschlüsselung.* SQLCipher 4.12 über `sqlcipher3-wheels` 0.5.7 mit einem
zufälligen Datenschlüssel (32 Byte) als Rohschlüssel. Er liegt zweimal
verpackt (AES-256-GCM) in `schutz.json`: mit der Passphrase über Argon2id
(t = 3, 64 MiB, p = 4, die zweite Empfehlung aus RFC 9106) und mit dem
Wiederherstellungsschlüssel (160 Bit, Base32 in Vierergruppen, HKDF-SHA256).
Eine neue Passphrase verpackt nur neu, die Datei bleibt bitgleich. Dadurch
bleiben Backups und verschlüsselte Downloads mit dem Wiederherstellungsschlüssel
lesbar. Der Schlüssel liegt nur im Arbeitsspeicher. Nach jedem Start ist die
Datenbank zu, `startup.ausfuehren()` (Migrationen, fällige Buchungen,
Plan → Ist, Backup) läuft erst beim Entsperren. Falsche Passphrasen bekommen
dieselbe Wartezeit wie Codes, aber keine dauerhafte Sperre. `db.verbindung()`
öffnet bei eingeschalteter Verschlüsselung mit SQLCipher, sonst wie bisher mit
`sqlite3`. Weil `sqlcipher3` eigene Fehlerklassen hat, fangen
`buchungen.kategorie_loeschen` und der XLSX-Import jetzt die Klassen beider
Treiber (`db.FEHLER`, `db.INTEGRITAETSFEHLER`).

Einschalten auf echten Daten (Entscheidung 44): Vorher muss die Datenbank
unverschlüsselt heruntergeladen worden sein (in den letzten 30 Minuten), der
Wiederherstellungsschlüssel abgetippt und eine Phrase bestätigt werden. Dann
Backup, verschlüsselte Kopien von Datenbank und allen Backups mit
`sqlcipher_export`, jede Kopie mit dem Schlüssel aus der Passphrase und mit dem
aus dem Wiederherstellungsschlüssel geöffnet und über eine Prüfsumme aus Schema
und allen Zeilen mit dem Original verglichen. Erst danach werden die Schlüssel
gespeichert und die Dateien getauscht. Bricht der Vorgang zwischen Speichern
und Tauschen ab, verschlüsselt das nächste Entsperren die übrigen Dateien
nach. Während der Umstellung antworten andere Anfragen mit 503. Restrisiko:
Auf Speicherkarten und SSDs können Reste der unverschlüsselten Datei bleiben,
bis der Speicher neu beschrieben wird. Ausschalten entschlüsselt alles mit
denselben Prüfungen.

Stapel: Ist die Datenbank zu, legen Siri und die Schnellbuchung Buchungen als
einzelne Dateien in `/data/stapel/` ab, sofort verschlüsselt mit einem
eigenen X25519-Schlüssel je Eintrag, HKDF-SHA256 und AES-256-GCM. Der
private Stapelschlüssel liegt mit dem Datenschlüssel verpackt in
`schutz.json`. Beim Entsperren bucht das Programm die Einträge in der
Reihenfolge der Erfassung mit denselben Prüfungen wie Siri und die
Schnellbuchung. Was scheitert, kommt in die Klärliste (neue Tabelle
`klaerliste`). Die Kennung jedes Eintrags wird mit der Buchung in
`stapel_erledigt` festgeschrieben, ein Absturz vor dem Löschen der Datei führt
nicht zu einer doppelten Buchung. Konten, Kategorien, Sparziele und das
Bundesland stehen als `auszug.json` unverschlüsselt daneben (Entscheidung 29),
erneuert nach jeder erfolgreichen Änderung. Die Regeln gehören nicht dazu,
deshalb verlangen Siri und die Schnellbuchung im verschlossenen Zustand immer
eine Kategorie. Entsperrt gilt bei Siri wie bisher die Kategorisierung über
Regeln (Entscheidung 49).

Downloads: Bei eingeschalteter Verschlüsselung liefert „Datenbank
herunterladen“ eine `.fvdb`-Datei: Kennung `FVDB1`, die beiden verpackten
Schlüssel, dann die SQLCipher-Datei. Öffnen lässt sie sich mit der Passphrase
vom Zeitpunkt des Downloads oder dem Wiederherstellungsschlüssel. Der
XLSX-Export bekommt ein Excel-Kennwort (`msoffcrypto-tool` 6.0.0, dort als
experimentell gekennzeichnet, mit Excel selbst nicht geprüft), das bei jedem
Export eingegeben wird und mindestens so lang sein muss wie die
Passphrase. Unverschlüsselt geht beides nur mit Phrase, die Kopie wird nach
dem Senden gelöscht. Damit Kennwort und Phrase nie in einer Adresse stehen
(das Zugriffsprotokoll von Uvicorn schreibt Adressen mit), bereitet
`POST /api/admin/download` den Inhalt vor und gibt ein einmaliges Ticket für
2 Minuten. Der Browser lädt dann über `GET /api/download/<ticket>` wie bisher
über einen Link. Ohne Sperre und Verschlüsselung bleiben die Links von 2.7.
„Datenbank wiederherstellen“ öffnet `.fvdb` mit Passphrase oder Schlüssel, der
Import öffnet XLSX mit Kennwort. Eine eingespielte Datei übernimmt den
Schutzzustand der Installation, sie liegt schon im Zwischenordner im
passenden Zustand.

*Pakete.* Für Alpine mit Python 3.12 gibt es fertige Pakete für aarch64 und
amd64 (`pip download --only-binary=:all: --platform musllinux_1_2_aarch64`
bzw. `musllinux_1_2_x86_64`, am 28.10.2026): `sqlcipher3-wheels` 0.5.7,
`cryptography` 50.0.2, `argon2-cffi` 25.1.0 mit `argon2-cffi-bindings`
26.1.0, `cffi` 2.1.1, `msoffcrypto-tool` 6.0.0 mit `olefile` 0.47. Der
Docker-Bau selbst ließ sich in der Testumgebung nicht ausführen.

**Messung** (`tests/v30_messung.py`, Testdaten mit 20 000 zusätzlichen
Buchungen, 2,3 MB, Testrechner Intel Xeon 2,1 GHz mit 2 Kernen): Argon2id
allein 123 ms, Entsperren mit Programmstart 158 ms, Einschalten 1,7 s.
Abfragen mit Verschlüsselung um 25 bis 70 Prozent langsamer, im Mittel
10 bis 20 ms mehr je Anfrage, weil jede Anfrage eine Verbindung öffnet und die
Seiten entschlüsselt. Der Saldo-Verlauf über zwei Jahre (rund 1 s) ändert
sich nicht messbar. Schätzung für den Raspberry Pi 5, nicht gemessen:
Faktor 1,5 bis 3, also Entsperren unter 1 s, Einschalten einige Sekunden,
Abfragen 20 bis 60 ms länger.

**Befund V (gefunden beim Testlauf vor dem Bau, besteht seit 2.0 bzw.
1.10):** Zwei Testerwartungen hingen am Testtag. Die Vorlage „Gehalt“ der
Testdaten hat den 28. als Tag, am 28.10.2026 wurde sie beim Start gebucht.
`funktion_test.py` erwartete danach einen festen Saldo des Girokontos,
`v2_test.py` noch eine anstehende Einnahme im laufenden Monat. Am Code lag es
nicht (gleicher Code bestand am Vortag). Behebung freigegeben: `funktion`
prüft die Saldoänderung durch die Umbuchungsvorlage, `v2` legt für den Rest
des Monats eine eigene Einnahme am letzten Bankarbeitstag an.

**Befund W (gefunden beim Bau, folgt aus Entscheidung 45, noch nicht
entschieden):** Die freiwilligen `rest`-Sensoren der Siri-Anleitung („Finanz
Kategorien“, „Finanz Konten“) fragen `/api/siri/favoriten` und `/api/konten`
ohne Benutzer ab. Bei eingeschalteter Sperre bekommen sie 403, bei
verschlossener Datenbank 423, Home Assistant meldet dann alle 5 Minuten einen
Fehler. Siri bucht weiter, wenn Konto und Kategorie im Kurzbefehl stehen. Die
Hilfe nennt das. Eine Ausnahme für diese Abfragen würde Konten- und
Kategorienamen als Sensorwerte für alle Home-Assistant-Benutzer sichtbar
machen.

**Nachweis „ohne Schutz wie 2.7“:** Alle Testreihen der Vorversionen laufen
unverändert. `v30_test.py` startet dazu denselben Datenbestand einmal mit dem
Code von 2.7 und einmal mit 3.0 und vergleicht 29 Abfragen, Siri- und
Formularbuchung, Download, Export und Vorlage (gleich bis auf den Zeitstempel
`erstellt_am` der neuen Buchungen) und prüft, dass 3.0 ohne Schutz keine
Datei anlegt, auch mit Benutzer-Headern. `upgrade_test.py` zieht eine
Datenbank mit dem Code von 2.7 hoch, startet 3.0, vergleicht alle Tabellen,
schaltet auf den hochgezogenen Daten die Verschlüsselung ein, startet neu,
entsperrt und schaltet wieder aus: Inhalt aller Tabellen gleich. Seit 3.0
läuft der Upgrade-Test in `alle_tests.py` mit (Code von 2.7 aus Commit
5e7b84c per `git archive`).

Tests: `v30_test.py` (fachlich, mit Fehlerfällen, eingefrorene Uhr der Sperre
über `schutzdatei.uhr`), `ui30_test.py` (Oberfläche mit eigenen Serverstarts
und Neustarts, Ingress-Header über Playwright, iPhone-Ansicht). Geprüft unter
anderem: keine bekannten Klartexte in Datenbank, Backups, Stapel und
Download, kein Schlüssel, keine Passphrase und kein Kennwort in Dateien oder
Protokoll, alle 106 geschützten Endpunkte ohne Code abgewiesen, Wartezeiten
1, 2, 4, 8, 16 Minuten und Deckel 1 Stunde, Stapel über einen Neustart, Absturz
zwischen Buchen und Löschen, Klärliste, Wiederherstellungsschlüssel, Ändern der
Passphrase, Download in beiden Formen, XLSX mit Kennwort hin und zurück.
Gegenprobe: Die Klartextprüfung findet in der Datenbank von 2.7 alle Proben.
Nicht geprüft: Docker-Bau, echte Ingress-Header eines Supervisors 2026.10.5,
Downloads in der Companion-App, Öffnen der Kennwort-XLSX in Excel.

## Neu in Version 2.7

**Schnellbuchung in der Seitenleiste als Integration über HACS (Wunsch des
Anwenders):** Bis 2.6.4 musste man `finanzen-schnellbuchung.js` von Hand nach
`config/www` kopieren, `panel_custom` in die `configuration.yaml` eintragen und
bei jeder neuen Fassung die Datei erneut kopieren und `?v=` hochzählen. Wer nur
über GitHub installiert, hatte keine Anleitung, woher die Datei kommt, und ein
Add-on-Update brachte sie nie mit. Erwogen wurden drei Wege: nur besser
dokumentieren, das Add-on legt die Datei selbst ab (braucht Schreibrecht auf
die ganze HA-Konfiguration), oder eine eigene Integration. Entschieden ist die
Integration, weil HACS sie installiert und aktualisiert und die
`configuration.yaml` unberührt bleibt.

Aufbau: `custom_components/finanzverwaltung/` im selben Repository, `hacs.json`
im Wurzelordner, Markenbild in `brand/icon.png` (Home Assistant liest es seit
der Brands-Komponente aus dem Integrationsordner, HACS verlangt es). Die
Integration meldet die Panel-Datei unter `/finanzverwaltung_dateien/` an
(`hass.http.async_register_static_paths`) und trägt das Panel mit
`panel_custom.async_register_panel` ein. Diese Funktion beschreibt die
Entwicklerdoku nicht, sie ist aber im Quelltext von Home Assistant vorhanden und
wird von verbreiteten Integrationen genutzt. Die Versionsnummer aus dem
Manifest hängt als `?v=` an der Adresse, dadurch laden Browser und App nach
einem Update die neue Fassung ohne Handarbeit. Einrichtung ohne Eingaben über
„Geräte & Dienste“, nur einmal möglich, ohne Supervisor bricht sie mit Hinweis
ab.

Übergang: Das Panel hat die neue Adresse `/finanzen-schnellbuchung` und den
neuen Elementnamen `finanzverwaltung-schnellbuchung`. Home Assistant lässt
keine zwei Panels mit derselben Adresse zu, und welches zuerst geladen wird,
hängt von der Startreihenfolge ab. Ein gleicher Elementname hätte zudem die
alte Fassung festhalten können, wenn beide Panels in einer Sitzung geöffnet
werden. Solange der alte Eintrag aus der `configuration.yaml` (erkannt am
Elementnamen `finanzen-schnellbuchung-panel` oder an der Datei
`finanzen-schnellbuchung.js`) besteht, zeigt Home Assistant unter
„Reparaturen“ einen Hinweis mit den Schritten. Geprüft wird nach dem Start von
Home Assistant.

`ha-integration/finanzen-schnellbuchung.js` entfällt, ebenso `ui264_test.py`
(ersetzt durch `ui27_test.py`). Wer nicht umsteigt, behält seine alte Kopie
in `config/www`, bekommt aber keine Korrekturen mehr. Ohne HACS lässt sich der
Ordner `custom_components/finanzverwaltung` von Hand kopieren. Zu jeder Version
gibt es ab jetzt ein GitHub-Release mit Tag `vX.Y`, damit HACS Updates mit
Versionsnummer anzeigt.

**Befund S (gefunden beim Lesen des Quelltexts von Home Assistant für die
Integration, besteht seit 2.5):** Benutzer ohne Administratorrechte sahen im
Panel nur die Fehlermeldung, wenn das Add-on aus einem Repository installiert
ist. Ursache: Das Panel fragte zuerst `local_finanzverwaltung` ab und suchte
danach in der Liste aller Add-ons nach `…_finanzverwaltung`. Ohne Adminrecht
erlaubt Home Assistant über `supervisor/api` aber nur die Ingress-Sitzung und
die Abfrage eines namentlich bekannten Add-ons (`WS_NO_ADMIN_ENDPOINTS` in
`homeassistant/components/hassio/websocket_api.py`), nicht die Liste.
Behebung: Die Integration ermittelt die Kennung beim Start auf dem Server
(Supervisor-Client, bei mehreren Treffern zählt nur ein laufendes Add-on) und
gibt sie dem Panel in `panel.config.kennung` mit. Die alte Suche bleibt als
Rückfall für Administratoren.

**Befund T (gefunden ebenda, besteht seit Einführung des Panels):** Das Panel
legte keine eigene Ingress-Sitzung an. Der Supervisor lässt eine Sitzung nach
15 Minuten ohne Anfrage verfallen (`supervisor/ingress.py`). Wer
„Schnellbuchung“ öffnete, ohne in den 15 Minuten davor „Finanzen“ geöffnet zu
haben, oder das Panel länger offen liegen ließ, bekam „401: Unauthorized“ oder
ein scheiterndes Speichern. Am System des Anwenders nicht beobachtet, aus dem
Quelltext abgeleitet. Behebung nach dem Vorbild des Add-on-Panels von Home
Assistant (`src/panels/app/ha-panel-app.ts` im Frontend): Beim Öffnen und beim
Zurückkehren eine neue Sitzung anlegen und als Cookie für
`/api/hassio_ingress/` setzen, jede Minute und beim Zurückholen der App
verlängern, eine abgelaufene ersetzen. Zuerst mit den neueren Befehlen
`supervisor/ingress/session` und `supervisor/ingress/validate_session`, bei
„unknown_command“ über `supervisor/api`. Das Cookie ist im Panel nicht lesbar
(eigener Pfad), deshalb merkt sich das Panel seine Sitzung selbst.

Tests: `v27_test.py` (16 Prüfungen mit `pytest-homeassistant-custom-component`
0.13.316, also Home Assistant 2026.2.3): Einrichtung mit Fehlerfällen, Panel
mit Adresse, Version und Kennung, Kennungswahl, Auslieferung der Datei,
Hinweis auf den alten Eintrag auch beim Start, Entfernen und Neuladen,
Pflichtdateien, gleiche Versionen in Add-on, Hilfe und Integration. Beim
Schreiben fiel dort auf, dass ein Startlistener nach dem Auslösen beim
Entfernen einen Fehler warf, deshalb `async_at_started`. `ui27_test.py`
(24 Prüfungen) bettet das Panel wie Home Assistant ein: Höhe und alle Felder
wie seit 2.6.4, ohne Adminrecht, Sitzung mit Uhr-Attrappe, ältere
Home-Assistant-Version. Gegenprobe mit dem Panel von 2.6.4: 16 von 24
Prüfungen schlagen fehl. Das sind die zu Befund T und alle, die ohne Adminrecht
laden (Befund S, darunter auch Höhe und Felder). Die angegebene
Mindestversion 2025.1 in `hacs.json` ist aus den genutzten Schnittstellen
abgeleitet, getestet ist nur 2026.2.3. Die deutschen Beschriftungen in HACS in
der Anleitung sind nicht am System geprüft.

**Befund U (gefunden beim Durchsehen der Texte für 2.7):** Zwei Texte waren
veraltet. `README.md` nannte die Feiertage als nur für Nordrhein-Westfalen
gültig, seit 2.6 ist das Bundesland wählbar. Der Abschnitt „Schnellbuchung“
oben beschrieb noch „Weitere Angaben“ und die gemerkte Kategorie, also den
Stand vor 2.6.3. Beide Texte sind nachgezogen, das Programm ändert sich nicht.

## Neu in Version 2.6.4

**Issue #4, eigentliche Ursache: Schnellbuchung in der Seitenleiste nur 150
Pixel hoch (vom Anwender nach 2.6.3 erneut gemeldet):** Im eigenen Panel
(`ha-integration/finanzen-schnellbuchung.js`) war sichtbar nur das Feld
„Betrag (€)“, darunter eine graue Fläche. Erst nach der Eingabetaste rollte die
Seite im Panel weiter, und dann ebenfalls abgeschnitten. Ursache: Das Panel
setzte `:host { height: 100% }` und das iframe auf `flex: 1`. Home Assistant
gibt dem Behälter eines eigenen Panels aber keine feste Höhe (aus dem
Verhalten geschlossen, im Quelltext von Home Assistant nicht geprüft), damit
lief die Prozentangabe ins Leere und das iframe fiel auf seine Standardhöhe von
150 Pixeln zurück. Das war schon der Kern der ersten Meldung von #4: Im
150-Pixel-Fenster war nur der Betrag zu sehen, die Eingabetaste buchte (seit
2.6.3 behoben) und leerte das Feld. Die Analyse in 2.6.3 war unvollständig,
weil die Seite nur direkt und nicht eingebettet getestet wurde.

Behebung im Panel: Höhe per CSS `100vh`/`100dvh` als Rückfall und per Skript
genau als Fensterhöhe abzüglich der Oberkante des Panels, nachgezogen bei
Größenänderung. Die Datei muss der Anwender erneut nach `config/www`
kopieren; `module_url` bekommt dafür den Zusatz `?v=2.6.4`, damit Browser und
App die neue Datei laden (Wirkung auf den Zwischenspeicher der App
ungeprüft). Hilfe und `README-HA-Integration.md` beschreiben das Aktualisieren.

Tests: neue Reihe `ui264_test.py` baut die Einbettung nach (Behälter ohne
Höhe, mit voller Höhe, mit Kopfleiste darüber, Desktop und iPhone,
Größenänderung) mit einer Attrappe der Supervisor-Abfrage. Gegenprobe mit dem
Panel von 2.6.3: 9 von 25 Prüfungen schlagen fehl, genau die Behälter ohne
feste Höhe. Lehre: Seiten, die eingebettet laufen, auch eingebettet testen.

## Neu in Version 2.6.3

**Issue #4, Schnellbuchung bucht bei der Eingabetaste (gemeldet vom Anwender,
besteht seit Einführung der Schnellbuchung):** Nach Eingabe des Betrags
verschwand dieser wieder, der Cursor blieb im Feld „Betrag (€)“. Ursache:
Alle Felder lagen in einem `<form>` mit einem Submit-Knopf, die Eingabetaste
bzw. „Return“ der Bildschirmtastatur schickte das Formular implizit ab. Es
entstand jedes Mal eine Buchung mit vorbelegtem Konto, vorbelegter Kategorie
und ohne Beschreibung. Die Bestätigung stand unterhalb der Knöpfe, hinter der
Tastatur, und verschwand nach 8 Sekunden. Behebung: Die Eingabetaste springt
ins nächste sichtbare Feld (im letzten Feld schließt sie die Tastatur),
„Speichern“ ist kein Submit-Knopf mehr, ein Submit-Ereignis bucht nie. Die
Meldung steht oberhalb des Formulars und bleibt, bis der nächste Betrag
eingegeben wird. Eine Warnung verschwindet bei der nächsten Eingabe.

**Befund R (gefunden beim Nachstellen von #4):** Die Kategorie-Auswahl der
Schnellbuchung hatte keine leere Option. Ohne gemerkte Kategorie stand die
erste Kategorie der Liste darin (in den Testdaten die Wurzel „Ausgaben“).
Weil dadurch immer eine Kategorie mitging, griffen die Kategorisierungsregeln
in der Schnellbuchung nie, der Server wendet sie nur ohne Kategorie an.
Behebung: Option „– bitte wählen –“, ohne Kategorie bucht die Seite nicht
(außer bei Übertragungen) und springt mit Hinweis zur Kategorie. Die Seite
merkt sich nur noch das Konto, nicht mehr die Kategorie.

**Schnellbuchung: alle Felder auf einen Blick, Kategorie aus der
Beschreibung:** „Weitere Angaben“ entfällt. Reihenfolge: Betrag, Konto,
Beschreibung, Kategorie, dann Buchungstyp und Datum nebeneinander; Zielkonto
und Sparziel erscheinen nur bei „Übertragung“, weil sie nur dort gelten. Beim
Tippen der Beschreibung fragt die Seite nach 250 ms `GET
/api/regeln/vorschlag` ab (erste passende Regel nach Priorität, Teiltext ohne
Groß- und Kleinschreibung) und setzt die Kategorie mit dem Hinweis
„automatisch erkannt“. Entscheidungen: Hat der Anwender die Kategorie selbst
gewählt, ändert die Regel sie nicht mehr; „– bitte wählen –“ gibt sie wieder
frei. Passt keine Regel mehr, fällt eine automatisch gesetzte Kategorie auf
„– bitte wählen –“ zurück. Kategorienamen werden nicht durchsucht, Grundlage
sind nur die Regeln. Veraltete Antworten werden über eine laufende Nummer
verworfen. Nach dem Buchen wird die Kategorie zurückgesetzt.

Tests: neue Reihen `v263_test.py` (Vorschlags-Schnittstelle, Priorität,
leere Eingabe, Sonderzeichen, Server-Regel bei Buchung ohne Kategorie) und
`ui263_test.py` (iPhone-Ansicht: Sichtbarkeit und Reihenfolge, #4, Befund R,
Vorauswahl und Vorrang, Meldung, Übertragung). Gegenprobe von `ui263` mit dem
Code von 2.6.2 scheitert wie erwartet. Das Bildwerkzeug legt dafür eine
Demo-Regel „Wochenmarkt“ an.

## Neu in Version 2.6.2

**Befund Q (gefunden bei der Recherche zu Verschlüsselung und Passwortschutz,
besteht seit der ersten Add-on-Version):** Der Server lauscht im Container auf
0.0.0.0:8099 und prüfte die Herkunft der Anfragen nicht. Aus dem LAN ist er
nicht erreichbar, weil `config.yaml` weder `host_network` noch `ports` setzt.
Im internen Netz von Home Assistant konnte aber jedes andere Add-on über den
Hostnamen (zum Beispiel `e396af1a-finanzverwaltung:8099`) alle Daten lesen
und ändern, ohne Anmeldung. Die Add-on-Doku empfiehlt bei Ingress, nur
Verbindungen von 172.30.32.2 anzunehmen. Ein vergleichbarer, schwererer Fall
war CVE-2026-59177 im ESPHome-Add-on (dort sogar aus dem LAN erreichbar).

Behebung: Middleware `HerkunftPruefenMiddleware` mit der Add-on-Option
„Zugriff im internen Netz prüfen“ (`herkunft_pruefen`):
- `protokoll` (Standard in 2.6.2): nichts sperren, jede neue Herkunftsadresse
  einmal im Add-on-Protokoll („Zugriff von … auf …: erlaubt“ bzw. „wäre
  gesperrt“),
- `sperren`: nur Ingress (172.30.32.2), Home Assistant selbst (172.30.32.1,
  für `rest_command` und `rest` der Siri-Anbindung) und lokale Aufrufe
  zulassen, alles andere mit 403 „Zugriff nur über Home Assistant.“,
- `aus`: keine Prüfung (auch der Desktop-Modus und die Tests ohne Option).

Dass Home Assistant selbst intern mit 172.30.32.1 ankommt, ist eine Annahme
(ungeprüft). Deshalb startet 2.6.2 mit `protokoll`: erst im Protokoll die
Adressen von Seitenleiste und Siri prüfen, dann auf `sperren` stellen.

**Einschätzung Verschlüsselung (Stand 26.10.2026):** Zugriff ist über die
Anmeldung bei Home Assistant geschützt (Ingress). Die Übertragung von außen
sichert Home Assistant (HTTPS bzw. Home Assistant Cloud), intern läuft HTTP
im Docker-Netz desselben Geräts. Die Datenpartition von Home Assistant OS ist
nach der Dokumentation des Partitionslayouts nicht verschlüsselt (keine
Erwähnung, ungeprüft). Automatische Backups von Home Assistant sind seit
2025.1 verschlüsselt und enthalten `/data` des Add-ons. Unverschlüsselt sind
die add-on-eigenen Backups unter `/data/Backups` und „Datenbank
herunterladen“. Eine Verschlüsselung der Datenbank selbst ginge mit SQLCipher
(`sqlcipher3-wheels`, Wheels für musllinux aarch64), offen ist die
Schlüsselfrage (Schlüssel in den Optionen schützt die SD-Karte nicht, ein
Passwort bei jedem Start sperrt Automatik und Siri bis zur Eingabe).
Entscheidung steht aus.

**Hilfe:** neues Unterkapitel „Feiertage und Buchungstermine“
(`admin.feiertage-termine`) erklärt Feiertage des Bundeslands (nur Markierung)
gegenüber Bankfeiertagen (Verschiebung) mit Beispielen. Das Kapitel
„Feiertage“ verweist darauf, Doppeltes ist dort entfernt. „Siri: Wenn etwas
nicht klappt“ nennt die Meldung „Zugriff nur über Home Assistant“.

Tests: neue Reihe `v262_test.py` (alle drei Modi, Ingress, Home Assistant,
lokal, fremdes Add-on, Siri-Buchung, Protokollzeilen, Hilfe). Gegenprobe mit
dem Code von 2.6.1 scheitert wie erwartet.

## Neu in Version 2.6.1

**Befund P (gefunden beim Oberflächentest zu 2.6, besteht seit mindestens
2.5):** Das Formular „Neue Buchung“ schickte bei Typ „Ist“ und „Plan“ das
Zielkonto aus dem verborgenen Auswahlfeld mit (das Feld hat immer einen Wert,
das erste Konto), und `buchung_anlegen()` speicherte es ungeprüft. Beim Ändern
leerte `buchung_bearbeiten()` es dagegen schon richtig. Folgen: Anzeige „A → B“
in der Buchungsliste, Kontofilter und Suche zeigten die Buchung zusätzlich
beim fremden Konto, der Export füllte die Spalte „zielkonto“, und eine solche
Zeile ließ sich nach Änderung nicht wieder importieren. Salden und
Auswertungen waren nicht betroffen, weil sie den Zugang nur bei Typ
„Uebertragung“ zählen.

Behebung: `buchung_anlegen()` verwirft das Zielkonto außer bei Übertragungen
(wie `buchung_bearbeiten()`), das Formular sendet es nur bei Übertragungen.
Eine einmalige Korrektur beim ersten Start (Merker
`korrektur_zielkonto_v261_erledigt`) leert es bei allen bestehenden Ist- und
Plan-Buchungen. Gibt es etwas zu korrigieren, legt sie vorher das Backup „vor
Korrektur Zielkonto 2.6.1“ an. Start-Status und Protokoll nennen die Anzahl.
Lehre: verborgene Formularfelder nur senden, wenn sie fachlich gelten, und im
Server beim Anlegen genauso prüfen wie beim Ändern.

Tests: neue Reihe `v261_test.py` (Korrektur, Backup, Merker, Anlegen je Typ,
Kontofilter, zweiter Start), Gegenprobe mit dem Code von 2.6 scheitert wie
erwartet. `ui26_test.py` prüft die Buchungsliste, `upgrade_test.py` legt im
Lauf der Vorversion eine fehlerhafte Ist-Buchung an.

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

**Befund P:** siehe „Neu in Version 2.6.1“.

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

# Home-Assistant-Integration

Zwei optionale Ergänzungen: ein eigener Seitenleisten-Eintrag für die
Schnellbuchung (Integration über HACS) und Siri-Kurzbefehle fürs iPhone/iPad.

---

## 1. Seitenleisten-Eintrag "Schnellbuchung"

Seit Version 2.7 legt die Integration **Finanzverwaltung** den Eintrag an.
Sie wird über HACS installiert und aktualisiert. Die `configuration.yaml`
bleibt unberührt.

### Voraussetzungen

- Home Assistant OS (die Schnellbuchung bettet das Add-on über Ingress ein,
  dafür braucht es den HA Supervisor). Supervised hat ihn ebenfalls, wird von
  Home Assistant aber seit HA Core 2025.12 nicht mehr unterstützt. Container
  und Core haben keine Add-ons.
- HA Core 2025.1 oder neuer (Mindestangabe in `hacs.json`, getestet mit
  HA Core 2026.2.3)
- das Add-on „Private Finanzverwaltung“, installiert und gestartet
- HACS (Gemeinschaftsprojekt, nicht Teil von Home Assistant, siehe
  [hacs.xyz](https://hacs.xyz))

### Installation über HACS

1. HACS öffnen, oben rechts das Menü (drei Punkte) und
   **Benutzerdefinierte Repositorys** (englisch „Custom repositories“) wählen.
2. Als Repository `https://github.com/koch-r-de/ha-finanzverwaltung`
   eintragen, als Typ **Integration** wählen und hinzufügen.
3. In HACS nach **Finanzverwaltung Schnellbuchung** suchen, öffnen und
   **Herunterladen** wählen. Die angebotene neueste Version bestätigen.
4. Home Assistant neu starten: **Einstellungen → System → ⏻ → Home Assistant
   neu starten**.
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen**, nach
   **Finanzverwaltung** suchen und bestätigen. Eingaben sind keine nötig.
6. In der Seitenleiste erscheint **Schnellbuchung**. In der App auf dem Handy
   erscheint der Eintrag nach dem nächsten Öffnen der App.

### Aktualisieren

Neue Versionen meldet HACS unter **Einstellungen → Updates**. Update
installieren und Home Assistant neu starten. Browser und App laden die neue
Fassung von selbst, weil die Integration die Versionsnummer an die Adresse der
Panel-Datei hängt.

Add-on und Integration sind zwei getrennte Updates: das Add-on im App-Store,
die Integration in HACS. Beide tragen dieselbe Versionsnummer.

### Umstieg vom YAML-Eintrag

Bis Version 2.6.4 kam der Eintrag über `panel_custom` in der
`configuration.yaml` und die Datei `config/www/finanzen-schnellbuchung.js`.
So wird umgestellt:

1. Die Integration wie oben installieren und einrichten. Bis zum nächsten
   Schritt stehen zwei Einträge „Schnellbuchung“ in der Seitenleiste, und unter
   **Einstellungen → System → Reparaturen** steht ein Hinweis auf den alten
   Eintrag.
2. In der `configuration.yaml` unter `panel_custom:` den Eintrag mit
   `name: finanzen-schnellbuchung-panel` löschen. War er der einzige, auch die
   Zeile `panel_custom:` selbst.
3. Die Datei `config/www/finanzen-schnellbuchung.js` löschen.
4. Home Assistant neu starten. Der alte Eintrag und der Hinweis verschwinden.

Die Schnellbuchung hat jetzt die Adresse `/finanzen-schnellbuchung` statt
`/schnellbuchung`. Ein Lesezeichen darauf bitte anpassen.

### Ohne HACS

Den Ordner `custom_components/finanzverwaltung` aus dem Repository nach
`config/custom_components/finanzverwaltung` kopieren, etwa über die
Samba-Freigabe, dann weiter mit Schritt 4 der Installation. Für ein Update
den Ordner ersetzen und neu starten. HACS meldet dann keine Updates.

### Gut zu wissen

- Die Schnellbuchung funktioniert auch für Benutzer ohne Administratorrechte.
- Die Integration findet das Add-on beim Start von Home Assistant selbst, ob
  es lokal oder aus einem Repository installiert ist. Wurde das Add-on neu
  oder aus einem anderen Repository installiert, Home Assistant einmal neu
  starten.
- Die Seite hält ihre Ingress-Sitzung selbst am Leben. Sie bleibt also auch
  benutzbar, wenn sie länger offen liegt.
- Entfernen: **Einstellungen → Geräte & Dienste → Finanzverwaltung →
  Löschen**, danach die Integration in HACS entfernen. Die Daten des Add-ons
  berührt das nicht.

---

## 2. Siri-Kurzbefehle

### Voraussetzung: Long-Lived Access Token

1. In Home Assistant unten links auf den eigenen Benutzernamen klicken
2. Reiter **Sicherheit** → ganz unten **"Langlebige Zugangstoken"**
3. **"Token erstellen"**, Name z. B. `Siri Finanzen`
4. Den angezeigten Token **sofort kopieren** – er wird nur einmal gezeigt

### Brücke in configuration.yaml anlegen

Wichtig: Die Ingress-Adresse des Add-ons lässt sich **nicht** direkt von
Siri aufrufen – Ingress arbeitet mit der Browser-Sitzung, ein Token
genügt dort nicht. Der Weg führt deshalb über einen `rest_command` in
Home Assistant, den Siri über die offizielle HA-API auslöst.

In `config/configuration.yaml` anhängen:

```yaml
rest_command:
  finanz_buchung:
    url: "http://local-finanzverwaltung:8099/api/siri/buchung"
    method: POST
    content_type: "application/json"
    payload: >-
      {"betrag": {{ betrag }},
       "kategorie": "{{ kategorie | default('') }}",
       "konto": "{{ konto | default('') }}",
       "beschreibung": "{{ beschreibung | default('') }}"}
```

Danach **Einstellungen → System → ⏻ → Home Assistant neu starten**.

Kurz testen lässt sich das unter **Entwicklerwerkzeuge → Aktionen** mit
der Aktion `rest_command.finanz_buchung` und diesen Daten:

```yaml
betrag: 12.50
kategorie: Lebensmittel
beschreibung: Test aus HA
```

### Kurzbefehl anlegen (iPhone/iPad)

App **Kurzbefehle** → **+** → **Aktion hinzufügen** → **"Inhalte von URL abrufen"**

| Feld | Wert |
|---|---|
| URL | `http://homeassistant.local:8123/api/services/rest_command/finanz_buchung` |
| Methode | `POST` |
| Header `Authorization` | `Bearer <dein Token>` |
| Header `Content-Type` | `application/json` |
| Anfragetext | JSON (siehe unten) |

**JSON-Anfragetext:**

```json
{
  "betrag": 12.50,
  "kategorie": "Lebensmittel",
  "beschreibung": "Bäckerei"
}
```

Pflicht sind `betrag` und `konto`, die übrigen Felder sind optional:

- **konto** – Pflicht (seit 1.3.0 gibt es kein Standardkonto mehr). Der
  exakte Name genügt ohne Rücksicht auf Groß-/Kleinschreibung; ein
  unvollständiger Name nur, wenn er eindeutig ist ("spar" findet
  "Sparkonto", "giro" bei zwei Girokonten nicht). Mehrdeutige oder
  unbekannte Angaben ergeben eine klare Fehlermeldung samt Kandidaten -
  nie eine Buchung auf einem womöglich falschen Konto.
- **kategorie** – dieselbe Regel wie beim Konto (exakt, sonst eindeutiger
  Teiltreffer, sonst Fehlermeldung). Fehlt sie ganz, greifen die
  Kategorisierungs-Regeln aus dem Admin-Bereich anhand der Beschreibung;
  eine angegebene, aber unbekannte Kategorie fällt seit 1.8 NICHT mehr
  still auf diese Regeln zurück.
- **datum** – Format `2026-08-05`, Standard ist heute.

### Betrag und Kategorie abfragen lassen

Für einen flexiblen Kurzbefehl vor der URL-Aktion einfügen:

1. **"Nach Eingabe fragen"** → Frage: *"Welcher Betrag?"*, Typ: Zahl
2. **"Aus Menü auswählen"** → die Siri-Favoriten als Einträge (im
   Admin-Bereich der App unter *Siri & Schnellbuchung* festlegen, max. 10)

Beide Werte dann im JSON-Anfragetext als Variablen einsetzen.

Kurzbefehl umbenennen in z. B. *"Ausgabe buchen"* – Siri startet ihn
dann mit **"Hey Siri, Ausgabe buchen"**.

### Wichtig: Erreichbarkeit

Bei euch ist der externe Zugriff deaktiviert. Die Kurzbefehle
funktionieren deshalb **nur im heimischen WLAN**. Unterwegs schlägt die
URL-Abfrage fehl – der Kurzbefehl sollte das abfangen (Aktion **"Wenn"**
auf das Ergebnis prüfen und sonst eine Meldung ausgeben).

**Für Zugriff von unterwegs** gibt es zwei Wege:

- **Nabu Casa Cloud** (Einstellungen → Home Assistant Cloud,
  kostenpflichtiges Abo): einfachste Variante, HA kümmert sich um
  Zertifikate und Erreichbarkeit. Die URL im Kurzbefehl wird dann die
  Nabu-Casa-Adresse statt `homeassistant.local`.
- **Eigener VPN-Zugang** (z. B. WireGuard auf der FritzBox oder als
  HA-Add-on): kostenlos, technisch aufwändiger, dafür bleibt alles im
  eigenen Netz.

Solange keins von beidem eingerichtet ist, bleibt die Schnellbuchung
über die Seitenleiste im WLAN die zuverlässigste Variante.

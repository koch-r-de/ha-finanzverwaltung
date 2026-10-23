# Home-Assistant-Integration

Zwei optionale Ergänzungen: ein eigener Seitenleisten-Eintrag für die
Schnellbuchung und Siri-Kurzbefehle fürs iPhone/iPad.

---

## 1. Seitenleisten-Eintrag "Schnellbuchung"

### Dateien kopieren

Über die Samba-Freigabe `\\<HA-IP>\config\`:

1. Ordner `www` anlegen, falls noch nicht vorhanden
2. `finanzen-schnellbuchung.js` aus diesem Ordner nach `config/www/` kopieren

### configuration.yaml ergänzen

In `config/configuration.yaml` anhängen:

```yaml
panel_custom:
  - name: finanzen-schnellbuchung-panel
    sidebar_title: Schnellbuchung
    sidebar_icon: mdi:cash-plus
    url_path: schnellbuchung
    module_url: /local/finanzen-schnellbuchung.js
    embed_iframe: false
    require_admin: false
```

Danach **Einstellungen → System → ⏻ → Home Assistant neu starten**.
Der Eintrag "Schnellbuchung" erscheint anschließend in der Seitenleiste.

### Warum das so gebaut ist

Die Ingress-URL des Add-ons enthält ein Token, das sich bei einer
Neuinstallation ändert. Das Panel ermittelt die URL deshalb zur
Laufzeit über die Supervisor-API, statt sie fest einzutragen – der
Seitenleisten-Eintrag überlebt damit jede Neuinstallation.

Das Panel sucht zuerst `local_finanzverwaltung` (lokal installiert) und
dann jedes Add-on, dessen Kennung auf `_finanzverwaltung` endet (aus einem
Repository installiert, z. B. `a1b2c3d4_finanzverwaltung`). Zeigt die Seite
trotzdem eine Fehlermeldung, in `finanzen-schnellbuchung.js` die Konstante
`ADDON_SLUG` ganz oben auf die Kennung setzen. Sie steht in der Adresszeile
des Browsers auf der Seite der App (`…/addon/<kennung>/info`).

Für Siri gilt dasselbe: Der Rechnername in den Adressen ist die Kennung mit
Bindestrich statt Unterstrich, also `local-finanzverwaltung` oder z. B.
`a1b2c3d4-finanzverwaltung`.

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

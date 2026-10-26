-- Schema: Private Finanzverwaltung
-- SQLite

PRAGMA foreign_keys = ON;

-- ─── Personen ────────────────────────────────────────────────────────
-- Für die Trennung von Konten, Wiederkehrend und Altersvorsorge nach
-- Person (z. B. bei gemeinsamer Haushaltsführung). Jede der drei
-- Bereiche trägt eine EIGENE, unabhängige person_id - ein gemeinsames
-- Konto kann also wiederkehrende Buchungen unterschiedlicher Personen
-- enthalten.
CREATE TABLE IF NOT EXISTS personen (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL,
    farbe  TEXT,
    aktiv  INTEGER NOT NULL DEFAULT 1
);

-- ─── Konten ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS konten (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    typ               TEXT NOT NULL CHECK (typ IN ('Girokonto','Sparkonto','Kreditkarte','Bargeld')),
    eroeffnungsdatum  DATE NOT NULL,
    person_id         INTEGER REFERENCES personen(id),
    in_gesamtsaldo    INTEGER NOT NULL DEFAULT 1,
    aktiv             INTEGER NOT NULL DEFAULT 1,
    farbe             TEXT
);

CREATE TABLE IF NOT EXISTS saldo_korrekturen (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    konto_id    INTEGER NOT NULL REFERENCES konten(id) ON DELETE CASCADE,
    datum       DATE NOT NULL,
    saldo       REAL NOT NULL,
    kommentar   TEXT
);

-- ─── Kategorien (Baumstruktur, beliebige Tiefe) ────────────────────────
-- system_key: stabiler Schlüssel für von der Fachlogik referenzierte
-- Kategorien. NIE über feste IDs referenzieren - IDs können in einer
-- gewachsenen Datenbank bereits durch eigene Kategorien belegt sein.
CREATE TABLE IF NOT EXISTS kategorien (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    parent_id   INTEGER REFERENCES kategorien(id) ON DELETE CASCADE,
    typ         TEXT CHECK (typ IN ('einnahme','ausgabe') OR typ IS NULL),
    system_key  TEXT UNIQUE,
    siri_favorit INTEGER NOT NULL DEFAULT 0
);

-- ─── Automatische Kategorisierung ───────────────────────────────────
-- Textregeln: enthält die Beschreibung einer Buchung das Muster, wird
-- die Kategorie automatisch vorgeschlagen/gesetzt (z. B. "REWE" ->
-- Lebensmittel). Reine Textsuche, ohne KI.
CREATE TABLE IF NOT EXISTS kategorie_regeln (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    muster       TEXT NOT NULL,
    kategorie_id INTEGER NOT NULL REFERENCES kategorien(id) ON DELETE CASCADE,
    prioritaet   INTEGER NOT NULL DEFAULT 100,
    aktiv        INTEGER NOT NULL DEFAULT 1
);

-- ─── Darlehen ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS darlehen (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    bezeichnung           TEXT NOT NULL,
    zinssatz              REAL NOT NULL,
    zinsbeginn            DATE NOT NULL,
    tilgungsbeginn        DATE NOT NULL,
    laufzeit_jahre        INTEGER NOT NULL,
    ende_zinsbindung      DATE NOT NULL,
    anschlusszinssatz     REAL NOT NULL,
    raten_modus           TEXT NOT NULL CHECK (raten_modus IN ('tilgungssatz','feste_rate')),
    tilgungssatz          REAL,
    feste_rate            REAL,
    anschluss_feste_rate  REAL,
    zahlungskonto_id      INTEGER REFERENCES konten(id),
    person_id             INTEGER REFERENCES personen(id),
    erzeugt_bis           DATE,  -- seit v1.8, siehe wiederkehrende_buchungen.erzeugt_bis
    darlehenssumme        REAL   -- seit v1.9: vertraglich vereinbarte Summe (Differenz zu den erfassten Auszahlungen)
);

CREATE TABLE IF NOT EXISTS darlehen_auszahlungen (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    darlehen_id  INTEGER NOT NULL REFERENCES darlehen(id) ON DELETE CASCADE,
    datum        DATE NOT NULL,
    betrag       REAL NOT NULL
);

-- ─── Wiederkehrende Buchungen ───────────────────────────────────────
-- Dynamik: vertraglich bekannte Steigerung (z. B. Prämie +3 % alle
-- 2 Jahre). Wirkt ECHT auf die erzeugten Beträge, kumuliert, jeweils
-- zum Jahrestag der Vorlage. Schließt inflationsflag gegenseitig aus,
-- da sonst in der Auswertung doppelt gerechnet würde.
CREATE TABLE IF NOT EXISTS wiederkehrende_buchungen (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    konto_id               INTEGER NOT NULL REFERENCES konten(id),
    person_id              INTEGER REFERENCES personen(id),
    betrag                 REAL NOT NULL,
    kategorie_id           INTEGER NOT NULL REFERENCES kategorien(id),
    beschreibung           TEXT,
    intervall              TEXT NOT NULL CHECK (intervall IN ('monatlich','quartalsweise','halbjaehrlich','jaehrlich')),
    tag_des_monats         INTEGER NOT NULL,
    monat                  INTEGER,
    startdatum             DATE NOT NULL,
    enddatum               DATE,
    inflationsflag         INTEGER NOT NULL DEFAULT 0,
    dynamik_aktiv          INTEGER NOT NULL DEFAULT 0,
    dynamik_rhythmus_jahre INTEGER,
    dynamik_prozent        REAL,
    dynamik_startjahr      INTEGER,
    darlehen_id            INTEGER REFERENCES darlehen(id),
    aktiv                  INTEGER NOT NULL DEFAULT 1,
    erzeugt_bis            DATE,  -- seit v1.8: Ist-Buchungen bis einschließlich diesem Datum erzeugt
    -- seit v1.10: gesetzt = Umbuchungs-Vorlage (Übertragung konto_id -> zielkonto_id,
    -- Kategorie fest "Umbuchung", Betrag ohne Vorzeichen, ohne Inflation/Dynamik)
    zielkonto_id           INTEGER REFERENCES konten(id),
    sparziel_id            INTEGER REFERENCES budgets(id)   -- seit v1.10, nur bei Umbuchung
);

-- ─── Altersvorsorge ─────────────────────────────────────────────────
-- Eigener Bereich (kein Untertyp von wiederkehrende_buchungen), da zwei
-- gegenläufige Buchungsströme entstehen: Beitragsphase (Ausgabe, bis
-- Rentenbeginn) und Auszahlungsphase (Einnahme, ab Rentenbeginn).
-- hat_einzahlung: bei arbeitgeber-/gehaltsfinanzierten Modellen gibt es
-- keine eigene Einzahlung - dann bleiben alle beitrag_*-Felder leer und
-- es werden nur Auszahlungs-Buchungen erzeugt (seit v1.5).
CREATE TABLE IF NOT EXISTS altersvorsorge (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    bezeichnung                 TEXT NOT NULL,
    anbieter                    TEXT,
    zahlungskonto_id            INTEGER NOT NULL REFERENCES konten(id),
    person_id                   INTEGER REFERENCES personen(id),
    stand_datum                 DATE NOT NULL,

    hat_einzahlung              INTEGER NOT NULL DEFAULT 1,

    -- Beitragsphase (Ausgabe) - Pflicht nur, wenn hat_einzahlung = 1
    beitrag_kategorie_id        INTEGER REFERENCES kategorien(id),
    beitrag_betrag              REAL,
    beitrag_intervall           TEXT CHECK (beitrag_intervall IN ('monatlich','quartalsweise','halbjaehrlich','jaehrlich') OR beitrag_intervall IS NULL),
    beitrag_tag_des_monats      INTEGER,
    beitrag_monat                INTEGER,
    beitrag_startdatum          DATE,
    beitrag_dynamik_aktiv       INTEGER NOT NULL DEFAULT 0,
    beitrag_dynamik_rhythmus_jahre INTEGER,
    beitrag_dynamik_prozent     REAL,
    beitrag_dynamik_startjahr   INTEGER,

    -- Auszahlungsphase (Einnahme) - Rentenbeginn ist die Phasengrenze
    rentenbeginn                 DATE NOT NULL,
    ende_datum                   DATE,
    auszahlungsart               TEXT NOT NULL CHECK (auszahlungsart IN ('rente','einmalzahlung')) DEFAULT 'rente',
    auszahlung_kategorie_id      INTEGER NOT NULL REFERENCES kategorien(id),
    rente_garantiert_betrag      REAL,
    rente_voraussichtlich_betrag REAL,
    einmalzahlung_garantiert_betrag      REAL,
    einmalzahlung_voraussichtlich_betrag REAL,

    -- Nur informativ, fließt in keine Berechnung ein
    rueckkaufswert               REAL,
    auszahlung_bei_tod           REAL,

    -- Inflationsfaktor (seit v1.6.3): rechnet den projizierten Auszahlungs-
    -- betrag (nur in Vorschau/Auswertung, NIE bei realen Buchungen - die
    -- nutzen immer den garantierten Betrag) mit Zinseszins ab heute bis
    -- zum jeweiligen Termin hoch, mit dem globalen Inflationsfaktor aus
    -- den Einstellungen. Siehe wiederkehrend.betrag_mit_inflation().
    auszahlung_inflationsflag    INTEGER NOT NULL DEFAULT 0,

    aktiv                         INTEGER NOT NULL DEFAULT 1,
    erzeugt_bis                   DATE   -- seit v1.8, siehe wiederkehrende_buchungen.erzeugt_bis
);

-- ─── Buchungen ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS buchungen (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    konto_id            INTEGER NOT NULL REFERENCES konten(id),
    zielkonto_id        INTEGER REFERENCES konten(id),
    ziel_darlehen_id    INTEGER REFERENCES darlehen(id),
    ziel_altersvorsorge_id INTEGER REFERENCES altersvorsorge(id),
    sparziel_id         INTEGER REFERENCES budgets(id),
    datum               DATE NOT NULL,
    betrag              REAL NOT NULL,
    kategorie_id        INTEGER NOT NULL REFERENCES kategorien(id),
    typ                 TEXT NOT NULL CHECK (typ IN ('Ist','Plan','Uebertragung')),
    beschreibung        TEXT,
    wiederkehrend_id    INTEGER REFERENCES wiederkehrende_buchungen(id),
    inflationsflag      INTEGER NOT NULL DEFAULT 0,
    erstellt_am         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_buchungen_datum ON buchungen(datum);
CREATE INDEX IF NOT EXISTS idx_buchungen_kategorie ON buchungen(kategorie_id);

-- ─── Budgets ────────────────────────────────────────────────────────
-- typ: 'ausgabe' / 'einnahme' -> Verbrauch aus Buchungen der Kategorie.
--      'sparziel'             -> Soll wächst je Periode, Ist kommt aus
--                                zugeordneten Übertragungen (sparziel_id).
-- uebertrag_modus: 'letzte'    -> Rest wird einmalig auf die nächste
--                                Periode aufgeschlagen.
--                  'kumuliert' -> alle Perioden werden fortlaufend
--                                zusammengerechnet (Sparschwein).
CREATE TABLE IF NOT EXISTS budgets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    typ               TEXT NOT NULL CHECK (typ IN ('ausgabe','einnahme','sparziel')) DEFAULT 'ausgabe',
    kategorie_id      INTEGER REFERENCES kategorien(id),
    inkl_unterkategorien INTEGER NOT NULL DEFAULT 1,
    konto_id          INTEGER REFERENCES konten(id),   -- nur bei Sparziel
    zielbetrag        REAL,                            -- nur bei Sparziel (Gesamtsumme)
    zieldatum         DATE,                            -- nur bei Sparziel (optional)
    betrag            REAL NOT NULL,
    zeitraum          TEXT NOT NULL CHECK (zeitraum IN ('monatlich','quartalsweise','jaehrlich','benutzerdefiniert')) DEFAULT 'monatlich',
    intervall_wert    INTEGER,                         -- nur bei benutzerdefiniert
    intervall_einheit TEXT CHECK (intervall_einheit IN ('tage','wochen','monate') OR intervall_einheit IS NULL),
    startdatum        DATE NOT NULL,
    enddatum          DATE,
    uebertrag         INTEGER NOT NULL DEFAULT 0,
    uebertrag_modus   TEXT CHECK (uebertrag_modus IN ('letzte','kumuliert') OR uebertrag_modus IS NULL),
    -- Deckel (seit v1.6.3): begrenzt einen positiven Übertrag nach oben,
    -- damit "Fortlaufend ansparen" (kumuliert) nicht unbegrenzt wächst,
    -- wenn ein Budget selten abgerufen wird (z. B. Auto: TÜV/Reparaturen).
    -- Negativer Übertrag (mitgeschleppte Überschreitung) wird NICHT
    -- gekappt - der Deckel ist eine Obergrenze für den Puffer, kein Boden.
    -- NULL = unbegrenzt (bisheriges Verhalten).
    uebertrag_deckel  REAL,
    -- Inflationsfaktor (seit v1.6.3): rechnet den Periodenbetrag (basis)
    -- mit Zinseszins seit dem Startdatum hoch, mit dem globalen
    -- Inflationsfaktor aus den Einstellungen. Siehe
    -- wiederkehrend.betrag_mit_inflation().
    inflationsflag    INTEGER NOT NULL DEFAULT 0,
    warnungen         TEXT NOT NULL DEFAULT '[{"schwelle": 80, "typ": "Warnung"}]',
    person_id         INTEGER REFERENCES personen(id),
    aktiv             INTEGER NOT NULL DEFAULT 1,
    erstellt_am       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aktualisiert_am   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─── Protokoll: Plan → Ist Umwandlungen ─────────────────────────────
CREATE TABLE IF NOT EXISTS plan_buchung_protokoll (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    buchung_id        INTEGER NOT NULL,
    datum_umwandlung  DATE NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('umgewandelt','angepasst','geloescht')),
    hinweis           TEXT
);

-- Feiertage: seit v2.6 keine Tabelle mehr, berechnet aus der Regeltabelle
-- in app/core/feiertage.py (Region aus der Einstellung 'bundesland').

-- ─── Backups ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS backups_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    erstellt_am  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dateiname    TEXT NOT NULL,
    typ          TEXT NOT NULL CHECK (typ IN ('automatisch_15','automatisch_ultimo','manuell')),
    beschreibung TEXT   -- seit v1.8, z. B. "vor Löschung von: Ist-Buchungen"
);

-- ─── Einstellungen ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS einstellungen (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('inflationsfaktor', '2.0');
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('prognose_min_perioden', '3');
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('auto_kategorisierung', '1');
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('siri_standardkonto', '');
-- v2.6: gewählte Feiertagsregion (Kürzel aus feiertage.REGIONEN), leer =
-- noch nicht gewählt, dann fragt die Oberfläche beim Start. Vorschlag nur
-- für Datenbanken von vor 2.6 (NRW, siehe db._migriere_feiertage_v26).
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('bundesland', '');
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('bundesland_vorschlag', '');
-- GUI-Theme-Farben (Administration -> System -> "Farben"). Leer = eingebauter
-- Standard (siehe :root in style.css) - überschrieben nur bei explizit
-- gesetztem, nicht-leerem Wert. grundton-dunkel/messing-hell/papier-karte
-- werden aus grundton/messing/papier rein rechnerisch abgeleitet (siehe
-- themeFarbenAnwenden in app.js), nicht separat gespeichert.
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('farbe_grundton', '');
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('farbe_messing', '');
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('farbe_gruen', '');
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('farbe_rot', '');
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('farbe_papier', '');
-- Reihenfolge/Trennlinien der Menüpunkte in der Seitenleiste (Start und
-- Admin/Administration sind fest oben bzw. unten und tauchen hier nicht auf).
-- Format: Liste von {"ziel": <nav-ziel>, "trenner_davor": bool}.
INSERT OR IGNORE INTO einstellungen (key, value) VALUES ('nav_reihenfolge',
    '[{"ziel":"konten","trenner_davor":false},{"ziel":"buchungen","trenner_davor":true},{"ziel":"wiederkehrend","trenner_davor":false},{"ziel":"plan","trenner_davor":false},{"ziel":"budgets","trenner_davor":false},{"ziel":"altersvorsorge","trenner_davor":false},{"ziel":"darlehen","trenner_davor":false},{"ziel":"auswertungen","trenner_davor":true},{"ziel":"jahr","trenner_davor":false}]');

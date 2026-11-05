"""
Datenbank-Zugriffsschicht: Pfade, Verbindung, Initialisierung, Migration.

Wichtig für den .exe-Betrieb: Bei PyInstaller werden mitgelieferte
Dateien (schema.sql, static/) in ein temporäres Verzeichnis entpackt,
das nach Programmende verschwindet. Persistente Nutzerdaten (Datenbank,
Backups) liegen deshalb NEBEN der .exe.
"""
import os
from datetime import date, timedelta
import sqlite3
import sys
from pathlib import Path


def basis_verzeichnis() -> Path:
    """
    Verzeichnis für persistente Nutzerdaten (Datenbank, Backups).
    Reihenfolge: Docker/Home-Assistant-Add-on (FINANZAPP_DATENVERZEICHNIS,
    zeigt auf /data) -> PyInstaller-.exe (neben der exe) -> Entwicklungsmodus
    (Projektwurzel).
    """
    docker_pfad = os.environ.get("FINANZAPP_DATENVERZEICHNIS")
    if docker_pfad:
        return Path(docker_pfad)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def resource_pfad(relativ: str) -> Path:
    if getattr(sys, "frozen", False):
        basis = Path(getattr(sys, "_MEIPASS", basis_verzeichnis()))
    else:
        basis = Path(__file__).resolve().parent.parent.parent
    return basis / relativ


DB_PFAD = basis_verzeichnis() / "finanzdaten.db"
BACKUP_VERZEICHNIS = basis_verzeichnis() / "Backups"

# ─── Verschlüsselung (seit 3.0) ─────────────────────────────────────
# Ist die Verschlüsselung eingeschaltet, öffnet verbindung() die Datei mit
# SQLCipher und dem Datenschlüssel aus dem Arbeitsspeicher (gesetzt von
# tresor.py beim Entsperren). Ohne Verschlüsselung bleibt es beim sqlite3
# der Standardbibliothek, genau wie bis 2.7.
try:
    from sqlcipher3 import dbapi2 as sqlcipher
except ImportError:  # Entwicklung ohne das Paket: nur unverschlüsselt möglich
    sqlcipher = None

# Fehlerklassen beider Treiber. sqlcipher3 hat eigene Klassen, die nicht von
# denen der Standardbibliothek erben.
FEHLER = (sqlite3.Error,) + ((sqlcipher.Error,) if sqlcipher else ())
INTEGRITAETSFEHLER = (sqlite3.IntegrityError,) + ((sqlcipher.IntegrityError,) if sqlcipher else ())

_VERSCHLUESSELT = False
_SCHLUESSEL: bytes | None = None


class DatenbankGesperrt(RuntimeError):
    """Die Datenbank ist verschlüsselt und noch nicht entsperrt."""


def verschluesselung_setzen(aktiv: bool, schluessel: bytes | None) -> None:
    global _VERSCHLUESSELT, _SCHLUESSEL
    _VERSCHLUESSELT, _SCHLUESSEL = aktiv, schluessel


def ist_verschluesselt() -> bool:
    return _VERSCHLUESSELT


def ist_gesperrt() -> bool:
    return _VERSCHLUESSELT and _SCHLUESSEL is None


def oeffnen(pfad, schluessel: bytes | None = None, nur_lesen: bool = False):
    """Öffnet eine Datenbankdatei, mit Schlüssel über SQLCipher. Der
    Schlüssel ist ein Rohschlüssel (32 Byte), SQLCipher leitet ihn nicht ab."""
    if schluessel is None:
        conn = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True) if nur_lesen else sqlite3.connect(pfad)
        conn.row_factory = sqlite3.Row
        return conn
    if sqlcipher is None:
        raise RuntimeError("SQLCipher (Paket sqlcipher3-wheels) ist nicht installiert.")
    conn = sqlcipher.connect(f"file:{pfad}?mode=ro", uri=True) if nur_lesen else sqlcipher.connect(str(pfad))
    conn.execute("PRAGMA cipher_log_level = NONE")
    conn.execute(f"PRAGMA key = \"x'{schluessel.hex()}'\"")
    conn.row_factory = sqlcipher.Row
    return conn


def verbindung():
    if _VERSCHLUESSELT:
        if _SCHLUESSEL is None:
            raise DatenbankGesperrt("Die Datenbank ist verschlüsselt und noch nicht entsperrt.")
        conn = oeffnen(DB_PFAD, _SCHLUESSEL)
    else:
        conn = oeffnen(DB_PFAD)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─── System-Kategorien ───────────────────────────────────────────────
# Von der Fachlogik referenziert. Immer über den system_key auflösen,
# nie über eine feste ID: in einer gewachsenen Datenbank können die
# IDs 5, 6, 7 ... längst durch eigene Kategorien des Nutzers belegt
# sein. (name, parent_system_key, typ)
SYSTEM_KATEGORIEN = [
    ("darlehen",              "Darlehen",                  None,        None),
    ("darlehen_sondertilgung","Sondertilgung",             "darlehen",  "ausgabe"),
    ("darlehen_zinsen",       "Darlehens-Zinsen",          "darlehen",  "ausgabe"),   # bis 2.1 "Zinsen"
    ("darlehen_tilgung",      "Tilgung",                   "darlehen",  "ausgabe"),
    ("darlehen_auszahlung",   "Auszahlung",                "darlehen",  "einnahme"),
    ("umbuchung",             "Umbuchung",                 None,        None),
    ("einnahmen",             "Einnahmen",                 None,        "einnahme"),
    ("einnahmen_gehalt",      "Gehalt & Lohn",             "einnahmen", "einnahme"),
    ("einnahmen_sonstige",    "Sonstige Einkünfte",        "einnahmen", "einnahme"),
    ("ausgaben",              "Ausgaben",                  None,        "ausgabe"),
    ("ausgaben_wohnen",       "Wohnen",                    "ausgaben",  "ausgabe"),
    ("ausgaben_lebenshaltung","Lebenshaltung",             "ausgaben",  "ausgabe"),
    ("ausgaben_mobilitaet",   "Mobilität",                 "ausgaben",  "ausgabe"),
    ("ausgaben_versicherung", "Versicherungen & Vorsorge", "ausgaben",  "ausgabe"),
    ("ausgaben_freizeit",     "Freizeit & Unterhaltung",   "ausgaben",  "ausgabe"),
    ("ausgaben_gesundheit",   "Gesundheit",                "ausgaben",  "ausgabe"),
    ("ausgaben_sonstiges",    "Sonstiges",                 "ausgaben",  "ausgabe"),
    # Default-Kategorien für die Altersvorsorge-Einzahlungs-/Auszahlungsphase
    # (seit v1.5 inhaltlich vorgeschlagen, seit v1.6.2 auch als echte
    # System-Kategorien geschützt - neue Altersvorsorge-Verträge können sich
    # jederzeit darauf verlassen, dass es sie unverändert gibt).
    ("altersvorsorge_beitrag","Altersvorsorge",            "ausgaben_versicherung", "ausgabe"),
    # Seit v2.2 direkt unter Einnahmen (bis 2.1 unter "Sonstige Einkünfte").
    ("altersvorsorge_rente",  "Rente",                     "einnahmen",             "einnahme"),
]

# Seit 3.1 (#12): Saldo-Korrektur als Buchung. Neutral, das Vorzeichen ist die
# berechnete Differenz, gebucht nur über die Saldo-Korrektur. Angelegt erst
# nach der Kategorie-Umstellung 2.2, damit ältere Datenbanken alle übrigen
# Kategorien mit denselben IDs bekommen wie bisher.
KORREKTUR_SYSTEM_KATEGORIEN = [
    ("korrekturbuchung",      "Korrekturbuchung",          None,        None),
    ("anfangsbestand",        "Anfangsbestand",            None,        None),
]

# Empfohlene Kategorien, die eine NEUE Datenbank zusätzlich bekommt (seit
# v2.2 nur noch dort: bis 2.1 wurden sie bei jedem Start ergänzt, eine
# gelöschte oder umbenannte Kategorie kam dadurch zurück, Befund K).
# (Name, system_key der Oberkategorie)
EMPFOHLENE_KATEGORIEN = [
    ("Abos & Streaming",         "ausgaben_freizeit"),
    ("Restaurant",               "ausgaben_freizeit"),
    ("Urlaub & Reisen",          "ausgaben_freizeit"),
    ("Arztkosten",               "ausgaben_gesundheit"),
    ("Medikamente & Sonstiges",  "ausgaben_gesundheit"),
    ("Drogerie & Haushalt",      "ausgaben_lebenshaltung"),
    ("Lebensmittel/Verpflegung", "ausgaben_lebenshaltung"),
    ("Kleidung",                 "ausgaben_lebenshaltung"),
    ("KFZ-Unterhalt",            "ausgaben_mobilitaet"),
    ("Kraftstoff",               "ausgaben_mobilitaet"),
    ("ÖPNV",                     "ausgaben_mobilitaet"),
    ("Spenden",                  "ausgaben_sonstiges"),
    ("Sach-Versicherungen",      "ausgaben_versicherung"),
    ("Internet & Telefon",       "ausgaben_wohnen"),
    ("Strom",                    "ausgaben_wohnen"),
    ("Wasser",                   "ausgaben_wohnen"),
    ("Heizung",                  "ausgaben_wohnen"),
    ("Renovierung",              "ausgaben_wohnen"),
    ("Steuern",                  "ausgaben"),
    ("Steuerrückerstattung",     "einnahmen"),
    ("Zinsen & Kapitalerträge",  "einnahmen"),
]


def kategorie_id(conn, system_key: str) -> int | None:
    row = conn.execute("SELECT id FROM kategorien WHERE system_key = ?", (system_key,)).fetchone()
    return row["id"] if row else None


def _spalten(conn, tabelle: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({tabelle})").fetchall()}


def _spalte_ergaenzen(conn, tabelle: str, spalte: str, definition: str) -> None:
    if spalte not in _spalten(conn, tabelle):
        conn.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {definition}")


def _migriere_schema(conn) -> list[str]:
    """Additive Schema-Migration für bestehende Datenbanken."""
    schritte = []
    for tabelle, spalte, definition in [
        ("kategorien", "typ", "TEXT"),
        ("kategorien", "system_key", "TEXT"),
        ("wiederkehrende_buchungen", "dynamik_aktiv", "INTEGER NOT NULL DEFAULT 0"),
        ("wiederkehrende_buchungen", "dynamik_rhythmus_jahre", "INTEGER"),
        ("wiederkehrende_buchungen", "dynamik_prozent", "REAL"),
        ("wiederkehrende_buchungen", "dynamik_startjahr", "INTEGER"),
        ("buchungen", "sparziel_id", "INTEGER"),
        ("kategorien", "siri_favorit", "INTEGER NOT NULL DEFAULT 0"),
        ("buchungen", "ziel_altersvorsorge_id", "INTEGER"),
        # v1.5: Personen-Trennung + optionale Altersvorsorge-Einzahlung
        ("konten", "person_id", "INTEGER"),
        ("wiederkehrende_buchungen", "person_id", "INTEGER"),
        ("altersvorsorge", "person_id", "INTEGER"),
        ("altersvorsorge", "hat_einzahlung", "INTEGER NOT NULL DEFAULT 1"),
        # v1.6: Gesamtsaldo-Auswahl je Konto, Person auf Budgets/Darlehen
        ("konten", "in_gesamtsaldo", "INTEGER NOT NULL DEFAULT 1"),
        ("budgets", "person_id", "INTEGER"),
        ("darlehen", "person_id", "INTEGER"),
        # v1.6.2: frei wählbare Kontofarbe (ersetzt/ergänzt die automatische
        # Zuordnung aus KONTEN_FARBSCHEMA im Frontend)
        ("konten", "farbe", "TEXT"),
        # v1.6.3: Inflationsfaktor für Altersvorsorge-Auszahlungen und
        # Budgets, plus Deckel für den kumulierten Budget-Übertrag.
        ("altersvorsorge", "auszahlung_inflationsflag", "INTEGER NOT NULL DEFAULT 0"),
        ("budgets", "inflationsflag", "INTEGER NOT NULL DEFAULT 0"),
        ("budgets", "uebertrag_deckel", "REAL"),
        # v1.8: Beschreibung zu Backups (z. B. "vor Löschung von: ...")
        ("backups_log", "beschreibung", "TEXT"),
        # v1.8: Erzeugungsmarke je Quelle - verhindert Duplikate nach
        # "Anpassen"/"Verwerfen" im Plan-Buchungen-Protokoll. Bleibt bei
        # bestehenden Quellen zunächst leer: der erste Lauf arbeitet wie
        # bisher (Existenzprüfung, schließt Lücken) und setzt sie dann.
        ("wiederkehrende_buchungen", "erzeugt_bis", "DATE"),
        ("darlehen", "erzeugt_bis", "DATE"),
        ("altersvorsorge", "erzeugt_bis", "DATE"),
        # v1.9: vertraglich vereinbarte Darlehenssumme
        ("darlehen", "darlehenssumme", "REAL"),
        # v1.10: wiederkehrende Umbuchungen (Übertragung zwischen eigenen
        # Konten) mit optionaler Sparziel-Zuordnung
        ("wiederkehrende_buchungen", "zielkonto_id", "INTEGER REFERENCES konten(id)"),
        ("wiederkehrende_buchungen", "sparziel_id", "INTEGER REFERENCES budgets(id)"),
    ]:
        if spalte not in _spalten(conn, tabelle):
            conn.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {definition}")
            schritte.append(f"Spalte {tabelle}.{spalte} ergänzt")
    conn.commit()
    return schritte


def _spalte_ist_pflicht(conn, tabelle: str, spalte: str) -> bool:
    row = next((r for r in conn.execute(f"PRAGMA table_info({tabelle})").fetchall()
                if r["name"] == spalte), None)
    return bool(row and row["notnull"])


def _migriere_altersvorsorge_einzahlung_optional(conn) -> list[str]:
    """
    Macht die Beitragsphase-Felder der Altersvorsorge nachträglich optional
    (für arbeitgeber-/gehaltsfinanzierte Modelle ohne eigene Einzahlung,
    v1.5). SQLite kennt kein 'ALTER COLUMN ... DROP NOT NULL' - deshalb
    wird die Tabelle nach dem von SQLite empfohlenen Verfahren neu gebaut:
    Kopie mit gelockertem Schema anlegen, Daten kopieren, alte Tabelle
    ersetzen. Nur nötig, wenn die alte (strengere) NOT-NULL-Fassung noch
    aktiv ist - bei neuen Datenbanken ohnehin nicht der Fall, da
    schema.sql die gelockerte Fassung direkt anlegt.
    """
    if not _spalte_ist_pflicht(conn, "altersvorsorge", "beitrag_kategorie_id"):
        return []

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("""
            CREATE TABLE altersvorsorge_neu (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                bezeichnung                 TEXT NOT NULL,
                anbieter                    TEXT,
                zahlungskonto_id            INTEGER NOT NULL REFERENCES konten(id),
                person_id                   INTEGER REFERENCES personen(id),
                stand_datum                 DATE NOT NULL,
                hat_einzahlung              INTEGER NOT NULL DEFAULT 1,
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
                rentenbeginn                 DATE NOT NULL,
                ende_datum                   DATE,
                auszahlungsart               TEXT NOT NULL CHECK (auszahlungsart IN ('rente','einmalzahlung')) DEFAULT 'rente',
                auszahlung_kategorie_id      INTEGER NOT NULL REFERENCES kategorien(id),
                rente_garantiert_betrag      REAL,
                rente_voraussichtlich_betrag REAL,
                einmalzahlung_garantiert_betrag      REAL,
                einmalzahlung_voraussichtlich_betrag REAL,
                rueckkaufswert               REAL,
                auszahlung_bei_tod           REAL,
                aktiv                         INTEGER NOT NULL DEFAULT 1
            )
        """)
        # _migriere_schema() läuft vor dieser Funktion und hat person_id /
        # hat_einzahlung bereits additiv auf die alte Tabelle ergänzt -
        # beide Spalten sind hier also schon vorhanden und lassen sich
        # ganz normal mitkopieren.
        spalten_liste = ", ".join(r["name"] for r in conn.execute(
            "PRAGMA table_info(altersvorsorge)").fetchall())
        conn.execute(
            f"INSERT INTO altersvorsorge_neu ({spalten_liste}) "
            f"SELECT {spalten_liste} FROM altersvorsorge"
        )
        conn.execute("DROP TABLE altersvorsorge")
        conn.execute("ALTER TABLE altersvorsorge_neu RENAME TO altersvorsorge")
        conn.execute("PRAGMA foreign_key_check")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    return ["Tabelle altersvorsorge umgebaut: Einzahlungsfelder sind jetzt optional (hat_einzahlung)"]


# Feste Kategorien, die eine gleichnamige eigene Hauptkategorie übernehmen und
# dabei neutral machen (seit 3.1, #12). Andere übernehmen den Typ nur, wenn er fehlt.
NEUTRAL_UEBERNOMMEN = {"korrekturbuchung", "anfangsbestand"}


def _migriere_system_kategorien(conn, liste=SYSTEM_KATEGORIEN) -> list[str]:
    """
    Ordnet den bereits vorhandenen System-Kategorien ihren system_key zu
    (Erkennung über Name + Elternknoten) und legt fehlende neu an - mit
    frei vergebener ID, nie mit einer festen.
    """
    schritte = []
    for key, name, parent_key, typ in liste:
        if kategorie_id(conn, key) is not None:
            continue
        parent_id = kategorie_id(conn, parent_key) if parent_key else None

        # Vorhandene Kategorie mit passendem Namen/Elternknoten übernehmen
        if parent_id is None:
            treffer = conn.execute(
                "SELECT id FROM kategorien WHERE name = ? AND parent_id IS NULL AND system_key IS NULL",
                (name,),
            ).fetchone()
        else:
            treffer = conn.execute(
                "SELECT id FROM kategorien WHERE name = ? AND parent_id = ? AND system_key IS NULL",
                (name, parent_id),
            ).fetchone()

        if treffer and key in NEUTRAL_UEBERNOMMEN:
            # Seit 3.1: eine eigene Hauptkategorie gleichen Namens wird übernommen
            # (Entscheidung zu #12) und neutral, Vorzeichen der Buchungen bleiben.
            conn.execute("UPDATE kategorien SET system_key = ?, typ = NULL WHERE id = ?", (key, treffer["id"]))
            anzahl = conn.execute("SELECT COUNT(*) FROM buchungen WHERE kategorie_id = ?",
                                  (treffer["id"],)).fetchone()[0]
            schritte.append(f"Eigene Kategorie „{name}“ als feste Kategorie übernommen ({anzahl} Buchung(en), "
                            "jetzt neutral und nur über die Saldo-Korrektur buchbar)")
        elif treffer:
            conn.execute("UPDATE kategorien SET system_key = ?, typ = COALESCE(typ, ?) WHERE id = ?",
                         (key, typ, treffer["id"]))
        else:
            conn.execute("INSERT INTO kategorien (name, parent_id, typ, system_key) VALUES (?, ?, ?, ?)",
                         (name, parent_id, typ, key))
            schritte.append(f"System-Kategorie '{name}' angelegt")
    conn.commit()
    return schritte


def typ_vom_wurzelknoten(conn, parent_id: int | None) -> str | None:
    """
    Ermittelt den Typ (einnahme/ausgabe) anhand des OBERSTEN Knotens der
    Elternkette. Unterkategorien von "Einnahmen"/"Ausgaben" erben deren
    Typ - auch über mehrere Ebenen. Kategorien unterhalb systemseitig
    neutraler Knoten (Darlehen, Umbuchung) bleiben bewusst NULL, weil
    dort ein Vorzeichen-Erbe fachlich keinen Sinn ergibt.
    """
    if parent_id is None:
        return None
    gesehen = set()
    aktuell = parent_id
    letzter_typ = None
    while aktuell is not None and aktuell not in gesehen:
        gesehen.add(aktuell)
        row = conn.execute("SELECT parent_id, typ FROM kategorien WHERE id = ?", (aktuell,)).fetchone()
        if row is None:
            break
        if row["typ"] is not None:
            letzter_typ = row["typ"]
        aktuell = row["parent_id"]
    return letzter_typ


def _migriere_kategorie_typen(conn) -> list[str]:
    """
    Erbt den Typ (einnahme/ausgabe) von der Elternkategorie für alle
    selbst angelegten Kategorien, bei denen er noch fehlt. Ohne das
    greifen weder Vorzeichen-Ableitung noch Budget-Zuordnung.
    """
    schritte = []
    for _ in range(10):  # mehrere Durchläufe für tiefe Bäume
        cur = conn.execute("""
            UPDATE kategorien SET typ = (SELECT p.typ FROM kategorien p WHERE p.id = kategorien.parent_id)
            WHERE typ IS NULL AND parent_id IS NOT NULL
              AND (SELECT p.typ FROM kategorien p WHERE p.id = kategorien.parent_id) IS NOT NULL
        """)
        if cur.rowcount:
            schritte.append(f"{cur.rowcount} Kategorie(n) haben den Typ von der Oberkategorie geerbt")
        else:
            break
    conn.commit()
    return schritte


def _migriere_empfohlene_kategorien(conn) -> list[str]:
    schritte = []
    for name, parent_key in EMPFOHLENE_KATEGORIEN:
        parent_id = kategorie_id(conn, parent_key)
        if parent_id is None:
            continue
        vorhanden = conn.execute(
            "SELECT 1 FROM kategorien WHERE name = ? AND parent_id = ?", (name, parent_id)
        ).fetchone()
        if vorhanden:
            continue
        parent_typ = conn.execute("SELECT typ FROM kategorien WHERE id = ?", (parent_id,)).fetchone()["typ"]
        conn.execute("INSERT INTO kategorien (name, parent_id, typ) VALUES (?, ?, ?)",
                     (name, parent_id, parent_typ))
        schritte.append(f"Kategorie '{name}' angelegt")
    conn.commit()
    return schritte


def kategorie_zusammenfuehren(conn, von_id: int, nach_id: int) -> dict:
    """Hängt alles von Kategorie von_id auf nach_id um (Buchungen, Vorlagen,
    Budgets, Regeln, Altersvorsorge, Unterkategorien, Siri-Favorit) und löscht
    von_id. Liefert die Anzahl je Bereich. Seit v2.2."""
    anzahl = {}
    for tabelle, spalte in (("buchungen", "kategorie_id"), ("wiederkehrende_buchungen", "kategorie_id"),
                            ("budgets", "kategorie_id"), ("kategorie_regeln", "kategorie_id"),
                            ("altersvorsorge", "beitrag_kategorie_id"), ("altersvorsorge", "auszahlung_kategorie_id"),
                            ("kategorien", "parent_id")):
        cur = conn.execute(f"UPDATE {tabelle} SET {spalte} = ? WHERE {spalte} = ?", (nach_id, von_id))
        if cur.rowcount:
            anzahl[f"{tabelle}.{spalte}"] = cur.rowcount
    conn.execute("""UPDATE kategorien SET siri_favorit = 1 WHERE id = ?
                    AND (SELECT siri_favorit FROM kategorien WHERE id = ?) = 1""", (nach_id, von_id))
    conn.execute("DELETE FROM kategorien WHERE id = ?", (von_id,))
    return anzahl


def _namensschluessel(name: str) -> str:
    """Vergleichsform für Kategorienamen: ohne Groß/klein, Leerzeichen, Bindestriche."""
    return "".join(ch for ch in (name or "").casefold() if ch.isalnum() or ch in "&/")


def _unterkategorie(conn, parent_id, name: str, nur_frei: bool = True):
    """Findet eine Unterkategorie per Namensvergleich (tolerant bei Leerzeichen/Bindestrich)."""
    sql = "SELECT id, name, system_key FROM kategorien WHERE parent_id IS ?" if parent_id is None \
        else "SELECT id, name, system_key FROM kategorien WHERE parent_id = ?"
    for r in conn.execute(sql, (parent_id,)).fetchall():
        if _namensschluessel(r["name"]) == _namensschluessel(name) and not (nur_frei and r["system_key"]):
            return r
    return None


# Kategorien, die Version 2.2 in bestehenden Datenbanken ergänzt (Name, system_key der
# Oberkategorie oder Name einer freien Oberkategorie unter "ausgaben").
_NEUE_KATEGORIEN_V22 = [
    ("Haustier", "ausgaben"),
    ("Arztkosten & Medikamente", "Haustier"), ("Futter", "Haustier"), ("Sonstiger Haustierbedarf", "Haustier"),
    ("Kleidung", "ausgaben_lebenshaltung"),
    ("Steuern", "ausgaben"),
    ("Wasser", "ausgaben_wohnen"), ("Heizung", "ausgaben_wohnen"), ("Renovierung", "ausgaben_wohnen"),
    ("Grundsteuer", "ausgaben_wohnen"),
    ("Zinsen & Kapitalerträge", "einnahmen"),
]


def _migriere_kategorien_v22(conn, neu: bool) -> list[str]:
    """
    Einmalige Umstellung der Kategorien auf den Stand 2.2 (Merker). Vorher
    automatisches Backup, jeder Schritt wird im Start-Status genannt:
    Darlehens-"Zinsen" heißt "Darlehens-Zinsen"; die feste "Rente" steht direkt
    unter Einnahmen, eine freie "Rente" dort wird mit ihr zusammengeführt;
    "Lebensmittel" geht in "Lebensmittel/Verpflegung" auf (fehlt diese, wird
    umbenannt); "Versicherungen" heißt "Sach-Versicherungen"; neue Kategorien
    aus _NEUE_KATEGORIEN_V22 kommen dazu, sofern noch nicht vorhanden.
    """
    merker = "migration_kategorien_v22_erledigt"
    if conn.execute("SELECT 1 FROM einstellungen WHERE key = ? AND value = '1'", (merker,)).fetchone():
        return []
    schritte = []
    if not neu:
        from .backup import backup_erstellen
        datei = backup_erstellen(conn, "manuell", beschreibung="vor Kategorie-Umstellung 2.2")
        schritte.append(f"Backup vor der Kategorie-Umstellung: {datei}")

    def bericht(anzahl: dict) -> str:
        namen = {"buchungen.kategorie_id": "Buchungen", "wiederkehrende_buchungen.kategorie_id": "Vorlagen",
                 "budgets.kategorie_id": "Budgets", "kategorie_regeln.kategorie_id": "Regeln",
                 "altersvorsorge.beitrag_kategorie_id": "Altersvorsorge-Beiträge",
                 "altersvorsorge.auszahlung_kategorie_id": "Altersvorsorge-Auszahlungen",
                 "kategorien.parent_id": "Unterkategorien"}
        teile = [f"{namen.get(k, k)} {n}" for k, n in anzahl.items()]
        return " (umgehängt: " + ", ".join(teile) + ")" if teile else ""

    # 1. Darlehens-Zinsen
    zid = kategorie_id(conn, "darlehen_zinsen")
    if zid and conn.execute("SELECT name FROM kategorien WHERE id = ?", (zid,)).fetchone()["name"] == "Zinsen":
        conn.execute("UPDATE kategorien SET name = 'Darlehens-Zinsen' WHERE id = ?", (zid,))
        schritte.append("Kategorie „Darlehen > Zinsen“ heißt jetzt „Darlehens-Zinsen“")
    # 2. Rente direkt unter Einnahmen, freie Rente dort zusammenführen
    rid, eid = kategorie_id(conn, "altersvorsorge_rente"), kategorie_id(conn, "einnahmen")
    if rid and eid:
        alt = conn.execute("SELECT parent_id FROM kategorien WHERE id = ?", (rid,)).fetchone()["parent_id"]
        if alt != eid:
            conn.execute("UPDATE kategorien SET parent_id = ? WHERE id = ?", (eid, rid))
            schritte.append("Feste Kategorie „Rente“ steht jetzt direkt unter Einnahmen")
        frei = _unterkategorie(conn, eid, "Rente")
        if frei and frei["id"] != rid:
            anz = kategorie_zusammenfuehren(conn, frei["id"], rid)
            schritte.append("Freie Kategorie „Rente“ mit der festen „Rente“ zusammengeführt" + bericht(anz))
    # 3. Lebensmittel -> Lebensmittel/Verpflegung
    lid = kategorie_id(conn, "ausgaben_lebenshaltung")
    if lid:
        lm = _unterkategorie(conn, lid, "Lebensmittel")
        lv = _unterkategorie(conn, lid, "Lebensmittel/Verpflegung")
        if lm and lv:
            anz = kategorie_zusammenfuehren(conn, lm["id"], lv["id"])
            schritte.append(f"„Lebensmittel“ in „{lv['name']}“ aufgegangen" + bericht(anz))
        elif lm:
            conn.execute("UPDATE kategorien SET name = 'Lebensmittel/Verpflegung' WHERE id = ?", (lm["id"],))
            schritte.append("„Lebensmittel“ heißt jetzt „Lebensmittel/Verpflegung“")
    # 4. Versicherungen -> Sach-Versicherungen
    vid = kategorie_id(conn, "ausgaben_versicherung")
    if vid:
        vs = _unterkategorie(conn, vid, "Versicherungen")
        if vs and not _unterkategorie(conn, vid, "Sach-Versicherungen"):
            conn.execute("UPDATE kategorien SET name = 'Sach-Versicherungen' WHERE id = ?", (vs["id"],))
            schritte.append("„Versicherungen“ heißt jetzt „Sach-Versicherungen“")
    # 5. Neue Kategorien
    if not neu:
        for name, oben in _NEUE_KATEGORIEN_V22:
            parent_id = kategorie_id(conn, oben)
            if parent_id is None:
                treffer = _unterkategorie(conn, kategorie_id(conn, "ausgaben"), oben)
                parent_id = treffer["id"] if treffer else None
            if parent_id is None or _unterkategorie(conn, parent_id, name, nur_frei=False):
                continue
            typ = conn.execute("SELECT typ FROM kategorien WHERE id = ?", (parent_id,)).fetchone()["typ"]
            conn.execute("INSERT INTO kategorien (name, parent_id, typ) VALUES (?, ?, ?)", (name, parent_id, typ))
            schritte.append(f"Kategorie „{name}“ angelegt")
    conn.execute("INSERT OR REPLACE INTO einstellungen (key, value) VALUES (?, '1')", (merker,))
    conn.commit()
    return schritte if len(schritte) > 1 or neu else []


def vorzeichen_konflikte(conn) -> list[dict]:
    """
    Buchungen, deren Vorzeichen nicht zum Kategorie-Typ passt
    (Ausgabe positiv oder Einnahme negativ). Wird dem Nutzer als
    Korrekturvorschlag angeboten - NIE automatisch umgedreht.
    """
    rows = conn.execute("""
        SELECT b.id, b.datum, b.betrag, b.beschreibung, b.typ, k.name AS kategorie, k.typ AS kategorie_typ
        FROM buchungen b JOIN kategorien k ON k.id = b.kategorie_id
        WHERE b.typ IN ('Ist','Plan')
          AND ((k.typ = 'ausgabe' AND b.betrag > 0) OR (k.typ = 'einnahme' AND b.betrag < 0))
        ORDER BY b.datum, b.id
    """).fetchall()
    return [dict(r) for r in rows]


def sparziel_konflikte(conn) -> dict:
    """
    Buchungen und Vorlagen, deren Sparziel-Zuordnung der Regel seit v2.0
    widerspricht (siehe buchungen.sparziel_pruefen): Ist-/Plan-Buchungen mit
    Sparziel, Übertragungen weder von noch zum Trägerkonto, Zuordnung zu
    einem nicht (mehr) vorhandenen Sparziel. Nur Anzeige - gelöst wird
    ausschließlich nach Bestätigung (sparziel_zuordnung_loesen).
    """
    buchungen = conn.execute("""
        SELECT b.id, b.datum, b.betrag, b.typ, b.beschreibung, ko.name AS konto, zk.name AS zielkonto,
               sz.name AS sparziel, tk.name AS traegerkonto
        FROM buchungen b
        LEFT JOIN budgets sz ON sz.id = b.sparziel_id AND sz.typ = 'sparziel'
        LEFT JOIN konten ko ON ko.id = b.konto_id
        LEFT JOIN konten zk ON zk.id = b.zielkonto_id
        LEFT JOIN konten tk ON tk.id = sz.konto_id
        WHERE b.sparziel_id IS NOT NULL
          AND (sz.id IS NULL OR b.typ != 'Uebertragung' OR sz.konto_id IS NULL
               OR sz.konto_id NOT IN (b.konto_id, COALESCE(b.zielkonto_id, -1)))
        ORDER BY b.datum, b.id""").fetchall()
    vorlagen = conn.execute("""
        SELECT w.id, w.beschreibung, w.betrag, ko.name AS konto, zk.name AS zielkonto,
               sz.name AS sparziel, tk.name AS traegerkonto
        FROM wiederkehrende_buchungen w
        LEFT JOIN budgets sz ON sz.id = w.sparziel_id AND sz.typ = 'sparziel'
        LEFT JOIN konten ko ON ko.id = w.konto_id
        LEFT JOIN konten zk ON zk.id = w.zielkonto_id
        LEFT JOIN konten tk ON tk.id = sz.konto_id
        WHERE w.sparziel_id IS NOT NULL
          AND (sz.id IS NULL OR w.zielkonto_id IS NULL OR sz.konto_id IS NULL
               OR sz.konto_id NOT IN (w.konto_id, w.zielkonto_id))
        ORDER BY w.id""").fetchall()
    return {"buchungen": [dict(r) for r in buchungen], "vorlagen": [dict(r) for r in vorlagen]}


def sparziel_zuordnung_loesen(conn, buchung_ids: list[int], vorlage_ids: list[int]) -> int:
    """Löst die Sparziel-Zuordnung - nur für Einträge, die tatsächlich als
    Konflikt gelten (Schutz gegen veraltete Auswahl im Browser)."""
    k = sparziel_konflikte(conn)
    b_ok = {r["id"] for r in k["buchungen"]} & set(buchung_ids)
    v_ok = {r["id"] for r in k["vorlagen"]} & set(vorlage_ids)
    for bid in b_ok:
        conn.execute("UPDATE buchungen SET sparziel_id = NULL WHERE id = ?", (bid,))
    for vid in v_ok:
        conn.execute("UPDATE wiederkehrende_buchungen SET sparziel_id = NULL WHERE id = ?", (vid,))
    conn.commit()
    return len(b_ok) + len(v_ok)


def vorlagen_vorzeichen_konflikte(conn) -> list[dict]:
    rows = conn.execute("""
        SELECT w.id, w.betrag, w.beschreibung, k.name AS kategorie, k.typ AS kategorie_typ
        FROM wiederkehrende_buchungen w JOIN kategorien k ON k.id = w.kategorie_id
        WHERE w.zielkonto_id IS NULL  -- Umbuchungen (seit v1.10) haben kein Vorzeichen
          AND ((k.typ = 'ausgabe' AND w.betrag > 0) OR (k.typ = 'einnahme' AND w.betrag < 0))
        ORDER BY w.id
    """).fetchall()
    return [dict(r) for r in rows]


def _migriere_alte_plan_buchungen(conn) -> list[str]:
    """
    Löscht Plan-Buchungen aus der alten Architektur (Vorproduktion für
    12 Monate). Betrifft nur automatisch erzeugte Zeilen - erkennbar an
    wiederkehrend_id bzw. ziel_darlehen_id - NIE manuell erfasste
    Plan-Buchungen (typ='Plan' ohne diese Verknüpfung).

    Seit v1.8 EINMALIG (Merker in den Einstellungen): Vorher lief sie bei
    jedem Start und löschte damit auch automatische Buchungen, die im
    Plan-Buchungen-Protokoll per "Anpassen" auf ein neues Datum gelegt
    und dabei wieder zu Plan wurden.
    """
    merker = "migration_alte_plan_buchungen_erledigt"
    if conn.execute("SELECT 1 FROM einstellungen WHERE key = ? AND value = '1'", (merker,)).fetchone():
        return []
    cur = conn.execute(
        "DELETE FROM buchungen WHERE typ = 'Plan' AND (wiederkehrend_id IS NOT NULL OR ziel_darlehen_id IS NOT NULL)"
    )
    conn.execute("INSERT OR REPLACE INTO einstellungen (key, value) VALUES (?, '1')", (merker,))
    conn.commit()
    return [f"{cur.rowcount} automatisch erzeugte Plan-Buchung(en) aus der alten Architektur entfernt"] \
        if cur.rowcount else []


def _migriere_kuenftige_saldo_korrekturen(conn) -> list[str]:
    """
    Seit v2.0 sind Saldo-Korrekturen mit Datum nach heute gesperrt (eine
    Korrektur hält einen festgestellten Kontostand fest). Vorhandene künftig
    datierte Korrekturen werden EINMALIG gelöscht (Merker, siehe Lehre aus
    _migriere_alte_plan_buchungen) und im Start-Status einzeln genannt.
    """
    from . import zeit
    merker = "migration_kuenftige_saldo_korrekturen_erledigt"
    if conn.execute("SELECT 1 FROM einstellungen WHERE key = ? AND value = '1'", (merker,)).fetchone():
        return []
    if not _tabelle_da(conn, "saldo_korrekturen"):   # seit 3.1 entfernt (#12)
        return []
    heute = zeit.heute().isoformat()
    rows = conn.execute(
        """SELECT s.id, s.datum, s.saldo, k.name AS konto FROM saldo_korrekturen s
           LEFT JOIN konten k ON k.id = s.konto_id WHERE s.datum > ? ORDER BY s.datum""", (heute,)).fetchall()
    conn.execute("DELETE FROM saldo_korrekturen WHERE datum > ?", (heute,))
    conn.execute("INSERT OR REPLACE INTO einstellungen (key, value) VALUES (?, '1')", (merker,))
    conn.commit()
    return [f"Künftig datierte Saldo-Korrektur gelöscht: {r['konto'] or '?'}, {r['datum']}, {r['saldo']:.2f} €"
            for r in rows]


def korrigiere_vorlagen_vorzeichen(conn) -> int:
    """
    Korrigiert das Vorzeichen wiederkehrender Vorlagen automatisch beim
    Start. Bewusst NUR Vorlagen: sie erzeugen erst noch zukünftige
    Buchungen, eine stille Korrektur ist hier unkritisch. Bereits
    gebuchte Ist-Buchungen bleiben unangetastet und verlangen weiterhin
    eine ausdrückliche Bestätigung durch den Anwender.
    """
    anzahl = 0
    for r in vorlagen_vorzeichen_konflikte(conn):
        neu = -abs(r["betrag"]) if r["kategorie_typ"] == "ausgabe" else abs(r["betrag"])
        conn.execute("UPDATE wiederkehrende_buchungen SET betrag = ? WHERE id = ?", (neu, r["id"]))
        anzahl += 1
    conn.commit()
    return anzahl


def _repariere_dynamik_ohne_prozent(conn) -> int:
    """
    Selbstheilung für Bug v1.4: Vorlagen mit aktiver Dynamik, aber ohne
    gespeicherten Prozentwert (dynamik_prozent NULL) ließen die komplette
    Wiederkehrend-Liste mit einem 500er abstürzen (Formatierungsfehler
    beim Anzeige-Text). Eine Dynamik ohne Prozentwert ist ohnehin
    unbrauchbar - sie wird deaktiviert, die Vorlage selbst (Betrag,
    Intervall usw.) bleibt unangetastet und weiter aktiv buchbar.
    """
    cur = conn.execute(
        "UPDATE wiederkehrende_buchungen SET dynamik_aktiv = 0 "
        "WHERE dynamik_aktiv = 1 AND dynamik_prozent IS NULL"
    )
    conn.commit()
    return cur.rowcount


def _migriere_feiertage_v26(conn) -> list[str]:
    """Seit v2.6 werden Feiertage nicht mehr gespeichert, sondern aus der
    Regeltabelle in feiertage.py berechnet. Die alte Tabelle feiertage enthielt
    nur abgeleitete Werte (bei jedem Start gelöscht und neu gefüllt) und wird
    ohne Backup entfernt. Ihr Vorhandensein zeigt eine Datenbank von vor 2.6:
    Dort war fest NRW eingestellt, daher wird NRW als Vorschlag für die
    einmalige Abfrage des Bundeslands hinterlegt. Gefahrlos wiederholbar,
    auch nach dem Einspielen eines alten Backups."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'feiertage'").fetchone():
        return []
    schritte = []
    gewaehlt = conn.execute("SELECT value FROM einstellungen WHERE key = 'bundesland'").fetchone()
    if not (gewaehlt and gewaehlt["value"]):
        from .feiertage import VORSCHLAG_BESTAND
        conn.execute("INSERT OR REPLACE INTO einstellungen (key, value) VALUES ('bundesland_vorschlag', ?)",
                     (VORSCHLAG_BESTAND,))
        schritte.append("Bundesland noch nicht gewählt, Nordrhein-Westfalen als Vorschlag hinterlegt")
    conn.execute("DROP TABLE feiertage")
    conn.commit()
    schritte.append("Tabelle feiertage entfernt (Feiertage werden jetzt berechnet)")
    return schritte


def _tabelle_da(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def _faellige_plan(conn, konto_id: int, ab_iso: str, bis_iso: str, heute_iso: str) -> float:
    """Plan-Buchungen bis heute: der Start wandelt sie gleich nach der
    Migration in Ist-Buchungen um (plan_buchungen.umwandeln_faellige)."""
    return conn.execute("SELECT COALESCE(SUM(betrag), 0) FROM buchungen WHERE konto_id = ? AND typ = 'Plan' "
                        "AND datum >= ? AND datum <= ? AND datum <= ?",
                        (konto_id, ab_iso, bis_iso, heute_iso)).fetchone()[0]


def _saldo_30(conn, konto_id: int, bis_iso: str, heute_iso: str) -> float:
    """Ist-Saldo nach dem Start mit der Regel bis 3.0 (Fixpunkt): jüngste
    Korrektur bis zum Stichtag als Basis, nur Buchungen ab ihrem Datum, fällige
    Plan-Buchungen wie Ist. Dieselbe Abfrage wie in 3.0, damit auch mehrere
    Korrekturen am selben Tag genauso zählen (dort tatsächlich die zuerst
    angelegte, Befund AB). Nur für die Prüfung der Umstellung."""
    k = conn.execute("""SELECT datum, saldo FROM saldo_korrekturen WHERE konto_id = ? AND datum <= ?
                        ORDER BY datum DESC LIMIT 1""", (konto_id, bis_iso)).fetchone()
    ab, basis = (k["datum"], k["saldo"]) if k else ("0001-01-01", 0.0)
    ist = conn.execute("SELECT COALESCE(SUM(betrag), 0) FROM buchungen WHERE konto_id = ? AND typ = 'Ist' "
                       "AND datum >= ? AND datum <= ?", (konto_id, ab, bis_iso)).fetchone()[0]
    ist += _faellige_plan(conn, konto_id, ab, bis_iso, heute_iso)
    ab_ue = conn.execute("SELECT COALESCE(SUM(betrag), 0) FROM buchungen WHERE konto_id = ? AND typ = 'Uebertragung' "
                         "AND datum >= ? AND datum <= ?", (konto_id, ab, bis_iso)).fetchone()[0]
    zu_ue = conn.execute("SELECT COALESCE(SUM(betrag), 0) FROM buchungen WHERE zielkonto_id = ? AND typ = 'Uebertragung' "
                         "AND datum >= ? AND datum <= ?", (konto_id, ab, bis_iso)).fetchone()[0]
    return round(basis + ist - ab_ue + zu_ue, 2)


def _migriere_saldo_korrekturen_v31(conn) -> list[str]:
    """
    Seit 3.1 (#12) ist die Saldo-Korrektur eine Buchung. Die alten Fixpunkte
    (Tabelle saldo_korrekturen) werden umgewandelt: je Konto nach Datum und Id,
    Betrag = eingegebener Wert minus neuer Saldo am Ende des Vortags
    (einschließlich der schon umgewandelten). Mehrere am selben Tag: die mit
    der höchsten Id gilt, die früheren werden zu Differenzen (zweite = K2 - K1).
    Die früheste wird zum Anfangsbestand, wenn vorher keine Ist-Buchung oder
    Übertragung des Kontos liegt und das Konto noch keinen hat. Betrag 0: keine
    Buchung. Fällige Plan-Buchungen (bis heute) zählen dabei schon wie Ist,
    weil der Start sie gleich danach umwandelt (Entscheidung zu #12); vor einer
    Korrektur liegen nur solche, Korrekturen sind nie künftig. Danach wird die Tabelle gelöscht. Vorher ein Backup, jeder Schritt
    im Start-Status, dazu der Vergleich der Salden vorher und nachher.
    Läuft, solange die Tabelle existiert (auch nach dem Einspielen eines
    Backups von 3.0), der Merker hält nur fest, dass es geschehen ist.
    """
    from . import buchungen, zeit
    merker = "migration_saldo_korrekturen_v31_erledigt"
    if not _tabelle_da(conn, "saldo_korrekturen"):
        return []
    zeilen = conn.execute("""SELECT s.id, s.konto_id, s.datum, s.saldo, s.kommentar, k.name AS konto
                             FROM saldo_korrekturen s JOIN konten k ON k.id = s.konto_id
                             ORDER BY s.konto_id, s.datum, s.id""").fetchall()
    schritte = []
    if zeilen:
        from .backup import backup_erstellen
        datei = backup_erstellen(conn, "manuell", beschreibung="vor Umstellung der Saldo-Korrekturen 3.1")
        schritte.append(f"Backup vor der Umstellung der Saldo-Korrekturen: {datei}")
    euro, de = buchungen.euro_de, (lambda iso: date.fromisoformat(iso).strftime("%d.%m.%Y"))
    try:
        # Salden nach der alten Regel vorher festhalten: an jedem Korrektur- und
        # Buchungstag des Kontos und heute.
        heute_iso = zeit.heute().isoformat()

        def saldo_neu(k, tag_iso):
            return round(buchungen.saldo(conn, k, date.fromisoformat(tag_iso))
                         + _faellige_plan(conn, k, "0001-01-01", tag_iso, heute_iso), 2)

        konten = sorted({z["konto_id"] for z in zeilen})
        stichtage, alt = {}, {}
        for k in konten:
            tage = {r[0] for r in conn.execute(
                "SELECT datum FROM buchungen WHERE konto_id = ? OR zielkonto_id = ? UNION "
                "SELECT datum FROM saldo_korrekturen WHERE konto_id = ?", (k, k, k))}
            stichtage[k] = sorted(tage | {heute_iso})
            alt[k] = {d: _saldo_30(conn, k, d, heute_iso) for d in stichtage[k]}
        id_korr = buchungen.kategorie_id_aus_schluessel(conn, "korrekturbuchung")
        id_ab = buchungen.kategorie_id_aus_schluessel(conn, "anfangsbestand")
        for k in konten:
            liste = [z for z in zeilen if z["konto_id"] == k]
            erste = liste[0]
            anfang_moeglich = not buchungen.hat_anfangsbestand(conn, k) and not conn.execute(
                """SELECT 1 FROM buchungen WHERE datum < ? AND ((typ IN ('Ist', 'Plan') AND konto_id = ?)
                   OR (typ = 'Uebertragung' AND (konto_id = ? OR zielkonto_id = ?))) LIMIT 1""",
                (erste["datum"], k, k, k)).fetchone()
            plan_vorher = conn.execute("SELECT COUNT(*) FROM buchungen WHERE konto_id = ? AND typ = 'Plan' AND datum < ?",
                                       (k, liste[-1]["datum"])).fetchone()[0]
            if plan_vorher:
                schritte.append(f"Hinweis „{erste['konto']}“: {plan_vorher} fällige Plan-Buchung(en) vor einer alten "
                                "Saldo-Korrektur zählen bei der Umstellung schon als Ist, der Start bucht sie gleich als Ist")
            vorheriger = None   # (datum, Wert) der vorigen Korrektur am selben Tag
            for z in liste:
                if vorheriger and vorheriger[0] == z["datum"]:
                    betrag = round(z["saldo"] - vorheriger[1], 2)
                else:
                    vortag = (date.fromisoformat(z["datum"]) - timedelta(days=1)).isoformat()
                    betrag = round(z["saldo"] - saldo_neu(k, vortag), 2)
                vorheriger = (z["datum"], z["saldo"])
                als_anfang = z is erste and anfang_moeglich
                kurz = f"Saldo-Korrektur „{z['konto']}“ vom {de(z['datum'])} ({euro(z['saldo'])})"
                if abs(betrag) < 0.005:
                    schritte.append(f"{kurz}: Differenz 0, keine Buchung")
                    continue
                beschreibung = (f"Anfangsbestand {euro(z['saldo'])}" if als_anfang
                                else f"Saldo-Korrektur auf {euro(z['saldo'])}")
                if z["kommentar"] and z["kommentar"].strip():
                    beschreibung += f" – {z['kommentar'].strip()}"
                conn.execute("""INSERT INTO buchungen (konto_id, datum, betrag, kategorie_id, typ, beschreibung)
                                VALUES (?, ?, ?, ?, 'Ist', ?)""",
                             (k, z["datum"], betrag, id_ab if als_anfang else id_korr, beschreibung))
                schritte.append(f"{kurz} → {'Anfangsbestand' if als_anfang else 'Korrekturbuchung'} {euro(betrag)}")
        # Vergleich: Ist-Saldo nach dem Start muss gleich bleiben. Ausnahme ist
        # nur der Fall mehrerer Korrekturen am selben Tag (höchste statt
        # niedrigster Id, Befund AB).
        for k in konten:
            name = next(z["konto"] for z in zeilen if z["konto_id"] == k)
            for d in stichtage[k]:
                differenz = round(saldo_neu(k, d) - alt[k][d], 2)
                if abs(differenz) >= 0.005:
                    schritte.append(f"Abweichung „{name}“: Ist-Saldo ab dem {de(d)} um {euro(differenz)} anders als "
                                    "bisher (mehrere Saldo-Korrekturen am selben Tag, jetzt gilt die zuletzt angelegte)")
                    break
        if zeilen:
            schritte.append("Prüfung: Ist-Saldo " + ("aller Konten" if not any(x.startswith("Abweichung") for x in schritte)
                            else "der übrigen Konten") + " an allen Buchungstagen vor und nach der Umstellung gleich")
        conn.execute("DROP TABLE saldo_korrekturen")
        conn.execute("INSERT OR REPLACE INTO einstellungen (key, value) VALUES (?, '1')", (merker,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if zeilen:
        schritte.append(f"{len(zeilen)} Saldo-Korrektur(en) in Buchungen umgewandelt, Tabelle saldo_korrekturen entfernt")
    return schritte


def _korrigiere_zielkonto_ohne_uebertragung_v261(conn) -> list[str]:
    """Befund P (2.6.1): Bis 2.6 speicherte „Neue Buchung“ bei Ist und Plan
    das Zielkonto aus dem verborgenen Auswahlfeld. Einmalig (Merker) wird es
    bei allen Buchungen geleert, die keine Übertragung sind. Backup nur,
    wenn es etwas zu korrigieren gibt."""
    merker = "korrektur_zielkonto_v261_erledigt"
    if conn.execute("SELECT 1 FROM einstellungen WHERE key = ? AND value = '1'", (merker,)).fetchone():
        return []
    anzahl = conn.execute(
        "SELECT COUNT(*) FROM buchungen WHERE typ <> 'Uebertragung' AND zielkonto_id IS NOT NULL").fetchone()[0]
    schritte = []
    if anzahl:
        from .backup import backup_erstellen
        datei = backup_erstellen(conn, "manuell", beschreibung="vor Korrektur Zielkonto 2.6.1")
        schritte.append(f"Backup vor der Korrektur des Zielkontos: {datei}")
        conn.execute("UPDATE buchungen SET zielkonto_id = NULL WHERE typ <> 'Uebertragung' AND zielkonto_id IS NOT NULL")
        schritte.append(f"Zielkonto bei {anzahl} Ist- bzw. Plan-Buchung(en) entfernt (Befund P)")
    conn.execute("INSERT OR REPLACE INTO einstellungen (key, value) VALUES (?, '1')", (merker,))
    conn.commit()
    return schritte


def initialisieren() -> dict:
    """Legt die Datenbank an (falls nötig), führt Schema und Migration aus."""
    neu = not DB_PFAD.exists()
    BACKUP_VERZEICHNIS.mkdir(exist_ok=True)
    conn = verbindung()
    try:
        schritte = _migriere_schema(conn) if not neu else []
        conn.executescript(resource_pfad("app/schema.sql").read_text(encoding="utf-8"))
        conn.commit()
        if not neu:
            schritte += _migriere_schema(conn)
        schritte += _migriere_feiertage_v26(conn)
        schritte += _migriere_altersvorsorge_einzahlung_optional(conn)
        schritte += _migriere_system_kategorien(conn)
        schritte += _migriere_kategorie_typen(conn)
        if neu:
            schritte += _migriere_empfohlene_kategorien(conn)
        schritte += _migriere_kategorien_v22(conn, neu)
        schritte += _migriere_system_kategorien(conn, KORREKTUR_SYSTEM_KATEGORIEN)
        schritte += _migriere_alte_plan_buchungen(conn)
        schritte += _migriere_kuenftige_saldo_korrekturen(conn)
        schritte += _migriere_saldo_korrekturen_v31(conn)
        schritte += _korrigiere_zielkonto_ohne_uebertragung_v261(conn)
        korrigiert = korrigiere_vorlagen_vorzeichen(conn)
        if korrigiert:
            schritte.append(f"{korrigiert} Vorlage(n) mit unpassendem Vorzeichen automatisch korrigiert")
        repariert = _repariere_dynamik_ohne_prozent(conn)
        if repariert:
            schritte.append(f"{repariert} Vorlage(n) mit aktiver Dynamik ohne Prozentwert repariert "
                             f"(Dynamik deaktiviert, Vorlage bleibt aktiv)")
        return {"datenbank_neu_angelegt": neu, "migration": schritte}
    finally:
        conn.close()

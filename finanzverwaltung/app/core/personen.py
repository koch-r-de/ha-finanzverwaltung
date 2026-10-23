"""
Personen: administrierbares Merkmal zur Trennung von Konten,
wiederkehrenden Buchungen und Altersvorsorge-Verträgen nach Person
(z. B. bei gemeinsamer Haushaltsführung, v1.5).

Jeder der drei Bereiche trägt eine EIGENE, unabhängige person_id - ein
gemeinsames Konto kann also wiederkehrende Buchungen unterschiedlicher
Personen enthalten. Buchungen selbst tragen keine eigene person_id;
eine Personen-Filterung dort erfolgt über das Konto (siehe
buchungen.buchungen_liste/buchungen_suchen).

Wie bei Konten: Personen werden deaktiviert statt hart gelöscht, damit
bereits vergebene Zuordnungen (Konten, Vorlagen, Verträge) nicht ins
Leere zeigen.
"""
from typing import Optional


def personen_liste(conn, nur_aktive: bool = True):
    if nur_aktive:
        return conn.execute("SELECT * FROM personen WHERE aktiv = 1 ORDER BY name").fetchall()
    return conn.execute("SELECT * FROM personen ORDER BY name").fetchall()


def person_anlegen(conn, name: str, farbe: Optional[str] = None) -> int:
    cur = conn.execute("INSERT INTO personen (name, farbe) VALUES (?, ?)", (name, farbe))
    conn.commit()
    return cur.lastrowid


def person_bearbeiten(conn, person_id: int, **felder) -> None:
    erlaubt = {"name", "farbe", "aktiv"}
    setzen = {k: v for k, v in felder.items() if k in erlaubt}
    if not setzen:
        return
    klauseln = ", ".join(f"{k} = ?" for k in setzen)
    conn.execute(f"UPDATE personen SET {klauseln} WHERE id = ?", (*setzen.values(), person_id))
    conn.commit()


def person_loeschen(conn, person_id: int) -> None:
    """Deaktivieren statt löschen - siehe Modul-Docstring."""
    conn.execute("UPDATE personen SET aktiv = 0 WHERE id = ?", (person_id,))
    conn.commit()

"""
FastAPI-Backend: REST-API für die Finanzverwaltung und Auslieferung
der Web-Oberfläche (Chart.js-Frontend unter app/static/).

Beim Start der Anwendung (Startup-Event) laufen automatisch alle in
Abschnitt 11.1 des Fachkonzepts geforderten Automatisierungen
(startup.ausfuehren) - das entspricht dem Programmstart einer
klassischen Desktop-Anwendung, auch wenn technisch ein lokaler
Webserver dahintersteht.
"""
from datetime import date, datetime
import os
import io
import re
from typing import Optional

from dateutil.relativedelta import relativedelta
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Annotated

from pydantic import AfterValidator, BaseModel


def _datum_pruefen(wert):
    """Datumsfelder (seit v1.9): ISO-Datum mit vierstelliger Jahreszahl.
    Verhindert u. a. fünfstellige Jahre, die später beim Programmstart
    (date.fromisoformat in den Generatoren) die ganze App lahmlegen würden."""
    if wert in (None, ""):
        return None
    try:
        d = date.fromisoformat(str(wert))
    except ValueError:
        raise ValueError(f"Ungültiges Datum: {wert}")
    if not 1900 <= d.year <= 9999:
        raise ValueError(f"Jahreszahl außerhalb des gültigen Bereichs: {wert}")
    return d.isoformat()


Datum = Annotated[str, AfterValidator(_datum_pruefen)]

from .core import altersvorsorge as altersvorsorge_modul
from .core import auswertungen, backup, buchungen, budgets as budgets_modul
from .core import darlehen as darlehen_modul
from .core import darlehensraten
from .core import db as db_modul
from .core import import_export
from .core import personen as personen_modul
from .core import plan_buchungen, startup, vertragsauswertung, wiederherstellen, wiederkehrend, zuruecksetzen
from .core.db import kategorie_id, resource_pfad, verbindung
from .core import zeit


class PfadNormalisierenMiddleware:
    """
    Normalisiert mehrfache aufeinanderfolgende Schrägstriche im Pfad
    (z. B. '//' -> '/'). Der Home-Assistant-Ingress-Proxy kann je nach
    Aufrufkontext einen doppelten Slash erzeugen (z. B. 'GET //' statt
    'GET /'), was FastAPI ohne diese Normalisierung mit 404 quittiert,
    da die Root-Route dann nicht mehr passt.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            pfad = scope.get("path", "")
            normalisiert = re.sub(r"/{2,}", "/", pfad)
            if normalisiert != pfad:
                scope = dict(scope)
                scope["path"] = normalisiert
        await self.app(scope, receive, send)


app = FastAPI(title="Private Finanzverwaltung")
app.add_middleware(PfadNormalisierenMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def kein_cache(request, call_next):
    """
    Caching komplett abschalten.

    Die Anwendung läuft bei jedem Start unter derselben Adresse
    (127.0.0.1:8935). Ohne diesen Header behält der Browser die
    JavaScript- und CSS-Dateien einer früheren Programmversion im Cache
    und führt nach einem Update weiterhin den alten Code aus - neue
    Funktionen erscheinen dann einfach nicht. Bei einer lokalen Anwendung
    bringt Caching ohnehin keinen Vorteil.
    """
    antwort = await call_next(request)
    antwort.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    antwort.headers["Pragma"] = "no-cache"
    antwort.headers["Expires"] = "0"
    return antwort

STARTUP_ERGEBNIS: dict = {}


@app.on_event("startup")
def beim_start():
    global STARTUP_ERGEBNIS
    STARTUP_ERGEBNIS = startup.ausfuehren()


def db():
    conn = verbindung()
    try:
        yield conn
    finally:
        conn.close()


def _parse_datum(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(_datum_pruefen(s))
    except ValueError as e:
        raise HTTPException(422, str(e))


# ─── Start-Status ───────────────────────────────────────────────────

@app.get("/api/start-status")
def start_status():
    # Serverzeit (seit v2.0, Befund H): die App rechnet fest in Europe/Berlin;
    # container_zeitzone zeigt zur Kontrolle, was der Container selbst meint.
    return {**STARTUP_ERGEBNIS, "version": os.environ.get("FINANZAPP_VERSION", "dev"),
            "version_datum": os.environ.get("FINANZAPP_VERSION_DATUM", ""),
            "serverzeit": zeit.jetzt().strftime("%d.%m.%Y %H:%M"), "zeitzone": zeit.ZEITZONE_NAME,
            "container_zeitzone": datetime.now().astimezone().tzname() or "?"}


# ─── Personen ───────────────────────────────────────────────────────

class PersonIn(BaseModel):
    name: str
    farbe: Optional[str] = None


@app.get("/api/personen")
def api_personen_liste(nur_aktive: bool = True):
    conn = verbindung()
    try:
        return [dict(p) for p in personen_modul.personen_liste(conn, nur_aktive)]
    finally:
        conn.close()


@app.post("/api/personen")
def api_person_anlegen(payload: PersonIn):
    conn = verbindung()
    try:
        return {"id": personen_modul.person_anlegen(conn, payload.name, payload.farbe)}
    finally:
        conn.close()


@app.put("/api/personen/{person_id}")
def api_person_bearbeiten(person_id: int, payload: dict):
    conn = verbindung()
    try:
        personen_modul.person_bearbeiten(conn, person_id, **payload)
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/personen/{person_id}")
def api_person_loeschen(person_id: int):
    conn = verbindung()
    try:
        personen_modul.person_loeschen(conn, person_id)
        return {"ok": True}
    finally:
        conn.close()


# ─── Konten ─────────────────────────────────────────────────────────

class KontoIn(BaseModel):
    name: str
    typ: str
    eroeffnungsdatum: Datum
    person_id: Optional[int] = None
    in_gesamtsaldo: bool = True
    farbe: Optional[str] = None


@app.get("/api/konten")
def api_konten_liste(nur_aktive: bool = True, person_id: Optional[int] = None):
    conn = verbindung()
    try:
        konten = [dict(k) for k in buchungen.konten_liste(conn, nur_aktive, person_id)]
        for k in konten:
            k["saldo"] = buchungen.saldo(conn, k["id"])
        return konten
    finally:
        conn.close()


@app.post("/api/konten")
def api_konto_anlegen(payload: KontoIn):
    conn = verbindung()
    try:
        konto_id = buchungen.konto_anlegen(conn, payload.name, payload.typ,
                                            _parse_datum(payload.eroeffnungsdatum),
                                            payload.person_id, payload.in_gesamtsaldo, payload.farbe)
        return {"id": konto_id}
    finally:
        conn.close()


@app.put("/api/konten/{konto_id}")
def api_konto_bearbeiten(konto_id: int, payload: dict):
    if payload.get("eroeffnungsdatum"):
        _parse_datum(payload["eroeffnungsdatum"])
    conn = verbindung()
    try:
        buchungen.konto_bearbeiten(conn, konto_id, **payload)
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/konten/{konto_id}")
def api_konto_loeschen(konto_id: int):
    conn = verbindung()
    try:
        buchungen.konto_loeschen(conn, konto_id)
        return {"ok": True}
    finally:
        conn.close()


class SaldoKorrekturIn(BaseModel):
    konto_id: int
    datum: Datum
    saldo: float
    kommentar: Optional[str] = None


@app.post("/api/saldo-korrekturen")
def api_saldo_korrektur(payload: SaldoKorrekturIn):
    # Seit v2.0: keine Korrekturen in der Zukunft (Kontostand ist dann noch
    # nicht festgestellt; die Saldo-Prognose könnte sie auch nicht sinnvoll
    # verrechnen).
    if payload.datum and payload.datum > zeit.heute().isoformat():
        raise HTTPException(422, "Eine Saldo-Korrektur darf nicht in der Zukunft liegen.")
    conn = verbindung()
    try:
        korrektur_id = buchungen.saldo_korrektur_anlegen(
            conn, konto_id=payload.konto_id, datum=_parse_datum(payload.datum),
            saldo=payload.saldo, kommentar=payload.kommentar,
        )
        return {"id": korrektur_id}
    finally:
        conn.close()


# ─── Kategorien ─────────────────────────────────────────────────────

class KategorieIn(BaseModel):
    name: str
    parent_id: Optional[int] = None
    typ: Optional[str] = None


@app.get("/api/kategorien")
def api_kategorien():
    conn = verbindung()
    try:
        return [dict(k) for k in buchungen.kategorien_baum(conn)]
    finally:
        conn.close()


@app.post("/api/kategorien")
def api_kategorie_anlegen(payload: KategorieIn):
    conn = verbindung()
    try:
        return {"id": buchungen.kategorie_anlegen(conn, payload.name, payload.parent_id, payload.typ)}
    finally:
        conn.close()


@app.put("/api/kategorien/{kategorie_id}")
def api_kategorie_bearbeiten(kategorie_id: int, payload: KategorieIn):
    conn = verbindung()
    try:
        buchungen.kategorie_bearbeiten(conn, kategorie_id, payload.name, payload.parent_id, payload.typ)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        conn.close()


@app.delete("/api/kategorien/{kategorie_id}")
def api_kategorie_loeschen(kategorie_id: int):
    conn = verbindung()
    try:
        buchungen.kategorie_loeschen(conn, kategorie_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        conn.close()


# ─── Buchungen ──────────────────────────────────────────────────────

class BuchungIn(BaseModel):
    konto_id: int
    datum: Datum
    betrag: float
    kategorie_id: Optional[int] = None
    typ: str = "Ist"
    beschreibung: Optional[str] = None
    zielkonto_id: Optional[int] = None
    sparziel_id: Optional[int] = None


@app.get("/api/buchungen")
def api_buchungen(konto_id: Optional[int] = None, von: Optional[str] = None,
                   bis: Optional[str] = None, typ: Optional[str] = None,
                   ziel_darlehen_id: Optional[int] = None, inkl_anstehende: bool = False,
                   herkunft: Optional[str] = None, kategorie_id: Optional[int] = None,
                   person_id: Optional[int] = None, inflation: bool = False):
    conn = verbindung()
    try:
        rows = buchungen.buchungen_liste(conn, konto_id, _parse_datum(von), _parse_datum(bis),
                                          typ, ziel_darlehen_id, herkunft, kategorie_id, person_id)
        ergebnis = [dict(r) for r in rows]

        if inkl_anstehende and typ != "Ist" and herkunft != "manuell":
            heute = zeit.heute()
            von_dt = _parse_datum(von) or heute
            bis_dt = _parse_datum(bis) or (heute + relativedelta(months=wiederkehrend.ANZEIGE_HORIZONT_MONATE))
            ab = max(heute, von_dt - relativedelta(days=1))
            if ab < bis_dt:
                feiertage = {date.fromisoformat(r["datum"]): r["name"]
                             for r in conn.execute("SELECT datum, name FROM feiertage").fetchall()}
                anstehend = wiederkehrend.anstehende_termine(conn, feiertage, ab, bis_dt, inflation=inflation)
                anstehend += darlehensraten.anstehende_raten(conn, feiertage, ab, bis_dt)
                anstehend += altersvorsorge_modul.anstehende_termine(conn, feiertage, ab, bis_dt, inflation=inflation)
                if konto_id is not None:
                    # Übertragungen (Umbuchungs-Vorlagen, seit v1.10) auch beim Zielkonto
                    anstehend = [b for b in anstehend
                                 if b["konto_id"] == konto_id or b.get("zielkonto_id") == konto_id]
                if kategorie_id is not None:
                    anstehend = [b for b in anstehend if b.get("kategorie_id") == kategorie_id]
                if person_id is not None:
                    konten_von_person = {k["id"] for k in buchungen.konten_liste(conn, False, person_id)}
                    anstehend = [b for b in anstehend if b["konto_id"] in konten_von_person]
                for i, b in enumerate(anstehend):
                    b["id"] = f"virtuell-{i}"
                ergebnis += anstehend

        return ergebnis
    finally:
        conn.close()


@app.post("/api/buchungen")
def api_buchung_anlegen(payload: BuchungIn):
    conn = verbindung()
    try:
        kategorie = payload.kategorie_id
        auto_kategorie = None
        if kategorie is None and payload.typ != "Uebertragung":
            kategorie = buchungen.kategorie_vorschlagen(conn, payload.beschreibung)
            auto_kategorie = kategorie
        if kategorie is None and payload.typ != "Uebertragung":
            raise HTTPException(400, "Kategorie fehlt und konnte nicht automatisch ermittelt werden.")

        fehler = buchungen.sparziel_pruefen(conn, payload.typ, payload.konto_id, payload.zielkonto_id,
                                            payload.sparziel_id)
        if fehler:
            raise HTTPException(422, fehler)

        duplikat = buchungen.moegliches_duplikat(
            conn, payload.konto_id, _parse_datum(payload.datum), payload.betrag)

        buchung_id = buchungen.buchung_anlegen(
            conn, konto_id=payload.konto_id, datum=_parse_datum(payload.datum),
            betrag=payload.betrag, kategorie_id=kategorie, typ=payload.typ,
            beschreibung=payload.beschreibung, zielkonto_id=payload.zielkonto_id,
            sparziel_id=payload.sparziel_id,
        )
        return {"id": buchung_id, "duplikat": duplikat, "auto_kategorie": auto_kategorie}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        conn.close()


@app.delete("/api/buchungen/{buchung_id}")
def api_buchung_loeschen(buchung_id: int):
    conn = verbindung()
    try:
        buchungen.buchung_loeschen(conn, buchung_id)
        return {"ok": True}
    finally:
        conn.close()


# ─── Wiederkehrende Buchungen ───────────────────────────────────────

class WiederkehrendIn(BaseModel):
    konto_id: int
    betrag: float
    kategorie_id: Optional[int] = None   # bei Umbuchung (zielkonto_id) ohne Bedeutung
    beschreibung: Optional[str] = None
    intervall: str
    tag_des_monats: int
    monat: Optional[int] = None
    startdatum: Datum
    enddatum: Optional[Datum] = None
    inflationsflag: bool = False
    dynamik_aktiv: bool = False
    dynamik_rhythmus_jahre: Optional[int] = None
    dynamik_prozent: Optional[float] = None
    dynamik_startjahr: Optional[int] = None
    person_id: Optional[int] = None
    zielkonto_id: Optional[int] = None   # seit v1.10: gesetzt = Umbuchungs-Vorlage
    sparziel_id: Optional[int] = None    # seit v1.10: nur bei Umbuchung


def _umbuchung_teilbaum(conn) -> set[int]:
    """Die Systemkategorie "Umbuchung" samt aller Unterkategorien."""
    return set(budgets_modul.kategorie_ids(conn, buchungen.umbuchung_kategorie_id(conn), True))


def _wiederkehrend_pruefen(conn, payload: WiederkehrendIn) -> dict:
    """Prüft eine Vorlage und liefert die zu speichernden, normalisierten
    Werte. Seit v1.10:
      - Dynamik ohne Prozentwert wird abgelehnt (analog zum Datei-Import).
        Bis v1.9.1 schickte das Formular bei jedem Speichern eine
        Scheindynamik, die das Inflations-Häkchen verdrängte.
      - Umbuchung (zielkonto_id gesetzt): Zielkonto muss existieren und sich
        vom Quellkonto unterscheiden; Kategorie fest "Umbuchung", Betrag ohne
        Vorzeichen, weder Inflation noch Dynamik; optionales Sparziel.
      - Buchung: Kategorie Pflicht und nicht aus dem Teilbaum "Umbuchung"
        (dafür gibt es den Typ Umbuchung); kein Sparziel."""
    werte = payload.model_dump()
    if payload.zielkonto_id:
        if payload.zielkonto_id == payload.konto_id:
            raise HTTPException(422, "Zielkonto und Konto müssen sich unterscheiden.")
        if not conn.execute("SELECT 1 FROM konten WHERE id = ?", (payload.zielkonto_id,)).fetchone():
            raise HTTPException(422, "Das Zielkonto existiert nicht.")
        fehler = buchungen.sparziel_pruefen(conn, "Uebertragung", payload.konto_id, payload.zielkonto_id,
                                            payload.sparziel_id)
        if fehler:
            raise HTTPException(422, fehler)
        werte.update(kategorie_id=buchungen.umbuchung_kategorie_id(conn), betrag=abs(payload.betrag),
                     inflationsflag=False, dynamik_aktiv=False, dynamik_rhythmus_jahre=None,
                     dynamik_prozent=None, dynamik_startjahr=None,
                     sparziel_id=payload.sparziel_id or None)
        return werte
    if payload.dynamik_aktiv and payload.dynamik_prozent is None:
        raise HTTPException(422, "Dynamik ist aktiv, aber es fehlt der Prozentwert (dynamik_prozent).")
    if payload.kategorie_id is None:
        raise HTTPException(422, "Kategorie fehlt.")
    if payload.kategorie_id in _umbuchung_teilbaum(conn):
        raise HTTPException(422, "Die Kategorie „Umbuchung“ ist Übertragungen vorbehalten. "
                                 "Bitte als Typ „Umbuchung“ mit Zielkonto anlegen.")
    werte.update(zielkonto_id=None, sparziel_id=None,
                 betrag=wiederkehrend.vorzeichen_anwenden(conn, payload.kategorie_id, payload.betrag),
                 inflationsflag=bool(payload.inflationsflag and not payload.dynamik_aktiv))
    return werte


_WK_SPALTEN = ["konto_id", "betrag", "kategorie_id", "beschreibung", "intervall", "tag_des_monats",
               "monat", "startdatum", "enddatum", "inflationsflag", "dynamik_aktiv",
               "dynamik_rhythmus_jahre", "dynamik_prozent", "dynamik_startjahr", "person_id",
               "zielkonto_id", "sparziel_id"]


def _wk_werte(werte: dict) -> tuple:
    return tuple(int(werte[s]) if isinstance(werte[s], bool) else werte[s] for s in _WK_SPALTEN)


@app.get("/api/wiederkehrend")
def api_wiederkehrend_liste(person_id: Optional[int] = None):
    conn = verbindung()
    try:
        sql = """SELECT w.*, k.name AS kategorie_name, ko.name AS konto_name,
                        zk.name AS zielkonto_name, sz.name AS sparziel_name
                 FROM wiederkehrende_buchungen w
                 LEFT JOIN kategorien k ON k.id = w.kategorie_id
                 LEFT JOIN konten ko ON ko.id = w.konto_id
                 LEFT JOIN konten zk ON zk.id = w.zielkonto_id
                 LEFT JOIN budgets sz ON sz.id = w.sparziel_id"""
        params: list = []
        if person_id is not None:
            sql += " WHERE w.person_id = ?"
            params.append(person_id)
        rows = conn.execute(sql + " ORDER BY w.beschreibung", params).fetchall()
        ergebnis = []
        for r in rows:
            d = dict(r)
            monate = wiederkehrend.abgeleitete_monate(r)
            d["monate_anzeige"] = "alle" if len(monate) == 12 else ", ".join(str(m) for m in monate)
            # Seit v1.10: Umbuchungen zeigen in der Kategorie-Spalte das Ziel.
            d["ist_umbuchung"] = bool(r["zielkonto_id"])
            if r["zielkonto_id"]:
                d["kategorie_anzeige"] = f"Umbuchung → {r['zielkonto_name'] or '?'}"
            else:
                d["kategorie_anzeige"] = r["kategorie_name"]
            # Defensiv gegen dynamik_prozent = NULL bei aktiver Dynamik (kann
            # bei sehr alten, vor 1.3.0 angelegten Vorlagen vorkommen) - ein
            # einzelner kaputter Datensatz darf nie die gesamte Liste
            # unbrauchbar machen (siehe Bugfix v1.4).
            if r["dynamik_aktiv"] and r["dynamik_prozent"] is not None:
                d["dynamik_anzeige"] = f"alle {r['dynamik_rhythmus_jahre']} J. · +{r['dynamik_prozent']:g} %"
            elif r["dynamik_aktiv"]:
                d["dynamik_anzeige"] = "Dynamik aktiv (Wert fehlt)"
            else:
                d["dynamik_anzeige"] = "–"
            ergebnis.append(d)
        return ergebnis
    finally:
        conn.close()


def _wk_loeschen(conn, vorlage_id: int, inkl_planbuchungen: bool = True) -> None:
    """Löscht eine Vorlage endgültig; noch offene Plan-Buchungen optional mit
    (seit v2.0 als Hilfsfunktion, auch vom XLSX-Roundtrip genutzt)."""
    if inkl_planbuchungen:
        conn.execute("DELETE FROM buchungen WHERE wiederkehrend_id = ? AND typ = 'Plan'", (vorlage_id,))
    conn.execute("UPDATE buchungen SET wiederkehrend_id = NULL WHERE wiederkehrend_id = ?", (vorlage_id,))
    conn.execute("DELETE FROM wiederkehrende_buchungen WHERE id = ?", (vorlage_id,))
    conn.commit()


@app.delete("/api/wiederkehrend/{vorlage_id}")
def api_wiederkehrend_loeschen(vorlage_id: int, inkl_planbuchungen: bool = True):
    conn = verbindung()
    try:
        _wk_loeschen(conn, vorlage_id, inkl_planbuchungen)
        return {"ok": True}
    finally:
        conn.close()


def _wk_anlegen(conn, payload: WiederkehrendIn) -> int:
    # Vorzeichen sofort aus dem Kategorietyp ableiten (wie bei normalen
    # Buchungen) statt erst beim nächsten Programmstart - siehe Bugfix v1.4.
    # Prüfung/Normalisierung in _wiederkehrend_pruefen.
    werte = _wiederkehrend_pruefen(conn, payload)
    cur = conn.execute(
        f"""INSERT INTO wiederkehrende_buchungen ({', '.join(_WK_SPALTEN)})
           VALUES ({', '.join('?' * len(_WK_SPALTEN))})""",
        _wk_werte(werte),
    )
    neu_id = cur.lastrowid
    conn.commit()
    wiederkehrend.erzeuge_faellige_ist_buchungen(conn, _feiertage_laden(conn))
    return neu_id


@app.post("/api/wiederkehrend")
def api_wiederkehrend_anlegen(payload: WiederkehrendIn):
    conn = verbindung()
    try:
        return {"id": _wk_anlegen(conn, payload)}
    finally:
        conn.close()


def _wk_aendern(conn, vorlage_id: int, payload: WiederkehrendIn) -> None:
    alt = conn.execute("SELECT startdatum FROM wiederkehrende_buchungen WHERE id = ?", (vorlage_id,)).fetchone()
    if alt is None:
        raise HTTPException(404, "Vorlage nicht gefunden.")
    # Wechsel Buchung <-> Umbuchung ist erlaubt (seit v1.10) und wirkt nur
    # auf künftige Termine; bereits erzeugte Buchungen bleiben unverändert.
    werte = _wiederkehrend_pruefen(conn, payload)
    conn.execute(
        f"UPDATE wiederkehrende_buchungen SET {', '.join(f'{s} = ?' for s in _WK_SPALTEN)} WHERE id = ?",
        (*_wk_werte(werte), vorlage_id),
    )
    conn.commit()
    feiertage = _feiertage_laden(conn)
    fenster = _vorverlegt(alt["startdatum"], payload.startdatum)
    if fenster:
        wiederkehrend.erzeuge_faellige_ist_buchungen(conn, feiertage, nur_id=vorlage_id, fenster=fenster)
    wiederkehrend.erzeuge_faellige_ist_buchungen(conn, feiertage)


@app.put("/api/wiederkehrend/{vorlage_id}")
def api_wiederkehrend_bearbeiten(vorlage_id: int, payload: WiederkehrendIn):
    conn = verbindung()
    try:
        _wk_aendern(conn, vorlage_id, payload)
        return {"ok": True}
    finally:
        conn.close()


def _wk_aktiv_setzen(conn, vorlage_id: int, aktiv: bool) -> None:
    if aktiv and conn.execute(
            "SELECT 1 FROM wiederkehrende_buchungen WHERE id = ? AND zielkonto_id = konto_id",
            (vorlage_id,)).fetchone():
        # Kann nach "Konten löschen" (Daten zurücksetzen) entstehen, seit v1.10.
        raise HTTPException(422, "Quell- und Zielkonto dieser Umbuchung sind gleich. "
                                 "Bitte zuerst über „Ändern“ ein anderes Zielkonto wählen.")
    conn.execute("UPDATE wiederkehrende_buchungen SET aktiv = ? WHERE id = ?", (int(aktiv), vorlage_id))
    conn.commit()


@app.put("/api/wiederkehrend/{vorlage_id}/aktiv")
def api_wiederkehrend_aktiv(vorlage_id: int, aktiv: bool):
    conn = verbindung()
    try:
        _wk_aktiv_setzen(conn, vorlage_id, aktiv)
        return {"ok": True}
    finally:
        conn.close()


# ─── Erzeugungsmarke bei rückwirkenden Änderungen (seit v1.8) ─────────

def _vorverlegt(alt: Optional[str], neu: Optional[str]):
    """Nachhol-Fenster [neu, alt), wenn ein Startdatum vorverlegt wurde."""
    if alt and neu and neu < alt:
        return (date.fromisoformat(neu), date.fromisoformat(alt))
    return None


# ─── Darlehen ───────────────────────────────────────────────────────

class DarlehenIn(BaseModel):
    bezeichnung: str
    zinssatz: float
    zinsbeginn: Datum
    tilgungsbeginn: Datum
    laufzeit_jahre: int
    ende_zinsbindung: Datum
    anschlusszinssatz: float
    raten_modus: str
    darlehenssumme: Optional[float] = None   # seit v1.9 (vertraglich vereinbart)
    tilgungssatz: Optional[float] = None
    feste_rate: Optional[float] = None
    anschluss_feste_rate: Optional[float] = None
    zahlungskonto_id: Optional[int] = None
    person_id: Optional[int] = None


@app.get("/api/darlehen")
def api_darlehen_liste(person_id: Optional[int] = None):
    conn = verbindung()
    try:
        if person_id is not None:
            rows = conn.execute("SELECT * FROM darlehen WHERE person_id = ?", (person_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM darlehen").fetchall()
        ergebnis = []
        for row in rows:
            warnungen = darlehen_modul.pruefe_darlehen_konsistenz(_darlehen_obj(conn, row))
            ausgezahlt = conn.execute(
                "SELECT COALESCE(SUM(betrag), 0) FROM darlehen_auszahlungen WHERE darlehen_id = ?",
                (row["id"],),
            ).fetchone()[0]
            d = dict(row)
            d["warnungen"] = warnungen
            d["ausgezahlt"] = ausgezahlt
            ergebnis.append(d)
        return ergebnis
    finally:
        conn.close()


def _darlehen_obj(conn, row):
    auszahlungen = conn.execute(
        "SELECT datum, betrag FROM darlehen_auszahlungen WHERE darlehen_id = ?", (row["id"],)
    ).fetchall()
    return darlehen_modul.aus_db_zeile(row, auszahlungen)


def _darlehen_params(payload: DarlehenIn):
    return (payload.bezeichnung, payload.zinssatz, payload.zinsbeginn, payload.tilgungsbeginn,
            payload.laufzeit_jahre, payload.ende_zinsbindung, payload.anschlusszinssatz,
            payload.raten_modus, payload.tilgungssatz, payload.feste_rate,
            payload.anschluss_feste_rate, payload.zahlungskonto_id, payload.person_id,
            payload.darlehenssumme)


def _darlehen_anlegen(conn, payload: DarlehenIn) -> int:
    cur = conn.execute(
        """INSERT INTO darlehen
           (bezeichnung, zinssatz, zinsbeginn, tilgungsbeginn, laufzeit_jahre,
            ende_zinsbindung, anschlusszinssatz, raten_modus, tilgungssatz,
            feste_rate, anschluss_feste_rate, zahlungskonto_id, person_id, darlehenssumme)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        _darlehen_params(payload),
    )
    conn.commit()
    return cur.lastrowid


@app.post("/api/darlehen")
def api_darlehen_anlegen(payload: DarlehenIn):
    conn = verbindung()
    try:
        return {"id": _darlehen_anlegen(conn, payload)}
    finally:
        conn.close()


def _darlehen_aendern(conn, darlehen_id: int, payload: DarlehenIn) -> None:
    row = conn.execute("SELECT id, zinsbeginn FROM darlehen WHERE id = ?", (darlehen_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Darlehen nicht gefunden.")
    fenster = _vorverlegt(row["zinsbeginn"], payload.zinsbeginn)
    conn.execute(
        """UPDATE darlehen SET
           bezeichnung = ?, zinssatz = ?, zinsbeginn = ?, tilgungsbeginn = ?, laufzeit_jahre = ?,
           ende_zinsbindung = ?, anschlusszinssatz = ?, raten_modus = ?, tilgungssatz = ?,
           feste_rate = ?, anschluss_feste_rate = ?, zahlungskonto_id = ?, person_id = ?,
           darlehenssumme = ?
           WHERE id = ?""",
        (*_darlehen_params(payload), darlehen_id),
    )
    conn.commit()
    if fenster:
        darlehensraten.erzeuge_faellige_ist_buchungen(conn, _feiertage_laden(conn),
                                                      nur_id=darlehen_id, fenster=fenster)


def _darlehen_loeschen(conn, darlehen_id: int) -> None:
    """Seit v2.0 (XLSX-Roundtrip): einzelnes Darlehen löschen - wie „Daten
    zurücksetzen → Darlehen“, nur für dieses eine: Buchungen bleiben und
    werden gelöst, Vorlagen verlieren die Verknüpfung, Auszahlungen entfallen."""
    conn.execute("UPDATE buchungen SET ziel_darlehen_id = NULL WHERE ziel_darlehen_id = ?", (darlehen_id,))
    conn.execute("UPDATE wiederkehrende_buchungen SET darlehen_id = NULL WHERE darlehen_id = ?", (darlehen_id,))
    conn.execute("DELETE FROM darlehen_auszahlungen WHERE darlehen_id = ?", (darlehen_id,))
    conn.execute("DELETE FROM darlehen WHERE id = ?", (darlehen_id,))
    conn.commit()


@app.put("/api/darlehen/{darlehen_id}")
def api_darlehen_bearbeiten(darlehen_id: int, payload: DarlehenIn):
    conn = verbindung()
    try:
        _darlehen_aendern(conn, darlehen_id, payload)
        return {"ok": True}
    finally:
        conn.close()


class AuszahlungIn(BaseModel):
    datum: Datum
    betrag: float


def _auszahlung_anlegen(conn, darlehen_id: int, payload: AuszahlungIn) -> Optional[str]:
    row = conn.execute("SELECT * FROM darlehen WHERE id = ?", (darlehen_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Darlehen nicht gefunden.")
    erste_bisher = conn.execute(
        "SELECT MIN(datum) FROM darlehen_auszahlungen WHERE darlehen_id = ?", (darlehen_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO darlehen_auszahlungen (darlehen_id, datum, betrag) VALUES (?, ?, ?)",
        (darlehen_id, payload.datum, payload.betrag),
    )
    conn.commit()
    # Eine nachträglich erfasste Auszahlung VOR der bisher ersten erzeugt
    # Zinsen in Monaten, die bisher ohne Restschuld (also ohne Buchung)
    # waren -> genau diese Monate nachbuchen.
    neu = _parse_datum(payload.datum)
    if row["zahlungskonto_id"] and (erste_bisher is None or payload.datum < erste_bisher):
        bis = date.fromisoformat(erste_bisher) if erste_bisher else date.max
        darlehensraten.erzeuge_faellige_ist_buchungen(conn, _feiertage_laden(conn), nur_id=darlehen_id,
                                                      fenster=(date(neu.year, neu.month, 1), bis))
    if row["zahlungskonto_id"]:
        # Die Darlehensauszahlung ist salden-wirksam: das Geld geht auf
        # dem hinterlegten Zahlungskonto ein.
        buchungen.buchung_anlegen(
            conn, konto_id=row["zahlungskonto_id"], datum=_parse_datum(payload.datum),
            betrag=abs(payload.betrag),
            kategorie_id=kategorie_id(conn, "darlehen_auszahlung"), typ="Ist",
            beschreibung=f"{row['bezeichnung']} - Auszahlung", ziel_darlehen_id=darlehen_id,
        )
        return None
    return "Kein Zahlungskonto hinterlegt - Auszahlung wurde nicht auf einem Konto verbucht."


def _auszahlung_buchung(conn, auszahlung) -> Optional[int]:
    """Die zur Auszahlung gehörende Buchung auf dem Zahlungskonto (gleiches
    Darlehen, Kategorie Auszahlung, Datum und Betrag) - es gibt keinen
    Fremdschlüssel, daher über die Merkmale (nur eindeutige Treffer)."""
    rows = conn.execute(
        """SELECT id FROM buchungen WHERE ziel_darlehen_id = ? AND kategorie_id = ? AND datum = ?
           AND ABS(ABS(betrag) - ?) < 0.005""",
        (auszahlung["darlehen_id"], kategorie_id(conn, "darlehen_auszahlung"), auszahlung["datum"],
         abs(auszahlung["betrag"]))).fetchall()
    return rows[0]["id"] if len(rows) == 1 else None


def _auszahlung_aendern(conn, auszahlung_id: int, datum: str, betrag: float) -> None:
    """Seit v2.0 (Roundtrip): Auszahlung ändern, die zugehörige Buchung zieht
    mit. Bereits gebuchte Zins-/Tilgungsraten bleiben unverändert."""
    alt = conn.execute("SELECT * FROM darlehen_auszahlungen WHERE id = ?", (auszahlung_id,)).fetchone()
    if alt is None:
        raise HTTPException(404, "Auszahlung nicht gefunden.")
    b_id = _auszahlung_buchung(conn, alt)
    conn.execute("UPDATE darlehen_auszahlungen SET datum = ?, betrag = ? WHERE id = ?", (datum, betrag, auszahlung_id))
    if b_id:
        conn.execute("UPDATE buchungen SET datum = ?, betrag = ? WHERE id = ?", (datum, abs(betrag), b_id))
    conn.commit()


def _auszahlung_loeschen(conn, auszahlung_id: int) -> None:
    alt = conn.execute("SELECT * FROM darlehen_auszahlungen WHERE id = ?", (auszahlung_id,)).fetchone()
    if alt is None:
        return
    b_id = _auszahlung_buchung(conn, alt)
    conn.execute("DELETE FROM darlehen_auszahlungen WHERE id = ?", (auszahlung_id,))
    if b_id:
        conn.execute("DELETE FROM buchungen WHERE id = ?", (b_id,))
    conn.commit()


@app.post("/api/darlehen/{darlehen_id}/auszahlungen")
def api_auszahlung_anlegen(darlehen_id: int, payload: AuszahlungIn):
    conn = verbindung()
    try:
        return {"ok": True, "hinweis": _auszahlung_anlegen(conn, darlehen_id, payload)}
    finally:
        conn.close()


@app.get("/api/darlehen/{darlehen_id}/tilgungsplan")
def api_tilgungsplan(darlehen_id: int):
    conn = verbindung()
    try:
        return auswertungen.tilgungsplan_fuer_darlehen(conn, darlehen_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    finally:
        conn.close()


class SondertilgungIn(BaseModel):
    konto_id: int
    datum: Datum
    betrag: float


@app.post("/api/darlehen/{darlehen_id}/sondertilgung")
def api_sondertilgung(darlehen_id: int, payload: SondertilgungIn):
    conn = verbindung()
    try:
        row = conn.execute("SELECT * FROM darlehen WHERE id = ?", (darlehen_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Darlehen nicht gefunden.")
        phasen_warnung = darlehen_modul.pruefe_sondertilgungs_zeitpunkt(
            _darlehen_obj(conn, row), _parse_datum(payload.datum)
        )
        buchung_id = buchungen.buchung_anlegen(
            conn, konto_id=payload.konto_id, datum=_parse_datum(payload.datum),
            betrag=-abs(payload.betrag), kategorie_id=kategorie_id(conn, "darlehen_sondertilgung"),
            typ="Ist",
            beschreibung=f"Sondertilgung {row['bezeichnung']}", ziel_darlehen_id=darlehen_id,
        )
        return {"id": buchung_id, "warnung": phasen_warnung}
    finally:
        conn.close()


# ─── Plan-Buchungen: Bestätigungsmaske ──────────────────────────────

@app.get("/api/plan-buchungen/protokoll")
def api_plan_protokoll(limit: int = 50):
    conn = verbindung()
    try:
        rows = conn.execute(
            """SELECT p.*, b.datum AS buchung_datum, b.betrag, b.beschreibung, b.typ AS buchung_typ
               FROM plan_buchung_protokoll p
               LEFT JOIN buchungen b ON b.id = p.buchung_id
               ORDER BY p.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.post("/api/plan-buchungen/{buchung_id}/ablehnen-anpassen")
def api_ablehnen_anpassen(buchung_id: int, neues_datum: str):
    conn = verbindung()
    try:
        plan_buchungen.ablehnen_anpassen(conn, buchung_id, _parse_datum(neues_datum))
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/plan-buchungen/{buchung_id}/ablehnen-loeschen")
def api_ablehnen_loeschen(buchung_id: int, inkl_zukuenftige: bool = True):
    conn = verbindung()
    try:
        anzahl = plan_buchungen.ablehnen_loeschen(conn, buchung_id, inkl_zukuenftige)
        return {"geloescht": anzahl}
    finally:
        conn.close()


# ─── Auswertungen ───────────────────────────────────────────────────

def _id_menge(liste: Optional[str], einzeln: Optional[int] = None):
    """Mehrfachfilter (seit v2.3): konten=1,3 bzw. kategorien=4,5,6.
    Parameter fehlt = kein Filter (None), leer = nichts gewählt (leere Menge).
    Der alte Einzelparameter (konto_id/kategorie_id) gilt weiter als Menge
    mit einem Element."""
    if liste is None:
        return None if einzeln is None else {einzeln}
    try:
        menge = {int(t) for t in liste.split(",") if t.strip()}
    except ValueError:
        raise HTTPException(422, "Ungültige ID-Liste.")
    if einzeln is not None:
        menge.add(einzeln)
    return menge


@app.get("/api/auswertungen/saldo-verlauf")
def api_saldo_verlauf(von: str, bis: str, inkl_darlehen: bool = True,
                       konto_id: Optional[int] = None, kategorie_id: Optional[int] = None,
                       konten: Optional[str] = None, kategorien: Optional[str] = None,
                       inflation: bool = False):
    conn = verbindung()
    try:
        return auswertungen.saldo_verlauf(conn, _parse_datum(von), _parse_datum(bis),
                                           konto_ids=_id_menge(konten, konto_id), inkl_darlehen=inkl_darlehen,
                                           kategorie_ids=_id_menge(kategorien, kategorie_id), inflation=inflation)
    finally:
        conn.close()


@app.get("/api/auswertungen/darlehen")
def api_auswertung_darlehen(darlehen_id: Optional[int] = None, von: Optional[str] = None,
                            bis: Optional[str] = None):
    """Darlehen-Tab der Auswertungen (seit v1.9): Kennzahlen, Restschuld-
    Verlauf, Jahrestabelle und Tabelle je Darlehen mit Summenzeile."""
    conn = verbindung()
    try:
        return vertragsauswertung.darlehen_auswertung(conn, darlehen_id, _parse_datum(von), _parse_datum(bis))
    finally:
        conn.close()


@app.get("/api/auswertungen/altersvorsorge")
def api_auswertung_altersvorsorge(av_id: Optional[int] = None, von: Optional[str] = None,
                                  bis: Optional[str] = None, inflation: bool = False):
    """Altersvorsorge-Tab der Auswertungen (seit v1.9)."""
    conn = verbindung()
    try:
        return vertragsauswertung.altersvorsorge_auswertung(conn, av_id, _parse_datum(von), _parse_datum(bis),
                                                            inflation=inflation)
    finally:
        conn.close()


@app.get("/api/auswertungen/altersvorsorge-korridor")
def api_altersvorsorge_korridor(von: str, bis: str, altersvorsorge_id: Optional[int] = None,
                                 konto_id: Optional[int] = None, konten: Optional[str] = None,
                                 inflation: bool = False):
    """Monatliche Differenz voraussichtlich./.garantiert - für den optionalen
    Korridor im Saldo-Verlauf bzw. in der Altersvorsorge-Detailansicht."""
    conn = verbindung()
    try:
        von_dt, bis_dt = _parse_datum(von), _parse_datum(bis)
        werte = altersvorsorge_modul.korridor_projektion(conn, von_dt, bis_dt, _id_menge(konten, konto_id),
                                                     altersvorsorge_id,
                                                     inflation=inflation)
        monate = sorted(werte)
        return {"monate": [m.isoformat() for m in monate], "werte": [werte[m] for m in monate]}
    finally:
        conn.close()


@app.get("/api/auswertungen/cashflow")
def api_cashflow(von: str, bis: str, konto_id: Optional[int] = None, kategorie_id: Optional[int] = None,
                 konten: Optional[str] = None, kategorien: Optional[str] = None, inflation: bool = False):
    conn = verbindung()
    try:
        return auswertungen.cashflow_monatlich(conn, _parse_datum(von), _parse_datum(bis),
                                                konto_ids=_id_menge(konten, konto_id),
                                                kategorie_ids=_id_menge(kategorien, kategorie_id),
                                                inflation=inflation)
    finally:
        conn.close()


@app.get("/api/auswertungen/kategorien")
def api_auswertungen_kategorien(von: str, bis: str, konto_id: Optional[int] = None,
                                 kategorie_id: Optional[int] = None, konten: Optional[str] = None,
                                 kategorien: Optional[str] = None, inflation: bool = False):
    """Für das Diagramm 'Kategorien': je Hauptkategorie kumulierte Summe
    über den gewählten Zeitraum, getrennt nach Einnahme/Ausgabe."""
    conn = verbindung()
    try:
        return auswertungen.kategorien_zeitraum(conn, _parse_datum(von), _parse_datum(bis),
                                                 konto_ids=_id_menge(konten, konto_id),
                                                 kategorie_ids=_id_menge(kategorien, kategorie_id),
                                                 inflation=inflation)
    finally:
        conn.close()


# ─── Admin ──────────────────────────────────────────────────────────

@app.get("/api/admin/einstellungen")
def api_einstellungen():
    conn = verbindung()
    try:
        rows = conn.execute("SELECT key, value FROM einstellungen").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


@app.put("/api/admin/einstellungen/{key}")
def api_einstellung_setzen(key: str, value: str):
    conn = verbindung()
    try:
        conn.execute("UPDATE einstellungen SET value = ? WHERE key = ?", (value, key))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/admin/backup")
def api_manuelles_backup():
    conn = verbindung()
    try:
        dateiname = backup.backup_erstellen(conn, "manuell")
        return {"dateiname": dateiname}
    finally:
        conn.close()


@app.get("/api/admin/backups")
def api_backups_liste():
    conn = verbindung()
    try:
        rows = conn.execute("SELECT * FROM backups_log ORDER BY erstellt_am DESC, id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── Daten zurücksetzen (seit v1.8) ──────────────────────────────────

class ZuruecksetzenIn(BaseModel):
    arten: list[str] = []
    konten_leeren_ids: list[int] = []
    konten_loeschen_ids: list[int] = []
    ziel_konto_id: Optional[int] = None
    ist_bis: Optional[Datum] = None
    token: Optional[str] = None
    phrase: Optional[str] = None


@app.get("/api/admin/zuruecksetzen/uebersicht")
def api_zuruecksetzen_uebersicht():
    conn = verbindung()
    try:
        return zuruecksetzen.uebersicht(conn)
    finally:
        conn.close()


@app.post("/api/admin/zuruecksetzen/vorschau")
def api_zuruecksetzen_vorschau(payload: ZuruecksetzenIn):
    """Zählt, was gelöscht würde. Ist alles gültig (kein blockierender Punkt,
    ggf. Zielkonto gewählt), kommt zusätzlich die zufällige Bestätigungs-
    phrase samt Token zurück - verändert wird hier noch nichts."""
    conn = verbindung()
    try:
        norm = zuruecksetzen.normalisieren(conn, payload.model_dump())
        info = zuruecksetzen.vorschau(conn, norm)
        info["token"], info["phrase"] = (
            zuruecksetzen.phrase_ausstellen(norm) if info["bereit"] else (None, None))
        return info
    except zuruecksetzen.ZuruecksetzenFehler as e:
        raise HTTPException(422, str(e))
    finally:
        conn.close()


@app.post("/api/admin/zuruecksetzen/ausfuehren")
def api_zuruecksetzen_ausfuehren(payload: ZuruecksetzenIn):
    """Prüft die Phrase, legt ein Backup "vor Löschung von ..." an und löscht
    dann in einer Transaktion. Schlägt das Backup fehl, wird nichts gelöscht."""
    conn = verbindung()
    try:
        norm = zuruecksetzen.normalisieren(conn, payload.model_dump())
        info = zuruecksetzen.vorschau(conn, norm)
        if not info["bereit"]:
            raise zuruecksetzen.ZuruecksetzenFehler(
                " ".join(info["blockiert"]) or "Es ist noch ein Zielkonto zu wählen.")
        zuruecksetzen.phrase_pruefen(payload.token, payload.phrase, norm)
        try:
            dateiname = backup.backup_erstellen(conn, "manuell", beschreibung=info["backup_beschreibung"])
        except OSError as e:
            raise HTTPException(500, f"Backup fehlgeschlagen, es wurde nichts gelöscht: {e}")
        ergebnis = zuruecksetzen.ausfuehren(conn, norm)
        ergebnis["backup"] = dateiname
        return ergebnis
    except zuruecksetzen.ZuruecksetzenFehler as e:
        raise HTTPException(422, str(e))
    finally:
        conn.close()


# ─── Datenbank wiederherstellen (seit v2.4) ──────────────────────────

class WiederherstellenBackupIn(BaseModel):
    dateiname: str


class WiederherstellenIn(BaseModel):
    quelle: str
    token: Optional[str] = None
    phrase: Optional[str] = None


@app.post("/api/admin/wiederherstellen/hochladen")
def api_wiederherstellen_hochladen(datei: UploadFile):
    """Schritt 1 für eine hochgeladene Datei: prüfen, Kennzahlen, Phrase."""
    try:
        return wiederherstellen.upload_vorbereiten(datei.file, datei.filename or "")
    except wiederherstellen.WiederherstellenFehler as e:
        raise HTTPException(422, str(e))


@app.post("/api/admin/wiederherstellen/backup")
def api_wiederherstellen_backup(payload: WiederherstellenBackupIn):
    """Schritt 1 für ein Backup aus der Backup-Liste."""
    conn = verbindung()
    try:
        return wiederherstellen.backup_vorbereiten(conn, payload.dateiname)
    except wiederherstellen.WiederherstellenFehler as e:
        raise HTTPException(422, str(e))
    finally:
        conn.close()


@app.post("/api/admin/wiederherstellen/ausfuehren")
def api_wiederherstellen_ausfuehren(payload: WiederherstellenIn):
    """Schritt 2: Phrase prüfen, Backup vorher, einspielen, Programmstart
    wie beim Hochfahren. Das Ergebnis ersetzt den Start-Status."""
    global STARTUP_ERGEBNIS
    try:
        ergebnis = wiederherstellen.ausfuehren(payload.quelle, payload.token, payload.phrase, startup.ausfuehren)
    except (wiederherstellen.WiederherstellenFehler, zuruecksetzen.ZuruecksetzenFehler) as e:
        raise HTTPException(422, str(e))
    STARTUP_ERGEBNIS = ergebnis["start"]
    return ergebnis


@app.get("/api/admin/datenbank-herunterladen")
def api_datenbank_herunterladen():
    """
    Lädt die aktuelle finanzdaten.db direkt herunter. Existiert, weil
    /data (der eigentliche Speicherort) über Samba nicht erreichbar ist -
    ohne diesen Endpunkt bliebe nur der Umweg über ein HA-Backup oder ein
    Terminal-Add-on mit Docker-Zugriff.
    """
    if not db_modul.DB_PFAD.exists():
        raise HTTPException(404, "Noch keine Datenbank vorhanden.")
    zeitstempel = zeit.heute().isoformat()
    return FileResponse(
        str(db_modul.DB_PFAD),
        media_type="application/octet-stream",
        filename=f"finanzdaten_{zeitstempel}.db",
    )


def _xlsx_antwort(wb, dateiname: str):
    puffer = io.BytesIO()
    wb.save(puffer)
    puffer.seek(0)
    return StreamingResponse(
        puffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={dateiname}"},
    )


@app.get("/api/admin/import-vorlage")
def api_import_vorlage():
    """Leere Vorlage (seit v2.0 im Roundtrip-Format: ein Tab je Bereich,
    Spalten id/aktion, ohne Daten)."""
    from . import roundtrip
    conn = verbindung()
    try:
        return _xlsx_antwort(roundtrip.export_workbook(conn, leer=True), "finanzverwaltung_vorlage.xlsx")
    finally:
        conn.close()


@app.get("/api/admin/export")
def api_export(von: Optional[str] = None, bis: Optional[str] = None):
    """XLSX-Roundtrip (seit v2.0): aktueller Datenbestand aller Bereiche,
    Buchungen optional im Zeitraum von/bis."""
    from . import roundtrip
    von_iso = _parse_datum(von).isoformat() if von else None
    bis_iso = _parse_datum(bis).isoformat() if bis else None
    conn = verbindung()
    try:
        name = f"finanzverwaltung_export_{zeit.heute().isoformat()}.xlsx"
        return _xlsx_antwort(roundtrip.export_workbook(conn, von_iso, bis_iso), name)
    finally:
        conn.close()


@app.post("/api/admin/import/vorschau")
async def api_import_vorschau(datei: UploadFile, art: Optional[str] = Form(None)):
    """Schritt 1 des Imports (seit v2.0): prüft die Datei vollständig (inkl.
    aller Folgeprüfungen) ohne etwas zu speichern und liefert je Tab neu/
    geändert/gelöscht/unverändert/Fehler. Ohne Fehler gibt es ein Token für
    die Übernahme."""
    from . import roundtrip
    rohbytes = await datei.read()
    conn = verbindung()
    try:
        return roundtrip.vorschau(conn, datei.filename or "", rohbytes, art)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        conn.close()


class ImportAusfuehrenIn(BaseModel):
    token: str


@app.post("/api/admin/import/ausfuehren")
def api_import_ausfuehren(payload: ImportAusfuehrenIn):
    """Schritt 2: Backup, dann Übernahme in einer Transaktion (alles oder nichts)."""
    from . import roundtrip
    conn = verbindung()
    try:
        return roundtrip.ausfuehren(conn, payload.token)
    finally:
        conn.close()


@app.post("/api/admin/feiertage/aktualisieren")
def api_feiertage_aktualisieren():
    """Berechnet die Feiertage komplett neu wie beim Start (rein lokal)."""
    conn = verbindung()
    try:
        alle = startup.feiertage_neu_berechnen(conn, zeit.heute())
        return {"anzahl": len(alle)}
    finally:
        conn.close()


# ─── Suche ──────────────────────────────────────────────────────────

@app.get("/api/buchungen/suche")
def api_buchungen_suche(text: Optional[str] = None, betrag_von: Optional[float] = None,
                         betrag_bis: Optional[float] = None, von: Optional[str] = None,
                         bis: Optional[str] = None, konto_id: Optional[int] = None,
                         kategorie_id_filter: Optional[int] = None,
                         inkl_unterkategorien: bool = True, typ: Optional[str] = None,
                         person_id: Optional[int] = None):
    conn = verbindung()
    try:
        return buchungen.buchungen_suchen(
            conn, text=text, betrag_von=betrag_von, betrag_bis=betrag_bis,
            von=_parse_datum(von), bis=_parse_datum(bis), konto_id=konto_id,
            kategorie_id=kategorie_id_filter, inkl_unterkategorien=inkl_unterkategorien, typ=typ,
            person_id=person_id,
        )
    finally:
        conn.close()


# ─── Vorzeichen-Korrektur ───────────────────────────────────────────

@app.get("/api/vorzeichen/konflikte")
def api_vorzeichen_konflikte():
    """Buchungen/Vorlagen, deren Vorzeichen nicht zum Kategorie-Typ passt."""
    conn = verbindung()
    try:
        return {"buchungen": db_modul.vorzeichen_konflikte(conn),
                "vorlagen": db_modul.vorlagen_vorzeichen_konflikte(conn)}
    finally:
        conn.close()


class KorrekturIn(BaseModel):
    buchung_ids: list[int] = []
    vorlage_ids: list[int] = []


@app.post("/api/vorzeichen/korrigieren")
def api_vorzeichen_korrigieren(payload: KorrekturIn):
    conn = verbindung()
    try:
        return {
            "buchungen_korrigiert": buchungen.vorzeichen_korrigieren(conn, payload.buchung_ids),
            "vorlagen_korrigiert": buchungen.vorlagen_vorzeichen_korrigieren(conn, payload.vorlage_ids),
        }
    finally:
        conn.close()


# ─── Budgets ────────────────────────────────────────────────────────

class BudgetIn(BaseModel):
    name: str
    typ: str = "ausgabe"
    kategorie_id: Optional[int] = None
    inkl_unterkategorien: bool = True
    konto_id: Optional[int] = None
    zielbetrag: Optional[float] = None
    zieldatum: Optional[Datum] = None
    betrag: float
    zeitraum: str = "monatlich"
    intervall_wert: Optional[int] = None
    intervall_einheit: Optional[str] = None
    startdatum: Datum
    enddatum: Optional[Datum] = None
    uebertrag: bool = False
    uebertrag_modus: Optional[str] = None
    uebertrag_deckel: Optional[float] = None
    inflationsflag: bool = False
    warnungen: Optional[list[dict]] = None
    person_id: Optional[int] = None


def _einstellung_int(conn, key: str, standard: int) -> int:
    row = conn.execute("SELECT value FROM einstellungen WHERE key = ?", (key,)).fetchone()
    try:
        return int(float(row["value"])) if row else standard
    except (TypeError, ValueError):
        return standard


@app.get("/api/budgets")
def api_budgets_liste(nur_aktive: bool = True, person_id: Optional[int] = None, inflation: bool = False):
    conn = verbindung()
    try:
        bedingungen = []
        parameter: list = []
        if nur_aktive:
            bedingungen.append("aktiv = 1")
        if person_id is not None:
            bedingungen.append("person_id = ?")
            parameter.append(person_id)
        sql = "SELECT * FROM budgets" + (" WHERE " + " AND ".join(bedingungen) if bedingungen else "")
        min_perioden = _einstellung_int(conn, "prognose_min_perioden", 3)
        return [budgets_modul.status(conn, b, min_perioden=min_perioden, inflation=inflation)
                for b in conn.execute(sql + " ORDER BY name", parameter).fetchall()]
    finally:
        conn.close()


@app.get("/api/budgets/{budget_id}")
def api_budget_detail(budget_id: int, inflation: bool = False):
    conn = verbindung()
    try:
        row = conn.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Budget nicht gefunden.")
        return budgets_modul.status(conn, row,
                                    min_perioden=_einstellung_int(conn, "prognose_min_perioden", 3),
                                    inflation=inflation)
    finally:
        conn.close()


@app.get("/api/budgets/details/verlauf")
def api_budget_details_verlauf(budget_id: Optional[int] = None, von: Optional[str] = None, bis: Optional[str] = None,
                               inflation: bool = False):
    """
    Kalendermonatsbasierter Verlauf für das Budgets-Details-Tab (seit
    v1.6.4). Ohne budget_id: Summe über alle aktiven Ausgabe-/
    Einnahme-Budgets (Sparziele ausgenommen) - Dropdown-Auswahl 'Alle'.
    von/bis als 'YYYY-MM'; Standard ist der 25-Monats-Horizont
    (letzte 12, aktueller und kommende 12 Monate).
    """
    conn = verbindung()
    try:
        heute = zeit.heute()
        heute_monat = date(heute.year, heute.month, 1)
        von_monat = date.fromisoformat(von + "-01") if von else heute_monat - relativedelta(months=12)
        bis_monat = date.fromisoformat(bis + "-01") if bis else heute_monat + relativedelta(months=12)
        if budget_id is not None:
            row = conn.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Budget nicht gefunden.")
            ids = budgets_modul.kategorie_ids(conn, row["kategorie_id"], row["inkl_unterkategorien"]) \
                if row["kategorie_id"] else []
        else:
            ids: list = []
            for b in conn.execute("SELECT * FROM budgets WHERE aktiv = 1 AND typ != 'sparziel'").fetchall():
                if b["kategorie_id"]:
                    ids += budgets_modul.kategorie_ids(conn, b["kategorie_id"], b["inkl_unterkategorien"])
        return budgets_modul.verlauf_je_monat(conn, ids, von_monat, bis_monat, heute, inflation=inflation)
    finally:
        conn.close()


@app.get("/api/budgets/{budget_id}/buchungen")
def api_budget_buchungen(budget_id: int, von: Optional[str] = None, bis: Optional[str] = None):
    """Plan-/Ist-Buchungen der Budget-Kategorie(n) im gewählten Zeitraum - für die Liste unter dem Details-Diagramm."""
    conn = verbindung()
    try:
        row = conn.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Budget nicht gefunden.")
        ids = budgets_modul.kategorie_ids(conn, row["kategorie_id"], row["inkl_unterkategorien"]) \
            if row["kategorie_id"] else []
        if not ids:
            return []
        platzhalter = ",".join("?" * len(ids))
        bedingungen = [f"b.kategorie_id IN ({platzhalter})", "b.typ IN ('Ist','Plan')"]
        params: list = [*ids]
        if von:
            bedingungen.append("b.datum >= ?")
            params.append(von + "-01")
        if bis:
            bis_ende = date.fromisoformat(bis + "-01") + relativedelta(months=1) - relativedelta(days=1)
            bedingungen.append("b.datum <= ?")
            params.append(bis_ende.isoformat())
        rows = conn.execute(f"""
            SELECT b.id, b.datum, b.typ, b.betrag, b.beschreibung, k.name AS kategorie
            FROM buchungen b JOIN kategorien k ON k.id = b.kategorie_id
            WHERE {' AND '.join(bedingungen)}
            ORDER BY b.datum DESC LIMIT 500
        """, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _budget_params(payload: BudgetIn):
    import json as _json
    warnungen = _json.dumps(payload.warnungen) if payload.warnungen else budgets_modul.STANDARD_WARNUNGEN
    return (payload.name, payload.typ, payload.kategorie_id, int(payload.inkl_unterkategorien),
            payload.konto_id, payload.zielbetrag, payload.zieldatum, abs(payload.betrag),
            payload.zeitraum, payload.intervall_wert, payload.intervall_einheit,
            payload.startdatum, payload.enddatum, int(payload.uebertrag),
            payload.uebertrag_modus if payload.uebertrag else None,
            payload.uebertrag_deckel if payload.uebertrag else None,
            int(payload.inflationsflag), warnungen, payload.person_id)


def _budget_anlegen(conn, payload: BudgetIn) -> int:
    cur = conn.execute(
        """INSERT INTO budgets
           (name, typ, kategorie_id, inkl_unterkategorien, konto_id, zielbetrag, zieldatum,
            betrag, zeitraum, intervall_wert, intervall_einheit, startdatum, enddatum,
            uebertrag, uebertrag_modus, uebertrag_deckel, inflationsflag, warnungen, person_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        _budget_params(payload),
    )
    conn.commit()
    return cur.lastrowid


@app.post("/api/budgets")
def api_budget_anlegen(payload: BudgetIn):
    conn = verbindung()
    try:
        return {"id": _budget_anlegen(conn, payload)}
    finally:
        conn.close()


def _budget_aendern(conn, budget_id: int, payload: BudgetIn) -> None:
    # Seit v2.0: Trägerkonto (bzw. Typ) eines Sparziels nur änderbar, solange
    # keine Übertragung oder Vorlage zugeordnet ist - sonst passten die
    # bisherigen Zuordnungen nicht mehr zur Sparziel-Regel.
    alt = conn.execute("SELECT typ, konto_id FROM budgets WHERE id = ?", (budget_id,)).fetchone()
    if alt and alt["typ"] == "sparziel" and (payload.typ != "sparziel" or payload.konto_id != alt["konto_id"]):
        n_b = conn.execute("SELECT COUNT(*) FROM buchungen WHERE sparziel_id = ?", (budget_id,)).fetchone()[0]
        n_v = conn.execute("SELECT COUNT(*) FROM wiederkehrende_buchungen WHERE sparziel_id = ?",
                           (budget_id,)).fetchone()[0]
        if n_b or n_v:
            raise HTTPException(422, f"Trägerkonto bzw. Typ des Sparziels lassen sich nicht ändern: Es sind noch "
                                     f"{n_b} Übertragung(en) und {n_v} Vorlage(n) zugeordnet. Für einen Kontowechsel "
                                     "den Stand per Entnahme und Einzahlung umbuchen.")
    conn.execute(
        """UPDATE budgets SET
           name = ?, typ = ?, kategorie_id = ?, inkl_unterkategorien = ?, konto_id = ?,
           zielbetrag = ?, zieldatum = ?, betrag = ?, zeitraum = ?, intervall_wert = ?,
           intervall_einheit = ?, startdatum = ?, enddatum = ?, uebertrag = ?,
           uebertrag_modus = ?, uebertrag_deckel = ?, inflationsflag = ?, warnungen = ?,
           person_id = ?, aktualisiert_am = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (*_budget_params(payload), budget_id),
    )
    conn.commit()


@app.put("/api/budgets/{budget_id}")
def api_budget_bearbeiten(budget_id: int, payload: BudgetIn):
    conn = verbindung()
    try:
        _budget_aendern(conn, budget_id, payload)
        return {"ok": True}
    finally:
        conn.close()


def _budget_loeschen(conn, budget_id: int) -> None:
    conn.execute("UPDATE buchungen SET sparziel_id = NULL WHERE sparziel_id = ?", (budget_id,))
    conn.execute("UPDATE wiederkehrende_buchungen SET sparziel_id = NULL WHERE sparziel_id = ?", (budget_id,))
    conn.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
    conn.commit()


@app.delete("/api/budgets/{budget_id}")
def api_budget_loeschen(budget_id: int):
    conn = verbindung()
    try:
        _budget_loeschen(conn, budget_id)
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/konten/{konto_id}/aufteilung")
def api_konto_aufteilung(konto_id: int):
    """Gesplittete Kontodarstellung: Kontostand = Sparziele + Rest."""
    conn = verbindung()
    try:
        return budgets_modul.konto_aufteilung(conn, konto_id)
    finally:
        conn.close()


@app.get("/api/sparziele/konflikte")
def api_sparziel_konflikte():
    """Sparziel-Zuordnungen, die der Regel seit v2.0 widersprechen."""
    conn = verbindung()
    try:
        return db_modul.sparziel_konflikte(conn)
    finally:
        conn.close()


class SparzielLoesenIn(BaseModel):
    buchung_ids: list[int] = []
    vorlage_ids: list[int] = []


@app.post("/api/sparziele/konflikte/loesen")
def api_sparziel_konflikte_loesen(payload: SparzielLoesenIn):
    conn = verbindung()
    try:
        return {"geloest": db_modul.sparziel_zuordnung_loesen(conn, payload.buchung_ids, payload.vorlage_ids)}
    finally:
        conn.close()


@app.get("/api/sparziele")
def api_sparziele():
    conn = verbindung()
    try:
        rows = conn.execute("SELECT id, name, konto_id FROM budgets WHERE typ = 'sparziel' AND aktiv = 1").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── Buchung bearbeiten ─────────────────────────────────────────────

@app.put("/api/buchungen/{buchung_id}")
def api_buchung_bearbeiten(buchung_id: int, payload: BuchungIn):
    conn = verbindung()
    try:
        if payload.kategorie_id is None and payload.typ != "Uebertragung":
            raise HTTPException(400, "Kategorie fehlt.")
        fehler = buchungen.sparziel_pruefen(conn, payload.typ, payload.konto_id, payload.zielkonto_id,
                                            payload.sparziel_id)
        if fehler:
            raise HTTPException(422, fehler)
        buchungen.buchung_bearbeiten(
            conn, buchung_id, konto_id=payload.konto_id, datum=_parse_datum(payload.datum),
            betrag=payload.betrag, kategorie_id=payload.kategorie_id or 0, typ=payload.typ,
            beschreibung=payload.beschreibung, zielkonto_id=payload.zielkonto_id,
            sparziel_id=payload.sparziel_id,
        )
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        conn.close()


@app.get("/api/buchungen/{buchung_id}")
def api_buchung_einzeln(buchung_id: int):
    conn = verbindung()
    try:
        row = conn.execute("SELECT * FROM buchungen WHERE id = ?", (buchung_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Buchung nicht gefunden.")
        return dict(row)
    finally:
        conn.close()


# ─── Automatische Kategorisierung ───────────────────────────────────

class RegelIn(BaseModel):
    muster: str
    kategorie_id: int
    prioritaet: int = 100


@app.get("/api/regeln")
def api_regeln():
    conn = verbindung()
    try:
        return [dict(r) for r in buchungen.regeln_liste(conn)]
    finally:
        conn.close()


@app.post("/api/regeln")
def api_regel_anlegen(payload: RegelIn):
    conn = verbindung()
    try:
        return {"id": buchungen.regel_anlegen(conn, payload.muster, payload.kategorie_id, payload.prioritaet)}
    finally:
        conn.close()


@app.delete("/api/regeln/{regel_id}")
def api_regel_loeschen(regel_id: int):
    conn = verbindung()
    try:
        buchungen.regel_loeschen(conn, regel_id)
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/regeln/vorschlag")
def api_regel_vorschlag(beschreibung: str):
    conn = verbindung()
    try:
        return {"kategorie_id": buchungen.kategorie_vorschlagen(conn, beschreibung)}
    finally:
        conn.close()


# ─── Siri-Favoriten ─────────────────────────────────────────────────

@app.get("/api/siri/favoriten")
def api_siri_favoriten():
    conn = verbindung()
    try:
        return [dict(r) for r in buchungen.siri_favoriten(conn)]
    finally:
        conn.close()


@app.put("/api/siri/favoriten/{kategorie_id}")
def api_siri_favorit_setzen(kategorie_id: int, aktiv: bool):
    conn = verbindung()
    try:
        buchungen.siri_favorit_setzen(conn, kategorie_id, aktiv)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        conn.close()


class SiriBuchungIn(BaseModel):
    """Vereinfachte Schnittstelle für Siri Shortcuts: Konto und Kategorie
    dürfen per Name statt ID übergeben werden, damit der Shortcut ohne
    ID-Verwaltung auskommt."""
    betrag: float
    kategorie: Optional[str] = None
    konto: Optional[str] = None
    beschreibung: Optional[str] = None
    datum: Optional[Datum] = None


def _siri_eindeutig(eintraege, suchtext: str, art: str):
    """Zweistufige Auflösung ohne stillen Fallback (seit v1.8 verschärft):
    exakter Name (ohne Groß-/Kleinschreibung), sonst ein EINDEUTIGER
    Teiltreffer. Mehrere Treffer oder keiner -> klare Fehlermeldung."""
    such = suchtext.strip().lower()
    for stufe in (lambda n: n == such, lambda n: such in n):
        treffer = [e for e in eintraege if stufe(e["name"].lower())]
        if len(treffer) == 1:
            return treffer[0]
        if len(treffer) > 1:
            namen = ", ".join(sorted({
                f"{e['eltern']} › {e['name']}" if "eltern" in e.keys() and e["eltern"] else e["name"]
                for e in treffer}))
            raise HTTPException(400, f"{art} „{suchtext}“ ist mehrdeutig: {namen}.")
    raise HTTPException(400, f"{art} „{suchtext}“ nicht gefunden.")


@app.post("/api/siri/buchung")
def api_siri_buchung(payload: SiriBuchungIn):
    conn = verbindung()
    try:
        konten = buchungen.konten_liste(conn)
        if not konten:
            raise HTTPException(400, "Es ist noch kein Konto angelegt.")
        if not payload.konto:
            raise HTTPException(400, "Kein Konto angegeben - bitte im Kurzbefehl ein Konto mitschicken.")
        konto = _siri_eindeutig(konten, payload.konto, "Konto")

        if payload.kategorie:
            # Angegebene Kategorie muss eindeutig erkannt werden - kein
            # stiller Rückgriff auf die Kategorisierungsregeln (seit v1.8).
            alle = conn.execute("""SELECT k.id, k.name, e.name AS eltern FROM kategorien k
                                   LEFT JOIN kategorien e ON e.id = k.parent_id""").fetchall()
            kategorie_id = _siri_eindeutig(alle, payload.kategorie, "Kategorie")["id"]
        else:
            kategorie_id = buchungen.kategorie_vorschlagen(conn, payload.beschreibung or "")
            if kategorie_id is None:
                raise HTTPException(400, "Keine Kategorie angegeben und keine Kategorisierungsregel passt.")

        datum = _parse_datum(payload.datum) or zeit.heute()
        buchung_id = buchungen.buchung_anlegen(
            conn, konto_id=konto["id"], datum=datum, betrag=payload.betrag,
            kategorie_id=kategorie_id, typ="Ist", beschreibung=payload.beschreibung,
        )
        kat_name = conn.execute("SELECT name FROM kategorien WHERE id = ?", (kategorie_id,)).fetchone()["name"]
        betrag_gebucht = conn.execute("SELECT betrag FROM buchungen WHERE id = ?", (buchung_id,)).fetchone()["betrag"]
        return {
            "id": buchung_id,
            "meldung": f"{abs(betrag_gebucht):.2f} Euro als {kat_name} auf {konto['name']} gebucht.",
            "konto": konto["name"], "kategorie": kat_name, "betrag": betrag_gebucht,
        }
    finally:
        conn.close()


# ─── Jahresübersicht ────────────────────────────────────────────────

@app.get("/api/auswertungen/jahresuebersicht")
def api_jahresuebersicht(jahr: Optional[int] = None, modus: str = "rollierend",
                          konto_id: Optional[int] = None, kategorie_id: Optional[int] = None,
                          konten: Optional[str] = None, kategorien: Optional[str] = None,
                          person_id: Optional[int] = None, inflation: bool = False):
    """
    modus='kalenderjahr': klassisches Kalenderjahr (Pflicht: 'jahr').
    konten/kategorien: Mehrfachfilter seit v2.3 (siehe _id_menge).
    modus='rollierend' (Standard seit v1.6.3): die letzten 12 Monate bis
    einschließlich des aktuellen Monats, unabhängig vom Kalenderjahr.
    """
    conn = verbindung()
    try:
        if modus == "kalenderjahr":
            if jahr is None:
                raise HTTPException(400, "Für den Kalenderjahr-Modus ist 'jahr' erforderlich.")
            von = date(jahr, 1, 1)
            bis = date(jahr, 12, 31)
        else:
            heute_monat = date(zeit.heute().year, zeit.heute().month, 1)
            von = heute_monat - relativedelta(months=11)
            bis = heute_monat + relativedelta(months=1) - relativedelta(days=1)
        konto_ids, kategorie_ids = _id_menge(konten, konto_id), _id_menge(kategorien, kategorie_id)
        daten = auswertungen.jahresuebersicht(conn, von, bis, konto_ids=konto_ids, kategorie_ids=kategorie_ids,
                                               person_id=person_id, inflation=inflation)
        daten["kategorien"] = auswertungen.jahresuebersicht_kategorien(
            conn, von, bis, konto_ids=konto_ids, kategorie_ids=kategorie_ids, person_id=person_id)
        daten["modus"] = modus
        return daten
    finally:
        conn.close()


# ─── Schnellbuchung (eigene, mobiloptimierte Seite) ─────────────────

@app.get("/schnellbuchung")
def schnellbuchung():
    return FileResponse(str(_STATIC_VERZEICHNIS / "schnellbuchung.html"))



# ─── Altersvorsorge ─────────────────────────────────────────────────

class AltersvorsorgeIn(BaseModel):
    bezeichnung: str
    anbieter: Optional[str] = None
    zahlungskonto_id: int
    person_id: Optional[int] = None
    stand_datum: Datum
    # hat_einzahlung=False bildet arbeitgeber-/gehaltsfinanzierte Modelle
    # ohne eigene Einzahlung ab (v1.5) - dann sind die beitrag_*-Felder
    # nicht Pflicht und es entstehen ausschließlich Plan-/Ist-Buchungen
    # für die Auszahlungsphase (siehe app/core/altersvorsorge.py).
    hat_einzahlung: bool = True
    beitrag_kategorie_id: Optional[int] = None
    beitrag_betrag: Optional[float] = None
    beitrag_intervall: str = "monatlich"
    beitrag_tag_des_monats: int = 1
    beitrag_monat: Optional[int] = None
    beitrag_startdatum: Optional[Datum] = None
    beitrag_dynamik_aktiv: bool = False
    beitrag_dynamik_rhythmus_jahre: Optional[int] = None
    beitrag_dynamik_prozent: Optional[float] = None
    beitrag_dynamik_startjahr: Optional[int] = None
    rentenbeginn: Datum
    ende_datum: Optional[Datum] = None
    auszahlungsart: str = "rente"
    auszahlung_kategorie_id: int
    rente_garantiert_betrag: Optional[float] = None
    rente_voraussichtlich_betrag: Optional[float] = None
    einmalzahlung_garantiert_betrag: Optional[float] = None
    einmalzahlung_voraussichtlich_betrag: Optional[float] = None
    rueckkaufswert: Optional[float] = None
    auszahlung_bei_tod: Optional[float] = None
    auszahlung_inflationsflag: bool = False


_AV_SPALTEN = [
    "bezeichnung", "anbieter", "zahlungskonto_id", "person_id", "stand_datum", "hat_einzahlung",
    "beitrag_kategorie_id", "beitrag_betrag", "beitrag_intervall", "beitrag_tag_des_monats",
    "beitrag_monat", "beitrag_startdatum", "beitrag_dynamik_aktiv", "beitrag_dynamik_rhythmus_jahre",
    "beitrag_dynamik_prozent", "beitrag_dynamik_startjahr", "rentenbeginn", "ende_datum",
    "auszahlungsart", "auszahlung_kategorie_id", "rente_garantiert_betrag", "rente_voraussichtlich_betrag",
    "einmalzahlung_garantiert_betrag", "einmalzahlung_voraussichtlich_betrag",
    "rueckkaufswert", "auszahlung_bei_tod", "auszahlung_inflationsflag",
]


def _av_pruefen(payload: AltersvorsorgeIn) -> None:
    """Beitrags-Pflichtfelder sind nur bei aktivierter Einzahlung Pflicht
    (v1.5) - ohne Einzahlung entstehen ausschließlich Auszahlungs-Buchungen."""
    if payload.hat_einzahlung and (
        payload.beitrag_kategorie_id is None or payload.beitrag_betrag is None
        or payload.beitrag_startdatum is None
    ):
        raise HTTPException(
            400, "Bei aktivierter Einzahlung sind Beitrags-Kategorie, -Betrag und -Startdatum Pflicht.")


def _av_werte(payload: AltersvorsorgeIn) -> tuple:
    return (
        payload.bezeichnung, payload.anbieter, payload.zahlungskonto_id, payload.person_id,
        payload.stand_datum, int(payload.hat_einzahlung),
        payload.beitrag_kategorie_id,
        abs(payload.beitrag_betrag) if payload.beitrag_betrag is not None else None,
        payload.beitrag_intervall,
        payload.beitrag_tag_des_monats, payload.beitrag_monat, payload.beitrag_startdatum,
        int(payload.beitrag_dynamik_aktiv), payload.beitrag_dynamik_rhythmus_jahre,
        payload.beitrag_dynamik_prozent, payload.beitrag_dynamik_startjahr,
        payload.rentenbeginn, payload.ende_datum, payload.auszahlungsart, payload.auszahlung_kategorie_id,
        payload.rente_garantiert_betrag, payload.rente_voraussichtlich_betrag,
        payload.einmalzahlung_garantiert_betrag, payload.einmalzahlung_voraussichtlich_betrag,
        payload.rueckkaufswert, payload.auszahlung_bei_tod, int(payload.auszahlung_inflationsflag),
    )


def _feiertage_laden(conn) -> dict:
    return {date.fromisoformat(r["datum"]): r["name"]
            for r in conn.execute("SELECT datum, name FROM feiertage").fetchall()}


@app.get("/api/altersvorsorge")
def api_altersvorsorge_liste(nur_aktive: bool = True, person_id: Optional[int] = None):
    conn = verbindung()
    try:
        sql = """SELECT a.*, k.name AS konto_name, kb.name AS beitrag_kategorie_name,
                         ka.name AS auszahlung_kategorie_name
                  FROM altersvorsorge a
                  LEFT JOIN konten k ON k.id = a.zahlungskonto_id
                  LEFT JOIN kategorien kb ON kb.id = a.beitrag_kategorie_id
                  LEFT JOIN kategorien ka ON ka.id = a.auszahlung_kategorie_id"""
        bedingungen = []
        params: list = []
        if nur_aktive:
            bedingungen.append("a.aktiv = 1")
        if person_id is not None:
            bedingungen.append("a.person_id = ?")
            params.append(person_id)
        if bedingungen:
            sql += " WHERE " + " AND ".join(bedingungen)
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY a.bezeichnung", params).fetchall()]
        for r in rows:
            r["beitrag_verbleibend_monate"] = None
            try:
                heute = zeit.heute()
                renten = date.fromisoformat(r["rentenbeginn"])
                if renten > heute:
                    r["beitrag_verbleibend_monate"] = (renten.year - heute.year) * 12 + (renten.month - heute.month)
            except Exception:
                pass
        return rows
    finally:
        conn.close()


@app.get("/api/altersvorsorge/{av_id}")
def api_altersvorsorge_einzeln(av_id: int):
    conn = verbindung()
    try:
        row = conn.execute("SELECT * FROM altersvorsorge WHERE id = ?", (av_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Altersvorsorge nicht gefunden.")
        return dict(row)
    finally:
        conn.close()


def _av_anlegen(conn, payload: AltersvorsorgeIn) -> int:
    _av_pruefen(payload)
    platzhalter = ", ".join("?" * len(_AV_SPALTEN))
    cur = conn.execute(
        f"INSERT INTO altersvorsorge ({', '.join(_AV_SPALTEN)}) VALUES ({platzhalter})",
        _av_werte(payload),
    )
    neu_id = cur.lastrowid
    conn.commit()
    altersvorsorge_modul.erzeuge_faellige_ist_buchungen(conn, _feiertage_laden(conn))
    return neu_id


@app.post("/api/altersvorsorge")
def api_altersvorsorge_anlegen(payload: AltersvorsorgeIn):
    conn = verbindung()
    try:
        return {"id": _av_anlegen(conn, payload)}
    finally:
        conn.close()


@app.get("/api/altersvorsorge/{av_id}/phasen-pruefung")
def api_altersvorsorge_phasen_pruefung(av_id: int, rentenbeginn: str):
    """Vorschau für den Bestätigungsdialog (seit v2.0): wie viele automatisch
    erzeugte Buchungen beim neuen Rentenbeginn in der falschen Phase lägen."""
    conn = verbindung()
    try:
        alt = conn.execute("SELECT * FROM altersvorsorge WHERE id = ?", (av_id,)).fetchone()
        if alt is None:
            raise HTTPException(404, "Altersvorsorge nicht gefunden.")
        k = altersvorsorge_modul.phasen_konflikte(conn, alt, _parse_datum(rentenbeginn), _feiertage_laden(conn))
        return {"loeschen": len(k["loeschen"]), "angepasst": len(k["angepasst"])}
    finally:
        conn.close()


def _av_aendern(conn, av_id: int, payload: AltersvorsorgeIn, phasen_bereinigen: bool = False) -> None:
    _av_pruefen(payload)
    alt = conn.execute("SELECT * FROM altersvorsorge WHERE id = ?", (av_id,)).fetchone()
    # Seit v2.0: Buchungen, die nach einem verschobenen Rentenbeginn in der
    # falschen Phase lägen, werden nach Bestätigung (phasen_bereinigen)
    # gelöscht - ermittelt mit dem ALTEN Terminplan, vor dem Update.
    bereinigen = []
    if alt and phasen_bereinigen and payload.rentenbeginn != alt["rentenbeginn"]:
        bereinigen = altersvorsorge_modul.phasen_konflikte(
            conn, alt, date.fromisoformat(payload.rentenbeginn), _feiertage_laden(conn))["loeschen"]
    setzen = ", ".join(f"{s} = ?" for s in _AV_SPALTEN)
    conn.execute(f"UPDATE altersvorsorge SET {setzen} WHERE id = ?", (*_av_werte(payload), av_id))
    altersvorsorge_modul.phasen_bereinigen(conn, bereinigen)
    conn.commit()
    feiertage = _feiertage_laden(conn)
    if alt:
        fenster = []
        if payload.hat_einzahlung and alt["hat_einzahlung"]:
            f = _vorverlegt(alt["beitrag_startdatum"], payload.beitrag_startdatum)
            if f:
                fenster.append(f)
        elif payload.hat_einzahlung and payload.beitrag_startdatum:
            # Einzahlung neu aktiviert: gesamte Beitragsphase ist neu
            fenster.append((date.fromisoformat(payload.beitrag_startdatum), date.max))
        if payload.rentenbeginn and alt["rentenbeginn"] and payload.rentenbeginn != alt["rentenbeginn"]:
            # Phasengrenze verschoben: früher -> Rente im Zwischenraum neu,
            # später -> Beiträge im Zwischenraum neu.
            a, b = sorted([payload.rentenbeginn, alt["rentenbeginn"]])
            fenster.append((date.fromisoformat(a), date.fromisoformat(b)))
            if payload.auszahlungsart == "einmalzahlung":
                # Einmalzahlung zum neuen Termin (seit v2.0): liegt er
                # schon zurück, verhindert sonst die Erzeugungsmarke die
                # Buchung, wenn der Rentenbeginn nach hinten wandert.
                neu = date.fromisoformat(payload.rentenbeginn)
                fenster.append((neu, neu + relativedelta(days=1)))
        for f in fenster:
            altersvorsorge_modul.erzeuge_faellige_ist_buchungen(conn, feiertage, nur_id=av_id, fenster=f)
    altersvorsorge_modul.erzeuge_faellige_ist_buchungen(conn, feiertage)


@app.put("/api/altersvorsorge/{av_id}")
def api_altersvorsorge_bearbeiten(av_id: int, payload: AltersvorsorgeIn, phasen_bereinigen: bool = False):
    conn = verbindung()
    try:
        _av_aendern(conn, av_id, payload, phasen_bereinigen)
        return {"ok": True}
    finally:
        conn.close()


def _av_loeschen(conn, av_id: int, inkl_buchungen: bool = False) -> None:
    if inkl_buchungen:
        conn.execute("DELETE FROM buchungen WHERE ziel_altersvorsorge_id = ?", (av_id,))
    else:
        conn.execute("UPDATE buchungen SET ziel_altersvorsorge_id = NULL WHERE ziel_altersvorsorge_id = ?", (av_id,))
    conn.execute("DELETE FROM altersvorsorge WHERE id = ?", (av_id,))
    conn.commit()


@app.delete("/api/altersvorsorge/{av_id}")
def api_altersvorsorge_loeschen(av_id: int, inkl_buchungen: bool = False):
    conn = verbindung()
    try:
        _av_loeschen(conn, av_id, inkl_buchungen)
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/altersvorsorge/{av_id}/tilgungsplan")
def api_altersvorsorge_verlauf(av_id: int, jahre: int = 30):
    """Monatlicher Beitrags-/Renten-Verlauf für die Detailansicht (Chart + Tabelle)."""
    conn = verbindung()
    try:
        row = conn.execute("SELECT * FROM altersvorsorge WHERE id = ?", (av_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Altersvorsorge nicht gefunden.")
        feiertage = _feiertage_laden(conn)
        heute = zeit.heute()
        bis = heute + relativedelta(years=jahre)
        posten = altersvorsorge_modul.anstehende_termine(conn, feiertage, heute - relativedelta(days=1), bis, av_id)
        # Bereits vergangene echte Buchungen ergänzen, damit die Kurve nicht bei "heute" beginnt
        vergangene = conn.execute(
            "SELECT datum, betrag, beschreibung FROM buchungen WHERE ziel_altersvorsorge_id = ? AND datum < ? ORDER BY datum",
            (av_id, heute.isoformat()),
        ).fetchall()
        alle = [{"datum": v["datum"], "betrag": v["betrag"], "beschreibung": v["beschreibung"]} for v in vergangene] +                [{"datum": p["datum"], "betrag": p["betrag"], "beschreibung": p["beschreibung"]} for p in posten]
        alle.sort(key=lambda x: x["datum"])
        return alle
    finally:
        conn.close()


# ─── Hilfe (seit v2.1) ──────────────────────────────────────────────
# Eine Quelle (app/hilfe/hilfe.md), zwei Ausgaben: Hilfe-Ansicht und PDF.

@app.get("/api/hilfe")
def api_hilfe():
    from .core import hilfe
    return hilfe.fuer_api(hilfe.laden())


@app.get("/api/hilfe/pdf")
def api_hilfe_pdf():
    from fastapi.responses import Response
    from .core import hilfe, hilfe_pdf
    daten = hilfe.laden()
    try:
        pdf = hilfe_pdf.erzeugen_zwischengespeichert()
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    name = f"Finanzverwaltung_Hilfe_{daten['version'] or 'aktuell'}.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/hilfe/bilder/{name}")
def api_hilfe_bild(name: str):
    from .core import hilfe
    pfad = (hilfe.BILDER_VERZEICHNIS / name).resolve()
    if pfad.parent != hilfe.BILDER_VERZEICHNIS.resolve() or not pfad.is_file():
        raise HTTPException(404, "Bild nicht gefunden")
    return FileResponse(str(pfad))


# ─── Frontend ausliefern ────────────────────────────────────────────

_STATIC_VERZEICHNIS = resource_pfad("app/static")
app.mount("/assets", StaticFiles(directory=str(_STATIC_VERZEICHNIS)), name="assets")


@app.get("/")
def index():
    return FileResponse(str(_STATIC_VERZEICHNIS / "index.html"))

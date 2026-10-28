"""
Code-Sperre (seit 3.0, Issue #5).

Wer die Oberfläche öffnet, sagt der Supervisor über die Ingress-Header
X-Remote-User-Id, X-Remote-User-Name, X-Remote-User-Display-Name und (ab
Supervisor 2026.10.5, Commit 3fbb083b) X-Remote-User-Groups. Ein Client kann
diese Header nicht unterschieben, der Supervisor ersetzt sie
(supervisor/api/ingress.py, _init_header). Das gilt nur für Aufrufe über
Ingress. Deshalb lässt sich die Sperre nur einschalten, wenn die
Herkunftsprüfung auf „sperren“ steht.

Adminrecht = Gruppe „system-admin“ im Header (HOMEASSISTANT_GROUP_ID_ADMIN in
supervisor/const.py). Fehlt der Header, gilt der Benutzer nicht als Admin
(Entscheidung 43).

Codes: PIN, Passwort oder Muster auf einem 3×3-Raster (Punkte 1 bis 9 als
„1-5-9-6-3“). Gespeichert wird nur ein Argon2id-Hash von „art:code“.

Sitzungen: Nach dem richtigen Code bekommt der Browser ein zufälliges Token,
das er im Header X-Finanz-Sitzung mitschickt. Es liegt nur im Arbeitsspeicher
des Servers und verfällt nach der eingestellten Untätigkeit.
"""
import hashlib
import hmac
import logging
import os
import secrets
import threading

from . import schutzdatei, tresor, zeit

LOG = logging.getLogger("app.schutz")

ADMIN_GRUPPE = "system-admin"
KOPF_ID = "x-remote-user-id"
KOPF_NAME = "x-remote-user-name"
KOPF_ANZEIGE = "x-remote-user-display-name"
KOPF_GRUPPEN = "x-remote-user-groups"
KOPF_SITZUNG = "x-finanz-sitzung"

ARTEN = ("pin", "passwort", "muster")
MINDEST_UNTERGRENZE = {"pin": 6, "passwort": 8, "muster": 5}   # Entscheidung 40
AUTO_MINUTEN_VORGABE = 5                                      # Entscheidung 42
GRENZE_BEREICH = (5, 20)
SITZUNG_OHNE_AUTO = 12 * 3600

_SITZUNGEN: dict[str, dict] = {}
_VORBEREITET: dict[str, dict] = {}
_SITZUNGEN_SPERRE = threading.Lock()


class SperreFehler(ValueError):
    def __init__(self, text: str, status: int = 422):
        super().__init__(text)
        self.status = status


# ─── Benutzer aus den Headern ────────────────────────────────────────

def benutzer(kopf) -> dict:
    """kopf: Mapping mit kleingeschriebenen Header-Namen."""
    gruppen_text = kopf.get(KOPF_GRUPPEN)
    gruppen = [g.strip() for g in (gruppen_text or "").split(",") if g.strip()]
    return {
        "id": kopf.get(KOPF_ID) or "",
        "name": kopf.get(KOPF_ANZEIGE) or kopf.get(KOPF_NAME) or "",
        "admin": ADMIN_GRUPPE in gruppen,
        "gruppen_bekannt": gruppen_text is not None,
    }


def bekannt_merken(b: dict) -> None:
    """Merkt sich Benutzer, die die Finanzverwaltung geöffnet haben, für die
    Auswahl der Freigabeliste. Schreibt nur bei Neuem."""
    if not b["id"]:
        return
    alt = schutzdatei.laden().get("bekannt", {}).get(b["id"])
    if alt and alt.get("name") == b["name"] and alt.get("admin") == b["admin"]:
        return

    def merken(d):
        d.setdefault("bekannt", {})[b["id"]] = {"name": b["name"], "admin": b["admin"]}
    schutzdatei.aendern(merken)


# ─── Zustand ─────────────────────────────────────────────────────────

def einstellungen() -> dict | None:
    return schutzdatei.laden().get("sperre")


def aktiv() -> bool:
    return bool(einstellungen())


def herkunft_modus() -> str:
    return os.environ.get("FINANZAPP_HERKUNFT_PRUEFEN", "aus")


def freigegeben(benutzer_id: str, s: dict | None = None) -> bool:
    s = s or einstellungen() or {}
    return bool(benutzer_id) and benutzer_id in s.get("benutzer", {})


def code_von(benutzer_id: str, s: dict | None = None) -> dict | None:
    s = s or einstellungen() or {}
    if s.get("modus") == "gemeinsam":
        return s.get("gemeinsamer_code")
    return (s.get("benutzer", {}).get(benutzer_id) or {}).get("code")


def grenze() -> int:
    return int((einstellungen() or {}).get("grenze") or 0)


def fehlversuche(benutzer_id: str) -> dict:
    return schutzdatei.fehlversuche(f"code:{benutzer_id}", grenze())


# ─── Codes ───────────────────────────────────────────────────────────

def mindestlaengen(s: dict | None = None) -> dict:
    s = s or einstellungen() or {}
    eigene = s.get("mindest") or {}
    return {a: max(MINDEST_UNTERGRENZE[a], int(eigene.get(a) or 0)) for a in ARTEN}


def code_pruefen_format(art: str, code: str, mindest: dict) -> str:
    """Prüft und normalisiert einen Code. Liefert den Code, wirft sonst."""
    code = code or ""
    if art == "pin":
        if not code.isdigit() or not code.isascii():
            raise SperreFehler("Eine PIN besteht nur aus Ziffern.")
        if len(code) < mindest["pin"]:
            raise SperreFehler(f"Die PIN braucht mindestens {mindest['pin']} Ziffern.")
        return code
    if art == "passwort":
        if len(code) < mindest["passwort"]:
            raise SperreFehler(f"Das Passwort braucht mindestens {mindest['passwort']} Zeichen.")
        return code
    if art == "muster":
        punkte = [p for p in code.replace(",", "-").split("-") if p]
        if not all(p in "123456789" and len(p) == 1 for p in punkte) or len(set(punkte)) != len(punkte):
            raise SperreFehler("Ein Muster verbindet Punkte von 1 bis 9, jeden höchstens einmal.")
        if len(punkte) < mindest["muster"]:
            raise SperreFehler(f"Das Muster braucht mindestens {mindest['muster']} Punkte.")
        return "-".join(punkte)
    raise SperreFehler("Unbekannte Art des Codes (PIN, Passwort oder Muster).")


def _hasher():
    from argon2 import PasswordHasher
    return PasswordHasher()


def code_hash(art: str, code: str) -> dict:
    return {"art": art, "hash": _hasher().hash(f"{art}:{code}")}


def code_stimmt(gespeichert: dict | None, code: str) -> bool:
    if not gespeichert:
        return False
    from argon2.exceptions import Argon2Error
    art = gespeichert["art"]
    if art == "muster":
        code = "-".join(p for p in (code or "").replace(",", "-").split("-") if p)
    try:
        return _hasher().verify(gespeichert["hash"], f"{art}:{code}")
    except Argon2Error:
        return False


def _wh_hash(roh: bytes, salz: bytes) -> str:
    return hashlib.sha256(salz + roh).hexdigest()


# ─── Sitzungen ───────────────────────────────────────────────────────

def _dauer() -> int:
    minuten = int((einstellungen() or {}).get("auto_minuten") or 0)
    return minuten * 60 if minuten > 0 else SITZUNG_OHNE_AUTO


def sitzung_anlegen(benutzer_id: str) -> str:
    token = secrets.token_urlsafe(24)
    with _SITZUNGEN_SPERRE:
        _SITZUNGEN[token] = {"benutzer": benutzer_id, "letzte": schutzdatei.uhr()}
    return token


def sitzung_gueltig(token: str | None, benutzer_id: str, verlaengern: bool = True) -> bool:
    if not token:
        return False
    with _SITZUNGEN_SPERRE:
        s = _SITZUNGEN.get(token)
        if not s:
            return False
        jetzt = schutzdatei.uhr()
        if s["benutzer"] != benutzer_id or jetzt - s["letzte"] > _dauer():
            _SITZUNGEN.pop(token, None)
            return False
        if verlaengern:
            s["letzte"] = jetzt
        return True


def sitzung_beenden(token: str | None) -> None:
    with _SITZUNGEN_SPERRE:
        _SITZUNGEN.pop(token or "", None)


def sitzungen_beenden(benutzer_id: str | None = None) -> None:
    with _SITZUNGEN_SPERRE:
        for t in [t for t, s in _SITZUNGEN.items() if benutzer_id is None or s["benutzer"] == benutzer_id]:
            del _SITZUNGEN[t]


# ─── Anmelden ────────────────────────────────────────────────────────

def _warte_text(sekunden: int) -> str:
    return tresor._dauer(sekunden)


def anmelden(b: dict, code: str) -> str:
    s = einstellungen()
    if not s:
        raise SperreFehler("Die Sperre ist nicht eingeschaltet.")
    if not freigegeben(b["id"], s):
        raise SperreFehler("Dieser Benutzer ist nicht freigegeben.", 403)
    gespeichert = code_von(b["id"], s)
    if not gespeichert:
        raise SperreFehler("Für diesen Benutzer ist noch kein Code festgelegt.", 409)
    stand = fehlversuche(b["id"])
    if stand["dauerhaft"]:
        raise SperreFehler("Gesperrt nach zu vielen Fehlversuchen. Freigabe durch einen anderen freigegebenen "
                           "Benutzer, mit der Passphrase oder dem Wiederherstellungsschlüssel.", 423)
    if stand["warten"]:
        raise SperreFehler(f"Zu viele Fehlversuche. Bitte {_warte_text(stand['warten'])} warten.", 429)
    if not code_stimmt(gespeichert, code):
        schutzdatei.fehlversuch_zaehlen(f"code:{b['id']}")
        stand = fehlversuche(b["id"])
        LOG.info("Sperre: falscher Code für %s (Fehlversuch %s)", b["name"] or b["id"], stand["anzahl"])
        if stand["dauerhaft"]:
            raise SperreFehler("Falscher Code. Gesperrt bis zur Freigabe.", 423)
        zusatz = f" Nächster Versuch in {_warte_text(stand['warten'])}." if stand["warten"] else ""
        raise SperreFehler("Falscher Code." + zusatz, 401)
    schutzdatei.fehlversuche_loeschen(f"code:{b['id']}")
    return sitzung_anlegen(b["id"])


def erstcode_setzen(b: dict, art: str, code: str, wiederholung: str) -> str:
    s = einstellungen()
    if not s or s.get("modus") != "je_benutzer":
        raise SperreFehler("Hier ist kein eigener Code vorgesehen.")
    if not freigegeben(b["id"], s):
        raise SperreFehler("Dieser Benutzer ist nicht freigegeben.", 403)
    if code_von(b["id"], s):
        raise SperreFehler("Der Code ist bereits festgelegt.", 409)
    code = code_pruefen_format(art, code, mindestlaengen(s))
    if code != code_pruefen_format(art, wiederholung, mindestlaengen(s)):
        raise SperreFehler("Die beiden Eingaben stimmen nicht überein.")
    neu = code_hash(art, code)
    schutzdatei.aendern(lambda d: d["sperre"]["benutzer"][b["id"]].__setitem__("code", neu))
    LOG.info("Sperre: %s hat den eigenen Code festgelegt", b["name"] or b["id"])
    return sitzung_anlegen(b["id"])


def wiederherstellen(b: dict, text: str) -> str:
    """Wiederherstellungsschlüssel der Sperre (Entscheidung 41): hebt die
    Sperre für diesen Benutzer auf und öffnet eine Sitzung."""
    s = einstellungen()
    if not s:
        raise SperreFehler("Die Sperre ist nicht eingeschaltet.")
    if not freigegeben(b["id"], s):
        raise SperreFehler("Dieser Benutzer ist nicht freigegeben.", 403)
    stand = schutzdatei.fehlversuche("sperre_wiederherstellung")
    if stand["warten"]:
        raise SperreFehler(f"Zu viele Fehlversuche. Bitte {_warte_text(stand['warten'])} warten.", 429)
    roh = tresor.wiederherstellungsschluessel_lesen(text)
    wh = s["wiederherstellung"]
    if roh is None or not hmac.compare_digest(_wh_hash(roh, bytes.fromhex(wh["salz"])), wh["hash"]):
        schutzdatei.fehlversuch_zaehlen("sperre_wiederherstellung")
        raise SperreFehler("Der Wiederherstellungsschlüssel der Sperre stimmt nicht.", 401)
    schutzdatei.fehlversuche_loeschen("sperre_wiederherstellung")
    schutzdatei.fehlversuche_loeschen(f"code:{b['id']}")
    LOG.info("Sperre: %s mit dem Wiederherstellungsschlüssel freigegeben", b["name"] or b["id"])
    return sitzung_anlegen(b["id"])


def mit_passphrase_freigeben(b: dict, passphrase: str) -> str:
    """Freigabe mit der Passphrase der Verschlüsselung (Entscheidung 32)."""
    if not freigegeben(b["id"]):
        raise SperreFehler("Dieser Benutzer ist nicht freigegeben.", 403)
    try:
        tresor.passphrase_bestaetigen(passphrase)
    except tresor.TresorFehler as e:
        raise SperreFehler(str(e), 401)
    schutzdatei.fehlversuche_loeschen(f"code:{b['id']}")
    LOG.info("Sperre: %s mit der Passphrase freigegeben", b["name"] or b["id"])
    return sitzung_anlegen(b["id"])


# ─── Verwalten ───────────────────────────────────────────────────────

def _einstellungen_pruefen(e: dict, alt: dict | None = None) -> dict:
    alt = alt or {}
    modus = e.get("modus", alt.get("modus", "je_benutzer"))
    if modus not in ("je_benutzer", "gemeinsam"):
        raise SperreFehler("Modus ist „je_benutzer“ oder „gemeinsam“.")
    g = int(e.get("grenze", alt.get("grenze", 10)) or 0)
    if g and not GRENZE_BEREICH[0] <= g <= GRENZE_BEREICH[1]:
        raise SperreFehler("Sperre bis Freigabe nach 5 bis 20 Fehlversuchen oder ohne Limit (0).")
    auto = int(e.get("auto_minuten", alt.get("auto_minuten", AUTO_MINUTEN_VORGABE)))
    if not 0 <= auto <= 240:
        raise SperreFehler("Automatische Sperre nach 1 bis 240 Minuten oder aus (0).")
    sb = e.get("schnellbuchung", alt.get("schnellbuchung", "nur_erfassen"))
    if sb not in ("nur_erfassen", "mit_code"):
        raise SperreFehler("Schnellbuchung ist „nur_erfassen“ oder „mit_code“.")
    mindest = dict(alt.get("mindest") or MINDEST_UNTERGRENZE)
    for art, wert in (e.get("mindest") or {}).items():
        if art not in ARTEN or int(wert) < MINDEST_UNTERGRENZE[art] or int(wert) > 64:
            raise SperreFehler(f"Mindestlänge für {art}: mindestens {MINDEST_UNTERGRENZE.get(art, '?')}.")
        mindest[art] = int(wert)
    return {"modus": modus, "grenze": g, "auto_minuten": auto,
            "auto_hintergrund": bool(e.get("auto_hintergrund", alt.get("auto_hintergrund", False))),
            "schnellbuchung": sb, "mindest": mindest}


def einschalten_vorbereiten(b: dict, eingabe: dict, art: str, code: str, wiederholung: str) -> dict:
    if aktiv():
        raise SperreFehler("Die Sperre ist bereits eingeschaltet.")
    if herkunft_modus() != "sperren":
        raise SperreFehler("Die Sperre lässt sich nur einschalten, wenn die Add-on-Option "
                           "„herkunft_pruefen“ auf „sperren“ steht.", 409)
    if not b["id"]:
        raise SperreFehler("Kein Home-Assistant-Benutzer erkannt. Bitte über Home Assistant öffnen.", 403)
    if not b["admin"]:
        raise SperreFehler("Nur Administratoren von Home Assistant können die Sperre einschalten.", 403)
    e = _einstellungen_pruefen(eingabe)
    code = code_pruefen_format(art, code, e["mindest"])
    if code != code_pruefen_format(art, wiederholung, e["mindest"]):
        raise SperreFehler("Die beiden Eingaben des Codes stimmen nicht überein.")
    text, roh = tresor.wiederherstellungsschluessel_erzeugen()
    salz = os.urandom(16)
    h = code_hash(art, code)
    block = {**e, "seit": zeit.jetzt().isoformat(timespec="seconds"),
             "gemeinsamer_code": h if e["modus"] == "gemeinsam" else None,
             "benutzer": {b["id"]: {"name": b["name"], "code": h if e["modus"] == "je_benutzer" else None}},
             "wiederherstellung": {"salz": salz.hex(), "hash": _wh_hash(roh, salz)}}
    kennung = secrets.token_urlsafe(16)
    _VORBEREITET.clear()
    _VORBEREITET[kennung] = {"block": block, "roh": roh, "benutzer": b["id"], "bis": schutzdatei.uhr() + 900}
    return {"kennung": kennung, "wiederherstellungsschluessel": text}


def einschalten_ausfuehren(b: dict, kennung: str, getippt: str) -> str:
    v = _VORBEREITET.get(kennung or "")
    if not v or v["bis"] < schutzdatei.uhr() or v["benutzer"] != b["id"]:
        raise SperreFehler("Die Vorbereitung ist abgelaufen. Bitte neu beginnen.")
    if tresor.wiederherstellungsschluessel_lesen(getippt) != v["roh"]:
        raise SperreFehler("Der abgetippte Wiederherstellungsschlüssel stimmt nicht.")
    schutzdatei.aendern(lambda d: d.__setitem__("sperre", v["block"]))
    schutzdatei.alle_fehlversuche_loeschen("code:")
    _VORBEREITET.clear()
    sitzungen_beenden()
    LOG.info("Sperre eingeschaltet von %s (Modus %s)", b["name"] or b["id"], v["block"]["modus"])
    return sitzung_anlegen(b["id"])


def verwalter_pruefen(b: dict, token: str | None) -> None:
    """Ändern dürfen nur freigegebene Benutzer mit Adminrecht und gültiger
    Sitzung (Entscheidung 27). Ohne Sperre genügt das Adminrecht."""
    if not b["admin"]:
        text = ("Nur Administratoren von Home Assistant dürfen den Schutz ändern."
                if b["gruppen_bekannt"] else
                "Das Adminrecht ist nicht erkennbar. Dafür ist Supervisor 2026.10.5 oder neuer nötig.")
        raise SperreFehler(text, 403)
    if aktiv() and not (freigegeben(b["id"]) and sitzung_gueltig(token, b["id"])):
        raise SperreFehler("Nur freigegebene Benutzer mit gültiger Anmeldung dürfen den Schutz ändern.", 403)


def einstellungen_aendern(eingabe: dict) -> dict:
    alt = einstellungen()
    if not alt:
        raise SperreFehler("Die Sperre ist nicht eingeschaltet.")
    neu = _einstellungen_pruefen(eingabe, alt)
    if neu["modus"] != alt["modus"]:
        raise SperreFehler("Der Modus lässt sich nur durch Aus- und Einschalten der Sperre wechseln.")
    schutzdatei.aendern(lambda d: d["sperre"].update(neu))
    LOG.info("Sperre: Einstellungen geändert")
    return neu


def benutzer_freigeben(benutzer_id: str) -> None:
    bekannt = schutzdatei.laden().get("bekannt", {})
    if benutzer_id not in bekannt:
        raise SperreFehler("Unbekannter Benutzer. Er muss die Finanzverwaltung einmal geöffnet haben.")
    name = bekannt[benutzer_id]["name"]
    schutzdatei.aendern(lambda d: d["sperre"]["benutzer"].setdefault(benutzer_id, {"name": name, "code": None}))
    LOG.info("Sperre: %s freigegeben", name or benutzer_id)


def benutzer_entfernen(b: dict, benutzer_id: str) -> None:
    if benutzer_id == b["id"]:
        raise SperreFehler("Den eigenen Eintrag kannst du nicht entfernen.")
    schutzdatei.aendern(lambda d: d["sperre"]["benutzer"].pop(benutzer_id, None))
    schutzdatei.fehlversuche_loeschen(f"code:{benutzer_id}")
    sitzungen_beenden(benutzer_id)
    LOG.info("Sperre: Benutzer %s aus der Freigabeliste entfernt", benutzer_id)


def benutzer_entsperren(benutzer_id: str) -> None:
    """Freigabe durch einen anderen freigegebenen Benutzer."""
    if not freigegeben(benutzer_id):
        raise SperreFehler("Dieser Benutzer steht nicht in der Freigabeliste.")
    schutzdatei.fehlversuche_loeschen(f"code:{benutzer_id}")
    LOG.info("Sperre: Fehlversuche von %s zurückgesetzt", benutzer_id)


def code_aendern(b: dict, alter_code: str, art: str, code: str, wiederholung: str) -> None:
    """Eigenen Code ändern (je Benutzer) oder gemeinsamen Code (nur Admin,
    vom Aufrufer geprüft). Der bisherige Code muss stimmen."""
    s = einstellungen()
    if not s:
        raise SperreFehler("Die Sperre ist nicht eingeschaltet.")
    if not code_stimmt(code_von(b["id"], s), alter_code):
        schutzdatei.fehlversuch_zaehlen(f"code:{b['id']}")
        raise SperreFehler("Der bisherige Code stimmt nicht.", 401)
    code = code_pruefen_format(art, code, mindestlaengen(s))
    if code != code_pruefen_format(art, wiederholung, mindestlaengen(s)):
        raise SperreFehler("Die beiden Eingaben stimmen nicht überein.")
    neu = code_hash(art, code)
    if s["modus"] == "gemeinsam":
        schutzdatei.aendern(lambda d: d["sperre"].__setitem__("gemeinsamer_code", neu))
    else:
        schutzdatei.aendern(lambda d: d["sperre"]["benutzer"][b["id"]].__setitem__("code", neu))
    LOG.info("Sperre: Code geändert von %s", b["name"] or b["id"])


def ausschalten(b: dict, code: str) -> None:
    s = einstellungen()
    if not s:
        raise SperreFehler("Die Sperre ist nicht eingeschaltet.")
    if not code_stimmt(code_von(b["id"], s), code):
        schutzdatei.fehlversuch_zaehlen(f"code:{b['id']}")
        raise SperreFehler("Der Code stimmt nicht.", 401)
    schutzdatei.aendern(lambda d: d.pop("sperre", None))
    schutzdatei.alle_fehlversuche_loeschen("code:")
    sitzungen_beenden()
    LOG.info("Sperre ausgeschaltet von %s", b["name"] or b["id"])


def uebersicht() -> dict:
    """Für die Administration: Einstellungen ohne Hashes, Benutzerlisten."""
    s = einstellungen()
    daten = schutzdatei.laden()
    bekannt = daten.get("bekannt", {})
    if not s:
        return {"aktiv": False, "bekannt": [{"id": i, **v} for i, v in bekannt.items()]}
    return {
        "aktiv": True,
        **{k: s[k] for k in ("modus", "grenze", "auto_minuten", "auto_hintergrund", "schnellbuchung", "seit")},
        "mindest": mindestlaengen(s),
        "gemeinsame_art": (s.get("gemeinsamer_code") or {}).get("art"),
        "benutzer": [{"id": i, "name": v.get("name") or bekannt.get(i, {}).get("name", ""),
                      "code_gesetzt": bool(v.get("code")) or s["modus"] == "gemeinsam",
                      "art": (code_von(i, s) or {}).get("art"),
                      **fehlversuche(i)} for i, v in s["benutzer"].items()],
        "bekannt": [{"id": i, **v} for i, v in bekannt.items() if i not in s["benutzer"]],
    }

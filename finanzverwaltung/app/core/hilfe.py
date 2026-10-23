"""
Hilfe der Anwendung (seit v2.1).

Eine einzige Quelle: app/hilfe/hilfe.md. Daraus entstehen die Hilfe-Ansicht
in der App (über /api/hilfe) und das PDF-Handbuch (hilfe_pdf.py). Beide nutzen
dieselbe Zerlegung mit markdown-it-py.

Auszeichnungen in der Datei (HTML-Kommentare, im Text unsichtbar):
  <!-- kapitel: bereich.thema -->   fester Anker, direkt unter jeder Überschrift
                                    der Ebenen 2 und 3. Bleibt beim Umschreiben.
  <!-- stichworte: A, B -->         Einträge fürs Stichwortverzeichnis
  <!-- hinweis: id --> … <!-- /hinweis -->
                                    Text, den die App wortgleich als Hinweis
                                    anzeigt (data-hinweis="id" in index.html).
  <!-- automatisch: stichwortverzeichnis -->
                                    Platzhalter, wird aus den Stichworten erzeugt.
Verweise auf Kapitel: [Text](#bereich.thema). Bilder: ![Text](bilder/datei.png),
höchstens eines je Unterkapitel.

Die zweite Zeile der Datei nennt die Programmversion („Programmversion: x.y“).
"""
import re
from pathlib import Path
from typing import Optional

from markdown_it import MarkdownIt

HILFE_VERZEICHNIS = Path(__file__).resolve().parent.parent / "hilfe"
HILFE_DATEI = HILFE_VERZEICHNIS / "hilfe.md"
BILDER_VERZEICHNIS = HILFE_VERZEICHNIS / "bilder"

_KOMMENTAR = re.compile(r"<!--\s*([a-zäöü/]+)\s*:?\s*(.*?)\s*-->", re.S)
_VERSION = re.compile(r"^Programmversion:\s*(\S+)\s*$", re.M)

_cache = {"mtime": None, "daten": None}


def _md() -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": True, "typographer": False}).enable("table")


def _kommentare(token) -> list:
    """Liefert [(art, wert)] aller Auszeichnungs-Kommentare eines html_block."""
    if token.type not in ("html_block", "html_inline"):
        return []
    return [(m.group(1).lower(), m.group(2).strip()) for m in _KOMMENTAR.finditer(token.content)]


def _klartext(tokens) -> str:
    teile = []
    for t in tokens:
        if t.type == "inline":
            for k in t.children or []:
                if k.type in ("text", "code_inline"):
                    teile.append(k.content)
                elif k.type in ("softbreak", "hardbreak"):
                    teile.append(" ")
            teile.append("\n")
    return re.sub(r"[ \t]+", " ", "".join(teile)).strip()


def _bildpfade_umschreiben(tokens) -> None:
    for t in tokens:
        for k in (t.children or []):
            if k.type == "image":
                src = k.attrGet("src") or ""
                if not src.startswith(("http:", "https:", "api/")):
                    k.attrSet("src", "api/hilfe/" + src.lstrip("./"))
                k.attrSet("loading", "lazy")


def zerlegen(text: str) -> dict:
    """Zerlegt die Markdown-Datei in Kapitel, Hinweise und Stichworte."""
    md = _md()
    tokens = md.parse(text)
    m = _VERSION.search(text)
    version = m.group(1) if m else ""

    titel = ""
    kapitel = []          # [{anker, titel, ebene, tokens, stichworte, eltern}]
    aktuell = None
    oberkapitel = None
    hinweise = {}
    hinweis_offen = None  # (id, start_index)
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.type == "heading_open" and t.tag in ("h1", "h2", "h3"):
            inhalt = tokens[i + 1].content
            if t.tag == "h1":
                titel = inhalt
                aktuell = None
                i += 3
                continue
            ebene = 1 if t.tag == "h2" else 2
            aktuell = {"anker": None, "titel": inhalt, "ebene": ebene, "tokens": [],
                       "stichworte": [], "eltern": None, "automatisch": None}
            if ebene == 1:
                oberkapitel = aktuell
            else:
                aktuell["eltern"] = oberkapitel["anker"] if oberkapitel else None
            kapitel.append(aktuell)
            i += 3
            continue
        for art, wert in _kommentare(t):
            if art == "kapitel" and aktuell is not None and aktuell["anker"] is None:
                aktuell["anker"] = wert
                if aktuell["ebene"] == 2 and oberkapitel is not None:
                    aktuell["eltern"] = oberkapitel["anker"]
            elif art == "stichworte" and aktuell is not None:
                aktuell["stichworte"] += [w.strip() for w in wert.split(",") if w.strip()]
            elif art == "automatisch" and aktuell is not None:
                aktuell["automatisch"] = wert
            elif art == "hinweis":
                hinweis_offen = (wert, len(aktuell["tokens"]) if aktuell else 0, aktuell)
            elif art == "/hinweis" and hinweis_offen:
                hid, start, kap = hinweis_offen
                if kap is not None:
                    hinweise[hid] = {"tokens": kap["tokens"][start:], "anker": kap["anker"]}
                hinweis_offen = None
        if aktuell is not None and not (t.type == "html_block" and _kommentare(t)):
            aktuell["tokens"].append(t)
        i += 1

    renderer = md.renderer
    ergebnis_kapitel = []
    for k in kapitel:
        _bildpfade_umschreiben(k["tokens"])
        ergebnis_kapitel.append({
            "anker": k["anker"], "titel": k["titel"], "ebene": k["ebene"], "eltern": k["eltern"],
            "html": renderer.render(k["tokens"], md.options, {}),
            "text": _klartext(k["tokens"]),
            "stichworte": k["stichworte"], "automatisch": k["automatisch"],
            "bilder": [c.attrGet("src") for t in k["tokens"] for c in (t.children or []) if c.type == "image"],
            "_tokens": k["tokens"],
        })
    ergebnis_hinweise = {}
    for hid, h in hinweise.items():
        tk = h["tokens"]
        if len(tk) == 3 and tk[0].type == "paragraph_open":
            html = renderer.renderInline(tk[1].children, md.options, {})
        else:
            html = renderer.render(tk, md.options, {})
        ergebnis_hinweise[hid] = {"html": html.strip(), "anker": h["anker"]}

    index = {}
    for k in ergebnis_kapitel:
        for w in k["stichworte"]:
            index.setdefault(w, [])
            if k["anker"] not in index[w]:
                index[w].append(k["anker"])
    stichwortverzeichnis = [{"wort": w, "anker": index[w]}
                            for w in sorted(index, key=lambda x: x.lower().replace("ä", "a").replace("ö", "o")
                                            .replace("ü", "u").replace("ß", "ss"))]
    return {"titel": titel, "version": version, "kapitel": ergebnis_kapitel,
            "hinweise": ergebnis_hinweise, "stichwortverzeichnis": stichwortverzeichnis}


def laden(datei: Optional[Path] = None) -> dict:
    """Liest und zerlegt die Hilfedatei, zwischengespeichert bis zur nächsten Änderung."""
    datei = datei or HILFE_DATEI
    mtime = datei.stat().st_mtime
    if datei == HILFE_DATEI and _cache["mtime"] == mtime:
        return _cache["daten"]
    daten = zerlegen(datei.read_text(encoding="utf-8"))
    if datei == HILFE_DATEI:
        _cache.update(mtime=mtime, daten=daten)
    return daten


def fuer_api(daten: dict) -> dict:
    return {
        "titel": daten["titel"], "version": daten["version"],
        "kapitel": [{k2: v for k2, v in k.items() if not k2.startswith("_")} for k in daten["kapitel"]],
        "hinweise": daten["hinweise"], "stichwortverzeichnis": daten["stichwortverzeichnis"],
    }


_MUSTER = ("Wofür?", "So geht's", "Gut zu wissen", "Siehe auch")
_VERSIONSHINWEIS = re.compile(r"\b(seit|ab|bis)\s+(Version|v)\s*\d|\bVersion\s+\d+\.\d+|\bv\d+\.\d+", re.I)


def pruefen(daten: dict, programmversion: Optional[str] = None, muster_ausnahmen=("erste-schritte",
            "rezepte", "begriffe", "stichwortverzeichnis")) -> list:
    """Prüft die Hilfedatei auf Regelverstöße und liefert eine Liste von Meldungen."""
    meldungen = []
    anker = [k["anker"] for k in daten["kapitel"]]
    for k in daten["kapitel"]:
        if not k["anker"]:
            meldungen.append(f"Kapitel „{k['titel']}“ ohne Anker")
    doppelt = {a for a in anker if a and anker.count(a) > 1}
    if doppelt:
        meldungen.append(f"Doppelte Anker: {sorted(doppelt)}")
    vorhanden = set(anker)
    for k in daten["kapitel"]:
        for ziel in re.findall(r'href="#([^"]+)"', k["html"]):
            if ziel not in vorhanden:
                meldungen.append(f"{k['anker']}: Verweis auf unbekanntes Kapitel #{ziel}")
        if len(k["bilder"]) > 1:
            meldungen.append(f"{k['anker']}: mehr als ein Bild")
        for b in k["bilder"]:
            pfad = HILFE_VERZEICHNIS / b.replace("api/hilfe/", "", 1)
            if not pfad.exists():
                meldungen.append(f"{k['anker']}: Bild fehlt ({b})")
        if _VERSIONSHINWEIS.search(k["text"]) or _VERSIONSHINWEIS.search(k["titel"]):
            meldungen.append(f"{k['anker']}: Hinweis auf einen Versionsstand")
        oben = (k["anker"] or "").split(".")[0]
        if k["ebene"] == 2 and oben not in muster_ausnahmen:
            pos = [k["text"].find(m) for m in _MUSTER]
            if any(p < 0 for p in pos) or pos != sorted(pos):
                meldungen.append(f"{k['anker']}: Muster Wofür?/So geht's/Gut zu wissen/Siehe auch fehlt oder Reihenfolge falsch")
    if programmversion and daten["version"] != programmversion:
        meldungen.append(f"Programmversion in der Hilfe {daten['version']!r}, im Programm {programmversion!r}")
    return meldungen

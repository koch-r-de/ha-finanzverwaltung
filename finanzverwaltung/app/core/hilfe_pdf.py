"""
PDF-Handbuch aus derselben Hilfedatei wie die Hilfe-Ansicht (seit v2.1).

ReportLab erzeugt Titelseite, Inhaltsverzeichnis mit Seitenzahlen,
Lesezeichen (Gliederung im PDF-Betrachter), Kopf- und Fußzeile mit
Programmversion und Seitenzahl sowie das Stichwortverzeichnis mit
Seitenzahlen. Schrift: DejaVu Sans (im Add-on über das Alpine-Paket
font-dejavu), damit Umlaute, „…“ und Pfeile korrekt erscheinen.
"""
import glob
import io
import os
from html import escape
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph,
                                Preformatted, Spacer, Table, TableStyle)
from reportlab.platypus.doctemplate import BaseDocTemplate, Frame, PageTemplate
from reportlab.platypus.tableofcontents import SimpleIndex, TableOfContents

from . import hilfe as hilfe_modul

GRUEN = colors.HexColor("#2f5d50")
GRAU = colors.HexColor("#666666")

_SCHRIFTEN = {
    "Hilfe": "DejaVuSans.ttf", "Hilfe-Fett": "DejaVuSans-Bold.ttf",
    "Hilfe-Kursiv": "DejaVuSans-Oblique.ttf", "Hilfe-FettKursiv": "DejaVuSans-BoldOblique.ttf",
    "Hilfe-Mono": "DejaVuSansMono.ttf",
}
_SUCHPFADE = ["/usr/share/fonts/dejavu", "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/TTF",
              "/usr/local/share/fonts", "C:/Windows/Fonts"]
_registriert = False


def _schrift_finden(name: str) -> Optional[str]:
    for verz in _SUCHPFADE:
        p = os.path.join(verz, name)
        if os.path.exists(p):
            return p
    treffer = glob.glob(f"/usr/share/fonts/**/{name}", recursive=True)
    return treffer[0] if treffer else None


def _schriften_registrieren() -> None:
    global _registriert
    if _registriert:
        return
    for alias, datei in _SCHRIFTEN.items():
        pfad = _schrift_finden(datei)
        if not pfad:
            raise RuntimeError(f"Schrift {datei} nicht gefunden (Paket font-dejavu fehlt?)")
        pdfmetrics.registerFont(TTFont(alias, pfad))
    pdfmetrics.registerFontFamily("Hilfe", normal="Hilfe", bold="Hilfe-Fett", italic="Hilfe-Kursiv",
                                  boldItalic="Hilfe-FettKursiv")
    _registriert = True


def _stile() -> dict:
    basis = dict(fontName="Hilfe", fontSize=10, leading=14.5)
    return {
        "text": ParagraphStyle("text", **basis, spaceAfter=5),
        "liste": ParagraphStyle("liste", **basis),
        "k1": ParagraphStyle("k1", fontName="Hilfe-Fett", fontSize=17, leading=21, textColor=GRUEN,
                             spaceBefore=4, spaceAfter=10, keepWithNext=1),
        "k2": ParagraphStyle("k2", fontName="Hilfe-Fett", fontSize=12.5, leading=16, textColor=GRUEN,
                             spaceBefore=12, spaceAfter=5, keepWithNext=1),
        "titel": ParagraphStyle("titel", fontName="Hilfe-Fett", fontSize=26, leading=32, textColor=GRUEN,
                                alignment=TA_CENTER),
        "untertitel": ParagraphStyle("untertitel", fontName="Hilfe", fontSize=12, leading=16, textColor=GRAU,
                                     alignment=TA_CENTER),
        "toc1": ParagraphStyle("toc1", fontName="Hilfe-Fett", fontSize=10.5, leading=15, spaceBefore=4),
        "toc2": ParagraphStyle("toc2", fontName="Hilfe", fontSize=9.5, leading=13, leftIndent=14),
        "zelle": ParagraphStyle("zelle", fontName="Hilfe", fontSize=9, leading=12),
        "index": ParagraphStyle("index", fontName="Hilfe", fontSize=9.5, leading=13),
        "code": ParagraphStyle("code", fontName="Hilfe-Mono", fontSize=8.3, leading=11, leftIndent=8,
                               backColor=colors.HexColor("#f2f1ec"), borderPadding=5, spaceBefore=4, spaceAfter=8),
    }


def _inline(children) -> str:
    """markdown-it-Inline-Token -> ReportLab-Paragraph-Markup."""
    teile = []
    for c in children or []:
        if c.type == "text":
            teile.append(escape(c.content, quote=False))
        elif c.type == "code_inline":
            teile.append(f'<font face="Hilfe-Mono">{escape(c.content, quote=False)}</font>')
        elif c.type in ("softbreak",):
            teile.append(" ")
        elif c.type == "hardbreak":
            teile.append("<br/>")
        elif c.type == "strong_open":
            teile.append("<b>")
        elif c.type == "strong_close":
            teile.append("</b>")
        elif c.type == "em_open":
            teile.append("<i>")
        elif c.type == "em_close":
            teile.append("</i>")
        elif c.type == "link_open":
            href = c.attrGet("href") or ""
            if href.startswith("#"):
                teile.append(f'<a href="#{escape(href[1:])}" color="#2f5d50">')
            else:
                teile.append(f'<a href="{escape(href)}" color="#2f5d50">')
        elif c.type == "link_close":
            teile.append("</a>")
    return "".join(teile)


class _Ueberschrift(Paragraph):
    def __init__(self, text, stil, ebene, anker, titel):
        super().__init__(text, stil)
        self.ebene, self.anker, self.titel_klar = ebene, anker, titel


class _Dokument(BaseDocTemplate):
    def __init__(self, puffer, version: str, **kw):
        super().__init__(puffer, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                         topMargin=2.2 * cm, bottomMargin=2 * cm, title="Finanzverwaltung – Hilfe",
                         author="Finanzverwaltung", **kw)
        self.version = version
        rahmen = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="inhalt")
        self.addPageTemplates([
            PageTemplate(id="titel", frames=[rahmen]),
            PageTemplate(id="normal", frames=[rahmen], onPage=self._kopf_fuss),
        ])

    def _kopf_fuss(self, canv, doc):
        canv.saveState()
        canv.setFont("Hilfe", 8.5)
        canv.setFillColor(GRAU)
        oben = A4[1] - 1.4 * cm
        canv.drawString(self.leftMargin, oben, "Finanzverwaltung · Hilfe")
        canv.drawRightString(A4[0] - self.rightMargin, oben, f"Programmversion {self.version}")
        canv.drawCentredString(A4[0] / 2, 1.1 * cm, f"Seite {doc.page}")
        canv.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, _Ueberschrift):
            schluessel = flowable.anker
            self.canv.bookmarkPage(schluessel)
            self.canv.addOutlineEntry(flowable.titel_klar, schluessel, level=flowable.ebene - 1, closed=True)
            self.notify("TOCEntry", (flowable.ebene - 1, flowable.titel_klar, self.page, schluessel))


def _bloecke(tokens, stile, breite) -> list:
    """Block-Token eines Kapitels -> Flowables."""
    story = []
    i = 0

    def liste(start):
        """Liest eine (verschachtelte) Liste ab tokens[start] und liefert (Flowable, Endindex)."""
        offen = tokens[start]
        nummeriert = offen.type == "ordered_list_open"
        schliessen = "ordered_list_close" if nummeriert else "bullet_list_close"
        punkte, j, tiefe = [], start + 1, 0
        aktuell = []
        while j < len(tokens):
            t = tokens[j]
            if t.type == schliessen and tiefe == 0:
                break
            if t.type == "list_item_open":
                aktuell = []
            elif t.type == "list_item_close":
                punkte.append(ListItem(aktuell, leftIndent=14))
            elif t.type == "inline":
                aktuell.append(Paragraph(_inline(t.children), stile["liste"]))
            elif t.type in ("bullet_list_open", "ordered_list_open"):
                unter, j = liste(j)
                aktuell.append(unter)
            j += 1
        kw = dict(bulletFontName="Hilfe", bulletFontSize=10, leftIndent=16)
        if nummeriert:
            fl = ListFlowable(punkte, bulletType="1", bulletFormat="%s.", start=offen.attrGet("start") or 1, **kw)
        else:
            fl = ListFlowable(punkte, bulletType="bullet", start="•", **kw)
        return fl, j

    while i < len(tokens):
        t = tokens[i]
        if t.type == "paragraph_open":
            inl = tokens[i + 1]
            bild = [c for c in inl.children or [] if c.type == "image"]
            if bild:
                story.append(_bild(bild[0], breite))
            else:
                story.append(Paragraph(_inline(inl.children), stile["text"]))
            i += 3
            continue
        if t.type in ("bullet_list_open", "ordered_list_open"):
            fl, i = liste(i)
            story.append(fl)
            story.append(Spacer(1, 5))
            i += 1
            continue
        if t.type in ("fence", "code_block"):
            story.append(Preformatted(t.content.rstrip("\n"), stile["code"]))
            i += 1
            continue
        if t.type == "table_open":
            zeilen, j = [], i + 1
            zeile = None
            while tokens[j].type != "table_close":
                if tokens[j].type == "tr_open":
                    zeile = []
                elif tokens[j].type == "tr_close":
                    zeilen.append(zeile)
                elif tokens[j].type == "inline":
                    zeile.append(Paragraph(_inline(tokens[j].children), stile["zelle"]))
                j += 1
            tab = Table(zeilen, repeatRows=1, hAlign="LEFT")
            tab.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bfbfbf")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8efe9")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story += [tab, Spacer(1, 6)]
            i = j + 1
            continue
        i += 1
    return story


def _bild(token, breite):
    src = token.attrGet("src") or ""
    pfad = hilfe_modul.HILFE_VERZEICHNIS / src.replace("api/hilfe/", "", 1)
    if not pfad.exists():
        return Spacer(1, 1)
    from reportlab.lib.utils import ImageReader
    b, h = ImageReader(str(pfad)).getSize()
    w = min(breite, b * 0.5)
    return KeepTogether([Spacer(1, 4), Image(str(pfad), width=w, height=h * w / b), Spacer(1, 8)])


_cache = {"schluessel": None, "pdf": None}


def erzeugen_zwischengespeichert() -> bytes:
    """Das PDF hängt nur von Hilfedatei und Bildern ab: einmal erzeugen,
    bis sich eine davon ändert."""
    dateien = [hilfe_modul.HILFE_DATEI] + sorted(hilfe_modul.BILDER_VERZEICHNIS.glob("*.png"))
    schluessel = tuple((str(d), d.stat().st_mtime) for d in dateien)
    if _cache["schluessel"] != schluessel:
        _cache.update(schluessel=schluessel, pdf=erzeugen())
    return _cache["pdf"]


def erzeugen(daten: Optional[dict] = None) -> bytes:
    _schriften_registrieren()
    daten = daten or hilfe_modul.laden()
    stile = _stile()
    puffer = io.BytesIO()
    doc = _Dokument(puffer, daten["version"])
    breite = doc.width

    story = [Spacer(1, 7 * cm), Paragraph("Finanzverwaltung", stile["titel"]), Spacer(1, 0.4 * cm),
             Paragraph("Hilfe und Handbuch", stile["untertitel"]), Spacer(1, 0.3 * cm),
             Paragraph(f"Programmversion {escape(daten['version'])}", stile["untertitel"])]
    from reportlab.platypus.doctemplate import NextPageTemplate
    story += [NextPageTemplate("normal"), PageBreak()]

    inhalt = TableOfContents(dotsMinLevel=0)
    inhalt.levelStyles = [stile["toc1"], stile["toc2"]]
    story += [Paragraph("Inhalt", stile["k1"]), inhalt, PageBreak()]

    index = SimpleIndex(dot=" . ", headers=True, style=stile["index"])
    erstes = True
    for k in daten["kapitel"]:
        if k["ebene"] == 1:
            if not erstes:
                story.append(PageBreak())
            erstes = False
        stichworte = "".join(f'<index item="{escape(w)}"/>' for w in k["stichworte"])
        story.append(_Ueberschrift(escape(k["titel"]) + stichworte, stile["k1" if k["ebene"] == 1 else "k2"],
                                   k["ebene"], k["anker"], k["titel"]))
        if k.get("automatisch") == "stichwortverzeichnis":
            story.append(index)
            continue
        story += _bloecke(k["_tokens"], stile, breite)

    doc.multiBuild(story, canvasmaker=index.getCanvasMaker())
    return puffer.getvalue()

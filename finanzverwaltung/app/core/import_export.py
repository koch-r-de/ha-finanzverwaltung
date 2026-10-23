"""
Wert-Konvertierung für den Datei-Import (CSV oder XLSX).

Seit v2.0 liegt der eigentliche Import/Export im XLSX-Roundtrip
(app/roundtrip.py: Export aller Bereiche, Re-Upload mit Vorschau,
Änderungen und Löschungen). Dieses Modul enthält nur noch die gemeinsamen,
bewusst großzügigen Konvertierungen (die Datei kommt meist aus Excel/
LibreOffice mit deutscher Spracheinstellung):
  - Zahlen akzeptieren Komma ODER Punkt als Dezimaltrennzeichen.
  - Datumsfelder akzeptieren reinen Text (CSV) und echte Datumszellen (XLSX).
  - CSV-Kodierung wird erkannt (utf-8-sig, cp1252, latin-1).
"""
from datetime import date, datetime
from typing import Optional


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v).strip()


def _opt_txt(v) -> Optional[str]:
    t = _txt(v)
    return t or None


def _zahl(v) -> Optional[float]:
    """Wandelt einen Zellwert in eine Zahl um - toleriert sowohl deutsches
    (1.234,56 bzw. 1086,97) als auch englisches (1234.56) Zahlenformat,
    plus Zellen, die openpyxl bereits als echte Zahl liefert."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = _txt(v)
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    return float(t)


def _ganz(v) -> Optional[int]:
    f = _zahl(v)
    return int(f) if f is not None else None


def _datum(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    t = _txt(v)
    if not t:
        return None
    return date.fromisoformat(t[:10]).isoformat()


def _bool01(v) -> bool:
    t = _txt(v).lower()
    return t in ("1", "true", "ja", "wahr", "yes", "x")


def _bool_default(v, standard: bool) -> bool:
    t = _txt(v)
    return standard if not t else _bool01(v)


def _text_dekodieren(rohbytes: bytes) -> str:
    for kodierung in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return rohbytes.decode(kodierung)
        except UnicodeDecodeError:
            continue
    raise ValueError("Zeichenkodierung der Datei konnte nicht erkannt werden.")

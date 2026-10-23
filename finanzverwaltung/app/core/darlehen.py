"""
Darlehens- und Tilgungsplan-Rechner.

Berechnet den vollständigen monatlichen Tilgungsplan eines Darlehens
über drei Phasen hinweg:

  1. Tilgungsfreie Phase (Zinsbeginn -> Tilgungsbeginn): nur Zinsen,
     Restschuld = Summe der bisherigen Auszahlungen.
  2. Tilgungsphase (Tilgungsbeginn -> Ende Zinsbindung): konstante
     Annuität (Zinssatz).
  3. Anschlussphase (Ende Zinsbindung -> Laufzeitende): neue
     konstante Annuität mit dem Anschlusszinssatz.

Die monatliche Rate ist wählbar (Entscheidung des Anwenders):
  - "tilgungssatz": Rate = (Zinssatz % + Tilgungssatz %) / 12 * Basis
  - "feste_rate":   Rate wird direkt in Euro vorgegeben

Annahme für die Anschlussphase (im Fachkonzept nicht spezifiziert):
  - Modus "tilgungssatz": neue Annuität mit demselben Tilgungssatz,
    aber dem Anschlusszinssatz, auf Basis der Restschuld zu Beginn
    der Anschlussphase.
  - Modus "feste_rate": nutzt `anschluss_feste_rate`, falls vom
    Anwender gesetzt, sonst bleibt die bisherige feste Rate bestehen.
  Das ist eine sinnvolle Annahme, aber bewusst konfigurierbar - bei
  Bedarf gerne anders spezifizieren.

Stufenweise Auszahlungen werden als laufende Zugänge zur Restschuld
behandelt, unabhängig davon, in welcher Phase sie erfolgen.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

from dateutil.relativedelta import relativedelta


@dataclass
class Auszahlung:
    datum: date
    betrag: float


@dataclass
class Darlehen:
    bezeichnung: str
    zinssatz: float                      # % p.a. während der Zinsbindung
    zinsbeginn: date
    tilgungsbeginn: date
    laufzeit_jahre: int
    ende_zinsbindung: date
    anschlusszinssatz: float             # % p.a. nach der Zinsbindung
    raten_modus: Literal["tilgungssatz", "feste_rate"]
    tilgungssatz: Optional[float] = None       # % p.a., falls raten_modus == "tilgungssatz"
    feste_rate: Optional[float] = None         # Euro/Monat, falls raten_modus == "feste_rate"
    anschluss_feste_rate: Optional[float] = None
    auszahlungen: list[Auszahlung] = field(default_factory=list)

    @property
    def laufzeitende(self) -> date:
        return self.zinsbeginn + relativedelta(years=self.laufzeit_jahre)


@dataclass
class TilgungsplanZeile:
    datum: date
    phase: str
    zinssatz: float
    zinsen: float
    tilgung: float
    sondertilgung: float
    rate: float
    restschuld: float


def aus_db_zeile(row, auszahlungen_rows) -> "Darlehen":
    """Baut ein Darlehen-Objekt aus einer sqlite3.Row der 'darlehen'-Tabelle
    plus den zugehörigen Zeilen aus 'darlehen_auszahlungen'."""
    return Darlehen(
        bezeichnung=row["bezeichnung"],
        zinssatz=row["zinssatz"],
        zinsbeginn=date.fromisoformat(row["zinsbeginn"]),
        tilgungsbeginn=date.fromisoformat(row["tilgungsbeginn"]),
        laufzeit_jahre=row["laufzeit_jahre"],
        ende_zinsbindung=date.fromisoformat(row["ende_zinsbindung"]),
        anschlusszinssatz=row["anschlusszinssatz"],
        raten_modus=row["raten_modus"],
        tilgungssatz=row["tilgungssatz"],
        feste_rate=row["feste_rate"],
        anschluss_feste_rate=row["anschluss_feste_rate"],
        auszahlungen=[Auszahlung(date.fromisoformat(a["datum"]), a["betrag"]) for a in auszahlungen_rows],
    )


def _ausgezahlt_bis(darlehen: Darlehen, stichtag: date) -> float:
    return sum(a.betrag for a in darlehen.auszahlungen if a.datum <= stichtag)


def berechne_annuitaet(zinssatz: float, tilgungssatz: float, basis: float) -> float:
    """Klassische Annuität: (Zins % + Tilgung %) / 12 * Basisbetrag."""
    return round((zinssatz + tilgungssatz) / 100 / 12 * basis, 2)


def berechne_tilgungsplan(
    darlehen: Darlehen,
    sondertilgungen: Optional[dict[date, float]] = None,
) -> list[TilgungsplanZeile]:
    sondertilgungen = sondertilgungen or {}
    zeilen: list[TilgungsplanZeile] = []

    restschuld = 0.0
    letzter_ausgezahlt_stand = 0.0
    rate_tilgungsphase: Optional[float] = None
    rate_anschlussphase: Optional[float] = None

    monat = date(darlehen.zinsbeginn.year, darlehen.zinsbeginn.month, 1)
    laufzeitende = darlehen.laufzeitende

    while monat < laufzeitende:
        ausgezahlt_stand = _ausgezahlt_bis(darlehen, monat)
        restschuld += ausgezahlt_stand - letzter_ausgezahlt_stand
        letzter_ausgezahlt_stand = ausgezahlt_stand

        if monat < darlehen.tilgungsbeginn:
            phase = "tilgungsfrei"
            zinssatz_aktuell = darlehen.zinssatz
            zinsen = round(restschuld * zinssatz_aktuell / 100 / 12, 2)
            tilgung = 0.0
            rate = zinsen

        elif monat < darlehen.ende_zinsbindung:
            phase = "tilgung"
            zinssatz_aktuell = darlehen.zinssatz
            if rate_tilgungsphase is None:
                if darlehen.raten_modus == "tilgungssatz":
                    rate_tilgungsphase = berechne_annuitaet(
                        darlehen.zinssatz, darlehen.tilgungssatz, restschuld
                    )
                else:
                    rate_tilgungsphase = darlehen.feste_rate
            zinsen = round(restschuld * zinssatz_aktuell / 100 / 12, 2)
            rate = rate_tilgungsphase
            tilgung = round(rate - zinsen, 2)

        else:
            phase = "anschluss"
            zinssatz_aktuell = darlehen.anschlusszinssatz
            if rate_anschlussphase is None:
                if darlehen.raten_modus == "tilgungssatz":
                    rate_anschlussphase = berechne_annuitaet(
                        darlehen.anschlusszinssatz, darlehen.tilgungssatz, restschuld
                    )
                else:
                    rate_anschlussphase = darlehen.anschluss_feste_rate or darlehen.feste_rate
            zinsen = round(restschuld * zinssatz_aktuell / 100 / 12, 2)
            rate = rate_anschlussphase
            tilgung = round(rate - zinsen, 2)

        if phase != "tilgungsfrei":
            # Seit v1.9.1: nie mehr tilgen als die Restschuld. Die letzte Rate
            # wird entsprechend kleiner (Zinsen + Resttilgung), danach folgen
            # Nullzeilen - vorher lief die volle Rate nach der Ablösung als
            # "Tilgung" bis zum Laufzeitende weiter.
            tilgung = round(min(tilgung, restschuld), 2)
            rate = zinsen + tilgung
        # Sondertilgung ebenfalls höchstens bis zur Restschuld
        sondertilgung = round(min(sondertilgungen.get(monat, 0.0), max(restschuld - tilgung, 0.0)), 2)
        restschuld = round(max(restschuld - tilgung - sondertilgung, 0.0), 2)

        zeilen.append(TilgungsplanZeile(
            datum=monat, phase=phase, zinssatz=zinssatz_aktuell,
            zinsen=zinsen, tilgung=tilgung, sondertilgung=sondertilgung,
            rate=round(rate, 2), restschuld=restschuld,
        ))

        monat = monat + relativedelta(months=1)

    return zeilen


def pruefe_sondertilgungs_zeitpunkt(darlehen: Darlehen, datum: date) -> Optional[str]:
    """Warnung (kein Hard-Block), falls das Datum außerhalb der Tilgungsphase liegt."""
    if not (darlehen.tilgungsbeginn <= datum < darlehen.ende_zinsbindung):
        return "Warnung: Die Sondertilgung liegt außerhalb der Tilgungsphase."
    return None


def pruefe_darlehen_konsistenz(darlehen: Darlehen) -> list[str]:
    """Warnungen bei fachlich unplausiblen Eckdaten (kein Hard-Block)."""
    warnungen = []
    if darlehen.tilgungsbeginn < darlehen.zinsbeginn:
        warnungen.append("Warnung: Der Tilgungsbeginn liegt vor dem Zinsbeginn.")
    if darlehen.laufzeitende < darlehen.ende_zinsbindung:
        warnungen.append("Warnung: Das Laufzeitende liegt vor dem Ende der Zinsbindung.")
    return warnungen

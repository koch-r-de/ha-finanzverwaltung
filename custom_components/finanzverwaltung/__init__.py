"""Finanzverwaltung: Seitenleisten-Eintrag „Schnellbuchung“ für das Add-on.

Die Integration ersetzt seit 2.7 den Eintrag über panel_custom in der
configuration.yaml. Sie liefert die Panel-Datei selbst aus, hängt die Version
an die Adresse (kein Zwischenspeicher-Problem nach Updates) und gibt dem Panel
die Kennung des Add-ons mit. Die Kennung ermittelt sie hier auf dem Server,
weil Home Assistant die Liste aller Add-ons nur Administratoren zeigt
(Befund S). Begründungen stehen in finanzverwaltung/DOCS.md.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.start import async_at_started
from homeassistant.loader import async_get_integration

_LOGGER = logging.getLogger(__name__)

DOMAIN = "finanzverwaltung"
URL_PFAD = "finanzen-schnellbuchung"
ELEMENT = "finanzverwaltung-schnellbuchung"
STATISCH = "/finanzverwaltung_dateien"
PANEL_DATEI = "schnellbuchung-panel.js"
TITEL = "Schnellbuchung"
SYMBOL = "mdi:cash-plus"
MELDUNG_ALT = "alter_seitenleisten_eintrag"
ANLEITUNG = ("https://github.com/koch-r-de/ha-finanzverwaltung/blob/main/"
             "ha-integration/README-HA-Integration.md#umstieg-vom-yaml-eintrag")

# Merkmale des Eintrags aus configuration.yaml (bis 2.6.4)
ALTES_ELEMENT = "finanzen-schnellbuchung-panel"
ALTE_DATEI = "finanzen-schnellbuchung.js"


def kennung_waehlen(addons: Iterable[tuple[str, str]]) -> str | None:
    """Kennung des Add-ons aus (Kennung, Zustand)-Paaren wählen.

    Lokal installiert heißt es local_finanzverwaltung, aus einem Repository
    <kennung>_finanzverwaltung. Bei mehreren Treffern zählt nur ein laufendes.
    Ohne eindeutigen Treffer None: Das Panel sucht dann selbst (nur für
    Administratoren möglich) und zeigt sonst eine Fehlermeldung."""
    treffer = [(k, z) for k, z in addons if k.endswith("_finanzverwaltung")]
    if len(treffer) == 1:
        return treffer[0][0]
    laufend = [k for k, z in treffer if str(z).lower() == "started"]
    if len(laufend) == 1:
        return laufend[0]
    if treffer:
        _LOGGER.warning("Mehrere Add-ons der Finanzverwaltung gefunden (%s), keines eindeutig laufend",
                        ", ".join(k for k, _ in treffer))
    return None


def alte_eintraege(panels: dict[str, Any]) -> list[str]:
    """Adressen von Seitenleisten-Einträgen, die noch die alte Panel-Datei aus
    config/www über panel_custom in der configuration.yaml laden."""
    gefunden = []
    for pfad, panel in panels.items():
        eigen = (getattr(panel, "config", None) or {}).get("_panel_custom") or {}
        quelle = str(eigen.get("module_url") or eigen.get("js_url") or "")
        if eigen.get("name") == ALTES_ELEMENT or ALTE_DATEI in quelle:
            gefunden.append(pfad)
    return sorted(gefunden)


async def _kennung_ermitteln(hass: HomeAssistant) -> str | None:
    try:
        from homeassistant.components.hassio import get_supervisor_client

        liste = await get_supervisor_client(hass).addons.list()
    except Exception as fehler:  # noqa: BLE001 - Supervisor fehlt oder antwortet nicht
        _LOGGER.warning("Add-on-Liste nicht abrufbar: %s", fehler)
        return None
    return kennung_waehlen((a.slug, getattr(a.state, "value", a.state)) for a in liste)


@callback
def _alten_eintrag_pruefen(hass: HomeAssistant) -> None:
    alte = alte_eintraege(hass.data.get(frontend.DATA_PANELS, {}))
    if alte:
        ir.async_create_issue(
            hass, DOMAIN, MELDUNG_ALT, is_fixable=False, is_persistent=False,
            severity=ir.IssueSeverity.WARNING, translation_key=MELDUNG_ALT,
            translation_placeholders={"adressen": ", ".join("/" + a for a in alte)},
            learn_more_url=ANLEITUNG)
    else:
        ir.async_delete_issue(hass, DOMAIN, MELDUNG_ALT)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    daten = hass.data.setdefault(DOMAIN, {})
    if not daten.get("statisch"):
        # Statische Pfade lassen sich zur Laufzeit nicht wieder entfernen,
        # deshalb nur einmal je Start von Home Assistant anmelden.
        ordner = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths([StaticPathConfig(STATISCH, str(ordner), False)])
        daten["statisch"] = True

    version = (await async_get_integration(hass, DOMAIN)).version
    kennung = await _kennung_ermitteln(hass)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=URL_PFAD,
        webcomponent_name=ELEMENT,
        sidebar_title=TITEL,
        sidebar_icon=SYMBOL,
        module_url=f"{STATISCH}/{PANEL_DATEI}?v={version}",
        embed_iframe=False,
        require_admin=False,
        config={"kennung": kennung},
    )

    # Erst nach dem Start prüfen: Vorher hat panel_custom die Einträge aus der
    # configuration.yaml eventuell noch nicht angelegt.
    @callback
    def _nach_start(_: HomeAssistant) -> None:
        _alten_eintrag_pruefen(hass)

    entry.async_on_unload(async_at_started(hass, _nach_start))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    frontend.async_remove_panel(hass, URL_PFAD, warn_if_unknown=False)
    ir.async_delete_issue(hass, DOMAIN, MELDUNG_ALT)
    return True

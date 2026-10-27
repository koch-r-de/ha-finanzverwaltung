"""Fachlicher Test 2.7: Integration custom_components/finanzverwaltung (HACS).

Läuft mit pytest in einer eigenen Python-Umgebung mit Home Assistant, weil die
Integration nur darin lauffähig ist (Einrichtung siehe tests/README.md):

    python3 tests/v27_test.py            # sucht tests/.ha-venv oder FINANZAPP_HA_PYTHON

Geprüft: Einrichtung (auch ohne Supervisor und doppelt), Panel mit Version und
Kennung (Befund S), Kennungswahl mit Fehlerfällen, Auslieferung der Panel-Datei,
Hinweis auf den alten YAML-Eintrag, Entfernen, Neuladen, Versionsgleichheit
und Pflichtdateien für HACS. Die Argumente von alle_tests.py werden ignoriert."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
INTEGRATION = WURZEL / "custom_components" / "finanzverwaltung"

if __name__ == "__main__":
    # Außerhalb von pytest: mit der Home-Assistant-Umgebung neu starten und
    # das Ergebnis im Format der übrigen Reihen ausgeben.
    python = os.environ.get("FINANZAPP_HA_PYTHON") or str(WURZEL / "tests" / ".ha-venv" / "bin" / "python")
    if not Path(python).exists():
        print("FEHL Home-Assistant-Testumgebung fehlt (tests/README.md, Abschnitt Einrichten)")
        print("\n0/1 bestanden ['HA-Testumgebung']")
        sys.exit(1)
    lauf = subprocess.run([python, "-m", "pytest", str(Path(__file__)), "-p", "no:cacheprovider",
                           "-p", "no:sugar", "-q", "-rA", "--no-header", "-o", "asyncio_mode=auto"],
                          cwd=WURZEL, capture_output=True, text=True)
    ergebnis = []
    for zeile in lauf.stdout.splitlines():
        m = re.match(r"^(PASSED|FAILED|ERROR) \S+::(\S+)", zeile)
        if m:
            ok = m.group(1) == "PASSED"
            ergebnis.append((m.group(2), ok))
            print(("OK   " if ok else "FEHL ") + m.group(2))
    if not ergebnis or lauf.returncode not in (0, 1):
        print(lauf.stdout[-4000:], lauf.stderr[-4000:])
    fehl = [n for n, ok in ergebnis if not ok] or ([] if ergebnis else ["pytest"])
    print(f"\n{len(ergebnis) - len([n for n, ok in ergebnis if not ok])}/{max(len(ergebnis), 1)} bestanden", fehl)
    sys.exit(1 if fehl else 0)

# ---------------------------------------------------------------- pytest-Teil
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml

sys.path.insert(0, str(WURZEL))

from homeassistant import config_entries
from homeassistant.components import frontend, panel_custom
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.finanzverwaltung as fv

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def addons(*paare):
    return [SimpleNamespace(slug=k, state=SimpleNamespace(value=z)) for k, z in paare]


def supervisor(liste=None, fehler=None):
    client = SimpleNamespace(addons=SimpleNamespace(list=AsyncMock(return_value=liste, side_effect=fehler)))
    return patch("homeassistant.components.hassio.get_supervisor_client", return_value=client)


async def einrichten(hass: HomeAssistant, liste=None, fehler=None) -> MockConfigEntry:
    eintrag = MockConfigEntry(domain=fv.DOMAIN, title="Finanzverwaltung", data={})
    eintrag.add_to_hass(hass)
    with supervisor(liste or [], fehler):
        assert await hass.config_entries.async_setup(eintrag.entry_id)
        await hass.async_block_till_done()
    return eintrag


def panel(hass: HomeAssistant, pfad: str = fv.URL_PFAD):
    return hass.data.get(frontend.DATA_PANELS, {}).get(pfad)


# --- Kennung wählen (Befund S, serverseitig) -------------------------------

def test_kennung_lokal_und_repository():
    assert fv.kennung_waehlen([("local_finanzverwaltung", "started")]) == "local_finanzverwaltung"
    assert fv.kennung_waehlen([("core_ssh", "started"), ("e396af1a_finanzverwaltung", "stopped")]) \
        == "e396af1a_finanzverwaltung"


def test_kennung_mehrere_nur_laufendes_zaehlt():
    assert fv.kennung_waehlen([("local_finanzverwaltung", "stopped"),
                               ("e396af1a_finanzverwaltung", "started")]) == "e396af1a_finanzverwaltung"


def test_kennung_fehlerfaelle_ergeben_none():
    assert fv.kennung_waehlen([]) is None
    assert fv.kennung_waehlen([("core_ssh", "started"), ("abc_finanzverwaltung_alt", "started"),
                               ("finanzverwaltung", "started")]) is None
    assert fv.kennung_waehlen([("local_finanzverwaltung", "started"),
                               ("e396af1a_finanzverwaltung", "started")]) is None
    assert fv.kennung_waehlen([("local_finanzverwaltung", "stopped"),
                               ("e396af1a_finanzverwaltung", "stopped")]) is None


# --- Einrichtung -----------------------------------------------------------

async def test_einrichtung_ohne_supervisor_bricht_ab(hass: HomeAssistant):
    with patch("custom_components.finanzverwaltung.config_flow.is_hassio", return_value=False):
        r = await hass.config_entries.flow.async_init(fv.DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "kein_supervisor"


async def test_einrichtung_mit_supervisor_und_nur_einmal(hass: HomeAssistant):
    with patch("custom_components.finanzverwaltung.config_flow.is_hassio", return_value=True), \
         supervisor(addons(("e396af1a_finanzverwaltung", "started"))):
        r = await hass.config_entries.flow.async_init(fv.DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert r["type"] is FlowResultType.FORM and r["step_id"] == "user"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        assert r["type"] is FlowResultType.CREATE_ENTRY and r["title"] == "Finanzverwaltung"
        await hass.async_block_till_done()
        r = await hass.config_entries.flow.async_init(fv.DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "single_instance_allowed"
    assert panel(hass) is not None


# --- Panel ------------------------------------------------------------------

async def test_panel_mit_version_kennung_und_adresse(hass: HomeAssistant):
    await einrichten(hass, addons(("core_ssh", "started"), ("e396af1a_finanzverwaltung", "started")))
    p = panel(hass)
    eigen = p.config["_panel_custom"]
    assert p.frontend_url_path == "finanzen-schnellbuchung" and p.sidebar_title == "Schnellbuchung"
    assert p.sidebar_icon == "mdi:cash-plus" and p.require_admin is False
    assert eigen["name"] == "finanzverwaltung-schnellbuchung" and eigen["embed_iframe"] is False
    version = json.loads((INTEGRATION / "manifest.json").read_text())["version"]
    assert eigen["module_url"] == f"/finanzverwaltung_dateien/schnellbuchung-panel.js?v={version}"
    assert p.config["kennung"] == "e396af1a_finanzverwaltung"
    assert panel(hass, "schnellbuchung") is None


async def test_panel_ohne_eindeutige_kennung_und_bei_supervisorfehler(hass: HomeAssistant):
    await einrichten(hass, fehler=RuntimeError("Supervisor nicht erreichbar"))
    assert panel(hass) is not None and panel(hass).config["kennung"] is None


async def test_panel_datei_wird_ausgeliefert(hass: HomeAssistant, hass_client):
    await einrichten(hass, addons(("local_finanzverwaltung", "started")))
    client = await hass_client()
    antwort = await client.get("/finanzverwaltung_dateien/schnellbuchung-panel.js?v=2.7")
    text = await antwort.text()
    assert antwort.status == 200 and 'const ELEMENT = "finanzverwaltung-schnellbuchung"' in text
    assert (await client.get("/finanzverwaltung_dateien/gibtsnicht.js")).status == 404
    assert (await client.get("/finanzverwaltung_dateien/../__init__.py")).status in (403, 404)


async def test_entfernen_und_neu_laden(hass: HomeAssistant):
    eintrag = await einrichten(hass, addons(("local_finanzverwaltung", "started")))
    with supervisor(addons(("local_finanzverwaltung", "started"))):
        assert await hass.config_entries.async_reload(eintrag.entry_id)
        await hass.async_block_till_done()
    assert panel(hass) is not None
    assert await hass.config_entries.async_unload(eintrag.entry_id)
    await hass.async_block_till_done()
    assert panel(hass) is None


# --- Alter Eintrag aus configuration.yaml ----------------------------------

async def alter_yaml_eintrag(hass: HomeAssistant):
    assert await async_setup_component(hass, "panel_custom", {"panel_custom": [{
        "name": "finanzen-schnellbuchung-panel", "sidebar_title": "Schnellbuchung",
        "sidebar_icon": "mdi:cash-plus", "url_path": "schnellbuchung",
        "module_url": "/local/finanzen-schnellbuchung.js?v=2.6.4", "embed_iframe": False}]})
    await hass.async_block_till_done()


async def test_hinweis_bei_altem_yaml_eintrag(hass: HomeAssistant):
    await alter_yaml_eintrag(hass)
    eintrag = await einrichten(hass, addons(("local_finanzverwaltung", "started")))
    meldung = ir.async_get(hass).async_get_issue(fv.DOMAIN, fv.MELDUNG_ALT)
    assert meldung is not None and meldung.translation_placeholders == {"adressen": "/schnellbuchung"}
    assert meldung.severity == ir.IssueSeverity.WARNING and "umstieg-vom-yaml-eintrag" in meldung.learn_more_url
    assert panel(hass) is not None and panel(hass, "schnellbuchung") is not None
    assert await hass.config_entries.async_unload(eintrag.entry_id)
    assert ir.async_get(hass).async_get_issue(fv.DOMAIN, fv.MELDUNG_ALT) is None


async def test_hinweis_erst_nach_dem_start_von_home_assistant(hass: HomeAssistant):
    # Beim Hochfahren ist panel_custom aus der YAML eventuell noch nicht da.
    hass.set_state(CoreState.starting)
    eintrag = await einrichten(hass, addons(("local_finanzverwaltung", "started")))
    await panel_custom.async_register_panel(hass, "schnellbuchung", "finanzen-schnellbuchung-panel",
                                            module_url="/local/finanzen-schnellbuchung.js?v=2.6.4")
    assert ir.async_get(hass).async_get_issue(fv.DOMAIN, fv.MELDUNG_ALT) is None
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(fv.DOMAIN, fv.MELDUNG_ALT) is not None
    assert await hass.config_entries.async_unload(eintrag.entry_id)


async def test_kein_hinweis_ohne_alten_eintrag(hass: HomeAssistant):
    await async_setup_component(hass, "panel_custom", {"panel_custom": [{
        "name": "anderes-panel", "url_path": "anderes", "module_url": "/local/anderes.js"}]})
    await einrichten(hass, addons(("local_finanzverwaltung", "started")))
    assert ir.async_get(hass).async_get_issue(fv.DOMAIN, fv.MELDUNG_ALT) is None


def test_alte_eintraege_erkennung():
    p = lambda **k: SimpleNamespace(config={"_panel_custom": k})
    assert fv.alte_eintraege({
        "a": p(name="finanzen-schnellbuchung-panel", module_url="/local/x.js"),
        "b": p(name="eigener-name", module_url="/local/finanzen-schnellbuchung.js?v=2.5"),
        "c": p(name="finanzverwaltung-schnellbuchung", module_url="/finanzverwaltung_dateien/schnellbuchung-panel.js"),
        "d": SimpleNamespace(config=None),
        "e": SimpleNamespace(),
    }) == ["a", "b"]


# --- Dateien und Versionen ---------------------------------------------------

def test_versionen_gleich():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    addon = yaml.safe_load((WURZEL / "finanzverwaltung" / "config.yaml").read_text())
    docker = (WURZEL / "finanzverwaltung" / "Dockerfile").read_text()
    hilfe = (WURZEL / "finanzverwaltung" / "app" / "hilfe" / "hilfe.md").read_text().splitlines()[1]
    assert manifest["version"] == addon["version"]
    assert f'io.hass.version="{manifest["version"]}"' in docker
    assert f'ENV FINANZAPP_VERSION="{manifest["version"]}"' in docker
    assert hilfe == f"Programmversion: {manifest['version']}"


def test_pflichtdateien_fuer_hacs_und_home_assistant():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    for schluessel in ("domain", "name", "codeowners", "documentation", "issue_tracker", "version",
                       "config_flow", "integration_type", "iot_class"):
        assert manifest.get(schluessel) not in (None, ""), schluessel
    assert manifest["domain"] == fv.DOMAIN
    hacs = json.loads((WURZEL / "hacs.json").read_text())
    assert hacs["name"] and hacs["homeassistant"]
    assert [p.name for p in (WURZEL / "custom_components").iterdir() if p.is_dir() and p.name != "__pycache__"] \
        == ["finanzverwaltung"]
    kopf = (INTEGRATION / "brand" / "icon.png").read_bytes()[:24]
    assert kopf[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", kopf[16:24]) == (256, 256)


def test_uebersetzungen_vollstaendig():
    def schluessel(d, p=""):
        return {p + k for k, v in d.items()} | {s for k, v in d.items() if isinstance(v, dict)
                                                 for s in schluessel(v, p + k + ".")}
    de = json.loads((INTEGRATION / "translations" / "de.json").read_text())
    en = json.loads((INTEGRATION / "translations" / "en.json").read_text())
    assert schluessel(de) == schluessel(en)
    assert "{adressen}" in de["issues"][fv.MELDUNG_ALT]["description"]
    assert "{adressen}" in en["issues"][fv.MELDUNG_ALT]["description"]

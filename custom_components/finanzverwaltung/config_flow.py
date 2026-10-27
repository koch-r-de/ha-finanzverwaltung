"""Einrichtung über Einstellungen → Geräte & Dienste. Keine Eingaben nötig."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
try:
    from homeassistant.helpers.hassio import is_hassio
except ImportError:  # ältere Home-Assistant-Versionen
    from homeassistant.components.hassio import is_hassio

from . import DOMAIN


class FinanzverwaltungConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        # Ohne Supervisor gibt es kein Add-on und keine Ingress-Adresse.
        if not is_hassio(self.hass):
            return self.async_abort(reason="kein_supervisor")
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
        return self.async_create_entry(title="Finanzverwaltung", data={})

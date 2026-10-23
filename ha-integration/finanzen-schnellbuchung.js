/*
 * Eigener Seitenleisten-Eintrag "Schnellbuchung" für Home Assistant.
 *
 * Das Add-on liefert die Schnellbuchungsseite unter seiner Ingress-URL
 * aus. Diese URL enthält ein Token, das sich bei Neuinstallation ändert -
 * deshalb wird sie hier zur Laufzeit über die Supervisor-API ermittelt,
 * statt sie fest in die Konfiguration zu schreiben. Damit überlebt der
 * Seitenleisten-Eintrag jede Neuinstallation des Add-ons.
 *
 * Installation: siehe ha-integration/README-HA-Integration.md
 */

// Kennung des Add-ons. Lokal installiert "local_finanzverwaltung", aus einem
// Repository installiert "<kennung>_finanzverwaltung". Seit v2.5 sucht das
// Panel bei Fehlschlag selbst nach einem Add-on, dessen Kennung auf
// "_finanzverwaltung" endet. Nur bei mehreren Treffern hier fest eintragen.
const ADDON_SLUG = "local_finanzverwaltung";

class FinanzenSchnellbuchungPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._geladen) {
      this._geladen = true;
      this._aufbauen();
    }
  }

  connectedCallback() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  async _aufbauen() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100%; background: var(--primary-background-color); }
        .huelle { height: 100%; display: flex; flex-direction: column; }
        iframe { flex: 1; border: 0; width: 100%; }
        .status { padding: 24px; font-family: var(--paper-font-body1_-_font-family, sans-serif);
                  color: var(--primary-text-color); }
        .fehler { color: var(--error-color, #c62828); }
        button { margin-top: 12px; padding: 8px 16px; cursor: pointer; }
      </style>
      <div class="huelle"><div class="status">Schnellbuchung wird geladen …</div></div>`;

    try {
      const info = await this._addonInfo();

      const basis = info && (info.ingress_url || info.ingress_entry);
      if (!basis) throw new Error("Keine Ingress-URL vom Add-on erhalten.");

      const url = basis.replace(/\/+$/, "") + "/schnellbuchung";
      this.shadowRoot.querySelector(".huelle").innerHTML =
        `<iframe src="${url}" allow="clipboard-write"></iframe>`;
    } catch (e) {
      this.shadowRoot.querySelector(".huelle").innerHTML = `
        <div class="status">
          <p class="fehler">Die Schnellbuchung konnte nicht geladen werden.</p>
          <p>${(e && e.message) || e}</p>
          <p>Mögliche Ursachen: Das Add-on läuft nicht, oder seine Kennung wurde nicht gefunden
             (gesucht: <code>${ADDON_SLUG}</code> oder <code>…_finanzverwaltung</code>).</p>
          <button id="erneut">Erneut versuchen</button>
        </div>`;
      const knopf = this.shadowRoot.querySelector("#erneut");
      if (knopf) knopf.addEventListener("click", () => this._aufbauen());
    }
  }
}

FinanzenSchnellbuchungPanel.prototype._addonInfo = async function () {
  const abfrage = (endpoint) => this._hass.callWS({ type: "supervisor/api", endpoint, method: "get" });
  try {
    return await abfrage(`/addons/${ADDON_SLUG}/info`);
  } catch (fehler) {
    const liste = await abfrage("/addons");
    const treffer = ((liste && liste.addons) || []).filter((a) => /_finanzverwaltung$/.test(a.slug || ""));
    if (treffer.length !== 1) throw fehler;
    return abfrage(`/addons/${treffer[0].slug}/info`);
  }
};

customElements.define("finanzen-schnellbuchung-panel", FinanzenSchnellbuchungPanel);

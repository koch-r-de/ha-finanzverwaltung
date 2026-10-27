/*
 * Seitenleisten-Eintrag „Schnellbuchung“ der Finanzverwaltung.
 *
 * Seit 2.7 liefert die Integration custom_components/finanzverwaltung diese
 * Datei aus und trägt das Panel ein. Sie gibt die Kennung des Add-ons in
 * panel.config.kennung mit. Das Panel holt damit die Ingress-Adresse, legt
 * eine Ingress-Sitzung an und bettet die Seite /schnellbuchung des Add-ons
 * ein. Begründungen stehen in finanzverwaltung/DOCS.md.
 *
 * Höhe (2.6.4, Issue #4): Home Assistant gibt dem Behälter eines eigenen
 * Panels keine feste Höhe. Das Panel nimmt die Höhe des Fensters ab seiner
 * Oberkante, per CSS als Rückfall und per Skript genau.
 *
 * Kennung (2.7, Befund S): Ohne Adminrecht erlaubt Home Assistant nur die
 * Abfrage eines namentlich bekannten Add-ons, nicht die Liste aller Add-ons.
 * Die eigene Suche bleibt nur als Rückfall, wenn die Integration keine
 * Kennung liefern konnte.
 *
 * Sitzung (2.7, Befund T): Der Supervisor lässt eine Ingress-Sitzung nach
 * 15 Minuten ohne Anfrage verfallen. Das Panel legt deshalb wie das
 * Add-on-Panel von Home Assistant eine Sitzung an und verlängert sie jede
 * Minute, solange es offen ist, und sofort beim Zurückkehren.
 */
const ELEMENT = "finanzverwaltung-schnellbuchung";
const RUECKFALL_KENNUNG = "local_finanzverwaltung";
const VERLAENGERN_MS = 60000;

class FinanzverwaltungSchnellbuchung extends HTMLElement {
  set panel(panel) { this._panel = panel; }
  get panel() { return this._panel; }

  set hass(hass) {
    this._hass = hass;
    if (!this._geladen) {
      this._geladen = true;
      this._aufbauen();
    }
  }

  connectedCallback() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._hoeheAnpassen = this._hoeheAnpassen || (() => {
      const oben = Math.max(0, this.getBoundingClientRect().top);
      this.style.height = Math.max(200, window.innerHeight - oben) + "px";
    });
    this._sichtbar = this._sichtbar || (() => {
      if (document.visibilityState === "visible") this._pflegeStill();
    });
    window.addEventListener("resize", this._hoeheAnpassen);
    document.addEventListener("visibilitychange", this._sichtbar);
    requestAnimationFrame(this._hoeheAnpassen);
    if (this._kennung) this._pflegeStarten(true);
  }

  disconnectedCallback() {
    if (this._hoeheAnpassen) window.removeEventListener("resize", this._hoeheAnpassen);
    if (this._sichtbar) document.removeEventListener("visibilitychange", this._sichtbar);
    clearInterval(this._takt);
    this._takt = null;
  }

  async _aufbauen() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100vh; height: 100dvh; overflow: hidden;
                background: var(--primary-background-color); }
        .huelle { height: 100%; display: flex; flex-direction: column; }
        iframe { flex: 1 1 auto; min-height: 0; height: 100%; border: 0; width: 100%; display: block; }
        .status { padding: 24px; font-family: var(--paper-font-body1_-_font-family, sans-serif);
                  color: var(--primary-text-color); }
        .fehler { color: var(--error-color, #c62828); }
        button { margin-top: 12px; padding: 8px 16px; cursor: pointer; }
      </style>
      <div class="huelle"><div class="status">Schnellbuchung wird geladen …</div></div>`;

    try {
      const info = await this._addonInfo();
      const basis = info && (info.ingress_url || info.ingress_entry);
      if (!basis) throw new Error("Keine Ingress-Adresse vom Add-on erhalten. Läuft das Add-on?");
      this._kennung = info.slug || this._kennung;
      await this._sitzungPflegen(true);
      this._pflegeStarten(false);

      const url = basis.replace(/\/+$/, "") + "/schnellbuchung";
      this.shadowRoot.querySelector(".huelle").innerHTML =
        `<iframe src="${url}" allow="clipboard-write" title="Schnellbuchung"></iframe>`;
      if (this._hoeheAnpassen) this._hoeheAnpassen();
    } catch (e) {
      const kennung = this.panel && this.panel.config && this.panel.config.kennung;
      this.shadowRoot.querySelector(".huelle").innerHTML = `
        <div class="status">
          <p class="fehler">Die Schnellbuchung konnte nicht geladen werden.</p>
          <p>${this._text(e)}</p>
          <p>${kennung
            ? `Mögliche Ursache: Das Add-on <code>${kennung}</code> läuft nicht.`
            : "Mögliche Ursachen: Das Add-on läuft nicht, ist nicht installiert oder mehrfach installiert. "
              + "Starte Home Assistant nach der Installation des Add-ons einmal neu, damit die Integration es findet."}</p>
          <button id="erneut">Erneut versuchen</button>
        </div>`;
      const knopf = this.shadowRoot.querySelector("#erneut");
      if (knopf) knopf.addEventListener("click", () => this._aufbauen());
    }
  }

  _text(e) {
    const t = (e && (e.message || e.code)) || String(e);
    return t.replace(/[<>&]/g, (z) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[z]));
  }

  async _addonInfo() {
    const abfrage = (endpoint) => this._hass.callWS({ type: "supervisor/api", endpoint, method: "get" });
    const kennung = this.panel && this.panel.config && this.panel.config.kennung;
    if (kennung) {
      this._kennung = kennung;
      return abfrage(`/addons/${kennung}/info`);
    }
    // Rückfall ohne Kennung aus der Integration (Liste nur für Administratoren)
    try {
      return await abfrage(`/addons/${RUECKFALL_KENNUNG}/info`);
    } catch (fehler) {
      const liste = await abfrage("/addons");
      const treffer = ((liste && liste.addons) || []).filter((a) => /_finanzverwaltung$/.test(a.slug || ""));
      if (treffer.length !== 1) throw fehler;
      return abfrage(`/addons/${treffer[0].slug}/info`);
    }
  }

  // Erst den neueren Befehl versuchen, bei unbekanntem Befehl den älteren Weg
  async _ws(neu, alt) {
    try {
      return await this._hass.callWS(neu);
    } catch (fehler) {
      if (fehler && fehler.code === "unknown_command") return this._hass.callWS(alt);
      throw fehler;
    }
  }

  _pflegeStarten(sofortNeu) {
    clearInterval(this._takt);
    this._takt = setInterval(() => this._pflegeStill(), VERLAENGERN_MS);
    if (sofortNeu) this._pflegeStill(true);
  }

  // Im Hintergrund: Ein Fehler wird beim nächsten Takt erneut versucht.
  _pflegeStill(neu = false) {
    this._sitzungPflegen(neu).catch((e) => console.warn("Finanzverwaltung: Ingress-Sitzung", e));
  }

  // Eigene Sitzung verlängern, wenn sie abgelaufen ist eine neue anlegen.
  // „neu“ legt sofort eine an: beim Öffnen und beim Zurückkehren, weil das
  // Add-on-Panel „Finanzen“ dasselbe Cookie mit seiner Sitzung belegt haben
  // kann. Das Cookie gilt nur für /api/hassio_ingress/ und ist hier nicht
  // lesbar, deshalb merkt sich das Panel seine Sitzung selbst.
  async _sitzungPflegen(neu = false) {
    if (!this._hass || !this._kennung) return;
    if (this._pflegeLaeuft) return this._pflegeLaeuft;
    this._pflegeLaeuft = (async () => {
      if (this._sitzung && !neu) {
        try {
          await this._ws({ type: "supervisor/ingress/validate_session", session: this._sitzung },
                         { type: "supervisor/api", endpoint: "/ingress/validate_session", method: "post",
                           data: { session: this._sitzung } });
          return;
        } catch (_) { /* abgelaufen: neue Sitzung */ }
      }
      const antwort = await this._ws({ type: "supervisor/ingress/session", slug: this._kennung },
                                     { type: "supervisor/api", endpoint: "/ingress/session", method: "post" });
      const sitzung = antwort && antwort.session;
      if (!sitzung) throw new Error("Keine Ingress-Sitzung erhalten.");
      this._sitzung = sitzung;
      document.cookie = `ingress_session=${sitzung};path=/api/hassio_ingress/;SameSite=Strict`
        + (location.protocol === "https:" ? ";Secure" : "");
    })();
    try {
      return await this._pflegeLaeuft;
    } finally {
      this._pflegeLaeuft = null;
    }
  }
}

if (!customElements.get(ELEMENT)) customElements.define(ELEMENT, FinanzverwaltungSchnellbuchung);

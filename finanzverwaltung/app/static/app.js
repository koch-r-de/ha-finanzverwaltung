// Private Finanzverwaltung – Frontend-Logik (Vanilla JS, keine Build-Kette)

const API = "api";  // relativ, damit es auch hinter Ingress-Präfixen funktioniert
let KONTEN = [];
let KATEGORIEN = [];
let PERSONEN = [];
let DARLEHEN_AKTIV_ID = null;
let CHART_SALDO, CHART_CASHFLOW, CHART_DARLEHEN, CHART_KATEGORIEN;

// ─── Hilfsfunktionen ──────────────────────────────────────────────

// Seit 3.0 mit dem Token der Sitzung (schutz.js). Greift die Sperre oder ist
// die Datenbank zu, erscheint der Sperrbildschirm, danach wird die Anfrage
// einmal wiederholt.
async function api(pfad, optionen = {}, nochmal = true) {
  const antwort = await fetch(API + pfad, {
    ...optionen,
    headers: { "Content-Type": "application/json", ...schutzKopf(), ...(optionen.headers || {}) },
  });
  if (!antwort.ok) {
    if (nochmal && await schutzBehandeln(antwort)) return api(pfad, optionen, false);
    const text = await antwort.text().catch(() => "");
    throw new Error(`API-Fehler ${antwort.status}: ${text}`);
  }
  const typ = antwort.headers.get("content-type") || "";
  return typ.includes("application/json") ? antwort.json() : null;
}

function euro(n) {
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(n ?? 0);
}

// Lokales Kalenderdatum als ISO-Text (JJJJ-MM-TT). Seit v1.10 bewusst
// NICHT mehr über toISOString(): das liefert UTC und damit zwischen 0 und
// 1 Uhr (Sommerzeit 2 Uhr) deutscher Zeit noch den Vortag.
function datumISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function heuteISO() {
  return datumISO(new Date());
}

// ─── Feiertage (seit v2.6) ────────────────────────────────────────
// Die Regeln stehen nur im Server (feiertage.py). Der Browser lädt die
// Feiertage der gewählten Region jahrweise und prüft Eingaben selbst.
// Nur Hinweis: nichts wird gesperrt oder übersprungen.
const FEIERTAGE_ANFRAGEN = new Map();   // Jahr -> Promise
const FEIERTAGE_GELADEN = new Map();    // Jahr -> Map(ISO-Datum -> {feiertag, bankfeiertag, text})

function feiertageJahr(jahr) {
  if (!FEIERTAGE_ANFRAGEN.has(jahr)) {
    FEIERTAGE_ANFRAGEN.set(jahr, api(`/feiertage?von_jahr=${jahr}&bis_jahr=${jahr}`)
      .then((r) => { const m = new Map(r.tage.map((t) => [t.datum, t])); FEIERTAGE_GELADEN.set(jahr, m); return m; })
      .catch(() => { FEIERTAGE_ANFRAGEN.delete(jahr); return new Map(); }));
  }
  return FEIERTAGE_ANFRAGEN.get(jahr);
}

function feiertagJahrAus(iso) {
  const m = /^(\d{4})-\d{2}-\d{2}$/.exec(String(iso ?? ""));
  const jahr = m ? Number(m[1]) : NaN;
  return jahr >= 1900 && jahr <= 9998 ? jahr : null;
}

async function feiertageVorladen(isoListe) {
  const jahre = new Set(isoListe.map(feiertagJahrAus).filter((j) => j !== null));
  await Promise.all([...jahre].map(feiertageJahr));
}

function feiertagInfo(iso) {
  const jahr = feiertagJahrAus(iso);
  return (jahr && FEIERTAGE_GELADEN.get(jahr)?.get(iso)) || null;
}

function feiertageZuruecksetzen() {
  FEIERTAGE_ANFRAGEN.clear();
  FEIERTAGE_GELADEN.clear();
}

// Symbol in Listen (Buchungsliste mit Vorschau)
function feiertagMarke(iso) {
  const info = feiertagInfo(iso);
  return info ? ` <span class="feiertag-marke" title="${resetEsc(info.text)}" aria-label="${resetEsc(info.text)}">F</span>` : "";
}

// Hinweis direkt unter einem Datumsfeld mit Attribut data-feiertag
async function feiertagHinweisZeigen(feld) {
  let ziel = feld.parentElement.querySelector(":scope > .feiertag-hinweis");
  if (!ziel) {
    ziel = document.createElement("small");
    ziel.className = "feiertag-hinweis";
    ziel.hidden = true;
    feld.insertAdjacentElement("afterend", ziel);
  }
  const wert = feld.value;
  const jahr = feiertagJahrAus(wert);
  if (jahr) await feiertageJahr(jahr);
  if (feld.value !== wert) return;   // inzwischen weiter getippt
  const info = jahr ? feiertagInfo(wert) : null;
  ziel.textContent = info ? info.text : "";
  ziel.hidden = !info;
}

function feiertagHinweiseAktualisieren(wurzel = document) {
  wurzel.querySelectorAll("input[data-feiertag]").forEach(feiertagHinweisZeigen);
}

["input", "change"].forEach((art) => document.addEventListener(art, (e) => {
  if (e.target.matches && e.target.matches("input[data-feiertag]")) feiertagHinweisZeigen(e.target);
}));
// form.reset() setzt Werte ohne input-Ereignis zurück
document.addEventListener("reset", (e) => setTimeout(() => feiertagHinweiseAktualisieren(e.target), 0));

// Hinweise zu Serien nach dem Speichern (Vorlagen, Darlehen, Altersvorsorge)
function serienHinweiseZeigen(elementId, liste) {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (!liste || !liste.length) { el.hidden = true; el.innerHTML = ""; return; }
  el.innerHTML = `${hinweisHtml("feiertage.serie")}<ul>${liste.map((h) => `<li>${resetEsc(h.text)}</li>`).join("")}</ul>`;
  el.hidden = false;
}

// ─── Diagramm-Grundstil (seit v2.3) ───────────────────────────────
// Gilt für alle Diagramme der App: Achse mit „Okt 26“ statt ISO-Datum und
// ohne Schräglage, nur waagrechte blasse Rasterlinien, Legende oben rechts
// als Punkte, ein gemeinsamer Tooltip je Monat, abgerundete Balken.

const MONATE_KURZ = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
const MONATE_LANG = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
  "Oktober", "November", "Dezember"];
const ISO_DATUM = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/;

function achsenDatum(text) {
  const m = ISO_DATUM.exec(String(text ?? ""));
  if (!m) return text;
  if (!m[3] || m[3] === "01") return `${MONATE_KURZ[Number(m[2]) - 1]} ${m[1].slice(2)}`;
  return `${m[3]}.${m[2]}.${m[1].slice(2)}`;
}

function tooltipDatum(text) {
  const m = ISO_DATUM.exec(String(text ?? ""));
  if (!m) return text;
  if (!m[3] || m[3] === "01") return `${MONATE_LANG[Number(m[2]) - 1]} ${m[1]}`;
  return `${m[3]}.${m[2]}.${m[1]}`;
}

function zahlDe(wert, stellen = 2) {
  return Number(wert || 0).toLocaleString("de-DE", { maximumFractionDigits: stellen });
}

function diagrammGrundstil() {
  if (typeof Chart === "undefined") return;
  const D = Chart.defaults;
  const schrift = getComputedStyle(document.documentElement).getPropertyValue("--schrift-text").trim();
  if (schrift) D.font.family = schrift;
  D.font.size = 12;
  D.color = "#16231f99";
  D.borderColor = "#16231f14";
  D.interaction.mode = "index";
  D.interaction.intersect = false;
  Object.assign(D.plugins.legend, { position: "top", align: "end" });
  Object.assign(D.plugins.legend.labels, { usePointStyle: true, pointStyle: "circle", boxWidth: 8, boxHeight: 8, padding: 14 });
  Object.assign(D.plugins.tooltip, { backgroundColor: "#16231f", padding: 10, cornerRadius: 8, boxPadding: 4,
    usePointStyle: true, titleMarginBottom: 6 });
  D.plugins.tooltip.callbacks.title = (eintraege) => (eintraege.length ? tooltipDatum(eintraege[0].label) : "");
  D.elements.bar.borderRadius = 4;
  D.elements.line.borderWidth = 2;
  D.elements.line.cubicInterpolationMode = "monotone";  // geglättet ohne Überschwingen
  D.elements.point.radius = 0;
  D.elements.point.hoverRadius = 4;
  D.set("scales.category", {
    grid: { display: false }, border: { display: false },
    ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 14,
      callback(wert) { return achsenDatum(this.getLabelForValue(wert)); } },
  });
  D.set("scales.linear", { grid: { color: "#16231f12", drawTicks: false }, border: { display: false }, ticks: { padding: 8 } });
}
diagrammGrundstil();

// Senkrechte Linie „heute“, wenn der Zeitraum in der Vergangenheit beginnt
// (options.plugins.heuteLinie.index = Index des laufenden Monats).
const HEUTE_LINIE = {
  id: "heuteLinie",
  afterDatasetsDraw(chart, _args, opt) {
    const i = opt && opt.index;
    if (!i || i <= 0 || i >= chart.data.labels.length) return;
    const x = chart.scales.x.getPixelForValue(i);
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = "#16231f55"; ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = "#16231f99"; ctx.font = `11px ${Chart.defaults.font.family}`;
    ctx.fillText("heute", x + 4, top + 10);
    ctx.restore();
  },
};

// ─── Mehrfachauswahl für Konten und Kategorien (seit v2.3) ────────
// Konten: Liste mit Häkchen. Kategorien: Baum mit Suchfeld, ein Haken an
// einer Oberkategorie setzt alle Unterkategorien, teilweise gewählte
// Oberkategorien zeigen „–“. Gespeichert wird die Menge der einzeln
// gewählten Knoten. Alle gewählt = kein Filter (paramWert() null), keine
// gewählt = leere Auswahl (""). Konten melden Änderungen sofort (kurz
// verzögert), Kategorien beim Schließen der Liste.

class MehrfachAuswahl {
  constructor(el, beiAenderung) {
    this.el = el;
    this.art = el.dataset.art;
    this.beiAenderung = beiAenderung;
    this.auswahl = null;  // null = alle
    this.geaendert = false;
    this.zeitgeber = null;
    el.innerHTML = '<button type="button" class="mehrfach-knopf" aria-haspopup="listbox" aria-expanded="false"></button>'
      + '<div class="mehrfach-liste" hidden></div>';
    this.knopf = el.querySelector(".mehrfach-knopf");
    this.liste = el.querySelector(".mehrfach-liste");
    this.knopf.addEventListener("click", () => (this.liste.hidden ? this.oeffnen() : this.schliessen()));
    document.addEventListener("click", (e) => {
      if (!this.liste.hidden && !el.contains(e.target)) this.schliessen();
    });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !this.liste.hidden) { this.schliessen(); this.knopf.focus(); }
    });
    this.liste.addEventListener("change", (e) => {
      const id = Number(e.target.dataset.id);
      if (!id) return;
      this.umschalten(id);
    });
    this.liste.addEventListener("click", (e) => {
      const aktion = e.target.dataset.aktion;
      if (aktion === "alle") this.setzen(null, true);
      if (aktion === "keine") this.setzen([], true);
    });
    this.liste.addEventListener("input", (e) => {
      if (e.target.classList.contains("mehrfach-suche")) this.suchen(e.target.value);
    });
    this.knopfZeichnen();
  }

  eintraege() {
    if (this.art === "konten") {
      return KONTEN.map((k, i) => ({ id: k.id, name: k.name, parent_id: null, tiefe: 0,
        farbe: k.farbe || KONTEN_FARBSCHEMA[i % KONTEN_FARBSCHEMA.length] }));
    }
    // Kategorien als Baum, ohne den Teilbaum „Umbuchung“ (zählt in keiner Auswertung)
    const liste = [];
    const ast = (parentId, tiefe) => KATEGORIEN
      .filter((k) => k.parent_id === parentId && k.system_key !== "umbuchung")
      .forEach((k) => { liste.push({ id: k.id, name: k.name, parent_id: k.parent_id, tiefe }); ast(k.id, tiefe + 1); });
    ast(null, 0);
    return liste;
  }

  alleIds() { return new Set(this.eintraege().map((e) => e.id)); }

  gewaehlt() {
    const alle = this.alleIds();
    if (this.auswahl === null) return alle;
    return new Set([...this.auswahl].filter((id) => alle.has(id)));
  }

  istAlle() { return this.gewaehlt().size === this.alleIds().size; }

  // Wert für die API: null = kein Filter, "" = nichts gewählt, sonst "1,2,3"
  paramWert() {
    if (this.istAlle()) return null;
    return [...this.gewaehlt()].sort((a, b) => a - b).join(",");
  }

  // Für den Speicher im Browser: null = alle
  speicherWert() { return this.istAlle() ? null : [...this.gewaehlt()]; }

  nachfahren(id) {
    const ergebnis = [];
    const eintraege = this.eintraege();
    const suche = (pid) => eintraege.filter((e) => e.parent_id === pid).forEach((e) => { ergebnis.push(e.id); suche(e.id); });
    suche(id);
    return ergebnis;
  }

  zustand(id, gewaehlt) {
    const gruppe = [id, ...this.nachfahren(id)];
    const an = gruppe.filter((g) => gewaehlt.has(g)).length;
    return an === 0 ? "aus" : an === gruppe.length ? "an" : "teil";
  }

  setzen(ids, melden = false) {
    this.auswahl = ids === null ? null : new Set(ids);
    this.knopfZeichnen();
    if (!this.liste.hidden) this.listeAktualisieren();
    if (melden) this.melden();
  }

  umschalten(id) {
    const gewaehlt = this.gewaehlt();
    const gruppe = this.art === "kategorien" ? [id, ...this.nachfahren(id)] : [id];
    const anschalten = this.art === "kategorien" ? this.zustand(id, gewaehlt) !== "an" : !gewaehlt.has(id);
    gruppe.forEach((g) => (anschalten ? gewaehlt.add(g) : gewaehlt.delete(g)));
    this.setzen([...gewaehlt], true);
  }

  melden() {
    this.geaendert = true;
    if (this.art === "konten") {
      clearTimeout(this.zeitgeber);
      this.zeitgeber = setTimeout(() => this.ausloesen(), 350);
    }
  }

  ausloesen() {
    if (!this.geaendert) return;
    this.geaendert = false;
    if (this.beiAenderung) this.beiAenderung(this);
  }

  oeffnen() {
    this.liste.hidden = false;
    this.knopf.setAttribute("aria-expanded", "true");
    const kat = this.art === "kategorien";
    this.liste.innerHTML = `<div class="mehrfach-aktionen"><button type="button" data-aktion="alle">Alle</button>`
      + `<button type="button" data-aktion="keine">Keine</button></div>`
      + (kat ? '<input type="search" class="mehrfach-suche" placeholder="Kategorie suchen …" autocomplete="off">' : "")
      + this.eintraege().map((e) => `<label class="mehrfach-zeile${kat && e.tiefe === 0 ? " wurzel" : ""}" data-zeile="${e.id}"
          style="padding-left:${6 + e.tiefe * 18}px"><input type="checkbox" data-id="${e.id}">`
          + (e.farbe ? `<span class="mehrfach-punkt" style="background:${e.farbe}"></span>` : "")
          + `<span>${e.name}</span></label>`).join("");
    this.listeAktualisieren();
    const suche = this.liste.querySelector(".mehrfach-suche");
    if (suche) suche.focus();
  }

  schliessen() {
    if (this.liste.hidden) return;
    this.liste.hidden = true;
    this.knopf.setAttribute("aria-expanded", "false");
    clearTimeout(this.zeitgeber);
    this.ausloesen();
  }

  listeAktualisieren() {
    const gewaehlt = this.gewaehlt();
    this.liste.querySelectorAll("input[data-id]").forEach((cb) => {
      const id = Number(cb.dataset.id);
      const z = this.art === "kategorien" ? this.zustand(id, gewaehlt) : (gewaehlt.has(id) ? "an" : "aus");
      cb.checked = z === "an";
      cb.indeterminate = z === "teil";
    });
  }

  suchen(text) {
    const t = text.trim().toLocaleLowerCase("de-DE");
    const eintraege = this.eintraege();
    const nachId = new Map(eintraege.map((e) => [e.id, e]));
    const sichtbar = new Set();
    eintraege.forEach((e) => {
      if (!t || e.name.toLocaleLowerCase("de-DE").includes(t)) {
        let x = e;
        while (x) { sichtbar.add(x.id); x = nachId.get(x.parent_id); }
      }
    });
    this.liste.querySelectorAll("[data-zeile]").forEach((z) => { z.hidden = !sichtbar.has(Number(z.dataset.zeile)); });
  }

  // Oberste gewählte Knoten (deren Oberkategorie nicht gewählt ist)
  gruppen() {
    const gewaehlt = this.gewaehlt();
    return this.eintraege().filter((e) => gewaehlt.has(e.id) && !gewaehlt.has(e.parent_id));
  }

  knopfZeichnen() {
    const alle = this.art === "konten" ? "Alle Konten" : "Alle Kategorien";
    let html;
    let titel = "";
    if (!this.eintraege().length || this.istAlle()) {
      html = `<span class="mehrfach-chip neutral">${alle}</span>`;
    } else if (!this.gewaehlt().size) {
      html = '<span class="mehrfach-chip leer">Keine</span>';
    } else {
      const gruppen = this.art === "konten" ? this.eintraege().filter((e) => this.gewaehlt().has(e.id)) : this.gruppen();
      titel = gruppen.map((g) => g.name).join(", ");
      html = gruppen.slice(0, 2).map((g) => `<span class="mehrfach-chip">`
        + (g.farbe ? `<span class="mehrfach-punkt" style="background:${g.farbe}"></span>` : "") + `${g.name}</span>`).join("")
        + (gruppen.length > 2 ? `<span class="mehrfach-chip neutral">+${gruppen.length - 2}</span>` : "");
    }
    this.knopf.innerHTML = html;
    this.knopf.title = titel;
  }
}

// Instanzen je Filterfeld (werden im jeweiligen Abschnitt angelegt)
const MEHRFACH = {};
function mehrfachNeuZeichnen() {
  Object.values(MEHRFACH).forEach((m) => m.knopfZeichnen());
}

// Filter im Browser merken (seit v2.3). Nur Bequemlichkeit: ohne Speicher
// (privates Fenster, gesperrt) startet die Seite mit den Standardwerten.
function filterLaden(schluessel) {
  try { return JSON.parse(localStorage.getItem(schluessel)) || {}; } catch { return {}; }
}
function filterSpeichern(schluessel, daten) {
  try { localStorage.setItem(schluessel, JSON.stringify(daten)); } catch { /* ohne Speicher weiter */ }
}

// Umschaltknöpfe für Auswahllisten (seit v2.3): <div class="segment"
// data-segment-fuer="id"> zeigt die Optionen der versteckten Auswahl als
// Knöpfe. Die Auswahl bleibt die Quelle, ihr change-Ereignis wird ausgelöst.
function segmenteAufbauen() {
  document.querySelectorAll(".segment[data-segment-fuer]").forEach((seg) => {
    const sel = document.getElementById(seg.dataset.segmentFuer);
    seg.innerHTML = [...sel.options].map((o) => `<button type="button" data-wert="${o.value}">${o.textContent}</button>`).join("");
    const markieren = () => seg.querySelectorAll("button").forEach((b) => b.classList.toggle("an", b.dataset.wert === sel.value));
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || b.dataset.wert === sel.value) return;
      sel.value = b.dataset.wert;
      sel.dispatchEvent(new Event("change"));
    });
    sel.addEventListener("change", markieren);
    markieren();
  });
}

// Schalter "Inflation einrechnen" (seit v2.0, je Seite, Standard aus) als
// Abfrageparameter für die Prognose-Endpunkte.
function inflationParam(id) {
  return document.getElementById(id)?.checked ? "&inflation=true" : "";
}

function formularZuObjekt(form) {
  const daten = new FormData(form);
  const obj = {};
  for (const [key, val] of daten.entries()) obj[key] = val;
  form.querySelectorAll('input[type="checkbox"]').forEach((cb) => (obj[cb.name] = cb.checked));
  return obj;
}

function el(html) {
  const div = document.createElement("div");
  div.innerHTML = html.trim();
  return div.firstChild;
}

// ─── Passwort-Manager von Nicht-Login-Feldern fernhalten (seit v1.8) ──
// Datumsfelder (und die Bestätigungsphrase beim Zurücksetzen) werden von
// manchen Passwort-Managern für Login-/Kennwortfelder gehalten. Die
// Attribute markieren sie für die gängigen Manager ausdrücklich als
// "nicht ausfüllen": autocomplete (Browser), data-1p-ignore (1Password),
// data-lpignore (LastPass), data-bwignore (Bitwarden), data-form-type
// (Dashlane). Ein MutationObserver erfasst auch später per JavaScript
// erzeugte Felder (z. B. im Zurücksetzen-Dialog).
// Seit v1.10 auch das Namensfeld der Kategorien (Anlegen und Ändern).
const KEIN_PASSWORT_FELD = 'input[type="date"], input[type="month"], #reset-phrase-eingabe, #wh-phrase-eingabe, '
  + '#form-kategorie input[name="name"], #schutz-dialog input, .schutz-formular input';

function passwortManagerFernhalten(wurzel = document) {
  const felder = wurzel.matches?.(KEIN_PASSWORT_FELD) ? [wurzel] : [];
  wurzel.querySelectorAll?.(KEIN_PASSWORT_FELD).forEach((f) => felder.push(f));
  felder.forEach((f) => {
    // Seit v1.9: vierstellige Jahreszahl erzwingen (ohne max lässt der
    // Browser fünf- und sechsstellige Jahre zu). Der Server prüft zusätzlich.
    if (f.type === "date") { f.min = f.min || "1900-01-01"; f.max = f.max || "9999-12-31"; }
    if (f.type === "month") { f.min = f.min || "1900-01"; f.max = f.max || "9999-12"; }
    f.setAttribute("autocomplete", "off");
    f.setAttribute("data-1p-ignore", "");
    f.setAttribute("data-lpignore", "true");
    f.setAttribute("data-bwignore", "");
    f.setAttribute("data-form-type", "other");
  });
}

passwortManagerFernhalten();
new MutationObserver((aenderungen) => aenderungen.forEach((a) =>
  a.addedNodes.forEach((k) => { if (k.nodeType === 1) passwortManagerFernhalten(k); })
)).observe(document.body, { childList: true, subtree: true });

// ─── GUI-Theme-Farben (Administration → System → "Farben") ─────────
// Konfigurierbar sind nur die fünf "Leitfarben"; abgeleitete Zwischentöne
// (--grundton-dunkel, --messing-hell, --papier-karte) werden rein rechnerisch
// aus ihnen erzeugt, statt einzeln gespeichert zu werden - so bleiben sie
// immer stimmig zur gewählten Leitfarbe.
const THEME_FARBEN_FELDER = ["farbe_grundton", "farbe_messing", "farbe_gruen", "farbe_rot", "farbe_papier"];
const THEME_CSS_VAR = {
  farbe_grundton: "--grundton", farbe_messing: "--messing",
  farbe_gruen: "--gruen", farbe_rot: "--rot", farbe_papier: "--papier",
};

function cssVarWert(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Mischt eine #rrggbb-Farbe mit einer Zielfarbe (z. B. Schwarz zum
// Abdunkeln, Weiß zum Aufhellen) im gegebenen Verhältnis (0..1).
function hexMischen(hex, ziel, anteil) {
  const zuRgb = (h) => {
    const n = h.replace("#", "");
    return [parseInt(n.slice(0, 2), 16), parseInt(n.slice(2, 4), 16), parseInt(n.slice(4, 6), 16)];
  };
  const [r1, g1, b1] = zuRgb(hex);
  const [r2, g2, b2] = zuRgb(ziel);
  const mischen = (a, b) => Math.round(a + (b - a) * anteil);
  const zuHex = (n) => n.toString(16).padStart(2, "0");
  return `#${zuHex(mischen(r1, r2))}${zuHex(mischen(g1, g2))}${zuHex(mischen(b1, b2))}`;
}

// Wendet gespeicherte (nicht-leere) Farb-Einstellungen als CSS-Custom-
// Properties auf <html> an - überschreibt die Standardwerte aus :root in
// style.css. Wird sowohl beim App-Start als auch direkt nach dem Speichern
// im Admin-Formular aufgerufen.
function themeFarbenAnwenden(einstellungen) {
  const root = document.documentElement.style;
  if (einstellungen.farbe_grundton) {
    root.setProperty("--grundton", einstellungen.farbe_grundton);
    root.setProperty("--grundton-dunkel", hexMischen(einstellungen.farbe_grundton, "#000000", 0.35));
  }
  if (einstellungen.farbe_messing) {
    root.setProperty("--messing", einstellungen.farbe_messing);
    root.setProperty("--messing-hell", hexMischen(einstellungen.farbe_messing, "#ffffff", 0.65));
  }
  if (einstellungen.farbe_gruen) root.setProperty("--gruen", einstellungen.farbe_gruen);
  if (einstellungen.farbe_rot) root.setProperty("--rot", einstellungen.farbe_rot);
  if (einstellungen.farbe_papier) {
    root.setProperty("--papier", einstellungen.farbe_papier);
    root.setProperty("--papier-karte", hexMischen(einstellungen.farbe_papier, "#ffffff", 0.55));
  }
}

function themeFarbenZuruecksetzenLokal() {
  const root = document.documentElement.style;
  ["--grundton", "--grundton-dunkel", "--messing", "--messing-hell", "--gruen", "--rot",
   "--papier", "--papier-karte"].forEach((v) => root.removeProperty(v));
}

async function ladeThemeFarbenFormular() {
  const es = await api("/admin/einstellungen");
  const form = document.getElementById("form-theme-farben");
  THEME_FARBEN_FELDER.forEach((feld) => {
    form[feld].value = es[feld] || cssVarWert(THEME_CSS_VAR[feld]);
  });
}

document.getElementById("form-theme-farben").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  for (const feld of THEME_FARBEN_FELDER) {
    await api(`/admin/einstellungen/${feld}?value=${encodeURIComponent(d[feld])}`, { method: "PUT" });
  }
  themeFarbenAnwenden(d);
});

document.getElementById("theme-farben-zuruecksetzen").addEventListener("click", async () => {
  if (!confirm("Alle Farben auf den eingebauten Standard zurücksetzen?")) return;
  for (const feld of THEME_FARBEN_FELDER) {
    await api(`/admin/einstellungen/${feld}?value=`, { method: "PUT" });
  }
  themeFarbenZuruecksetzenLokal();
  await ladeThemeFarbenFormular();
});

// ─── Navigation ───────────────────────────────────────────────────

// Icon-/Label-Nachschlage für alle Menüpunkte außer "start" und "admin"
// (die bleiben fest in der Sidebar-HTML). Wird sowohl beim Rendern der
// Sidebar selbst als auch im Reihenfolge-Editor (Administration) benutzt.
const NAV_ICONS = {
  konten: '<rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>',
  buchungen: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
  wiederkehrend: '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
  plan: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  budgets: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
  darlehen: '<line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
  altersvorsorge: '<path d="M12 2 4 5v6c0 5.55 3.84 10.74 8 12 4.16-1.26 8-6.45 8-12V5l-8-3z"/>',
  auswertungen: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
  jahr: '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
};
const NAV_LABELS = {
  konten: "Konten", buchungen: "Buchungen", wiederkehrend: "Wiederkehrend",
  plan: "Plan-Buchungen", budgets: "Budgets", darlehen: "Darlehen",
  altersvorsorge: "Altersvorsorge", auswertungen: "Auswertungen", jahr: "Jahresübersicht",
};
// Muss mit dem Default in schema.sql (einstellungen.nav_reihenfolge) übereinstimmen -
// nur als Rückfallebene gedacht, falls die Einstellung mal fehlt/kaputt ist.
const NAV_REIHENFOLGE_STANDARD = [
  { ziel: "konten", trenner_davor: false },
  { ziel: "buchungen", trenner_davor: true },
  { ziel: "wiederkehrend", trenner_davor: false },
  { ziel: "plan", trenner_davor: false },
  { ziel: "budgets", trenner_davor: false },
  { ziel: "altersvorsorge", trenner_davor: false },
  { ziel: "darlehen", trenner_davor: false },
  { ziel: "auswertungen", trenner_davor: true },
  { ziel: "jahr", trenner_davor: false },
];

function navEintragHtml(ziel) {
  return `<li><button class="nav-eintrag" data-ziel="${ziel}"><svg class="nav-symbol" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${NAV_ICONS[ziel]}</svg> ${NAV_LABELS[ziel]}</button></li>`;
}

async function ladeNavReihenfolge() {
  try {
    const es = await api("/admin/einstellungen");
    const config = JSON.parse(es.nav_reihenfolge || "[]");
    if (Array.isArray(config) && config.length) return config;
  } catch (e) { /* fällt auf Standard zurück */ }
  return NAV_REIHENFOLGE_STANDARD;
}

async function renderNavigation() {
  const config = await ladeNavReihenfolge();
  const liste = document.getElementById("nav-liste-haupt");
  // Start-Eintrag steht schon im DOM (statisches HTML, fix an erster Stelle) - übernehmen statt neu zu bauen.
  const startLi = liste.querySelector('[data-ziel="start"]')?.closest("li");
  let html = startLi ? startLi.outerHTML : "";
  config.forEach((eintrag) => {
    if (!NAV_LABELS[eintrag.ziel]) return; // unbekanntes Ziel (z. B. altes Format) überspringen
    if (eintrag.trenner_davor) html += '<li class="nav-trenner" role="separator"></li>';
    html += navEintragHtml(eintrag.ziel);
  });
  liste.innerHTML = html;
}

// Ein einziger, delegierter Klick-Listener statt individueller Bindungen -
// überlebt das dynamische Neu-Rendern der Sidebar (renderNavigation()).
document.querySelector("nav.seitenleiste").addEventListener("click", (e) => {
  const btn = e.target.closest(".nav-eintrag");
  if (btn) zeigeAbschnitt(btn.dataset.ziel);
});

function zeigeAbschnitt(ziel) {
  document.querySelectorAll(".abschnitt").forEach((s) => s.classList.remove("aktiv"));
  document.querySelectorAll(".nav-eintrag").forEach((b) => b.classList.remove("aktiv"));
  document.getElementById("abschnitt-" + ziel).classList.add("aktiv");
  document.querySelector(`.nav-eintrag[data-ziel="${ziel}"]`).classList.add("aktiv");
  const lader = { start: ladeStart, konten: ladeKontenAbschnitt, buchungen: ladeBuchungenAbschnitt,
    wiederkehrend: ladeWiederkehrendAbschnitt, plan: ladePlanAbschnitt,
    budgets: ladeBudgetAbschnitt, darlehen: ladeDarlehenAbschnitt,
    altersvorsorge: ladeAltersvorsorgeAbschnitt,
    auswertungen: ladeAuswertungenAbschnitt, jahr: ladeJahrAbschnitt,
    admin: ladeAdminAbschnitt, hilfe: ladeHilfeAbschnitt }[ziel];
  return lader ? lader() : Promise.resolve();
}

// ─── Gemeinsame Daten (Konten / Kategorien) ───────────────────────

async function ladeKonten() {
  KONTEN = await api("/konten");
  document.querySelectorAll(".konto-auswahl").forEach((sel) => {
    const bisher = sel.value;
    const vorherigeErsteOption = sel.querySelector('option[value=""]')?.outerHTML || "";
    sel.innerHTML = vorherigeErsteOption + KONTEN.map((k) => `<option value="${k.id}">${k.name}</option>`).join("");
    if (bisher) sel.value = bisher;
  });
  mehrfachNeuZeichnen();
}

async function ladePersonen() {
  // Immer alle (auch deaktivierte) laden, damit personName() für bereits
  // zugeordnete, inzwischen deaktivierte Personen weiterhin den echten
  // Namen anzeigt statt "–". Auswahlfelder (Formulare/Filter) zeigen
  // trotzdem nur aktive Personen zur Auswahl an.
  PERSONEN = await api("/personen?nur_aktive=false");
  const aktive = PERSONEN.filter((p) => p.aktiv);
  document.querySelectorAll(".person-auswahl").forEach((sel) => {
    const bisher = sel.value;
    const vorherigeErsteOption = sel.querySelector('option[value=""]')?.outerHTML || "";
    sel.innerHTML = vorherigeErsteOption + aktive.map((p) => `<option value="${p.id}">${p.name}</option>`).join("");
    if (bisher) sel.value = bisher;
  });
}

function personName(id) {
  if (!id) return "–";
  const p = PERSONEN.find((x) => x.id === id);
  return p ? p.name : "–";
}

function kategorieName(id) {
  const k = KATEGORIEN.find((x) => x.id === id);
  return k ? k.name : "–";
}

function kategoriePfad(id) {
  const k = KATEGORIEN.find((x) => x.id === id);
  if (!k) return "–";
  return k.parent_id ? `${kategoriePfad(k.parent_id)} → ${k.name}` : k.name;
}

async function ladeKategorien() {
  KATEGORIEN = await api("/kategorien");
  // ohneUmbuchung: Teilbaum der Systemkategorie "Umbuchung" auslassen (seit
  // v1.10 im Vorlagen-Formular, Auswahlfelder mit data-ohne-umbuchung).
  const optionen = (parentId, praefix, ohneUmbuchung) =>
    KATEGORIEN.filter((k) => k.parent_id === parentId && !(ohneUmbuchung && k.system_key === "umbuchung"))
      .flatMap((k) => [`<option value="${k.id}">${praefix}${k.name}</option>`,
                       ...optionen(k.id, praefix + "— ", ohneUmbuchung)])
      .join("");
  document.querySelectorAll(".kategorie-auswahl").forEach((sel) => {
    const vorherigeErsteOption = sel.querySelector('option[value=""]')?.outerHTML || "";
    sel.innerHTML = vorherigeErsteOption + optionen(null, "", sel.hasAttribute("data-ohne-umbuchung"));
  });
  mehrfachNeuZeichnen();
}

// ─── Start ────────────────────────────────────────────────────────

async function ladeStart() {
  document.getElementById("start-stempel").textContent = "Stand " +
    new Date().toLocaleDateString("de-DE");
  await ladeKonten();

  const gesamtsaldo = KONTEN.filter((k) => k.in_gesamtsaldo).reduce((summe, k) => summe + k.saldo, 0);
  document.getElementById("start-gesamtsaldo").innerHTML = `
    <div class="etikett">Gesamtsaldo</div>
    <div class="betrag zahl ${gesamtsaldo < 0 ? "negativ" : "positiv"}">${euro(gesamtsaldo)}</div>`;

  const karten = document.getElementById("start-konten-karten");
  const aufteilungen = await Promise.all(KONTEN.map((k) =>
    api(`/konten/${k.id}/aufteilung`).catch(() => null)));
  karten.innerHTML = KONTEN.map((k, i) => {
    const a = aufteilungen[i];
    const ziele = (a && a.sparziele) || [];
    return `
    <div class="karte">
      <div class="etikett">${k.name} · ${k.typ}</div>
      <div class="betrag zahl ${k.saldo < 0 ? "negativ" : "positiv"}">${euro(k.saldo)}</div>
      ${ziele.length ? `<div class="hinweis" style="margin-top:6px; border-top:1px solid var(--linie); padding-top:6px">
          ${ziele.map((z) => `${z.name}: ${euro(z.ist)}`).join("<br>")}
          <br><strong>Frei verfügbar: <span class="${a.rest < 0 ? "negativ" : "positiv"}">${euro(a.rest)}</span></strong>
        </div>` : ""}
    </div>`;
  }).join("") || '<p class="leer">Noch keine Konten angelegt.</p>';

  const letzte = await api("/buchungen");
  const juengste = letzte.slice(-8).reverse();
  document.getElementById("start-letzte-buchungen").innerHTML = juengste.length
    ? `<table><thead><tr><th>Datum</th><th>Beschreibung</th><th class="rechts">Betrag</th></tr></thead><tbody>
        ${juengste.map((b) => `<tr><td>${b.datum}</td><td>${b.beschreibung || "–"}</td>
          <td class="rechts zahl ${b.betrag < 0 ? "negativ" : "positiv"}">${euro(b.betrag)}</td></tr>`).join("")}
      </tbody></table>`
    : '<p class="leer">Noch keine Buchungen vorhanden.</p>';
}

// ─── Konten-Abschnitt ─────────────────────────────────────────────

async function ladeKontenAbschnitt() {
  saldoKorrekturDatumVorbelegen();
  await Promise.all([ladeKonten(), ladePersonen()]);
  await renderKontenTabelle();
}

document.getElementById("konten-filter-person").addEventListener("change", renderKontenTabelle);

// Effektive Kontofarbe: eigene Farbe, falls gesetzt - sonst dieselbe
// automatische Zuordnung aus der 14er-Palette wie im Saldo-Verlauf-Diagramm
// (Reihenfolge/Index dort und hier identisch, da beide auf derselben
// nach Name sortierten Kontenliste basieren).
function kontoFarbe(k, i) {
  return k.farbe || KONTEN_FARBSCHEMA[i % KONTEN_FARBSCHEMA.length];
}

async function renderKontenTabelle() {
  const personFilter = document.getElementById("konten-filter-person").value;
  const liste = personFilter ? KONTEN.filter((k) => String(k.person_id) === personFilter) : KONTEN;
  document.getElementById("konten-tabelle").innerHTML = liste.map((k, i) => `
    <tr><td><span title="${k.farbe ? "Eigene Farbe" : "Automatisch zugeordnet"}"
              style="display:inline-block; width:10px; height:10px; border-radius:50%;
                     background:${kontoFarbe(k, i)}"></span></td>
    <td>${k.name}</td><td>${k.typ}</td><td>${personName(k.person_id)}</td><td>${k.eroeffnungsdatum}</td>
    <td>${k.in_gesamtsaldo ? "Ja" : "Nein"}</td>
    <td class="rechts zahl ${k.saldo < 0 ? "negativ" : "positiv"}">${euro(k.saldo)}</td>
    <td><button class="knopf sekundaer klein" onclick="kontoBearbeiten(${k.id})">Ändern</button></td></tr>`).join("")
    || `<tr><td colspan="8" class="leer">Keine Konten</td></tr>`;
}

document.getElementById("konto-farbe-aktiv").addEventListener("change", (e) => {
  document.getElementById("konto-farbe-feld").style.display = e.target.checked ? "block" : "none";
});

document.getElementById("form-konto").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  const koerper = JSON.stringify({
    name: d.name, typ: d.typ, eroeffnungsdatum: d.eroeffnungsdatum,
    person_id: d.person_id ? Number(d.person_id) : null,
    in_gesamtsaldo: !!d.in_gesamtsaldo,
    farbe: d.farbe_aktiv ? d.farbe : null,
  });
  const id = e.target.dataset.bearbeitetId;
  if (id) {
    await api(`/konten/${id}`, { method: "PUT", body: koerper });
  } else {
    await api("/konten", { method: "POST", body: koerper });
  }
  kontoFormularZuruecksetzen();
  await ladeKontenAbschnitt();
});

async function kontoBearbeiten(id) {
  const k = KONTEN.find((x) => x.id === id);
  if (!k) return;
  const form = document.getElementById("form-konto");
  form.name.value = k.name;
  form.typ.value = k.typ;
  form.eroeffnungsdatum.value = k.eroeffnungsdatum;
  form.person_id.value = k.person_id || "";
  form.in_gesamtsaldo.checked = !!k.in_gesamtsaldo;
  form.farbe_aktiv.checked = !!k.farbe;
  form.farbe.value = k.farbe || "#2f7d4f";
  document.getElementById("konto-farbe-feld").style.display = k.farbe ? "block" : "none";
  form.dataset.bearbeitetId = id;
  document.getElementById("konto-form-titel").textContent = "Konto ändern";
  document.getElementById("konto-submit").textContent = "Änderung speichern";
  document.getElementById("konto-verwerfen").style.display = "inline-block";
  form.scrollIntoView({ behavior: "smooth" });
}

function kontoFormularZuruecksetzen() {
  const form = document.getElementById("form-konto");
  form.reset();
  delete form.dataset.bearbeitetId;
  document.getElementById("konto-form-titel").textContent = "Neues Konto";
  document.getElementById("konto-submit").textContent = "Anlegen";
  document.getElementById("konto-verwerfen").style.display = "none";
  document.getElementById("konto-farbe-feld").style.display = "none";
}

document.getElementById("konto-verwerfen").addEventListener("click", kontoFormularZuruecksetzen);

// Saldo-Korrektur: Datum mit heute vorbelegen (seit v1.10). Als
// defaultValue gesetzt, damit form.reset() die Vorbelegung wiederherstellt;
// bei jedem Öffnen des Abschnitts und nach dem Absenden neu, damit sie auch
// über Mitternacht hinweg stimmt.
function datumMitHeuteVorbelegen(selektor) {
  const feld = document.querySelector(selektor);
  const leer = !feld.value || feld.value === feld.defaultValue;
  feld.defaultValue = heuteISO();
  if (leer) feld.value = feld.defaultValue;
  feiertagHinweisZeigen(feld);
}

function saldoKorrekturDatumVorbelegen() {
  datumMitHeuteVorbelegen('#form-saldo-korrektur [name="datum"]');
  // Seit v2.0 keine Saldo-Korrektur in der Zukunft (Server prüft ebenfalls).
  document.querySelector('#form-saldo-korrektur [name="datum"]').max = heuteISO();
}

// Buchungsformular ebenso (seit v1.10, Befund C).
function buchungDatumVorbelegen() {
  datumMitHeuteVorbelegen('#form-buchung [name="datum"]');
}

document.getElementById("form-saldo-korrektur").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  await api("/saldo-korrekturen", { method: "POST", body: JSON.stringify({
    konto_id: Number(d.konto_id), datum: d.datum, saldo: Number(d.saldo), kommentar: d.kommentar || null,
  })});
  saldoKorrekturDatumVorbelegen();
  e.target.reset();
  await ladeKontenAbschnitt();
});

// ─── Buchungen-Abschnitt ──────────────────────────────────────────

document.getElementById("buchung-typ").addEventListener("change", (e) => {
  const istUebertragung = e.target.value === "Uebertragung";
  document.getElementById("ziel-konto-feld").style.display = istUebertragung ? "block" : "none";
  document.getElementById("kategorie-feld").style.display = istUebertragung ? "none" : "block";
  document.querySelector('#form-buchung [name="kategorie_id"]').required = !istUebertragung;
  document.getElementById("betrag-label").textContent = istUebertragung ? "Betrag (€, ohne Vorzeichen)" : "Betrag (€)";
  document.getElementById("sparziel-feld").style.display = istUebertragung ? "block" : "none";
  buchungSparzieleFiltern();
});

async function ladeBuchungenAbschnitt() {
  buchungDatumVorbelegen();
  await Promise.all([ladeKonten(), ladeKategorien(), ladePersonen()]);
  await renderBuchungenTabelle();
}

["buchungen-filter-konto", "buchungen-filter-person", "buchungen-filter-herkunft", "buchungen-inflation"].forEach((id) =>
  document.getElementById(id).addEventListener("change", renderBuchungenTabelle));

const HERKUNFT_PARAM = {
  "": {},
  "ist-manuell": { herkunft: "manuell", typ: "Ist" },
  "plan-manuell": { herkunft: "manuell", typ: "Plan" },
  "wiederkehrend": { herkunft: "wiederkehrend" },
  "anstehend": { inkl_anstehende: "true" },
};

async function renderBuchungenTabelle() {
  const kontoId = document.getElementById("buchungen-filter-konto").value;
  const personId = document.getElementById("buchungen-filter-person").value;
  const auswahl = document.getElementById("buchungen-filter-herkunft").value;
  const params = new URLSearchParams(HERKUNFT_PARAM[auswahl] || {});
  if (kontoId) params.set("konto_id", kontoId);
  if (personId) params.set("person_id", personId);
  if (document.getElementById("buchungen-inflation").checked) params.set("inflation", "true");
  const liste = await api(`/buchungen?${params.toString()}`);
  const sortiert = liste.slice().sort((a, b) => (a.datum < b.datum ? 1 : -1));
  await feiertageVorladen(sortiert.map((b) => b.datum));

  document.getElementById("buchungen-tabelle").innerHTML = sortiert.map((b) => {
    const konto = KONTEN.find((k) => k.id === b.konto_id);
    // Seit v1.10: Übertragungen zeigen "Quelle → Ziel".
    const ziel = b.zielkonto_id ? KONTEN.find((k) => k.id === b.zielkonto_id) : null;
    const kontoText = (konto ? konto.name : "–") + (b.zielkonto_id ? ` → ${ziel ? ziel.name : "–"}` : "");
    const herkunft = b.virtuell ? "anstehend"
      : b.wiederkehrend_id ? "Vorlage" : b.ziel_altersvorsorge_id ? "Altersvorsorge"
      : b.ziel_darlehen_id ? "Darlehen" : "manuell";
    return `<tr${b.virtuell ? ' style="opacity:.72"' : ""}>
      <td>${b.datum}${feiertagMarke(b.datum)}</td>
      <td>${kontoText}</td>
      <td>${kategoriePfad(b.kategorie_id)}</td>
      <td><span class="abzeichen ${b.typ.toLowerCase()}">${b.typ}</span></td>
      <td><span class="hinweis">${herkunft}</span></td>
      <td>${b.beschreibung || "–"}</td>
      <td class="rechts zahl ${b.betrag < 0 ? "negativ" : "positiv"}">${euro(b.betrag)}</td>
      <td class="reihen-werkzeuge">${b.virtuell ? '<span class="hinweis">geplant</span>' :
        `<button class="knopf sekundaer klein" onclick="buchungBearbeiten(${b.id})">Ändern</button>
         <button class="knopf gefahr klein" onclick="loescheBuchung(${b.id})">Löschen</button>`}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="8" class="leer">Keine Buchungen</td></tr>`;
}

async function loescheBuchung(id) {
  if (!confirm("Buchung wirklich löschen?")) return;
  await api(`/buchungen/${id}`, { method: "DELETE" });
  await renderBuchungenTabelle();
  await ladeKonten();
}

async function buchungBearbeiten(id) {
  const b = await api(`/buchungen/${id}`);
  const form = document.getElementById("form-buchung");
  form.konto_id.value = b.konto_id;
  form.typ.value = b.typ;
  form.datum.value = b.datum;
  feiertagHinweisZeigen(form.datum);
  form.betrag.value = Math.abs(b.betrag);
  if (b.kategorie_id) form.kategorie_id.value = b.kategorie_id;
  form.beschreibung.value = b.beschreibung || "";
  if (b.zielkonto_id) form.zielkonto_id.value = b.zielkonto_id;
  form.typ.dispatchEvent(new Event("change"));
  form.sparziel_id.value = b.sparziel_id || "";
  form.dataset.bearbeitetId = id;
  document.getElementById("buchung-submit").textContent = "Änderung speichern";
  document.getElementById("buchung-verwerfen").style.display = "inline-block";
  document.getElementById("buchung-hinweis").textContent =
    "Betrag bitte positiv eingeben – das Vorzeichen wird aus der Kategorie abgeleitet.";
  form.scrollIntoView({ behavior: "smooth" });
}

function buchungFormularZuruecksetzen() {
  const form = document.getElementById("form-buchung");
  buchungDatumVorbelegen();
  form.reset();
  delete form.dataset.bearbeitetId;
  document.getElementById("buchung-submit").textContent = "Buchen";
  document.getElementById("buchung-verwerfen").style.display = "none";
  document.getElementById("buchung-hinweis").textContent = "";
  document.getElementById("ziel-konto-feld").style.display = "none";
  document.getElementById("kategorie-feld").style.display = "block";
  document.getElementById("sparziel-feld").style.display = "none";
}

document.getElementById("buchung-verwerfen").addEventListener("click", buchungFormularZuruecksetzen);

document.getElementById("form-buchung").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  const koerper = JSON.stringify({
    konto_id: Number(d.konto_id), datum: d.datum, betrag: Number(d.betrag),
    kategorie_id: d.typ === "Uebertragung" ? null : (d.kategorie_id ? Number(d.kategorie_id) : null),
    typ: d.typ, beschreibung: d.beschreibung || null,
    // Zielkonto nur bei Übertragungen (seit 2.6.1, Befund P: das verborgene
    // Auswahlfeld hat immer einen Wert)
    zielkonto_id: d.typ === "Uebertragung" && d.zielkonto_id ? Number(d.zielkonto_id) : null,
    // Sparziel nur bei Übertragungen (seit v2.0, Server prüft ebenfalls)
    sparziel_id: d.typ === "Uebertragung" && d.sparziel_id ? Number(d.sparziel_id) : null,
  });
  const id = e.target.dataset.bearbeitetId;
  const antwort = id
    ? await api(`/buchungen/${id}`, { method: "PUT", body: koerper })
    : await api("/buchungen", { method: "POST", body: koerper });

  const hinweise = [];
  if (antwort && antwort.auto_kategorie) {
    const k = KATEGORIEN.find((x) => x.id === antwort.auto_kategorie);
    hinweise.push(`Kategorie automatisch erkannt: ${k ? k.name : "–"}`);
  }
  if (antwort && antwort.duplikat) {
    hinweise.push(`Achtung: Am ${antwort.duplikat.datum} ist auf diesem Konto bereits ein
      gleicher Betrag gebucht („${antwort.duplikat.beschreibung || "ohne Beschreibung"}“).`);
  }
  buchungFormularZuruecksetzen();
  document.getElementById("buchung-hinweis").innerHTML = hinweise.join("<br>");
  await renderBuchungenTabelle();
  await ladeKonten();
});

// ─── Wiederkehrende Buchungen ─────────────────────────────────────

let WK_LISTE = [];
let WK_SORT = { spalte: "beschreibung", auf: true };

async function ladeWiederkehrendAbschnitt() {
  await Promise.all([ladeKonten(), ladeKategorien(), ladePersonen(), wkSparzieleLaden()]);
  wkArtAnwenden();
  await renderWiederkehrendTabelle();
}

document.getElementById("wk-inflation").addEventListener("change", () => {});

// ─── Umbuchungs-Vorlagen (seit v1.10) ──
// Art "Umbuchung": Zielkonto statt Kategorie (fest "Umbuchung", setzt der
// Server), Betrag ohne Vorzeichen, weder Inflation noch Dynamik, optional
// ein Sparziel - wie eine manuelle Übertragung im Buchungsformular.
async function wkSparzieleLaden() {
  SPARZIELE = await api("/sparziele").catch(() => []);
  wkSparzieleFiltern();
}

function wkSparzieleFiltern() {
  const f = document.getElementById("form-wiederkehrend");
  sparzieleFiltern(f.sparziel_id, [f.konto_id.value, f.zielkonto_id.value]);
}

["konto_id", "zielkonto_id"].forEach((n) =>
  document.querySelector(`#form-wiederkehrend [name="${n}"]`).addEventListener("change", wkSparzieleFiltern));

function wkIstUmbuchung() {
  return document.getElementById("wk-art").value === "umbuchung";
}

function wkArtAnwenden() {
  const umbuchung = wkIstUmbuchung();
  const form = document.getElementById("form-wiederkehrend");
  document.getElementById("wk-zielkonto-feld").style.display = umbuchung ? "block" : "none";
  document.getElementById("wk-sparziel-feld").style.display = umbuchung ? "block" : "none";
  document.getElementById("wk-kategorie-feld").style.display = umbuchung ? "none" : "block";
  document.getElementById("wk-inflation-feld").style.display = umbuchung ? "none" : "block";
  form.kategorie_id.required = !umbuchung;
  form.zielkonto_id.required = umbuchung;
  if (umbuchung) form.inflationsflag.checked = false;
  document.getElementById("wk-betrag-label").textContent = umbuchung ? "Betrag (€, ohne Vorzeichen)" : "Betrag (€)";
  // Alt-Dynamik wird bei Umbuchungen nicht übernommen (Server setzt sie auf 0).
  const dynamik = document.getElementById("wk-dynamik-hidden").value === "1";
  document.getElementById("wk-dynamik-hinweis").style.display = dynamik && !umbuchung ? "block" : "none";
}

document.getElementById("wk-art").addEventListener("change", wkArtAnwenden);

["wk-filter-text", "wk-filter-intervall", "wk-filter-status", "wk-filter-konto", "wk-filter-person"].forEach((id) =>
  document.getElementById(id).addEventListener("input", renderWiederkehrendTabelle));

document.querySelectorAll("#abschnitt-wiederkehrend th.sortierbar").forEach((th) =>
  th.addEventListener("click", () => {
    const sp = th.dataset.spalte;
    WK_SORT = { spalte: sp, auf: WK_SORT.spalte === sp ? !WK_SORT.auf : true };
    renderWiederkehrendTabelle();
  }));

async function renderWiederkehrendTabelle() {
  WK_LISTE = await api("/wiederkehrend");
  const text = document.getElementById("wk-filter-text").value.toLowerCase();
  const intervall = document.getElementById("wk-filter-intervall").value;
  const status = document.getElementById("wk-filter-status").value;
  const kontoFilter = document.getElementById("wk-filter-konto").value;
  const personFilter = document.getElementById("wk-filter-person").value;

  let liste = WK_LISTE.filter((v) => {
    if (text && !`${v.beschreibung || ""} ${v.kategorie_anzeige || ""}`.toLowerCase().includes(text)) return false;
    if (intervall && v.intervall !== intervall) return false;
    if (status !== "" && String(v.aktiv) !== status) return false;
    if (kontoFilter && String(v.konto_id) !== kontoFilter && String(v.zielkonto_id) !== kontoFilter) return false;
    if (personFilter && String(v.person_id) !== personFilter) return false;
    return true;
  });

  liste.sort((a, b) => {
    const x = a[WK_SORT.spalte], y = b[WK_SORT.spalte];
    const cmp = typeof x === "number" && typeof y === "number"
      ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "de");
    return WK_SORT.auf ? cmp : -cmp;
  });

  document.getElementById("wiederkehrend-tabelle").innerHTML = liste.map((v) => `
    <tr>
      <td>${v.beschreibung || "–"}</td>
      <td>${personName(v.person_id)}</td>
      <td>${v.kategorie_anzeige || "–"}${v.sparziel_name ? `<br><span class="hinweis">Sparziel: ${v.sparziel_name}</span>` : ""}</td>
      <td class="rechts zahl ${v.ist_umbuchung ? "" : v.betrag < 0 ? "negativ" : "positiv"}">${euro(v.betrag)}</td>
      <td>${v.intervall}</td>
      <td>${v.tag_des_monats}.</td>
      <td>${v.monate_anzeige}</td>
      <td>${v.startdatum}</td>
      <td>${v.inflationsflag ? "ja" : "–"}</td>
      <td>${v.aktiv ? "aktiv" : "deaktiviert"}</td>
      <td class="reihen-werkzeuge">
        <button class="knopf sekundaer klein" onclick="wiederkehrendBearbeiten(${v.id})">Ändern</button>
        <button class="knopf sekundaer klein" onclick="wiederkehrendUmschalten(${v.id}, ${v.aktiv ? "false" : "true"})">${v.aktiv ? "Deaktivieren" : "Aktivieren"}</button>
        <button class="knopf gefahr klein" onclick="wiederkehrendLoeschen(${v.id})">Löschen</button>
      </td>
    </tr>`).join("") || `<tr><td colspan="11" class="leer">Keine Vorlagen</td></tr>`;
}

function wiederkehrendFormularZuruecksetzen() {
  const form = document.getElementById("form-wiederkehrend");
  form.reset();
  delete form.dataset.bearbeitetId;
  document.getElementById("wk-submit").textContent = "Anlegen";
  document.getElementById("wk-verwerfen").style.display = "none";
  document.getElementById("wk-dynamik-hidden").value = "0";
  document.getElementById("wk-dynamik-rhythmus-hidden").value = "";
  document.getElementById("wk-dynamik-prozent-hidden").value = "";
  document.getElementById("wk-dynamik-startjahr-hidden").value = "";
  document.getElementById("wk-dynamik-hinweis").style.display = "none";
  wkArtAnwenden();
}

document.getElementById("wk-verwerfen").addEventListener("click", wiederkehrendFormularZuruecksetzen);

async function wiederkehrendBearbeiten(id) {
  const v = (await api("/wiederkehrend")).find((x) => x.id === id);
  if (!v) return;
  const form = document.getElementById("form-wiederkehrend");
  document.getElementById("wk-meldung").textContent = "";
  form.art.value = v.zielkonto_id ? "umbuchung" : "buchung";
  form.konto_id.value = v.konto_id;
  form.zielkonto_id.value = v.zielkonto_id || "";
  wkSparzieleFiltern();
  form.sparziel_id.value = v.sparziel_id || "";
  form.person_id.value = v.person_id || "";
  form.betrag.value = v.zielkonto_id ? Math.abs(v.betrag) : v.betrag;
  form.kategorie_id.value = v.zielkonto_id ? "" : v.kategorie_id;
  form.beschreibung.value = v.beschreibung || "";
  form.intervall.value = v.intervall;
  form.tag_des_monats.value = v.tag_des_monats;
  form.monat.value = v.monat || "";
  form.startdatum.value = v.startdatum;
  form.enddatum.value = v.enddatum || "";
  form.inflationsflag.checked = !!v.inflationsflag;
  // Dynamik ist nur noch bei Altersvorsorge pflegbar - bestehende Werte
  // werden unverändert in verdeckten Feldern mitgeführt, damit ein
  // Speichern sie nicht versehentlich zurücksetzt.
  // Wichtig: "?? """ statt "|| """ verwenden - sonst würde ein
  // tatsächlicher Wert von 0 (z. B. 0 % Dynamik) fälschlich als "leer"
  // behandelt und beim nächsten Speichern in NULL verwandelt, was die
  // gesamte Wiederkehrend-Liste zum Absturz bringen kann (siehe
  // Bugfix v1.4).
  document.getElementById("wk-dynamik-hidden").value = v.dynamik_aktiv ? "1" : "0";
  document.getElementById("wk-dynamik-rhythmus-hidden").value = v.dynamik_rhythmus_jahre ?? "";
  document.getElementById("wk-dynamik-prozent-hidden").value = v.dynamik_prozent ?? "";
  document.getElementById("wk-dynamik-startjahr-hidden").value = v.dynamik_startjahr ?? "";
  wkArtAnwenden();
  form.dataset.bearbeitetId = id;
  document.getElementById("wk-submit").textContent = "Änderung speichern";
  document.getElementById("wk-verwerfen").style.display = "inline-block";
  form.scrollIntoView({ behavior: "smooth" });
}

// Fehlertext aus einer API-Fehlermeldung ("API-Fehler 422: {"detail": ...}").
function apiFehlerText(err) {
  const m = String(err.message || err).match(/^API-Fehler \d+: (.*)$/s);
  if (!m) return String(err.message || err);
  try {
    const d = JSON.parse(m[1]).detail;
    return typeof d === "string" ? d : (Array.isArray(d) ? d.map((x) => x.msg).join("; ") : m[1]);
  } catch { return m[1]; }
}

async function wiederkehrendUmschalten(id, aktiv) {
  const meldung = document.getElementById("wk-meldung");
  meldung.textContent = "";
  try {
    await api(`/wiederkehrend/${id}/aktiv?aktiv=${aktiv}`, { method: "PUT" });
  } catch (err) {
    meldung.textContent = apiFehlerText(err);
  }
  await renderWiederkehrendTabelle();
}

async function wiederkehrendLoeschen(id) {
  if (!confirm("Vorlage endgültig löschen? Noch offene Plan-Buchungen dieser Vorlage werden mit entfernt.")) return;
  await api(`/wiederkehrend/${id}`, { method: "DELETE" });
  wiederkehrendFormularZuruecksetzen();
  await renderWiederkehrendTabelle();
}

document.getElementById("form-wiederkehrend").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  const umbuchung = d.art === "umbuchung";
  const meldung = document.getElementById("wk-meldung");
  meldung.textContent = "";
  if (umbuchung && d.zielkonto_id === d.konto_id) {
    meldung.textContent = "Zielkonto und Konto müssen sich unterscheiden.";
    return;
  }
  const koerper = JSON.stringify({
    konto_id: Number(d.konto_id), betrag: Number(d.betrag),
    kategorie_id: umbuchung ? null : Number(d.kategorie_id),
    zielkonto_id: umbuchung ? Number(d.zielkonto_id) : null,
    sparziel_id: umbuchung && d.sparziel_id ? Number(d.sparziel_id) : null,
    beschreibung: d.beschreibung || null, intervall: d.intervall,
    tag_des_monats: Number(d.tag_des_monats), monat: d.monat ? Number(d.monat) : null,
    startdatum: d.startdatum, enddatum: d.enddatum || null, inflationsflag: !umbuchung && !!d.inflationsflag,
    // Verdecktes Textfeld mit "0"/"1" - NICHT per !! auswerten, der Text
    // "0" wäre wahr (Fehler bis v1.9.1: jede Vorlage bekam Scheindynamik
    // und verlor dadurch ihr Inflations-Häkchen).
    dynamik_aktiv: d.dynamik_aktiv === "1",
    dynamik_rhythmus_jahre: d.dynamik_rhythmus_jahre ? Number(d.dynamik_rhythmus_jahre) : null,
    dynamik_prozent: d.dynamik_prozent ? Number(d.dynamik_prozent) : null,
    dynamik_startjahr: d.dynamik_startjahr ? Number(d.dynamik_startjahr) : null,
    person_id: d.person_id ? Number(d.person_id) : null,
  });
  const id = e.target.dataset.bearbeitetId;
  serienHinweiseZeigen("wk-feiertage", null);
  let antwort;
  try {
    if (id) antwort = await api(`/wiederkehrend/${id}`, { method: "PUT", body: koerper });
    else antwort = await api("/wiederkehrend", { method: "POST", body: koerper });
  } catch (err) {
    meldung.textContent = apiFehlerText(err);
    return;
  }
  wiederkehrendFormularZuruecksetzen();
  serienHinweiseZeigen("wk-feiertage", antwort && antwort.feiertagshinweise);
  await renderWiederkehrendTabelle();
});

// ─── Plan-Buchungen-Protokoll ─────────────────────────────────────

async function ladePlanAbschnitt() {
  const liste = await api("/plan-buchungen/protokoll");
  document.getElementById("plan-protokoll-tabelle").innerHTML = liste.map((p) => `
    <tr>
      <td>${p.datum_umwandlung}</td>
      <td>${p.buchung_datum ?? "–"}</td>
      <td>${p.beschreibung || "–"}</td>
      <td class="rechts zahl ${(p.betrag ?? 0) < 0 ? "negativ" : "positiv"}">${p.betrag != null ? euro(p.betrag) : "–"}</td>
      <td><span class="abzeichen ${p.status === "umgewandelt" ? "ist" : "plan"}">${p.status}</span></td>
      <td class="reihen-werkzeuge">
        ${p.status === "umgewandelt" && p.buchung_typ === "Ist" ? `
          <button class="knopf sekundaer klein" onclick="planAnpassen(${p.buchung_id}, '${p.buchung_datum ?? ""}')">Datum ändern</button>
          <button class="knopf gefahr klein" onclick="planLoeschen(${p.buchung_id})">Verwerfen</button>` : ""}
      </td>
    </tr>`).join("") || `<tr><td colspan="6" class="leer">Noch keine Umwandlungen protokolliert</td></tr>`;
}

// Kleiner Dialog mit Datumsfeld (seit v2.6 statt prompt(), damit der
// Feiertagshinweis unter dem Feld erscheinen kann). Liefert das Datum oder null.
function datumDialog(titel, vorbelegung) {
  const dialog = document.getElementById("datum-dialog");
  const form = document.getElementById("form-datum-dialog");
  document.getElementById("datum-dialog-titel").textContent = titel;
  form.reset();
  form.datum.value = vorbelegung || heuteISO();
  feiertagHinweisZeigen(form.datum);
  return new Promise((fertig) => {
    const abbrechen = document.getElementById("datum-dialog-abbrechen");
    const aufraeumen = (wert) => {
      form.onsubmit = null; abbrechen.onclick = null; dialog.oncancel = null;
      dialog.close();
      fertig(wert);
    };
    form.onsubmit = (e) => { e.preventDefault(); aufraeumen(form.datum.value || null); };
    abbrechen.onclick = () => aufraeumen(null);
    dialog.oncancel = (e) => { e.preventDefault(); aufraeumen(null); };
    dialog.showModal();
  });
}

async function planAnpassen(buchungId, bisherigesDatum) {
  const neu = await datumDialog("Datum ändern", bisherigesDatum);
  if (!neu) return;
  await api(`/plan-buchungen/${buchungId}/ablehnen-anpassen?neues_datum=${neu}`, { method: "POST" });
  await ladePlanAbschnitt();
}

async function planLoeschen(buchungId) {
  if (!confirm("Buchung (und ggf. zukünftige Termine dieser Vorlage) wirklich verwerfen?")) return;
  await api(`/plan-buchungen/${buchungId}/ablehnen-loeschen`, { method: "POST" });
  await ladePlanAbschnitt();
}

// ─── Darlehen ─────────────────────────────────────────────────────

let DARLEHEN_LISTE = [];

document.getElementById("darlehen-raten-modus").addEventListener("change", (e) => {
  const istTilgungssatz = e.target.value === "tilgungssatz";
  document.getElementById("feld-tilgungssatz").style.display = istTilgungssatz ? "block" : "none";
  document.getElementById("feld-feste-rate").style.display = istTilgungssatz ? "none" : "block";
});

async function ladeDarlehenAbschnitt() {
  await Promise.all([ladeKonten(), ladePersonen()]);
  await renderDarlehenListe();
}

document.getElementById("darlehen-filter-person").addEventListener("change", renderDarlehenListe);

async function renderDarlehenListe() {
  DARLEHEN_LISTE = await api("/darlehen");
  const personFilter = document.getElementById("darlehen-filter-person").value;
  const liste = personFilter
    ? DARLEHEN_LISTE.filter((d) => String(d.person_id) === personFilter)
    : DARLEHEN_LISTE;
  document.getElementById("darlehen-liste").innerHTML = liste.map((d) => `
    <div class="karte" style="margin-bottom:10px; cursor:pointer" onclick="zeigeDarlehenDetail(${d.id}, '${d.bezeichnung.replace(/'/g, "\\'")}')">
      <div style="display:flex; justify-content:space-between; align-items:baseline">
        <div class="etikett">${d.bezeichnung}${d.person_id ? " · " + personName(d.person_id) : ""}</div>
        <div class="reihen-werkzeuge">
          <button class="knopf sekundaer klein" onclick="event.stopPropagation(); darlehenDialog('auszahlung', ${d.id})">Auszahlung</button>
          <button class="knopf sekundaer klein" onclick="event.stopPropagation(); darlehenDialog('sondertilgung', ${d.id})">Sondertilgung</button>
          <button class="knopf sekundaer klein" onclick="event.stopPropagation(); darlehenBearbeiten(${d.id})">Ändern</button>
        </div>
      </div>
      <div>Zins ${d.zinssatz}% · ${d.raten_modus === "tilgungssatz" ? `Tilgung ${d.tilgungssatz}%` : `Rate ${euro(d.feste_rate)}`}
        · Zinsbindung bis ${d.ende_zinsbindung}</div>
      <div class="etikett" style="margin-top:8px">Ausgezahlt (salden-wirksam)</div>
      <div class="betrag zahl positiv" style="font-size:18px">${euro(d.ausgezahlt)}</div>
      <div class="hinweis">${d.darlehenssumme != null
        ? `Darlehenssumme ${euro(d.darlehenssumme)} · noch nicht ausgezahlt ${euro(d.darlehenssumme - d.ausgezahlt)}`
        : "Darlehenssumme noch nicht erfasst (über „Ändern“ nachtragen)"}</div>
      ${(d.warnungen || []).map((w) => `<div class="warnung">${w}</div>`).join("")}
    </div>`).join("") || '<p class="leer">Noch keine Darlehen angelegt.</p>';
}

function darlehenFormularZuruecksetzen() {
  const form = document.getElementById("form-darlehen");
  form.reset();
  delete form.dataset.bearbeitetId;
  document.getElementById("darlehen-raten-modus").dispatchEvent(new Event("change"));
  document.getElementById("darlehen-submit").textContent = "Anlegen";
  document.getElementById("darlehen-verwerfen").style.display = "none";
  document.getElementById("darlehen-form-titel").textContent = "Neues Darlehen";
  document.getElementById("darlehen-summe").required = true;   // Pflicht bei neuen Darlehen
}

document.getElementById("darlehen-verwerfen").addEventListener("click", darlehenFormularZuruecksetzen);

function darlehenBearbeiten(id) {
  const d = DARLEHEN_LISTE.find((x) => x.id === id);
  if (!d) return;
  const form = document.getElementById("form-darlehen");
  form.bezeichnung.value = d.bezeichnung;
  form.zinssatz.value = d.zinssatz;
  form.zinsbeginn.value = d.zinsbeginn;
  form.tilgungsbeginn.value = d.tilgungsbeginn;
  form.laufzeit_jahre.value = d.laufzeit_jahre;
  form.ende_zinsbindung.value = d.ende_zinsbindung;
  form.anschlusszinssatz.value = d.anschlusszinssatz;
  form.raten_modus.value = d.raten_modus;
  form.tilgungssatz.value = d.tilgungssatz ?? "";
  form.feste_rate.value = d.feste_rate ?? "";
  form.zahlungskonto_id.value = d.zahlungskonto_id || "";
  form.person_id.value = d.person_id || "";
  form.darlehenssumme.value = d.darlehenssumme ?? "";
  // Bestehende Darlehen ohne erfasste Summe dürfen leer bleiben
  document.getElementById("darlehen-summe").required = false;
  document.getElementById("darlehen-raten-modus").dispatchEvent(new Event("change"));
  form.dataset.bearbeitetId = id;
  document.getElementById("darlehen-form-titel").textContent = "Darlehen ändern";
  document.getElementById("darlehen-submit").textContent = "Änderung speichern";
  document.getElementById("darlehen-verwerfen").style.display = "inline-block";
  form.scrollIntoView({ behavior: "smooth" });
}

document.getElementById("form-darlehen").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  const koerper = JSON.stringify({
    bezeichnung: d.bezeichnung, zinssatz: Number(d.zinssatz), zinsbeginn: d.zinsbeginn,
    tilgungsbeginn: d.tilgungsbeginn, laufzeit_jahre: Number(d.laufzeit_jahre),
    ende_zinsbindung: d.ende_zinsbindung, anschlusszinssatz: Number(d.anschlusszinssatz),
    raten_modus: d.raten_modus, tilgungssatz: d.tilgungssatz ? Number(d.tilgungssatz) : null,
    feste_rate: d.feste_rate ? Number(d.feste_rate) : null,
    zahlungskonto_id: d.zahlungskonto_id ? Number(d.zahlungskonto_id) : null,
    person_id: d.person_id ? Number(d.person_id) : null,
    darlehenssumme: d.darlehenssumme !== "" ? Number(d.darlehenssumme) : null,
  });
  const id = e.target.dataset.bearbeitetId;
  serienHinweiseZeigen("darlehen-feiertage", null);
  const antwort = id
    ? await api(`/darlehen/${id}`, { method: "PUT", body: koerper })
    : await api("/darlehen", { method: "POST", body: koerper });
  darlehenFormularZuruecksetzen();
  serienHinweiseZeigen("darlehen-feiertage", antwort && antwort.feiertagshinweise);
  await renderDarlehenListe();
  // Seit v2.6 erste Auszahlung im Dialog (mit Feiertagshinweis) statt prompt();
  // „Abbrechen“ überspringt sie wie früher die leere Eingabe.
  if (!id) darlehenDialog("auszahlung", antwort.id, { datum: d.zinsbeginn, erste: true });
});

async function zeigeDarlehenDetail(darlehenId, bezeichnung) {
  DARLEHEN_AKTIV_ID = darlehenId;
  document.getElementById("darlehen-detail-block").style.display = "block";
  document.getElementById("darlehen-detail-titel").textContent = "Tilgungsplan · " + bezeichnung;
  const plan = await api(`/darlehen/${darlehenId}/tilgungsplan`);

  const zahlungen = await api(`/buchungen?ziel_darlehen_id=${darlehenId}`);
  const sortiert = zahlungen.slice().sort((a, b) => (a.datum < b.datum ? 1 : -1));
  document.getElementById("tilgungsplan-tabelle").innerHTML = sortiert.map((b) => `
    <tr><td>${b.datum}</td><td>${kategoriePfad(b.kategorie_id)}</td>
    <td><span class="abzeichen ${b.typ.toLowerCase()}">${b.typ}</span></td>
    <td>${b.beschreibung || "–"}</td>
    <td class="rechts zahl ${b.betrag < 0 ? "negativ" : "positiv"}">${euro(b.betrag)}</td></tr>`).join("")
    || `<tr><td colspan="5" class="leer">Noch keine Zahlungen für dieses Darlehen gebucht</td></tr>`;

  if (CHART_DARLEHEN) CHART_DARLEHEN.destroy();
  CHART_DARLEHEN = new Chart(document.getElementById("darlehen-chart"), {
    type: "line",
    data: { labels: plan.map((z) => z.datum), datasets: [{
      label: "Restschuld", data: plan.map((z) => z.restschuld),
      borderColor: "#c9a227", backgroundColor: "#c9a22733", fill: true, tension: 0.15, pointRadius: 0,
    }]},
    options: { responsive: true, maintainAspectRatio: false,
      scales: { x: { ticks: { maxTicksLimit: 12 } }, y: { beginAtZero: true } } },
  });
  document.getElementById("darlehen-detail-block").scrollIntoView({ behavior: "smooth" });
}

// ─── Dialog: Auszahlung / Sondertilgung (seit v1.9, ersetzt das Formular
// in der Detailansicht) ───────────────────────────────────────────────
function darlehenDialog(art, id, vorgaben = {}) {
  const d = DARLEHEN_LISTE.find((x) => x.id === id);
  if (!d) return;
  const konto = KONTEN.find((k) => k.id === d.zahlungskonto_id);
  const istAuszahlung = art === "auszahlung";
  const kontoFeld = istAuszahlung
    ? `<p class="hinweis">${konto ? `Wird auf dem Zahlungskonto „${resetEsc(konto.name)}“ gebucht.`
        : "Kein Zahlungskonto hinterlegt – die Auszahlung wird nur am Darlehen erfasst, nicht auf einem Konto gebucht."}</p>`
    : `<div><label>Konto</label><select name="konto_id" required>${KONTEN.map((k) =>
        `<option value="${k.id}" ${k.id === d.zahlungskonto_id ? "selected" : ""}>${resetEsc(k.name)}</option>`).join("")}</select></div>`;
  document.getElementById("darlehen-dialog-inhalt").innerHTML = `
    <h2>${vorgaben.erste ? "Erste Auszahlung" : istAuszahlung ? "Auszahlung" : "Sondertilgung"} · ${resetEsc(d.bezeichnung)}</h2>
    <form class="formular" id="form-darlehen-dialog">
      ${kontoFeld}
      <div><label>Datum</label><input type="date" name="datum" value="${vorgaben.datum || heuteISO()}" required data-feiertag></div>
      <div><label>Betrag (€)</label><input type="number" step="0.01" min="0.01" name="betrag" required></div>
      <div class="warnung" id="darlehen-dialog-meldung" hidden></div>
      <div class="reihen-werkzeuge reset-knoepfe">
        <button type="button" class="knopf sekundaer" id="darlehen-dialog-abbrechen">${vorgaben.erste ? "Überspringen" : "Abbrechen"}</button>
        <button type="submit" class="knopf" id="darlehen-dialog-buchen">Buchen</button>
      </div>
    </form>`;
  const dialog = document.getElementById("darlehen-dialog");
  document.getElementById("darlehen-dialog-abbrechen").addEventListener("click", () => dialog.close());
  document.getElementById("form-darlehen-dialog").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = formularZuObjekt(e.target);
    const meldung = document.getElementById("darlehen-dialog-meldung");
    const knopf = document.getElementById("darlehen-dialog-buchen");
    knopf.disabled = true;
    try {
      const antwort = istAuszahlung
        ? await api(`/darlehen/${id}/auszahlungen`, { method: "POST", body: JSON.stringify({ datum: f.datum, betrag: Number(f.betrag) }) })
        : await api(`/darlehen/${id}/sondertilgung`, { method: "POST",
            body: JSON.stringify({ konto_id: Number(f.konto_id), datum: f.datum, betrag: Number(f.betrag) }) });
      await renderDarlehenListe();
      if (DARLEHEN_AKTIV_ID === id) await zeigeDarlehenDetail(id, d.bezeichnung);
      const hinweis = antwort && (antwort.hinweis || antwort.warnung);
      if (hinweis) {
        // Gebucht, aber mit Hinweis: Meldung zeigen, Knopf wird zu "Schließen"
        meldung.textContent = "Gebucht. " + hinweis;
        meldung.hidden = false;
        knopf.textContent = "Schließen";
        knopf.disabled = false;
        knopf.type = "button";
        knopf.onclick = () => dialog.close();
      } else {
        dialog.close();
      }
    } catch (fehler) {
      meldung.textContent = resetFehlertext(fehler);
      meldung.hidden = false;
      knopf.disabled = false;
    }
  });
  feiertagHinweiseAktualisieren(dialog);
  dialog.showModal();
}

// ─── Altersvorsorge ───────────────────────────────────────────────

let AV_LISTE = [];
let AV_SORT = { spalte: "bezeichnung", auf: true };

document.getElementById("av-dynamik").addEventListener("change", (e) => {
  document.querySelectorAll(".av-dynamik-feld").forEach((f) => (f.style.display = e.target.checked ? "block" : "none"));
});
document.getElementById("av-auszahlungsart").addEventListener("change", (e) => {
  const rente = e.target.value === "rente";
  document.querySelectorAll(".av-rente-feld").forEach((f) => (f.style.display = rente ? "block" : "none"));
  document.querySelectorAll(".av-einmal-feld").forEach((f) => (f.style.display = rente ? "none" : "block"));
});

// Einzahlung ist optional (z. B. rein arbeitgeber-/gehaltsfinanzierte
// Modelle, v1.5): ohne Häkchen werden die Beitrags-Felder deaktiviert,
// visuell abgeblendet und nicht mehr als Pflichtfeld verlangt.
function avEinzahlungAktualisieren() {
  const aktiv = document.getElementById("av-hat-einzahlung").checked;
  // Seit v1.9 ganz ausgeblendet statt ausgegraut
  document.getElementById("av-einzahlung-block").style.display = aktiv ? "" : "none";
  document.querySelectorAll("#av-einzahlung-felder input, #av-einzahlung-felder select").forEach((f) => (f.disabled = !aktiv));
  const form = document.getElementById("form-altersvorsorge");
  ["beitrag_betrag", "beitrag_kategorie_id", "beitrag_startdatum"].forEach((name) => {
    const feld = form.querySelector(`[name="${name}"]`);
    if (feld) feld.required = aktiv;
  });
}
document.getElementById("av-hat-einzahlung").addEventListener("change", avEinzahlungAktualisieren);

// Bequemlichkeits-Vorschlag: Neue Altersvorsorgen sollen ohne weiteres
// Zutun mit den empfohlenen Standard-Kategorien vorbelegt sein.
function avKategorieVorschlag(name) {
  const k = KATEGORIEN.find((x) => x.name === name);
  return k ? String(k.id) : "";
}

async function ladeAltersvorsorgeAbschnitt() {
  await Promise.all([ladeKonten(), ladeKategorien(), ladePersonen()]);
  const form = document.getElementById("form-altersvorsorge");
  if (!form.dataset.bearbeitetId) altersvorsorgeFormularZuruecksetzen();
  await renderAltersvorsorgeTabelle();
}

["av-filter-text", "av-filter-person", "av-filter-status"].forEach((id) => {
  const el = document.getElementById(id);
  el.addEventListener(id === "av-filter-text" ? "input" : "change", renderAltersvorsorgeTabelle);
});

document.querySelectorAll("#abschnitt-altersvorsorge th.sortierbar").forEach((th) =>
  th.addEventListener("click", () => {
    const sp = th.dataset.spalte;
    AV_SORT = { spalte: sp, auf: AV_SORT.spalte === sp ? !AV_SORT.auf : true };
    renderAltersvorsorgeTabelle();
  }));

function avAuszahlungGarantiert(a) {
  return a.auszahlungsart === "rente" ? (a.rente_garantiert_betrag || 0) : (a.einmalzahlung_garantiert_betrag || 0);
}
function avAuszahlungVoraussichtlich(a) {
  return a.auszahlungsart === "rente" ? (a.rente_voraussichtlich_betrag || 0) : (a.einmalzahlung_voraussichtlich_betrag || 0);
}

async function renderAltersvorsorgeTabelle() {
  AV_LISTE = await api("/altersvorsorge?nur_aktive=false");
  const text = document.getElementById("av-filter-text").value.toLowerCase();
  const personFilter = document.getElementById("av-filter-person").value;
  const status = document.getElementById("av-filter-status").value;

  let liste = AV_LISTE.filter((a) => {
    if (text && !`${a.bezeichnung || ""} ${a.anbieter || ""}`.toLowerCase().includes(text)) return false;
    if (personFilter && String(a.person_id) !== personFilter) return false;
    if (status !== "" && String(a.aktiv) !== status) return false;
    return true;
  }).map((a) => ({ ...a, _garantiert: avAuszahlungGarantiert(a), _voraussichtlich: avAuszahlungVoraussichtlich(a) }));

  liste.sort((a, b) => {
    const x = a[AV_SORT.spalte], y = b[AV_SORT.spalte];
    const cmp = typeof x === "number" && typeof y === "number"
      ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "de");
    return AV_SORT.auf ? cmp : -cmp;
  });

  document.getElementById("altersvorsorge-tabelle").innerHTML = liste.map((a) => `
    <tr>
      <td>${a.bezeichnung}</td>
      <td>${a.anbieter || "–"}</td>
      <td>${personName(a.person_id)}</td>
      <td>${a.rentenbeginn}</td>
      <td>${a.auszahlungsart === "rente" ? "Rente" : "Einmalzahlung"}</td>
      <td class="rechts zahl">${euro(a._garantiert)}</td>
      <td class="rechts zahl">${a._voraussichtlich ? euro(a._voraussichtlich) : "–"}</td>
      <td>${a.auszahlung_inflationsflag ? "ja" : "–"}</td>
      <td>${a.aktiv ? "aktiv" : "deaktiviert"}</td>
      <td class="reihen-werkzeuge">
        <button class="knopf sekundaer klein" onclick="altersvorsorgeBearbeiten(${a.id})">Ändern</button>
        <button class="knopf gefahr klein" onclick="altersvorsorgeLoeschen(${a.id})">Löschen</button>
      </td>
    </tr>`).join("") || `<tr><td colspan="10" class="leer">Noch keine Altersvorsorge angelegt.</td></tr>`;
}

function altersvorsorgeFormularZuruecksetzen() {
  const form = document.getElementById("form-altersvorsorge");
  form.reset();
  delete form.dataset.bearbeitetId;
  delete form.dataset.alterRentenbeginn;
  document.getElementById("av-submit").textContent = "Anlegen";
  document.getElementById("av-verwerfen").style.display = "none";
  document.getElementById("av-form-titel").textContent = "Neue Altersvorsorge";
  document.querySelectorAll(".av-dynamik-feld").forEach((f) => (f.style.display = "none"));
  document.querySelectorAll(".av-einmal-feld").forEach((f) => (f.style.display = "none"));
  document.querySelectorAll(".av-rente-feld").forEach((f) => (f.style.display = "block"));
  // Einzahlung ist bei neuen Verträgen standardmäßig deaktiviert (v1.5) -
  // erst mit gesetztem Häkchen werden Beitrags-Felder Pflicht.
  document.getElementById("av-hat-einzahlung").checked = false;
  avEinzahlungAktualisieren();
  const beitragKat = form.querySelector('[name="beitrag_kategorie_id"]');
  const auszahlungKat = form.querySelector('[name="auszahlung_kategorie_id"]');
  if (beitragKat) beitragKat.value = avKategorieVorschlag("Altersvorsorge");
  if (auszahlungKat) auszahlungKat.value = avKategorieVorschlag("Rente");
}

document.getElementById("av-verwerfen").addEventListener("click", altersvorsorgeFormularZuruecksetzen);

async function altersvorsorgeBearbeiten(id) {
  const a = await api(`/altersvorsorge/${id}`);
  const form = document.getElementById("form-altersvorsorge");
  const feld = (name) => form.querySelector(`[name="${name}"]`);
  for (const name of ["bezeichnung", "anbieter", "zahlungskonto_id", "person_id", "stand_datum",
      "beitrag_kategorie_id", "beitrag_betrag", "beitrag_intervall", "beitrag_tag_des_monats",
      "beitrag_monat", "beitrag_startdatum", "rentenbeginn", "ende_datum", "auszahlungsart",
      "auszahlung_kategorie_id", "rente_garantiert_betrag", "rente_voraussichtlich_betrag",
      "einmalzahlung_garantiert_betrag", "einmalzahlung_voraussichtlich_betrag",
      "rueckkaufswert", "auszahlung_bei_tod"]) {
    if (feld(name) && a[name] != null) feld(name).value = a[name];
  }
  // Ursprünglicher Rentenbeginn für den Bestätigungsdialog (seit v2.0)
  form.dataset.alterRentenbeginn = a.rentenbeginn || "";
  feld("auszahlung_inflationsflag").checked = !!a.auszahlung_inflationsflag;
  feld("beitrag_dynamik_aktiv").checked = !!a.beitrag_dynamik_aktiv;
  document.querySelectorAll(".av-dynamik-feld").forEach((f) => (f.style.display = a.beitrag_dynamik_aktiv ? "block" : "none"));
  if (a.beitrag_dynamik_rhythmus_jahre) feld("beitrag_dynamik_rhythmus_jahre").value = a.beitrag_dynamik_rhythmus_jahre;
  if (a.beitrag_dynamik_prozent) feld("beitrag_dynamik_prozent").value = a.beitrag_dynamik_prozent;
  if (a.beitrag_dynamik_startjahr) feld("beitrag_dynamik_startjahr").value = a.beitrag_dynamik_startjahr;
  feld("hat_einzahlung").checked = !!a.hat_einzahlung;
  avEinzahlungAktualisieren();
  feld("auszahlungsart").dispatchEvent(new Event("change"));
  form.dataset.bearbeitetId = id;
  document.getElementById("av-submit").textContent = "Änderung speichern";
  document.getElementById("av-verwerfen").style.display = "inline-block";
  document.getElementById("av-form-titel").textContent = "Altersvorsorge ändern";
  form.scrollIntoView({ behavior: "smooth" });
}

async function altersvorsorgeLoeschen(id) {
  if (!confirm("Altersvorsorge löschen? Bereits gebuchte Beiträge/Renten bleiben als Buchung erhalten.")) return;
  await api(`/altersvorsorge/${id}`, { method: "DELETE" });
  await renderAltersvorsorgeTabelle();
}

document.getElementById("form-altersvorsorge").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  const hatEinzahlung = !!d.hat_einzahlung;
  const koerper = JSON.stringify({
    bezeichnung: d.bezeichnung, anbieter: d.anbieter || null,
    zahlungskonto_id: Number(d.zahlungskonto_id), person_id: d.person_id ? Number(d.person_id) : null,
    stand_datum: d.stand_datum,
    hat_einzahlung: hatEinzahlung,
    beitrag_kategorie_id: hatEinzahlung ? Number(d.beitrag_kategorie_id) : null,
    beitrag_betrag: hatEinzahlung ? Number(d.beitrag_betrag) : null,
    beitrag_intervall: d.beitrag_intervall || "monatlich",
    beitrag_tag_des_monats: hatEinzahlung ? Number(d.beitrag_tag_des_monats) : 1,
    beitrag_monat: d.beitrag_monat ? Number(d.beitrag_monat) : null,
    beitrag_startdatum: hatEinzahlung ? d.beitrag_startdatum : null,
    beitrag_dynamik_aktiv: hatEinzahlung && !!d.beitrag_dynamik_aktiv,
    beitrag_dynamik_rhythmus_jahre: hatEinzahlung && d.beitrag_dynamik_rhythmus_jahre ? Number(d.beitrag_dynamik_rhythmus_jahre) : null,
    beitrag_dynamik_prozent: hatEinzahlung && d.beitrag_dynamik_prozent ? Number(d.beitrag_dynamik_prozent) : null,
    beitrag_dynamik_startjahr: hatEinzahlung && d.beitrag_dynamik_startjahr ? Number(d.beitrag_dynamik_startjahr) : null,
    rentenbeginn: d.rentenbeginn, ende_datum: d.ende_datum || null, auszahlungsart: d.auszahlungsart,
    auszahlung_kategorie_id: Number(d.auszahlung_kategorie_id),
    rente_garantiert_betrag: d.rente_garantiert_betrag ? Number(d.rente_garantiert_betrag) : null,
    rente_voraussichtlich_betrag: d.rente_voraussichtlich_betrag ? Number(d.rente_voraussichtlich_betrag) : null,
    einmalzahlung_garantiert_betrag: d.einmalzahlung_garantiert_betrag ? Number(d.einmalzahlung_garantiert_betrag) : null,
    einmalzahlung_voraussichtlich_betrag: d.einmalzahlung_voraussichtlich_betrag ? Number(d.einmalzahlung_voraussichtlich_betrag) : null,
    rueckkaufswert: d.rueckkaufswert ? Number(d.rueckkaufswert) : null,
    auszahlung_bei_tod: d.auszahlung_bei_tod ? Number(d.auszahlung_bei_tod) : null,
    auszahlung_inflationsflag: !!d.auszahlung_inflationsflag,
  });
  const id = e.target.dataset.bearbeitetId;
  let antwort;
  if (id) {
    // Rentenbeginn verschoben (seit v2.0): Bestätigungsdialog, danach werden
    // automatisch erzeugte Buchungen in der falschen Phase gelöscht.
    let bereinigen = false;
    const alt = e.target.dataset.alterRentenbeginn;
    if (alt && d.rentenbeginn && d.rentenbeginn !== alt) {
      const p = await api(`/altersvorsorge/${id}/phasen-pruefung?rentenbeginn=${d.rentenbeginn}`);
      if (p.loeschen || p.angepasst) {
        const text = `Rentenbeginn wird von ${alt} auf ${d.rentenbeginn} verschoben.\n\n`
          + (p.loeschen ? `${p.loeschen} automatisch erzeugte Buchung(en) lägen danach in der falschen Phase `
            + `(Beiträge nach dem Rentenbeginn bzw. Renten davor) und werden gelöscht.\n` : "")
          + (p.angepasst ? `${p.angepasst} im Plan-Protokoll angepasste Buchung(en) im betroffenen Zeitraum `
            + `bleiben unverändert stehen – bitte selbst prüfen.\n` : "")
          + `\nFehlende Beiträge bzw. Renten im verschobenen Zeitraum werden nachgebucht. Fortfahren?`;
        if (!confirm(text)) return;
        bereinigen = p.loeschen > 0;
      }
    }
    serienHinweiseZeigen("av-feiertage", null);
    antwort = await api(`/altersvorsorge/${id}${bereinigen ? "?phasen_bereinigen=true" : ""}`, { method: "PUT", body: koerper });
  } else {
    serienHinweiseZeigen("av-feiertage", null);
    antwort = await api("/altersvorsorge", { method: "POST", body: koerper });
  }
  altersvorsorgeFormularZuruecksetzen();
  serienHinweiseZeigen("av-feiertage", antwort && antwort.feiertagshinweise);
  await renderAltersvorsorgeTabelle();
  await ladeKonten();
});

// ─── Auswertungen ─────────────────────────────────────────────────

async function ladeAuswertungenAbschnitt() {
  await Promise.all([ladeKonten(), ladeKategorien()]);
  await renderAktivenAuswertungTab();
}

// ─── Auswertungen: Tabs Allgemein / Darlehen / Altersvorsorge (seit v1.9) ─

document.querySelectorAll(".auswertung-tab-knopf").forEach((knopf) => {
  knopf.addEventListener("click", () => {
    document.querySelectorAll(".auswertung-tab-knopf").forEach((k) => k.classList.remove("aktiv"));
    document.querySelectorAll(".auswertung-tab-inhalt").forEach((i) => i.classList.remove("aktiv"));
    knopf.classList.add("aktiv");
    document.querySelector(`.auswertung-tab-inhalt[data-auswertung-tab-inhalt="${knopf.dataset.auswertungTab}"]`).classList.add("aktiv");
    renderAktivenAuswertungTab();
  });
});

async function renderAktivenAuswertungTab() {
  const tab = document.querySelector(".auswertung-tab-knopf.aktiv")?.dataset.auswertungTab || "allgemein";
  if (tab === "darlehen") return renderDarlehenAuswertung();
  if (tab === "altersvorsorge") return renderAvAuswertung();
  return renderAuswertungen();
}

let CHART_AD_RESTSCHULD, CHART_AD_JAHRE, CHART_AA_JAHRE, CHART_AA_KUMULIERT;

// Validiert mit dem dataviz-Validator (Kategorial, hell): Zinsen, Tilgung, Sondertilgung
const FARBE_ZINSEN = "#c46210", FARBE_TILGUNG = "#3f6fb5", FARBE_SONDERTILGUNG = "#2f7d4f";
const FARBE_BEITRAG = "#c46210", FARBE_AUSZAHLUNG = "#2f7d4f", FARBE_VORAUSSICHTLICH = "#3f6fb5";

function vertragsZeitraum(selectId) {
  const wert = document.getElementById(selectId).value;
  if (wert === "gesamt") return "";
  const bis = new Date(); bis.setFullYear(bis.getFullYear() + Number(wert));
  return `&von=${heuteISO()}&bis=${datumISO(bis)}`;
}

function auswahlFuellen(selectId, eintraege, alleText) {
  const sel = document.getElementById(selectId);
  const bisher = sel.value;
  sel.innerHTML = `<option value="">${alleText}</option>` +
    eintraege.map((e) => `<option value="${e.id}">${resetEsc(e.name)}</option>`).join("");
  if ([...sel.options].some((o) => o.value === bisher)) sel.value = bisher;
}

function kennzahlKarte(etikett, wert, zusatz = "", klasse = "") {
  return `<div class="karte"><div class="etikett">${etikett}</div>
    <div class="betrag zahl ${klasse}">${wert}</div>${zusatz ? `<div class="kennzahl-zusatz">${zusatz}</div>` : ""}</div>`;
}

function prognoseMarke(p) {
  return p === "voll" ? '<span class="prognose-marke">Prognose</span>'
    : p === "teilweise" ? '<span class="prognose-marke">teilw. Prognose</span>' : "";
}

// Senkrechte, gestrichelte Markierungen (z. B. Ende der Zinsbindung) ohne Zusatz-Plugin
const markierungsPlugin = {
  id: "markierungen",
  afterDatasetsDraw(chart, _args, optionen) {
    const { ctx, chartArea, scales } = chart;
    (optionen.linien || []).forEach((l) => {
      const index = chart.data.labels.indexOf(l.label);
      if (index < 0) return;
      const x = scales.x.getPixelForValue(index);
      ctx.save();
      ctx.strokeStyle = l.farbe; ctx.lineWidth = 2; ctx.setLineDash([5, 4]);
      ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
      ctx.restore();
    });
  },
};

document.getElementById("ad-auswahl").addEventListener("change", renderDarlehenAuswertung);
document.getElementById("ad-zeitraum").addEventListener("change", renderDarlehenAuswertung);

async function renderDarlehenAuswertung() {
  const liste = await api("/darlehen");
  auswahlFuellen("ad-auswahl", liste.map((d) => ({ id: d.id, name: d.bezeichnung })), "Alle Darlehen");
  const id = document.getElementById("ad-auswahl").value;
  const a = await api(`/auswertungen/darlehen?${id ? `darlehen_id=${id}` : ""}${vertragsZeitraum("ad-zeitraum")}`);
  const k = a.kennzahlen;

  document.getElementById("ad-kennzahlen").innerHTML =
    kennzahlKarte("Restschuld heute", euro(k.restschuld_heute), "", "negativ")
    + kennzahlKarte("Restschuld Ende Zinsbindung", euro(k.restschuld_ende_zinsbindung), "Betrag für die Anschlussfinanzierung")
    + kennzahlKarte("Bisher gezahlt", euro(k.zinsen_bisher + k.tilgung_bisher),
        `Zinsen ${euro(k.zinsen_bisher)} · Tilgung ${euro(k.tilgung_bisher)}`)
    + kennzahlKarte("Noch anfallende Zinsen", euro(k.zinsen_kuenftig), "bis Laufzeitende, ohne künftige Sondertilgungen")
    + kennzahlKarte("Restschuld Laufzeitende", euro(k.restschuld_laufzeitende));

  // Restschuld-Verlauf, gestapelt je Darlehen (Farbe folgt dem Darlehen, nicht dem Rang)
  const farbeJe = Object.fromEntries(liste.map((d, i) => [d.bezeichnung, KONTEN_FARBSCHEMA[i % KONTEN_FARBSCHEMA.length]]));
  if (CHART_AD_RESTSCHULD) CHART_AD_RESTSCHULD.destroy();
  CHART_AD_RESTSCHULD = new Chart(document.getElementById("ad-restschuld-chart"), {
    type: "line",
    data: { labels: a.verlauf.monate, datasets: a.verlauf.reihen.map((r) => ({
      label: r.name, data: r.werte, borderColor: farbeJe[r.name], backgroundColor: farbeJe[r.name] + "33",
      borderWidth: 2, fill: true, tension: 0.1, pointRadius: 0, stack: "restschuld",
    })) },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: a.verlauf.reihen.length > 1 },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${euro(c.parsed.y)}` } },
        markierungen: { linien: a.verlauf.reihen.map((r) => ({ label: r.ende_zinsbindung, farbe: farbeJe[r.name] })) } },
      scales: { x: { ticks: { maxTicksLimit: 14 } }, y: { stacked: true, beginAtZero: true, ticks: { callback: (v) => euro(v) } } } },
    plugins: [markierungsPlugin],
  });

  // Zins / Tilgung / Sondertilgung je Jahr - Prognosejahre heller
  const hell = (farbe) => a.jahre.map((j) => (j.prognose === "voll" ? farbe + "80" : farbe));
  if (CHART_AD_JAHRE) CHART_AD_JAHRE.destroy();
  CHART_AD_JAHRE = new Chart(document.getElementById("ad-jahre-chart"), {
    type: "bar",
    data: { labels: a.jahre.map((j) => j.jahr), datasets: [
      { label: "Zinsen", data: a.jahre.map((j) => j.zinsen), backgroundColor: hell(FARBE_ZINSEN), borderRadius: 4, borderSkipped: "start", borderColor: "#fff", borderWidth: { top: 2 } },
      { label: "Tilgung", data: a.jahre.map((j) => j.tilgung), backgroundColor: hell(FARBE_TILGUNG), borderRadius: 4, borderSkipped: "start", borderColor: "#fff", borderWidth: { top: 2 } },
      { label: "Sondertilgung", data: a.jahre.map((j) => j.sondertilgung), backgroundColor: hell(FARBE_SONDERTILGUNG), borderRadius: 4, borderSkipped: "start", borderColor: "#fff", borderWidth: { top: 2 } },
    ] },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${euro(c.parsed.y)}` } } },
      scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, ticks: { callback: (v) => euro(v) } } } },
  });

  document.getElementById("ad-jahre-tabelle").innerHTML = a.jahre.map((j) => `
    <tr class="${j.prognose === "voll" ? "prognose" : ""}"><td>${j.jahr}${prognoseMarke(j.prognose)}</td>
      <td class="rechts zahl">${euro(j.zinsen)}</td><td class="rechts zahl">${euro(j.tilgung)}</td>
      <td class="rechts zahl">${euro(j.sondertilgung)}</td><td class="rechts zahl">${euro(j.rate)}</td>
      <td class="rechts zahl">${euro(j.restschuld)}</td></tr>`).join("")
    || '<tr><td colspan="6" class="leer">Keine Daten im Zeitraum</td></tr>';

  const geld = (w) => (w == null ? "–" : euro(w));
  const zeile = (d, klasse = "") => `
    <tr class="${klasse}"><td>${resetEsc(d.bezeichnung)}</td>
      <td class="rechts zahl">${geld(d.darlehenssumme)}</td><td class="rechts zahl">${geld(d.nicht_ausgezahlt)}</td>
      <td class="rechts zahl">${geld(d.bisher.zinsen)}</td><td class="rechts zahl">${geld(d.bisher.tilgung)}</td>
      <td class="rechts zahl">${geld(d.bisher.sondertilgung)}</td><td class="rechts zahl">${geld(d.bisher.raten)}</td>
      <td class="rechts zahl">${geld(d.gesamt.zinsen)}</td><td class="rechts zahl">${geld(d.gesamt.tilgung)}</td>
      <td class="rechts zahl">${geld(d.gesamt.sondertilgung)}</td><td class="rechts zahl">${geld(d.gesamt.raten)}</td>
      <td class="rechts zahl">${geld(d.restschuld_heute)}</td><td class="rechts zahl">${geld(d.restschuld_laufzeitende)}</td></tr>`;
  document.getElementById("ad-darlehen-tabelle").innerHTML =
    (a.darlehen.map((d) => zeile(d)).join("") + (a.summe ? zeile(a.summe, "summe") : ""))
    || '<tr><td colspan="13" class="leer">Noch keine Darlehen angelegt</td></tr>';
}

document.getElementById("aa-auswahl").addEventListener("change", renderAvAuswertung);
document.getElementById("aa-zeitraum").addEventListener("change", renderAvAuswertung);

async function renderAvAuswertung() {
  const liste = await api("/altersvorsorge?nur_aktive=false");
  auswahlFuellen("aa-auswahl", liste.map((v) => ({ id: v.id, name: v.bezeichnung })), "Alle Verträge");
  const id = document.getElementById("aa-auswahl").value;
  const a = await api(`/auswertungen/altersvorsorge?${id ? `av_id=${id}` : ""}${vertragsZeitraum("aa-zeitraum")}${inflationParam("auswertung-inflation")}`);
  const k = a.kennzahlen;
  const datumDe = (iso) => iso ? new Date(iso).toLocaleDateString("de-DE") : "";

  const be = a.break_even;
  const beText = (jahr) => (jahr ? `ab ${jahr}` : `nicht im Planungshorizont (bis ${datumDe(a.horizont_bis)})`);
  document.getElementById("aa-meldungen").innerHTML =
    `<p class="hinweis"><strong>Nulldurchgang</strong> (Auszahlungen übersteigen die Beiträge): garantiert ${beText(be.garantiert)},
      voraussichtlich ${beText(be.voraussichtlich)}.</p>`
    + (k.veraltet.length ? `<div class="warnung">Standmitteilung älter als 14 Monate: ${k.veraltet.map(resetEsc).join(", ")}</div>` : "");

  document.getElementById("aa-kennzahlen").innerHTML =
    kennzahlKarte("Bisher gezahlte Beiträge", euro(k.beitraege_bisher))
    + kennzahlKarte("Noch zu zahlende Beiträge", euro(k.beitraege_kuenftig), "bis Rentenbeginn")
    + kennzahlKarte("Rente monatlich (garantiert)", euro(k.rente_monatlich_garantiert),
        `voraussichtlich ${euro(k.rente_monatlich_voraussichtlich)}`, "positiv")
    + kennzahlKarte("Einmalzahlungen (garantiert)", euro(k.einmalzahlung_garantiert),
        `voraussichtlich ${euro(k.einmalzahlung_voraussichtlich)}`, "positiv")
    + kennzahlKarte("Rückkaufswerte", k.rueckkaufswert == null ? "–" : euro(k.rueckkaufswert),
        k.rueckkaufswert == null ? "keine erfasst" : `rein informativ · ältester Stand ${datumDe(k.rueckkaufswert_stand)}`);

  const jahre = a.jahre;
  if (CHART_AA_JAHRE) CHART_AA_JAHRE.destroy();
  CHART_AA_JAHRE = new Chart(document.getElementById("aa-jahre-chart"), {
    type: "bar",
    data: { labels: jahre.map((j) => j.jahr), datasets: [
      { label: "Beiträge", data: jahre.map((j) => j.beitraege), backgroundColor: FARBE_BEITRAG, stack: "beitrag", borderRadius: 4, borderSkipped: "start" },
      { label: "Auszahlung garantiert", data: jahre.map((j) => j.auszahlung_garantiert), backgroundColor: FARBE_AUSZAHLUNG, stack: "auszahlung", borderRadius: 4, borderSkipped: "start", borderColor: "#fff", borderWidth: { top: 2 } },
      { label: "zusätzlich voraussichtlich", data: jahre.map((j) => Math.max(0, j.auszahlung_voraussichtlich - j.auszahlung_garantiert)),
        backgroundColor: FARBE_AUSZAHLUNG + "59", stack: "auszahlung", borderRadius: 4, borderSkipped: "start" },
    ] },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${euro(c.parsed.y)}` } } },
      scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, ticks: { callback: (v) => euro(v) } } } },
  });

  if (CHART_AA_KUMULIERT) CHART_AA_KUMULIERT.destroy();
  CHART_AA_KUMULIERT = new Chart(document.getElementById("aa-kumuliert-chart"), {
    type: "line",
    data: { labels: jahre.map((j) => j.jahr), datasets: [
      { label: "Kumuliert garantiert", data: jahre.map((j) => j.kumuliert_garantiert), borderColor: FARBE_AUSZAHLUNG, borderWidth: 2, pointRadius: 0, tension: 0.1 },
      { label: "Kumuliert voraussichtlich", data: jahre.map((j) => j.kumuliert_voraussichtlich), borderColor: FARBE_VORAUSSICHTLICH, borderDash: [6, 4], borderWidth: 2, pointRadius: 0, tension: 0.1 },
    ] },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${euro(c.parsed.y)}` } } },
      scales: { y: { ticks: { callback: (v) => euro(v) }, grid: { color: (c) => (c.tick.value === 0 ? "#16231f66" : "#16231f14") } } } },
  });

  document.getElementById("aa-jahre-tabelle").innerHTML = jahre.map((j) => `
    <tr class="${j.prognose === "voll" ? "prognose" : ""}"><td>${j.jahr}${prognoseMarke(j.prognose)}</td>
      <td class="rechts zahl">${euro(j.beitraege)}</td><td class="rechts zahl">${euro(j.auszahlung_garantiert)}</td>
      <td class="rechts zahl">${euro(j.auszahlung_voraussichtlich)}</td>
      <td class="rechts zahl ${j.kumuliert_garantiert < 0 ? "negativ" : "positiv"}">${euro(j.kumuliert_garantiert)}</td>
      <td class="rechts zahl ${j.kumuliert_voraussichtlich < 0 ? "negativ" : "positiv"}">${euro(j.kumuliert_voraussichtlich)}</td></tr>`).join("")
    || '<tr><td colspan="6" class="leer">Keine Daten im Zeitraum</td></tr>';
}

// 14 klar unterscheidbare Farben für Konten (Saldo-Verlauf, Kategorien-
// Diagramm usw.) - reicht für bis zu 14 Konten, bevor sich Farben
// wiederholen.
const KONTEN_FARBSCHEMA = [
  "#2f7d4f", // Grün
  "#c9a227", // Messing-Gold
  "#6a8caf", // Blau
  "#a23e3e", // Rot
  "#7d5ba6", // Violett
  "#3f8fa6", // Petrol
  "#b5651d", // Terrakotta
  "#5b8c6b", // Salbei
  "#c46210", // Bernstein
  "#4f6b91", // Stahlblau
  "#8a6d3b", // Ocker
  "#3f7d5c", // Tanne
  "#9c4f6b", // Weinrot
  "#6b6b3f", // Oliv
];

// ─── Auswertungen „Allgemein“: Filter (seit v2.3 Mehrfachauswahl, automatisch, gemerkt) ─

const FILTER_AUSWERTUNGEN = "finanzapp.filter.auswertungen";
let KATEGORIEN_SEITE = "ausgabe";
let CHART_SPARK;

function auswertungFilterSpeichern() {
  filterSpeichern(FILTER_AUSWERTUNGEN, {
    horizont: document.getElementById("auswertung-horizont").value,
    von: document.getElementById("auswertung-von").value,
    bis: document.getElementById("auswertung-bis").value,
    einheit: document.getElementById("auswertung-einheit").value,
    konten: MEHRFACH.auswertungKonten.speicherWert(),
    kategorien: MEHRFACH.auswertungKategorien.speicherWert(),
    kategorien_seite: KATEGORIEN_SEITE,
  });
}

function auswertungFilterGeaendert() {
  auswertungFilterSpeichern();
  renderAuswertungen();
}

function benutzerdefFelderZeigen() {
  const benutzerdef = document.getElementById("auswertung-horizont").value === "benutzerdefiniert";
  document.getElementById("auswertung-von-feld").style.display = benutzerdef ? "block" : "none";
  document.getElementById("auswertung-bis-feld").style.display = benutzerdef ? "block" : "none";
  return benutzerdef;
}

MEHRFACH.auswertungKonten = new MehrfachAuswahl(document.getElementById("auswertung-konten"), auswertungFilterGeaendert);
MEHRFACH.auswertungKategorien = new MehrfachAuswahl(document.getElementById("auswertung-kategorien"), auswertungFilterGeaendert);
(() => {
  const f = filterLaden(FILTER_AUSWERTUNGEN);
  const setzeWenn = (id, wert) => {
    const sel = document.getElementById(id);
    if (wert !== undefined && wert !== null && [...(sel.options || [{ value: wert }])].some((o) => o.value === wert)) sel.value = wert;
  };
  setzeWenn("auswertung-horizont", f.horizont);
  setzeWenn("auswertung-einheit", f.einheit);
  if (f.von) document.getElementById("auswertung-von").value = f.von;
  if (f.bis) document.getElementById("auswertung-bis").value = f.bis;
  if (Array.isArray(f.konten)) MEHRFACH.auswertungKonten.setzen(f.konten);
  if (Array.isArray(f.kategorien)) MEHRFACH.auswertungKategorien.setzen(f.kategorien);
  if (f.kategorien_seite === "einnahme") KATEGORIEN_SEITE = "einnahme";
  benutzerdefFelderZeigen();
  segmenteAufbauen();
  document.querySelectorAll("#kategorien-seite button").forEach((b) => b.classList.toggle("an", b.dataset.wert === KATEGORIEN_SEITE));
})();

["auswertung-einheit", "auswertung-von", "auswertung-bis"].forEach((id) =>
  document.getElementById(id).addEventListener("change", auswertungFilterGeaendert));
["auswertung-korridor", "auswertung-inkl-darlehen"].forEach((id) =>
  document.getElementById(id).addEventListener("change", renderAuswertungen));
document.getElementById("auswertung-inflation").addEventListener("change", () => {
  renderAuswertungen();
  renderAvAuswertung();
});
document.getElementById("auswertung-horizont").addEventListener("change", () => {
  if (benutzerdefFelderZeigen() && !document.getElementById("auswertung-von").value) {
    document.getElementById("auswertung-von").value = heuteISO();
  }
  auswertungFilterGeaendert();
});
document.getElementById("kategorien-seite").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b || b.dataset.wert === KATEGORIEN_SEITE) return;
  KATEGORIEN_SEITE = b.dataset.wert;
  document.querySelectorAll("#kategorien-seite button").forEach((x) => x.classList.toggle("an", x === b));
  auswertungFilterSpeichern();
  if (AUSWERTUNG_DATEN) kategorienRanglisteZeichnen(AUSWERTUNG_DATEN);
});

function auswertungZeitraum() {
  const horizont = document.getElementById("auswertung-horizont").value;
  if (horizont === "benutzerdefiniert") {
    const von = document.getElementById("auswertung-von").value || heuteISO();
    const bis = document.getElementById("auswertung-bis").value || heuteISO();
    return { von, bis };
  }
  const jahre = Number(horizont);
  const von = heuteISO();
  const bisDatum = new Date();
  bisDatum.setFullYear(bisDatum.getFullYear() + jahre);
  return { von, bis: datumISO(bisDatum) };
}

// Cashflow verdichten (seit v2.3): bis 25 Monate je Monat, bis 121 Monate
// je Quartal, darüber je Jahr. Liefert Beschriftungen und Summen je Gruppe.
function cashflowVerdichten(cf) {
  const n = cf.monate.length;
  const stufe = n <= 25 ? "monat" : n <= 121 ? "quartal" : "jahr";
  const gruppen = [];
  const index = new Map();
  cf.monate.forEach((m, i) => {
    const [j, mo] = m.split("-").map(Number);
    const schluessel = stufe === "monat" ? m : stufe === "quartal" ? `Q${Math.ceil(mo / 3)} ${String(j).slice(2)}` : String(j);
    if (!index.has(schluessel)) {
      index.set(schluessel, gruppen.length);
      gruppen.push({ label: schluessel, ein: 0, aus: 0, einAnst: 0, ausAnst: 0 });
    }
    const g = gruppen[index.get(schluessel)];
    g.ein += cf.einnahmen[i]; g.aus += cf.ausgaben[i];
    g.einAnst += (cf.einnahmen_anstehend || [])[i] || 0;
    g.ausAnst += (cf.ausgaben_anstehend || [])[i] || 0;
  });
  return { stufe, gruppen };
}

let AUSWERTUNG_LAUF = 0;
let AUSWERTUNG_DATEN = null;

function kachel(etikett, wert, zusatz = "", klasse = "") {
  return `<div class="karte"><div class="etikett">${etikett}</div>
    <div class="betrag zahl ${klasse}">${wert}</div><div class="kennzahl-zusatz">${zusatz}</div></div>`;
}

async function renderAuswertungen() {
  const lauf = ++AUSWERTUNG_LAUF;
  const inklDarlehen = document.getElementById("auswertung-inkl-darlehen").checked;
  const einheit = Number(document.getElementById("auswertung-einheit").value);
  const einheitLabel = einheit === 1000 ? "k€" : "€";
  const skaliert = (werte) => werte.map((w) => Math.round((w / einheit) * 100) / 100);
  const betragText = (w) => (einheit === 1000 ? `${zahlDe(w / 1000, 1)} k€` : euro(w));
  const { von, bis } = auswertungZeitraum();
  const kontenParam = MEHRFACH.auswertungKonten.paramWert();
  const katParam = MEHRFACH.auswertungKategorien.paramWert();
  const katAktiv = katParam !== null;
  document.getElementById("auswertung-kategorie-hinweis").style.display = katAktiv && katParam !== "" ? "block" : "none";

  const leer = kontenParam === "" ? "Keine Konten gewählt. Wähle unter „Konten“ mindestens eines aus."
    : katParam === "" ? "Keine Kategorien gewählt. Wähle unter „Kategorien“ mindestens eine aus." : "";
  document.getElementById("auswertung-leer").style.display = leer ? "block" : "none";
  document.getElementById("auswertung-leer").textContent = leer;
  document.getElementById("auswertung-inhalt").style.display = leer ? "none" : "block";
  if (leer) return;

  const filterParams = (kontenParam !== null ? `&konten=${kontenParam}` : "") + (katAktiv ? `&kategorien=${katParam}` : "")
    + inflationParam("auswertung-inflation");
  const mitKorridor = document.getElementById("auswertung-korridor").checked && !katAktiv;
  const [saldoDaten, cashflowDaten, kategorienDaten, korridor] = await Promise.all([
    api(`/auswertungen/saldo-verlauf?von=${von}&bis=${bis}&inkl_darlehen=${inklDarlehen}${filterParams}`),
    api(`/auswertungen/cashflow?von=${von}&bis=${bis}${filterParams}`),
    api(`/auswertungen/kategorien?von=${von}&bis=${bis}${filterParams}`),
    mitKorridor ? api(`/auswertungen/altersvorsorge-korridor?von=${von}&bis=${bis}`
      + `${kontenParam !== null ? `&konten=${kontenParam}` : ""}${inflationParam("auswertung-inflation")}`) : null,
  ]);
  if (lauf !== AUSWERTUNG_LAUF) return;  // inzwischen neu angefordert
  AUSWERTUNG_DATEN = { kategorienDaten, einheit, einheitLabel, skaliert, betragText };

  const tooltipBetrag = (c) => ` ${c.dataset.label}: ${zahlDe(Math.abs(c.parsed.y))} ${einheitLabel}`;
  const yTicks = { callback: (v) => `${zahlDe(v)} ${einheitLabel}` };

  // ── Saldo-Verlauf ──
  if (CHART_SALDO) CHART_SALDO.destroy();
  const n = saldoDaten.monate.length;
  let saldoDatasets;
  let stapeln = true;
  if (saldoDaten.modus === "kategorien") {
    const serien = saldoDaten.kategorien;
    const vorzeichen = new Set(serien.map((s) => Math.sign(s.werte.reduce((a, b) => a + b, 0)) || 1));
    stapeln = vorzeichen.size === 1;  // gemischte Vorzeichen nicht stapeln
    saldoDatasets = serien.map((s, i) => {
      const farbe = KONTEN_FARBSCHEMA[i % KONTEN_FARBSCHEMA.length];
      return { label: s.name, data: skaliert(s.werte), stack: stapeln ? "kategorien" : `k${i}`, fill: stapeln,
        borderColor: farbe, backgroundColor: farbe + "c0", borderWidth: stapeln ? 1 : 2, tension: 0.3, order: 2 };
    });
    if (serien.length > 1) {
      const summe = saldoDaten.monate.map((_, i) => serien.reduce((a, s) => a + s.werte[i], 0));
      saldoDatasets.unshift({ label: "Summe", data: skaliert(summe), stack: "summe", fill: false,
        borderColor: "#16231f", borderWidth: 2.5, tension: 0.3, order: 0 });
    }
    document.getElementById("saldo-unter").textContent = "Aufsummierte Beträge je gewählter Kategorie über die gewählten Konten";
  } else {
    saldoDatasets = saldoDaten.konten.map((s, i) => {
      const farbe = s.farbe || KONTEN_FARBSCHEMA[i % KONTEN_FARBSCHEMA.length];
      return { label: s.name, data: skaliert(s.werte), stack: "konten", fill: true,
        borderColor: farbe, backgroundColor: farbe + "c0", borderWidth: 1, tension: 0.3, order: 2 };
    });
    const mitRestschuld = inklDarlehen && saldoDaten.darlehen.length > 0;
    const gesamt = saldoDaten.monate.map((_, i) =>
      saldoDaten.konten.reduce((a, s) => a + s.werte[i], 0) + (mitRestschuld ? saldoDaten.darlehen.reduce((a, d) => a + d.werte[i], 0) : 0));
    saldoDatasets.unshift({ label: mitRestschuld ? "Nettovermögen" : "Summe der Konten", data: skaliert(gesamt), stack: "netto",
      fill: false, borderColor: "#16231f", borderWidth: 2.5, tension: 0.3, order: 0 });
    saldoDaten.darlehen.forEach((s, i) => saldoDatasets.push({ label: s.name, data: skaliert(s.werte), stack: "darlehen-" + i,
      fill: false, borderDash: [5, 4], borderColor: "#a23e3e", borderWidth: 1.5, tension: 0.3, order: 1 }));
    if (korridor) {
      const korridorMap = {};
      let kumKorr = 0;
      (korridor.monate || []).forEach((m, i) => { kumKorr += korridor.werte[i]; korridorMap[m] = kumKorr; });
      const kontenSumme = saldoDaten.monate.map((_, i) => saldoDaten.konten.reduce((a, s) => a + s.werte[i], 0));
      let letzterWert = 0;
      const korridorWerte = saldoDaten.monate.map((m, i) => {
        if (korridorMap[m] !== undefined) letzterWert = korridorMap[m];
        return skaliert([kontenSumme[i] + letzterWert])[0];
      });
      saldoDatasets.push({ label: "Voraussichtlich (Korridor)", data: korridorWerte, stack: "korridor",
        borderColor: "#c9a227", borderDash: [5, 4], fill: false, tension: 0.3, order: 1 });
    }
    document.getElementById("saldo-unter").textContent = mitRestschuld
      ? "Gestapelt je Konto, dunkle Linie = Nettovermögen (Konten minus Restschuld)"
      : "Gestapelt je Konto, dunkle Linie = Summe der Konten";
  }
  CHART_SALDO = new Chart(document.getElementById("saldo-chart"), {
    type: "line",
    data: { labels: saldoDaten.monate, datasets: saldoDatasets },
    plugins: [HEUTE_LINIE],
    options: { responsive: true, maintainAspectRatio: false,
      scales: { x: { ticks: { maxTicksLimit: 12 } },
        // suggestedMin/Max: Achse bei Bedarf bis 0, schneidet aber keine Werte ab
        y: { stacked: true, suggestedMin: 0, suggestedMax: 0, ticks: yTicks } },
      plugins: { tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${zahlDe(c.parsed.y)} ${einheitLabel}` } },
        heuteLinie: { index: saldoDaten.prognose_ab_index } } },
  });

  // ── Cashflow ──
  if (CHART_CASHFLOW) CHART_CASHFLOW.destroy();
  const { stufe, gruppen } = cashflowVerdichten(cashflowDaten);
  const r2 = (w) => Math.round(w * 100) / 100;
  CHART_CASHFLOW = new Chart(document.getElementById("cashflow-chart"), {
    data: { labels: gruppen.map((g) => g.label), datasets: [
      { type: "line", label: "Überschuss", data: skaliert(gruppen.map((g) => r2(g.ein - g.aus))), borderColor: "#16231f",
        borderWidth: 2, pointRadius: gruppen.length > 40 ? 0 : 2.5, pointBackgroundColor: "#16231f", tension: 0.3, order: 0 },
      { type: "bar", label: "Einnahmen", data: skaliert(gruppen.map((g) => r2(g.ein - g.einAnst))), backgroundColor: "#2f7d4f",
        stack: "cashflow", order: 1 },
      { type: "bar", label: "Einnahmen anstehend", data: skaliert(gruppen.map((g) => r2(g.einAnst))),
        backgroundColor: "#2f7d4f66", stack: "cashflow", order: 1 },
      { type: "bar", label: "Ausgaben", data: skaliert(gruppen.map((g) => -r2(g.aus - g.ausAnst))), backgroundColor: "#a23e3e",
        stack: "cashflow", order: 1 },
      { type: "bar", label: "Ausgaben anstehend", data: skaliert(gruppen.map((g) => -r2(g.ausAnst))),
        backgroundColor: "#a23e3e66", stack: "cashflow", order: 1 },
    ] },
    options: { responsive: true, maintainAspectRatio: false,
      scales: { x: { stacked: true, ticks: { maxTicksLimit: 12 } }, y: { stacked: true, ticks: yTicks } },
      plugins: {
        legend: { labels: { filter: (item, daten) => !/anstehend/.test(item.text)
          || daten.datasets[item.datasetIndex].data.some((w) => w) } },
        tooltip: { filter: (c) => c.parsed.y !== 0 || c.dataset.type === "line", callbacks: { label: tooltipBetrag } } } },
  });
  document.getElementById("cashflow-unter").textContent =
    `je ${{ monat: "Monat", quartal: "Quartal", jahr: "Jahr" }[stufe]}, Ausgaben nach unten, dunkle Linie = Überschuss`;

  kategorienRanglisteZeichnen(AUSWERTUNG_DATEN);

  // ── Kennzahlen-Kacheln ──
  const summeEin = cashflowDaten.einnahmen.reduce((a, b) => a + b, 0);
  const summeAus = cashflowDaten.ausgaben.reduce((a, b) => a + b, 0);
  const monate = Math.max(1, cashflowDaten.monate.length);
  const ueberschuss = (summeEin - summeAus) / monate;
  const letzter = saldoDaten.monate[n - 1];
  const kacheln = [];
  if (saldoDaten.modus === "konten" && saldoDaten.stand_heute) {
    const mitRestschuld = inklDarlehen && saldoDaten.darlehen.length > 0;
    const heute = saldoDaten.stand_heute.konten - (mitRestschuld ? saldoDaten.stand_heute.restschuld : 0);
    const ende = saldoDaten.konten.reduce((a, s) => a + s.werte[n - 1], 0)
      + (mitRestschuld ? saldoDaten.darlehen.reduce((a, d) => a + d.werte[n - 1], 0) : 0);
    const diff = ende - heute;
    const anzahl = saldoDaten.konten.length;
    kacheln.push(kachel(mitRestschuld ? "Nettovermögen heute" : "Vermögen heute", betragText(heute),
      `${anzahl} ${anzahl === 1 ? "Konto" : "Konten"}${mitRestschuld ? " minus Restschuld" : ""}`, heute < 0 ? "negativ" : ""));
    const [ej, em] = letzter.split("-").map(Number);
    kacheln.push(kachel(`${mitRestschuld ? "Nettovermögen" : "Vermögen"} ${MONATE_KURZ[em - 1]} ${ej}`, betragText(ende),
      `${diff >= 0 ? "▲" : "▼"} ${betragText(Math.abs(diff))} gegenüber heute`, ende < 0 ? "negativ" : "positiv"));
  } else {
    kacheln.push(kachel("Einnahmen im Zeitraum", betragText(summeEin), "gewählte Kategorien", "positiv"));
    kacheln.push(kachel("Ausgaben im Zeitraum", betragText(summeAus), "gewählte Kategorien", "negativ"));
  }
  kacheln.push(kachel("Ø Überschuss je Monat", betragText(ueberschuss), '<canvas id="spark-chart" height="30"></canvas>',
    ueberschuss < 0 ? "negativ" : ""));
  kacheln.push(kachel("Sparquote", summeEin > 0 ? `${zahlDe(((summeEin - summeAus) / summeEin) * 100, 0)} %` : "–",
    "Überschuss ÷ Einnahmen"));
  document.getElementById("auswertung-kacheln").innerHTML = kacheln.join("");
  if (CHART_SPARK) CHART_SPARK.destroy();
  const netto = gruppen.map((g) => g.ein - g.aus);
  CHART_SPARK = new Chart(document.getElementById("spark-chart"), {
    type: "bar",
    data: { labels: gruppen.map((g) => g.label), datasets: [{ data: netto,
      backgroundColor: netto.map((w) => (w < 0 ? "#a23e3e99" : "#2f7d4f99")), borderRadius: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: false, events: [],
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } } },
  });
}

// Kategorien als sortierte Rangliste (seit v2.3, vorher ein gestapelter
// Balken): Ausgaben oder Einnahmen, Betrag und Anteil, ab Platz 13 „Übrige“.
function kategorienRanglisteZeichnen(d) {
  if (CHART_KATEGORIEN) CHART_KATEGORIEN.destroy();
  const { kategorienDaten, skaliert, betragText } = d;
  const seite = KATEGORIEN_SEITE;
  let zeilen = kategorienDaten.filter((k) => k.typ === seite).sort((a, b) => b.summe - a.summe);
  const gesamt = zeilen.reduce((a, k) => a + k.summe, 0);
  if (zeilen.length > 13) {
    const rest = zeilen.slice(12);
    zeilen = [...zeilen.slice(0, 12), { kategorie: `Übrige (${rest.length})`, summe: rest.reduce((a, k) => a + k.summe, 0),
      anzahl: rest.reduce((a, k) => a + k.anzahl, 0) }];
  }
  const text = seite === "ausgabe" ? "Ausgaben" : "Einnahmen";
  document.getElementById("kategorien-unter").textContent = zeilen.length
    ? `Summe im Zeitraum, Anteil an allen ${text}` : `Keine ${text} im Zeitraum`;
  document.getElementById("kategorien-flaeche").style.height = `${Math.max(120, zeilen.length * 30 + 20)}px`;
  const farbe = seite === "ausgabe" ? "#a23e3e" : "#2f7d4f";
  CHART_KATEGORIEN = new Chart(document.getElementById("kategorien-chart"), {
    type: "bar",
    data: { labels: zeilen.map((k) => k.kategorie),
      datasets: [{ label: text, data: skaliert(zeilen.map((k) => k.summe)),
        backgroundColor: zeilen.map((_, i) => (i < 3 ? farbe : farbe + "8c")), barPercentage: 0.75 }] },
    options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, layout: { padding: { right: 120 } },
      interaction: { mode: "nearest", intersect: true },
      scales: { x: { display: false, beginAtZero: true }, y: { ticks: { color: "#16231fcc" } } },
      plugins: { legend: { display: false },
        tooltip: { callbacks: { title: (e) => e[0].label,
          label: (c) => ` ${betragText(zeilen[c.dataIndex].summe)} · ${zeilen[c.dataIndex].anzahl} Buchungen und Termine` } } } },
    plugins: [{ id: "werte", afterDatasetsDraw(chart) {
      const ctx = chart.ctx;
      ctx.save();
      ctx.font = `12px ${Chart.defaults.font.family}`; ctx.fillStyle = "#16231fcc"; ctx.textBaseline = "middle";
      chart.getDatasetMeta(0).data.forEach((balken, i) => {
        const anteil = gesamt ? Math.round((zeilen[i].summe / gesamt) * 100) : 0;
        ctx.fillText(`${betragText(zeilen[i].summe)} · ${anteil} %`, balken.x + 6, balken.y);
      });
      ctx.restore();
    } }],
  });
}

// Budget-Übersicht lebt seit v1.6.4 im "Übersicht"-Tab des
// Budgets-Bereichs (siehe ladeBudgetAbschnitt) - nicht mehr hier in den
// Auswertungen.
let CHART_BUDGET_UEBERSICHT;

// Budget-Übersicht: EIN vertikaler Balken (Säulendiagramm, seit v1.6.4 -
// bis dahin horizontal) je aktivem Ausgabe-/Einnahme-Budget (Sparziele
// ausgenommen - die haben ein eigenes Soll/Ist-Konzept ohne
// Perioden-Fortschritt), Höhe = Verbrauch in % vom verfügbaren Betrag
// (inkl. Übertrag) der laufenden Periode, Farbe nach Ampelstatus.
async function renderBudgetUebersicht() {
  const alle = await api(`/budgets?x=1${inflationParam("budgets-inflation-schalter")}`);
  const budgets = alle.filter((b) => b.typ !== "sparziel");

  if (CHART_BUDGET_UEBERSICHT) CHART_BUDGET_UEBERSICHT.destroy();
  CHART_BUDGET_UEBERSICHT = new Chart(document.getElementById("budget-uebersicht-chart"), {
    type: "bar",
    data: {
      labels: budgets.map((b) => b.name),
      datasets: [{
        data: budgets.map((b) => Math.min(100, Math.round(b.fortschritt * 10) / 10)),
        backgroundColor: budgets.map((b) => AMPEL_FARBE[b.ampel] || AMPEL_FARBE.gruen),
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { y: { min: 0, max: 100, ticks: { callback: (v) => `${v} %` } } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: (ctx) => {
            const b = budgets[ctx.dataIndex];
            return `${b.fortschritt.toFixed(1)} % · Verbraucht ${euro(b.verbrauch)} von ${euro(b.verfuegbar)} · Rest ${euro(b.restbetrag)}`;
          },
        } },
      },
    },
  });
}

// ─── Admin ────────────────────────────────────────────────────────

// Administration ist in zwei Tabs unterteilt (Stammdaten/System) - reines
// Ein-/Ausblenden per CSS-Klasse, kein Neuladen der Inhalte nötig (die
// <details>-Blöcke bleiben dabei im DOM, nur der umgebende
// .admin-tab-inhalt-Container wird versteckt).
document.querySelectorAll(".admin-tab-knopf").forEach((knopf) => {
  knopf.addEventListener("click", () => {
    document.querySelectorAll(".admin-tab-knopf").forEach((k) => k.classList.remove("aktiv"));
    document.querySelectorAll(".admin-tab-inhalt").forEach((i) => i.classList.remove("aktiv"));
    knopf.classList.add("aktiv");
    document.querySelector(`.admin-tab-inhalt[data-admin-tab-inhalt="${knopf.dataset.adminTab}"]`).classList.add("aktiv");
  });
});

async function ladeAdminAbschnitt() {
  await ladeKategorien();
  renderKategorienBaum();

  const einstellungen = await api("/admin/einstellungen");
  document.getElementById("inflation-input").value = einstellungen.inflationsfaktor ?? 2.0;
  const themeForm = document.getElementById("form-theme-farben");
  THEME_FARBEN_FELDER.forEach((feld) => {
    themeForm[feld].value = einstellungen[feld] || cssVarWert(THEME_CSS_VAR[feld]);
  });

  await ladeKonten();
  await ladePersonen();
  renderPersonenListe();
  await renderRegeln();
  await renderSiri();
  await feiertageAdminLaden().catch(() => {});
  await renderBackups();
  await renderReihenfolgeEditor();
  await ladeZuruecksetzen();
  await renderSicherheit().catch((e) => console.warn(e));
}

// ─── Daten zurücksetzen (Administration, seit v1.8) ───────────────
//
// Ablauf: Auswahl -> Server-Vorschau (Anzahlen, blockierende Punkte, ggf.
// Zielkonto) -> Dialog Schritt 1 (Übersicht) -> Schritt 2 (Übersicht
// nochmals + zufällige Phrase) -> Löschen. Die Phrase kommt vom Server und
// ist an die Auswahl gebunden; geprüft wird sie dort, nicht hier.

// Die Erklärtexte stehen seit v2.1 in der Hilfedatei (hinweis: zuruecksetzen.<hinweis>).
const RESET_ARTEN = [
  { key: "konten_leeren", titel: "Konten leeren (Kontostand auf 0)", zaehler: "konten", einheit: "Konten", konten: true, hinweis: "konten-leeren", anker: "zuruecksetzen.konten-leeren" },
  { key: "konten_loeschen", titel: "Konten löschen", zaehler: "konten", einheit: "Konten", konten: true, hinweis: "konten-loeschen", anker: "zuruecksetzen.konten-loeschen" },
  { key: "ist_buchungen", titel: "Ist-Buchungen", zaehler: "ist_buchungen", einheit: "Buchungen", hinweis: "ist-buchungen", anker: "zuruecksetzen.ist-buchungen" },
  { key: "plan_buchungen", titel: "Plan-Buchungen", zaehler: "plan_buchungen", einheit: "Buchungen", hinweis: "plan-buchungen", anker: "zuruecksetzen.plan-buchungen" },
  { key: "darlehen", titel: "Darlehen", zaehler: "darlehen", einheit: "Darlehen", hinweis: "darlehen", anker: "zuruecksetzen.vertraege" },
  { key: "altersvorsorge", titel: "Altersvorsorge", zaehler: "altersvorsorge", einheit: "Verträge", hinweis: "altersvorsorge", anker: "zuruecksetzen.vertraege" },
  { key: "wiederkehrend", titel: "Wiederkehrende Buchungen (Vorlagen)", zaehler: "wiederkehrend", einheit: "Vorlagen", hinweis: "wiederkehrend", anker: "zuruecksetzen.vertraege" },
];

let RESET_KONTEN = [];
let RESET_ZAEHLER = {};
let RESET_VORSCHAU = null;
let RESET_AUSWAHL = null;

function resetEsc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function resetZahl(n) { return Number(n || 0).toLocaleString("de-DE"); }

function resetFehlertext(e) {
  const m = String(e && e.message || e).match(/\{.*\}/s);
  if (m) { try { const d = JSON.parse(m[0]).detail; return typeof d === "string" ? d : JSON.stringify(d); } catch (_) { /* Rohtext */ } }
  return String(e && e.message || e);
}

async function ladeZuruecksetzen() {
  [RESET_KONTEN, RESET_ZAEHLER] = await Promise.all([
    api("/konten?nur_aktive=false"), api("/admin/zuruecksetzen/uebersicht")]);
  renderZuruecksetzenOptionen();
}

function renderZuruecksetzenOptionen() {
  document.getElementById("reset-optionen").innerHTML = RESET_ARTEN.map((a) => `
    <div class="reset-karte" data-art="${a.key}">
      <div class="reset-kopf">
        <label><input type="checkbox" class="reset-art" value="${a.key}"> <strong>${a.titel}</strong></label>
        <span class="reset-anzahl">${resetZahl(RESET_ZAEHLER[a.zaehler])} ${a.einheit}</span>
        <button type="button" class="hilfe-icon hilfe-knopf" aria-expanded="false"
                aria-label="Hilfe zu ${a.titel}" title="Was wird gelöscht?">?</button>
      </div>
      <div class="hilfetext" hidden>${hinweisHtml("zuruecksetzen." + a.hinweis)}
        <a href="#" class="hilfe-link" data-anker="${a.anker}">Mehr in der Hilfe</a></div>
      ${a.key === "ist_buchungen" ? `<div class="reset-unterbereich reset-datum" hidden>
        <label for="reset-ist-bis">Ist-Buchungen und Übertragungen löschen bis einschließlich</label>
        <input type="date" id="reset-ist-bis" value="${heuteISO()}">
      </div>` : ""}
      ${a.konten ? `<div class="reset-unterbereich reset-konten" hidden>
        <label class="reset-alle"><input type="checkbox" class="reset-konto-alle"> Alle Konten</label>
        ${RESET_KONTEN.map((k) => `<label><input type="checkbox" class="reset-konto" value="${k.id}">
          ${resetEsc(k.name)} <span class="hinweis">· ${resetEsc(k.typ)} · ${euro(k.saldo)}${k.aktiv ? "" : " · deaktiviert"}</span></label>`).join("")
          || '<span class="leer">Keine Konten vorhanden</span>'}
      </div>` : ""}
    </div>`).join("");
}

document.getElementById("reset-optionen").addEventListener("click", (e) => {
  const knopf = e.target.closest(".hilfe-knopf");
  if (!knopf) return;
  const text = knopf.closest(".reset-karte").querySelector(".hilfetext");
  text.hidden = !text.hidden;
  knopf.setAttribute("aria-expanded", String(!text.hidden));
});

document.getElementById("reset-optionen").addEventListener("change", (e) => {
  const karte = e.target.closest(".reset-karte");
  if (!karte) return;
  if (e.target.classList.contains("reset-art")) {
    karte.classList.toggle("gewaehlt", e.target.checked);
    karte.querySelectorAll(".reset-unterbereich").forEach((b) => (b.hidden = !e.target.checked));
  } else if (e.target.classList.contains("reset-konto-alle")) {
    karte.querySelectorAll(".reset-konto").forEach((c) => (c.checked = e.target.checked));
  } else if (e.target.classList.contains("reset-konto")) {
    const alle = [...karte.querySelectorAll(".reset-konto")];
    karte.querySelector(".reset-konto-alle").checked = alle.every((c) => c.checked);
  }
});

function resetAuswahlLesen() {
  const ids = (art) => [...document.querySelectorAll(`.reset-karte[data-art="${art}"] .reset-konto:checked`)]
    .map((c) => Number(c.value));
  return {
    arten: [...document.querySelectorAll(".reset-art:checked")].map((c) => c.value),
    konten_leeren_ids: ids("konten_leeren"),
    konten_loeschen_ids: ids("konten_loeschen"),
    ziel_konto_id: null,
    ist_bis: document.getElementById("reset-ist-bis")?.value || heuteISO(),
  };
}

function resetStatus(text, fehler = false) {
  const el = document.getElementById("reset-status");
  el.textContent = text;
  el.style.color = fehler ? "var(--rot)" : "";
}

async function resetVorschauLaden(body) {
  RESET_VORSCHAU = await api("/admin/zuruecksetzen/vorschau", { method: "POST", body: JSON.stringify(body) });
  RESET_AUSWAHL = body;
}

document.getElementById("reset-start").addEventListener("click", async () => {
  resetStatus("");
  const body = resetAuswahlLesen();
  if (!body.arten.length) return resetStatus("Bitte mindestens eine Datenart auswählen.", true);
  for (const [art, ids] of [["konten_leeren", body.konten_leeren_ids], ["konten_loeschen", body.konten_loeschen_ids]]) {
    if (body.arten.includes(art) && !ids.length) {
      return resetStatus(`Bitte für „${RESET_ARTEN.find((a) => a.key === art).titel}“ mindestens ein Konto auswählen.`, true);
    }
  }
  if (body.arten.includes("ist_buchungen") && !document.getElementById("reset-ist-bis").value) {
    return resetStatus("Bitte für „Ist-Buchungen“ ein Datum angeben.", true);
  }
  try { await resetVorschauLaden(body); } catch (e) { return resetStatus(resetFehlertext(e), true); }
  resetDialogSchritt1();
  document.getElementById("reset-dialog").showModal();
});

function resetZusammenfassungHtml(v) {
  const zeilen = v.zeilen.map((z) => `
    <tr>
      <td><strong>${resetEsc(z.titel)}</strong>${z.namen ? `<div class="hinweis">${z.namen.map(resetEsc).join(", ")}</div>` : ""}
        ${z.zusatz.filter((x) => x.anzahl > 0).map((x) => `<div class="hinweis">${resetEsc(x.label)}: ${resetZahl(x.anzahl)}</div>`).join("")}</td>
      <td class="rechts zahl">${resetZahl(z.anzahl)} ${resetEsc(z.einheit)}</td>
    </tr>`).join("");
  const gesamt = v.buchungen_geloescht_gesamt == null ? "" : `
    <tr><td><strong>Buchungen insgesamt gelöscht</strong><div class="hinweis">ohne Doppelzählung bei überschneidenden Auswahlen</div></td>
        <td class="rechts zahl"><strong>${resetZahl(v.buchungen_geloescht_gesamt)}</strong></td></tr>`;
  const hinweis = v.zeilen.length > 1
    ? '<p class="hinweis">Die Anzahlen gelten je Datenart einzeln. Überschneidungen (z. B. Ist-Buchungen und Konten löschen) werden nur einmal gelöscht.</p>' : "";
  return `<table class="reset-uebersicht"><tbody>${zeilen}${gesamt}</tbody></table>${hinweis}`;
}

function resetMeldungenHtml(v) {
  return (v.warnungen || []).map((w) => `<div class="warnung">${resetEsc(w)}</div>`).join("")
    + (v.blockiert || []).map((w) => `<div class="warnung"><strong>Nicht möglich:</strong> ${resetEsc(w)}</div>`).join("");
}

function resetDialogSchritt1() {
  const v = RESET_VORSCHAU;
  const ziel = v.ziel_erforderlich ? `
    <div class="reset-ziel">
      <label for="reset-ziel">Auf welches Konto sollen die Daten der gelöschten Konten umgestellt werden?</label>
      <select id="reset-ziel">
        <option value="">– bitte wählen –</option>
        ${v.ziel_kandidaten.map((k) => `<option value="${k.id}" ${RESET_AUSWAHL.ziel_konto_id === k.id ? "selected" : ""}>
          ${resetEsc(k.name)}${k.aktiv ? "" : " (deaktiviert)"}</option>`).join("")}
      </select>
      <p class="hinweis">Gilt für alle gelöschten Konten gemeinsam: Buchungen, wiederkehrende Vorlagen,
        Altersvorsorge-Verträge sowie Zahlungs- bzw. Trägerkonten von Darlehen und Sparzielen.</p>
    </div>` : "";
  document.getElementById("reset-dialog-inhalt").innerHTML = `
    <h2>Diese Daten werden gelöscht</h2>
    ${resetMeldungenHtml(v)}
    ${resetZusammenfassungHtml(v)}
    ${ziel}
    <p class="hinweis">Vorher wird automatisch ein Backup angelegt: „${resetEsc(v.backup_beschreibung)}“.</p>
    <div class="warnung" id="reset-dialog-fehler" hidden></div>
    <div class="reihen-werkzeuge reset-knoepfe">
      <button type="button" class="knopf sekundaer" id="reset-abbrechen">Abbrechen</button>
      <button type="button" class="knopf gefahr" id="reset-weiter" ${v.bereit ? "" : "disabled"}>Weiter</button>
    </div>`;
  document.getElementById("reset-abbrechen").addEventListener("click", resetDialogSchliessen);
  document.getElementById("reset-weiter").addEventListener("click", resetDialogSchritt2);
  const sel = document.getElementById("reset-ziel");
  if (sel) sel.addEventListener("change", async () => {
    try {
      await resetVorschauLaden({ ...RESET_AUSWAHL, ziel_konto_id: sel.value ? Number(sel.value) : null });
      resetDialogSchritt1();
    } catch (e) {
      const fehler = document.getElementById("reset-dialog-fehler");
      fehler.textContent = resetFehlertext(e);
      fehler.hidden = false;
    }
  });
}

function resetDialogSchritt2() {
  const v = RESET_VORSCHAU;
  document.getElementById("reset-dialog-inhalt").innerHTML = `
    <h2>Letzte Bestätigung</h2>
    ${resetMeldungenHtml(v)}
    ${resetZusammenfassungHtml(v)}
    <p>Zur Bestätigung diese Phrase eintippen:</p>
    <div class="reset-phrase" id="reset-phrase-anzeige">${resetEsc(v.phrase)}</div>
    <input id="reset-phrase-eingabe" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Phrase eingeben">
    <div class="warnung" id="reset-fehler" hidden></div>
    <div class="reihen-werkzeuge reset-knoepfe">
      <button type="button" class="knopf sekundaer" id="reset-zurueck">Zurück</button>
      <button type="button" class="knopf gefahr" id="reset-ausfuehren" disabled>Endgültig löschen</button>
    </div>`;
  const eingabe = document.getElementById("reset-phrase-eingabe");
  const knopf = document.getElementById("reset-ausfuehren");
  eingabe.addEventListener("input", () => {
    knopf.disabled = eingabe.value.trim().toLowerCase() !== v.phrase.toLowerCase();
  });
  document.getElementById("reset-zurueck").addEventListener("click", resetDialogSchritt1);
  knopf.addEventListener("click", async () => {
    knopf.disabled = true;
    const fehler = document.getElementById("reset-fehler");
    fehler.hidden = true;
    try {
      const antwort = await api("/admin/zuruecksetzen/ausfuehren", {
        method: "POST", body: JSON.stringify({ ...RESET_AUSWAHL, token: v.token, phrase: eingabe.value }) });
      resetDialogSchliessen();
      resetStatus(`Gelöscht. Backup: ${antwort.backup}`);
      await ladeKonten();
      await Promise.all([ladeZuruecksetzen(), renderBackups()]);
    } catch (e) {
      fehler.textContent = resetFehlertext(e);
      fehler.hidden = false;
      knopf.disabled = eingabe.value.trim().toLowerCase() !== v.phrase.toLowerCase();
    }
  });
  eingabe.focus();
}

function resetDialogSchliessen() {
  const dialog = document.getElementById("reset-dialog");
  if (dialog.open) dialog.close();
  RESET_VORSCHAU = null;
  RESET_AUSWAHL = null;
}

document.getElementById("reset-dialog").addEventListener("cancel", () => { RESET_VORSCHAU = null; RESET_AUSWAHL = null; });

// ─── Menü-Reihenfolge (Administration) ─────────────────────────────

let REIHENFOLGE_AKTUELL = [];

async function renderReihenfolgeEditor() {
  REIHENFOLGE_AKTUELL = await ladeNavReihenfolge();
  reihenfolgeEditorZeichnen();
}

function reihenfolgeEditorZeichnen() {
  const el = document.getElementById("reihenfolge-editor");
  el.innerHTML = REIHENFOLGE_AKTUELL.map((eintrag, i) => `
    <div class="reihenfolge-zeile ${eintrag.trenner_davor ? "reihenfolge-trenner-linie" : ""}">
      <span class="reihenfolge-name">${NAV_LABELS[eintrag.ziel] || eintrag.ziel}</span>
      <label><input type="checkbox" ${eintrag.trenner_davor ? "checked" : ""}
             onchange="reihenfolgeTrennerUmschalten(${i}, this.checked)"> Trenner davor</label>
      <button type="button" class="knopf sekundaer klein" ${i === 0 ? "disabled" : ""} onclick="reihenfolgeVerschieben(${i}, -1)">↑</button>
      <button type="button" class="knopf sekundaer klein" ${i === REIHENFOLGE_AKTUELL.length - 1 ? "disabled" : ""} onclick="reihenfolgeVerschieben(${i}, 1)">↓</button>
    </div>`).join("");
}

function reihenfolgeTrennerUmschalten(index, wert) {
  REIHENFOLGE_AKTUELL[index].trenner_davor = wert;
  reihenfolgeEditorZeichnen();
}

function reihenfolgeVerschieben(index, richtung) {
  const ziel = index + richtung;
  if (ziel < 0 || ziel >= REIHENFOLGE_AKTUELL.length) return;
  [REIHENFOLGE_AKTUELL[index], REIHENFOLGE_AKTUELL[ziel]] = [REIHENFOLGE_AKTUELL[ziel], REIHENFOLGE_AKTUELL[index]];
  reihenfolgeEditorZeichnen();
}

document.getElementById("reihenfolge-speichern").addEventListener("click", async () => {
  const wert = encodeURIComponent(JSON.stringify(REIHENFOLGE_AKTUELL));
  await api(`/admin/einstellungen/nav_reihenfolge?value=${wert}`, { method: "PUT" });
  await renderNavigation();
  const status = document.getElementById("reihenfolge-status");
  status.textContent = "Gespeichert.";
  setTimeout(() => { status.textContent = ""; }, 2500);
});

function renderPersonenListe() {
  document.getElementById("personen-liste").innerHTML = PERSONEN.map((p) => `
    <div style="display:flex; align-items:center; gap:8px; padding:5px 0; ${p.aktiv ? "" : "opacity:.55"}">
      <span style="width:10px; height:10px; border-radius:50%; background:${p.farbe || "var(--tinte-45)"}; flex-shrink:0"></span>
      <span style="flex:1">${p.name}${p.aktiv ? "" : ' <span class="hinweis">(deaktiviert)</span>'}</span>
      <button class="knopf sekundaer klein" onclick="personBearbeiten(${p.id})">Ändern</button>
      ${p.aktiv
        ? `<button class="knopf gefahr klein" onclick="personLoeschen(${p.id})">Löschen</button>`
        : `<button class="knopf sekundaer klein" onclick="personReaktivieren(${p.id})">Reaktivieren</button>`}
    </div>`).join("") || '<p class="leer">Noch keine Personen angelegt.</p>';
}

document.getElementById("form-person").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  await api("/personen", { method: "POST", body: JSON.stringify({ name: d.name, farbe: d.farbe || null }) });
  e.target.reset();
  await ladePersonen();
  renderPersonenListe();
});

async function personBearbeiten(id) {
  const p = PERSONEN.find((x) => x.id === id);
  if (!p) return;
  const neuerName = prompt("Name:", p.name);
  if (neuerName === null || !neuerName.trim()) return;
  await api(`/personen/${id}`, { method: "PUT", body: JSON.stringify({ name: neuerName.trim() }) });
  await ladePersonen();
  renderPersonenListe();
}

async function personLoeschen(id) {
  if (!confirm("Person deaktivieren? Bestehende Zuordnungen (Konten, Vorlagen, Verträge) bleiben erhalten und lassen sich weiter über die Person filtern.")) return;
  await api(`/personen/${id}`, { method: "DELETE" });
  await ladePersonen();
  renderPersonenListe();
}

async function personReaktivieren(id) {
  await api(`/personen/${id}`, { method: "PUT", body: JSON.stringify({ aktiv: true }) });
  await ladePersonen();
  renderPersonenListe();
}

function renderKategorienBaum() {
  const TYP_FARBE = { einnahme: "var(--gruen)", ausgabe: "var(--rot)" };
  // "geschützt" richtet sich ausschließlich nach system_key (nie über feste
  // IDs - siehe db.py-Modul-Docstring: in einer gewachsenen Datenbank
  // können IDs längst durch eigene Kategorien des Nutzers belegt sein).
  const ebene = (parentId, tiefe) =>
    KATEGORIEN.filter((k) => k.parent_id === parentId)
      .map((k) => {
        const geschuetzt = !!k.system_key;
        const farbe = TYP_FARBE[k.typ] || "var(--tinte-45)";
        return `
        <div style="display:flex; align-items:center; gap:8px; padding:5px 0 5px ${tiefe * 20}px;
                    border-left:${tiefe ? "2px solid var(--linie)" : "none"}; margin-left:${tiefe ? "9px" : "0"}">
          <span style="width:7px; height:7px; border-radius:50%; background:${farbe}; flex-shrink:0"></span>
          <span style="flex:1">${k.name}</span>
          ${geschuetzt
            ? '<span class="hinweis" style="font-size:11px">fest vorgegeben</span>'
            : `<button class="knopf sekundaer klein" style="padding:2px 8px; font-size:11px"
                 onclick="kategorieBearbeiten(${k.id})" title="Kategorie ändern">Ändern</button>
               <button class="knopf sekundaer klein" style="padding:2px 8px; font-size:11px"
                 onclick="kategorieLoeschen(${k.id})" title="Kategorie löschen">✕</button>`}
        </div>
        ${ebene(k.id, tiefe + 1)}`;
      }).join("");
  document.getElementById("kategorien-baum").innerHTML =
    `<div style="margin-bottom:8px" class="hinweis">● grün = Einnahme · ● rot = Ausgabe · ● grau = neutral</div>` +
    ebene(null, 0);
}

async function kategorieLoeschen(id) {
  if (!confirm("Kategorie löschen?")) return;
  try {
    await api(`/kategorien/${id}`, { method: "DELETE" });
  } catch (err) {
    alert(err.message);
    return;
  }
  await kategorieFormularZuruecksetzen();
  renderKategorienBaum();
}

// Alle Nachfahren (inkl. der Kategorie selbst) - beim Ändern aus der
// Oberkategorie-Auswahl entfernt, damit sich eine Kategorie nicht
// versehentlich unter sich selbst (oder einem eigenen Kind) einhängen lässt.
function kategorieUndNachfahren(id) {
  const ids = new Set([id]);
  let veraendert = true;
  while (veraendert) {
    veraendert = false;
    KATEGORIEN.forEach((k) => {
      if (k.parent_id !== null && ids.has(k.parent_id) && !ids.has(k.id)) {
        ids.add(k.id);
        veraendert = true;
      }
    });
  }
  return ids;
}

async function kategorieBearbeiten(id) {
  const k = KATEGORIEN.find((x) => x.id === id);
  if (!k) return;
  await ladeKategorien();
  const form = document.getElementById("form-kategorie");
  form.name.value = k.name;
  const ausschluss = kategorieUndNachfahren(id);
  Array.from(form.parent_id.options).forEach((opt) => {
    if (opt.value && ausschluss.has(Number(opt.value))) opt.remove();
  });
  form.parent_id.value = k.parent_id || "";
  form.dataset.bearbeitetId = id;
  document.getElementById("kategorie-form-titel").textContent = "Kategorie ändern";
  document.getElementById("kategorie-submit").textContent = "Änderung speichern";
  document.getElementById("kategorie-verwerfen").style.display = "inline-block";
  form.scrollIntoView({ behavior: "smooth" });
}

async function kategorieFormularZuruecksetzen() {
  const form = document.getElementById("form-kategorie");
  form.reset();
  delete form.dataset.bearbeitetId;
  document.getElementById("kategorie-form-titel").textContent = "Neue Kategorie";
  document.getElementById("kategorie-submit").textContent = "Anlegen";
  document.getElementById("kategorie-verwerfen").style.display = "none";
  await ladeKategorien();  // stellt die vollständige (ungefilterte) Oberkategorie-Liste wieder her
}

document.getElementById("kategorie-verwerfen").addEventListener("click", kategorieFormularZuruecksetzen);

document.getElementById("form-kategorie").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  const koerper = JSON.stringify({ name: d.name, parent_id: d.parent_id ? Number(d.parent_id) : null });
  const id = e.target.dataset.bearbeitetId;
  try {
    if (id) await api(`/kategorien/${id}`, { method: "PUT", body: koerper });
    else await api("/kategorien", { method: "POST", body: koerper });
  } catch (err) {
    alert(err.message);
    return;
  }
  await kategorieFormularZuruecksetzen();
  renderKategorienBaum();
});

document.getElementById("form-inflation").addEventListener("submit", async (e) => {
  e.preventDefault();
  const wert = e.target.inflationsfaktor.value;
  await api(`/admin/einstellungen/inflationsfaktor?value=${wert}`, { method: "PUT" });
});

async function renderBackups() {
  const liste = await api("/admin/backups");
  document.getElementById("backups-tabelle").innerHTML = liste.map((b) => `
    <tr><td>${new Date(b.erstellt_am).toLocaleString("de-DE")}</td><td>${b.dateiname}</td><td>${b.typ}</td>
    <td>${b.beschreibung ? resetEsc(b.beschreibung) : "–"}</td>
    <td class="rechts"><button type="button" class="knopf sekundaer klein" data-wh-backup="${resetEsc(b.dateiname)}">Wiederherstellen</button></td></tr>`
  ).join("") || `<tr><td colspan="5" class="leer">Noch keine Backups</td></tr>`;
}

// ─── Datenbank wiederherstellen (seit v2.4) ────────────────────────
// Schritt 1 prüft die Datei auf dem Server und liefert Kennzahlen samt
// Bestätigungsphrase, Schritt 2 spielt nach Eingabe der Phrase ein. Danach
// lädt die Seite neu, weil alle zwischengespeicherten Daten veraltet sind.

let WH_VORSCHAU = null;

function whStatus(text, fehler = true) {
  const el = document.getElementById("wh-status");
  el.textContent = text;
  el.hidden = !text;
  el.className = fehler ? "warnung" : "hinweis";
}

function whDatum(iso) {
  return iso ? iso.split("-").reverse().join(".") : "–";
}

function whGroesse(bytes) {
  return bytes >= 1048576 ? `${zahlDe(bytes / 1048576, 1)} MB` : `${zahlDe(bytes / 1024, 0)} KB`;
}

function whDialogZeigen(v) {
  WH_VORSCHAU = v;
  const zeile = (titel, a, d) => `<tr><td>${titel}</td><td class="rechts zahl">${a ?? "–"}</td><td class="rechts zahl">${d ?? "–"}</td></tr>`;
  const a = v.aktuell || {};
  const d = v.datei;
  document.getElementById("wh-dialog-inhalt").innerHTML = `
    <h2>Datenbank wiederherstellen</h2>
    <p>Quelle: <strong>${resetEsc(v.bezeichnung)}</strong>. Die Datei ist geprüft und lesbar.</p>
    <table><thead><tr><th></th><th class="rechts">Jetzt</th><th class="rechts">Aus der Datei</th></tr></thead><tbody>
      ${zeile("Konten", a.konten, d.konten)}${zeile("Buchungen", a.buchungen, d.buchungen)}
      ${zeile("Kategorien", a.kategorien, d.kategorien)}
      ${zeile("Letzte Ist-Buchung", whDatum(a.letzte_buchung), whDatum(d.letzte_buchung))}
      ${zeile("Größe", a.groesse ? whGroesse(a.groesse) : "–", whGroesse(d.groesse))}
    </tbody></table>
    <p class="hinweis">${hinweisHtml("admin.wiederherstellen-bestaetigen")}</p>
    <p>Zur Bestätigung diese Phrase eintippen:</p>
    <div class="reset-phrase">${resetEsc(v.phrase)}</div>
    <input id="wh-phrase-eingabe" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Phrase eingeben">
    <div class="warnung" id="wh-fehler" hidden></div>
    <div class="reihen-werkzeuge reset-knoepfe">
      <button type="button" class="knopf sekundaer" id="wh-abbrechen">Abbrechen</button>
      <button type="button" class="knopf gefahr" id="wh-ausfuehren" disabled>Jetzt wiederherstellen</button>
    </div>`;
  const dialog = document.getElementById("wh-dialog");
  if (!dialog.open) dialog.showModal();
  const eingabe = document.getElementById("wh-phrase-eingabe");
  const knopf = document.getElementById("wh-ausfuehren");
  eingabe.addEventListener("input", () => {
    knopf.disabled = eingabe.value.trim().toLowerCase() !== v.phrase.toLowerCase();
  });
  document.getElementById("wh-abbrechen").addEventListener("click", () => dialog.close());
  knopf.addEventListener("click", async () => {
    knopf.disabled = true;
    const fehler = document.getElementById("wh-fehler");
    fehler.hidden = true;
    try {
      const e = await api("/admin/wiederherstellen/ausfuehren", {
        method: "POST", body: JSON.stringify({ quelle: v.quelle, token: v.token, phrase: eingabe.value }) });
      const mig = (e.start && e.start.migration) || [];
      document.getElementById("wh-dialog-inhalt").innerHTML = `
        <h2 style="color:var(--gruen)">Wiederhergestellt</h2>
        <p>Der vorherige Stand liegt als Backup <strong>${resetEsc(e.backup_vorher)}</strong> in der Backup-Liste.</p>
        <p>Jetzt: ${resetZahl(e.kennzahlen.konten)} Konten, ${resetZahl(e.kennzahlen.buchungen)} Buchungen,
          letzte Ist-Buchung ${whDatum(e.kennzahlen.letzte_buchung)}.</p>
        ${mig.length ? `<p>Beim Start angepasst:</p><ul>${mig.map((m) => `<li>${resetEsc(m)}</li>`).join("")}</ul>` : ""}
        <div class="reihen-werkzeuge reset-knoepfe">
          <button type="button" class="knopf" id="wh-neu-laden">Seite neu laden</button>
        </div>`;
      document.getElementById("wh-neu-laden").addEventListener("click", () => location.reload());
    } catch (err) {
      fehler.textContent = resetFehlertext(err);
      fehler.hidden = false;
      knopf.disabled = eingabe.value.trim().toLowerCase() !== v.phrase.toLowerCase();
    }
  });
  eingabe.focus();
}

document.getElementById("wh-datei-feld").addEventListener("change", (e) => {
  const datei = e.target.files[0];
  document.getElementById("wh-datei-name").textContent = datei ? datei.name : "Keine Datei ausgewählt";
  document.getElementById("wh-pruefen").disabled = !datei;
  whStatus("");
});

document.getElementById("wh-pruefen").addEventListener("click", async () => {
  const datei = document.getElementById("wh-datei-feld").files[0];
  if (!datei) return;
  const knopf = document.getElementById("wh-pruefen");
  knopf.disabled = true;
  whStatus("Datei wird hochgeladen und geprüft …", false);
  try {
    const form = new FormData();
    form.append("datei", datei);
    const geheimnis = document.getElementById("wh-geheimnis").value;
    if (geheimnis) form.append("geheimnis", geheimnis);
    const antwort = await fetch(API + "/admin/wiederherstellen/hochladen", { method: "POST", body: form, headers: schutzKopf() });
    const daten = await antwort.json().catch(() => ({}));
    if (!antwort.ok) throw new Error(daten.detail || `Fehler ${antwort.status}`);
    whStatus("");
    whDialogZeigen(daten);
  } catch (err) {
    whStatus(resetFehlertext(err));
  } finally {
    knopf.disabled = false;
  }
});

document.getElementById("backups-tabelle").addEventListener("click", async (e) => {
  const knopf = e.target.closest("[data-wh-backup]");
  if (!knopf) return;
  try {
    whDialogZeigen(await api("/admin/wiederherstellen/backup", {
      method: "POST", body: JSON.stringify({ dateiname: knopf.dataset.whBackup }) }));
  } catch (err) {
    document.getElementById("admin-wiederherstellen-block").open = true;
    whStatus(resetFehlertext(err));
  }
});

document.getElementById("backup-jetzt").addEventListener("click", async () => {
  await api("/admin/backup", { method: "POST" });
  await renderBackups();
});

document.getElementById("import-datei-feld").addEventListener("change", (e) => {
  const datei = e.target.files[0];
  document.getElementById("import-datei-name").textContent = datei ? datei.name : "Keine Datei ausgewählt";
});

// ─── Export & Import (XLSX-Roundtrip, seit v2.0) ──
document.getElementById("export-herunterladen").addEventListener("click", () => {
  const von = document.getElementById("export-von").value;
  const bis = document.getElementById("export-bis").value;
  if (SCHUTZ.status && SCHUTZ.status.verschluesselung.aktiv) {
    schutzDownloadDialog("export", { von: von || null, bis: bis || null });
    return;
  }
  if (schutzAktiv()) { herunterladen("export", { von: von || null, bis: bis || null }); return; }
  const p = new URLSearchParams();
  if (von) p.set("von", von);
  if (bis) p.set("bis", bis);
  window.location.href = `${API}/admin/export${p.toString() ? "?" + p.toString() : ""}`;
});

let IMPORT_TOKEN = null;

function importVorschauAnzeigen(v, uebernommen = false) {
  const zielDiv = document.getElementById("import-ergebnis");
  if (!v.bereiche.length) {
    zielDiv.innerHTML = `<p class="warnung">${resetEsc(v.meldung || "Keine passenden Tabs bzw. Zeilen in der Datei gefunden.")}</p>`;
    return;
  }
  const kopf = uebernommen
    ? (v.uebernommen
      ? `<p class="hinweis"><strong>Übernommen.</strong> Backup vorher: ${resetEsc(v.backup || "")}</p>`
      : `<p class="warnung">${resetEsc(v.meldung || "Nicht übernommen.")}</p>`)
    : v.fehler
      ? `<p class="warnung"><strong>${v.fehler} Fehler – es wird nichts übernommen.</strong> Bitte die Datei korrigieren und erneut prüfen.</p>`
      : v.aenderungen
        ? `<p class="hinweis"><strong>Keine Fehler.</strong> ${v.aenderungen} Änderung(en) bereit zur Übernahme.</p>`
        : '<p class="hinweis"><strong>Keine Änderungen</strong> – die Datei entspricht dem aktuellen Stand.</p>';
  const tabelle = `<table><thead><tr><th>Tab</th><th class="rechts">neu</th><th class="rechts">geändert</th>
      <th class="rechts">gelöscht</th><th class="rechts">unverändert</th><th class="rechts">Fehler</th></tr></thead><tbody>
      ${v.bereiche.map((b) => `<tr><td>${resetEsc(b.sheet)}</td><td class="rechts">${b.neu}</td>
        <td class="rechts">${b.geaendert}</td><td class="rechts">${b.geloescht}</td>
        <td class="rechts">${b.unveraendert}${b.entfallen ? ` <span class="hinweis">(+${b.entfallen} entfällt)</span>` : ""}</td><td class="rechts ${b.fehler.length ? "negativ" : ""}">${b.fehler.length}</td></tr>`).join("")}
      </tbody></table>`;
  const fehler = v.bereiche.flatMap((b) => b.fehler.map((f) => ({ ...f, sheet: b.sheet })));
  const fehlerListe = fehler.length ? `<h3 style="font-family:var(--schrift-anzeige); font-weight:400">Fehler</h3>
      <table><thead><tr><th>Tab</th><th>Zeile</th><th>Bezeichnung</th><th>Hinweis</th></tr></thead><tbody>
      ${fehler.map((f) => `<tr><td>${resetEsc(f.sheet)}</td><td>${f.zeile}</td><td>${resetEsc(String(f.titel || ""))}</td>
        <td class="warnung" style="background:none;border:none">${resetEsc(String(f.hinweis))}</td></tr>`).join("")}</tbody></table>` : "";
  const details = v.bereiche.flatMap((b) => b.details.map((d) => ({ ...d, sheet: b.sheet })));
  const detailListe = details.length ? `<details style="margin-top:10px"><summary class="hinweis">Einzelne Änderungen anzeigen (${details.length})</summary>
      <table><thead><tr><th>Tab</th><th>Zeile</th><th>Aktion</th><th>Bezeichnung</th><th>Änderung</th></tr></thead><tbody>
      ${details.map((d) => `<tr><td>${resetEsc(d.sheet)}</td><td>${d.zeile}</td><td>${d.aktion}</td>
        <td>${resetEsc(String(d.titel || ""))}</td><td>${(d.felder || []).map(resetEsc).join("<br>")}</td></tr>`).join("")}
      </tbody></table></details>` : "";
  const hinweise = (v.hinweise || []).length
    ? `<div class="warnung">${v.hinweise.map(resetEsc).join("<br>")}</div>` : "";
  // Seit v2.6: Feiertagshinweise zu neuen oder geänderten Zeilen
  const feiertage = (v.feiertagshinweise || []).length
    ? `<div class="feiertag-serie">${hinweisHtml("feiertage.import")}<ul>${v.feiertagshinweise.map((h) =>
        `<li>${resetEsc(h.sheet)}, Zeile ${h.zeile} (${resetEsc(String(h.titel || ""))}): ${resetEsc(h.text)}</li>`).join("")}</ul></div>` : "";
  const knopf = !uebernommen && v.token
    ? `<div class="reihen-werkzeuge" style="margin-top:10px">
         <button class="knopf" id="import-uebernehmen">Übernehmen</button>
         <button class="knopf sekundaer" id="import-verwerfen">Verwerfen</button></div>` : "";
  zielDiv.innerHTML = kopf + tabelle + hinweise + feiertage + fehlerListe + detailListe + knopf;
  IMPORT_TOKEN = uebernommen ? null : v.token;
  document.getElementById("import-uebernehmen")?.addEventListener("click", importUebernehmen);
  document.getElementById("import-verwerfen")?.addEventListener("click", () => {
    IMPORT_TOKEN = null;
    zielDiv.innerHTML = '<p class="hinweis">Verworfen – es wurde nichts übernommen.</p>';
  });
}

async function importUebernehmen() {
  if (!IMPORT_TOKEN) return;
  const knopf = document.getElementById("import-uebernehmen");
  if (knopf) { knopf.disabled = true; knopf.textContent = "Übernehme …"; }
  try {
    const ergebnis = await api("/admin/import/ausfuehren", { method: "POST", body: JSON.stringify({ token: IMPORT_TOKEN }) });
    importVorschauAnzeigen(ergebnis, true);
    await Promise.all([ladeKonten(), ladeKategorien(), ladePersonen(), ladeSparziele()]);
  } catch (err) {
    document.getElementById("import-ergebnis").innerHTML = `<div class="warnung">${resetEsc(apiFehlerText(err))}</div>`;
  }
}

document.getElementById("form-import").addEventListener("submit", async (e) => {
  e.preventDefault();
  const datei = e.target.datei.files[0];
  if (!datei) return;
  const art = e.target.art.value;
  const formDaten = new FormData();
  formDaten.append("datei", datei);
  if (art) formDaten.append("art", art);
  if (e.target.kennwort.value) formDaten.append("kennwort", e.target.kennwort.value);

  const zielDiv = document.getElementById("import-ergebnis");
  zielDiv.innerHTML = '<p class="hinweis">Prüfe …</p>';
  try {
    // Bewusst nicht ueber api(): der Browser muss bei multipart/form-data
    // selbst die Content-Type-Grenze setzen, api() wuerde sie ueberschreiben.
    const antwort = await fetch(API + "/admin/import/vorschau", { method: "POST", body: formDaten, headers: schutzKopf() });
    if (!antwort.ok) throw new Error(`API-Fehler ${antwort.status}: ${await antwort.text()}`);
    importVorschauAnzeigen(await antwort.json());
  } catch (err) {
    zielDiv.innerHTML = `<div class="warnung">${resetEsc(apiFehlerText(err))}</div>`;
  }
  e.target.reset();
  document.getElementById("import-datei-name").textContent = "Keine Datei ausgewählt";
});

document.getElementById("admin-vorzeichen-pruefen").addEventListener("click", async () => {
  const k = await api("/vorzeichen/konflikte");
  const gesamt = k.buchungen.length + k.vorlagen.length;
  const ziel = document.getElementById("admin-vorzeichen-ergebnis");
  document.getElementById("admin-vorzeichen-korrigieren").style.display = gesamt ? "inline-block" : "none";
  if (!gesamt) {
    ziel.innerHTML = '<p class="hinweis">Alle Vorzeichen passen zum Kategorie-Typ – nichts zu korrigieren.</p>';
    return;
  }
  ziel.innerHTML = `<p class="warnung">${gesamt} Eintrag/Einträge mit unpassendem Vorzeichen:
      ${k.buchungen.length} Buchung(en), ${k.vorlagen.length} Vorlage(n).</p>
    <table><thead><tr><th>Datum</th><th>Beschreibung</th><th>Kategorie</th><th class="rechts">Betrag jetzt</th><th class="rechts">wird zu</th></tr></thead><tbody>
    ${k.buchungen.slice(0, 40).map((b) => `<tr><td>${b.datum}</td><td>${b.beschreibung || "–"}</td>
        <td>${b.kategorie}</td><td class="rechts zahl">${euro(b.betrag)}</td>
        <td class="rechts zahl negativ">${euro(b.kategorie_typ === "ausgabe" ? -Math.abs(b.betrag) : Math.abs(b.betrag))}</td></tr>`).join("")}
    </tbody></table>
    ${k.buchungen.length > 40 ? `<p class="hinweis">… und ${k.buchungen.length - 40} weitere.</p>` : ""}`;
});

// ─── Sparziele prüfen (seit v2.0) ──
let SPARZIEL_KONFLIKTE = { buchungen: [], vorlagen: [] };

async function sparzielePruefen() {
  SPARZIEL_KONFLIKTE = await api("/sparziele/konflikte");
  const k = SPARZIEL_KONFLIKTE;
  const gesamt = k.buchungen.length + k.vorlagen.length;
  const ziel = document.getElementById("admin-sparziele-ergebnis");
  document.getElementById("admin-sparziele-loesen").style.display = gesamt ? "inline-block" : "none";
  if (!gesamt) {
    ziel.innerHTML = '<p class="hinweis">Alle Sparziel-Zuordnungen passen – nichts zu tun.</p>';
    return;
  }
  const zeile = (art, r, datum) => `<tr>
      <td><input type="checkbox" class="sz-konflikt" data-art="${art}" data-id="${r.id}" checked style="width:auto"></td>
      <td>${art === "b" ? "Buchung" : "Vorlage"}</td><td>${datum || "–"}</td><td>${resetEsc(r.beschreibung || "–")}</td>
      <td>${resetEsc(r.konto || "–")}${r.zielkonto ? " → " + resetEsc(r.zielkonto) : ""}</td>
      <td>${resetEsc(r.sparziel || "(gelöscht)")}${r.traegerkonto ? ` <span class="hinweis">auf ${resetEsc(r.traegerkonto)}</span>` : ""}</td>
      <td class="rechts zahl">${euro(r.betrag)}</td></tr>`;
  ziel.innerHTML = `<p class="warnung">${gesamt} unstimmige Zuordnung(en): ${k.buchungen.length} Buchung(en),
      ${k.vorlagen.length} Vorlage(n).</p>
    <table><thead><tr><th></th><th>Art</th><th>Datum</th><th>Beschreibung</th><th>Konto</th><th>Sparziel</th>
      <th class="rechts">Betrag</th></tr></thead><tbody>
    ${k.buchungen.map((b) => zeile("b", b, b.datum)).join("")}${k.vorlagen.map((v) => zeile("v", v, "")).join("")}
    </tbody></table>`;
}

document.getElementById("admin-sparziele-pruefen").addEventListener("click", sparzielePruefen);
document.getElementById("admin-sparziele-loesen").addEventListener("click", async () => {
  const markiert = [...document.querySelectorAll(".sz-konflikt:checked")];
  if (!markiert.length) return;
  await api("/sparziele/konflikte/loesen", { method: "POST", body: JSON.stringify({
    buchung_ids: markiert.filter((c) => c.dataset.art === "b").map((c) => Number(c.dataset.id)),
    vorlage_ids: markiert.filter((c) => c.dataset.art === "v").map((c) => Number(c.dataset.id)),
  })});
  await sparzielePruefen();
  await pruefeSparziele();
});

async function pruefeSparziele() {
  const banner = document.getElementById("sparziel-banner");
  if (!banner) return;
  const k = await api("/sparziele/konflikte");
  const gesamt = k.buchungen.length + k.vorlagen.length;
  if (!gesamt) { banner.innerHTML = ""; return; }
  banner.innerHTML = `
    <div class="warnung" style="margin-bottom:18px">
      <strong>${gesamt} unstimmige Sparziel-Zuordnung(en) gefunden.</strong><br>
      Sie zählen nicht zum Sparziel-Stand, denn zum Sparziel zählen nur Übertragungen von oder zu seinem Trägerkonto.
      <div class="reihen-werkzeuge" style="margin-top:8px">
        <button class="knopf" onclick="zurSparzielPruefung()">Ansehen</button>
        <button class="knopf sekundaer" onclick="document.getElementById('sparziel-banner').innerHTML=''">Später</button>
      </div>
    </div>`;
}

function zurSparzielPruefung() {
  zeigeAbschnitt("admin");
  document.querySelector('.admin-tab-knopf[data-admin-tab="stammdaten"]').click();
  const block = document.getElementById("admin-sparziele-block");
  block.open = true;
  sparzielePruefen();
  block.scrollIntoView({ behavior: "smooth" });
}

document.getElementById("admin-vorzeichen-korrigieren").addEventListener("click", async () => {
  await vorzeichenKorrigieren();
  document.getElementById("admin-vorzeichen-pruefen").click();
});

// ─── Bundesland für Feiertage (seit v2.6) ─────────────────────────
// Pflichtangabe beim ersten Start: Dialog ohne Abbrechen. Bestehende
// Installationen bekommen NRW als Vorschlag, der bestätigt werden muss.

function regionenOptionen(regionen, auswahl, mitLeer) {
  return (mitLeer ? '<option value="">– bitte wählen –</option>' : "")
    + regionen.map((r) => `<option value="${r.kuerzel}" ${r.kuerzel === auswahl ? "selected" : ""}>${resetEsc(r.name)}</option>`).join("");
}

async function feiertageAdminLaden() {
  const r = await api("/feiertage/regionen");
  document.getElementById("feiertage-region").innerHTML = regionenOptionen(r.regionen, r.gewaehlt, !r.gewaehlt);
  const jahr = new Date().getFullYear();
  const liste = await api(`/feiertage?von_jahr=${jahr}&bis_jahr=${jahr}`);
  const tage = liste.tage.filter((t) => t.feiertag);
  document.getElementById("feiertage-liste").innerHTML = tage.length
    ? `<table><thead><tr><th>Datum ${jahr}</th><th>Feiertag</th></tr></thead><tbody>${tage.map((t) =>
        `<tr><td>${t.datum}</td><td>${resetEsc(t.feiertag)}</td></tr>`).join("")}</tbody></table>`
    : "";
}

async function feiertagsregionSpeichern(kuerzel) {
  const antwort = await api("/feiertage/region", { method: "PUT", body: JSON.stringify({ kuerzel }) });
  feiertageZuruecksetzen();
  feiertagHinweiseAktualisieren();
  return antwort;
}

document.getElementById("form-feiertage-region").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("feiertage-status");
  try {
    const antwort = await feiertagsregionSpeichern(e.target.kuerzel.value);
    status.textContent = `Gespeichert: ${antwort.name}`;
    await feiertageAdminLaden();
  } catch (err) {
    status.textContent = apiFehlerText(err);
  }
});

async function bundeslandPruefen() {
  const r = await api("/feiertage/regionen");
  if (r.gewaehlt) return;
  const dialog = document.getElementById("bundesland-dialog");
  document.getElementById("bundesland-auswahl").innerHTML = regionenOptionen(r.regionen, r.vorschlag, !r.vorschlag);
  dialog.addEventListener("cancel", (e) => e.preventDefault());   // Pflichtangabe
  document.getElementById("form-bundesland").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!e.target.kuerzel.value) return;
    await feiertagsregionSpeichern(e.target.kuerzel.value);
    dialog.close();
    if (document.getElementById("abschnitt-buchungen")?.classList.contains("aktiv")) await renderBuchungenTabelle();
  });
  dialog.showModal();
}


// ─── Suche ────────────────────────────────────────────────────────

document.getElementById("suche-umschalten").addEventListener("click", () => {
  const b = document.getElementById("suche-bereich");
  const offen = b.style.display !== "none";
  b.style.display = offen ? "none" : "block";
  document.getElementById("suche-umschalten").textContent = offen ? "Suche einblenden" : "Suche ausblenden";
});

document.getElementById("s-suchen").addEventListener("click", sucheAusfuehren);
document.getElementById("s-zuruecksetzen").addEventListener("click", async () => {
  ["s-text", "s-betrag-von", "s-betrag-bis", "s-von", "s-bis"].forEach((id) => (document.getElementById(id).value = ""));
  document.getElementById("s-konto").value = "";
  document.getElementById("s-kategorie").value = "";
  document.getElementById("s-person").value = "";
  document.getElementById("s-typ").value = "";
  document.getElementById("s-ergebnis").textContent = "";
  await renderBuchungenTabelle();
});

async function sucheAusfuehren() {
  const p = new URLSearchParams();
  const feld = (id) => document.getElementById(id).value.trim();
  if (feld("s-text")) p.set("text", feld("s-text"));
  if (feld("s-betrag-von")) p.set("betrag_von", feld("s-betrag-von"));
  if (feld("s-betrag-bis")) p.set("betrag_bis", feld("s-betrag-bis"));
  if (feld("s-von")) p.set("von", feld("s-von"));
  if (feld("s-bis")) p.set("bis", feld("s-bis"));
  if (feld("s-konto")) p.set("konto_id", feld("s-konto"));
  if (feld("s-kategorie")) p.set("kategorie_id_filter", feld("s-kategorie"));
  if (feld("s-person")) p.set("person_id", feld("s-person"));
  if (feld("s-typ")) p.set("typ", feld("s-typ"));
  p.set("inkl_unterkategorien", document.getElementById("s-unter").checked);

  const ergebnis = await api(`/buchungen/suche?${p.toString()}`);
  document.getElementById("s-ergebnis").textContent =
    `${ergebnis.anzahl} Treffer · Summe ${euro(ergebnis.summe)}`;
  document.getElementById("buchungen-tabelle").innerHTML = ergebnis.treffer.map((b) => `
    <tr>
      <td>${b.datum}</td><td>${b.konto_name || "–"}</td><td>${b.kategorie_name || "–"}</td>
      <td><span class="abzeichen ${b.typ.toLowerCase()}">${b.typ}</span></td>
      <td>${b.beschreibung || "–"}</td>
      <td class="rechts zahl ${b.betrag < 0 ? "negativ" : "positiv"}">${euro(b.betrag)}</td>
      <td><button class="knopf gefahr klein" onclick="loescheBuchung(${b.id})">Löschen</button></td>
    </tr>`).join("") || `<tr><td colspan="7" class="leer">Keine Treffer</td></tr>`;
}

// ─── Vorzeichen-Korrektur ─────────────────────────────────────────

async function pruefeVorzeichen() {
  const banner = document.getElementById("vorzeichen-banner");
  if (!banner) return;
  const k = await api("/vorzeichen/konflikte");
  const gesamt = k.buchungen.length + k.vorlagen.length;
  if (!gesamt) { banner.innerHTML = ""; return; }
  banner.innerHTML = `
    <div class="warnung" style="margin-bottom:18px">
      <strong>${gesamt} Buchung(en)/Vorlage(n) mit unpassendem Vorzeichen gefunden.</strong><br>
      Ausgaben müssen negativ, Einnahmen positiv gebucht sein – sonst rechnen Saldo, Cashflow und
      Budgets falsch. Betroffen: ${k.buchungen.length} Buchung(en), ${k.vorlagen.length} Vorlage(n).
      <div class="reihen-werkzeuge" style="margin-top:8px">
        <button class="knopf" onclick="vorzeichenKorrigieren()">Jetzt korrigieren</button>
        <button class="knopf sekundaer" onclick="document.getElementById('vorzeichen-banner').innerHTML=''">Später</button>
      </div>
    </div>`;
}

async function vorzeichenKorrigieren() {
  if (!confirm("Vorzeichen aller betroffenen Buchungen und Vorlagen passend zum Kategorie-Typ umdrehen?")) return;
  const k = await api("/vorzeichen/konflikte");
  const e = await api("/vorzeichen/korrigieren", { method: "POST", body: JSON.stringify({
    buchung_ids: k.buchungen.map((b) => b.id), vorlage_ids: k.vorlagen.map((v) => v.id) })});
  alert(`${e.buchungen_korrigiert} Buchung(en) und ${e.vorlagen_korrigiert} Vorlage(n) korrigiert.`);
  await ladeKonten();
  if (document.getElementById("abschnitt-start").classList.contains("aktiv")) await ladeStart();
}

// ─── Budgets ──────────────────────────────────────────────────────

document.getElementById("budget-typ").addEventListener("change", () => { budgetFelderUmschalten(); budgetKategorieOptionenFiltern(); });
document.getElementById("budget-zeitraum").addEventListener("change", budgetFelderUmschalten);
document.getElementById("budget-uebertrag").addEventListener("change", budgetFelderUmschalten);

function budgetFelderUmschalten() {
  const typ = document.getElementById("budget-typ").value;
  const istSparziel = typ === "sparziel";
  document.querySelectorAll(".budget-sparziel-feld").forEach((f) => (f.style.display = istSparziel ? "block" : "none"));
  document.querySelectorAll(".budget-kategorie-feld").forEach((f) => (f.style.display = istSparziel ? "none" : "block"));
  const benutzerdef = document.getElementById("budget-zeitraum").value === "benutzerdefiniert";
  document.querySelectorAll(".budget-intervall-feld").forEach((f) => (f.style.display = benutzerdef ? "block" : "none"));
  const uebertrag = document.getElementById("budget-uebertrag").checked;
  document.querySelectorAll(".budget-uebertrag-feld").forEach((f) => (f.style.display = uebertrag ? "block" : "none"));
  const hinweis = document.getElementById("budget-uebertrag-hinweis");
  hinweis.style.display = uebertrag ? "block" : "none";
  hinweis.textContent = uebertrag
    ? "Nur in die nächste Periode: Was übrig bleibt, wird einmalig auf die nächste Periode aufgeschlagen, danach beginnt das Budget wieder frisch. — Fortlaufend ansparen: Alle Perioden werden zusammengerechnet, Überschüsse bleiben dauerhaft erhalten, Überschreitungen werden ebenfalls mitgeschleppt. — Deckel (optional): begrenzt nur den positiven Übertrag (Puffer) nach oben, damit er bei selten abgerufenen Budgets nicht unbegrenzt wächst; Überschreitungen werden davon nicht gekappt."
    : "";
}

// Kategorie-Dropdown automatisch auf die zum gewählten Typ (Einnahme/
// Ausgabe) passenden Kategorien einschränken - jede Kategorie trägt (seit
// der Typ-Vererbung, siehe _migriere_kategorie_typen) ihren eigenen Typ,
// nicht nur die Wurzelkategorie.
function budgetKategorieOptionenFiltern() {
  const typ = document.getElementById("budget-typ").value;
  const sel = document.querySelector('#form-budget [name="kategorie_id"]');
  if (!sel || (typ !== "ausgabe" && typ !== "einnahme")) return;
  const bisher = sel.value;
  const passend = (k) => k.typ === typ;
  sel.innerHTML = KATEGORIEN.filter(passend).map((k) =>
    `<option value="${k.id}">${kategoriePfad(k.id)}</option>`).join("");
  if ([...sel.options].some((o) => o.value === bisher)) sel.value = bisher;
}

const AMPEL_FARBE = { gruen: "#2f7d4f", gelb: "#c9a227", rot: "#a23e3e" };
const VERFAHREN_LABEL = { B: "Fix-Prognose", D: "Trend-Prognose" };
// Erklärtext seit v2.1 aus der Hilfedatei (hinweis: budgets.prognose)
function verfahrenAnzeige(code) {
  if (!code || code === "-") return "–";
  const label = VERFAHREN_LABEL[code] || code;
  return `${label} <button type="button" class="hilfe-icon hilfe-sprung-klein" data-anker="budgets.uebersicht"
    title="${resetEsc(hinweisText("budgets.prognose"))}">?</button>`;
}

// Budgets ist seit v1.6.4 in drei Tabs unterteilt (Neues Budget/
// Übersicht/Details) - wie bei Administration wird beim Laden des
// Abschnitts einmalig alles befüllt, das Umschalten selbst ist reines
// Ein-/Ausblenden per CSS-Klasse (siehe .budget-tab-knopf-Handler unten).
document.querySelectorAll(".budget-tab-knopf").forEach((knopf) => {
  knopf.addEventListener("click", () => {
    document.querySelectorAll(".budget-tab-knopf").forEach((k) => k.classList.remove("aktiv"));
    document.querySelectorAll(".budget-tab-inhalt").forEach((i) => i.classList.remove("aktiv"));
    knopf.classList.add("aktiv");
    document.querySelector(`.budget-tab-inhalt[data-budget-tab-inhalt="${knopf.dataset.budgetTab}"]`).classList.add("aktiv");
  });
});

function budgetTabAktivieren(name) {
  document.querySelector(`.budget-tab-knopf[data-budget-tab="${name}"]`).click();
}

async function ladeBudgetAbschnitt() {
  await Promise.all([ladeKonten(), ladeKategorien(), ladePersonen()]);
  budgetKategorieOptionenFiltern();
  document.getElementById("budget-stempel").textContent = "Stand " + new Date().toLocaleDateString("de-DE");
  await Promise.all([renderBudgetListe(), renderBudgetUebersicht(), ladeBudgetDetailsAbschnitt()]);
}

document.getElementById("budget-filter-person").addEventListener("change", renderBudgetListe);
document.getElementById("budgets-inflation-schalter").addEventListener("change", () =>
  Promise.all([renderBudgetListe(), renderBudgetUebersicht(), renderBudgetDetails()]));

async function renderBudgetListe() {
  const alle = await api(`/budgets?x=1${inflationParam("budgets-inflation-schalter")}`);
  const personFilter = document.getElementById("budget-filter-person").value;
  const liste = personFilter ? alle.filter((b) => String(b.person_id) === personFilter) : alle;
  document.getElementById("budget-liste").innerHTML = liste.map((b) => {
    const breite = Math.min(100, Math.max(0, b.fortschritt));
    const farbe = AMPEL_FARBE[b.ampel] || AMPEL_FARBE.gruen;
    const istSparziel = b.typ === "sparziel";
    const pr = b.prognose || {};
    return `
    <div class="karte" style="margin-bottom:12px">
      <div style="display:flex; justify-content:space-between; align-items:baseline">
        <div class="etikett" style="font-size:13px">${b.name} · ${istSparziel ? "Sparziel" : b.typ}${b.person_id ? " · " + personName(b.person_id) : ""}</div>
        <div class="zahl" style="font-weight:600; color:${farbe}">${b.fortschritt.toFixed(1)} %</div>
      </div>
      <div style="background:var(--linie); height:9px; border-radius:5px; margin:8px 0; overflow:hidden">
        <div style="width:${breite}%; height:100%; background:${farbe}"></div>
      </div>
      <div class="hinweis">
        ${istSparziel
          ? `Angespart ${euro(b.verbrauch)} von ${euro(b.zielbetrag || 0)} · Soll bis heute ${euro(b.soll)} (${b.differenz >= 0 ? "erfüllt" : euro(b.differenz) + " im Rückstand"})`
          : `Verbraucht ${euro(b.verbrauch)} von ${euro(b.verfuegbar)} · Rest ${euro(b.restbetrag)}
             ${b.uebertrag_betrag ? ` · davon Übertrag ${euro(b.uebertrag_betrag)}` : ""}
             ${b.uebertrag_deckel ? ` · Puffer ${euro(Math.max(0, b.uebertrag_betrag || 0))} von max. ${euro(b.uebertrag_deckel)}` : ""}
             ${pr.erwartet != null ? ` · Prognose ${euro(pr.erwartet)} (${verfahrenAnzeige(pr.verfahren)})` : ""}
             ${pr.tage_bis_budget != null ? ` · Budget erreicht in ca. ${pr.tage_bis_budget} Tagen` : ""}`}
      </div>
      ${(b.ueberschneidungen || []).length
        ? `<div class="hinweis" style="color:var(--messing)">Überschneidet sich mit: ${b.ueberschneidungen.join(", ")}</div>` : ""}
      ${(b.warnungen_aktiv || []).map((w) => `<div class="warnung">${w.nachricht || `${w.schwelle} % erreicht (${w.typ || "Warnung"})`}</div>`).join("")}
      <div class="reihen-werkzeuge" style="margin-top:8px; justify-content:flex-end">
        <button class="knopf sekundaer klein" onclick="budgetBearbeiten(${b.id})">Ändern</button>
        <button class="knopf gefahr klein" onclick="budgetLoeschen(${b.id})">Löschen</button>
      </div>
    </div>`;
  }).join("") || '<p class="leer">Noch keine Budgets angelegt.</p>';
}

// ─── Budgets · Details-Tab (seit v1.6.4) ───────────────────────────
//
// DropDown mit den Budget-Positionen (Sparziele ausgeschlossen, wie in
// der Übersicht), Standard "Alle". Das Diagramm darunter rechnet - anders
// als die alte, periodenbasierte Historie - in Kalendermonaten (siehe
// budgets.verlauf_je_monat), damit "Alle" und ein einzelnes Budget auf
// derselben Zeitachse dargestellt werden können. Standard-Horizont: 25
// Monate (letzte 12, aktueller und kommende 12 Monate). Die Liste der
// zugehörigen Plan-/Buchungen erscheint nur bei einem einzelnen
// ausgewählten Budget (bei "Alle" wäre sie fachlich uneindeutig, welche
// Buchungen zu welchem Budget gehören, und bleibt deshalb ausgeblendet).
let CHART_BUDGET;

async function ladeBudgetDetailsAbschnitt() {
  const alle = await api("/budgets");
  const budgets = alle.filter((b) => b.typ !== "sparziel");
  const sel = document.getElementById("budget-detail-auswahl");
  const bisher = sel.value;
  sel.innerHTML = '<option value="">Alle</option>' + budgets.map((b) => `<option value="${b.id}">${b.name}</option>`).join("");
  if ([...sel.options].some((o) => o.value === bisher)) sel.value = bisher;
  await renderBudgetDetails();
}

function _monatInput(datum) { return `${datum.getFullYear()}-${String(datum.getMonth() + 1).padStart(2, "0")}`; }

document.getElementById("budget-detail-auswahl").addEventListener("change", renderBudgetDetails);
document.getElementById("budget-detail-horizont").addEventListener("change", () => {
  const benutzerdef = document.getElementById("budget-detail-horizont").value === "benutzerdefiniert";
  document.getElementById("budget-detail-von-feld").style.display = benutzerdef ? "block" : "none";
  document.getElementById("budget-detail-bis-feld").style.display = benutzerdef ? "block" : "none";
  if (benutzerdef) {
    const heute = new Date();
    if (!document.getElementById("budget-detail-von").value)
      document.getElementById("budget-detail-von").value = _monatInput(new Date(heute.getFullYear(), heute.getMonth() - 12, 1));
    if (!document.getElementById("budget-detail-bis").value)
      document.getElementById("budget-detail-bis").value = _monatInput(new Date(heute.getFullYear(), heute.getMonth() + 12, 1));
  }
  renderBudgetDetails();
});
document.getElementById("budget-detail-von").addEventListener("change", renderBudgetDetails);
document.getElementById("budget-detail-bis").addEventListener("change", renderBudgetDetails);

async function renderBudgetDetails() {
  const budgetId = document.getElementById("budget-detail-auswahl").value;
  const benutzerdef = document.getElementById("budget-detail-horizont").value === "benutzerdefiniert";
  const heute = new Date();
  // Immer explizit von/bis mitgeben (auch im Standard-Fall) - damit
  // Diagramm und Buchungsliste garantiert dasselbe Zeitfenster zeigen,
  // statt sich auf zwei getrennte Server-Standardwerte zu verlassen.
  const von = benutzerdef ? document.getElementById("budget-detail-von").value : _monatInput(new Date(heute.getFullYear(), heute.getMonth() - 12, 1));
  const bis = benutzerdef ? document.getElementById("budget-detail-bis").value : _monatInput(new Date(heute.getFullYear(), heute.getMonth() + 12, 1));
  const zeitraumParam = (von ? `&von=${von}` : "") + (bis ? `&bis=${bis}` : "");
  const idParam = budgetId ? `&budget_id=${budgetId}` : "";

  const v = await api(`/budgets/details/verlauf?${idParam}${zeitraumParam}${inflationParam("budgets-inflation-schalter")}`);
  if (CHART_BUDGET) CHART_BUDGET.destroy();
  CHART_BUDGET = new Chart(document.getElementById("budget-chart"), {
    type: "bar",
    data: { labels: v.monate, datasets: [
      { label: "Verbrauch", data: v.verbrauch, backgroundColor: "#2f7d4f", borderRadius: 3, stack: "b" },
      { label: "Prognose", data: v.prognose, backgroundColor: "#2f7d4f66", borderRadius: 3, stack: "b" },
    ]},
    // gestapelt (seit v2.0): im laufenden Monat Verbrauch + anstehende Termine
    options: { responsive: true, maintainAspectRatio: false,
      scales: { y: { stacked: true, suggestedMin: 0, suggestedMax: 0, ticks: { callback: (val) => `${val} €` } },
                x: { stacked: true, ticks: { maxTicksLimit: 14 } } } },
  });

  const buchungenTitel = document.getElementById("budget-detail-buchungen-titel");
  const buchungenTabelle = document.getElementById("budget-detail-buchungen-tabelle");
  const buchungenKoerper = document.getElementById("budget-detail-buchungen");
  if (!budgetId) {
    buchungenTabelle.style.display = "none";
    buchungenTitel.style.display = "none";
    return;
  }
  buchungenTabelle.style.display = "";
  buchungenTitel.style.display = "";
  const liste = await api(`/budgets/${budgetId}/buchungen?${zeitraumParam.replace(/^&/, "")}`);
  buchungenKoerper.innerHTML = liste.map((buchung) => `
    <tr><td>${buchung.datum}</td><td>${buchung.kategorie}</td><td>${buchung.typ}</td>
    <td>${buchung.beschreibung || ""}</td>
    <td class="rechts zahl ${buchung.betrag < 0 ? "negativ" : "positiv"}">${euro(buchung.betrag)}</td></tr>`
  ).join("") || `<tr><td colspan="5" class="leer">Keine Buchungen im Zeitraum</td></tr>`;
}

function budgetFormularZuruecksetzen() {
  const form = document.getElementById("form-budget");
  form.reset();
  delete form.dataset.bearbeitetId;
  document.getElementById("budget-submit").textContent = "Anlegen";
  document.getElementById("budget-verwerfen").style.display = "none";
  document.getElementById("budget-form-titel").textContent = "Neues Budget";
  budgetFelderUmschalten();
  budgetKategorieOptionenFiltern();
}

document.getElementById("budget-verwerfen").addEventListener("click", budgetFormularZuruecksetzen);

async function budgetBearbeiten(id) {
  const b = await api(`/budgets/${id}`);
  const form = document.getElementById("form-budget");
  form.name.value = b.name;
  form.typ.value = b.typ;
  budgetKategorieOptionenFiltern();
  form.betrag.value = b.betrag;
  form.zeitraum.value = b.zeitraum;
  form.startdatum.value = b.startdatum;
  form.enddatum.value = b.enddatum || "";
  form.kategorie_id.value = b.kategorie_id || "";
  form.inkl_unterkategorien.checked = !!b.inkl_unterkategorien;
  form.konto_id.value = b.konto_id || "";
  form.zielbetrag.value = b.zielbetrag || "";
  form.zieldatum.value = b.zieldatum || "";
  form.intervall_wert.value = b.intervall_wert || "";
  form.intervall_einheit.value = b.intervall_einheit || "monate";
  form.uebertrag.checked = !!b.uebertrag;
  if (b.uebertrag_modus) form.uebertrag_modus.value = b.uebertrag_modus;
  form.uebertrag_deckel.value = b.uebertrag_deckel ?? "";
  form.inflationsflag.checked = !!b.inflationsflag;
  form.person_id.value = b.person_id || "";
  try {
    form.warnschwellen.value = JSON.parse(b.warnungen || "[]").map((w) => w.schwelle).join(", ");
  } catch { form.warnschwellen.value = "80"; }
  form.dataset.bearbeitetId = id;
  document.getElementById("budget-submit").textContent = "Änderung speichern";
  document.getElementById("budget-verwerfen").style.display = "inline-block";
  document.getElementById("budget-form-titel").textContent = "Budget ändern";
  budgetFelderUmschalten();
  budgetTabAktivieren("neu");
  form.scrollIntoView({ behavior: "smooth" });
}

async function budgetLoeschen(id) {
  if (!confirm("Budget löschen?")) return;
  await api(`/budgets/${id}`, { method: "DELETE" });
  budgetFormularZuruecksetzen();
  await Promise.all([renderBudgetListe(), renderBudgetUebersicht(), ladeBudgetDetailsAbschnitt()]);
}

document.getElementById("form-budget").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  const schwellen = (d.warnschwellen || "80").split(",").map((x) => parseFloat(x.trim()))
    .filter((x) => !isNaN(x)).map((s) => ({ schwelle: s, typ: s >= 100 ? "Fehler" : "Warnung" }));
  const koerper = JSON.stringify({
    name: d.name, typ: d.typ,
    kategorie_id: d.typ === "sparziel" ? null : (d.kategorie_id ? Number(d.kategorie_id) : null),
    inkl_unterkategorien: !!d.inkl_unterkategorien,
    konto_id: d.typ === "sparziel" && d.konto_id ? Number(d.konto_id) : null,
    zielbetrag: d.zielbetrag ? Number(d.zielbetrag) : null,
    zieldatum: d.zieldatum || null,
    betrag: Number(d.betrag), zeitraum: d.zeitraum,
    intervall_wert: d.intervall_wert ? Number(d.intervall_wert) : null,
    intervall_einheit: d.zeitraum === "benutzerdefiniert" ? d.intervall_einheit : null,
    startdatum: d.startdatum, enddatum: d.enddatum || null,
    uebertrag: !!d.uebertrag, uebertrag_modus: d.uebertrag ? d.uebertrag_modus : null,
    uebertrag_deckel: d.uebertrag && d.uebertrag_deckel ? Number(d.uebertrag_deckel) : null,
    inflationsflag: !!d.inflationsflag,
    warnungen: schwellen,
    person_id: d.person_id ? Number(d.person_id) : null,
  });
  const id = e.target.dataset.bearbeitetId;
  const meldung = document.getElementById("budget-meldung");
  meldung.textContent = "";
  try {
    if (id) await api(`/budgets/${id}`, { method: "PUT", body: koerper });
    else await api("/budgets", { method: "POST", body: koerper });
  } catch (err) {
    // z. B. Trägerkonto eines Sparziels mit Zuordnungen (seit v2.0 gesperrt)
    meldung.textContent = apiFehlerText(err);
    return;
  }
  budgetFormularZuruecksetzen();
  await Promise.all([renderBudgetListe(), renderBudgetUebersicht(), ladeBudgetDetailsAbschnitt()]);
});

// Sparziele (seit v2.0): Auswahl nur mit Sparzielen, deren Trägerkonto Quelle
// oder Ziel der Übertragung ist (Ziel = Einzahlung, Quelle = Entnahme).
let SPARZIELE = [];
function sparzieleFiltern(sel, kontoIds) {
  if (!sel) return;
  const bisher = sel.value;
  const ids = kontoIds.filter(Boolean).map(Number);
  const passend = SPARZIELE.filter((z) => ids.includes(z.konto_id));
  sel.innerHTML = '<option value="">– keines –</option>' +
    passend.map((z) => `<option value="${z.id}">${z.name}</option>`).join("");
  if (passend.some((z) => String(z.id) === bisher)) sel.value = bisher;
}

function buchungSparzieleFiltern() {
  const f = document.getElementById("form-buchung");
  sparzieleFiltern(f.sparziel_id, [f.konto_id.value, f.zielkonto_id.value]);
}

async function ladeSparziele() {
  SPARZIELE = await api("/sparziele");
  buchungSparzieleFiltern();
}

["konto_id", "zielkonto_id"].forEach((n) =>
  document.querySelector(`#form-buchung [name="${n}"]`).addEventListener("change", buchungSparzieleFiltern));


// ─── Jahresübersicht ──────────────────────────────────────────────

let CHART_JAHR;
const FILTER_JAHR = "finanzapp.filter.jahr";

function jahrFilterGeaendert() {
  filterSpeichern(FILTER_JAHR, { konten: MEHRFACH.jahrKonten.speicherWert(), kategorien: MEHRFACH.jahrKategorien.speicherWert() });
  renderJahr();
}
MEHRFACH.jahrKonten = new MehrfachAuswahl(document.getElementById("jahr-filter-konten"), jahrFilterGeaendert);
MEHRFACH.jahrKategorien = new MehrfachAuswahl(document.getElementById("jahr-filter-kategorien"), jahrFilterGeaendert);
(() => {
  const f = filterLaden(FILTER_JAHR);
  if (Array.isArray(f.konten)) MEHRFACH.jahrKonten.setzen(f.konten);
  if (Array.isArray(f.kategorien)) MEHRFACH.jahrKategorien.setzen(f.kategorien);
})();

document.getElementById("jahr-modus").addEventListener("change", () => {
  const kalenderjahr = document.getElementById("jahr-modus").value === "kalenderjahr";
  document.getElementById("jahr-auswahl-feld").style.display = kalenderjahr ? "block" : "none";
  renderJahr();
});

async function ladeJahrAbschnitt() {
  await Promise.all([ladeKonten(), ladeKategorien(), ladePersonen()]);
  const auswahl = document.getElementById("jahr-auswahl");
  if (!auswahl.options.length) {
    const jetzt = new Date().getFullYear();
    for (let j = jetzt + 2; j >= jetzt - 5; j--) {
      auswahl.innerHTML += `<option value="${j}" ${j === jetzt ? "selected" : ""}>${j}</option>`;
    }
    auswahl.addEventListener("change", renderJahr);
    ["jahr-filter-person", "jahr-inflation"].forEach((id) =>
      document.getElementById(id).addEventListener("change", renderJahr));
    // Rollierend 12 Monate ist der neue Standard (seit v1.6.3) - das
    // Kalenderjahr-Auswahlfeld ist dafür nicht relevant und bleibt versteckt.
    document.getElementById("jahr-auswahl-feld").style.display = "none";
  }
  await renderJahr();
}

async function renderJahr() {
  const modus = document.getElementById("jahr-modus").value;
  const jahr = document.getElementById("jahr-auswahl").value;
  const konten = MEHRFACH.jahrKonten.paramWert();
  const kategorien = MEHRFACH.jahrKategorien.paramWert();
  const personId = document.getElementById("jahr-filter-person").value;
  // Mehrfachauswahl seit v2.3 (null = alle, "" = keine)
  const filterParams = (konten !== null ? `&konten=${konten}` : "") + (kategorien !== null ? `&kategorien=${kategorien}` : "")
    + (personId ? `&person_id=${personId}` : "");
  const jahrParam = modus === "kalenderjahr" ? `&jahr=${jahr}` : "";
  const d = await api(`/auswertungen/jahresuebersicht?modus=${modus}${jahrParam}${filterParams}${inflationParam("jahr-inflation")}`);
  const zeitraumLabel = modus === "kalenderjahr" ? jahr : `${d.von.slice(0, 7)} – ${d.bis.slice(0, 7)}`;

  document.getElementById("jahr-kennzahlen").innerHTML = `
    <div class="karte"><div class="etikett">Einnahmen ${zeitraumLabel}</div>
      <div class="betrag zahl positiv">${euro(d.summe_einnahmen)}</div></div>
    <div class="karte"><div class="etikett">Ausgaben ${zeitraumLabel}</div>
      <div class="betrag zahl negativ">${euro(d.summe_ausgaben)}</div></div>
    <div class="karte"><div class="etikett">Saldo ${zeitraumLabel}</div>
      <div class="betrag zahl ${d.summe_saldo < 0 ? "negativ" : "positiv"}">${euro(d.summe_saldo)}</div></div>
    <div class="karte"><div class="etikett">Ø Saldo je Monat</div>
      <div class="betrag zahl ${d.durchschnitt_saldo < 0 ? "negativ" : "positiv"}">${euro(d.durchschnitt_saldo)}</div></div>`;

  document.getElementById("jahr-tabelle").innerHTML = d.monate.map((m) => {
    const kuenftig = d.prognose_ab_monat && m.monat > d.prognose_ab_monat;
    // laufender Monat (seit v2.0): enthält noch anstehende Termine
    const teilweise = !kuenftig && m.anstehend > 0;
    return `<tr${kuenftig ? ' style="opacity:.7"' : ""}>
      <td>${m.monat}${kuenftig ? ' <span class="hinweis">(Prognose)</span>' : ""}${teilweise ? ' <span class="hinweis">(inkl. anstehender Termine)</span>' : ""}</td>
      <td class="rechts zahl positiv">${euro(m.einnahmen)}</td>
      <td class="rechts zahl negativ">${euro(m.ausgaben)}</td>
      <td class="rechts zahl ${m.saldo < 0 ? "negativ" : "positiv"}">${euro(m.saldo)}</td></tr>`;
  }).join("");

  document.getElementById("jahr-kategorien").innerHTML = (d.kategorien || []).map((k) => `
    <tr><td>${k.kategorie}</td><td>${k.typ || "neutral"}</td>
    <td class="rechts zahl">${k.anzahl}</td>
    <td class="rechts zahl ${k.typ === "ausgabe" ? "negativ" : "positiv"}">${euro(k.summe)}</td></tr>`
  ).join("") || `<tr><td colspan="4" class="leer">Keine Buchungen im Zeitraum ${zeitraumLabel}</td></tr>`;

  if (CHART_JAHR) CHART_JAHR.destroy();
  CHART_JAHR = new Chart(document.getElementById("jahr-chart"), {
    type: "bar",
    data: { labels: d.monate.map((m) => m.monat), datasets: [
      { label: "Saldo", data: d.monate.map((m) => m.saldo), type: "line", order: 0,
        borderColor: "#16231f", pointRadius: 2.5, pointBackgroundColor: "#16231f", tension: 0.3 },
      { label: "Einnahmen", data: d.monate.map((m) => m.einnahmen), backgroundColor: "#2f7d4f", order: 1 },
      { label: "Ausgaben", data: d.monate.map((m) => m.ausgaben), backgroundColor: "#a23e3e", order: 1 },
    ]},
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${euro(c.parsed.y)}` } } },
      scales: { y: { suggestedMin: 0, suggestedMax: 0, ticks: { callback: (v) => `${zahlDe(v)} €` } } } },
  });
}

// ─── Kategorisierungs-Regeln ──────────────────────────────────────

async function renderRegeln() {
  const liste = await api("/regeln");
  document.getElementById("regeln-tabelle").innerHTML = liste.map((r) => `
    <tr><td><code>${r.muster}</code></td><td>${r.kategorie_name || "–"}</td>
    <td class="rechts zahl">${r.prioritaet}</td>
    <td><button class="knopf gefahr klein" onclick="regelLoeschen(${r.id})">Löschen</button></td></tr>`
  ).join("") || `<tr><td colspan="4" class="leer">Noch keine Regeln</td></tr>`;
}

async function regelLoeschen(id) {
  await api(`/regeln/${id}`, { method: "DELETE" });
  await renderRegeln();
}

document.getElementById("form-regel").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = formularZuObjekt(e.target);
  await api("/regeln", { method: "POST", body: JSON.stringify({
    muster: d.muster, kategorie_id: Number(d.kategorie_id),
    prioritaet: Number(d.prioritaet) || 100 })});
  e.target.reset();
  await renderRegeln();
});

// ─── Siri-Favoriten & Standardkonto ───────────────────────────────

async function renderSiri() {
  const favoriten = await api("/siri/favoriten");
  const favIds = new Set(favoriten.map((f) => f.id));
  const buchbar = KATEGORIEN.filter((k) => k.typ);
  document.getElementById("siri-favoriten-liste").innerHTML = `
    <p class="hinweis">${favoriten.length} Favorit${favoriten.length === 1 ? "" : "en"} gewählt.</p>
    <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:4px">
      ${buchbar.map((k) => `<label style="font-size:12.5px">
        <input type="checkbox" style="width:auto" ${favIds.has(k.id) ? "checked" : ""}
               onchange="siriFavorit(${k.id}, this.checked, this)"> ${k.name}</label>`).join("")}
    </div>`;
}

async function siriFavorit(id, aktiv, el) {
  try {
    await api(`/siri/favoriten/${id}?aktiv=${aktiv}`, { method: "PUT" });
  } catch (e) {
    el.checked = !aktiv;
    alert("Favorit konnte nicht gespeichert werden.");
  }
  await renderSiri();
}


// ─── Initialisierung ──────────────────────────────────────────────


// ─── Hilfe (seit v2.1) ────────────────────────────────────────────
// Eine Quelle: app/hilfe/hilfe.md. Der Server zerlegt sie (/api/hilfe);
// hier entstehen Hilfe-Ansicht, Suche, „?“-Sprünge und die festen
// Hinweistexte der Oberfläche (data-hinweis / data-hinweis-titel).

let HILFE = null;
let HILFE_RUECKSPRUNG = null;
let HILFE_GERENDERT = false;

async function hilfeLaden() {
  if (!HILFE) HILFE = await api("/hilfe");
  return HILFE;
}

function hinweisHtml(id) {
  return (HILFE && HILFE.hinweise[id] && HILFE.hinweise[id].html) || "";
}

function hinweisText(id) {
  const tmp = document.createElement("div");
  tmp.innerHTML = hinweisHtml(id);
  return tmp.textContent.trim();
}

function hinweiseAnwenden(wurzel = document) {
  wurzel.querySelectorAll("[data-hinweis]").forEach((el) => { el.innerHTML = hinweisHtml(el.dataset.hinweis); });
  wurzel.querySelectorAll("[data-hinweis-titel]").forEach((el) => { el.title = hinweisText(el.dataset.hinweisTitel); });
}

function hilfeKnoepfeEinfuegen(wurzel = document) {
  wurzel.querySelectorAll("[data-hilfe]").forEach((el) => {
    if (el.querySelector(":scope > .hilfe-sprung")) return;
    const knopf = document.createElement("button");
    knopf.type = "button";
    knopf.className = "hilfe-sprung";
    knopf.dataset.anker = el.dataset.hilfe;
    knopf.title = "Hilfe zu diesem Thema";
    knopf.setAttribute("aria-label", "Hilfe zu diesem Thema");
    knopf.textContent = "?";
    el.appendChild(knopf);
  });
}

async function hilfeHinweiseLaden() {
  try {
    await hilfeLaden();
    hinweiseAnwenden();
  } catch (e) {
    console.warn("Hilfe konnte nicht geladen werden", e);
  }
  hilfeKnoepfeEinfuegen();
}

function aktiverAbschnitt() {
  const s = document.querySelector(".abschnitt.aktiv");
  return s ? s.id.replace("abschnitt-", "") : "start";
}

async function hilfeOeffnen(anker) {
  const vorher = aktiverAbschnitt();
  if (vorher !== "hilfe") {
    HILFE_RUECKSPRUNG = { ziel: vorher, scroll: document.querySelector(".hauptbereich").scrollTop };
  }
  await zeigeAbschnitt("hilfe");
  const suche = document.getElementById("hilfe-suche");
  if (suche.value) { suche.value = ""; hilfeTextZeichnen(); }
  hilfeZuKapitel(anker);
}

function hilfeZuKapitel(anker) {
  const ziel = anker && document.getElementById("hilfe-k-" + anker);
  const bereich = document.querySelector(".hauptbereich");
  if (!ziel) { bereich.scrollTop = 0; return; }
  const kopf = document.querySelector(".hilfe-kopf").offsetHeight - 30;
  bereich.scrollTop = ziel.getBoundingClientRect().top - bereich.getBoundingClientRect().top + bereich.scrollTop - kopf - 8;
  ziel.classList.add("hilfe-markiert");
  setTimeout(() => ziel.classList.remove("hilfe-markiert"), 1600);
  document.querySelectorAll("#hilfe-inhalt a").forEach((a) => a.classList.toggle("aktiv", a.dataset.anker === anker));
}

// Ein Listener für alle „?“ und Verweise auf Hilfekapitel
document.addEventListener("click", (e) => {
  const sprung = e.target.closest(".hilfe-sprung, .hilfe-sprung-klein, .hilfe-link");
  if (sprung) {
    e.preventDefault();
    e.stopPropagation();
    hilfeOeffnen(sprung.dataset.anker);
    return;
  }
  const verweis = e.target.closest("#hilfe-text a[href^='#'], #hilfe-inhalt a[href^='#']");
  if (verweis) {
    e.preventDefault();
    const suche = document.getElementById("hilfe-suche");
    if (suche.value) { suche.value = ""; hilfeTextZeichnen(); }
    hilfeZuKapitel(verweis.getAttribute("href").slice(1));
  }
}, true);

document.getElementById("hilfe-zurueck").addEventListener("click", async () => {
  if (!HILFE_RUECKSPRUNG) return;
  const { ziel, scroll } = HILFE_RUECKSPRUNG;
  HILFE_RUECKSPRUNG = null;
  await zeigeAbschnitt(ziel);
  document.querySelector(".hauptbereich").scrollTop = scroll;
});

async function ladeHilfeAbschnitt() {
  document.getElementById("hilfe-zurueck").style.display = HILFE_RUECKSPRUNG ? "inline-block" : "none";
  try {
    await hilfeLaden();
  } catch (e) {
    document.getElementById("hilfe-text").innerHTML = `<p class="warnung">Die Hilfe konnte nicht geladen werden: ${resetEsc(apiFehlerText(e))}</p>`;
    return;
  }
  document.getElementById("hilfe-version").textContent = HILFE.version ? "Programmversion " + HILFE.version : "–";
  const kopf = document.querySelector(".hilfe-kopf");
  document.getElementById("abschnitt-hilfe").style.setProperty("--hilfe-kopf-hoehe", (kopf.offsetHeight - 30 + 10) + "px");
  if (!HILFE_GERENDERT) {
    hilfeInhaltZeichnen();
    hilfeTextZeichnen();
    HILFE_GERENDERT = true;
  }
}

function hilfeInhaltZeichnen() {
  const oben = HILFE.kapitel.filter((k) => k.ebene === 1);
  document.getElementById("hilfe-inhalt").innerHTML = "<ol>" + oben.map((k) => {
    const unter = HILFE.kapitel.filter((u) => u.ebene === 2 && u.eltern === k.anker);
    return `<li><a href="#${k.anker}" data-anker="${k.anker}">${resetEsc(k.titel)}</a>${unter.length
      ? "<ol>" + unter.map((u) => `<li><a href="#${u.anker}" data-anker="${u.anker}">${resetEsc(u.titel)}</a></li>`).join("") + "</ol>"
      : ""}</li>`;
  }).join("") + "</ol>";
}

function hilfeStichwortverzeichnis() {
  const titel = Object.fromEntries(HILFE.kapitel.map((k) => [k.anker, k.titel]));
  let buchstabe = "";
  return HILFE.stichwortverzeichnis.map((e) => {
    const b = e.wort[0].toUpperCase().replace("Ä", "A").replace("Ö", "O").replace("Ü", "U");
    const kopf = b !== buchstabe ? `<h4 class="hilfe-buchstabe">${resetEsc(b)}</h4>` : "";
    buchstabe = b;
    return kopf + `<p class="hilfe-stichwort"><strong>${resetEsc(e.wort)}</strong>: ${e.anker.map((a) =>
      `<a href="#${a}">${resetEsc(titel[a] || a)}</a>`).join(", ")}</p>`;
  }).join("");
}

function hilfeTextZeichnen() {
  document.getElementById("hilfe-text").innerHTML = HILFE.kapitel.map((k) => {
    const h = k.ebene === 1 ? "h2" : "h3";
    const inhalt = k.automatisch === "stichwortverzeichnis" ? hilfeStichwortverzeichnis() : k.html;
    return `<section class="hilfe-kapitel ebene-${k.ebene}" id="hilfe-k-${k.anker}">
      <${h}>${resetEsc(k.titel)}</${h}>${inhalt}</section>`;
  }).join("");
}

function hilfeNormal(t) {
  return t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

function hilfeSuchen(begriff) {
  const woerter = hilfeNormal(begriff).split(/\s+/).filter(Boolean);
  const titel = Object.fromEntries(HILFE.kapitel.map((k) => [k.anker, k.titel]));
  const treffer = HILFE.kapitel.filter((k) => k.automatisch !== "stichwortverzeichnis").map((k) => {
    const voll = hilfeNormal(k.titel + " " + k.stichworte.join(" ") + " " + k.text);
    if (!woerter.every((w) => voll.includes(w))) return null;
    const imTitel = woerter.filter((w) => hilfeNormal(k.titel).includes(w)).length;
    return { k, punkte: imTitel * 10 + woerter.filter((w) => hilfeNormal(k.stichworte.join(" ")).includes(w)).length * 5 };
  }).filter(Boolean).sort((a, b) => b.punkte - a.punkte);
  const ziel = document.getElementById("hilfe-text");
  if (!treffer.length) {
    ziel.innerHTML = `<p class="leer">Keine Treffer für „${resetEsc(begriff)}“.</p>`;
    return;
  }
  ziel.innerHTML = `<p class="hinweis">${treffer.length} Treffer für „${resetEsc(begriff)}“</p>` + treffer.map(({ k }) => {
    const pfad = k.eltern ? `${resetEsc(titel[k.eltern] || "")} › ` : "";
    return `<div class="hilfe-treffer"><a href="#${k.anker}"><span class="hinweis">${pfad}</span>${resetEsc(k.titel)}</a>
      <div class="hilfe-auszug">${hilfeAuszug(k.text, woerter)}</div></div>`;
  }).join("");
}

function hilfeAuszug(text, woerter) {
  // hilfeNormal() erhält die Länge je Zeichen (Umlaute -> Grundbuchstabe),
  // Fundstellen im normalisierten Text gelten deshalb auch im Original.
  const norm = hilfeNormal(text);
  let pos = -1;
  woerter.forEach((w) => { const p = norm.indexOf(w); if (p >= 0 && (pos < 0 || p < pos)) pos = p; });
  const start = Math.max(0, pos - 70);
  const ende = Math.min(text.length, start + 220);
  const stueck = text.slice(start, ende);
  const rx = new RegExp(woerter.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g");
  const n = hilfeNormal(stueck);
  let html = "", letzte = 0, m;
  while ((m = rx.exec(n)) !== null) {
    if (!m[0].length) { rx.lastIndex++; continue; }
    html += resetEsc(stueck.slice(letzte, m.index)) + `<mark>${resetEsc(stueck.slice(m.index, m.index + m[0].length))}</mark>`;
    letzte = m.index + m[0].length;
  }
  html += resetEsc(stueck.slice(letzte));
  return (start > 0 ? "… " : "") + html.replace(/\s+/g, " ") + (ende < text.length ? " …" : "");
}

let HILFE_SUCHE_TIMER = null;
document.getElementById("hilfe-suche").addEventListener("input", (e) => {
  clearTimeout(HILFE_SUCHE_TIMER);
  HILFE_SUCHE_TIMER = setTimeout(() => {
    const begriff = e.target.value.trim();
    if (begriff.length < 2) hilfeTextZeichnen();
    else hilfeSuchen(begriff);
    document.querySelector(".hauptbereich").scrollTop = 0;
  }, 180);
});

(async function init() {
  // Seit 3.0: erst Sperre und Verschlüsselung klären (Sperrbildschirm)
  await schutzSicherstellen();
  try {
    themeFarbenAnwenden(await api("/admin/einstellungen"));
  } catch {
    // Ohne erreichbares Backend bleibt es beim eingebauten Standard-Theme.
  }
  try {
    const status = await api("/start-status");
    const teile = [];
    if (status.datenbank_neu_angelegt) teile.push("Datenbank neu angelegt");
    if (status.umgewandelte_plan_buchungen?.length) teile.push(`${status.umgewandelte_plan_buchungen.length} Plan-Buchung(en) umgewandelt`);
    if (status.backup_erstellt) teile.push("Backup erstellt");
    const stapel = SCHUTZ.entsperrt && SCHUTZ.entsperrt.stapel;
    if (stapel && stapel.gebucht) teile.push(`${stapel.gebucht} vorgemerkte Buchung(en) gebucht`);
    if (stapel && stapel.klaerliste) teile.push(`${stapel.klaerliste} in der Klärliste`);
    document.getElementById("fuss-status").textContent = teile.length ? teile.join(" · ") : "Bereit";
    document.getElementById("systeminfo-zeit").textContent = status.serverzeit
      ? `Serverzeit beim Laden: ${status.serverzeit} (${status.zeitzone}) · Zeitzone des Containers: ${status.container_zeitzone}`
      : "–";
    document.getElementById("fuss-version").textContent = status.version
      ? `Version ${status.version}${status.version_datum ? " · " + status.version_datum : ""}`
      : "";
  } catch {
    document.getElementById("fuss-status").textContent = "Bereit";
  }
  await renderNavigation();
  await hilfeHinweiseLaden();
  await bundeslandPruefen().catch(() => {});
  await ladeKategorien();
  await ladePersonen();
  await ladeStart();
  await ladeSparziele();
  await pruefeVorzeichen();
  await pruefeSparziele();
  // Direktaufruf eines Hilfekapitels, z. B. aus der Schnellbuchung: #hilfe:anker
  const m = location.hash.match(/^#hilfe:(.+)$/);
  if (m) hilfeOeffnen(decodeURIComponent(m[1]));
})();

// ─── Sicherheit: Sperre, Verschlüsselung, Klärliste (seit 3.0) ──────
// Regeln und Begründungen: DOCS.md „Neu in Version 3.0“. Der Server prüft
// alles selbst, die Oberfläche zeigt nur an, was erlaubt ist.

function schutzAktiv() {
  const st = SCHUTZ.status;
  return !!(st && (st.sperre.aktiv || st.verschluesselung.aktiv));
}

// Downloads (seit 3.0): Ohne Sperre und Verschlüsselung wie bis 2.7 über
// Links. Sonst bereitet der Server den Inhalt vor und gibt ein einmaliges
// Ticket, der Browser lädt dann wie gewohnt über einen Link.
async function herunterladen(art, extra = {}) {
  const r = await api("/admin/download", { method: "POST", body: JSON.stringify({ art, ...extra }) });
  window.location.href = `${API}/download/${encodeURIComponent(r.ticket)}`;
}

document.getElementById("db-herunterladen").addEventListener("click", async () => {
  if (SCHUTZ.status && SCHUTZ.status.verschluesselung.aktiv) { schutzDownloadDialog("datenbank"); return; }
  if (schutzAktiv()) { await herunterladen("datenbank"); return; }
  window.location.href = `${API}/admin/datenbank-herunterladen`;
});

document.getElementById("import-vorlage").addEventListener("click", async () => {
  if (schutzAktiv()) { await herunterladen("import_vorlage"); return; }
  window.location.href = `${API}/admin/import-vorlage`;
});

function schutzDialog(html) {
  const dialog = document.getElementById("schutz-dialog");
  document.getElementById("schutz-dialog-inhalt").innerHTML = html;
  if (!dialog.open) dialog.showModal();
  dialog.querySelectorAll("[data-schliessen]").forEach((k) => k.addEventListener("click", () => dialog.close()));
  dialog.querySelectorAll("form").forEach((f) => musterImFormular(f));
  return dialog;
}

function schutzFehler(ziel, text) {
  const f = typeof ziel === "string" ? document.getElementById(ziel) : ziel;
  if (!f) return;
  f.textContent = text || "";
  f.hidden = !text;
}

// Datenbank-Download und Export bei eingeschalteter Verschlüsselung:
// Standard geschützt, unverschlüsselt nur mit Warnung und Phrase.
function schutzDownloadDialog(art, extra = {}) {
  const istExport = art === "export";
  const min = (SCHUTZ.status && SCHUTZ.status.verschluesselung.mindestlaenge) || 16;
  schutzDialog(`
    <h2>${istExport ? "Export herunterladen" : "Datenbank herunterladen"}</h2>
    <p class="hinweis">${istExport ? hinweisHtml("sicherheit.export") : hinweisHtml("sicherheit.download")}</p>
    <form id="schutz-dl-form" class="formular" autocomplete="off">
      ${istExport ? `
        <div><label>Excel-Kennwort (mindestens ${min} Zeichen)</label><input type="password" name="kennwort"></div>
        <div><label>Kennwort wiederholen</label><input type="password" name="wiederholung"></div>` : ""}
      <div class="reihen-werkzeuge reset-knoepfe">
        <button type="button" class="knopf sekundaer" data-schliessen>Abbrechen</button>
        <button type="submit" class="knopf">${istExport ? "Mit Kennwort herunterladen" : "Verschlüsselt herunterladen"}</button>
      </div>
    </form>
    <div class="warnung" id="schutz-dl-fehler" hidden></div>
    <details style="margin-top:12px"><summary>Unverschlüsselt herunterladen …</summary>
      <p class="warnung">${hinweisHtml("sicherheit.unverschluesselt")}</p>
      <div class="reihen-werkzeuge"><button type="button" class="knopf gefahr klein" id="schutz-dl-klar-start">Phrase anfordern</button></div>
      <div id="schutz-dl-klar"></div>
    </details>`);
  document.getElementById("schutz-dl-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const f = e.target;
      await herunterladen(art, istExport ? { ...extra, kennwort: f.kennwort.value, wiederholung: f.wiederholung.value } : extra);
      document.getElementById("schutz-dialog").close();
    } catch (err) { schutzFehler("schutz-dl-fehler", apiFehlerText(err)); }
  });
  document.getElementById("schutz-dl-klar-start").addEventListener("click", async () => {
    try {
      const p = await api(`/admin/klartext-phrase?art=${istExport ? "export" : "datenbank"}`, { method: "POST" });
      document.getElementById("schutz-dl-klar").innerHTML = `
        <p>Zur Bestätigung diese Phrase eintippen:</p><div class="reset-phrase">${resetEsc(p.phrase)}</div>
        <input id="schutz-dl-phrase" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Phrase eingeben">
        <div class="reihen-werkzeuge" style="margin-top:8px"><button type="button" class="knopf gefahr" id="schutz-dl-klar-los" disabled>Unverschlüsselt herunterladen</button></div>`;
      const eingabe = document.getElementById("schutz-dl-phrase");
      const los = document.getElementById("schutz-dl-klar-los");
      eingabe.addEventListener("input", () => { los.disabled = eingabe.value.trim().toLowerCase() !== p.phrase; });
      los.addEventListener("click", async () => {
        try {
          await herunterladen(`${art}_klartext`, { ...extra, token: p.token, phrase: eingabe.value });
          document.getElementById("schutz-dialog").close();
        } catch (err) { schutzFehler("schutz-dl-fehler", apiFehlerText(err)); }
      });
    } catch (err) { schutzFehler("schutz-dl-fehler", apiFehlerText(err)); }
  });
}

// Wiederherstellungsschlüssel ausdrucken: eigenes, unsichtbares Fenster,
// damit nur der Schlüssel auf dem Papier steht.
function schluesselDrucken(titel, schluessel) {
  const rahmen = document.createElement("iframe");
  rahmen.style.cssText = "position:fixed;width:0;height:0;border:0;right:0;bottom:0";
  document.body.appendChild(rahmen);
  const d = rahmen.contentDocument;
  d.open();
  d.write(`<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>${resetEsc(titel)}</title></head>
    <body style="font-family:sans-serif;padding:24px">
    <h1 style="font-size:20px">${resetEsc(titel)}</h1>
    <p>Private Finanzverwaltung · erstellt am ${new Date().toLocaleDateString("de-DE")}</p>
    <p style="font-family:monospace;font-size:24px;letter-spacing:.08em;border:1px dashed #333;padding:14px;text-align:center">${resetEsc(schluessel)}</p>
    <p>Sicher aufbewahren, getrennt vom Gerät. Wer diesen Schlüssel hat, kommt an die Daten.</p></body></html>`);
  d.close();
  rahmen.contentWindow.focus();
  rahmen.contentWindow.print();
  setTimeout(() => rahmen.remove(), 60000);
}

function schluesselBestaetigenHtml(titel, schluessel, extraHtml = "") {
  return `
    <h2 style="color:var(--tinte)">${resetEsc(titel)}</h2>
    <p class="hinweis">${hinweisHtml("sicherheit.wiederherstellungsschluessel")}</p>
    <div class="schluessel-anzeige" id="schutz-schluessel">${resetEsc(schluessel)}</div>
    <div class="reihen-werkzeuge"><button type="button" class="knopf sekundaer klein" id="schutz-drucken">Drucken</button></div>
    <form id="schutz-bestaetigen-form" class="formular" autocomplete="off" style="margin-top:12px">
      <div style="grid-column:1/-1"><label>Schlüssel zur Bestätigung abtippen</label>
        <input name="getippt" autocomplete="off" autocapitalize="characters" spellcheck="false"></div>
      ${extraHtml}
      <div class="reihen-werkzeuge reset-knoepfe" style="grid-column:1/-1">
        <button type="button" class="knopf sekundaer" data-schliessen>Abbrechen</button>
        <button type="submit" class="knopf gefahr" id="schutz-bestaetigen-los">Einschalten</button>
      </div>
    </form>
    <div class="warnung" id="schutz-bestaetigen-fehler" hidden></div>`;
}

function codeAuswahlHtml(mindest, praefix = "") {
  return `
    <div><label>Art des Codes</label><select name="${praefix}art">
      <option value="pin">PIN (mindestens ${mindest.pin} Ziffern)</option>
      <option value="passwort">Passwort (mindestens ${mindest.passwort} Zeichen)</option>
      <option value="muster">Muster (mindestens ${mindest.muster} Punkte)</option></select></div>
    <div class="breit schutz-codefelder" data-praefix="${praefix}"></div>`;
}

function codeFelderBinden(form, praefix = "") {
  const sel = form.elements[`${praefix}art`];
  const ziel = form.querySelector(`.schutz-codefelder[data-praefix="${praefix}"]`);
  const zeichnen = () => {
    const art = sel.value;
    ziel.innerHTML = `<div class="schutz-formular">
      <div><label>${ART_NAMEN[art]}</label>${codeFeldHtml(art, `${praefix}code`)}</div>
      <div><label>${ART_NAMEN[art]} wiederholen</label>${codeFeldHtml(art, `${praefix}wiederholung`)}</div></div>`;
    musterImFormular(form);
  };
  sel.addEventListener("change", zeichnen);
  zeichnen();
}

async function renderSicherheit() {
  await schutzStatusLaden();
  await Promise.all([sperreRendern(), verschluesselungRendern(), klaerlisteRendern()]);
}

async function sperreRendern() {
  const d = await api("/schutz/sperre");
  const ziel = document.getElementById("sperre-inhalt");
  const status = `<p><span class="schutz-status ${d.aktiv ? "an" : ""}">${d.aktiv ? "eingeschaltet" : "ausgeschaltet"}</span>
    ${d.aktiv ? `seit ${resetEsc((d.seit || "").slice(0, 10).split("-").reverse().join("."))} · ${d.modus === "gemeinsam" ? "gemeinsamer Code" : "eigener Code je Benutzer"}` : ""}</p>`;
  const herkunft = d.herkunft_modus !== "sperren"
    ? `<p class="warnung">${hinweisHtml("sicherheit.herkunft")}</p>` : "";
  const grund = d.verwalten ? "" : `<p class="hinweis">${resetEsc(d.grund || "")}</p>`;
  const einst = (e, mitModus) => `
    ${mitModus ? `<div><label>Code</label><select name="modus"><option value="je_benutzer">eigener Code je Benutzer</option>
      <option value="gemeinsam">ein gemeinsamer Code</option></select></div>` : ""}
    <div><label>Sperre bis Freigabe nach</label><select name="grenze">
      ${[0, 5, 6, 7, 8, 9, 10, 12, 15, 20].map((g) => `<option value="${g}" ${g === e.grenze ? "selected" : ""}>${g ? `${g} Fehlversuchen` : "ohne Limit"}</option>`).join("")}</select></div>
    <div><label>Automatische Sperre nach Minuten (0 = aus)</label><input type="number" name="auto_minuten" min="0" max="240" value="${e.auto_minuten}"></div>
    <div><label>Schnellbuchung</label><select name="schnellbuchung">
      <option value="nur_erfassen" ${e.schnellbuchung === "nur_erfassen" ? "selected" : ""}>ohne Code nur erfassen</option>
      <option value="mit_code" ${e.schnellbuchung === "mit_code" ? "selected" : ""}>immer mit Code</option></select></div>
    <div class="breit"><label><input type="checkbox" name="auto_hintergrund" ${e.auto_hintergrund ? "checked" : ""}>
      Auch sperren, wenn die App in den Hintergrund geht oder der Tab verlassen wird</label></div>
    <div><label>Mindestlänge PIN</label><input type="number" name="min_pin" min="6" max="64" value="${e.mindest.pin}"></div>
    <div><label>Mindestlänge Passwort</label><input type="number" name="min_passwort" min="8" max="64" value="${e.mindest.passwort}"></div>
    <div><label>Mindestzahl Punkte Muster</label><input type="number" name="min_muster" min="5" max="9" value="${e.mindest.muster}"></div>`;
  const einstLesen = (f) => ({ grenze: Number(f.grenze.value), auto_minuten: Number(f.auto_minuten.value),
    schnellbuchung: f.schnellbuchung.value, auto_hintergrund: f.auto_hintergrund.checked,
    mindest: { pin: Number(f.min_pin.value), passwort: Number(f.min_passwort.value), muster: Number(f.min_muster.value) },
    ...(f.modus ? { modus: f.modus.value } : {}) });

  if (!d.aktiv) {
    const vorgabe = { grenze: 10, auto_minuten: 5, schnellbuchung: "nur_erfassen", auto_hintergrund: false,
      mindest: { pin: 6, passwort: 8, muster: 5 } };
    ziel.innerHTML = status + herkunft + grund + (d.verwalten ? `
      <form id="form-sperre-ein" class="schutz-formular" autocomplete="off">
        ${einst(vorgabe, true)}
        ${codeAuswahlHtml(vorgabe.mindest)}
        <div class="breit reihen-werkzeuge"><button type="submit" class="knopf">Sperre einschalten …</button></div>
      </form><div class="warnung" id="sperre-fehler" hidden></div>` : "");
    const form = document.getElementById("form-sperre-ein");
    if (!form) return;
    codeFelderBinden(form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      schutzFehler("sperre-fehler", "");
      try {
        const v = await api("/schutz/sperre/vorbereiten", { method: "POST", body: JSON.stringify({
          einstellungen: einstLesen(form), art: form.art.value, code: codeWert(form, "code"),
          wiederholung: codeWert(form, "wiederholung") }) });
        sperreEinschaltenDialog(v);
      } catch (err) { schutzFehler("sperre-fehler", apiFehlerText(err)); }
    });
    return;
  }

  const ich = d.benutzer.find((b) => b.id === d.ich);
  const zeilen = d.benutzer.map((b) => `<tr>
      <td>${resetEsc(b.name || b.id)}${b.id === d.ich ? " (du)" : ""}</td>
      <td>${b.code_gesetzt ? resetEsc(ART_NAMEN[b.art] || "gesetzt") : "noch nicht festgelegt"}</td>
      <td>${b.dauerhaft ? "gesperrt bis Freigabe" : (b.anzahl ? `${b.anzahl} Fehlversuch(e)` : "–")}</td>
      <td class="rechts">
        ${b.anzahl && b.id !== d.ich ? `<button class="knopf sekundaer klein" data-sperre-freigeben="${resetEsc(b.id)}">Freigeben</button>` : ""}
        ${d.verwalten && b.id !== d.ich ? `<button class="knopf gefahr klein" data-sperre-entfernen="${resetEsc(b.id)}">Entfernen</button>` : ""}
      </td></tr>`).join("");
  const darfCode = d.modus === "je_benutzer" || d.verwalten;
  const alteArt = (ich && ich.art) || d.gemeinsame_art || "pin";
  ziel.innerHTML = status + herkunft + grund + `
    <h3>Freigegebene Benutzer</h3>
    <table><thead><tr><th>Benutzer</th><th>Code</th><th>Fehlversuche</th><th></th></tr></thead><tbody id="sperre-benutzer">${zeilen}</tbody></table>
    ${d.verwalten ? `<div class="reihen-werkzeuge" style="margin-top:8px">
      <select id="sperre-bekannt">${d.bekannt.length ? d.bekannt.map((b) => `<option value="${resetEsc(b.id)}">${resetEsc(b.name || b.id)}</option>`).join("")
        : '<option value="">– niemand weiteres hat die Finanzverwaltung geöffnet –</option>'}</select>
      <button class="knopf sekundaer klein" id="sperre-hinzu" ${d.bekannt.length ? "" : "disabled"}>Freigeben</button></div>` : ""}
    ${d.verwalten ? `<h3>Einstellungen</h3><form id="form-sperre-einst" class="schutz-formular" autocomplete="off">
      ${einst(d, false)}<div class="breit reihen-werkzeuge"><button type="submit" class="knopf">Speichern</button></div></form>` : ""}
    ${darfCode ? `<h3>${d.modus === "gemeinsam" ? "Gemeinsamen Code ändern" : "Eigenen Code ändern"}</h3>
      <form id="form-sperre-code" class="schutz-formular" autocomplete="off">
        <div class="breit"><label>Bisheriger Code (${resetEsc(ART_NAMEN[alteArt])})</label>${codeFeldHtml(alteArt, "alter_code")}</div>
        ${codeAuswahlHtml(d.mindest, "neu_")}
        <div class="breit reihen-werkzeuge"><button type="submit" class="knopf">Code ändern</button></div></form>` : ""}
    ${d.verwalten ? `<h3>Ausschalten</h3><form id="form-sperre-aus" class="schutz-formular" autocomplete="off">
      <div class="breit"><label>Dein Code (${resetEsc(ART_NAMEN[alteArt])})</label>${codeFeldHtml(alteArt, "code")}</div>
      <div class="breit reihen-werkzeuge"><button type="submit" class="knopf gefahr">Sperre ausschalten</button></div></form>` : ""}
    <div class="warnung" id="sperre-fehler" hidden></div><div class="hinweis" id="sperre-meldung"></div>`;
  ziel.querySelectorAll("form").forEach((f) => musterImFormular(f));
  const melden = (text) => { document.getElementById("sperre-meldung").textContent = text; };
  const ausfuehren = async (fn, text) => {
    schutzFehler("sperre-fehler", "");
    try { await fn(); await sperreRendern(); melden(text); } catch (err) { schutzFehler("sperre-fehler", apiFehlerText(err)); }
  };
  ziel.querySelectorAll("[data-sperre-freigeben]").forEach((k) => k.addEventListener("click", () => ausfuehren(
    () => api(`/schutz/sperre/benutzer/${encodeURIComponent(k.dataset.sperreFreigeben)}/entsperren`, { method: "POST" }),
    "Fehlversuche zurückgesetzt.")));
  ziel.querySelectorAll("[data-sperre-entfernen]").forEach((k) => k.addEventListener("click", () => ausfuehren(
    () => api(`/schutz/sperre/benutzer/${encodeURIComponent(k.dataset.sperreEntfernen)}`, { method: "DELETE" }),
    "Aus der Freigabeliste entfernt.")));
  const hinzu = document.getElementById("sperre-hinzu");
  if (hinzu) hinzu.addEventListener("click", () => ausfuehren(
    () => api("/schutz/sperre/benutzer", { method: "POST", body: JSON.stringify({ id: document.getElementById("sperre-bekannt").value }) }),
    "Freigegeben. Beim ersten Öffnen legt der Benutzer seinen Code fest."));
  const einstForm = document.getElementById("form-sperre-einst");
  if (einstForm) einstForm.addEventListener("submit", (e) => { e.preventDefault(); ausfuehren(async () => {
    await api("/schutz/sperre", { method: "PUT", body: JSON.stringify(einstLesen(einstForm)) });
    await schutzStatusLaden(); autoSperreStarten(); }, "Gespeichert."); });
  const codeForm = document.getElementById("form-sperre-code");
  if (codeForm) {
    codeFelderBinden(codeForm, "neu_");
    codeForm.addEventListener("submit", (e) => { e.preventDefault(); ausfuehren(() => api("/schutz/sperre/code", {
      method: "POST", body: JSON.stringify({ alter_code: codeWert(codeForm, "alter_code"), art: codeForm.neu_art.value,
        code: codeWert(codeForm, "neu_code"), wiederholung: codeWert(codeForm, "neu_wiederholung") }) }), "Code geändert."); });
  }
  const ausForm = document.getElementById("form-sperre-aus");
  if (ausForm) ausForm.addEventListener("submit", (e) => { e.preventDefault(); ausfuehren(async () => {
    await api("/schutz/sperre/ausschalten", { method: "POST", body: JSON.stringify({ code: codeWert(ausForm, "code") }) });
    schutzSitzungSetzen(null); await schutzStatusLaden(); autoSperreStarten(); }, "Die Sperre ist ausgeschaltet."); });
}

function sperreEinschaltenDialog(v) {
  schutzDialog(schluesselBestaetigenHtml("Wiederherstellungsschlüssel der Sperre", v.wiederherstellungsschluessel));
  document.getElementById("schutz-drucken").addEventListener("click", () =>
    schluesselDrucken("Wiederherstellungsschlüssel der Sperre", v.wiederherstellungsschluessel));
  document.getElementById("schutz-bestaetigen-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r = await api("/schutz/sperre/einschalten", { method: "POST",
        body: JSON.stringify({ kennung: v.kennung, getippt: e.target.getippt.value }) });
      schutzSitzungSetzen(r.sitzung);
      document.getElementById("schutz-dialog").close();
      await schutzStatusLaden();
      autoSperreStarten();
      await sperreRendern();
      document.getElementById("sperre-meldung").textContent = "Die Sperre ist eingeschaltet.";
    } catch (err) { schutzFehler("schutz-bestaetigen-fehler", apiFehlerText(err)); }
  });
}

async function verschluesselungRendern() {
  const v = await api("/schutz/verschluesselung");
  const ziel = document.getElementById("verschluesselung-inhalt");
  const status = `<p><span class="schutz-status ${v.aktiv ? "an" : ""}">${v.aktiv ? "eingeschaltet" : "ausgeschaltet"}</span>
    ${v.aktiv && v.seit ? `seit ${resetEsc(v.seit.slice(0, 10).split("-").reverse().join("."))}` : ""}</p>`;
  const grund = v.verwalten ? "" : `<p class="hinweis">${resetEsc(v.grund || "")}</p>`;
  if (!v.verfuegbar) { ziel.innerHTML = status + '<p class="warnung">SQLCipher ist in diesem Add-on nicht verfügbar.</p>'; return; }
  if (!v.aktiv) {
    ziel.innerHTML = status + grund + (v.verwalten ? `
      <p><strong>1.</strong> Sicherung: Datenbank unverschlüsselt herunterladen.
        <button type="button" class="knopf sekundaer klein" id="vs-download">Datenbank herunterladen</button>
        <span class="hinweis" id="vs-download-status">${v.klartext_download ? "erledigt" : "noch offen"}</span></p>
      <p><strong>2.</strong> Passphrase festlegen.</p>
      <form id="form-vs-ein" class="schutz-formular" autocomplete="off">
        <div><label>Passphrase</label><input type="password" name="passphrase"></div>
        <div><label>Passphrase wiederholen</label><input type="password" name="wiederholung"></div>
        <div><label>Mindestlänge (ab ${v.untergrenze})</label><input type="number" name="mindestlaenge" min="${v.untergrenze}" max="200" value="${v.mindestlaenge}"></div>
        <div class="breit reihen-werkzeuge"><button type="submit" class="knopf">Weiter …</button></div>
      </form><div class="warnung" id="vs-fehler" hidden></div>` : "");
    const dl = document.getElementById("vs-download");
    if (!dl) return;
    dl.addEventListener("click", async () => {
      try {
        if (schutzAktiv()) await herunterladen("datenbank");
        else window.location.href = `${API}/admin/datenbank-herunterladen`;
        document.getElementById("vs-download-status").textContent = "erledigt";
      } catch (err) { schutzFehler("vs-fehler", apiFehlerText(err)); }
    });
    document.getElementById("form-vs-ein").addEventListener("submit", async (e) => {
      e.preventDefault();
      schutzFehler("vs-fehler", "");
      const f = e.target;
      try {
        const r = await api("/schutz/verschluesselung/vorbereiten", { method: "POST", body: JSON.stringify({
          passphrase: f.passphrase.value, wiederholung: f.wiederholung.value, mindestlaenge: Number(f.mindestlaenge.value) }) });
        verschluesselungEinschaltenDialog(r);
      } catch (err) { schutzFehler("vs-fehler", apiFehlerText(err)); }
    });
    return;
  }
  ziel.innerHTML = status + grund + (v.stapel ? `<p class="hinweis">${v.stapel} vorgemerkte Buchung(en) warten im Stapel.</p>` : "") + (v.verwalten ? `
    <h3>Passphrase ändern</h3>
    <form id="form-vs-pp" class="schutz-formular" autocomplete="off">
      <div><label>Bisherige Passphrase oder Wiederherstellungsschlüssel</label><input type="password" name="geheimnis"></div>
      <div><label>Neue Passphrase (mindestens ${v.mindestlaenge} Zeichen)</label><input type="password" name="neu"></div>
      <div><label>Neue Passphrase wiederholen</label><input type="password" name="wiederholung"></div>
      <div class="breit reihen-werkzeuge"><button type="submit" class="knopf">Passphrase ändern</button></div>
    </form>
    <h3>Mindestlänge der Passphrase</h3>
    <form id="form-vs-min" class="schutz-formular" autocomplete="off">
      <div><label>Zeichen (ab ${v.untergrenze})</label><input type="number" name="laenge" min="${v.untergrenze}" max="200" value="${v.mindestlaenge}"></div>
      <div class="reihen-werkzeuge"><button type="submit" class="knopf">Speichern</button></div>
    </form>
    <h3>Ausschalten</h3>
    <div class="reihen-werkzeuge"><button type="button" class="knopf gefahr" id="vs-aus">Verschlüsselung ausschalten …</button></div>
    <div class="warnung" id="vs-fehler" hidden></div><div class="hinweis" id="vs-meldung"></div>` : "");
  if (!v.verwalten) return;
  const melden = (t) => { document.getElementById("vs-meldung").textContent = t; schutzFehler("vs-fehler", ""); };
  document.getElementById("form-vs-pp").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      await api("/schutz/verschluesselung/passphrase", { method: "POST", body: JSON.stringify({
        geheimnis: f.geheimnis.value, neu: f.neu.value, wiederholung: f.wiederholung.value }) });
      f.reset(); melden("Passphrase geändert. Die Datenbank musste dafür nicht neu verschlüsselt werden.");
    } catch (err) { schutzFehler("vs-fehler", apiFehlerText(err)); }
  });
  document.getElementById("form-vs-min").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/schutz/verschluesselung/mindestlaenge", { method: "PUT", body: JSON.stringify({ laenge: Number(e.target.laenge.value) }) });
      melden("Gespeichert. Gilt für neue Passphrasen und Excel-Kennwörter.");
    } catch (err) { schutzFehler("vs-fehler", apiFehlerText(err)); }
  });
  document.getElementById("vs-aus").addEventListener("click", async () => {
    try {
      const p = await api("/schutz/verschluesselung/ausschalten-phrase", { method: "POST" });
      schutzDialog(`<h2>Verschlüsselung ausschalten</h2>
        <p class="warnung">${hinweisHtml("sicherheit.ausschalten")}</p>
        <form id="form-vs-aus" class="formular" autocomplete="off">
          <div style="grid-column:1/-1"><label>Passphrase oder Wiederherstellungsschlüssel</label><input type="password" name="geheimnis"></div>
          <div style="grid-column:1/-1"><p>Zur Bestätigung diese Phrase eintippen:</p><div class="reset-phrase">${resetEsc(p.phrase)}</div>
            <input name="phrase" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Phrase eingeben"></div>
          <div class="reihen-werkzeuge reset-knoepfe" style="grid-column:1/-1">
            <button type="button" class="knopf sekundaer" data-schliessen>Abbrechen</button>
            <button type="submit" class="knopf gefahr">Entschlüsseln</button></div>
        </form><div class="warnung" id="vs-aus-fehler" hidden></div><div id="vs-aus-ergebnis"></div>`);
      document.getElementById("form-vs-aus").addEventListener("submit", async (e) => {
        e.preventDefault();
        const knopf = e.target.querySelector('[type="submit"]');
        knopf.disabled = true;
        schutzFehler("vs-aus-fehler", "Wird entschlüsselt …");
        try {
          const r = await api("/schutz/verschluesselung/ausschalten", { method: "POST", body: JSON.stringify({
            geheimnis: e.target.geheimnis.value, token: p.token, phrase: e.target.phrase.value }) });
          schutzFehler("vs-aus-fehler", "");
          e.target.remove();
          document.getElementById("vs-aus-ergebnis").innerHTML = `<h3 style="color:var(--gruen)">Ausgeschaltet</h3>
            <ul>${r.schritte.map((t) => `<li>${resetEsc(t)}</li>`).join("")}</ul>
            <div class="reihen-werkzeuge reset-knoepfe"><button type="button" class="knopf" data-schliessen>Schließen</button></div>`;
          document.querySelectorAll("#vs-aus-ergebnis [data-schliessen]").forEach((k) => k.addEventListener("click", () => document.getElementById("schutz-dialog").close()));
          await renderSicherheit();
        } catch (err) { knopf.disabled = false; schutzFehler("vs-aus-fehler", apiFehlerText(err)); }
      });
    } catch (err) { schutzFehler("vs-fehler", apiFehlerText(err)); }
  });
}

function verschluesselungEinschaltenDialog(v) {
  schutzDialog(schluesselBestaetigenHtml("Wiederherstellungsschlüssel der Verschlüsselung", v.wiederherstellungsschluessel, `
    <div style="grid-column:1/-1"><p class="warnung">${hinweisHtml("sicherheit.einschalten")}</p>
      <p>Zur Bestätigung diese Phrase eintippen:</p><div class="reset-phrase">${resetEsc(v.phrase)}</div>
      <input name="phrase" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Phrase eingeben"></div>`));
  document.getElementById("schutz-bestaetigen-los").textContent = "Verschlüsseln";
  document.getElementById("schutz-drucken").addEventListener("click", () =>
    schluesselDrucken("Wiederherstellungsschlüssel der Verschlüsselung", v.wiederherstellungsschluessel));
  document.getElementById("schutz-bestaetigen-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const knopf = document.getElementById("schutz-bestaetigen-los");
    knopf.disabled = true;
    schutzFehler("schutz-bestaetigen-fehler", "Wird verschlüsselt und geprüft …");
    try {
      const r = await api("/schutz/verschluesselung/einschalten", { method: "POST", body: JSON.stringify({
        kennung: v.kennung, getippt: e.target.getippt.value, token: v.token, phrase: e.target.phrase.value }) });
      schutzFehler("schutz-bestaetigen-fehler", "");
      document.getElementById("schutz-dialog-inhalt").innerHTML = `<h2 style="color:var(--gruen)">Verschlüsselt</h2>
        <ul>${r.schritte.map((t) => `<li>${resetEsc(t)}</li>`).join("")}</ul>
        <p class="hinweis">${hinweisHtml("sicherheit.nach-einschalten")}</p>
        <div class="reihen-werkzeuge reset-knoepfe"><button type="button" class="knopf" data-schliessen>Schließen</button></div>`;
      document.querySelectorAll("#schutz-dialog [data-schliessen]").forEach((k) => k.addEventListener("click", () => document.getElementById("schutz-dialog").close()));
      await renderSicherheit();
    } catch (err) { knopf.disabled = false; schutzFehler("schutz-bestaetigen-fehler", apiFehlerText(err)); }
  });
}

async function klaerlisteRendern() {
  const block = document.getElementById("klaerliste-block");
  const st = SCHUTZ.status;
  const liste = await api("/klaerliste");
  block.hidden = !(st && st.verschluesselung.aktiv) && !liste.length;
  const ziel = document.getElementById("klaerliste-inhalt");
  if (!liste.length) { ziel.innerHTML = '<p class="hinweis">Keine offenen Einträge.</p>'; return; }
  const angaben = (d) => [d.betrag != null ? euro(d.betrag) : null, d.konto || null, d.kategorie || null,
    d.datum ? d.datum.split("-").reverse().join(".") : null, d.beschreibung || null].filter(Boolean).map(resetEsc).join(" · ");
  ziel.innerHTML = `<table><thead><tr><th>Erfasst</th><th>Quelle</th><th>Angaben</th><th>Grund</th><th></th></tr></thead><tbody>
    ${liste.map((e) => `<tr data-klaer="${e.id}"><td>${resetEsc((e.erfasst_am || "").slice(0, 16).replace("T", " "))}</td>
      <td>${e.quelle === "siri" ? "Siri" : "Schnellbuchung"}</td><td>${angaben(e.daten)}</td><td>${resetEsc(e.grund)}</td>
      <td class="rechts"><button class="knopf sekundaer klein" data-klaer-buchen="${e.id}">Buchen …</button>
        <button class="knopf gefahr klein" data-klaer-verwerfen="${e.id}">Verwerfen</button></td></tr>`).join("")}
    </tbody></table><div id="klaer-formular"></div><div class="warnung" id="klaer-fehler" hidden></div>`;
  ziel.querySelectorAll("[data-klaer-verwerfen]").forEach((k) => k.addEventListener("click", async () => {
    await api(`/klaerliste/${k.dataset.klaerVerwerfen}`, { method: "DELETE" });
    await klaerlisteRendern();
  }));
  ziel.querySelectorAll("[data-klaer-buchen]").forEach((k) => k.addEventListener("click", async () => {
    const e = liste.find((x) => String(x.id) === k.dataset.klaerBuchen);
    const d = e.daten;
    await ladeKategorien();
    const konten = KONTEN.length ? KONTEN : await api("/konten");
    const kontoId = d.konto_id || (konten.find((x) => x.name.toLowerCase() === String(d.konto || "").toLowerCase()) || {}).id;
    const katId = d.kategorie_id || (KATEGORIEN.find((x) => x.name.toLowerCase() === String(d.kategorie || "").toLowerCase()) || {}).id;
    const katOpt = (pid, pre) => KATEGORIEN.filter((x) => x.parent_id === pid).flatMap((x) =>
      [`<option value="${x.id}" ${x.id === katId ? "selected" : ""}>${pre}${resetEsc(x.name)}</option>`, ...katOpt(x.id, pre + "— ")]).join("");
    document.getElementById("klaer-formular").innerHTML = `<h3>Eintrag buchen</h3>
      <form id="form-klaer" class="schutz-formular" autocomplete="off">
        <div><label>Konto</label><select name="konto_id">${konten.map((x) => `<option value="${x.id}" ${x.id === kontoId ? "selected" : ""}>${resetEsc(x.name)}</option>`).join("")}</select></div>
        <div><label>Kategorie</label><select name="kategorie_id"><option value="">– bitte wählen –</option>${katOpt(null, "")}</select></div>
        <div><label>Betrag</label><input type="number" step="0.01" name="betrag" value="${Math.abs(Number(d.betrag || 0))}"></div>
        <div><label>Datum</label><input type="date" name="datum" value="${resetEsc(d.datum || heuteISO())}"></div>
        <div class="breit"><label>Beschreibung</label><input name="beschreibung" value="${resetEsc(d.beschreibung || "")}"></div>
        <div class="breit reihen-werkzeuge"><button type="submit" class="knopf">Buchen</button></div>
      </form>`;
    document.getElementById("form-klaer").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const f = ev.target;
      try {
        await api(`/klaerliste/${e.id}/buchen`, { method: "POST", body: JSON.stringify({
          konto_id: Number(f.konto_id.value), kategorie_id: f.kategorie_id.value ? Number(f.kategorie_id.value) : null,
          betrag: Number(f.betrag.value), datum: f.datum.value, beschreibung: f.beschreibung.value || null,
          typ: d.typ || "Ist", zielkonto_id: d.zielkonto_id || null, sparziel_id: d.sparziel_id || null }) });
        await klaerlisteRendern();
      } catch (err) { schutzFehler("klaer-fehler", apiFehlerText(err)); }
    });
  }));
}

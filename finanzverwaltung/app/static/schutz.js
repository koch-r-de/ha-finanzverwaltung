// Sperre und Verschlüsselung im Browser (seit 3.0, Issue #5).
// Gemeinsam für die Oberfläche (index.html) und die Schnellbuchung
// (schnellbuchung.html). Die eigentliche Prüfung macht der Server
// (SchutzMiddleware in main.py). Hier nur der Sperrbildschirm, das Token der
// Sitzung und die automatische Sperre.
//
// Das Token liegt in sessionStorage (nur dieser Tab, nur Bequemlichkeit, in
// try). Ohne sessionStorage fragt die Seite nach jedem Neuladen neu.

const SCHUTZ = { sitzung: null, status: null, laeuft: null, letzte: Date.now(), puls: Date.now(),
  takt: null, optionen: {}, entsperrt: null };
try { SCHUTZ.sitzung = sessionStorage.getItem("fv_sitzung"); } catch {}

function schutzKopf() {
  return SCHUTZ.sitzung ? { "X-Finanz-Sitzung": SCHUTZ.sitzung } : {};
}

function schutzSitzungSetzen(token) {
  SCHUTZ.sitzung = token || null;
  try {
    if (token) sessionStorage.setItem("fv_sitzung", token);
    else sessionStorage.removeItem("fv_sitzung");
  } catch {}
}

function schutzEsc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (z) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[z]));
}

async function schutzAnfrage(pfad, daten, methode = "POST") {
  const antwort = await fetch("api/" + pfad, {
    method: methode, headers: { "Content-Type": "application/json", ...schutzKopf() },
    body: methode === "GET" ? undefined : JSON.stringify(daten || {}) });
  const json = await antwort.json().catch(() => ({}));
  if (!antwort.ok) {
    const fehler = new Error(typeof json.detail === "string" ? json.detail
      : (Array.isArray(json.detail) ? json.detail.map((x) => x.msg).join("; ") : `Fehler ${antwort.status}`));
    fehler.status = antwort.status;
    throw fehler;
  }
  return json;
}

async function schutzStatusLaden() {
  const antwort = await fetch("api/schutz/status", { headers: schutzKopf() });
  SCHUTZ.status = await antwort.json();
  return SCHUTZ.status;
}

// Darf die Seite arbeiten? erfassen = Schnellbuchung, die bei „ohne Code nur
// erfassen“ und bei verschlossener Datenbank (Stapel) ohne Code weiterläuft.
function schutzOffen(st, erfassen) {
  if (st.umstellung) return false;
  const sp = st.sperre;
  if (sp.aktiv) {
    if (!sp.freigegeben) return false;
    if (!sp.sitzung && !(erfassen && sp.schnellbuchung === "nur_erfassen")) return false;
  }
  if (st.verschluesselung.gesperrt && !erfassen) return false;
  return true;
}

// Sorgt dafür, dass die Seite arbeiten darf. Zeigt sonst den Sperrbildschirm
// und kehrt erst zurück, wenn entsperrt ist. Mehrere gleichzeitige Aufrufe
// teilen sich einen Ablauf.
function schutzSicherstellen(optionen) {
  if (optionen) SCHUTZ.optionen = optionen;
  if (SCHUTZ.laeuft) return SCHUTZ.laeuft;
  SCHUTZ.laeuft = (async () => {
    try {
      for (;;) {
        const st = await schutzStatusLaden();
        if (st.sperre.aktiv && !st.sperre.sitzung && SCHUTZ.sitzung) schutzSitzungSetzen(null);
        if (schutzOffen(st, SCHUTZ.optionen.erfassen)) {
          schirmVerbergen();
          autoSperreStarten();
          return st;
        }
        await schirmZeigen(st);
      }
    } finally {
      SCHUTZ.laeuft = null;
    }
  })();
  return SCHUTZ.laeuft;
}

// Antwort einer API-Anfrage prüfen: true, wenn der Schutz eingegriffen hat
// und die Anfrage nach dem Entsperren wiederholt werden kann.
async function schutzBehandeln(antwort) {
  if (![401, 403, 423, 503].includes(antwort.status)) return false;
  const json = await antwort.clone().json().catch(() => ({}));
  if (!json.schutz) return false;
  if (json.schutz === "code") schutzSitzungSetzen(null);
  await schutzSicherstellen();
  return true;
}

// ─── Automatische Sperre ─────────────────────────────────────────────
function autoSperreStarten() {
  clearInterval(SCHUTZ.takt);
  const sp = SCHUTZ.status && SCHUTZ.status.sperre;
  if (!sp || !sp.aktiv || !SCHUTZ.sitzung) return;
  SCHUTZ.letzte = Date.now();
  SCHUTZ.takt = setInterval(() => {
    if (sp.auto_minuten > 0 && Date.now() - SCHUTZ.letzte > sp.auto_minuten * 60000) schutzSperren();
  }, 5000);
}

["pointerdown", "keydown", "wheel", "touchstart"].forEach((art) => document.addEventListener(art, () => {
  SCHUTZ.letzte = Date.now();
  // Tätigkeit ohne Serveranfrage: Sitzung höchstens einmal je Minute verlängern
  if (SCHUTZ.sitzung && !SCHUTZ.laeuft && Date.now() - SCHUTZ.puls > 60000) {
    SCHUTZ.puls = Date.now();
    fetch("api/schutz/puls", { headers: schutzKopf() }).catch(() => {});
  }
}, { capture: true, passive: true }));

document.addEventListener("visibilitychange", () => {
  const sp = SCHUTZ.status && SCHUTZ.status.sperre;
  if (document.hidden && sp && sp.aktiv && sp.auto_hintergrund && SCHUTZ.sitzung) schutzSperren();
});

async function schutzSperren() {
  clearInterval(SCHUTZ.takt);
  const token = SCHUTZ.sitzung;
  schutzSitzungSetzen(null);
  if (token) {
    try { await fetch("api/schutz/abmelden", { method: "POST", headers: { "X-Finanz-Sitzung": token } }); } catch {}
  }
  schutzSicherstellen();
}

// ─── Sperrbildschirm ─────────────────────────────────────────────────
function schirm() {
  let el = document.getElementById("schutz-schirm");
  if (!el) {
    el = document.createElement("div");
    el.id = "schutz-schirm";
    el.className = "schutz-schirm";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.innerHTML = '<div class="schutz-karte" id="schutz-karte"></div>';
    document.body.appendChild(el);
  }
  return el;
}

function schirmVerbergen() {
  const el = document.getElementById("schutz-schirm");
  if (el) el.hidden = true;
  document.documentElement.classList.remove("schutz-zu");
}

const ART_NAMEN = { pin: "PIN", passwort: "Passwort", muster: "Muster" };

function codeFeldHtml(art, name, platzhalter) {
  if (art === "muster") return `<div class="muster" data-muster="${name}"></div>`;
  const pin = art === "pin";
  return `<input type="password" name="${name}" ${pin ? 'inputmode="numeric" pattern="[0-9]*"' : ""}
    autocomplete="off" autocapitalize="off" spellcheck="false" data-1p-ignore data-lpignore="true"
    data-bwignore data-form-type="other" placeholder="${schutzEsc(platzhalter || ART_NAMEN[art])}">`;
}

function codeWert(form, name) {
  const muster = form.querySelector(`[data-muster="${name}"]`);
  return muster ? (muster.dataset.wert || "") : (form.elements[name] ? form.elements[name].value : "");
}

// Muster auf einem 3×3-Raster: Punkte antippen oder darüber ziehen, jeder
// Punkt höchstens einmal. Wert als „1-5-9-6-3“.
function musterAufbauen(el) {
  const punkte = [];
  for (let i = 0; i < 9; i++) punkte.push({ n: i + 1, x: 50 + (i % 3) * 100, y: 50 + Math.floor(i / 3) * 100 });
  el.innerHTML = `<svg viewBox="0 0 300 300" class="muster-svg" aria-label="Muster">
      <polyline class="muster-linie" points=""></polyline>
      ${punkte.map((p) => `<circle class="muster-punkt" data-punkt="${p.n}" cx="${p.x}" cy="${p.y}" r="26"></circle>`).join("")}
    </svg>
    <div class="muster-leiste"><span class="hinweis" data-muster-anzahl>0 Punkte</span>
      <button type="button" class="knopf sekundaer klein" data-muster-zurueck>Zurück</button>
      <button type="button" class="knopf sekundaer klein" data-muster-leeren>Leeren</button></div>`;
  const svg = el.querySelector("svg");
  let folge = [];
  let ziehen = false;
  const zeichnen = () => {
    el.dataset.wert = folge.join("-");
    svg.querySelectorAll(".muster-punkt").forEach((c) => c.classList.toggle("aktiv", folge.includes(Number(c.dataset.punkt))));
    svg.querySelector(".muster-linie").setAttribute("points",
      folge.map((n) => `${punkte[n - 1].x},${punkte[n - 1].y}`).join(" "));
    el.querySelector("[data-muster-anzahl]").textContent = `${folge.length} Punkt${folge.length === 1 ? "" : "e"}`;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  };
  const punktBei = (e) => {
    const ziel = document.elementFromPoint(e.clientX, e.clientY);
    return ziel && ziel.closest && ziel.closest(".muster-punkt") ? Number(ziel.closest(".muster-punkt").dataset.punkt) : null;
  };
  const hinzu = (n) => { if (n && !folge.includes(n)) { folge.push(n); zeichnen(); } };
  svg.addEventListener("pointerdown", (e) => { e.preventDefault(); ziehen = true; hinzu(punktBei(e)); });
  svg.addEventListener("pointermove", (e) => { if (ziehen) hinzu(punktBei(e)); });
  ["pointerup", "pointercancel", "pointerleave"].forEach((art) => svg.addEventListener(art, () => { ziehen = false; }));
  el.querySelector("[data-muster-zurueck]").addEventListener("click", () => { folge.pop(); zeichnen(); });
  el.querySelector("[data-muster-leeren]").addEventListener("click", () => { folge = []; zeichnen(); });
  zeichnen();
}

function musterImFormular(form) {
  form.querySelectorAll("[data-muster]").forEach((el) => { if (!el.querySelector("svg")) musterAufbauen(el); });
}

function wartenText(sekunden) {
  if (sekunden < 60) return `${sekunden} Sekunden`;
  const minuten = Math.ceil(sekunden / 60);
  return minuten === 1 ? "1 Minute" : `${minuten} Minuten`;
}

// Zeigt den passenden Bildschirm. Das Versprechen erfüllt sich, sobald eine
// Aktion den Zustand geändert haben kann; schutzSicherstellen prüft dann neu.
function schirmZeigen(st) {
  document.querySelectorAll("dialog[open]").forEach((d) => d.close());
  const el = schirm();
  el.hidden = false;
  document.documentElement.classList.add("schutz-zu");
  const karte = document.getElementById("schutz-karte");
  const sp = st.sperre;
  const vs = st.verschluesselung;
  const wer = st.benutzer.name ? ` als „${schutzEsc(st.benutzer.name)}“` : "";
  return new Promise((fertig) => {
    if (st.umstellung) {
      karte.innerHTML = `<h2>Bitte warten</h2><p>Die Verschlüsselung wird gerade umgestellt.</p>`;
      setTimeout(fertig, 2000);
      return;
    }
    if (sp.aktiv && !sp.freigegeben) {
      karte.innerHTML = `<h2>Kein Zugang</h2>
        <p>Du bist in Home Assistant${wer} angemeldet. Dieser Benutzer ist für die Finanzverwaltung nicht freigegeben.</p>
        <p class="hinweis">Ein Administrator kann dich unter „Administration“ → „Sicherheit“ → „Sperre“ freigeben,
          nachdem du diese Seite einmal geöffnet hast.</p>
        <div class="reihen-werkzeuge"><button type="button" class="knopf sekundaer" id="schutz-neu">Erneut prüfen</button></div>`;
      karte.querySelector("#schutz-neu").addEventListener("click", fertig);
      return;
    }
    if (vs.gesperrt && !SCHUTZ.optionen.erfassen) {
      passphraseSchirm(karte, st, fertig);
      return;
    }
    if (sp.aktiv && !sp.code_gesetzt) {
      erstcodeSchirm(karte, st, fertig);
      return;
    }
    codeSchirm(karte, st, fertig);
  });
}

function fehlerZeigen(karte, text) {
  const f = karte.querySelector(".schutz-fehler");
  f.textContent = text || "";
  f.hidden = !text;
}

function passphraseSchirm(karte, st, fertig) {
  const min = st.verschluesselung.mindestlaenge || 16;
  karte.innerHTML = `<h2>Datenbank entsperren</h2>
    <p>Die Daten sind verschlüsselt. Nach jedem Neustart des Add-ons braucht es die Passphrase.</p>
    <form id="schutz-pp-form" autocomplete="off">
      <label>Passphrase</label>
      <input type="password" name="geheimnis" autocomplete="off" data-1p-ignore data-lpignore="true" data-bwignore data-form-type="other" required>
      <div class="schutz-vergessen" hidden>
        <p class="hinweis">Gib statt der Passphrase den Wiederherstellungsschlüssel ein und lege eine neue Passphrase fest (mindestens ${min} Zeichen).</p>
        <label>Neue Passphrase</label><input type="password" name="neu" autocomplete="off" data-1p-ignore data-lpignore="true" data-bwignore data-form-type="other">
        <label>Neue Passphrase wiederholen</label><input type="password" name="wiederholung" autocomplete="off" data-1p-ignore data-lpignore="true" data-bwignore data-form-type="other">
      </div>
      <div class="warnung schutz-fehler" hidden></div>
      <div class="reihen-werkzeuge">
        <button type="submit" class="knopf">Entsperren</button>
        <button type="button" class="knopf sekundaer klein" id="schutz-pp-vergessen">Passphrase vergessen?</button>
      </div>
    </form>`;
  const form = karte.querySelector("form");
  const warten = st.verschluesselung.warten;
  if (warten) fehlerZeigen(karte, `Zu viele Fehlversuche. Bitte ${wartenText(warten)} warten.`);
  karte.querySelector("#schutz-pp-vergessen").addEventListener("click", () => {
    const v = karte.querySelector(".schutz-vergessen");
    v.hidden = !v.hidden;
    form.elements.geheimnis.previousElementSibling.textContent = v.hidden ? "Passphrase" : "Wiederherstellungsschlüssel";
  });
  form.elements.geheimnis.focus();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const knopf = form.querySelector('[type="submit"]');
    knopf.disabled = true;
    fehlerZeigen(karte, "Wird geprüft und entsperrt …");
    const vergessen = !karte.querySelector(".schutz-vergessen").hidden;
    try {
      const r = await schutzAnfrage("schutz/entsperren", { geheimnis: form.elements.geheimnis.value,
        neue_passphrase: vergessen ? form.elements.neu.value : null,
        wiederholung: vergessen ? form.elements.wiederholung.value : null });
      if (r.sitzung) schutzSitzungSetzen(r.sitzung);
      SCHUTZ.entsperrt = r;
      fertig();
    } catch (err) {
      fehlerZeigen(karte, err.message);
      knopf.disabled = false;
      if (err.status === 409) fertig();
    }
  });
}

function erstcodeSchirm(karte, st, fertig) {
  const m = st.sperre.mindest;
  karte.innerHTML = `<h2>Eigenen Code festlegen</h2>
    <p>Du bist${st.benutzer.name ? ` als „${schutzEsc(st.benutzer.name)}“` : ""} freigegeben. Lege einmalig deinen Code fest.
      Danach fragt die Finanzverwaltung ihn beim Öffnen ab.</p>
    <form id="schutz-erst-form" autocomplete="off">
      <label>Art</label>
      <select name="art"><option value="pin">PIN (mindestens ${m.pin} Ziffern)</option>
        <option value="passwort">Passwort (mindestens ${m.passwort} Zeichen)</option>
        <option value="muster">Muster (mindestens ${m.muster} Punkte)</option></select>
      <div class="schutz-codefelder"></div>
      <div class="warnung schutz-fehler" hidden></div>
      <div class="reihen-werkzeuge"><button type="submit" class="knopf">Festlegen</button></div>
    </form>`;
  const form = karte.querySelector("form");
  const felder = () => {
    const art = form.elements.art.value;
    form.querySelector(".schutz-codefelder").innerHTML =
      `<label>${ART_NAMEN[art]}</label>${codeFeldHtml(art, "code")}
       <label>${ART_NAMEN[art]} wiederholen</label>${codeFeldHtml(art, "wiederholung")}`;
    musterImFormular(form);
  };
  form.elements.art.addEventListener("change", felder);
  felder();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r = await schutzAnfrage("schutz/erstcode", { art: form.elements.art.value,
        code: codeWert(form, "code"), wiederholung: codeWert(form, "wiederholung") });
      schutzSitzungSetzen(r.sitzung);
      fertig();
    } catch (err) { fehlerZeigen(karte, err.message); }
  });
}

function codeSchirm(karte, st, fertig) {
  const sp = st.sperre;
  const art = sp.art || "pin";
  const mitPassphrase = st.verschluesselung.aktiv && !st.verschluesselung.gesperrt;
  karte.innerHTML = `<h2>Gesperrt</h2>
    <p>${sp.dauerhaft ? "Nach zu vielen Fehlversuchen gesperrt. Ein anderer freigegebener Benutzer kann dich freigeben, "
      + "oder du nutzt den Wiederherstellungsschlüssel der Sperre" + (mitPassphrase ? " oder die Passphrase." : ".")
      : `Bitte ${art === "muster" ? "das Muster zeichnen" : `${ART_NAMEN[art] === "PIN" ? "die PIN" : "das Passwort"} eingeben`}.`}</p>
    <form id="schutz-code-form" autocomplete="off" ${sp.dauerhaft ? "hidden" : ""}>
      ${codeFeldHtml(art, "code")}
      <div class="warnung schutz-fehler" hidden></div>
      <div class="reihen-werkzeuge"><button type="submit" class="knopf">Entsperren</button>
        <button type="button" class="knopf sekundaer klein" data-zeige="schutz-wh-form">Code vergessen?</button></div>
    </form>
    <form id="schutz-wh-form" autocomplete="off" ${sp.dauerhaft ? "" : "hidden"}>
      <label>Wiederherstellungsschlüssel der Sperre</label>
      <input name="schluessel" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="XXXX-XXXX-…">
      <div class="warnung schutz-fehler" hidden></div>
      <div class="reihen-werkzeuge"><button type="submit" class="knopf">Freigeben</button>
        ${mitPassphrase ? '<button type="button" class="knopf sekundaer klein" data-zeige="schutz-pp-frei-form">Mit der Passphrase</button>' : ""}</div>
    </form>
    ${mitPassphrase ? `<form id="schutz-pp-frei-form" autocomplete="off" hidden>
      <label>Passphrase der Verschlüsselung</label>
      <input type="password" name="passphrase" autocomplete="off" data-1p-ignore data-lpignore="true" data-bwignore data-form-type="other">
      <div class="warnung schutz-fehler" hidden></div>
      <div class="reihen-werkzeuge"><button type="submit" class="knopf">Freigeben</button></div>
    </form>` : ""}`;
  const codeForm = karte.querySelector("#schutz-code-form");
  musterImFormular(codeForm);
  karte.querySelectorAll("[data-zeige]").forEach((k) => k.addEventListener("click", () => {
    karte.querySelectorAll("form").forEach((f) => { f.hidden = f.id !== k.dataset.zeige; });
  }));
  const fehler = (form, text) => { const f = form.querySelector(".schutz-fehler"); f.textContent = text; f.hidden = !text; };
  let countdown = null;
  const sperrenFuer = (sekunden) => {
    const knopf = codeForm.querySelector('[type="submit"]');
    clearInterval(countdown);
    let rest = sekunden;
    const tick = () => {
      if (!document.body.contains(codeForm)) { clearInterval(countdown); return; }
      if (rest <= 0) { clearInterval(countdown); knopf.disabled = false; fehler(codeForm, ""); return; }
      knopf.disabled = true;
      fehler(codeForm, `Zu viele Fehlversuche. Nächster Versuch in ${wartenText(rest)}.`);
      rest -= 1;
    };
    tick();
    countdown = setInterval(tick, 1000);
  };
  if (sp.warten && !sp.dauerhaft) sperrenFuer(sp.warten);
  const eingabe = codeForm.querySelector("input");
  if (eingabe && !sp.dauerhaft) eingabe.focus();
  codeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r = await schutzAnfrage("schutz/anmelden", { code: codeWert(codeForm, "code") });
      schutzSitzungSetzen(r.sitzung);
      clearInterval(countdown);
      fertig();
    } catch (err) {
      if (eingabe) eingabe.value = "";
      const muster = codeForm.querySelector("[data-muster]");
      if (muster) musterAufbauen(muster);
      if (err.status === 423) { fertig(); return; }   // jetzt dauerhaft gesperrt: neu zeichnen
      const st2 = await schutzStatusLaden().catch(() => null);
      if (st2 && st2.sperre.warten) sperrenFuer(st2.sperre.warten);
      else fehler(codeForm, err.message);
    }
  });
  karte.querySelector("#schutz-wh-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    try {
      const r = await schutzAnfrage("schutz/wiederherstellen", { schluessel: form.elements.schluessel.value });
      schutzSitzungSetzen(r.sitzung);
      fertig();
    } catch (err) { fehler(form, err.message); }
  });
  const ppForm = karte.querySelector("#schutz-pp-frei-form");
  if (ppForm) ppForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r = await schutzAnfrage("schutz/freigabe-passphrase", { passphrase: ppForm.elements.passphrase.value });
      schutzSitzungSetzen(r.sitzung);
      fertig();
    } catch (err) { fehler(ppForm, err.message); }
  });
}

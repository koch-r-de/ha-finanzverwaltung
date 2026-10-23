"""Fachliche Tests 2.3: Mehrfachfilter Konten/Kategorien (inkl. Unterkategorien), Saldo je Kategorie, Kennzahlen."""
import os, sys, shutil
from datetime import date
from dateutil.relativedelta import relativedelta
code, quelle, ziel = sys.argv[1], sys.argv[2], sys.argv[3]
shutil.rmtree(ziel, ignore_errors=True); shutil.copytree(quelle, ziel)
os.environ["FINANZAPP_DATENVERZEICHNIS"] = ziel
sys.path.insert(0, code)
from fastapi.testclient import TestClient
from app.main import app

ERG = []
def pruef(name, bed, info=""):
    ERG.append((name, bool(bed)))
    print(("OK   " if bed else "FEHL ") + name + (f"  [{info}]" if info and not bed else ""))
def ok(r):
    assert r.status_code < 300, (r.status_code, r.text[:300])
    return r.json()
def nah(a, b, tol=0.02):
    return abs(a - b) <= tol

HEUTE = date.today()
VON, BIS = HEUTE.isoformat(), (HEUTE + relativedelta(years=2)).isoformat()
Z = f"von={VON}&bis={BIS}"

with TestClient(app) as c:
    konten = {k["name"]: k for k in ok(c.get("/api/konten"))}
    kats = ok(c.get("/api/kategorien"))
    kid = {k["name"]: k["id"] for k in kats}
    kinder = lambda pid: [k["id"] for k in kats if k["parent_id"] == pid]
    def teilbaum(pid):
        ids = [pid]
        for k in kinder(pid):
            ids += teilbaum(k)
        return ids
    giro, tg = konten["Girokonto"]["id"], konten["Tagesgeld"]["id"]
    wohnen = teilbaum(kid["Wohnen"])
    liste = lambda ids: ",".join(str(i) for i in ids)

    # ── Konten ──
    alt = ok(c.get(f"/api/auswertungen/cashflow?{Z}&konto_id={giro}"))
    neu = ok(c.get(f"/api/auswertungen/cashflow?{Z}&konten={giro}"))
    pruef("Alter Parameter konto_id liefert dasselbe wie konten=", alt == neu)
    cf_g, cf_t = neu, ok(c.get(f"/api/auswertungen/cashflow?{Z}&konten={tg}"))
    cf_gt = ok(c.get(f"/api/auswertungen/cashflow?{Z}&konten={giro},{tg}"))
    pruef("Cashflow zweier Konten = Summe der einzelnen (je Monat)",
          all(nah(cf_gt[s][i], cf_g[s][i] + cf_t[s][i]) for s in ("einnahmen", "ausgaben") for i in range(len(cf_gt["monate"]))))
    sv_gt = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}&konten={giro},{tg}"))
    sv_g = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}&konten={giro}"))
    pruef("Saldo-Verlauf zweier Konten: genau diese zwei Reihen, Werte wie einzeln",
          [s["konto_id"] for s in sv_gt["konten"]] == sorted([giro, tg], key=lambda i: [k["id"] for k in konten.values()].index(i))
          and next(s for s in sv_gt["konten"] if s["konto_id"] == giro)["werte"] == sv_g["konten"][0]["werte"])
    leer = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}&konten="))
    cf_leer = ok(c.get(f"/api/auswertungen/cashflow?{Z}&konten="))
    pruef("Leere Kontenauswahl: keine Reihen, Cashflow null",
          leer["konten"] == [] and not any(cf_leer["einnahmen"]) and not any(cf_leer["ausgaben"]))
    pruef("Ungültige ID-Liste wird abgelehnt", c.get(f"/api/auswertungen/cashflow?{Z}&konten=1,x").status_code == 422)
    kz = ok(c.get(f"/api/auswertungen/kategorien?{Z}&konten={giro},{tg}"))
    kz_g = {k["kategorie"]: k["summe"] for k in ok(c.get(f"/api/auswertungen/kategorien?{Z}&konten={giro}"))}
    kz_t = {k["kategorie"]: k["summe"] for k in ok(c.get(f"/api/auswertungen/kategorien?{Z}&konten={tg}"))}
    pruef("Kategorien-Rangliste zweier Konten = Summe der einzelnen",
          all(nah(k["summe"], kz_g.get(k["kategorie"], 0) + kz_t.get(k["kategorie"], 0)) for k in kz))

    # ── Kategorien inkl. Unterkategorien ──
    cf_w = ok(c.get(f"/api/auswertungen/cashflow?{Z}&kategorien={liste(wohnen)}"))
    einzeln = [ok(c.get(f"/api/auswertungen/cashflow?{Z}&kategorien={k}")) for k in wohnen]
    pruef("Cashflow Teilbaum Wohnen = Summe der einzelnen Kategorien",
          all(nah(cf_w["ausgaben"][i], sum(e["ausgaben"][i] for e in einzeln)) for i in range(len(cf_w["monate"]))))
    nur_w = ok(c.get(f"/api/auswertungen/cashflow?{Z}&kategorie_id={kid['Wohnen']}"))
    pruef("Unterkategorien zählen mit: Teilbaum Wohnen > nur „Wohnen“ selbst",
          sum(cf_w["ausgaben"]) > sum(nur_w["ausgaben"]), (sum(cf_w["ausgaben"]), sum(nur_w["ausgaben"])))
    zinsen = kats_zins = next(k["id"] for k in kats if k.get("system_key") == "darlehen_zinsen")
    cf_z = ok(c.get(f"/api/auswertungen/cashflow?{Z}&kategorien={zinsen}"))
    pruef("Darlehens-Zinsen gewählt: Raten zählen auch in der Prognose", sum(cf_z["ausgaben"][1:]) > 0, cf_z["ausgaben"][:4])

    # ── Saldo-Verlauf je Kategorie ──
    sv_k = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}&kategorien={liste(wohnen + [kid['Kraftstoff']])}"))
    pruef("Saldo je Kategorie: Modus und Gruppen „Mobilität › Kraftstoff“, „Wohnen“",
          sv_k["modus"] == "kategorien" and [s["name"] for s in sv_k["kategorien"]] == ["Mobilität › Kraftstoff", "Wohnen"]
          and sv_k["darlehen"] == [] and sv_k["stand_heute"] is None, [s["name"] for s in sv_k["kategorien"]])
    ohne_strom = [i for i in wohnen if i != kid["Strom"]]
    sv_t = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}&kategorien={liste(ohne_strom)}"))
    pruef("Teilweise gewählte Oberkategorie heißt „Wohnen (teilweise)“",
          [s["name"] for s in sv_t["kategorien"]] == ["Wohnen (teilweise)"], [s["name"] for s in sv_t["kategorien"]])
    nur_strom = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}&kategorien={kid['Strom']}"))
    pruef("Einzelne Unterkategorie: Name mit Pfad „Wohnen › Strom“", nur_strom["kategorien"][0]["name"] == "Wohnen › Strom")
    w = next(s for s in sv_k["kategorien"] if s["name"] == "Wohnen")["werte"]
    pruef("Saldo je Kategorie: Monatsänderung = Cashflow derselben Auswahl (ab Monat 2)",
          all(nah(w[i] - w[i - 1], cf_w["einnahmen"][i] - cf_w["ausgaben"][i]) for i in range(1, len(w))),
          [(round(w[i] - w[i - 1], 2), round(cf_w["einnahmen"][i] - cf_w["ausgaben"][i], 2)) for i in range(1, 6)])
    sv_kg = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}&kategorien={liste(wohnen)}&konten={giro}"))
    sv_kt = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}&kategorien={liste(wohnen)}&konten={tg}"))
    sv_kgt = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}&kategorien={liste(wohnen)}&konten={giro},{tg}"))
    pruef("Saldo je Kategorie über zwei Konten = Summe je Konto",
          all(nah(sv_kgt["kategorien"][0]["werte"][i], sv_kg["kategorien"][0]["werte"][i] + sv_kt["kategorien"][0]["werte"][i])
              for i in range(len(sv_kgt["monate"]))))

    # ── Kennzahlen-Grundlage ──
    sv = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}"))
    aktiv = [k for k in ok(c.get("/api/konten"))]
    pruef("stand_heute.konten = Summe der Kontostände (wie Startseite)",
          nah(sv["stand_heute"]["konten"], sum(k["saldo"] for k in aktiv)), (sv["stand_heute"], sum(k["saldo"] for k in aktiv)))
    rs = ok(c.get("/api/auswertungen/darlehen"))["kennzahlen"]["restschuld_heute"]
    pruef("stand_heute.restschuld = „Restschuld heute“ im Reiter Darlehen", nah(sv["stand_heute"]["restschuld"], rs),
          (sv["stand_heute"]["restschuld"], rs))
    sv_o = ok(c.get(f"/api/auswertungen/saldo-verlauf?{Z}&inkl_darlehen=false"))
    pruef("Ohne „inkl. Darlehen“: Restschuld 0 und keine Restschuld-Reihen",
          sv_o["stand_heute"]["restschuld"] == 0 and sv_o["darlehen"] == [])
    pruef("Korridor akzeptiert konten=", c.get(f"/api/auswertungen/altersvorsorge-korridor?{Z}&konten={giro},{tg}").status_code == 200)

    # ── Jahresübersicht ──
    j_g = ok(c.get(f"/api/auswertungen/jahresuebersicht?konten={giro}"))
    j_t = ok(c.get(f"/api/auswertungen/jahresuebersicht?konten={tg}"))
    j_gt = ok(c.get(f"/api/auswertungen/jahresuebersicht?konten={giro},{tg}"))
    pruef("Jahresübersicht zweier Konten = Summe der einzelnen",
          nah(j_gt["summe_einnahmen"], j_g["summe_einnahmen"] + j_t["summe_einnahmen"])
          and nah(j_gt["summe_ausgaben"], j_g["summe_ausgaben"] + j_t["summe_ausgaben"]))
    j_w = ok(c.get(f"/api/auswertungen/jahresuebersicht?kategorien={liste(wohnen)}"))
    j_alt = ok(c.get(f"/api/auswertungen/jahresuebersicht?kategorie_id={kid['Wohnen']}"))
    pruef("Jahresübersicht Teilbaum Wohnen ≥ nur „Wohnen“, Hauptkategorie „Wohnen“",
          j_w["summe_ausgaben"] >= j_alt["summe_ausgaben"] and all(k["kategorie"] == "Wohnen" for k in j_w["kategorien"]),
          (j_w["summe_ausgaben"], j_alt["summe_ausgaben"], j_w["kategorien"]))

fehl = [n for n, o in ERG if not o]
print(f"\n{len(ERG) - len(fehl)}/{len(ERG)} bestanden", fehl)

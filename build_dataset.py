#!/usr/bin/env python3
"""
Health Retailers – construction du Data Warehouse (version B) et des jeux Machine Learning,
selon le cahier de spécification (docs/cahier-de-spec.pdf).

Entrée  : ./cleaned/               données réelles nettoyées      (30/09/2024 → 30/04/2025)
          ./cleaned/synthetique/   données synthétiques nettoyées (01/05/2025 → 29/09/2026)
          ./externe/               météo Open-Meteo, épidémies Réseau Sentinelles (téléchargées si absentes)
Sortie  : ./dataset/dwh/   5 dimensions + 4 tables de faits, DICTIONNAIRE_DATASET.md, controles_qualite.csv, README.md
          ./dataset/ml/    6 jeux de données Machine Learning (§11 du cahier), README.md

Modèle (§9 du cahier) :
  dim_temps, dim_produit, dim_client, dim_fournisseur, dim_paiement
  ×  fait_ventes, fait_achats, fait_stock_actuel, fait_paiements
Règle : une colonne n'est stockée que si le cahier l'exige et qu'elle ne peut pas être recalculée ;
le reste est calculé dans Power BI (mesures) ou reste en zone ETL.
Délimitation réel / synthétique : par la date (réel ≤ 30/04/2025), sans colonne dédiée.

Bibliothèque standard uniquement :  python build_dataset.py
"""
import csv
import json
import statistics
from collections import Counter, OrderedDict, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLEAN = HERE / "cleaned"
SYNTH = CLEAN / "synthetique"
EXT = HERE / "externe"
OUT = HERE / "dataset"
START, END_REAL, END = date(2024, 9, 30), date(2025, 4, 30), date(2026, 9, 29)
if not SYNTH.exists():                      # sans données synthétiques : période réelle seule
    END = END_REAL

TABLES = OrderedDict()   # chemin relatif -> infos pour la documentation
CHECKS = []              # contrôles qualité (§7.1)


# --------------------------------------------------------------------------- #
# utilitaires
# --------------------------------------------------------------------------- #
def _read(path):
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def R(name):
    """Fichier nettoyé de l'export réel."""
    return _read(CLEAN / name)


def RA(name):
    """Fichier nettoyé réel + synthétique (empilés ; identifiants disjoints par construction)."""
    rows = R(name)
    if (SYNTH / name).exists():
        rows += _read(SYNTH / name)
    return rows


def W(rel, cols, rows, desc, grain, sources, spec, notes=()):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])
    TABLES[rel] = dict(cols=cols, n=len(rows), desc=desc, grain=grain, sources=sources, spec=spec, notes=list(notes))
    print(f"{rel:52s} {len(rows):>8,} lignes  {len(cols):>3} colonnes")


def check(name, table, count, total, ok_if_zero=True, detail=""):
    status = "OK" if (count == 0) == ok_if_zero else "ATTENTION"
    CHECKS.append(dict(Controle=name, Table=table, NbConcernes=count, NbTotal=total,
                       Pourcentage=f"{100 * count / total:.2f}" if total else "", Statut=status, Detail=detail))


def f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def r2(x, nd=2):
    return "" if x is None else f"{round(x, nd):.{nd}f}".rstrip("0").rstrip(".") or "0"


def d_of(s):
    return date.fromisoformat(s[:10]) if s else None


def hour_of(s):
    return int(s[11:13]) if s and len(s) >= 13 else ""


def datekey(d):
    return d.strftime("%Y%m%d") if d else ""


def week_start(d):
    return d - timedelta(days=d.weekday())


def zscores(values):
    if len(values) < 3:
        return [0.0] * len(values)
    m, s = statistics.mean(values), statistics.pstdev(values)
    return [(v - m) / s if s else 0.0 for v in values]


def fr(n):
    return f"{n:,}".replace(",", " ")


def periode(d):
    return "réelle" if d <= END_REAL else "synthétique"


# --------------------------------------------------------------------------- #
# calendrier français (calculé) et données externes ML (météo, épidémies)
# --------------------------------------------------------------------------- #
def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def holidays(y):
    e = easter(y)
    return {date(y, 1, 1): "Jour de l'an", e + timedelta(1): "Lundi de Pâques", date(y, 5, 1): "Fête du Travail",
            date(y, 5, 8): "Victoire 1945", e + timedelta(39): "Ascension", e + timedelta(50): "Lundi de Pentecôte",
            date(y, 7, 14): "Fête nationale", date(y, 8, 15): "Assomption", date(y, 11, 1): "Toussaint",
            date(y, 11, 11): "Armistice 1918", date(y, 12, 25): "Noël"}


METEO_VILLE, METEO_LAT, METEO_LON = "Paris", 48.8566, 2.3522
SENTI = {"3": "Grippe", "25": "IRA", "6": "Gastro", "7": "Varicelle"}   # indicateur Sentinelles → nom


def download(url, path, force=False):
    import urllib.request
    if force or not path.exists():
        EXT.mkdir(exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as resp:
            path.write_bytes(resp.read())
        print(f"téléchargé : {path.name}")
    return path


def load_meteo():
    url = ("https://archive-api.open-meteo.com/v1/archive?"
           f"latitude={METEO_LAT}&longitude={METEO_LON}&start_date=2024-09-01&end_date={END.isoformat()}"
           "&daily=temperature_2m_mean,temperature_2m_min,temperature_2m_max,precipitation_sum,"
           "sunshine_duration,shortwave_radiation_sum&timezone=Europe%2FParis")
    path = EXT / f"meteo_{METEO_VILLE.lower()}_open-meteo.json"
    covered = path.exists() and json.loads(path.read_text(encoding="utf-8"))["daily"]["time"][-1] >= END.isoformat()
    data = json.loads(download(url, path, force=not covered).read_text(encoding="utf-8"))["daily"]
    out = {}
    for i, day in enumerate(data["time"]):
        g = lambda k: data[k][i]
        out[date.fromisoformat(day)] = {
            "TempMoy": g("temperature_2m_mean"), "TempMin": g("temperature_2m_min"), "TempMax": g("temperature_2m_max"),
            "Pluie_mm": g("precipitation_sum"),
            "Ensoleillement_h": None if g("sunshine_duration") is None else g("sunshine_duration") / 3600,
            "Rayonnement_MJm2": g("shortwave_radiation_sum")}
    return out


def load_sentinelles():
    out = defaultdict(dict)        # (année ISO, semaine ISO) -> {Grippe_Inc100: valeur, …}
    for ind, name in SENTI.items():
        p = download(f"https://www.sentiweb.fr/datasets/all/inc-{ind}-PAY.csv", EXT / f"sentinelles_inc-{ind}-PAY.csv")
        lines = [l for l in p.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
        for r in csv.DictReader(lines):
            wk = r["week"]
            if r["inc100"] not in ("", "-", "NA"):
                out[(int(wk[:4]), int(wk[4:]))][f"{name}_Inc100"] = float(r["inc100"])
    return out


def build_calendar():
    hol = {}
    for y in range(START.year, END.year + 1):
        hol.update(holidays(y))
    rows, cal = [], {}
    d = START
    while d <= END:
        iso = d.isocalendar()
        rows.append(dict(DateKey=datekey(d), Date=d.isoformat(), Annee=d.year, Trimestre=(d.month - 1) // 3 + 1,
                         Mois=d.month, SemaineISO=iso[1], EstFerie="true" if d in hol else "false"))
        cal[d] = dict(iso=(iso[0], iso[1]), AnneeSemaine=f"{iso[0]}-S{iso[1]:02d}", ferie=d in hol)
        d += timedelta(1)
    W("dwh/dim_temps.csv", list(rows[0].keys()), rows,
      "Dimension Temps : date, année, trimestre, mois, semaine ISO, jour férié.",
      f"1 ligne = 1 date ({START:%d/%m/%Y} → {END:%d/%m/%Y})",
      "Calculée : calendrier français (fêtes fixes et fêtes mobiles calculées à partir de Pâques)",
      "§7 et §9 du cahier : « Date, semaine, mois, trimestre, année, EstFerie »",
      ["Le calendrier français est calculé : ce n'est pas une source externe.",
       "Pas de vacances scolaires, de météo ni d'indicateur épidémique dans cette dimension : la météo et les "
       "épidémies sont réservées au jeu ML de prévision (§4.2, §8).",
       f"Délimitation réel / synthétique par la date : réel jusqu'au {END_REAL:%d/%m/%Y} inclus."])
    return cal


# --------------------------------------------------------------------------- #
# DIMENSIONS
# --------------------------------------------------------------------------- #
def build_products(lines_by_ps, moves):
    stocks = R("product_stocks.csv")
    prods = R("products.csv")
    prio = {"code": 0, "barcode": 1, "name": 2}
    best = {}
    for p in prods:
        pid = p["Product_Id"]
        if pid and (pid not in best or prio.get(p["ProductIdSource"], 9) < prio.get(best[pid]["ProductIdSource"], 9)):
            best[pid] = p
    labels = {}
    for e in R("audit_events.csv"):
        if e["Entity"] == "PRODUCT" and e["Data_lbl"]:
            labels[e["EntityId"]] = e["Data_lbl"]            # dernier libellé connu (fichier trié par Id)
    brands = sorted({b["BrandName"] for b in R("brands.csv")}, key=len, reverse=True)
    rows, full, src_name, src_alert = [], {}, Counter(), Counter()
    for s in stocks:
        pid = s["Product_Id"]
        p = best.get(pid, {})
        name = p.get("Libellé") or labels.get(pid) or lines_by_ps.get(s["Id"], "")
        src_name["Produits" if p else "Events" if pid in labels else "documentItemm" if name else "absent"] += 1
        brand = p.get("Marque", "")
        if not brand and name:
            up = name.upper()
            brand = next((b for b in brands if up.startswith(b + " ") or up == b), "")
        alert = p.get("Quantité d'Alerte") or "5"
        src_alert["export Produits" if p.get("Quantité d'Alerte") else "paramètre par défaut (5)"] += 1
        r = {"Product_Id": pid, "Libellé": name or f"PRODUIT {pid}", "Famille": p.get("Famille") or "NON RENSEIGNE",
             "Marque": brand or "NON RENSEIGNE"}
        rows.append(r)
        full[pid] = {**r, "QuantiteAlerte": r2(f(alert), 3), "FamilyGroup": p.get("FamilyGroup") or "NON RENSEIGNE",
                     "PrixAchatHT": p.get("Prix d'achat HT", ""), "ProductIdSource": p.get("ProductIdSource", "non rapproche")}
    unmatched = sum(1 for v in full.values() if v["ProductIdSource"] == "non rapproche")
    check("Produit du référentiel interne absent de l'export Produits", "dim_produit", unmatched, len(rows),
          detail="famille indisponible ; libellé repris des événements ou des lignes de vente ; seuil d'alerte = 5")
    W("dwh/dim_produit.csv", list(rows[0].keys()), rows,
      "Dimension Produit : libellé, famille, marque.",
      "1 ligne = 1 produit du référentiel interne (ProductStocks), clé Product_Id",
      "ProductStocks, Produits, Events (libellés), ProductBrands, users_settings (seuil par défaut)",
      "§7 et §9 du cahier : « Libellé, Famille, Marque » ; §6.2, §6.4, §6.6",
      [f"Libellé : {dict(src_name)}.",
       "Marque manquante : déduite si le libellé commence par un nom de ProductBrands, sinon `NON RENSEIGNE`.",
       "Le seuil d'alerte de stock (QuantiteAlerte) est stocké dans `fait_stock_actuel`, à côté de la quantité.",
       "Les prix d'achat / de vente et le coût moyen pondéré restent en zone ETL : ils servent à calculer `CA_HT` et "
       "`Cout_HT`, aucun KPI n'utilise le prix catalogue."])
    ALERT_SOURCES.update(src_alert)
    return full


ALERT_SOURCES = Counter()   # origine du seuil d'alerte, documentée dans fait_stock_actuel


def build_clients(sale_company_ids):
    companies = {c["Id"]: c for c in R("companies.csv")}
    custs = {c["Code"]: c for c in R("customers.csv")}
    typ = {"INDIVIDUAL": "PARTICULIER", "LABORATORY": "B2B"}
    rows = []
    ids = {i for i, c in companies.items() if c["CompanyType"] == "CUSTOMER"} | (sale_company_ids & set(companies))
    for i in sorted(ids, key=int):
        c = companies[i]
        cu = custs.get(c["Code"], {})
        walk = i == "2"
        rows.append({"Company_Id": i, "Nom": cu.get("Nom") or c["Name"],
                     "TypeClient": "COMPTOIR_ANONYME" if walk else typ.get(cu.get("CustomerType"), "NON RENSEIGNE"),
                     "EstClientIdentifie": "false" if walk else "true"})
    unknown = sale_company_ids - set(companies) - {"-1"}
    for i in sorted(unknown, key=int):
        rows.append({"Company_Id": i, "Nom": f"CLIENT INCONNU {i}", "TypeClient": "NON RENSEIGNE",
                     "EstClientIdentifie": "true"})
    rows.append({"Company_Id": "-1", "Nom": "NON RENSEIGNE", "TypeClient": "NON RENSEIGNE", "EstClientIdentifie": "false"})
    check("Company_Id client absent de CompaniesList", "fait_ventes / fait_paiements", len(unknown), len(sale_company_ids),
          detail="ajoutés dans dim_client comme 'CLIENT INCONNU <id>' ; -1 = client non renseigné")
    types = Counter(r["TypeClient"] for r in rows)
    W("dwh/dim_client.csv", list(rows[0].keys()), rows,
      "Dimension Client : nom, type de client, client identifié ou non.",
      "1 ligne = 1 client, y compris le client comptoir anonyme (clé Company_Id, celle des transactions)",
      "CompaniesList, Clients, Transactions", "§6.3 Analyse des clients ; §9 Dimension Client",
      [f"TypeClient : {dict(types)}. Company_Id 2 = client comptoir anonyme (la majorité des ventes comptoir).",
       "`EstClientIdentifie` = false pour le client comptoir et la ligne -1 : filtre de tous les KPI clients "
       "(§6.3 : les transactions anonymes ne sont pas utilisées pour les KPI clients).",
       "Le nom vient du fichier Clients quand le code y existe (les noms de CompaniesList ont été anonymisés différemment) ; "
       "le code client sert seulement à cette jointure dans l'ETL."])
    return {r["Company_Id"]: r for r in rows}


def build_suppliers(used_ids):
    companies = {c["Id"]: c for c in R("companies.csv")}
    names = {s["Code"]: s["Nom"] for s in R("suppliers.csv")}
    ids = {i for i, c in companies.items() if c["CompanyType"] == "SUPPLIER"}
    rows = [{"Fournisseur_Id": i, "Nom": names.get(companies[i]["Code"]) or companies[i]["Name"]}
            for i in sorted(ids, key=int)]
    unknown = used_ids - set(companies) - {"-1", ""}
    rows += [{"Fournisseur_Id": i, "Nom": f"FOURNISSEUR INCONNU {i}"} for i in sorted(unknown, key=int)]
    rows.append({"Fournisseur_Id": "-1", "Nom": "NON RENSEIGNE"})
    check("Fournisseur d'un achat ou d'un paiement absent de CompaniesList", "fait_achats / fait_paiements",
          len(unknown), len(used_ids - {"-1", ""}),
          detail="ajoutés dans dim_fournisseur comme 'FOURNISSEUR INCONNU <id>' ; -1 = fournisseur non renseigné")
    W("dwh/dim_fournisseur.csv", list(rows[0].keys()), rows,
      "Dimension Fournisseur : nom du fournisseur.",
      "1 ligne = 1 fournisseur (clé Fournisseur_Id = identifiant de la société dans le logiciel)",
      "CompaniesList (sociétés de type fournisseur), Fournisseurs (noms), Transactions",
      "§6.6 Achats ; §6.5 Paiements ; §9 Dimension Fournisseur",
      ["Le nom vient du fichier Fournisseurs quand le code y existe (les noms de CompaniesList ont été anonymisés "
       "différemment) ; le code fournisseur sert seulement à cette jointure dans l'ETL.",
       f"{fr(len(unknown))} fournisseurs cités par des factures ou des paiements sont absents de CompaniesList : "
       "conservés comme 'FOURNISSEUR INCONNU <id>'. -1 = fournisseur non renseigné (et valeur des lignes qui ne "
       "concernent pas un fournisseur dans fait_paiements)."])
    return {r["Fournisseur_Id"] for r in rows}


PAY_FR = {"11": "Espèces", "5": "Carte bancaire", "1": "Chèque", "7": "Crédit (paiement différé)", "21": "Jetons",
          "-1": "Non renseigné"}


def build_payment_modes():
    rows = [{"PaymentMode_Id": k, "PaymentModeName": v} for k, v in PAY_FR.items()]
    W("dwh/dim_paiement.csv", list(rows[0].keys()), rows, "Dimension Paiement : moyen de paiement.",
      "1 ligne = 1 moyen de paiement", "PaymentsList (PaymentMode_Id / PaymentMethodName)",
      "§6.5 Paiements ; §9 « Libellé / type de moyen »",
      ["-1 = paiement sans moyen renseigné dans la source (encaissements de caisse).",
       "Le mode « Inconnu (4) » du logiciel n'est utilisé par aucun paiement : il n'est pas repris."])


# --------------------------------------------------------------------------- #
# FAITS
# --------------------------------------------------------------------------- #
CANAL = {"6": "COMPTOIR", "1": "FACTURE", "5": "FACTURE", "4": "FACTURE", "7": "FACTURE"}
SALES_COLS = ["Id", "Document_Id", "DateKey", "Product_Id", "Company_Id", "QuantiteVendue", "Remise_HT", "CA_HT", "Cout_HT"]


def build_sales(docs_by_id, items, linked_invoices, txn, products, cost_by_line):
    rows, excluded = [], Counter()
    for it in items:
        d = docs_by_id.get(it["Document_Id"])
        if not d:
            excluded["ligne sans document"] += 1
            continue
        if d["Flow"] not in ("SALE", "SALE_RETURN"):
            continue
        if not it["Product_Id"] and f(it["PrixTotalHt"]) == 0:
            excluded["ligne de commentaire sans produit ni montant"] += 1
            continue
        if d["IsValidated"] != "true":
            excluded["document brouillon (State = 0)"] += 1
            continue
        if d["Id"] in linked_invoices:
            excluded["facture client regroupant des BL déjà comptés"] += 1
            continue
        sign = -1 if d["Flow"] == "SALE_RETURN" else 1
        dd = d_of(d["DocumentDate"])
        q, ht, ttc = f(it["Quantity"]), f(it["PrixTotalHt"]), f(it["PrixTotalTtc"])
        p = products.get(it["Product_Id"], {})
        cu, src = cost_by_line.get((it["Document_Id"], it["ProductStock_Id"])), "CUMP_MOUVEMENT"
        if cu is None and f(p.get("PrixAchatHT"), 0) > 0:
            cu, src = f(p["PrixAchatHT"]), "PRIX_ACHAT_PRODUIT"
        if cu is None:
            src = "ABSENT"
        cost = q * cu if cu is not None else None
        rows.append({
            # colonnes du Data Warehouse
            "Id": it["Id"], "Document_Id": d["Id"], "DateKey": datekey(dd), "Product_Id": it["Product_Id"],
            "Company_Id": txn.get(d["Transaction_Id"]) or "-1",
            "QuantiteVendue": r2(sign * q, 4), "Remise_HT": r2(sign * f(it["SumDiscountTotal"]), 4),
            "CA_HT": r2(sign * ht, 4), "Cout_HT": r2(sign * cost, 4) if cost is not None else "",
            # colonnes de travail (zone ETL → jeux ML), non écrites dans le DWH
            "Date": dd.isoformat(), "Heure": hour_of(d["CreatedDate"]), "CreatedBy": d["CreatedBy"],
            "Canal": CANAL.get(d["DocumentType_Id"], ""), "Signe": sign, "Quantity": it["Quantity"],
            "PrixHt": it["PrixHt"], "PrixTotalHt": it["PrixTotalHt"], "DiscountPourcentage": it["DiscountPourcentage"] or "0",
            "CA_TTC": sign * ttc, "SourceCout": src,
            "VenteSousCout": cost is not None and q > 0 and ht < cost - 0.005,
        })
    srcs = Counter(r["SourceCout"] for r in rows)
    real = sum(1 for r in rows if r["Date"] <= END_REAL.isoformat())
    W("dwh/fait_ventes.csv", SALES_COLS, rows,
      "Fait Ventes : ligne de produit vendue (ou retournée) dans un document validé à une date donnée.",
      "1 ligne = 1 produit vendu dans 1 document à 1 date",
      "documentItemm, Documents, Transactions, StockMovements (coût) — réel + synthétique",
      "§6.1, §6.2, §6.3 ; §9 fait_ventes (Document_Id, QuantiteVendue, CA_HT, Remise_HT, Cout_HT)",
      [f"{fr(real)} lignes de la période réelle et {fr(len(rows) - real)} lignes de la période synthétique "
       f"(délimitation par la date : réel jusqu'au {END_REAL:%d/%m/%Y}).",
       "Ventes = vente comptoir (6), bon de livraison (5), facture client (1) ; retours = avoir (4) et bon de retour (7) "
       "en négatif : `QuantiteVendue`, `CA_HT`, `Remise_HT`, `Cout_HT` sont signés.",
       "`Document_Id` est une dimension dégénérée : Nombre de ventes = COUNT(DISTINCT Document_Id), "
       "panier moyen = SUM(CA_HT) / Nombre de ventes.",
       "Exclusions : " + "; ".join(f"{k} : {fr(v)} lignes" for k, v in excluded.items()) + ".",
       f"Coût : {dict(srcs)} — CUMP = coût moyen pondéré au moment de la vente (StockMovements), sinon prix d'achat HT "
       "du produit. Marge HT = SUM(CA_HT) − SUM(Cout_HT) est une mesure Power BI, pas une colonne.",
       "Retirés de la version précédente : CA_TTC (recalculable), Marge_HT (mesure), coût unitaire, signe, taux de "
       "remise, colonnes brutes et colonnes document / utilisateur / moyen de paiement."])
    return rows


PURCHASE_COLS = ["Id", "Document_Id", "DateKey", "Product_Id", "Fournisseur_Id", "QuantiteAchetee", "MontantAchat_HT"]


def build_purchases(docs_by_id, items, txn, suppliers):
    rows, excluded = [], Counter()
    for it in items:
        d = docs_by_id.get(it["Document_Id"])
        if not d or d["Flow"] not in ("PURCHASE", "PURCHASE_RETURN"):
            continue
        if not it["Product_Id"] and f(it["PrixTotalHt"]) == 0:
            excluded["ligne de commentaire sans produit ni montant"] += 1
            continue
        if d["IsValidated"] != "true":
            excluded["document brouillon (State = 0)"] += 1
            continue
        sign = -1 if d["Flow"] == "PURCHASE_RETURN" else 1
        dd = d_of(d["DocumentDate"])
        sup = txn.get(d["Transaction_Id"]) or "-1"
        rows.append({"Id": it["Id"], "Document_Id": d["Id"], "DateKey": datekey(dd), "Product_Id": it["Product_Id"],
                     "Fournisseur_Id": sup if sup in suppliers else "-1",
                     "QuantiteAchetee": r2(sign * f(it["Quantity"]), 4),
                     "MontantAchat_HT": r2(sign * f(it["PrixTotalHt"]), 4), "_date": dd})
    real = sum(1 for r in rows if r["_date"] <= END_REAL)
    no_sup = sum(1 for r in rows if r["Fournisseur_Id"] == "-1")
    check("Ligne d'achat sans fournisseur identifié", "fait_achats", no_sup, len(rows),
          detail="facture fournisseur dont la transaction ne cite aucune société : Fournisseur_Id = -1")
    W("dwh/fait_achats.csv", PURCHASE_COLS, rows,
      "Fait Achats : ligne de produit achetée (ou retournée) à un fournisseur dans une facture validée.",
      "1 ligne = 1 produit acheté dans 1 facture fournisseur à 1 date",
      "documentItemm, Documents (factures et avoirs fournisseurs), Transactions — réel + synthétique",
      "§6.6 Achats ; §9 fait_achats (Document_Id, QuantiteAchetee, MontantAchat_HT)",
      [f"{fr(real)} lignes de la période réelle et {fr(len(rows) - real)} lignes de la période synthétique.",
       "Achats = facture fournisseur (20) ; retours = avoir fournisseur (23) en négatif : `QuantiteAchetee` et "
       "`MontantAchat_HT` sont signés. Aucune facture fournisseur ne regroupe d'autres documents : pas de double comptage.",
       "`Document_Id` est une dimension dégénérée : Nombre de factures fournisseurs = COUNT(DISTINCT Document_Id).",
       "`MontantAchat_HT` = montant HT de la ligne après remise. Le prix d'achat unitaire n'est pas stocké : "
       "SUM(MontantAchat_HT) / SUM(QuantiteAchetee).",
       "Exclusions : " + ("; ".join(f"{k} : {fr(v)} lignes" for k, v in excluded.items()) or "aucune") + "."])
    return rows


def build_stock(products):
    src = SYNTH if (SYNTH / "product_stocks.csv").exists() else CLEAN
    stocks = {s["Product_Id"]: s for s in _read(src / "product_stocks.csv")}
    rows = [{"Product_Id": pid, "DateKey": datekey(END), "Quantity": r2(f(stocks.get(pid, {}).get("Quantity")), 3),
             "QuantiteAlerte": p["QuantiteAlerte"]} for pid, p in products.items()]
    neg = sum(1 for r in rows if f(r["Quantity"]) < 0)
    zero = sum(1 for r in rows if f(r["Quantity"]) == 0)
    low = sum(1 for r in rows if 0 < f(r["Quantity"]) <= f(r["QuantiteAlerte"]))
    check("Produit à stock négatif (vente enregistrée sans réception)", "fait_stock_actuel", neg, len(rows),
          detail="conservé tel quel (défaut de saisie du logiciel) ; compte comme rupture potentielle")
    W("dwh/fait_stock_actuel.csv", list(rows[0].keys()), rows,
      "Fait Stock actuel : quantité en stock et seuil d'alerte de chaque produit à la date du snapshot.",
      f"1 ligne = 1 produit à la date de snapshot ({END:%d/%m/%Y}, fin de la période chargée)",
      "ProductStocks (" + ("données synthétiques, état au 29/09/2026" if src == SYNTH else "export réel")
      + "), Produits (seuil d'alerte)",
      "§6.4 Gestion du stock ; §9 « Quantity, QuantiteAlerte. Rupture et stock faible sont calculés »",
      [f"Au snapshot : {fr(zero)} produits à 0 (rupture), {fr(low)} en stock faible (0 < Quantity ≤ QuantiteAlerte), "
       f"{fr(neg)} à stock négatif.",
       "Rupture et stock faible ne sont pas stockés : mesures Power BI à partir de `Quantity` et de `QuantiteAlerte`, "
       "dans la même table.",
       f"QuantiteAlerte : {dict(ALERT_SOURCES)}. Seuil choisi par le magasin pour chaque produit (pas une valeur "
       "calculable). Une ligne par produit : le seuil n'est stocké qu'une fois.",
       "Pas d'historique de stock dans le BI (rotation non retenue, §6.4) : les mouvements restent en zone ETL."])


def payment_side(p, ctype):
    """Le paiement concerne-t-il un fournisseur ? (type de société, sinon libellé du paiement)."""
    t = ctype.get(p["Company_Id"])
    return t == "SUPPLIER" if t in ("SUPPLIER", "CUSTOMER") else p["IsPurchase"] == "true"


PAYMENT_COLS = ["Id", "DateKey", "PaymentMode_Id", "Company_Id", "Fournisseur_Id", "Amount"]


def build_payments(pays, ctype, clients, suppliers):
    rows = []
    for p in pays:
        dd = d_of(p["PaymentDate"])
        mode = p["PaymentMode_Id"] or "-1"
        cid = p["Company_Id"] or "-1"
        to_supplier = payment_side(p, ctype)
        rows.append({"Id": p["Id"], "DateKey": datekey(dd), "PaymentMode_Id": mode if mode in PAY_FR else "-1",
                     "Company_Id": "-1" if to_supplier else (cid if cid in clients else "-1"),
                     "Fournisseur_Id": (cid if cid in suppliers else "-1") if to_supplier else "-1",
                     "Amount": p["Amount"], "_date": dd, "_sup": to_supplier})
    sup = [r for r in rows if r["_sup"]]
    cli = [r for r in rows if not r["_sup"]]
    nomode = sum(1 for r in cli if r["PaymentMode_Id"] == "-1")
    check("Paiement client sans moyen de paiement renseigné", "fait_paiements", nomode, len(cli),
          detail="limite de la source (encaissements de caisse) : la répartition par moyen est dominée par « Non renseigné »")
    check("Paiement fournisseur sans fournisseur identifié", "fait_paiements",
          sum(1 for r in sup if r["Fournisseur_Id"] == "-1"), len(sup),
          detail="doit être 0 : sinon le paiement serait compté dans le montant encaissé")
    check("Paiement client sans client identifié", "fait_paiements", sum(1 for r in cli if r["Company_Id"] == "-1"), len(cli))
    walk = sum(1 for r in cli if r["Company_Id"] == "2")
    real = sum(1 for r in rows if r["_date"] <= END_REAL)
    W("dwh/fait_paiements.csv", PAYMENT_COLS, rows,
      "Fait Paiements : montant réellement versé, moyen de paiement, date ; client qui paie ou fournisseur payé.",
      "1 ligne = 1 paiement", "PaymentsList + Payment (fusionnés), CompaniesList — réel + synthétique",
      "§6.5 Paiements ; §6.6 Achats ; §9 fait_paiements (Amount ; client ; fournisseur)",
      [f"{fr(real)} paiements de la période réelle et {fr(len(rows) - real)} de la période synthétique.",
       "Encaissement client : `Company_Id` = client qui paie (2 = client comptoir anonyme), `Fournisseur_Id` = -1. "
       "Paiement fournisseur : `Fournisseur_Id` = fournisseur payé, `Company_Id` = -1.",
       f"Montant encaissé = SUM(Amount) où Fournisseur_Id = -1 : {fr(round(sum(f(r['Amount']) for r in cli)))} "
       f"sur {fr(len(cli))} paiements clients (dont {fr(walk)} au comptoir) ; {fr(len(sup))} paiements fournisseurs "
       f"({fr(round(sum(f(r['Amount']) for r in sup)))}).",
       "Le client et le fournisseur viennent directement du paiement source (`Company_Id` de PaymentsList, identique "
       "à celui de la transaction réglée sur 100 % des liens TransactionPayments).",
       "`Amount` est TTC et n'est pas le CA : impayés, paiements fractionnés ou différés.",
       "`EstPaiementFournisseur` est retiré : il se recalcule (paiement fournisseur ⇔ Fournisseur_Id ≠ -1).",
       "Retirés de la version précédente : UsedAmount (égal à Amount à 99,9 %), document, heure, caisse, compte bancaire."])


# --------------------------------------------------------------------------- #
# MACHINE LEARNING
# --------------------------------------------------------------------------- #
METEO_COLS = ["Meteo_TempMoyenne", "Meteo_TempMin", "Meteo_TempMax", "Meteo_Pluie_mm", "Meteo_NbJoursPluie",
              "Meteo_Ensoleillement_h", "Meteo_Rayonnement_MJm2"]


def ml_demand(sales, products, cal, meteo, senti):
    weeks, w = [], week_start(START)
    while w <= END:
        weeks.append(w)
        w += timedelta(7)

    def week_feats(w):
        days = [w + timedelta(i) for i in range(7)]
        inside = [d for d in days if d in cal]
        mt = [meteo[d] for d in days if d in meteo]
        v = lambda k: [m[k] for m in mt if m.get(k) is not None]
        tm, tn, tx, pl, so, ra = (v(k) for k in ("TempMoy", "TempMin", "TempMax", "Pluie_mm", "Ensoleillement_h",
                                                 "Rayonnement_MJm2"))
        out = dict(NbJoursFeries=sum(cal[d]["ferie"] for d in inside),
                   NbJoursOuvres=sum(d.weekday() < 6 and not cal[d]["ferie"] for d in inside),
                   Mois=w.month, SemaineISO=cal[w]["iso"][1],
                   Meteo_TempMoyenne=r2(statistics.mean(tm), 2) if tm else "", Meteo_TempMin=r2(min(tn), 2) if tn else "",
                   Meteo_TempMax=r2(max(tx), 2) if tx else "", Meteo_Pluie_mm=r2(sum(pl), 2) if pl else "",
                   Meteo_NbJoursPluie=sum(x >= 1 for x in pl) if pl else "",
                   Meteo_Ensoleillement_h=r2(sum(so), 2) if so else "", Meteo_Rayonnement_MJm2=r2(sum(ra), 2) if ra else "")
        s = senti.get(cal[w]["iso"], {})
        for name in SENTI.values():
            out[f"{name}_Inc100"] = r2(s[f"{name}_Inc100"], 2) if f"{name}_Inc100" in s else ""
        return out

    feats = {w: week_feats(w) for w in weeks}
    brand_qty = Counter()
    for s in sales:
        brand_qty[products.get(s["Product_Id"], {}).get("Marque", "NON RENSEIGNE")] += f(s["QuantiteVendue"])
    top = {b for b, _ in brand_qty.most_common(26) if b != "NON RENSEIGNE"}
    last_real_week = week_start(END_REAL)             # dernière semaine ENTIÈREMENT réelle
    if last_real_week + timedelta(6) > END_REAL:
        last_real_week -= timedelta(7)

    for level, keyf, fname, label in (
            ("FamilyGroup", lambda p: p.get("FamilyGroup", "NON RENSEIGNE"),
             "ml/ml_11_1_prevision_demande_famille_hebdo.csv", "famille"),
            ("Marque", lambda p: p.get("Marque") if p.get("Marque") in top else "AUTRES MARQUES",
             "ml/ml_11_1_prevision_demande_marque_hebdo.csv", "marque")):
        agg = defaultdict(lambda: dict(q=0.0, ca=0.0, brut=0.0, rem=0.0, qc=0.0, docs=set()))
        groups = set()
        for s in sales:
            g = keyf(products.get(s["Product_Id"], {}))
            groups.add(g)
            a = agg[(g, week_start(date.fromisoformat(s["Date"])))]
            q = f(s["QuantiteVendue"])
            a["q"] += q
            a["ca"] += f(s["CA_HT"])
            a["brut"] += f(s["CA_HT"]) + f(s["Remise_HT"])
            a["rem"] += f(s["Remise_HT"])
            a["qc"] += q if s["Canal"] == "COMPTOIR" else 0
            a["docs"].add(s["Document_Id"])
        rows = []
        for g in sorted(groups):
            hist, start_i = [], len(rows)
            for w in weeks:
                a = agg.get((g, w), dict(q=0.0, ca=0.0, brut=0.0, rem=0.0, qc=0.0, docs=set()))
                lag = lambda k: r2(hist[-k], 3) if len(hist) >= k else ""
                r = {level: g, "SemaineDebut": w.isoformat(), "AnneeSemaine": cal[w]["AnneeSemaine"],
                     "Y_Quantite": r2(a["q"], 3), "Y_QuantiteSemaineSuivante": "",
                     "X_Qte_Lag1": lag(1), "X_Qte_Lag2": lag(2), "X_Qte_Lag4": lag(4),
                     "X_Qte_MoyenneMobile4": r2(statistics.mean(hist[-4:]), 3) if len(hist) >= 4 else "",
                     "X_CA_HT": r2(a["ca"], 2), "X_PrixMoyen_HT": r2(a["ca"] / a["q"], 3) if a["q"] > 0 else "",
                     "X_TauxRemisePct": r2(100 * a["rem"] / a["brut"], 2) if a["brut"] > 0 else "0",
                     "X_PartComptoirPct": r2(100 * a["qc"] / a["q"], 2) if a["q"] > 0 else "",
                     "X_NbDocuments": len(a["docs"])}
                r.update({"X_" + k: v for k, v in feats[w].items()})
                r["SemaineComplete"] = "true" if w + timedelta(6) <= END and w >= START else "false"
                rows.append(r)
                hist.append(a["q"])
            for i in range(start_i, len(rows) - 1):          # cible t+1 pour une prévision à 1 semaine
                rows[i]["Y_QuantiteSemaineSuivante"] = rows[i + 1]["Y_Quantite"]
        W(fname, list(rows[0].keys()), rows,
          f"ML 11.1 – Prévision de la demande : quantité vendue par {label} et par semaine.",
          f"1 ligne = 1 semaine × 1 {label} (toutes les semaines, 0 si aucune vente)",
          "fait_ventes, dim_produit, calendrier ; externes : Open-Meteo, Réseau Sentinelles",
          "§11.1 Prévision de la demande (régression / séries temporelles), horizon N+1 semaine",
          ["Cible Y : `Y_QuantiteSemaineSuivante` (prévision N+1) ; `Y_Quantite` = semaine courante. Variables explicatives "
           "préfixées `X_` (§15 : séparer X, Y, granularité et métrique).",
           "X internes : lags 1/2/4, moyenne mobile 4 semaines (toujours sur le passé), CA, prix moyen, taux de remise, "
           "part comptoir, nombre de documents. X temporelles : semaine ISO, mois, jours fériés, jours ouvrés.",
           f"X externes candidates (§8) : météo de la semaine ({METEO_VILLE}, Open-Meteo) `X_Meteo_*` et épidémies "
           "(Réseau Sentinelles, France, /100 000 hab.) `X_Grippe_Inc100`, `X_IRA_Inc100`, `X_Gastro_Inc100`, "
           "`X_Varicelle_Inc100`. Pas de vacances scolaires.",
           f"Période réelle = semaines commençant jusqu'au {last_real_week:%d/%m/%Y} inclus ; la semaine suivante mélange "
           "réel et synthétique, les autres sont synthétiques. Règle du §8 : "
           "l'apport de la météo et des épidémies se mesure sur la période réelle uniquement (ces effets ont servi "
           "d'hypothèses à la génération) — comparer le modèle avec et sans ces variables (MAE / RMSE, baseline = X_Qte_Lag1).",
           "Ne pas entraîner sur les semaines `SemaineComplete = false` (bords de période). Sentinelles publie avec "
           "~1 semaine de délai : en production, décaler les épidémies d'une semaine."]
          + (["Les 26 marques les plus vendues sont gardées, les autres regroupées en `AUTRES MARQUES`."]
             if level == "Marque" else []))


def ml_sales_anomalies(sales, products):
    lines = [s for s in sales if s["Signe"] == 1]
    by_prod = defaultdict(list)
    for s in lines:
        by_prod[s["Product_Id"]].append(s)
    ref_price, zq = {}, {}
    for pid, ls in by_prod.items():
        ref_price[pid] = statistics.median(f(s["PrixHt"]) for s in ls)
        for s, z in zip(ls, zscores([f(s["Quantity"]) for s in ls])):
            zq[s["Id"]] = z
    lines_per_doc = Counter(s["Document_Id"] for s in lines)
    user_disc = defaultdict(list)
    for s in lines:
        user_disc[s["CreatedBy"]].append(f(s["DiscountPourcentage"]))
    user_avg = {u: statistics.mean(v) for u, v in user_disc.items()}
    rows = []
    for s in lines:
        d = date.fromisoformat(s["Date"])
        rp = ref_price.get(s["Product_Id"], 0)
        cost = f(s["Cout_HT"]) if s["Cout_HT"] != "" else None
        disc = f(s["DiscountPourcentage"])
        r1, r2_, r3 = disc > 50, s["VenteSousCout"], abs(zq.get(s["Id"], 0)) > 3
        rows.append({
            "Id": s["Id"], "Document_Id": s["Document_Id"], "DateKey": s["DateKey"], "Product_Id": s["Product_Id"],
            "FamilyGroup": products.get(s["Product_Id"], {}).get("FamilyGroup", ""),
            "X_CreatedBy": s["CreatedBy"], "X_Heure": s["Heure"], "X_JourSemaine": d.isoweekday(), "X_Canal": s["Canal"],
            "X_Quantity": s["Quantity"], "X_Quantity_ZScoreProduit": r2(zq.get(s["Id"], 0), 3),
            "X_PrixHt": s["PrixHt"], "X_PrixHt_Reference": r2(rp, 3),
            "X_EcartPrixReferencePct": r2(100 * (f(s["PrixHt"]) - rp) / rp, 2) if rp else "",
            "X_DiscountPourcentage": s["DiscountPourcentage"], "X_PrixTotalHt": s["PrixTotalHt"],
            "X_Cout_HT": r2(cost, 4) if cost is not None else "", "X_SourceCout": s["SourceCout"],
            "X_EcartPrixTotalHtCoutPct": r2(100 * (f(s["PrixTotalHt"]) - cost) / cost, 2) if cost else "",
            "X_NbLignesDocument": lines_per_doc[s["Document_Id"]],
            "X_RemiseMoyenneUtilisateur": r2(user_avg[s["CreatedBy"]], 2),
            "Regle_RemiseSup50": str(r1).lower(), "Regle_VenteSousCout": str(r2_).lower(),
            "Regle_QuantiteAtypique": str(r3).lower(), "ScoreRegles": int(r1) + int(r2_) + int(r3),
        })
    n50 = sum(r["Regle_RemiseSup50"] == "true" for r in rows)
    nsc = sum(r["Regle_VenteSousCout"] == "true" for r in rows)
    withcost = sum(r["X_Cout_HT"] != "" for r in rows)
    check("Ligne de vente sous le coût", "fait_ventes", nsc, len(rows), detail="règle d'interprétation du ML 11.2")
    W("ml/ml_11_2_anomalies_ventes.csv", list(rows[0].keys()), rows,
      "ML 11.2 – Détection d'anomalies sur les lignes de vente (remise, prix vs coût, quantité, utilisateur, heure).",
      "1 ligne = 1 ligne de vente (retours exclus)", "fait_ventes + colonnes de la zone ETL (heure, vendeur, prix, remise)",
      "§11.2 Détection d'anomalies (non supervisé : Isolation Forest, LOF…)",
      ["Pas de cible Y étiquetée : apprentissage non supervisé sur les colonnes `X_`.",
       "Les colonnes `Regle_*` sont des règles métier pour contrôler les résultats, pas une vérité terrain : ne pas les "
       "utiliser comme X.",
       f"{fr(n50)} lignes avec remise > 50 % ; {fr(nsc)} lignes vendues sous le coût "
       f"({100 * nsc / max(withcost, 1):.1f} % des lignes ayant un coût).",
       "Le jeu couvre les deux périodes ; les anomalies de la période synthétique sont simulées : à interpréter "
       "en priorité sur la période réelle."])


def ml_cash(registers):
    ops = RA("cash_operations.csv")
    for o in ops:
        o["CaisseName"] = o.get("CaisseName") or registers.get(o["CaisseId"].upper(), "")
    per_user = defaultdict(list)
    for o in ops:
        per_user[o["AddedByUserId"]].append(o)
    z = {}
    for u, ls in per_user.items():
        for o, v in zip(ls, zscores([abs(f(o["Amount"])) for o in ls])):
            z[o["Id"]] = v
    canc_rate = {u: sum(o["IsCancelled"] == "true" for o in ls) / len(ls) for u, ls in per_user.items()}
    day_ops, day_canc = Counter(), Counter()
    for o in ops:
        k = (o["AddedByUserId"], o["AddedAtUtc"][:10])
        day_ops[k] += 1
        day_canc[k] += o["IsCancelled"] == "true"
    rows = []
    for o in ops:
        dd = d_of(o["AddedAtUtc"])
        k = (o["AddedByUserId"], o["AddedAtUtc"][:10])
        delay = ""
        if o["CancelledAtUtc"]:
            delay = int((datetime.fromisoformat(o["CancelledAtUtc"]) - datetime.fromisoformat(o["AddedAtUtc"])).total_seconds() // 60)
        rows.append({"Id": o["Id"], "CaisseId": o["CaisseId"], "CaisseName": o["CaisseName"], "DateKey": datekey(dd),
                     "AddedAtUtc": o["AddedAtUtc"], "X_AddedByUserId": o["AddedByUserId"],
                     "X_HeureUtc": hour_of(o["AddedAtUtc"]), "X_JourSemaine": dd.isoweekday(),
                     "X_Amount": o["Amount"], "X_EstMontantNegatif": str(f(o["Amount"]) < 0).lower(),
                     "X_Amount_ZScoreUtilisateur": r2(z[o["Id"]], 3), "X_Status": o["Status"],
                     "X_TauxAnnulationUtilisateur": r2(100 * canc_rate[o["AddedByUserId"]], 2),
                     "X_NbOperationsJourUtilisateur": day_ops[k],
                     "X_NbAnnulationsJourUtilisateur": day_canc[k] - (o["IsCancelled"] == "true"),
                     "Y_IsCancelled": o["IsCancelled"], "DelaiAnnulationMinutes": delay})
    ncanc = sum(r["Y_IsCancelled"] == "true" for r in rows)
    W("ml/ml_11_3_operations_caisse.csv", list(rows[0].keys()), rows,
      "ML 11.3 – Opérations de caisse : montant, utilisateur, heure, fréquence d'annulation par utilisateur.",
      "1 ligne = 1 opération de caisse", "CaisseOperations (+ noms des caisses issus de DomainEvents) — réel + synthétique",
      "§11.3 Détection d'anomalies de caisse ; Y possible = IsCancelled",
      [f"`Y_IsCancelled` = annulation enregistrée ({fr(ncanc)} cas) : cible d'une classification d'annulation, "
       "sinon détection d'anomalies sur les `X_`.",
       "`X_NbAnnulationsJourUtilisateur` exclut l'opération elle-même (pas de fuite de la cible). "
       "`DelaiAnnulationMinutes` n'est connu qu'après annulation : à ne pas utiliser comme X.",
       "Heures en UTC. Une opération annulée n'est pas automatiquement frauduleuse : validation humaine (§11.3)."])

    ev = RA("cash_register_events.csv")
    disc = [e for e in ev if e["EventType"] == "DISCREPANCY"]
    for e in disc:
        e["CaisseName"] = e.get("CaisseName") or registers.get(e["AggregateId"].upper(), "")
    per_user = Counter(e["UserId"] for e in disc)
    per_caisse = Counter(e["AggregateId"] for e in disc)
    rows = []
    for e in disc:
        dd = d_of(e["UtcTimestamp"])
        rows.append({"Id": e["Id"], "DateKey": datekey(dd), "UtcTimestamp": e["UtcTimestamp"],
                     "AggregateId": e["AggregateId"], "CaisseName": e["CaisseName"], "X_UserId": e["UserId"],
                     "X_HeureUtc": hour_of(e["UtcTimestamp"]), "X_JourSemaine": dd.isoweekday(),
                     "X_DetectedAt": e["DetectedAt"], "X_Data_expectedBalance": e["Data_expectedBalance"],
                     "X_Data_foundBalance": e["Data_foundBalance"], "X_Data_amount": e["Data_amount"],
                     "X_EcartAbsolu": r2(abs(f(e["Data_amount"])), 3),
                     "X_EcartRelatifPct": r2(100 * abs(f(e["Data_amount"])) / f(e["Data_expectedBalance"]), 2)
                     if f(e["Data_expectedBalance"]) else "",
                     "X_NbEcartsUtilisateur": per_user[e["UserId"]], "X_NbEcartsCaisse": per_caisse[e["AggregateId"]],
                     "EstFondDeCaisseRetire": str(e["DetectedAt"] == "OPENING" and f(e["Data_foundBalance"]) == 0).lower()})
    W("ml/ml_11_3_ecarts_caisse.csv", list(rows[0].keys()), rows,
      "ML 11.3 – Écarts de caisse détectés à l'ouverture / la fermeture (attendu vs trouvé).",
      "1 ligne = 1 écart de caisse", "DomainEvents (CaisseDiscrepancyIdentified) — réel + synthétique", "§11.3",
      [f"{fr(len(rows))} écarts.",
       "`EstFondDeCaisseRetire` = écart à l'ouverture avec caisse trouvée à 0 : fond de caisse retiré la veille, pas une "
       "perte — à traiter à part avant de parler de comportement à risque."])


def ml_segmentation(sales, clients):
    agg = defaultdict(lambda: dict(ca=0.0, marge=0.0, cout=0.0, q=0.0, rem=0.0, brut=0.0, docs=set(),
                                   prods=set(), dates=[], months=set(), comptoir=0.0, lines=0))
    total_ca = 0.0
    for s in sales:
        total_ca += f(s["CA_HT"])
        cid = s["Company_Id"]
        c = clients.get(cid)
        if not c or c["EstClientIdentifie"] != "true":
            continue
        a = agg[cid]
        a["ca"] += f(s["CA_HT"])
        a["q"] += f(s["QuantiteVendue"])
        a["rem"] += f(s["Remise_HT"])
        a["brut"] += f(s["CA_HT"]) + f(s["Remise_HT"])
        if s["Cout_HT"] != "":
            a["marge"] += f(s["CA_HT"]) - f(s["Cout_HT"])
            a["cout"] += f(s["Cout_HT"])
        a["docs"].add(s["Document_Id"])
        a["prods"].add(s["Product_Id"])
        d = date.fromisoformat(s["Date"])
        a["dates"].append(d)
        a["months"].add(d.strftime("%Y-%m"))
        a["comptoir"] += f(s["CA_HT"]) if s["Canal"] == "COMPTOIR" else 0
        a["lines"] += 1
    rows = []
    for cid, a in agg.items():
        c = clients[cid]
        first, last = min(a["dates"]), max(a["dates"])
        months_span = max(((END - first).days + 1) / 30.44, 1)
        nd = len(a["docs"])
        rows.append({"Company_Id": cid, "Nom": c["Nom"], "TypeClient": c["TypeClient"],
                     "X_CA_HT_Total": r2(a["ca"], 2), "X_NbDocuments": nd,
                     "X_FrequenceAchatMensuelle": r2(nd / months_span, 3),
                     "X_PanierMoyen_HT": r2(a["ca"] / nd, 2) if nd else "",
                     "X_AncienneteJours": (END - first).days, "X_RecenceJours": (END - last).days,
                     "X_NbMoisActifs": len(a["months"]), "X_QuantiteTotale": r2(a["q"], 2),
                     "X_NbProduitsDistincts": len(a["prods"]), "X_NbLignes": a["lines"],
                     "X_TauxRemisePct": r2(100 * a["rem"] / a["brut"], 2) if a["brut"] > 0 else "0",
                     "X_PartComptoirPct": r2(100 * a["comptoir"] / a["ca"], 2) if a["ca"] else "",
                     "X_TauxMargePct": r2(100 * a["marge"] / a["ca"], 2) if a["ca"] and a["cout"] else "",
                     "X_EstB2B": "1" if c["TypeClient"] == "B2B" else "0" if c["TypeClient"] == "PARTICULIER" else "",
                     "PremierAchat": first.isoformat(), "DernierAchat": last.isoformat()})
    rows.sort(key=lambda r: -f(r["X_CA_HT_Total"]))
    share = 100 * sum(f(r["X_CA_HT_Total"]) for r in rows) / total_ca
    known_type = sum(r["TypeClient"] in ("B2B", "PARTICULIER") for r in rows)
    W("ml/ml_11_4_segmentation_clients.csv", list(rows[0].keys()), rows,
      "ML 11.4 – Segmentation client : CA, fréquence, panier moyen, récence, ancienneté, produits distincts, type.",
      "1 ligne = 1 client identifié ayant au moins une vente (client comptoir anonyme exclu)",
      "fait_ventes, dim_client", "§11.4 Segmentation client (clustering, aucune cible Y)",
      [f"{len(rows)} clients identifiés, {share:.1f} % du CA HT sur les deux périodes.",
       f"Type de client connu (B2B / particulier) pour {known_type} clients : `X_EstB2B` vide = inconnu.",
       "Récence et ancienneté calculées à la fin de la période chargée "
       f"({END:%d/%m/%Y}) ; standardiser les X avant K-Means (passer CA et quantités en log)."])


# --------------------------------------------------------------------------- #
# documentation
# --------------------------------------------------------------------------- #
SPEC_MAP = [
    ("Direction générale", "CA, nombre de ventes, panier moyen, croissance",
     "SUM(CA_HT) ; COUNT(DISTINCT Document_Id) ; CA / ventes ; (CA_N − CA_N-1) / CA_N-1 × 100", "fait_ventes × dim_temps"),
    ("Responsable commercial", "Produits, familles, marques les plus vendus et les plus rentables, panier moyen",
     "SUM(CA_HT) ; SUM(QuantiteVendue) ; Marge HT = SUM(CA_HT) − SUM(Cout_HT)", "fait_ventes × dim_produit × dim_temps"),
    ("Responsable relation client", "Clients actifs, valeur, fréquence, panier",
     "DISTINCTCOUNT(Company_Id) avec EstClientIdentifie = true ; SUM(CA_HT) ; COUNT(DISTINCT Document_Id)",
     "fait_ventes × dim_client × dim_temps ; ml_11_4"),
    ("Responsable approvisionnement / stock", "Stock disponible, ruptures, stock faible, demande à anticiper",
     "SUM(Quantity) ; COUNT où Quantity = 0 ; COUNT où 0 < Quantity ≤ QuantiteAlerte", "fait_stock_actuel × dim_produit ; ml_11_1"),
    ("Responsable financier / caisse",
     "Montant encaissé, montant payé par chaque client, montant payé à chaque fournisseur, nombre de paiements, "
     "répartition par moyen",
     "SUM(Amount) où Fournisseur_Id = -1 ; SUM(Amount) par client ou par fournisseur ; COUNT(Id)",
     "fait_paiements × dim_paiement × dim_client × dim_fournisseur × dim_temps ; ml_11_3"),
    ("Responsable achats", "Achats par fournisseur et par produit, quel produit vient de quel fournisseur",
     "SUM(MontantAchat_HT) ; SUM(QuantiteAchetee) ; COUNT(DISTINCT Document_Id)",
     "fait_achats × dim_fournisseur × dim_produit × dim_temps"),
]


def write_docs():
    dwh = [(k, t) for k, t in TABLES.items() if k.startswith("dwh/")]
    ml = [(k, t) for k, t in TABLES.items() if k.startswith("ml/")]
    period = (f"Données réelles du {START:%d/%m/%Y} au {END_REAL:%d/%m/%Y} (7 mois), prolongées par des données "
              f"synthétiques jusqu'au {END:%d/%m/%Y}. Délimitation par la date : réel jusqu'au {END_REAL:%d/%m/%Y} inclus, "
              "synthétique ensuite (aucune colonne dédiée).")
    L = ["# Dictionnaire du jeu de données – Health Retailers (version B)", "",
         "Construit par `build_dataset.py` (branche `main`) à partir de `cleaned/` (réel) et `cleaned/synthetique/` "
         "(données générées). Les fichiers sources ne sont jamais modifiés.", "", f"**Période :** {period}", "",
         "## Règles", "",
         "- Modèle du §9 du cahier : 5 dimensions (`dim_temps`, `dim_produit`, `dim_client`, `dim_fournisseur`, "
         "`dim_paiement`) et 4 faits (`fait_ventes`, `fait_achats`, `fait_stock_actuel`, `fait_paiements`).",
         "- Une colonne n'est stockée que si le cahier l'exige **et** qu'elle ne peut pas être recalculée. Les mesures "
         "(marge, rupture, stock faible, montant encaissé…) sont calculées dans Power BI.",
         "- CSV UTF-8, séparateur virgule, décimale `.`, dates ISO, booléens `true/false`. `DateKey` = `AAAAMMJJ`.",
         "- Membres `-1` « NON RENSEIGNE » dans `dim_client`, `dim_fournisseur` et `dim_paiement` : toutes les clés "
         "étrangères retrouvent leur dimension.",
         "- Jeux ML : variables explicatives `X_…`, cibles `Y_…`, règles d'interprétation `Regle_…` (ni X ni Y). Ils "
         "sont construits depuis la zone ETL (données nettoyées), pas depuis le Data Warehouse.", "",
         "## Besoins du cahier → tables", "", "| Décideur | Questions | Mesures | Tables |", "|---|---|---|---|"]
    L += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in SPEC_MAP]
    for title, group in (("Tables du Data Warehouse", dwh), ("Jeux de données Machine Learning", ml)):
        L += ["", f"## {title}", ""]
        for rel, t in group:
            L += [f"### `{rel}`", "", t["desc"], "", f"- **Granularité :** {t['grain']}", f"- **Lignes :** {fr(t['n'])}",
                  f"- **Sources :** {t['sources']}", f"- **Cahier :** {t['spec']}",
                  f"- **Colonnes :** {', '.join('`' + c + '`' for c in t['cols'])}"]
            L += [f"- {n}" for n in t["notes"]]
            L.append("")
    L += ["## Contrôles qualité (§7.1)", "", "| Contrôle | Table | Concernés | Total | % | Statut |", "|---|---|---|---|---|---|"]
    L += [f"| {c['Controle']} | {c['Table']} | {fr(c['NbConcernes'])} | {fr(c['NbTotal'])} | {c['Pourcentage']} | {c['Statut']} |"
          for c in CHECKS]
    (OUT / "dwh" / "DICTIONNAIRE_DATASET.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    readme = ["# Data Warehouse – version B (5 dimensions, 4 faits)", "",
              "Tables produites par `build_dataset.py` (branche `main`) à partir de "
              "[`data-cleaned`](../../tree/data-cleaned) et [`data-external`](../../tree/data-external). "
              "Le schéma (diagramme, descriptif, script SQL) est dans la branche [`dwh-schema`](../../tree/dwh-schema).", "",
              f"**Période :** {period}", "", "| Table | Type | Lignes | Colonnes |", "|---|---|---|---|"]
    readme += [f"| `{k.split('/')[1]}` | {'Dimension' if 'dim_' in k else 'Fait'} | {fr(t['n'])} | "
               f"{', '.join(t['cols'])} |" for k, t in dwh]
    readme += ["", "- Mesures Power BI : CA HT, quantité vendue, nombre de ventes, panier moyen, croissance, marge HT, "
               "clients actifs, stock disponible, ruptures, stock faible, montant encaissé, nombre de paiements, "
               "montant payé par client et par fournisseur, achats HT, quantité achetée, nombre de factures fournisseurs.",
               "- [`DICTIONNAIRE_DATASET.md`](DICTIONNAIRE_DATASET.md) : description de chaque table et de chaque jeu ML, "
               "règles appliquées. [`controles_qualite.csv`](controles_qualite.csv) : contrôles du §7.1.",
               "- Chargement PostgreSQL : `schema_dwh.sql` dans la branche `dwh-schema`.", "",
               "Retour à la vue d'ensemble : branche [`main`](../../tree/main).", ""]
    (OUT / "dwh" / "README.md").write_text("\n".join(readme), encoding="utf-8", newline="\n")

    readme = ["# Jeux de données Machine Learning – version B", "",
              "Un fichier par objectif ML du cahier de spécification (§11), produit par `build_dataset.py` (branche `main`) "
              "à partir de la zone ETL (données nettoyées réelles et synthétiques).", "", f"**Période :** {period}", "",
              "| Fichier | Objectif | Lignes |", "|---|---|---|"]
    readme += [f"| `{k.split('/')[1]}` | {t['spec'].split(' (')[0]} | {fr(t['n'])} |" for k, t in ml]
    readme += ["", "Conventions (§15 du cahier : séparer X, Y, granularité et métrique) :",
               "- `X_…` = variables explicatives, `Y_…` = cible ; `Regle_…` = règles métier d'interprétation (ni X ni Y) ;",
               "- les identifiants (`Id`, `Product_Id`, `Company_Id`…) servent à relier les résultats au Data Warehouse ;",
               "- prévision (11.1) : météo et épidémies sont des variables **candidates**, conservées seulement si elles "
               "améliorent le modèle — mesure à faire sur la **période réelle** uniquement (§8).", "",
               "La description détaillée de chaque fichier est dans `DICTIONNAIRE_DATASET.md` de la branche "
               "[`dataset-dwh`](../../tree/dataset-dwh).", "", "Retour à la vue d'ensemble : branche [`main`](../../tree/main).", ""]
    (OUT / "ml" / "README.md").write_text("\n".join(readme), encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- #
def main():
    docs = RA("documents.csv")
    docs_by_id = {d["Id"]: d for d in docs}
    items = RA("document_items.csv")
    linked_invoices = {r["Document1_Id"] for r in R("related_documents.csv")
                       if docs_by_id.get(r["Document1_Id"], {}).get("DocumentType_Id") == "1"}
    txn = {t["Id"]: t["Company_Id"] for t in RA("transactions.csv")}
    lines_by_ps = {}
    for it in items:
        lines_by_ps[it["ProductStock_Id"]] = it["Description"]
    moves = RA("stock_movements.csv")
    cost_by_line = {}
    for m in moves:
        if m["DocumentId"] and m["Extra_cump"] and m["Action"] == "VALIDATION":
            cost_by_line.setdefault((m["DocumentId"], m["ProductStock_Id"]), f(m["Extra_cump"]))

    # contrôles d'intégrité de base (§7.1)
    doc_ids = set(docs_by_id)
    check("Ligne de document sans document", "documentItemm", sum(1 for i in items if i["Document_Id"] not in doc_ids), len(items))
    check("Ligne de document sans produit", "documentItemm", sum(1 for i in items if not i["Product_Id"]), len(items),
          detail="lignes de commentaire / mise en page des factures, exclues des ventes")
    check("Identifiant de document en double", "Documents", len(docs) - len(doc_ids), len(docs))
    check("Quantité ≤ 0 sur une ligne", "documentItemm", sum(1 for i in items if f(i["Quantity"]) <= 0), len(items),
          detail="quantités nulles / négatives")
    check("Prix unitaire HT ≤ 0", "documentItemm", sum(1 for i in items if f(i["PrixHt"]) <= 0), len(items))
    check("Remise > 100 %", "documentItemm", sum(1 for i in items if f(i["DiscountPourcentage"]) > 100), len(items))
    out = [d for d in docs if not (START <= d_of(d["DocumentDate"]) <= END)]
    check(f"Document hors période {START:%d/%m/%Y} – {END:%d/%m/%Y}", "Documents", len(out), len(docs))
    check("Document brouillon (non validé)", "Documents", sum(d["IsValidated"] != "true" for d in docs), len(docs),
          detail="exclus des faits")
    check("Facture client regroupant des BL (double comptage évité)", "Documents", len(linked_invoices),
          sum(d["DocumentType_Id"] == "1" for d in docs), detail="exclues de fait_ventes, les BL sont comptés")

    cal = build_calendar()
    products = build_products(lines_by_ps, moves)
    ctype = {c["Id"]: c["CompanyType"] for c in R("companies.csv")}
    pays = RA("payments.csv")
    sale_cids = {txn.get(d["Transaction_Id"], "") for d in docs if d["Flow"] in ("SALE", "SALE_RETURN")}
    pay_cids = {p["Company_Id"] for p in pays if not payment_side(p, ctype)}
    clients = build_clients((sale_cids | pay_cids) - {""})
    purchase_sids = {txn.get(d["Transaction_Id"], "") for d in docs if d["Flow"] in ("PURCHASE", "PURCHASE_RETURN")}
    pay_sids = {p["Company_Id"] for p in pays if payment_side(p, ctype)}
    suppliers = build_suppliers((purchase_sids | pay_sids) - {""})
    build_payment_modes()
    sales = build_sales(docs_by_id, items, linked_invoices, txn, products, cost_by_line)
    check("Ligne de vente sans coût (marge non calculable)", "fait_ventes",
          sum(s["SourceCout"] == "ABSENT" for s in sales), len(sales))
    purchases = build_purchases(docs_by_id, items, txn, suppliers)
    build_stock(products)
    build_payments(pays, ctype, clients, suppliers)

    # intégrité référentielle des faits (§7.1)
    dates = {datekey(d) for d in cal}
    for fact, rows, key, dim in (("fait_ventes", sales, "Product_Id", set(products)),
                                 ("fait_ventes", sales, "Company_Id", set(clients)),
                                 ("fait_ventes", sales, "DateKey", dates),
                                 ("fait_achats", purchases, "Product_Id", set(products)),
                                 ("fait_achats", purchases, "Fournisseur_Id", suppliers),
                                 ("fait_achats", purchases, "DateKey", dates)):
        check(f"Clé {key} de {fact} absente de la dimension", fact, sum(1 for s in rows if s[key] not in dim), len(rows))
    with (OUT / "dwh" / "fait_paiements.csv").open(encoding="utf-8") as fh:
        paid = list(csv.DictReader(fh))
    for key, dim in (("Company_Id", set(clients)), ("Fournisseur_Id", suppliers), ("PaymentMode_Id", set(PAY_FR)),
                     ("DateKey", dates)):
        check(f"Clé {key} de fait_paiements absente de la dimension", "fait_paiements",
              sum(1 for p in paid if p[key] not in dim), len(paid))

    meteo, senti = load_meteo(), load_sentinelles()
    ml_demand(sales, products, cal, meteo, senti)
    ml_sales_anomalies(sales, products)
    registers = {r["AggregateId"].upper(): f"Caisse {r['Data_name']}" for r in R("registers_and_bank_accounts.csv")
                 if r["AggregateName"].endswith("Caisse") and r["Data_name"]}
    ml_cash(registers)
    ml_segmentation(sales, clients)

    with (OUT / "dwh" / "controles_qualite.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CHECKS[0].keys()))
        w.writeheader()
        w.writerows(CHECKS)
    write_docs()
    print(f"\nJeu de données écrit dans {OUT}")


if __name__ == "__main__":
    main()

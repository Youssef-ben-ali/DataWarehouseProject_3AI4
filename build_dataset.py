#!/usr/bin/env python3
"""
Health Retailers – construction du jeu de données selon le cahier de spécification
(fichiers/cahier-de-spec.pdf).

Entrée  : ./cleaned/   (sortie de clean_data.py)
Sortie  : ./dataset/
            dwh/   dimensions et tables de faits (modèle en étoile, sections 6, 9, 10 du cahier)
            ml/    jeux de données Machine Learning (section 11 du cahier)
            controles_qualite.csv  (section 7.1)
            README.md              (dictionnaire + lien besoin -> table)

Bibliothèque standard uniquement :  python build_dataset.py
"""
import csv
import statistics
from collections import Counter, OrderedDict, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLEAN = HERE / "cleaned"
OUT = HERE / "dataset"
START, END = date(2024, 9, 30), date(2025, 4, 30)   # période réelle des transactions validées

TABLES = OrderedDict()   # chemin relatif -> infos pour le README
CHECKS = []              # contrôles qualité


# --------------------------------------------------------------------------- #
# utilitaires
# --------------------------------------------------------------------------- #
def R(name):
    with (CLEAN / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def W(rel, cols, rows, desc, grain, sources, spec, notes=()):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])
    TABLES[rel] = dict(cols=cols, n=len(rows), desc=desc, grain=grain, sources=sources, spec=spec, notes=list(notes))
    print(f"{rel:55s} {len(rows):>8,} lignes  {len(cols):>3} colonnes")


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


# --------------------------------------------------------------------------- #
# calendrier français (donnée externe autorisée, section 8 du cahier)
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


# Vacances scolaires (calendrier officiel Éducation nationale) : (début, fin incluse)
VAC = {
    "A": [("2024-10-19", "2024-11-03"), ("2024-12-21", "2025-01-05"), ("2025-02-22", "2025-03-09"),
          ("2025-04-19", "2025-05-04"), ("2025-07-05", "2025-08-31"), ("2025-10-18", "2025-11-02"),
          ("2025-12-20", "2025-12-31")],
    "B": [("2024-10-19", "2024-11-03"), ("2024-12-21", "2025-01-05"), ("2025-02-08", "2025-02-23"),
          ("2025-04-05", "2025-04-21"), ("2025-07-05", "2025-08-31"), ("2025-10-18", "2025-11-02"),
          ("2025-12-20", "2025-12-31")],
    "C": [("2024-10-19", "2024-11-03"), ("2024-12-21", "2025-01-05"), ("2025-02-15", "2025-03-02"),
          ("2025-04-12", "2025-04-27"), ("2025-07-05", "2025-08-31"), ("2025-10-18", "2025-11-02"),
          ("2025-12-20", "2025-12-31")],
}
VAC = {z: [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in v] for z, v in VAC.items()}
MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre",
        "Novembre", "Décembre"]
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def season(d):
    md = (d.month, d.day)
    if md >= (12, 21) or md < (3, 20):
        return "Hiver"
    if md < (6, 21):
        return "Printemps"
    if md < (9, 22):
        return "Été"
    return "Automne"


# --------------------------------------------------------------------------- #
# données externes : météo (Open-Meteo) et épidémies (réseau Sentinelles)
# --------------------------------------------------------------------------- #
EXT = HERE / "externe"            # téléchargements bruts conservés (hors de dataset/, jamais effacés)
METEO_VILLE, METEO_LAT, METEO_LON = "Paris", 48.8566, 2.3522
SENTI = {"3": "Grippe", "25": "IRA", "6": "Gastro", "7": "Varicelle"}   # indicateur Sentinelles → nom


def download(url, path):
    import urllib.request
    if not path.exists():
        EXT.mkdir(exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as resp:
            path.write_bytes(resp.read())
        print(f"téléchargé : {path.name}")
    return path


def load_meteo():
    import json
    url = ("https://archive-api.open-meteo.com/v1/archive?"
           f"latitude={METEO_LAT}&longitude={METEO_LON}&start_date=2024-09-01&end_date=2025-12-31"
           "&daily=temperature_2m_mean,temperature_2m_min,temperature_2m_max,precipitation_sum,"
           "sunshine_duration,shortwave_radiation_sum&timezone=Europe%2FParis")
    data = json.loads(download(url, EXT / f"meteo_{METEO_VILLE.lower()}_open-meteo.json").read_text(encoding="utf-8"))["daily"]
    out = {}
    for i, day in enumerate(data["time"]):
        g = lambda k: data[k][i]
        out[date.fromisoformat(day)] = {
            "Meteo_TempMoy": g("temperature_2m_mean"), "Meteo_TempMin": g("temperature_2m_min"),
            "Meteo_TempMax": g("temperature_2m_max"), "Meteo_Pluie_mm": g("precipitation_sum"),
            "Meteo_Ensoleillement_h": None if g("sunshine_duration") is None else g("sunshine_duration") / 3600,
            "Meteo_Rayonnement_MJm2": g("shortwave_radiation_sum")}
    return out


def load_sentinelles():
    out = defaultdict(dict)        # (année ISO, semaine ISO) -> {Senti_<nom>_Inc100: valeur}
    for ind, name in SENTI.items():
        p = download(f"https://www.sentiweb.fr/datasets/all/inc-{ind}-PAY.csv", EXT / f"sentinelles_inc-{ind}-PAY.csv")
        lines = [l for l in p.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
        for r in csv.DictReader(lines):
            wk = r["week"]
            if r["inc100"] not in ("", "-", "NA"):
                out[(int(wk[:4]), int(wk[4:]))][f"Senti_{name}_Inc100"] = float(r["inc100"])
    return out


EXT_COLS = ["Meteo_TempMoy", "Meteo_TempMin", "Meteo_TempMax", "Meteo_Pluie_mm", "Meteo_Ensoleillement_h",
            "Meteo_Rayonnement_MJm2"] + [f"Senti_{n}_Inc100" for n in SENTI.values()]


def build_calendar():
    hol = {}
    for y in (2024, 2025):
        hol.update(holidays(y))
    meteo, senti = load_meteo(), load_sentinelles()
    rows, cal = [], {}
    d = date(2024, 9, 1)
    while d <= date(2025, 12, 31):
        iso = d.isocalendar()
        vac = {z: any(a <= d <= b for a, b in VAC[z]) for z in "ABC"}
        r = dict(DateKey=datekey(d), Date=d.isoformat(), Annee=d.year, Trimestre=(d.month - 1) // 3 + 1,
                 Mois=d.month, NomMois=MOIS[d.month - 1], AnneeMois=f"{d.year}-{d.month:02d}",
                 SemaineISO=iso[1], AnneeSemaine=f"{iso[0]}-S{iso[1]:02d}", DebutSemaine=week_start(d).isoformat(),
                 Jour=d.day, JourSemaine=iso[2], NomJour=JOURS[d.weekday()],
                 EstWeekend="true" if d.weekday() >= 5 else "false",
                 EstFerie="true" if d in hol else "false", NomFerie=hol.get(d, ""),
                 VacancesZoneA=str(vac["A"]).lower(), VacancesZoneB=str(vac["B"]).lower(),
                 VacancesZoneC=str(vac["C"]).lower(), EstVacances=str(any(vac.values())).lower(),
                 Saison=season(d), DansPeriodeDonnees="true" if START <= d <= END else "false")
        ext = {**meteo.get(d, {}), **senti.get((iso[0], iso[1]), {})}
        for c in EXT_COLS:
            r[c] = r2(ext[c], 2) if ext.get(c) is not None else ""
        rows.append(r)
        cal[d] = r
        d += timedelta(1)
    W("dwh/dim_temps.csv", list(rows[0].keys()), rows,
      "Dimension Temps : jour, semaine, mois, trimestre, année, saison, jours fériés et vacances scolaires.",
      "1 ligne = 1 jour (01/09/2024 → 31/12/2025, pour couvrir aussi l'horizon de prévision)",
      "Calculé (calendrier français : jours fériés par calcul de Pâques, vacances scolaires officielles 2024-2025 zones A/B/C) ; "
      f"météo journalière Open-Meteo ({METEO_VILLE}) ; incidences hebdomadaires du réseau Sentinelles (France)",
      "§8 Données externes – Calendrier français, Météo ; §11.1 indicateurs épidémiques ; §9 Dimension Temps",
      ["`DansPeriodeDonnees` = true entre le 30/09/2024 et le 30/04/2025 (période des transactions).",
       "Zone C = Paris / Toulouse, zone B = Marseille / Lille / Nantes / Strasbourg…, zone A = Lyon / Bordeaux / Grenoble.",
       f"Météo (`Meteo_*`, valeur du jour, {METEO_VILLE}, source archive-api.open-meteo.com) : température moyenne / "
       "min / max (°C), pluie (mm), ensoleillement (heures), rayonnement solaire (MJ/m²). Jointure : DateKey.",
       "Épidémies (`Senti_*_Inc100`, taux d'incidence pour 100 000 habitants, France entière, réseau Sentinelles – "
       "Inserm / Sorbonne Université, sentiweb.fr) : Grippe = syndromes grippaux (indicateur 3), IRA = infections "
       "respiratoires aiguës (25), Gastro = diarrhée aiguë (6), Varicelle (7). Valeur HEBDOMADAIRE répétée sur les "
       "7 jours de la semaine ISO : jointure par semaine (AnneeSemaine), ne pas sommer sur les jours.",
       "Fichiers bruts téléchargés conservés dans `externe/`."])
    return cal


# --------------------------------------------------------------------------- #
# DIMENSIONS
# --------------------------------------------------------------------------- #
CITY_REGION = {"PARIS": "Île-de-France", "LYON": "Auvergne-Rhône-Alpes", "GRENOBLE": "Auvergne-Rhône-Alpes",
               "TOULOUSE": "Occitanie", "MONTPELLIER": "Occitanie", "LILLE": "Hauts-de-France",
               "MARSEILLE": "Provence-Alpes-Côte d'Azur", "NICE": "Provence-Alpes-Côte d'Azur",
               "NANTES": "Pays de la Loire", "BORDEAUX": "Nouvelle-Aquitaine", "STRASBOURG": "Grand Est",
               "RENNES": "Bretagne"}
CITY_DEPT = {"PARIS": "75", "LYON": "69", "GRENOBLE": "38", "TOULOUSE": "31", "MONTPELLIER": "34", "LILLE": "59",
             "MARSEILLE": "13", "NICE": "06", "NANTES": "44", "BORDEAUX": "33", "STRASBOURG": "67", "RENNES": "35"}


def build_geo(customers, suppliers):
    cities = sorted({r["Ville"] for r in customers + suppliers if r["Ville"]})
    rows, geo = [], {}
    for i, c in enumerate(cities, 1):
        rows.append(dict(Geo_Id=i, Ville=c, Departement=CITY_DEPT.get(c, ""), Region=CITY_REGION.get(c, "NON RENSEIGNE"),
                         Pays="FRANCE"))
        geo[c] = i
    rows.append(dict(Geo_Id=-1, Ville="NON RENSEIGNE", Departement="", Region="NON RENSEIGNE", Pays=""))
    bad = sum(1 for r in customers + suppliers if r["Ville"] in CITY_DEPT and not r["Code postal"].startswith(CITY_DEPT[r["Ville"]]))
    check("Code postal incohérent avec la ville", "Clients/Fournisseurs", bad, len(customers + suppliers),
          detail="ex. NICE avec codes postaux 60…69 : la géographie est donc prise depuis la ville, pas le code postal")
    W("dwh/dim_geographie.csv", list(rows[0].keys()), rows,
      "Dimension Géographie : ville, département, région (clients et fournisseurs).",
      "1 ligne = 1 ville", "Clients, Fournisseurs (Ville)", "§9 Dimension Géographie",
      [f"Département et région déduits de la ville ; le code postal n'est pas fiable ({bad} codes incohérents).",
       "Les ventes comptoir (client anonyme) n'ont pas de géographie : le magasin est unique."])
    return geo


def build_products(lines_by_ps):
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
    prices = {p["Product_Id"]: p for p in R("product_prices.csv") if p["PriceName_Id"] == "1"}
    barcodes = defaultdict(list)
    for b in R("barcodes.csv"):
        barcodes[b["Product_Id"]].append(b)
    cump = {}
    for m in R("stock_movements.csv"):
        if m["Extra_cump"]:
            cump[m["Product_Id"]] = m["Extra_cump"]            # dernier CUMP connu
    brands = sorted({b["BrandName"] for b in R("brands.csv")}, key=len, reverse=True)

    rows, src_name, src_brand = [], Counter(), Counter()
    for s in stocks:
        pid = s["Product_Id"]
        p = best.get(pid, {})
        name = p.get("Libellé") or labels.get(pid) or lines_by_ps.get(s["Id"], "")
        src_name["Produits" if p else "Events" if pid in labels else "documentItemm" if name else "absent"] += 1
        brand, bsrc = p.get("Marque", ""), "Produits" if p.get("Marque") else ""
        if not brand and name:
            up = name.upper()
            brand = next((b for b in brands if up.startswith(b + " ") or up == b), "")
            bsrc = "deduite_du_libelle" if brand else ""
        src_brand[bsrc or "absent"] += 1
        pr = prices.get(pid, {})
        bc = barcodes.get(pid, [])
        ean = next((b["Code"] for b in bc if b["CodeKind"] == "EAN13" and b["IsValidEan"] == "true"), "") or \
            (bc[0]["Code"] if bc else "")
        alert = p.get("Quantité d'Alerte") or "5"
        rows.append({
            "Product_Id": pid, "ProductStock_Id": s["Id"], "Libellé": name or f"PRODUIT {pid}",
            "Code": p.get("Code", ""), "CodeBarre": ean,
            "Famille": p.get("Famille") or "NON RENSEIGNE", "FamilyGroup": p.get("FamilyGroup") or "NON RENSEIGNE",
            "Marque": brand or "NON RENSEIGNE", "MarqueSource": bsrc or "absent",
            "Prix d'achat HT": p.get("Prix d'achat HT", ""),
            "Prix de vente HT": p.get("Prix de vente HT") or pr.get("PriceHt", ""),
            "Tva": p.get("Tva") or pr.get("VatRatePct", ""),
            "Prix de vente TTC": p.get("Prix de vente TTC") or pr.get("PriceTtc", ""),
            "CoutMoyenPondere": cump.get(pid, ""), "Quantité d'Alerte": alert,
            "AlerteSource": "Produits" if p.get("Quantité d'Alerte") else "parametre_defaut_5",
            "IsDeletedInSoftware": p.get("IsDeletedInSoftware", "false"),
            "ProductIdSource": p.get("ProductIdSource", "non rapproche"),
        })
    unmatched = sum(1 for r in rows if r["ProductIdSource"] == "non rapproche")
    check("Produit du référentiel interne absent de l'export Produits", "dim_produit", unmatched, len(rows), True,
          "famille / prix d'achat indisponibles pour ces produits ; libellé repris des événements ou des lignes de vente")
    W("dwh/dim_produit.csv", list(rows[0].keys()), rows,
      "Dimension Produit : identifiant, libellé, marque, famille (catégorie), prix, code-barres, seuil d'alerte.",
      "1 ligne = 1 produit du référentiel interne (ProductStocks), clé Product_Id",
      "ProductStocks, Produits, Events (libellés), ProductPrices (liste 1), Barcodes, ProductBrands, StockMovements (CUMP)",
      "§9 Dimension Produit ; §6.2 Analyse des ventes",
      [f"Libellé : {dict(src_name)}.", f"Marque : {dict(src_brand)} – quand la marque manque, elle est déduite si le "
       "libellé commence par un nom de ProductBrands (colonne `MarqueSource`).",
       "Famille = catégorie ; `NON RENSEIGNE` quand le produit n'a pas pu être rapproché de l'export Produits.",
       "Seuil d'alerte manquant → paramètre logiciel `ProductsDefaultAlertQuantity = 5` (colonne `AlerteSource`)."])
    return {r["Product_Id"]: r for r in rows}


def build_clients(geo, sale_company_ids):
    companies = {c["Id"]: c for c in R("companies.csv")}
    custs = {c["Code"]: c for c in R("customers.csv")}
    typ = {"INDIVIDUAL": "PARTICULIER", "LABORATORY": "B2B"}
    rows = []
    ids = {i for i, c in companies.items() if c["CompanyType"] == "CUSTOMER"} | (sale_company_ids & set(companies))
    for i in sorted(ids, key=int):
        c = companies[i]
        cu = custs.get(c["Code"], {})
        walk = i == "2"
        rows.append({"Company_Id": i, "Code": c["Code"], "Nom": cu.get("Nom") or c["Name"],
                     "TypeClient": "COMPTOIR_ANONYME" if walk else typ.get(cu.get("CustomerType"), "NON RENSEIGNE"),
                     "Ville": cu.get("Ville", ""), "Geo_Id": geo.get(cu.get("Ville"), -1), "Solde": cu.get("Solde", ""),
                     "EstClientIdentifie": "false" if walk else "true", "CompanyType": c["CompanyType"]})
    unknown = sale_company_ids - set(companies) - {"-1"}
    for i in sorted(unknown, key=int):
        rows.append({"Company_Id": i, "Code": "", "Nom": f"CLIENT INCONNU {i}", "TypeClient": "NON RENSEIGNE",
                     "Ville": "", "Geo_Id": -1, "Solde": "", "EstClientIdentifie": "true", "CompanyType": "INCONNU"})
    rows.append({"Company_Id": "-1", "Code": "", "Nom": "NON RENSEIGNE", "TypeClient": "NON RENSEIGNE", "Ville": "",
                 "Geo_Id": -1, "Solde": "", "EstClientIdentifie": "false", "CompanyType": "INCONNU"})
    check("Company_Id client (ventes / paiements) absent de CompaniesList", "fait_ventes, fait_paiements", len(unknown),
          len(sale_company_ids), detail="ajoutés dans dim_client comme 'CLIENT INCONNU <id>' ; -1 = client non renseigné")
    not_linked = sum(1 for code in custs if code not in {c["Code"] for c in companies.values()})
    check("Client du fichier Clients sans Company_Id (non reliable aux ventes)", "Clients", not_linked, len(custs))
    W("dwh/dim_client.csv", list(rows[0].keys()), rows,
      "Dimension Client : identifiant, nom, type (particulier / B2B / comptoir anonyme), ville, solde (créance).",
      "1 ligne = 1 client (clé Company_Id, celle des transactions)",
      "CompaniesList, Clients, Transactions", "§6.3 Analyse des clients ; §9 Dimension Client",
      ["Company_Id 2 = client comptoir anonyme (la majorité des ventes comptoir).",
       "Le nom vient du fichier Clients quand le code y existe (les noms de CompaniesList ont été anonymisés différemment).",
       f"{not_linked} clients du fichier Clients n'existent pas dans CompaniesList : ils n'ont aucune vente reliable et "
       "ne sont pas dans la dimension."])
    return {r["Company_Id"]: r for r in rows}


def build_suppliers(geo, needed_ids):
    allc = {c["Id"]: c for c in R("companies.csv")}
    companies = [c for c in allc.values() if c["CompanyType"] == "SUPPLIER"]
    sups = {s["Code"]: s for s in R("suppliers.csv")}
    rows = []
    for c in companies:
        s = sups.get(c["Code"], {})
        rows.append({"Company_Id": c["Id"], "Code": c["Code"], "Nom": s.get("Nom") or c["Name"],
                     "Ville": s.get("Ville", ""), "Geo_Id": geo.get(s.get("Ville"), -1), "Solde": s.get("Solde", "")})
    known = {c["Id"] for c in companies}
    unknown = needed_ids - known - {"-1"}
    for i in sorted(unknown, key=int):
        c = allc.get(i)
        rows.append({"Company_Id": i, "Code": c["Code"] if c else "",
                     "Nom": c["Name"] if c else f"FOURNISSEUR INCONNU {i}", "Ville": "", "Geo_Id": -1, "Solde": ""})
    rows.append({"Company_Id": "-1", "Code": "", "Nom": "NON RENSEIGNE", "Ville": "", "Geo_Id": -1, "Solde": ""})
    check("Company_Id fournisseur (achats / paiements) absent des fournisseurs de CompaniesList", "fait_achats, fait_paiements",
          len(unknown), len(needed_ids), detail="ajoutés dans dim_fournisseur (nom CompaniesList ou 'FOURNISSEUR INCONNU <id>')")
    W("dwh/dim_fournisseur.csv", list(rows[0].keys()), rows,
      "Dimension Fournisseur : identifiant, nom, ville, solde (dette).",
      "1 ligne = 1 fournisseur (clé Company_Id)", "CompaniesList, Fournisseurs",
      "§9 Dimension Fournisseur ; §7 Fournisseurs (approvisionnement)",
      [f"{len(sups) - sum(1 for c in companies if c['Code'] in sups)} fournisseurs du fichier Fournisseurs n'ont pas de "
       "Company_Id : aucun achat reliable, non repris."])
    return {r["Company_Id"]: r for r in rows}


PAY_FR = {"1": ("Chèque", "false", "false"), "4": ("Inconnu (4)", "false", "false"),
          "5": ("Carte bancaire", "false", "false"), "7": ("Crédit (paiement différé)", "false", "true"),
          "11": ("Espèces", "true", "false"), "21": ("Jetons", "false", "false"),
          "-1": ("Non renseigné", "false", "false")}


def build_payment_modes():
    rows = [{"PaymentMode_Id": k, "PaymentModeName": v[0], "EstEspeces": v[1], "EstDiffere": v[2]}
            for k, v in PAY_FR.items()]
    W("dwh/dim_paiement.csv", list(rows[0].keys()), rows, "Dimension Paiement : moyen / type de paiement.",
      "1 ligne = 1 moyen de paiement", "PaymentsList (PaymentMode_Id / PaymentMethodName)",
      "§6.5 Paiements ; §9 Dimension Paiement",
      ["-1 = document sans moyen de paiement renseigné (ex. bons de livraison, factures non réglées)."])


CANAL = {"6": "COMPTOIR", "1": "FACTURE", "5": "FACTURE", "4": "FACTURE", "7": "FACTURE", "2": "DEVIS",
         "3": "COMMANDE", "20": "ACHAT", "23": "ACHAT", "21": "ACHAT", "22": "ACHAT", "24": "ACHAT"}
TYPE_FR = {"1": "Facture client", "2": "Devis (proforma)", "3": "Commande client", "4": "Avoir client",
           "5": "Bon de livraison", "6": "Vente comptoir", "7": "Bon de retour", "8": "Facture de route",
           "20": "Facture fournisseur", "21": "Commande fournisseur", "22": "Bon de réception",
           "23": "Avoir fournisseur", "24": "Retour fournisseur", "40": "Bon de sortie", "41": "Bon d'entrée"}


def build_documents(docs, linked_invoices, cal):
    rows = []
    for d in docs:
        dd = d_of(d["DocumentDate"])
        rows.append({"Document_Id": d["Id"], "DocumentNumber": d["DocumentNumber"], "DateKey": datekey(dd),
                     "DocumentType_Id": d["DocumentType_Id"], "TypeDocument": TYPE_FR.get(d["DocumentType_Id"], ""),
                     "Flow": d["Flow"], "Canal": CANAL.get(d["DocumentType_Id"], "AUTRE"), "State": d["State"],
                     "IsValidated": d["IsValidated"],
                     "EstFactureDeBL": "true" if d["Id"] in linked_invoices else "false",
                     "PaymentMode_Id": d["PaymentMode_Id"] or "-1", "CreatedBy": d["CreatedBy"],
                     "Heure": hour_of(d["CreatedDate"]), "TotalNetHt": d["TotalNetHt"], "TotalTtc": d["TotalTtc"]})
    rows.append({"Document_Id": "-1", "DocumentNumber": "", "DateKey": "", "DocumentType_Id": "",
                 "TypeDocument": "Aucun document (stock initial, ajustement, document supprimé)", "Flow": "",
                 "Canal": "AUTRE", "State": "", "IsValidated": "", "EstFactureDeBL": "false", "PaymentMode_Id": "-1",
                 "CreatedBy": "", "Heure": "", "TotalNetHt": "", "TotalTtc": ""})
    W("dwh/dim_document.csv", list(rows[0].keys()), rows,
      "Dimension Document : numéro, type, statut (validé / brouillon), canal (comptoir / facturé / achat).",
      "1 ligne = 1 document", "Documents, DocumentTypes, RelatedDocuments", "§9 Dimension Document (type / statut)",
      ["`EstFactureDeBL` = facture client qui regroupe des bons de livraison déjà comptés (exclue des ventes).",
       "`Heure` = heure de création du document (DocumentDate n'a pas d'heure)."])


def build_users():
    rows = [{"User_Id": u["Id"], "FullName": u["FullName"], "IsStaff": u["IsStaff"]} for u in R("users.csv")]
    W("dwh/dim_utilisateur.csv", list(rows[0].keys()), rows, "Dimension Utilisateur (vendeur / caissier).",
      "1 ligne = 1 utilisateur", "users_csv (sans mots de passe)",
      "§11.2 et §11.3 (variable explicative « utilisateur »)",
      ["Les données d'authentification sont exclues (§4.2 du cahier)."])


# --------------------------------------------------------------------------- #
# FAITS
# --------------------------------------------------------------------------- #
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
        q, ht, ttc, tva = f(it["Quantity"]), f(it["PrixTotalHt"]), f(it["PrixTotalTtc"]), f(it["TotalTva"])
        p = products.get(it["Product_Id"], {})
        cu, src = cost_by_line.get((it["Document_Id"], it["ProductStock_Id"])), "CUMP_MOUVEMENT"
        if cu is None and f(p.get("Prix d'achat HT"), 0) > 0:
            cu, src = f(p["Prix d'achat HT"]), "PRIX_ACHAT_PRODUIT"
        if cu is None:
            src = "ABSENT"
        cost = q * cu if cu is not None else None
        rows.append({
            "Id": it["Id"], "Document_Id": d["Id"], "DocumentNumber": d["DocumentNumber"], "DateKey": datekey(dd),
            "Date": dd.isoformat(), "Heure": hour_of(d["CreatedDate"]), "Product_Id": it["Product_Id"],
            "Company_Id": txn.get(d["Transaction_Id"]) or "-1", "PaymentMode_Id": d["PaymentMode_Id"] or "-1",
            "DocumentType_Id": d["DocumentType_Id"], "Canal": CANAL.get(d["DocumentType_Id"], ""),
            "CreatedBy": d["CreatedBy"], "Signe": sign,
            "Quantity": it["Quantity"], "PrixHt": it["PrixHt"], "DiscountPourcentage": it["DiscountPourcentage"] or "0",
            "Tva": it["Tva"], "PrixTotalHt": it["PrixTotalHt"], "TotalTva": it["TotalTva"],
            "PrixTotalTtc": it["PrixTotalTtc"],
            "QuantiteVendue": r2(sign * q, 4), "Remise_HT": r2(sign * f(it["SumDiscountTotal"]), 4),
            "CA_HT": r2(sign * ht, 4), "TVA_Montant": r2(sign * tva, 4), "CA_TTC": r2(sign * ttc, 4),
            "CoutUnitaire": r2(cu, 4) if cu is not None else "", "SourceCout": src,
            "Cout_HT": r2(sign * cost, 4) if cost is not None else "",
            "Marge_HT": r2(sign * (ht - cost), 4) if cost is not None else "",
            "VenteSousCout": ("true" if cost is not None and q > 0 and ht < cost - 0.005 else "false"),
        })
    srcs = Counter(r["SourceCout"] for r in rows)
    W("dwh/fait_ventes.csv", list(rows[0].keys()), rows,
      "Fait Ventes : ligne de produit vendue (ou retournée) dans un document validé à une date donnée.",
      "1 ligne = 1 produit × 1 document de vente × 1 date (granularité candidate du §9.1, confirmée)",
      "documentItemm, Documents, Transactions, StockMovements (CUMP), Produits",
      "§6.1, §6.2, §6.3 ; §9 Mesures ventes (quantité, CA, nb documents, panier moyen)",
      ["Ventes = vente comptoir (6), bon de livraison (5), facture client (1) ; retours = avoir (4) et bon de retour (7) "
       "avec `Signe = -1` : les mesures `QuantiteVendue`, `CA_HT`, `CA_TTC`, `Remise_HT`, `Cout_HT`, `Marge_HT` sont signées.",
       "Les colonnes d'origine (`Quantity`, `PrixHt`, `PrixTotalHt`…) sont recopiées telles quelles (non signées).",
       "CA du cahier = Σ(Quantité × Prix) = Σ `CA_HT` (net de remise). Nb documents = COUNT(DISTINCT Document_Id). "
       "Panier moyen = Σ CA_HT / Nb documents.",
       "Exclusions : " + "; ".join(f"{k} : {v:,} lignes" for k, v in excluded.items()) + ".",
       f"Coût unitaire : {dict(srcs)} – CUMP = coût moyen pondéré au moment de la vente (StockMovements.Extra_cump), "
       "sinon prix d'achat HT du produit."])
    return rows


def build_purchases(docs_by_id, items, txn):
    rows = []
    for it in items:
        d = docs_by_id.get(it["Document_Id"])
        if not d or d["Flow"] not in ("PURCHASE", "PURCHASE_RETURN") or d["IsValidated"] != "true":
            continue
        if not it["Product_Id"] and f(it["PrixTotalHt"]) == 0:
            continue
        sign = -1 if d["Flow"] == "PURCHASE_RETURN" else 1
        dd = d_of(d["DocumentDate"])
        rows.append({"Id": it["Id"], "Document_Id": d["Id"], "DocumentNumber": d["DocumentNumber"],
                     "DateKey": datekey(dd), "Date": dd.isoformat(), "Product_Id": it["Product_Id"],
                     "Company_Id": txn.get(d["Transaction_Id"]) or "-1", "DocumentType_Id": d["DocumentType_Id"],
                     "Signe": sign, "Quantity": it["Quantity"], "PrixHt": it["PrixHt"],
                     "DiscountPourcentage": it["DiscountPourcentage"] or "0", "PrixTotalHt": it["PrixTotalHt"],
                     "QuantiteAchetee": r2(sign * f(it["Quantity"]), 4), "MontantAchat_HT": r2(sign * f(it["PrixTotalHt"]), 4),
                     "MontantAchat_TTC": r2(sign * f(it["PrixTotalTtc"]), 4),
                     "EstUniteGratuite": "true" if f(it["DiscountPourcentage"]) >= 100 else "false"})
    W("dwh/fait_achats.csv", list(rows[0].keys()), rows,
      "Fait Achats : ligne de produit achetée sur une facture fournisseur validée (avoirs fournisseur en négatif).",
      "1 ligne = 1 produit × 1 document d'achat", "documentItemm, Documents, Transactions",
      "§7 Fournisseurs – approvisionnement ; §9 Dimension Fournisseur",
      ["Permet de relier les fournisseurs aux produits et au stock (approvisionnement).",
       "`EstUniteGratuite` = ligne avec remise 100 % : unités offertes par le fournisseur (≈ 700 lignes). C'est là que se "
       "trouvent presque toutes les « remises > 50 % » citées au §11.2 du cahier.",
       "Lignes de commentaire (sans produit ni montant) exclues."])


def build_stock(products, sales, cal, doc_ids):
    moves = R("stock_movements.csv")
    rows = []
    for m in moves:
        dd = d_of(m["MovementDate"])
        rows.append({"Id": m["Id"], "DateKey": datekey(dd), "Date": dd.isoformat() if dd else "",
                     "Heure": hour_of(m["MovementDate"]), "Product_Id": m["Product_Id"],
                     "ProductStock_Id": m["ProductStock_Id"], "DocumentId": m["DocumentId"],
                     "Document_Id": m["DocumentId"] if m["DocumentId"] in doc_ids else "-1", "Action": m["Action"],
                     "SourceKind": m["SourceKind"], "Direction": m["Direction"], "Quantity": m["Quantity"],
                     "CurrentBalance": m["CurrentBalance"], "Extra_cump": m["Extra_cump"],
                     "ValeurMouvement_HT": r2(f(m["Quantity"]) * f(m["Extra_cump"]), 4) if m["Extra_cump"] else "",
                     "User_Id": m["User_Id"]})
    W("dwh/fait_stock_mouvements.csv", list(rows[0].keys()), rows,
      "Fait Mouvements de stock : chaque entrée / sortie de stock avec le solde après mouvement.",
      "1 ligne = 1 mouvement de stock d'un produit", "StockMovements",
      "§6.4 Gestion des stocks ; §9 Mesures stock (mouvements)",
      ["`DocumentId` = valeur d'origine ; `Document_Id` = clé étrangère vers dim_document (-1 = stock initial, "
       "ajustement manuel ou document absent de Documents).",
       "`SourceKind` = origine (COUNTER_SALE, DELIVERY_NOTE, SUPPLIER_INVOICE, INITIAL_STOCK, MANUAL_ADJUSTMENT…).",
       "`CurrentBalance` = stock du produit après le mouvement → permet de reconstituer l'historique (fait_stock_hebdo)."])

    # --- historique hebdomadaire reconstitué ---
    by_prod = defaultdict(list)
    for m in moves:
        if m["MovementDate"]:
            by_prod[m["Product_Id"]].append((m["MovementDate"], int(m["Id"]), f(m["Quantity"]), f(m["CurrentBalance"])))
    sold_w = defaultdict(float)
    ca_w = defaultdict(float)
    last_sale = {}
    sold_total = defaultdict(float)
    ca_total = defaultdict(float)
    for s in sales:
        dd = date.fromisoformat(s["Date"])
        k = (s["Product_Id"], week_start(dd))
        sold_w[k] += f(s["QuantiteVendue"])
        ca_w[k] += f(s["CA_HT"])
        sold_total[s["Product_Id"]] += f(s["QuantiteVendue"])
        ca_total[s["Product_Id"]] += f(s["CA_HT"])
        if f(s["QuantiteVendue"]) > 0:
            last_sale[s["Product_Id"]] = max(last_sale.get(s["Product_Id"], dd), dd)
    weeks = []
    w = week_start(START)
    while w <= END:
        weeks.append(w)
        w += timedelta(7)
    hist, avg_stock = [], {}
    for pid, ms in by_prod.items():
        ms.sort()
        i, bal, levels = 0, None, []
        for w in weeks:
            wend = w + timedelta(6)
            qin = qout = 0.0
            while i < len(ms) and date.fromisoformat(ms[i][0][:10]) <= wend:
                q = ms[i][2]
                if date.fromisoformat(ms[i][0][:10]) >= w:
                    qin += max(q, 0)
                    qout += max(-q, 0)
                bal = ms[i][3]
                i += 1
            if bal is None:
                continue
            levels.append(bal)
            hist.append({"Product_Id": pid, "SemaineDebut": w.isoformat(), "DateKey": datekey(w),
                         "AnneeSemaine": cal[w]["AnneeSemaine"], "StockFinSemaine": r2(bal, 3),
                         "QteEntree": r2(qin, 3), "QteSortie": r2(qout, 3),
                         "QteVendue": r2(sold_w.get((pid, w), 0), 3), "CA_HT": r2(ca_w.get((pid, w), 0), 2),
                         "EnRupture": "true" if bal <= 0 else "false",
                         "SemaineComplete": "true" if w + timedelta(6) <= END else "false"})
        avg_stock[pid] = statistics.mean(levels) if levels else None
    W("dwh/fait_stock_hebdo.csv", list(hist[0].keys()), hist,
      "Fait Stock hebdomadaire : stock de fin de semaine, entrées, sorties, quantités vendues, rupture.",
      "1 ligne = 1 produit × 1 semaine (lundi), à partir de son premier mouvement",
      "StockMovements (CurrentBalance), fait_ventes",
      "§6.4 (rupture, faible rotation, demande) ; §9.1 granularité stock « par produit et par date »",
      ["L'historique par produit et par date existe (solde après chaque mouvement) : la granularité hebdomadaire a été "
       "retenue (≈ 31 semaines).", "La dernière semaine (28/04 → 30/04/2025) est incomplète : `SemaineComplete = false`."])

    # --- photo actuelle + rotation ---
    ndays = (END - START).days + 1
    ranked = sorted(ca_total.items(), key=lambda x: -x[1])
    tot = sum(v for _, v in ranked if v > 0)
    abc, cum = {}, 0.0
    for pid, v in ranked:
        if v <= 0:
            abc[pid] = "C"
            continue
        cum += v
        abc[pid] = "A" if cum <= 0.8 * tot else "B" if cum <= 0.95 * tot else "C"
    stocks = {s["Product_Id"]: s for s in R("product_stocks.csv")}
    snap = []
    for pid, p in products.items():
        st = f(stocks.get(pid, {}).get("Quantity"))
        alert = f(p["Quantité d'Alerte"], 5)
        sold = sold_total.get(pid, 0.0)
        avg = avg_stock.get(pid)
        daily = sold / ndays
        ls = last_sale.get(pid)
        snap.append({
            "Product_Id": pid, "DateKey": datekey(END), "Quantity": r2(st, 3), "Quantité d'Alerte": r2(alert, 3),
            "EnRupture": "true" if st == 0 else "false", "StockNegatif": "true" if st < 0 else "false",
            "StockFaible": "true" if 0 < st <= alert else "false",
            "QteVendue_Periode": r2(sold, 3), "CA_HT_Periode": r2(ca_total.get(pid, 0.0), 2),
            "StockMoyenHebdo": r2(avg, 3) if avg is not None else "",
            "Rotation": r2(sold / avg, 3) if avg and avg > 0 else "",
            "CouvertureJours": r2(st / daily, 1) if daily > 0 and st > 0 else "",
            "DateDerniereVente": ls.isoformat() if ls else "",
            "JoursDepuisDerniereVente": (END - ls).days if ls else "",
            "ValeurStock_HT": r2(max(st, 0) * f(p["CoutMoyenPondere"]), 2) if p["CoutMoyenPondere"] else "",
            "ClasseABC": abc.get(pid, "C"),
            "EstProduitActif": "true" if pid in last_sale else "false",
        })
    W("dwh/fait_stock_actuel.csv", list(snap[0].keys()), snap,
      "Fait Stock actuel : stock disponible, rupture, stock faible, rotation, couverture, classe ABC à la date de fin.",
      "1 ligne = 1 produit (photo au 30/04/2025)", "ProductStocks, fait_ventes, fait_stock_hebdo, Produits",
      "§6.4 (stock faible, rupture, faible rotation) ; §12 Taux de rupture",
      ["Taux de rupture (§12) = COUNT(EnRupture) / COUNT(produits suivis) × 100. `EstProduitActif` = vendu au moins "
       "une fois sur la période : à utiliser comme « produit suivi », sinon les produits jamais vendus (souvent à stock 0) "
       "gonflent le taux.",
       "Rotation = quantité vendue sur la période / stock moyen hebdomadaire (formule « à définir » du cahier : "
       "proposition à valider). Aucun seuil de faible rotation n'est imposé : utiliser `Rotation` et "
       "`JoursDepuisDerniereVente`.",
       "`StockFaible` utilise le seuil d'alerte du logiciel (Quantité d'Alerte), pas un seuil inventé.",
       "Classe ABC = Pareto sur le CA (A = 80 % du CA, B = 15 %, C = 5 %).",
       "Inventaire : InventaireItems ne contient aucune quantité comptée (FinalRealQuantity vide) → pas de mesure "
       "d'écart d'inventaire possible."])
    return weeks


def payment_side(p, ctype):
    """Le paiement concerne-t-il un fournisseur ? (type de société, sinon libellé du paiement)."""
    t = ctype.get(p["Company_Id"])
    return t == "SUPPLIER" if t in ("SUPPLIER", "CUSTOMER") else p["IsPurchase"] == "true"


def build_payments(docnum_to_id, ctype):
    treso = {t["SalePaymentId"]: t for t in R("treasury_payments.csv")}
    rows = []
    for p in R("payments.csv"):
        dd = d_of(p["PaymentDate"])
        t = treso.get(p["Id"], {})
        sup = payment_side(p, ctype)
        rows.append({"Id": p["Id"], "DateKey": datekey(dd), "Date": dd.isoformat() if dd else "",
                     "Heure": hour_of(p["PaymentDate"]), "Company_Id": p["Company_Id"],
                     "Client_Id": "" if sup else (p["Company_Id"] or "-1"),
                     "Fournisseur_Id": (p["Company_Id"] or "-1") if sup else "",
                     "PaymentMode_Id": p["PaymentMode_Id"] or "-1", "Amount": p["Amount"], "UsedAmount": p["UsedAmount"],
                     "IsPurchase": p["IsPurchase"], "EstPaiementFournisseur": str(sup).lower(),
                     "DocumentNumber": p["DocumentNumber"],
                     "Document_Id": docnum_to_id.get(p["DocumentNumber"], "-1"), "CaisseId": t.get("CaisseId", ""),
                     "CaisseName": t.get("CaisseName", ""), "BankAccountId": t.get("BankAccountId", ""),
                     "Extra_gA": p["Extra_gA"], "Extra_rA": p["Extra_rA"]})
    nodoc = sum(1 for r in rows if r["Document_Id"] == "-1")
    check("Paiement sans document retrouvé", "fait_paiements", nodoc, len(rows))
    W("dwh/fait_paiements.csv", list(rows[0].keys()), rows,
      "Fait Paiements : montant encaissé (ou payé aux fournisseurs), moyen, date, caisse.",
      "1 ligne = 1 paiement", "PaymentsList + Payment (fusionnés), TresoreriePayments",
      "§6.5 Paiements ; §9 Mesures paiements (montant payé, nb transactions)",
      ["Montant encaissé = Σ Amount où EstPaiementFournisseur = false ; répartition par PaymentMode_Id ; évolution par DateKey.",
       "`Company_Id` (origine) désigne un client OU un fournisseur : il est réparti en deux clés étrangères, `Client_Id` "
       "(→ dim_client) et `Fournisseur_Id` (→ dim_fournisseur), selon le type de la société dans CompaniesList "
       "(à défaut, selon `IsPurchase`). Une seule des deux est remplie.",
       "`Document_Id` retrouvé grâce au numéro de pièce cité dans la description du paiement ; -1 si introuvable."])


# --------------------------------------------------------------------------- #
# MACHINE LEARNING
# --------------------------------------------------------------------------- #
def ml_demand(sales, products, cal, weeks):
    def week_feats(w):
        days = [w + timedelta(i) for i in range(7)]
        return dict(NbJoursFeries=sum(cal[d]["EstFerie"] == "true" for d in days),
                    NbJoursVacancesZoneC=sum(cal[d]["VacancesZoneC"] == "true" for d in days),
                    NbJoursVacancesToutesZones=sum(cal[d]["EstVacances"] == "true" for d in days),
                    NbJoursOuvres=sum(d.weekday() < 6 and cal[d]["EstFerie"] == "false" for d in days),
                    Mois=w.month, SemaineISO=cal[w]["SemaineISO"], Saison=cal[w]["Saison"],
                    **meteo_week(days),
                    **{c.replace("Senti_", ""): cal[w][c] for c in EXT_COLS if c.startswith("Senti_")},
                    SemaineComplete="true" if w + timedelta(6) <= END else "false")

    def meteo_week(days):
        v = lambda c: [f(cal[d][c]) for d in days if cal[d][c] != ""]
        tm, tn, tx, pl, so, ra = (v(c) for c in ("Meteo_TempMoy", "Meteo_TempMin", "Meteo_TempMax", "Meteo_Pluie_mm",
                                                  "Meteo_Ensoleillement_h", "Meteo_Rayonnement_MJm2"))
        return dict(Meteo_TempMoyenne=r2(statistics.mean(tm), 2) if tm else "",
                    Meteo_TempMin=r2(min(tn), 2) if tn else "", Meteo_TempMax=r2(max(tx), 2) if tx else "",
                    Meteo_Pluie_mm=r2(sum(pl), 2) if pl else "", Meteo_NbJoursPluie=sum(x >= 1 for x in pl),
                    Meteo_Ensoleillement_h=r2(sum(so), 2) if so else "",
                    Meteo_Rayonnement_MJm2=r2(sum(ra), 2) if ra else "")

    brand_qty = Counter()
    for s in sales:
        brand_qty[products.get(s["Product_Id"], {}).get("Marque", "NON RENSEIGNE")] += f(s["QuantiteVendue"])
    top = {b for b, _ in brand_qty.most_common(26) if b != "NON RENSEIGNE"}

    for level, keyf, fname in (
            ("FamilyGroup", lambda p: p.get("FamilyGroup", "NON RENSEIGNE"), "ml/ml_11_1_prevision_demande_famille_hebdo.csv"),
            ("Marque", lambda p: p.get("Marque") if p.get("Marque") in top else "AUTRES MARQUES",
             "ml/ml_11_1_prevision_demande_marque_hebdo.csv")):
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
            hist = []
            for i, w in enumerate(weeks):
                a = agg.get((g, w), dict(q=0.0, ca=0.0, brut=0.0, rem=0.0, qc=0.0, docs=set()))
                lag = lambda k: r2(hist[-k], 3) if len(hist) >= k else ""
                r = {level: g, "SemaineDebut": w.isoformat(), "AnneeSemaine": cal[w]["AnneeSemaine"],
                     "Y_Quantite": r2(a["q"], 3),
                     "Y_QuantiteSemaineSuivante": "",
                     "X_Qte_Lag1": lag(1), "X_Qte_Lag2": lag(2), "X_Qte_Lag4": lag(4),
                     "X_Qte_MoyenneMobile4": r2(statistics.mean(hist[-4:]), 3) if len(hist) >= 4 else "",
                     "X_CA_HT": r2(a["ca"], 2), "X_PrixMoyen_HT": r2(a["ca"] / a["q"], 3) if a["q"] > 0 else "",
                     "X_TauxRemisePct": r2(100 * a["rem"] / a["brut"], 2) if a["brut"] > 0 else "0",
                     "X_PartComptoirPct": r2(100 * a["qc"] / a["q"], 2) if a["q"] > 0 else "",
                     "X_NbDocuments": len(a["docs"])}
                r.update({"X_" + k: v for k, v in week_feats(w).items() if k != "SemaineComplete"})
                r["SemaineComplete"] = week_feats(w)["SemaineComplete"]
                rows.append(r)
                hist.append(a["q"])
            for i in range(len(weeks) - 1):          # cible t+1 pour une prévision à 1 semaine
                rows[-len(weeks) + i]["Y_QuantiteSemaineSuivante"] = rows[-len(weeks) + i + 1]["Y_Quantite"]
        W(fname, list(rows[0].keys()), rows,
          f"ML 11.1 – Prévision de la demande : quantité vendue par {'famille' if level == 'FamilyGroup' else 'marque'} et par semaine.",
          f"1 ligne = 1 {level} × 1 semaine (toutes les semaines, 0 si aucune vente)",
          "fait_ventes, dim_produit, dim_temps", "§11.1 Prévision de la demande (régression / séries temporelles)",
          ["Cible Y : `Y_Quantite` (semaine courante) ou `Y_QuantiteSemaineSuivante` (prévision t+1). Les variables "
           "explicatives sont préfixées `X_` (§13 : séparer clairement X et Y).",
           "X : historique (lags 1/2/4, moyenne mobile 4 semaines, toujours calculés sur le passé), prix moyen, remise, "
           "canal comptoir / facturé, jours fériés, vacances scolaires, jours ouvrés, mois, saison.",
           f"Externes intégrés : météo de la semaine ({METEO_VILLE}, Open-Meteo) – `X_Meteo_TempMoyenne`, `X_Meteo_TempMin`, "
           "`X_Meteo_TempMax`, `X_Meteo_Pluie_mm` (cumul), `X_Meteo_NbJoursPluie` (≥ 1 mm), `X_Meteo_Ensoleillement_h` "
           "(cumul), `X_Meteo_Rayonnement_MJm2` (cumul) ; épidémies de la semaine (réseau Sentinelles, France, pour 100 000 "
           "hab.) – `X_Grippe_Inc100`, `X_IRA_Inc100`, `X_Gastro_Inc100`, `X_Varicelle_Inc100`. Jointure par semaine ISO.",
           "Pour prévoir `Y_QuantiteSemaineSuivante`, les X de la semaine courante sont connus au moment de la prévision "
           "(Sentinelles publie avec ~1 semaine de délai : en production, décaler les épidémies d'une semaine).",
           "Externes non intégrés : Google Trends, taux EUR/TND.",
           "Ne pas utiliser la dernière semaine (`SemaineComplete = false`) pour l'entraînement ; ~30 semaines "
           "d'historique : valider sur les dernières semaines (baseline = X_Qte_Lag1, métriques MAE / RMSE du §12)."]
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
        r1, r2_, r3 = disc > 50, s["VenteSousCout"] == "true", abs(zq.get(s["Id"], 0)) > 3
        rows.append({
            "Id": s["Id"], "Document_Id": s["Document_Id"], "DateKey": s["DateKey"], "Product_Id": s["Product_Id"],
            "FamilyGroup": products.get(s["Product_Id"], {}).get("FamilyGroup", ""),
            "X_CreatedBy": s["CreatedBy"], "X_Heure": s["Heure"], "X_JourSemaine": d.isoweekday(), "X_Canal": s["Canal"],
            "X_Quantity": s["Quantity"], "X_Quantity_ZScoreProduit": r2(zq.get(s["Id"], 0), 3),
            "X_PrixHt": s["PrixHt"], "X_PrixHt_Reference": r2(rp, 3),
            "X_EcartPrixReferencePct": r2(100 * (f(s["PrixHt"]) - rp) / rp, 2) if rp else "",
            "X_DiscountPourcentage": s["DiscountPourcentage"], "X_PrixTotalHt": s["PrixTotalHt"],
            "X_CoutMoyenPondere_HT": r2(cost, 4) if cost is not None else "", "X_SourceCout": s["SourceCout"],
            "X_EcartPrixTotalHtCoutPct": r2(100 * (f(s["PrixTotalHt"]) - cost) / cost, 2) if cost else "",
            "X_NbLignesDocument": lines_per_doc[s["Document_Id"]],
            "X_RemiseMoyenneUtilisateur": r2(user_avg[s["CreatedBy"]], 2),
            "Regle_RemiseSup50": str(r1).lower(), "Regle_VenteSousCout": str(r2_).lower(),
            "Regle_QuantiteAtypique": str(r3).lower(), "ScoreRegles": int(r1) + int(r2_) + int(r3),
        })
    n50 = sum(r["Regle_RemiseSup50"] == "true" for r in rows)
    nsc = sum(r["Regle_VenteSousCout"] == "true" for r in rows)
    withcost = sum(r["X_CoutMoyenPondere_HT"] != "" for r in rows)
    W("ml/ml_11_2_anomalies_ventes.csv", list(rows[0].keys()), rows,
      "ML 11.2 – Détection d'anomalies sur les lignes de vente (remise, prix vs coût moyen pondéré, quantité, utilisateur, heure).",
      "1 ligne = 1 ligne de vente (retours exclus)", "fait_ventes, dim_produit",
      "§11.2 Détection d'anomalies (non supervisé)",
      ["Pas de cible Y étiquetée dans les données : apprentissage non supervisé (Isolation Forest, LOF…) sur les colonnes `X_`.",
       "Les colonnes `Regle_*` sont des règles métier simples, utiles pour interpréter / évaluer les anomalies, "
       "pas une vérité terrain. Ne pas les utiliser comme X.",
       f"Vérification des chiffres du cahier : {n50:,} lignes de VENTE avec remise > 50 %. Le chiffre de 789 du cahier "
       "se retrouve exactement en comptant toutes les lignes de documents, mais 703 d'entre elles sont des unités gratuites "
       "sur factures fournisseurs (remise 100 %, voir fait_achats.EstUniteGratuite) et 37 sont sur des factures qui "
       "refacturent des BL : ce ne sont pas des ventes anormales.",
       f"{nsc:,} lignes vendues sous le coût moyen pondéré = {100 * nsc / max(withcost, 1):.1f} % des lignes ayant un coût. "
       "Le chiffre de 22 % du cahier n'a pas pu être reproduit (prix HT médian = 1,45 × CUMP ; même le prix unitaire avant "
       "remise n'est sous le coût que pour 0,6 % des lignes) : à revoir dans le cahier."])


def ml_cash():
    ops = R("cash_operations.csv")
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
    W("ml/ml_11_3_operations_caisse.csv", list(rows[0].keys()), rows,
      "ML 11.3 – Opérations de caisse : montant, utilisateur, heure, fréquence d'annulation par utilisateur.",
      "1 ligne = 1 opération de caisse", "CaisseOperations (+ noms des caisses issus de DomainEvents)",
      "§11.3 Détection des écarts de caisse et annulations anormales",
      [f"`Y_IsCancelled` = annulation enregistrée ({sum(r['Y_IsCancelled'] == 'true' for r in rows)} cas, cahier : 102) : "
       "cible possible pour un modèle supervisé, sinon détection d'anomalies sur les `X_`.",
       "`X_NbAnnulationsJourUtilisateur` exclut l'opération elle-même (pas de fuite de la cible).",
       "`DelaiAnnulationMinutes` n'est connu qu'après annulation : à ne pas utiliser comme X.",
       "Heures en UTC (horodatage d'origine)."])

    ev = R("cash_register_events.csv")
    disc = [e for e in ev if e["EventType"] == "DISCREPANCY"]
    approved = {e["Id"] for e in ev if e["EventType"] == "DISCREPANCY_APPROVED"}
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
      "1 ligne = 1 écart de caisse", "DomainEvents (CaisseDiscrepancyIdentified)", "§11.3",
      [f"{len(rows)} écarts (cahier : 437).",
       "`EstFondDeCaisseRetire` = écart à l'ouverture avec caisse trouvée à 0 : probablement le fond de caisse retiré "
       "la veille, pas une perte – à traiter à part avant de parler de comportement à risque."])


def ml_segmentation(sales, clients):
    agg = defaultdict(lambda: dict(ca=0.0, ttc=0.0, marge=0.0, cout=0.0, q=0.0, rem=0.0, brut=0.0, docs=set(),
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
        a["ttc"] += f(s["CA_TTC"])
        a["q"] += f(s["QuantiteVendue"])
        a["rem"] += f(s["Remise_HT"])
        a["brut"] += f(s["CA_HT"]) + f(s["Remise_HT"])
        if s["Marge_HT"] != "":
            a["marge"] += f(s["Marge_HT"])
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
        rows.append({"Company_Id": cid, "Code": c["Code"], "Nom": c["Nom"], "TypeClient": c["TypeClient"],
                     "Ville": c["Ville"], "Geo_Id": c["Geo_Id"],
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
                     "Solde": c["Solde"], "CA_TTC_Total": r2(a["ttc"], 2),
                     "PremierAchat": first.isoformat(), "DernierAchat": last.isoformat()})
    rows.sort(key=lambda r: -f(r["X_CA_HT_Total"]))
    share = 100 * sum(f(r["X_CA_HT_Total"]) for r in rows) / total_ca
    known_type = sum(r["TypeClient"] in ("B2B", "PARTICULIER") for r in rows)
    W("ml/ml_11_4_segmentation_clients.csv", list(rows[0].keys()), rows,
      "ML 11.4 – Segmentation client : CA total, fréquence, panier moyen, ancienneté, récence, type de client.",
      "1 ligne = 1 client identifié ayant au moins une vente (client comptoir anonyme exclu)",
      "fait_ventes, dim_client (CompaniesList, Clients)", "§11.4 Segmentation client (clustering) ; §6.3 clients actifs",
      [f"{len(rows)} clients identifiés ; ils représentent {share:.1f} % du CA HT (cahier : ~60 %). L'écart vient du "
        "double comptage évité : les factures qui refacturent des BL (clients identifiés) ne sont plus comptées deux fois.",
       f"Type de client connu (B2B / particulier) pour {known_type} clients seulement (les autres n'existent pas dans le "
       "fichier Clients) : `X_EstB2B` vide = inconnu.",
       "Clients actifs (§6.3) = clients ayant au moins une transaction sur la période → tous les clients de ce fichier ; "
       "filtrer sur `X_RecenceJours` pour une période plus courte.",
       "Standardiser les X avant K-Means (montants très asymétriques : passer CA et quantités en log)."])


# --------------------------------------------------------------------------- #
# README
# --------------------------------------------------------------------------- #
SPEC_MAP = [
    ("Direction générale", "Quel est le CA ? Évolution ? Période la plus forte ?",
     "CA = Σ CA_HT ; croissance = (CA_N − CA_N-1)/CA_N-1 × 100 ; nb documents = COUNT(DISTINCT Document_Id)",
     "fait_ventes × dim_temps"),
    ("Responsable commercial", "Produits / marques les plus vendus, panier moyen, évolution",
     "Σ QuantiteVendue, Σ CA_HT par Product_Id / Marque ; panier moyen = Σ CA_HT / nb documents",
     "fait_ventes × dim_produit × dim_temps"),
    ("Responsable relation client", "CA par client, fréquence, panier client, clients actifs",
     "Σ CA_HT par Company_Id ; COUNT(DISTINCT Document_Id) ; CA client / nb documents client",
     "fait_ventes × dim_client ; ml_11_4_segmentation_clients"),
    ("Responsable approvisionnement / stock", "Stock faible, ruptures, faible rotation, demande à prévoir",
     "Quantity, EnRupture, StockFaible, Rotation ; taux de rupture = Σ EnRupture / nb produits × 100",
     "fait_stock_actuel, fait_stock_hebdo, fait_stock_mouvements ; ml_11_1"),
    ("Responsable financier / caisse", "Montants encaissés, répartition par moyen, évolution",
     "Σ Amount (IsPurchase = false) par PaymentMode_Id et par DateKey ; nb transactions = COUNT(Id)",
     "fait_paiements × dim_paiement × dim_temps ; ml_11_3"),
]


def write_readme():
    L = ["# Jeu de données Health Retailers – conforme au cahier de spécification", "",
         "Construit par `build_dataset.py` à partir des fichiers nettoyés (`cleaned/`). Les fichiers originaux et nettoyés "
         "ne sont pas modifiés.", "",
         "## Organisation", "", "```", "dataset/",
         "├── dwh/   modèle en étoile : dimensions (dim_*) et faits (fait_*)",
         "├── ml/    un jeu de données par objectif ML du §11 (X préfixées X_, cible Y_)",
         "├── controles_qualite.csv   contrôles du §7.1",
         "└── README.md", "```", "",
         "## Conventions", "",
         "- CSV UTF-8, séparateur virgule, décimale `.`, dates ISO `AAAA-MM-JJ`, booléens `true/false`.",
         "- Clé de date `DateKey` = `AAAAMMJJ` (jointure avec `dim_temps`). Clé produit `Product_Id`, clé client / "
         "fournisseur `Company_Id`, moyen de paiement `PaymentMode_Id`, document `Document_Id`.",
         "- Les colonnes recopiées d'une source gardent leur **nom d'origine** (`Quantity`, `PrixHt`, `Libellé`…). "
         "Les mesures calculées portent le vocabulaire du cahier (`CA_HT`, `Marge_HT`, `PanierMoyen`, `EnRupture`…).",
         "- Dans `ml/` : variables explicatives préfixées `X_`, cibles préfixées `Y_`, colonnes `Regle_*` = règles métier "
         "d'interprétation (ni X ni Y). Les identifiants servent seulement à relier les résultats.", "",
         "## Besoins du cahier → tables", "",
         "| Décideur | Questions | Mesure / formule | Tables |", "|---|---|---|---|"]
    L += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in SPEC_MAP]
    L += ["", "Filtres minimum du §10 (période, produit, marque) : `dim_temps`, `dim_produit.Product_Id`, "
          "`dim_produit.Marque`.", "",
          "## Schéma en étoile", "", "```",
          "dim_temps ─┐        ┌─ dim_produit ── (Famille, Marque)",
          "dim_client ┼─ fait_ventes ─┼─ dim_document ── dim_paiement",
          "dim_geographie ─ dim_client / dim_fournisseur   dim_utilisateur (CreatedBy)",
          "fait_achats      : dim_temps, dim_produit, dim_fournisseur, dim_document",
          "fait_stock_*     : dim_temps, dim_produit",
          "fait_paiements   : dim_temps, dim_client, dim_paiement, dim_document", "```", "",
          "## Tables", ""]
    for rel, t in TABLES.items():
        L += [f"### `{rel}`", "", t["desc"], "",
              f"- **Granularité :** {t['grain']}", f"- **Lignes :** {t['n']:,}", f"- **Sources :** {t['sources']}",
              f"- **Cahier :** {t['spec']}", f"- **Colonnes :** {', '.join('`' + c + '`' for c in t['cols'])}"]
        L += [f"- {n}" for n in t["notes"]]
        L.append("")
    L += ["## Contrôles qualité (§7.1)", "", "| Contrôle | Table | Concernés | Total | % | Statut |", "|---|---|---|---|---|---|"]
    L += [f"| {c['Controle']} | {c['Table']} | {c['NbConcernes']:,} | {c['NbTotal']:,} | {c['Pourcentage']} | {c['Statut']} |"
          for c in CHECKS]
    (OUT / "README.md").write_text("\n".join(L), encoding="utf-8")


# --------------------------------------------------------------------------- #
def main():
    docs = R("documents.csv")
    docs_by_id = {d["Id"]: d for d in docs}
    items = R("document_items.csv")
    linked_invoices = {r["Document1_Id"] for r in R("related_documents.csv")
                       if docs_by_id.get(r["Document1_Id"], {}).get("DocumentType_Id") == "1"}
    txn = {t["Id"]: t["Company_Id"] for t in R("transactions.csv")}
    lines_by_ps = {}
    for it in items:
        lines_by_ps[it["ProductStock_Id"]] = it["Description"]
    cost_by_line = {}
    for m in R("stock_movements.csv"):
        if m["DocumentId"] and m["Extra_cump"] and m["Action"] == "VALIDATION":
            cost_by_line.setdefault((m["DocumentId"], m["ProductStock_Id"]), f(m["Extra_cump"]))

    # contrôles d'intégrité de base
    doc_ids = set(docs_by_id)
    check("Ligne de document sans document", "documentItemm", sum(1 for i in items if i["Document_Id"] not in doc_ids), len(items))
    check("Ligne de document sans produit", "documentItemm", sum(1 for i in items if not i["Product_Id"]), len(items))
    check("Identifiant de document en double", "Documents", len(docs) - len(doc_ids), len(docs))
    check("Quantité ≤ 0 sur une ligne", "documentItemm", sum(1 for i in items if f(i["Quantity"]) <= 0), len(items),
          detail="quantités nulles / négatives")
    check("Prix unitaire HT ≤ 0", "documentItemm", sum(1 for i in items if f(i["PrixHt"]) <= 0), len(items))
    check("Remise > 100 %", "documentItemm", sum(1 for i in items if f(i["DiscountPourcentage"]) > 100), len(items))
    out = [d for d in docs if not (START <= d_of(d["DocumentDate"]) <= END)]
    check("Document hors période 30/09/2024 – 30/04/2025", "Documents", len(out), len(docs))
    check("Document brouillon (non validé)", "Documents", sum(d["IsValidated"] != "true" for d in docs), len(docs),
          detail="exclus des faits")
    check("Facture client regroupant des BL (double comptage évité)", "Documents", len(linked_invoices),
          sum(d["DocumentType_Id"] == "1" for d in docs), detail="exclues de fait_ventes, les BL sont comptés")

    cal = build_calendar()
    geo = build_geo(R("customers.csv"), R("suppliers.csv"))
    products = build_products(lines_by_ps)
    ctype = {c["Id"]: c["CompanyType"] for c in R("companies.csv")}
    pays = R("payments.csv")
    sale_cids = {txn.get(d["Transaction_Id"], "") for d in docs if d["Flow"] in ("SALE", "SALE_RETURN")}
    sale_cids |= {p["Company_Id"] for p in pays if not payment_side(p, ctype)}
    sup_ids = {txn.get(d["Transaction_Id"], "") for d in docs if d["Flow"] in ("PURCHASE", "PURCHASE_RETURN")}
    sup_ids |= {p["Company_Id"] for p in pays if payment_side(p, ctype)}
    clients = build_clients(geo, sale_cids - {""})
    build_suppliers(geo, sup_ids - {""})
    build_payment_modes()
    build_documents(docs, linked_invoices, cal)
    build_users()
    sales = build_sales(docs_by_id, items, linked_invoices, txn, products, cost_by_line)
    check("Ligne de vente sans coût (marge non calculable)", "fait_ventes",
          sum(s["SourceCout"] == "ABSENT" for s in sales), len(sales))
    check("Ligne de vente sous le coût", "fait_ventes", sum(s["VenteSousCout"] == "true" for s in sales), len(sales))
    build_purchases(docs_by_id, items, txn)
    weeks = build_stock(products, sales, cal, doc_ids)
    build_payments({d["DocumentNumber"]: d["Id"] for d in docs}, ctype)
    ml_demand(sales, products, cal, weeks)
    ml_sales_anomalies(sales, products)
    ml_cash()
    ml_segmentation(sales, clients)

    with (OUT / "controles_qualite.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CHECKS[0].keys()))
        w.writeheader()
        w.writerows(CHECKS)
    write_readme()
    print(f"\nJeu de données écrit dans {OUT}")


if __name__ == "__main__":
    main()

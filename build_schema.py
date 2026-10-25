#!/usr/bin/env python3
"""
Documentation du schéma du Data Warehouse – version B (5 dimensions, 4 tables de faits).

Entrée  : ./dataset/dwh/*.csv            (sortie de build_dataset.py)
Sortie  : ./dataset/schema/
            schema_dwh_diagramme.svg / .png   diagramme du modèle (PNG rendu par Chrome / Edge)
            schema_dwh.html / .pdf            descriptif détaillé : modèle, tables, relations, dictionnaire, mesures
            schema_dwh.sql                    CREATE TABLE PostgreSQL avec clés primaires et étrangères
            README.md
Vérifie que le dictionnaire correspond exactement aux colonnes des CSV ; tous les chiffres sont recalculés.

Bibliothèque standard uniquement (+ Chrome ou Edge pour le PNG et le PDF) :  python build_schema.py
"""
import csv
import html
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DWH = HERE / "dataset" / "dwh"
OUT = HERE / "dataset" / "schema"
REAL_END = "20250430"           # délimitation réel / synthétique (DateKey)

# table -> (type, grain, [(colonne, type SQL, clé, rôle affiché, description)])
#   clé : "PK", "FK:table.colonne", "PK FK:table.colonne", "M" (mesure) ou ""
META = {
    "dim_temps": ("Dimension", "1 ligne = 1 date", [
        ("DateKey", "INTEGER", "PK", "PK", "Clé de la date au format AAAAMMJJ (ex. 20250430)."),
        ("Date", "DATE", "", "attribut", "Date calendaire."),
        ("Annee", "SMALLINT", "", "attribut", "Année civile."),
        ("Trimestre", "SMALLINT", "", "attribut", "Trimestre (1 à 4) ; vues trimestrielles de la direction (§6.1)."),
        ("Mois", "SMALLINT", "", "attribut", "Numéro du mois (1 à 12)."),
        ("SemaineISO", "SMALLINT", "", "attribut", "Numéro de semaine ISO 8601 (granularité de la prévision ML)."),
        ("EstFerie", "BOOLEAN", "", "attribut",
         "Jour férié français (fêtes fixes et fêtes mobiles calculées à partir de Pâques). Remplace une source "
         "externe de calendrier.")]),
    "dim_produit": ("Dimension", "1 ligne = 1 produit", [
        ("Product_Id", "INTEGER", "PK", "PK", "Identifiant numérique du produit dans le logiciel (référentiel ProductStocks)."),
        ("Libellé", "TEXT", "", "attribut",
         "Nom du produit (export Produits, sinon dernier libellé connu dans les événements ou les lignes de vente)."),
        ("Famille", "TEXT", "", "attribut", "Catégorie du produit ; NON RENSEIGNE si inconnue."),
        ("Marque", "TEXT", "", "attribut", "Marque (export Produits, ou déduite du début du libellé) ; NON RENSEIGNE si inconnue.")]),
    "dim_client": ("Dimension", "1 ligne = 1 client, y compris le client comptoir anonyme", [
        ("Company_Id", "INTEGER", "PK", "PK", "Identifiant de la société dans le logiciel (CompaniesList) ; -1 = client non renseigné."),
        ("Nom", "TEXT", "", "attribut", "Nom du client, pour l'affichage dans le dashboard Clients."),
        ("TypeClient", "TEXT", "", "attribut",
         "PARTICULIER, B2B (laboratoires), COMPTOIR_ANONYME (client de passage, Company_Id = 2) ou NON RENSEIGNE. "
         "Axe « type client » du cahier (§6, §10)."),
        ("EstClientIdentifie", "BOOLEAN", "", "attribut",
         "false pour le client comptoir anonyme et la ligne -1 : filtre de tous les KPI clients. Gardé bien que "
         "théoriquement déductible : il porte une règle métier (quels clients sont anonymes), définie une seule fois.")]),
    "dim_fournisseur": ("Dimension", "1 ligne = 1 fournisseur", [
        ("Fournisseur_Id", "INTEGER", "PK", "PK",
         "Identifiant de la société fournisseur dans le logiciel (CompaniesList) ; -1 = fournisseur non renseigné, ou "
         "paiement qui ne concerne pas un fournisseur."),
        ("Nom", "TEXT", "", "attribut",
         "Nom du fournisseur (fichier Fournisseurs quand le code y existe, sinon CompaniesList), pour l'affichage dans "
         "les dashboards Achats et Paiements.")]),
    "dim_paiement": ("Dimension", "1 ligne = 1 moyen de paiement", [
        ("PaymentMode_Id", "INTEGER", "PK", "PK",
         "Identifiant du moyen de paiement : 11 Espèces, 5 Carte bancaire, 1 Chèque, 7 Crédit (paiement différé), "
         "21 Jetons, -1 Non renseigné."),
        ("PaymentModeName", "TEXT", "", "attribut",
         "Libellé affiché dans les graphiques et les filtres du dashboard Paiements (§9 : « Libellé / type de moyen »).")]),
    "fait_ventes": ("Fait", "1 produit vendu dans 1 document à 1 date", [
        ("Id", "BIGINT", "PK", "PK", "Identifiant de la ligne de document source."),
        ("Document_Id", "BIGINT", "", "dimension dégénérée",
         "Identifiant du document (ticket, bon de livraison, facture) : permet de compter les ventes et de calculer "
         "le panier moyen, sans dimension Document."),
        ("DateKey", "INTEGER", "FK:dim_temps.DateKey", "FK → dim_temps", "Date du document."),
        ("Product_Id", "INTEGER", "FK:dim_produit.Product_Id", "FK → dim_produit", "Produit vendu."),
        ("Company_Id", "INTEGER", "FK:dim_client.Company_Id", "FK → dim_client", "Client de la transaction ; -1 si non renseigné."),
        ("QuantiteVendue", "NUMERIC(14,4)", "M", "mesure", "Quantité vendue, négative pour un retour ou un avoir."),
        ("Remise_HT", "NUMERIC(14,4)", "M", "mesure", "Montant total de la remise HT accordée sur la ligne (cité par le cahier, §9)."),
        ("CA_HT", "NUMERIC(14,4)", "M", "mesure", "Chiffre d'affaires HT de la ligne, remises déduites, signé (négatif pour un retour)."),
        ("Cout_HT", "NUMERIC(14,4)", "M", "mesure",
         "Coût d'achat HT = quantité × coût unitaire à la date de la vente (coût moyen pondéré du mouvement de stock, "
         "à défaut prix d'achat du produit), calculé dans l'ETL. Vide si aucun coût n'est connu.")]),
    "fait_achats": ("Fait", "1 produit acheté dans 1 facture fournisseur à 1 date", [
        ("Id", "BIGINT", "PK", "PK", "Identifiant de la ligne de document source."),
        ("Document_Id", "BIGINT", "", "dimension dégénérée",
         "Identifiant de la facture (ou de l'avoir) fournisseur : permet de compter les factures fournisseurs."),
        ("DateKey", "INTEGER", "FK:dim_temps.DateKey", "FK → dim_temps", "Date de la facture fournisseur."),
        ("Product_Id", "INTEGER", "FK:dim_produit.Product_Id", "FK → dim_produit", "Produit acheté."),
        ("Fournisseur_Id", "INTEGER", "FK:dim_fournisseur.Fournisseur_Id", "FK → dim_fournisseur",
         "Fournisseur de la facture ; -1 si la transaction ne cite aucune société."),
        ("QuantiteAchetee", "NUMERIC(14,4)", "M", "mesure", "Quantité achetée, négative pour un avoir fournisseur."),
        ("MontantAchat_HT", "NUMERIC(14,4)", "M", "mesure",
         "Montant HT de la ligne après remise, signé (négatif pour un avoir). Le prix unitaire n'est pas stocké : "
         "il se recalcule (montant / quantité).")]),
    "fait_stock_actuel": ("Fait (snapshot)", "1 produit à la date de snapshot", [
        ("Product_Id", "INTEGER", "PK FK:dim_produit.Product_Id", "PK / FK → dim_produit", "Produit (une ligne par produit)."),
        ("DateKey", "INTEGER", "FK:dim_temps.DateKey", "FK → dim_temps", "Date de la photo du stock (fin de la période chargée)."),
        ("Quantity", "NUMERIC(14,3)", "M", "mesure",
         "Quantité en stock selon le logiciel ; peut être négative quand une vente est enregistrée avant ou sans la "
         "réception de la marchandise (le logiciel l'autorise pour les ventes comptoir et les bons de livraison)."),
        ("QuantiteAlerte", "NUMERIC(12,3)", "", "seuil",
         "Seuil d'alerte de stock choisi par le magasin pour le produit (export Produits, sinon paramètre par défaut du "
         "logiciel = 5). Stocké à côté de la quantité : le stock faible se calcule dans la même table. Non additif, non "
         "calculable ; une seule valeur par produit (une ligne par produit).")]),
    "fait_paiements": ("Fait", "1 paiement imputé à 1 document réglé", [
        ("Id", "BIGINT", "PK", "PK", "Clé technique de la ligne d'imputation (un paiement qui règle plusieurs documents a "
                                     "plusieurs lignes)."),
        ("Payment_Id", "BIGINT", "", "dimension dégénérée",
         "Numéro du paiement dans le logiciel : Nombre de paiements = DISTINCTCOUNT(Payment_Id)."),
        ("Document_Id", "BIGINT", "", "dimension dégénérée",
         "Document réglé : même clé que fait_ventes (encaissement client) ou fait_achats (paiement fournisseur). "
         "Répond à « quelle vente / quelle facture ce paiement règle-t-il ? » ; -1 si aucune imputation."),
        ("DateKey", "INTEGER", "FK:dim_temps.DateKey", "FK → dim_temps", "Date du paiement."),
        ("PaymentMode_Id", "INTEGER", "FK:dim_paiement.PaymentMode_Id", "FK → dim_paiement", "Moyen de paiement ; -1 si non renseigné."),
        ("Company_Id", "INTEGER", "FK:dim_client.Company_Id", "FK → dim_client",
         "Client qui paie (2 = client comptoir anonyme) ; -1 pour un paiement à un fournisseur."),
        ("Fournisseur_Id", "INTEGER", "FK:dim_fournisseur.Fournisseur_Id", "FK → dim_fournisseur",
         "Fournisseur payé ; -1 pour un encaissement client. Remplace l'indicateur EstPaiementFournisseur, qui se "
         "recalcule (paiement fournisseur ⇔ Fournisseur_Id ≠ -1)."),
        ("Amount", "NUMERIC(14,4)", "M", "mesure",
         "Montant TTC réellement versé et imputé à ce document ; la somme des lignes d'un paiement est exactement le "
         "montant payé. Valeur de base non recalculable : elle diffère du CA (impayés, paiements fractionnés ou différés, "
         "TVA).")]),
}
DIMS = ["dim_temps", "dim_produit", "dim_client", "dim_fournisseur", "dim_paiement"]
FACTS = ["fait_ventes", "fait_achats", "fait_stock_actuel", "fait_paiements"]


# --------------------------------------------------------------------------- #
# lecture et vérification
# --------------------------------------------------------------------------- #
def read(t):
    with (DWH / f"{t}.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def verify():
    data = {}
    for t, (_, _, cols) in META.items():
        with (DWH / f"{t}.csv").open(encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        expected = [c[0] for c in cols]
        assert header == expected, f"{t} : colonnes différentes\nCSV  : {header}\nMETA : {expected}"
        data[t] = read(t)
    return data


def fr(n, d=0):
    s = f"{n:,.{d}f}".replace(",", " ").replace(".", ",")
    return s


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def stats(data):
    S = {t: len(rows) for t, rows in data.items()}
    v, p, st = data["fait_ventes"], data["fait_paiements"], data["fait_stock_actuel"]
    S["dates"] = (data["dim_temps"][0]["Date"], data["dim_temps"][-1]["Date"])
    S["ventes_reel"] = sum(1 for r in v if r["DateKey"] <= REAL_END)
    S["docs"] = len({r["Document_Id"] for r in v})
    S["docs_reel"] = len({r["Document_Id"] for r in v if r["DateKey"] <= REAL_END})
    cli = [r for r in p if r["Fournisseur_Id"] == "-1"]
    sup = [r for r in p if r["Fournisseur_Id"] != "-1"]
    S["encaisse"], S["n_cli"] = sum(num(r["Amount"]) for r in cli), len({r["Payment_Id"] for r in cli})
    S["decaisse"], S["n_sup"] = sum(num(r["Amount"]) for r in sup), len({r["Payment_Id"] for r in sup})
    S["comptoir"] = len({r["Payment_Id"] for r in cli if r["Company_Id"] == "2"})
    S["sans_mode"] = len({r["Payment_Id"] for r in cli if r["PaymentMode_Id"] == "-1"})
    per_pay = Counter(r["Payment_Id"] for r in p)
    S["n_pay"] = len(per_pay)
    S["pay_multi"] = sum(1 for n in per_pay.values() if n > 1)
    S["pay_sans_doc"] = len({r["Payment_Id"] for r in p if r["Document_Id"] == "-1"})
    S["paiements_reel"] = len({r["Payment_Id"] for r in p if r["DateKey"] <= REAL_END})
    a = data["fait_achats"]
    S["achats_reel"] = sum(1 for r in a if r["DateKey"] <= REAL_END)
    S["achats_ht"] = sum(num(r["MontantAchat_HT"]) for r in a)
    S["factures_four"] = len({r["Document_Id"] for r in a})
    doc_total = Counter()
    for r in a:
        doc_total[r["Document_Id"]] += num(r["MontantAchat_HT"])
    S["avoirs_four"] = sum(1 for v in doc_total.values() if v < 0)
    per_product = Counter(pid for pid, _ in {(r["Product_Id"], r["Fournisseur_Id"]) for r in a})
    S["multi_four"] = sum(1 for n in per_product.values() if n > 1)
    S["inconnus_four"] = sum(1 for r in data["dim_fournisseur"] if r["Nom"].startswith("FOURNISSEUR INCONNU"))
    S["ca_ht"] = sum(num(r["CA_HT"]) for r in v)
    S["types"] = Counter(r["TypeClient"] for r in data["dim_client"])
    S["alertes"] = Counter(r["QuantiteAlerte"] for r in data["fait_stock_actuel"]).most_common(2)
    S["stock_date"] = st[0]["DateKey"]
    alert = {r["Product_Id"]: num(r["QuantiteAlerte"]) for r in st}
    S["rupture"] = sum(1 for r in st if num(r["Quantity"]) == 0)
    S["negatif"] = sum(1 for r in st if num(r["Quantity"]) < 0)
    S["faible"] = sum(1 for r in st if 0 < num(r["Quantity"]) <= alert[r["Product_Id"]])
    ex = [r for r in v if r["Document_Id"] == "15"]
    S["ex"] = dict(n=len(ex), ca=sum(num(r["CA_HT"]) for r in ex), cout=sum(num(r["Cout_HT"]) for r in ex),
                   lignes=[num(r["CA_HT"]) for r in ex])
    return S


# --------------------------------------------------------------------------- #
# diagramme SVG
# --------------------------------------------------------------------------- #
ROW, HEAD = 25, 44
BOXES = {   # table -> (x, y, largeur, style)
    "dim_temps": (57, 150, 330, "dim"), "dim_produit": (421, 150, 330, "dim"), "dim_client": (785, 150, 330, "dim"),
    "dim_fournisseur": (1149, 150, 330, "dim"), "dim_paiement": (1513, 150, 330, "dim"),
    "fait_stock_actuel": (83, 600, 390, "fait"), "fait_ventes": (521, 600, 390, "fait"),
    "fait_achats": (959, 600, 400, "fait"), "fait_paiements": (1407, 600, 410, "pay"),
}
ICON = {"dim_temps": "cal", "dim_produit": "box", "dim_client": "users", "dim_fournisseur": "truck",
        "dim_paiement": "card", "fait_stock_actuel": "box", "fait_ventes": "chart", "fait_achats": "cart",
        "fait_paiements": "coins"}
COL = {"dim_temps": "#1e63c4", "dim_produit": "#2f9b46", "dim_client": "#7b3fc4", "dim_fournisseur": "#c0661c",
       "dim_paiement": "#b0397a"}
# relations dimension -> faits, une voie horizontale par dimension (de haut en bas)
LANES = [("dim_temps", 425, ["fait_stock_actuel", "fait_ventes", "fait_achats", "fait_paiements"]),
         ("dim_produit", 450, ["fait_stock_actuel", "fait_ventes", "fait_achats"]),
         ("dim_client", 475, ["fait_ventes", "fait_paiements"]),
         ("dim_fournisseur", 500, ["fait_achats", "fait_paiements"]),
         ("dim_paiement", 525, ["fait_paiements"])]


def esc(s):
    return html.escape(str(s))


def svg_icon(kind, x, y):
    w = 'stroke="#fff" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"'
    g = {"cal": f'<rect x="0" y="3" width="24" height="21" rx="3" {w}/><line x1="0" y1="10" x2="24" y2="10" {w}/>'
                f'<line x1="7" y1="0" x2="7" y2="6" {w}/><line x1="17" y1="0" x2="17" y2="6" {w}/>'
                + "".join(f'<circle cx="{a}" cy="{b}" r="1.4" fill="#fff"/>' for a, b in ((5, 15), (12, 15), (19, 15), (5, 20), (12, 20))),
         "box": f'<path d="M12 1 L23 6.5 L23 18.5 L12 24 L1 18.5 L1 6.5 Z" {w}/><path d="M1 6.5 L12 12 L23 6.5 M12 12 L12 24" {w}/>',
         "users": f'<circle cx="9" cy="7" r="5" {w}/><path d="M0 23 C0 15 18 15 18 23" {w}/><circle cx="19" cy="8" r="4" {w}/>'
                  f'<path d="M17 15 C24 15 26 18 26 22" {w}/>',
         "truck": f'<rect x="0" y="5" width="16" height="13" rx="1.5" {w}/><path d="M16 9 H22 L26 14 V18 H16 Z" {w}/>'
                  f'<circle cx="6" cy="21" r="2.6" {w}/><circle cx="20" cy="21" r="2.6" {w}/>',
         "card": f'<rect x="0" y="3" width="26" height="19" rx="3" {w}/><line x1="0" y1="9" x2="26" y2="9" {w}/>'
                 f'<line x1="4" y1="16" x2="11" y2="16" {w}/>',
         "cart": f'<path d="M0 2 H4 L7 16 H22 L25 6 H5.5" {w}/><circle cx="9" cy="21" r="2.2" {w}/><circle cx="20" cy="21" r="2.2" {w}/>',
         "chart": "".join(f'<rect x="{a}" y="{24 - h}" width="4.5" height="{h}" rx="1" fill="#fff"/>' for a, h in ((2, 8), (9, 14), (16, 19), (23, 24))),
         "coins": "".join(f'<ellipse cx="11" cy="{yy}" rx="10" ry="4" {w}/>' for yy in (6, 12, 18)) + f'<ellipse cx="21" cy="14" rx="6" ry="6" {w}/>'}[kind]
    return f'<g transform="translate({x},{y})">{g}</g>'


def svg_diagram(S):
    W, H = 1900, 1000
    cx = W / 2
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         'font-family="Segoe UI, Arial, sans-serif">',
         '<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f2f7fd"/>'
         '<stop offset="0.5" stop-color="#f4f9fb"/><stop offset="1" stop-color="#eff8f2"/></linearGradient>'
         '<linearGradient id="hdim" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#123f7c"/><stop offset="1" stop-color="#1d5aa6"/></linearGradient>'
         '<linearGradient id="hfait" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0f5e3c"/><stop offset="1" stop-color="#1b7f55"/></linearGradient>'
         '<linearGradient id="hpay" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#5a2f93"/><stop offset="1" stop-color="#7b4cc0"/></linearGradient>'
         '<filter id="sh" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="3" stdDeviation="4" '
         'flood-color="#1f3b63" flood-opacity="0.16"/></filter></defs>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="url(#bg)"/>',
         f'<rect x="{cx - 456}" y="8" width="912" height="64" rx="22" fill="#e6f0fc" stroke="#c5d9f2" stroke-width="1.5"/>',
         f'<text x="{cx}" y="52" text-anchor="middle" font-size="33" font-weight="700" fill="#12365e">'
         'Schéma du Data Warehouse — Health Retailers</text>',
         f'<text x="{cx}" y="98" text-anchor="middle" font-size="19" fill="#3e5f86">Modèle BI : '
         f'5 dimensions et 4 tables de faits — volumes : {esc(S["dates"][0][8:10] + "/" + S["dates"][0][5:7] + "/" + S["dates"][0][:4])}'
         f' → {esc(S["dates"][1][8:10] + "/" + S["dates"][1][5:7] + "/" + S["dates"][1][:4])} (réel + synthétique)</text>',
         f'<rect x="38" y="116" width="{W - 76}" height="290" rx="22" fill="#dfeaf8" fill-opacity="0.6" stroke="#c3d6ef" stroke-width="1.5"/>',
         f'<rect x="38" y="560" width="{W - 76}" height="340" rx="22" fill="#e0f2e8" fill-opacity="0.65" stroke="#bfe0cc" stroke-width="1.5"/>',
         '<rect x="57" y="104" width="190" height="32" rx="10" fill="#174a8b"/>'
         '<text x="73" y="127" font-size="18" font-weight="700" fill="#fff" letter-spacing="0.5">DIMENSIONS</text>',
         '<rect x="57" y="548" width="100" height="32" rx="10" fill="#1b7a52"/>'
         '<text x="73" y="571" font-size="18" font-weight="700" fill="#fff" letter-spacing="0.5">FAITS</text>']
    geo = {}
    for t, (x, y, w, kind) in BOXES.items():
        cols = META[t][2]
        h = HEAD + len(cols) * ROW + 16
        geo[t] = (x, y, w, h)
        head = {"dim": "url(#hdim)", "fait": "url(#hfait)", "pay": "url(#hpay)"}[kind]
        border = {"dim": "#c9d7ea", "fait": "#bfe2cf", "pay": "#d6c8ee"}[kind]
        band = {"dim": "#f2f6fc", "fait": "#f1f8f4", "pay": "#f6f2fc"}[kind]
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#fff" stroke="{border}" stroke-width="1.5" filter="url(#sh)"/>')
        o.append(f'<path d="M{x} {y + HEAD} V{y + 10} Q{x} {y} {x + 10} {y} H{x + w - 10} Q{x + w} {y} {x + w} {y + 10} '
                 f'V{y + HEAD} Z" fill="{head}"/>')
        o.append(svg_icon(ICON[t], x + 16, y + 9))
        o.append(f'<text x="{x + 54}" y="{y + 29}" font-size="21" font-weight="700" fill="#fff">{t}</text>')
        o.append(f'<text x="{x + w - 16}" y="{y + 28}" text-anchor="end" font-size="15" fill="#e8f0fb">{fr(S[t])} lignes</text>')
        for i, (col, _, key, _, _) in enumerate(cols):
            ry = y + HEAD + 8 + i * ROW
            if i % 2 == 0:
                o.append(f'<rect x="{x + 12}" y="{ry}" width="{w - 24}" height="{ROW - 2}" rx="5" fill="{band}"/>')
            parts = key.split()
            is_key = "PK" in parts or any(p.startswith("FK") for p in parts)
            tag, ref = "", ""
            if key == "M":
                tag = '<tspan dx="10" font-size="15" fill="#7d6aa8">[mesure]</tspan>'
            elif is_key:
                label = "PK/FK" if "PK" in parts and len(parts) > 1 else "PK" if "PK" in parts else "FK"
                color = "#2a7a52" if label == "FK" else "#1f4e8c"
                tag = f'<tspan dx="10" font-size="15" font-weight="700" fill="{color}">[{label}]</tspan>'
                fk = next((p[3:].split(".")[0] for p in parts if p.startswith("FK:")), "")
                if fk:
                    ref = f'<tspan dx="6" font-size="15" fill="#5a6b82">→ {fk}</tspan>'
            o.append(f'<text x="{x + 24}" y="{ry + 17}" font-size="16" font-weight="{700 if is_key else 400}" '
                     f'fill="#1d2330">{esc(col)}{tag}{ref}</text>')

    def line(d, color):
        o.append(f'<path d="{d}" stroke="#f3f8fb" stroke-width="10" fill="none" stroke-linecap="round"/>')
        o.append(f'<path d="{d}" stroke="{color}" stroke-width="3.5" fill="none" stroke-linejoin="round"/>')

    def badge(x, y, label, color):
        o.append(f'<circle cx="{x}" cy="{y}" r="13" fill="{color}" stroke="#fff" stroke-width="2.5"/>'
                 f'<text x="{x}" y="{y + 5.5}" text-anchor="middle" font-size="15" font-weight="700" fill="#fff">{label}</text>')

    # point d'arrivée de chaque relation sur sa table de faits : répartis sur la largeur de la boîte
    incoming = {f: [d for d, _, facts in LANES if f in facts] for f in BOXES if f.startswith("fait_")}
    slot = {}
    for f, dims in incoming.items():
        x, _, w, _ = geo[f]
        for k, d in enumerate(dims):
            slot[(d, f)] = x + w * (k + 1) / (len(dims) + 1)
    badges = []
    for d, lane, facts in LANES:
        x, y, w, h = geo[d]
        dx = x + w / 2
        xs = [slot[(d, f)] for f in facts]
        line(f"M{dx} {y + h} V{lane}", COL[d])
        line(f"M{min(xs + [dx])} {lane} H{max(xs + [dx])}", COL[d])
        for f, fx in zip(facts, xs):
            line(f"M{fx} {lane} V{geo[f][1]}", COL[d])
            badges.append((fx, geo[f][1] - 16, "N", COL[d]))
        badges.append((dx, y + h + 16, "1", COL[d]))
    for b in badges:
        badge(*b)
    ly = 920
    o += [f'<rect x="38" y="{ly}" width="{W - 76}" height="68" rx="14" fill="#fff" fill-opacity="0.7" stroke="#b8c6d8" '
          'stroke-width="1.5" stroke-dasharray="6 5"/>',
          f'<text x="70" y="{ly + 41}" font-size="17" font-weight="700" fill="#1d2330">Légende :</text>']
    for x, w, label, fill, color, txt in ((175, 78, "PK", "#d6e5f8", "#1f4e8c", "= clé primaire"),
                                          (390, 78, "FK", "#d5eedf", "#2a7a52", "= clé étrangère"),
                                          (610, 100, "mesure", "#e7ddf6", "#5a3f8f", "= valeur additive")):
        o.append(f'<rect x="{x}" y="{ly + 17}" width="{w}" height="34" rx="17" fill="{fill}"/>'
                 f'<text x="{x + w / 2}" y="{ly + 40}" text-anchor="middle" font-size="16" font-weight="700" fill="{color}">{label}</text>'
                 f'<text x="{x + w + 14}" y="{ly + 40}" font-size="15" fill="#2b3442">{txt}</text>')
    badge(900, ly + 34, "1", COL["dim_temps"])
    o.append(f'<path d="M915 {ly + 34} H985" stroke="{COL["dim_temps"]}" stroke-width="3"/>'
             f'<path d="M981 {ly + 28} L991 {ly + 34} L981 {ly + 40} Z" fill="{COL["dim_temps"]}"/>')
    badge(1007, ly + 34, "N", COL["dim_temps"])
    o.append(f'<text x="1033" y="{ly + 30}" font-size="15" fill="#2b3442">= relation 1 vers plusieurs</text>'
             f'<text x="1033" y="{ly + 49}" font-size="12" fill="#5a6b82">(1 ligne de dimension pour plusieurs lignes de la '
             'table de faits ; la couleur est celle de la dimension)</text>')
    o.append("</svg>")
    return "\n".join(o), W, H


# --------------------------------------------------------------------------- #
# descriptif HTML (imprimé en PDF)
# --------------------------------------------------------------------------- #
CSS = """
@page { size: A4; margin: 14mm 15mm 16mm 15mm;
  @bottom-center { content: "Health Retailers — Schéma du Data Warehouse (version B) — page " counter(page) " / " counter(pages); font-family: Arial, sans-serif; font-size: 7pt; color: #666; } }
@page paysage { size: A4 landscape; margin: 10mm 12mm 14mm 12mm; }
* { box-sizing: border-box; }
body { font-family: Arial, "Liberation Sans", Helvetica, sans-serif; font-size: 9pt; line-height: 1.38; color: #1d2330; margin: 0; }
.paysage { page: paysage; page-break-after: always; }
h1 { font-family: Calibri, Arial, sans-serif; font-size: 21pt; color: #12365e; margin: 0 0 2px; }
.sub { color: #4a5a70; font-size: 10pt; margin-bottom: 6px; }
h2 { font-family: Calibri, Arial, sans-serif; font-size: 15pt; color: #12365e; border-bottom: 1.5pt solid #12365e; padding-bottom: 2px; margin: 16px 0 7px; page-break-after: avoid; }
h3 { font-family: Calibri, Arial, sans-serif; font-size: 11.5pt; color: #12365e; margin: 12px 0 4px; page-break-after: avoid; }
h3 .tag { font-family: Arial, sans-serif; font-size: 7.5pt; font-weight: 700; padding: 1px 6px; border-radius: 8px; margin-left: 6px; vertical-align: 2px; color: #fff; }
.dim { background: #1f4e8c; } .fait { background: #1b7a52; } .fp { background: #6b3fa0; }
p { margin: 0 0 6px; } ul { margin: 0 0 6px 4px; padding-left: 14px; } li { margin: 1px 0; }
table { border-collapse: collapse; width: 100%; margin: 4px 0 10px; } tr { page-break-inside: avoid; }
th, td { border: 0.6pt solid #a9b3c1; padding: 3px 5px; font-size: 8pt; vertical-align: top; text-align: left; }
th { background: #dce6f2; font-weight: 700; }
code { font-family: Consolas, monospace; font-size: 8pt; background: #eef2f7; padding: 0 2px; border-radius: 2px; }
.pk { color: #1f4e8c; font-weight: 700; } .fk { color: #1b7a52; font-weight: 700; } .ms { color: #6b3fa0; font-weight: 700; }
.box { border: 0.8pt solid #a9b3c1; border-left: 3.5pt solid #12365e; background: #f3f6fa; padding: 6px 9px; margin: 6px 0 10px; }
.schema img { width: 100%; display: block; border: 0.6pt solid #c9d2de; }
.legend { font-size: 8pt; color: #4a5a70; margin-top: 4px; }
.keep { break-inside: avoid; page-break-inside: avoid; }
.small { font-size: 7.6pt; color: #4a5a70; }
"""


def role_html(role):
    if role.startswith("PK"):
        return role.replace("PK", '<span class="pk">PK</span>').replace("FK", '<span class="fk">FK</span>')
    if role.startswith("FK"):
        return role.replace("FK", '<span class="fk">FK</span>')
    if role == "mesure":
        return '<span class="ms">mesure</span>'
    return esc(role)


def build_html(S):
    d0, d1 = (f"{x[8:10]}/{x[5:7]}/{x[:4]}" for x in S["dates"])
    reel = "30/09/2024 → 30/04/2025"
    tag = {"Dimension": ("dim", "DIMENSION"), "Fait": ("fait", "FAIT"), "Fait (snapshot)": ("fait", "FAIT · SNAPSHOT")}
    H = [f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Schéma du Data Warehouse — Health Retailers"
         f"</title><style>{CSS}</style></head><body>",
         "<section class='paysage'><h1>Schéma du Data Warehouse — Health Retailers</h1>"
         "<div class='sub'>Modèle BI (version B) : 5 dimensions et 4 tables de faits — descriptif détaillé</div>"
         "<div class='schema'><img src='schema_dwh_diagramme.png' alt='Schéma du Data Warehouse'></div>"
         f"<div class='legend'>Clés primaires (PK), clés étrangères (FK) et mesures. La couleur d'un lien est celle de la "
         f"dimension d'origine. Volumes de la période chargée ({d0} → {d1}) : données réelles du {reel}, puis données "
         "synthétiques. Le détail de chaque table, des relations et des mesures figure dans les pages suivantes.</div></section>",
         "<h2>1. Présentation du modèle</h2>",
         "<p>Le Data Warehouse de Health Retailers est un <b>modèle dimensionnel en constellation</b> : quatre tables de faits "
         "partagent des dimensions communes. Chaque table de faits enregistre un processus métier (une vente, un achat, l'état "
         "du stock, un paiement) au niveau de détail utile au cahier de spécification ; chaque dimension apporte le contexte "
         "d'analyse (quand, quoi, quel client, quel fournisseur, comment).</p>",
         "<table><tr><th style='width:22%'>Élément</th><th>Choix retenu</th></tr>"
         "<tr><td>Dimensions (5)</td><td><code>dim_temps</code>, <code>dim_produit</code>, <code>dim_client</code>, "
         "<code>dim_fournisseur</code>, <code>dim_paiement</code></td></tr>"
         "<tr><td>Tables de faits (4)</td><td><code>fait_ventes</code>, <code>fait_achats</code>, <code>fait_stock_actuel</code>, "
         "<code>fait_paiements</code></td></tr>"
         "<tr><td>Règle de conservation d'une colonne</td><td>Une colonne n'est stockée que si elle est <b>exigée par le cahier</b> "
         "(KPI, filtre ou attribut cité) <b>et</b> qu'elle <b>ne peut pas être recalculée</b> à partir des autres colonnes du Data "
         "Warehouse. Tout le reste est calculé dans Power BI ou reste en zone ETL.</td></tr>"
         "<tr><td>Principe des mesures</td><td>Une mesure est définie une seule fois dans Power BI ; les vues par produit, marque, "
         "client, période ou moyen de paiement sont obtenues par les dimensions et les filtres.</td></tr>"
         f"<tr><td>Période</td><td>Données réelles du {reel} (7 mois), prolongées par des données synthétiques jusqu'au {d1} "
         "(2 ans au total).</td></tr>"
         "<tr><td>Délimitation réel / synthétique</td><td>Par la date, sans colonne dédiée : toute donnée datée jusqu'au "
         "30/04/2025 inclus est réelle ; toute donnée à partir du 01/05/2025 est synthétique.</td></tr>"
         "<tr><td>Données externes</td><td>Météo (Open-Meteo) et indicateurs épidémiques (Réseau Sentinelles) : réservés au jeu "
         "ML de prévision de la demande, <b>hors du Data Warehouse</b>. Le calendrier français (jours fériés) est calculé dans "
         "<code>dim_temps</code>.</td></tr>"
         "<tr><td>Machine Learning</td><td>Les jeux ML sont construits à partir des données nettoyées (zone ETL), pas à partir du "
         "Data Warehouse : retirer une colonne du DW n'enlève rien aux cas ML.</td></tr></table>",
         "<h2>2. Vue d'ensemble des tables</h2>",
         "<table><tr><th>Table</th><th>Type</th><th>Grain</th><th>Clé primaire</th><th>Clés étrangères</th><th>Col.</th>"
         "<th>Lignes</th></tr>"]
    for t, (kind, grain, cols) in META.items():
        pk = ", ".join(c[0] for c in cols if "PK" in c[2].split())
        fk = ", ".join(c[0] for c in cols if "FK:" in c[2]) or "—"
        H.append(f"<tr><td><code>{t}</code></td><td>{kind}</td><td>{esc(grain)}</td><td>{pk}</td><td>{fk}</td>"
                 f"<td>{len(cols)}</td><td>{fr(S[t])}</td></tr>")
    H.append("</table>")
    H.append(f"<p class='small'>fait_ventes : {fr(S['ventes_reel'])} lignes réelles et {fr(S['fait_ventes'] - S['ventes_reel'])} "
             f"synthétiques ; fait_achats : {fr(S['achats_reel'])} lignes réelles et {fr(S['fait_achats'] - S['achats_reel'])} "
             f"synthétiques ; fait_paiements : {fr(S['n_pay'])} paiements ({fr(S['paiements_reel'])} réels et "
             f"{fr(S['n_pay'] - S['paiements_reel'])} synthétiques) sur {fr(S['fait_paiements'])} lignes d'imputation ; fait_stock_actuel : photo au {S['stock_date'][6:]}/{S['stock_date'][4:6]}/{S['stock_date'][:4]}.</p>")
    rel = [("dim_temps", "fait_ventes", "DateKey", "Évolution du CA, des ventes, du panier ; croissance"),
           ("dim_temps", "fait_stock_actuel", "DateKey", "Date du snapshot de stock"),
           ("dim_temps", "fait_achats", "DateKey", "Évolution des achats"),
           ("dim_temps", "fait_paiements", "DateKey", "Évolution des encaissements et des paiements fournisseurs"),
           ("dim_produit", "fait_ventes", "Product_Id", "Ventes et marge par produit, famille, marque"),
           ("dim_produit", "fait_achats", "Product_Id", "Achats par produit, famille, marque ; quel produit vient de quel fournisseur"),
           ("dim_produit", "fait_stock_actuel", "Product_Id", "Stock disponible, ruptures, stock faible par produit, famille, marque"),
           ("dim_client", "fait_ventes", "Company_Id", "Analyse des clients identifiés, clients actifs ; qui a acheté quoi et quand"),
           ("dim_client", "fait_paiements", "Company_Id", "Montant payé par chaque client"),
           ("dim_fournisseur", "fait_achats", "Fournisseur_Id", "Achats par fournisseur"),
           ("dim_fournisseur", "fait_paiements", "Fournisseur_Id", "Montant payé à chaque fournisseur"),
           ("fait_ventes / fait_achats", "fait_paiements", "Document_Id (dimension dégénérée)",
            "Quelle vente ou quelle facture fournisseur chaque paiement règle ; montant réglé par document"),
           ("dim_paiement", "fait_paiements", "PaymentMode_Id", "Répartition des encaissements par moyen de paiement")]
    H += ["<h2>3. Relations</h2><p>Toutes les relations vont d'une dimension (côté 1) vers une table de faits (côté N).</p>",
          "<table><tr><th>Dimension (1)</th><th>Table de faits (N)</th><th>Clé de jointure</th><th>Utilisation</th></tr>"]
    H += [f"<tr><td><code>{a}</code></td><td><code>{b}</code></td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in rel]
    H += ["</table><div class='box'>Les tables de faits ne sont <b>pas reliées entre elles</b> : une analyse croisée (par exemple "
          "ventes et stock d'un même produit) passe par la dimension commune, ici <code>dim_produit</code>. Seule exception : "
          "<code>Document_Id</code>, dimension dégénérée partagée par <code>fait_ventes</code>, <code>fait_achats</code> et "
          "<code>fait_paiements</code>, qui relie un paiement au document qu'il règle. Dans Power BI, on filtre les deux "
          "visuels sur le même <code>Document_Id</code>, ou l'on crée une relation plusieurs-à-plusieurs sur cette colonne "
          "(filtre dans un seul sens, de fait_paiements vers la table de faits du document).</div>",
          "<h2>4. Dictionnaire des données</h2><p class='small'>Légende : <span class='pk'>PK</span> clé primaire · "
          "<span class='fk'>FK</span> clé étrangère · <span class='ms'>mesure</span> valeur additive.</p>"]
    notes = {
        "dim_client": "Types : " + ", ".join(f"{k} ({v})" for k, v in S["types"].most_common()) + ".",
        "dim_fournisseur": (f"{fr(S['dim_fournisseur'] - 1)} fournisseurs, dont {fr(S['inconnus_four'])} cités par des factures "
                            "ou des paiements mais absents de la liste des sociétés (« FOURNISSEUR INCONNU &lt;id&gt; »)."),
        "fait_achats": (f"{fr(S['factures_four'])} factures et avoirs fournisseurs (dont {fr(S['avoirs_four'])} à montant négatif : avoirs et factures de correction), "
                        f"{fr(S['achats_ht'])} € HT d'achats. {fr(S['multi_four'])} produits sont achetés chez plusieurs "
                        "fournisseurs : le lien produit → fournisseur passe donc par cette table, pas par <code>dim_produit</code>. "
                        "Seuls les documents validés sont chargés ; aucune facture fournisseur ne regroupe d'autres documents."),
        "fait_ventes": (f"<b>Exemple réel — Document_Id 15 (ticket VC0013/24) :</b> {S['ex']['n']} lignes, CA HT = "
                        + " + ".join(fr(x, 2) for x in S["ex"]["lignes"]) + f" = {fr(S['ex']['ca'], 2)} € ; coût HT = "
                        f"{fr(S['ex']['cout'], 2)} € ; marge HT = {fr(S['ex']['ca'] - S['ex']['cout'], 2)} €. Il compte pour "
                        f"<b>1 vente</b> ({fr(S['fait_ventes'])} lignes = {fr(S['docs'])} ventes). Lignes chargées : ventes comptoir, "
                        "bons de livraison, factures client et retours validés ; brouillons, lignes de commentaire et factures "
                        "qui regroupent des bons de livraison déjà comptés sont exclus."),
        "fait_stock_actuel": (f"Au snapshot : {fr(S['rupture'])} produits à 0, {fr(S['faible'])} en stock faible, "
                              f"{fr(S['negatif'])} à stock négatif. Rupture et stock faible ne sont <b>pas stockés</b> : mesures "
                              "Power BI à partir de <code>Quantity</code> et <code>QuantiteAlerte</code>, dans la même table (§9). "
                              "Seuils d'alerte les plus fréquents : " + ", ".join(f"{v} ({fr(n)} produits)" for v, n in S["alertes"]) + "."),
        "fait_paiements": (f"Encaissé clients : {fr(S['encaisse'])} € sur {fr(S['n_cli'])} paiements (dont {fr(S['comptoir'])} au "
                           f"comptoir, Company_Id = 2) ; paiements fournisseurs : {fr(S['n_sup'])} ({fr(S['decaisse'])} €), exclus "
                           "du montant encaissé. Chaque paiement porte soit un client, soit un fournisseur (jamais les deux). "
                           f"<b>Imputation :</b> {fr(S['n_pay'] - S['pay_multi'] - S['pay_sans_doc'])} paiements règlent un seul "
                           f"document, {fr(S['pay_multi'])} en règlent plusieurs (montant réparti selon TransactionPayments, puis "
                           "au prorata du total TTC quand une facture regroupe des bons de livraison), "
                           f"{fr(S['pay_sans_doc'])} n'ont pas de document chargé (Document_Id = -1). Le client ou le fournisseur "
                           "du paiement est toujours celui du document réglé. "
                           f"{fr(S['sans_mode'])} paiements clients ({100 * S['sans_mode'] / max(S['n_cli'], 1):.0f} %) n'ont pas "
                           "de moyen renseigné : le logiciel ne le saisit que pendant les premières semaines (sept.-oct. 2024). "
                           "Aucun montant négatif : l'argent rendu lors d'un retour n'est pas un paiement dans la source."),
    }
    for t, (kind, grain, cols) in META.items():
        cls, lab = tag[kind]
        H.append(f"<div class='keep'><h3>{t} <span class='tag {cls}'>{lab}</span></h3>"
                 "<table><tr><th style='width:20%'>Colonne</th><th style='width:14%'>Rôle</th><th>Description</th></tr>")
        H += [f"<tr><td>{esc(c)}</td><td>{role_html(role)}</td><td>{esc(desc)}</td></tr>" for c, _, _, role, desc in cols]
        H.append("</table></div>")
        if t in notes:
            H.append(f"<div class='box'>{notes[t]}</div>")
    meas = [("CA HT", "SUM(CA_HT)", "fait_ventes", "Synthèse, Commercial, Clients"),
            ("Quantité vendue", "SUM(QuantiteVendue)", "fait_ventes", "Commercial"),
            ("Nombre de ventes", "COUNT(DISTINCT Document_Id)", "fait_ventes", "Synthèse, Clients"),
            ("Panier moyen", "CA HT / Nombre de ventes", "fait_ventes", "Synthèse, Commercial, Clients"),
            ("Taux de croissance du CA", "(CA_N − CA_N-1) / CA_N-1 × 100", "fait_ventes + dim_temps", "Synthèse"),
            ("Marge HT", "SUM(CA_HT) − SUM(Cout_HT), lignes sans coût exclues", "fait_ventes", "Commercial"),
            ("Clients actifs", "DISTINCTCOUNT(Company_Id) avec au moins une vente, filtre EstClientIdentifie = true",
             "fait_ventes + dim_client", "Clients"),
            ("Stock disponible", "SUM(Quantity)", "fait_stock_actuel", "Stock"),
            ("Produits en rupture", "COUNT(Product_Id) où Quantity = 0", "fait_stock_actuel", "Stock"),
            ("Produits en stock faible", "COUNT(Product_Id) où 0 < Quantity ≤ QuantiteAlerte", "fait_stock_actuel", "Stock"),
            ("Montant encaissé", "SUM(Amount) où Fournisseur_Id = -1", "fait_paiements", "Paiements"),
            ("Montant payé par client", "Montant encaissé par Company_Id, filtre EstClientIdentifie = true",
             "fait_paiements + dim_client", "Paiements, Clients"),
            ("Montant payé aux fournisseurs", "SUM(Amount) où Fournisseur_Id ≠ -1", "fait_paiements + dim_fournisseur",
             "Paiements, Achats"),
            ("Nombre de paiements", "DISTINCTCOUNT(Payment_Id)", "fait_paiements", "Paiements"),
            ("Montant réglé d'une vente / d'une facture", "SUM(Amount) par Document_Id", "fait_paiements",
             "Paiements, Clients, Achats"),
            ("Achats HT", "SUM(MontantAchat_HT)", "fait_achats", "Achats"),
            ("Quantité achetée", "SUM(QuantiteAchetee)", "fait_achats", "Achats"),
            ("Nombre de factures fournisseurs", "COUNT(DISTINCT Document_Id)", "fait_achats", "Achats"),
            ("Prix d'achat moyen", "Achats HT / Quantité achetée", "fait_achats", "Achats")]
    H += ["<h2>5. Mesures et KPI (Power BI)</h2><table><tr><th style='width:20%'>Mesure / KPI</th><th style='width:32%'>"
          "Formule</th><th style='width:18%'>Tables</th><th>Dashboards</th></tr>"]
    H += [f"<tr><td>{a}</td><td><code>{esc(b)}</code></td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in meas]
    H.append("</table>")
    removed = [("dim_document", "Document_Id est gardé directement dans fait_ventes ; aucun KPI n'analyse le type ou le statut du document."),
               ("dim_geographie, dim_utilisateur", "Analyses géographique et par utilisateur hors périmètre BI."),
               ("fait_stock_hebdo, fait_stock_mouvements", "Pas d'historique de stock dans le BI ; les mouvements restent en source / ETL."),
               ("dim_temps : météo, épidémies, vacances, AnneeMois, NomJour, Saison…", "Météo et épidémies réservées au ML ; vacances non retenues ; le reste se déduit de la date."),
               ("dim_produit : codes, prix, TVA, coût moyen pondéré…", "Aucun KPI ne les utilise ; prix et coût servent dans l'ETL au calcul de CA_HT et Cout_HT."),
               ("dim_client : Code, Solde, Ville, Geo_Id", "Code = clé de jointure de l'ETL ; aucun KPI n'utilise le solde ni la ville."),
               ("dim_paiement : EstEspeces, EstDiffere, ligne « Inconnu (4) »", "Déductibles du moyen de paiement ; la ligne 4 n'est utilisée par aucun paiement."),
               ("fait_ventes : CA_TTC, Marge_HT, CoutUnitaire, Signe, taux de remise, colonnes brutes", "Recalculables ou non utilisées par les KPI ; la marge devient une mesure."),
               ("fait_stock_actuel : EnRupture, StockFaible, ValeurStock_HT, rotation, couverture…", "Rupture et stock faible deviennent des mesures ; les autres ne sont pas des KPI du cahier."),
               ("fait_paiements : UsedAmount, heure, caisse", "UsedAmount = Amount à 99,9 % ; aucun KPI n'utilise les autres colonnes.")]
    added = [("dim_fournisseur", "Nouvelle dimension : savoir quel fournisseur est payé et chez qui un produit est acheté."),
             ("fait_achats", "Nouveau fait : achats par fournisseur, produit et période ; quel produit vient de quel fournisseur."),
             ("fait_paiements : Company_Id", "Montant payé par chaque client (2 = paiements au comptoir)."),
             ("fait_paiements : Fournisseur_Id", "Montant payé à chaque fournisseur."),
             ("fait_paiements : grain « 1 paiement imputé à 1 document », Payment_Id, Document_Id",
              "Le cahier demande quelle vente ou facture chaque paiement règle ; un paiement qui règle plusieurs documents "
              "est réparti sur plusieurs lignes, sans table pont."),
             ("fait_paiements : EstPaiementFournisseur retiré", "Recalculable : paiement fournisseur ⇔ Fournisseur_Id ≠ -1."),
             ("QuantiteAlerte : de dim_produit vers fait_stock_actuel",
              "Le seuil est stocké à côté de la quantité ; le stock faible se calcule dans une seule table.")]
    H += ["<h2>6. Différences avec le modèle précédent (version A)</h2><table><tr><th style='width:36%'>Élément retiré</th>"
          "<th>Raison</th></tr>"]
    H += [f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in removed]
    H += ["</table><h2>7. Ajouts au modèle B (achats, fournisseurs, client et fournisseur des paiements)</h2>"
          "<table><tr><th style='width:36%'>Élément</th><th>Raison</th></tr>"]
    H += [f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in added]
    H += ["</table><h2>8. Règles de chargement et limites</h2><ul>",
          "<li><b>Valeurs inconnues :</b> un client, un fournisseur ou un moyen de paiement absent pointe vers la ligne -1 "
          "« NON RENSEIGNE » de <code>dim_client</code>, <code>dim_fournisseur</code> ou <code>dim_paiement</code> ; le produit "
          "et la date sont toujours renseignés.</li>",
          "<li><b>Documents :</b> seuls les documents validés sont chargés ; retours et avoirs signés négativement ; pas de double "
          "comptage entre factures et bons de livraison.</li>",
          "<li><b>Ventes anonymes :</b> conservées (client comptoir) mais exclues des KPI clients par <code>EstClientIdentifie</code>.</li>",
          "<li><b>Paiements :</b> un encaissement porte le client qui paie (<code>Fournisseur_Id</code> = -1), un paiement "
          "fournisseur porte le fournisseur payé (<code>Company_Id</code> = -1) ; le montant encaissé exclut les paiements "
          "fournisseurs par le filtre <code>Fournisseur_Id = -1</code>.</li>",
          "<li><b>Achats :</b> factures fournisseurs validées ; avoirs fournisseurs signés négativement. Les achats sont HT, "
          "les paiements TTC : ne pas comparer les deux montants directement.</li>",
          "<li><b>Retours et remboursements :</b> les marchandises retournées sont des lignes négatives de "
          "<code>fait_ventes</code> et <code>fait_achats</code> ; l'argent rendu n'est pas enregistré comme paiement dans "
          "la source, il n'apparaît donc pas dans <code>fait_paiements</code> (aucun montant négatif).</li>",
          "<li><b>Moyen de paiement :</b> saisi par le logiciel pendant les premières semaines seulement (sept.-oct. 2024) ; "
          "la répartition par moyen n'est représentative que sur cette période, réelle comme synthétique.</li>",
          "<li><b>Période synthétique :</b> pas d'avoir client ni fournisseur généré (types de documents rares) ; les retours "
          "clients y apparaissent seulement comme lignes négatives de tickets de caisse.</li>",
          "<li><b>Stock :</b> une seule photo du stock, donc Product_Id suffit comme clé ; avec plusieurs photos, la clé "
          "deviendrait (Product_Id, DateKey).</li>",
          "<li><b>Stock :</b> quantité du logiciel conservée, y compris les stocks négatifs (signalés par les contrôles qualité).</li>",
          "<li><b>Données synthétiques :</b> générées par simulation (hypothèses documentées dans la branche data-external) ; "
          "l'apport de la météo et des épidémies se mesure sur la période réelle uniquement.</li>",
          "<li><b>Sources brutes :</b> jamais modifiées ; le nettoyage produit des copies, puis le chargement du Data Warehouse.</li>",
          "</ul></body></html>"]
    return "\n".join(H)


# --------------------------------------------------------------------------- #
# SQL
# --------------------------------------------------------------------------- #
def build_sql():
    L = ["-- Schéma du Data Warehouse Health Retailers – version B (PostgreSQL)",
         "-- Généré par build_schema.py. 5 dimensions, 4 tables de faits.",
         "-- Chargement : \\copy <table> FROM 'dataset/dwh/<table>.csv' WITH (FORMAT csv, HEADER true, NULL '')",
         "-- Ordre : dimensions puis faits (même ordre que ci-dessous).", ""]
    for t in DIMS + FACTS:
        kind, grain, cols = META[t]
        lines = [f'    "{c}" {typ}{" NOT NULL" if "PK" in key.split() else ""}' for c, typ, key, _, _ in cols]
        pk = [c for c, _, key, _, _ in cols if "PK" in key.split()]
        lines.append(f'    CONSTRAINT pk_{t} PRIMARY KEY ({", ".join(chr(34) + p + chr(34) for p in pk)})')
        for c, _, key, _, _ in cols:
            for part in key.split():
                if part.startswith("FK:"):
                    tt, cc = part[3:].split(".")
                    lines.append(f'    CONSTRAINT fk_{t}_{c.lower()} FOREIGN KEY ("{c}") REFERENCES {tt} ("{cc}")')
        L += [f"-- {kind} : {grain}", f"CREATE TABLE {t} (", ",\n".join(lines), ");", ""]
    L += ["-- Chargement des données (psql)"]
    L += [f"\\copy {t} FROM 'dataset/dwh/{t}.csv' WITH (FORMAT csv, HEADER true, NULL '')"
          for t in DIMS + FACTS]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# rendu PNG / PDF avec Chrome ou Edge (headless)
# --------------------------------------------------------------------------- #
def browser():
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(p).exists():
            return p
    for n in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        if shutil.which(n):
            return shutil.which(n)
    return None


def render(svg, w, h):
    exe = browser()
    if not exe:
        print("Chrome / Edge introuvable : PNG et PDF non produits (ouvrir schema_dwh.html et l'imprimer en PDF).")
        return
    tmp = OUT / "_diagramme.html"
    tmp.write_text(f"<html><body style='margin:0'>{svg}</body></html>", encoding="utf-8")
    common = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files"]
    subprocess.run(common + ["--force-device-scale-factor=2", f"--window-size={w},{h}",
                             f"--screenshot={OUT / 'schema_dwh_diagramme.png'}", tmp.as_uri()],
                   check=True, capture_output=True)
    subprocess.run(common + ["--no-pdf-header-footer", f"--print-to-pdf={OUT / 'schema_dwh.pdf'}",
                             (OUT / "schema_dwh.html").as_uri()], check=True, capture_output=True)
    tmp.unlink()


def write_readme(S):
    L = ["# Schéma du Data Warehouse – version B", "",
         "Produit par `build_schema.py` (branche `main`), qui vérifie que la description correspond exactement aux colonnes "
         "des tables de [`dataset-dwh`](../../tree/dataset-dwh).", "", "![Schéma du DWH](schema_dwh_diagramme.png)", "",
         "| Fichier | Contenu |", "|---|---|",
         "| `schema_dwh.pdf` / `schema_dwh.html` | Descriptif détaillé : modèle, tables, relations, dictionnaire de chaque colonne, "
         "mesures Power BI, différences avec la version A, règles de chargement |",
         "| `schema_dwh_diagramme.png` / `.svg` | Diagramme seul |",
         "| `schema_dwh.sql` | `CREATE TABLE` PostgreSQL avec clés primaires et étrangères + commandes de chargement des CSV |", "",
         "Modèle : 4 tables de faits (ventes, achats, stock actuel, paiements) partagent 5 dimensions (temps, produit, client, "
         "fournisseur, paiement). "
         f"Période : {S['dates'][0]} → {S['dates'][1]} (réel jusqu'au 2025-04-30, synthétique ensuite).", "",
         "Retour à la vue d'ensemble : branche [`main`](../../tree/main).", ""]
    (OUT / "README.md").write_text("\n".join(L), encoding="utf-8", newline="\n")


def main():
    data = verify()
    S = stats(data)
    OUT.mkdir(parents=True, exist_ok=True)
    svg, w, h = svg_diagram(S)
    (OUT / "schema_dwh_diagramme.svg").write_text(svg, encoding="utf-8")
    (OUT / "schema_dwh.html").write_text(build_html(S), encoding="utf-8")
    (OUT / "schema_dwh.sql").write_text(build_sql(), encoding="utf-8")
    render(svg, w, h)
    write_readme(S)
    print(f"Schéma écrit dans {OUT}")


if __name__ == "__main__":
    main()

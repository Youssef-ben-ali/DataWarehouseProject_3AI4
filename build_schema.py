#!/usr/bin/env python3
"""
Génère la documentation du schéma du Data Warehouse (dataset/dwh) :
  dataset/schema/schema_dwh.html  – diagramme + matrice des liens + dictionnaire (à imprimer en PDF)
  dataset/schema/schema_dwh.sql   – script CREATE TABLE avec clés primaires et étrangères (PostgreSQL)
Vérifie aussi que la description correspond exactement aux colonnes des CSV.
    python build_schema.py
"""
import csv
import html
from pathlib import Path

HERE = Path(__file__).resolve().parent
DWH = HERE / "dataset" / "dwh"
OUT = HERE / "dataset" / "schema"

# colonne | type | clé | description      (clé : PK, FK:table.colonne, PK FK:table.colonne)
META = {
"dim_temps": ("Dimension", "1 ligne = 1 jour (01/09/2024 → 31/12/2025)", """
DateKey|INT|PK|Date au format AAAAMMJJ (clé de jointure de tous les faits)
Date|DATE||Date du jour
Annee|INT||Année
Trimestre|INT||Trimestre (1 à 4)
Mois|INT||Mois (1 à 12)
NomMois|TEXTE||Nom du mois
AnneeMois|TEXTE||Année-mois (AAAA-MM)
SemaineISO|INT||Numéro de semaine ISO
AnneeSemaine|TEXTE||Année-semaine ISO (AAAA-Sxx)
DebutSemaine|DATE||Lundi de la semaine
Jour|INT||Jour du mois
JourSemaine|INT||Jour de la semaine (1 = lundi … 7 = dimanche)
NomJour|TEXTE||Nom du jour
EstWeekend|BOOL||Samedi ou dimanche
EstFerie|BOOL||Jour férié en France
NomFerie|TEXTE||Nom du jour férié
VacancesZoneA|BOOL||Vacances scolaires zone A
VacancesZoneB|BOOL||Vacances scolaires zone B
VacancesZoneC|BOOL||Vacances scolaires zone C (Paris, Toulouse)
EstVacances|BOOL||Vacances dans au moins une zone
Saison|TEXTE||Hiver / Printemps / Été / Automne
DansPeriodeDonnees|BOOL||Jour compris dans la période des transactions (30/09/2024 – 30/04/2025)
Meteo_TempMoy|DEC||EXTERNE Open-Meteo (Paris) – température moyenne du jour (°C)
Meteo_TempMin|DEC||EXTERNE Open-Meteo – température minimale (°C)
Meteo_TempMax|DEC||EXTERNE Open-Meteo – température maximale (°C)
Meteo_Pluie_mm|DEC||EXTERNE Open-Meteo – précipitations du jour (mm)
Meteo_Ensoleillement_h|DEC||EXTERNE Open-Meteo – durée d'ensoleillement (heures)
Meteo_Rayonnement_MJm2|DEC||EXTERNE Open-Meteo – rayonnement solaire (MJ/m²)
Senti_Grippe_Inc100|DEC||EXTERNE Sentinelles – syndromes grippaux, incidence /100 000 hab. (valeur de la semaine)
Senti_IRA_Inc100|DEC||EXTERNE Sentinelles – infections respiratoires aiguës /100 000 hab. (semaine)
Senti_Gastro_Inc100|DEC||EXTERNE Sentinelles – diarrhée aiguë /100 000 hab. (semaine)
Senti_Varicelle_Inc100|DEC||EXTERNE Sentinelles – varicelle /100 000 hab. (semaine)
"""),
"dim_geographie": ("Dimension", "1 ligne = 1 ville (-1 = non renseigné)", """
Geo_Id|INT|PK|Identifiant de la ville
Ville|TEXTE||Ville
Departement|TEXTE||Numéro de département (déduit de la ville)
Region|TEXTE||Région
Pays|TEXTE||Pays
"""),
"dim_produit": ("Dimension", "1 ligne = 1 produit du référentiel interne", """
Product_Id|INT|PK|Identifiant produit du logiciel
ProductStock_Id|INT||Identifiant de la fiche stock du produit
Libellé|TEXTE||Nom du produit
Code|TEXTE||Code de l'export Produits (GUID ou ART…)
CodeBarre|TEXTE||Code-barres EAN-13
Famille|TEXTE||Famille / catégorie du produit
FamilyGroup|TEXTE||Famille regroupée (petites familles → AUTRES)
Marque|TEXTE||Marque
MarqueSource|TEXTE||Origine de la marque (Produits / déduite du libellé / absent)
Prix d'achat HT|DEC||Prix d'achat hors taxe
Prix de vente HT|DEC||Prix de vente hors taxe
Tva|DEC||Taux de TVA (%)
Prix de vente TTC|DEC||Prix de vente toutes taxes
CoutMoyenPondere|DEC||Dernier coût moyen pondéré (CUMP) connu
Quantité d'Alerte|DEC||Seuil d'alerte de stock
AlerteSource|TEXTE||Origine du seuil (Produits / paramètre par défaut 5)
IsDeletedInSoftware|BOOL||Produit supprimé dans le logiciel
ProductIdSource|TEXTE||Méthode de rapprochement avec l'export Produits
"""),
"dim_client": ("Dimension", "1 ligne = 1 client (-1 = non renseigné, 2 = client comptoir anonyme)", """
Company_Id|INT|PK|Identifiant du client (celui des transactions)
Code|TEXTE||Code client (CL…)
Nom|TEXTE||Nom du client
TypeClient|TEXTE||PARTICULIER / B2B / COMPTOIR_ANONYME / NON RENSEIGNE
Ville|TEXTE||Ville
Geo_Id|INT|FK:dim_geographie.Geo_Id|Ville du client
Solde|DEC||Solde du compte client (créance)
EstClientIdentifie|BOOL||Faux pour le client comptoir anonyme
CompanyType|TEXTE||Type de société dans CompaniesList
"""),
"dim_fournisseur": ("Dimension", "1 ligne = 1 fournisseur (-1 = non renseigné)", """
Company_Id|INT|PK|Identifiant du fournisseur
Code|TEXTE||Code fournisseur (FOU…)
Nom|TEXTE||Nom du fournisseur
Ville|TEXTE||Ville
Geo_Id|INT|FK:dim_geographie.Geo_Id|Ville du fournisseur
Solde|DEC||Solde du compte fournisseur (dette)
"""),
"dim_paiement": ("Dimension", "1 ligne = 1 moyen de paiement (-1 = non renseigné)", """
PaymentMode_Id|INT|PK|Identifiant du moyen de paiement
PaymentModeName|TEXTE||Espèces, Carte bancaire, Chèque, Crédit, Jetons…
EstEspeces|BOOL||Paiement en espèces
EstDiffere|BOOL||Paiement différé (crédit)
"""),
"dim_utilisateur": ("Dimension", "1 ligne = 1 utilisateur (vendeur / caissier)", """
User_Id|INT|PK|Identifiant de l'utilisateur
FullName|TEXTE||Nom
IsStaff|BOOL||Faux pour les comptes administrateur / système
"""),
"dim_document": ("Dimension", "1 ligne = 1 document (-1 = aucun document)", """
Document_Id|INT|PK|Identifiant du document
DocumentNumber|TEXTE||Numéro de pièce (VC0001/24, BL…, FV…)
DateKey|INT|FK:dim_temps.DateKey|Date du document
DocumentType_Id|INT||Code du type de document
TypeDocument|TEXTE||Vente comptoir, Bon de livraison, Facture client, Facture fournisseur…
Flow|TEXTE||SALE / SALE_RETURN / PURCHASE / PURCHASE_RETURN / QUOTE / ORDER
Canal|TEXTE||COMPTOIR / FACTURE / ACHAT / DEVIS / COMMANDE
State|INT||Statut d'origine (1 = validé, 0 = brouillon)
IsValidated|BOOL||Document validé
EstFactureDeBL|BOOL||Facture qui regroupe des BL déjà comptés (exclue des ventes)
PaymentMode_Id|INT|FK:dim_paiement.PaymentMode_Id|Moyen de paiement du document
CreatedBy|INT|FK:dim_utilisateur.User_Id|Utilisateur qui a créé le document
Heure|INT||Heure de création
TotalNetHt|DEC||Total net hors taxe du document
TotalTtc|DEC||Total toutes taxes du document
"""),
"fait_ventes": ("Fait", "1 ligne = 1 produit vendu (ou retourné) dans 1 document validé à 1 date", """
Id|INT|PK|Identifiant de la ligne de document
Document_Id|INT|FK:dim_document.Document_Id|Document de vente
DocumentNumber|TEXTE||Numéro de pièce
DateKey|INT|FK:dim_temps.DateKey|Date de la vente
Date|DATE||Date de la vente
Heure|INT||Heure de la vente
Product_Id|INT|FK:dim_produit.Product_Id|Produit vendu
Company_Id|INT|FK:dim_client.Company_Id|Client
PaymentMode_Id|INT|FK:dim_paiement.PaymentMode_Id|Moyen de paiement
DocumentType_Id|INT||Type de document (6 comptoir, 5 BL, 1 facture, 4/7 retours)
Canal|TEXTE||COMPTOIR / FACTURE
CreatedBy|INT|FK:dim_utilisateur.User_Id|Vendeur
Signe|INT||+1 vente, -1 retour
Quantity|DEC||Quantité (valeur d'origine, non signée)
PrixHt|DEC||Prix unitaire HT avant remise
DiscountPourcentage|DEC||Remise en %
Tva|DEC||Taux de TVA (%)
PrixTotalHt|DEC||Total HT de la ligne après remise (d'origine)
TotalTva|DEC||TVA de la ligne (d'origine)
PrixTotalTtc|DEC||Total TTC de la ligne (d'origine)
QuantiteVendue|DEC||MESURE – quantité signée
Remise_HT|DEC||MESURE – montant de remise HT signé
CA_HT|DEC||MESURE – chiffre d'affaires HT signé
TVA_Montant|DEC||MESURE – TVA signée
CA_TTC|DEC||MESURE – chiffre d'affaires TTC signé
CoutUnitaire|DEC||Coût unitaire (CUMP au moment de la vente)
SourceCout|TEXTE||Origine du coût (CUMP_MOUVEMENT / PRIX_ACHAT_PRODUIT / ABSENT)
Cout_HT|DEC||MESURE – coût de revient signé
Marge_HT|DEC||MESURE – marge HT signée (CA_HT − Cout_HT)
VenteSousCout|BOOL||Ligne vendue sous le coût
"""),
"fait_achats": ("Fait", "1 ligne = 1 produit acheté sur 1 document fournisseur validé", """
Id|INT|PK|Identifiant de la ligne de document
Document_Id|INT|FK:dim_document.Document_Id|Facture / avoir fournisseur
DocumentNumber|TEXTE||Numéro de pièce
DateKey|INT|FK:dim_temps.DateKey|Date de l'achat
Date|DATE||Date de l'achat
Product_Id|INT|FK:dim_produit.Product_Id|Produit acheté
Company_Id|INT|FK:dim_fournisseur.Company_Id|Fournisseur
DocumentType_Id|INT||Type de document (20 facture, 23 avoir)
Signe|INT||+1 achat, -1 avoir
Quantity|DEC||Quantité (d'origine)
PrixHt|DEC||Prix unitaire HT
DiscountPourcentage|DEC||Remise en %
PrixTotalHt|DEC||Total HT de la ligne (d'origine)
QuantiteAchetee|DEC||MESURE – quantité signée
MontantAchat_HT|DEC||MESURE – montant HT signé
MontantAchat_TTC|DEC||MESURE – montant TTC signé
EstUniteGratuite|BOOL||Unité offerte par le fournisseur (remise 100 %)
"""),
"fait_paiements": ("Fait", "1 ligne = 1 paiement", """
Id|INT|PK|Identifiant du paiement
DateKey|INT|FK:dim_temps.DateKey|Date du paiement
Date|DATE||Date du paiement
Heure|INT||Heure du paiement
Company_Id|INT||Société d'origine (client OU fournisseur)
Client_Id|INT|FK:dim_client.Company_Id|Client (rempli si paiement client)
Fournisseur_Id|INT|FK:dim_fournisseur.Company_Id|Fournisseur (rempli si paiement fournisseur)
PaymentMode_Id|INT|FK:dim_paiement.PaymentMode_Id|Moyen de paiement
Amount|DEC||MESURE – montant payé
UsedAmount|DEC||Montant affecté aux pièces
IsPurchase|BOOL||Paiement d'achat selon le libellé
EstPaiementFournisseur|BOOL||Paiement fait à un fournisseur
DocumentNumber|TEXTE||Numéro de la pièce payée
Document_Id|INT|FK:dim_document.Document_Id|Document payé (-1 si introuvable)
CaisseId|TEXTE||Caisse qui a encaissé
CaisseName|TEXTE||Nom de la caisse
BankAccountId|TEXTE||Compte bancaire
Extra_gA|DEC||Espèces données par le client
Extra_rA|DEC||Monnaie rendue
"""),
"fait_stock_mouvements": ("Fait", "1 ligne = 1 mouvement de stock d'un produit", """
Id|INT|PK|Identifiant du mouvement
DateKey|INT|FK:dim_temps.DateKey|Date du mouvement
Date|DATE||Date du mouvement
Heure|INT||Heure du mouvement
Product_Id|INT|FK:dim_produit.Product_Id|Produit
ProductStock_Id|INT||Fiche stock du produit
DocumentId|INT||Document d'origine (valeur brute)
Document_Id|INT|FK:dim_document.Document_Id|Document lié (-1 = stock initial / ajustement)
Action|TEXTE||VALIDATION / CORRECTION / MANUAL / INITIAL
SourceKind|TEXTE||COUNTER_SALE, DELIVERY_NOTE, SUPPLIER_INVOICE, INITIAL_STOCK…
Direction|TEXTE||IN / OUT / NONE
Quantity|DEC||MESURE – quantité (+ entrée, − sortie)
CurrentBalance|DEC||Stock du produit après le mouvement
Extra_cump|DEC||Coût moyen pondéré au moment du mouvement
ValeurMouvement_HT|DEC||MESURE – Quantity × CUMP
User_Id|INT|FK:dim_utilisateur.User_Id|Utilisateur
"""),
"fait_stock_hebdo": ("Fait", "1 ligne = 1 produit × 1 semaine (clé composée)", """
Product_Id|INT|PK FK:dim_produit.Product_Id|Produit
SemaineDebut|DATE|PK|Lundi de la semaine
DateKey|INT|FK:dim_temps.DateKey|Lundi de la semaine (AAAAMMJJ)
AnneeSemaine|TEXTE||Année-semaine ISO
StockFinSemaine|DEC||MESURE – stock en fin de semaine
QteEntree|DEC||MESURE – quantités entrées
QteSortie|DEC||MESURE – quantités sorties
QteVendue|DEC||MESURE – quantités vendues
CA_HT|DEC||MESURE – CA HT de la semaine
EnRupture|BOOL||Stock ≤ 0 en fin de semaine
SemaineComplete|BOOL||Faux pour la dernière semaine (partielle)
"""),
"fait_stock_actuel": ("Fait", "1 ligne = 1 produit (photo au 30/04/2025)", """
Product_Id|INT|PK FK:dim_produit.Product_Id|Produit
DateKey|INT|FK:dim_temps.DateKey|Date de la photo (20250430)
Quantity|DEC||MESURE – stock disponible
Quantité d'Alerte|DEC||Seuil d'alerte
EnRupture|BOOL||Stock = 0
StockNegatif|BOOL||Stock < 0
StockFaible|BOOL||0 < stock ≤ seuil d'alerte
QteVendue_Periode|DEC||MESURE – quantité vendue sur la période
CA_HT_Periode|DEC||MESURE – CA HT sur la période
StockMoyenHebdo|DEC||Stock moyen de fin de semaine
Rotation|DEC||MESURE – quantité vendue / stock moyen
CouvertureJours|DEC||Nombre de jours de vente couverts par le stock
DateDerniereVente|DATE||Date de la dernière vente
JoursDepuisDerniereVente|INT||Jours depuis la dernière vente
ValeurStock_HT|DEC||MESURE – stock × CUMP
ClasseABC|TEXTE||A / B / C selon le CA (Pareto)
EstProduitActif|BOOL||Vendu au moins une fois sur la période
"""),
}
for k, (kind, grain, txt) in META.items():
    rows = []
    for line in txt.strip().splitlines():
        c, t, key, d = line.split("|")
        rows.append(dict(col=c, type=t, key=key, desc=d))
    META[k] = dict(kind=kind, grain=grain, cols=rows)

# colonnes mises en avant dans le diagramme (en plus des PK / FK)
MAIN = {
    "dim_temps": ["Date", "Annee", "Mois", "SemaineISO", "NomJour", "EstFerie", "VacancesZoneC", "Saison"],
    "dim_document": ["DocumentNumber", "TypeDocument", "Flow", "Canal", "IsValidated"],
    "dim_utilisateur": ["FullName", "IsStaff"], "dim_paiement": ["PaymentModeName", "EstEspeces"],
    "dim_produit": ["Libellé", "Famille", "Marque", "CodeBarre", "Prix de vente HT", "Prix d'achat HT"],
    "dim_client": ["Nom", "TypeClient", "Ville", "Solde"], "dim_fournisseur": ["Nom", "Ville", "Solde"],
    "dim_geographie": ["Ville", "Departement", "Region"],
    "fait_ventes": ["QuantiteVendue", "CA_HT", "CA_TTC", "Remise_HT", "Cout_HT", "Marge_HT"],
    "fait_achats": ["QuantiteAchetee", "MontantAchat_HT", "EstUniteGratuite"],
    "fait_paiements": ["Amount", "CaisseName", "EstPaiementFournisseur"],
    "fait_stock_mouvements": ["Quantity", "CurrentBalance", "SourceKind", "ValeurMouvement_HT"],
    "fait_stock_hebdo": ["StockFinSemaine", "QteVendue", "EnRupture"],
    "fait_stock_actuel": ["Quantity", "EnRupture", "StockFaible", "Rotation", "ClasseABC"],
}
TOP = ["dim_utilisateur", "dim_document", "dim_temps", "dim_paiement"]
FACTS = ["fait_stock_actuel", "fait_stock_hebdo", "fait_stock_mouvements", "fait_achats", "fait_ventes", "fait_paiements"]
BOTTOM = ["dim_produit", "dim_fournisseur", "dim_client", "dim_geographie"]
COLOR = {"fait_ventes": "#2563eb", "fait_achats": "#d97706", "fait_paiements": "#7c3aed",
         "fait_stock_mouvements": "#059669", "fait_stock_hebdo": "#0d9488", "fait_stock_actuel": "#b45309"}
SNOW = "#64748b"


def verify():
    rows_count = {}
    for t, m in META.items():
        with (DWH / f"{t}.csv").open(encoding="utf-8") as fh:
            r = csv.reader(fh)
            header = next(r)
            rows_count[t] = sum(1 for _ in r)
        cols = [c["col"] for c in m["cols"]]
        assert header == cols, f"{t}: colonnes différentes\nCSV : {header}\nMETA: {cols}"
    return rows_count


def fks(t):
    out = []
    for c in META[t]["cols"]:
        for part in c["key"].split():
            if part.startswith("FK:"):
                tt, cc = part[3:].split(".")
                out.append((c["col"], tt, cc))
    return out


def pks(t):
    return [c["col"] for c in META[t]["cols"] if "PK" in c["key"].split()]


# --------------------------------------------------------------------------- #
# diagramme SVG
# --------------------------------------------------------------------------- #
W_BOX, ROW, HEAD = 250, 19, 30


def diag_rows(t):
    m = META[t]
    keyed = [c for c in m["cols"] if c["key"]]
    main = [c for c in m["cols"] if c["col"] in MAIN.get(t, []) and not c["key"]]
    rest = len(m["cols"]) - len(keyed) - len(main)
    return keyed, main, rest


def box_h(t):
    keyed, main, rest = diag_rows(t)
    return HEAD + ROW * (len(keyed) + len(main) + (1 if rest else 0)) + 8


def esc(s):
    return html.escape(str(s))


def svg_diagram(counts):
    gap = 34
    width = len(FACTS) * W_BOX + (len(FACTS) - 1) * gap + 80
    pos = {}

    def place(row, y, spread=None):
        n = len(row)
        total = n * W_BOX + (n - 1) * (spread or gap)
        x0 = (width - total) / 2
        hmax = max(box_h(t) for t in row)          # même hauteur dans une rangée : aucun trait ne passe sous une boîte
        for i, t in enumerate(row):
            pos[t] = [x0 + i * (W_BOX + (spread or gap)), y, hmax]

    place(TOP, 70, 120)
    top_h = max(pos[t][2] for t in TOP)
    fy = 70 + top_h + 150
    place(FACTS, fy)
    fact_h = max(pos[t][2] for t in FACTS)
    by = fy + fact_h + 150
    place(BOTTOM, by, 120)
    # align bottom boxes' tops
    height = by + max(pos[t][2] for t in BOTTOM) + 90

    # attach points per side
    edges = []
    for t in FACTS + TOP + BOTTOM:
        for col, tt, cc in fks(t):
            edges.append((t, col, tt))
    side_slots = {}

    def slot(t, side, key):
        side_slots.setdefault((t, side), []).append(key)

    for i, (a, col, b) in enumerate(edges):
        if a in FACTS:
            sa = "top" if b in TOP else "bottom"
            sb = "bottom" if b in TOP else "top"
        else:   # dimension → dimension (flocon)
            sa = sb = "top" if a in TOP else "bottom"
        edges[i] = (a, col, b, sa, sb)
        slot(a, sa, i)
        slot(b, sb, i)

    def point(t, side, i):
        x, y, h = pos[t]
        keys = side_slots[(t, side)]
        k = keys.index(i)
        px = x + W_BOX * (k + 1) / (len(keys) + 1)
        return px, (y if side == "top" else y + h)

    # order slots left→right by the other end's x to limit crossings
    for (t, side), keys in side_slots.items():
        def other_x(i):
            a, _, b, _, _ = edges[i]
            o = b if a == t else a
            return pos[o][0]
        keys.sort(key=other_x)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           f'font-family="Segoe UI, Arial, sans-serif">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           '<defs><marker id="one" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="10" markerHeight="10" orient="auto">'
           '<path d="M5,0 L5,10" stroke="#334155" stroke-width="2"/></marker></defs>']
    for label, y in (("DIMENSIONS", 46), ("FAITS (tables de faits)", fy - 52), ("DIMENSIONS", by - 24)):
        out.append(f'<text x="40" y="{y}" font-size="15" font-weight="700" fill="#475569" letter-spacing="1">{label}</text>')

    # edges
    for i, (a, col, b, sa, sb) in enumerate(edges):
        x1, y1 = point(a, sa, i)
        x2, y2 = point(b, sb, i)
        color = COLOR.get(a, SNOW)
        if a in FACTS:
            dy = 70 if sa == "bottom" else -70
            d = f"M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + dy:.1f} {x2:.1f},{y2 - dy:.1f} {x2:.1f},{y2:.1f}"
            dash = ""
        else:
            lift = -55 if sa == "top" else 55
            d = f"M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + lift:.1f} {x2:.1f},{y2 + lift:.1f} {x2:.1f},{y2:.1f}"
            dash = ' stroke-dasharray="6 4"'
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8" opacity="0.85"{dash}/>')
        # cardinalités
        ny = y1 + (12 if sa == "bottom" else -6)
        oy = y2 + (14 if sb == "bottom" else -6)
        out.append(f'<text x="{x1 + 4:.1f}" y="{ny:.1f}" font-size="11" font-weight="700" fill="{color}">N</text>')
        out.append(f'<text x="{x2 + 4:.1f}" y="{oy:.1f}" font-size="11" font-weight="700" fill="{color}">1</text>')

    # boxes
    for t, (x, y, h) in pos.items():
        fact = META[t]["kind"] == "Fait"
        head = COLOR[t] if fact else "#334155"
        out.append(f'<rect x="{x}" y="{y}" width="{W_BOX}" height="{h}" rx="6" fill="#ffffff" stroke="{head}" stroke-width="1.6"/>')
        out.append(f'<path d="M{x},{y + 6} a6,6 0 0 1 6,-6 h{W_BOX - 12} a6,6 0 0 1 6,6 v{HEAD - 6} h-{W_BOX} z" fill="{head}"/>')
        out.append(f'<text x="{x + 10}" y="{y + 20}" font-size="14" font-weight="700" fill="#fff">{esc(t)}</text>')
        out.append(f'<text x="{x + W_BOX - 8}" y="{y + 20}" font-size="10.5" fill="#e2e8f0" text-anchor="end">'
                   f'{counts[t]:,} lignes</text>')
        keyed, main, rest = diag_rows(t)
        yy = y + HEAD + 15
        for c in keyed + main:
            k = c["key"].split()
            tag, col = "", "#0f172a"
            if "PK" in k:
                tag, col = "PK", "#b91c1c"
            fk = [p for p in k if p.startswith("FK:")]
            if fk:
                tag = "PK FK" if "PK" in k else "FK"
                col = "#b91c1c" if "PK" in k else "#1d4ed8"
            weight = "700" if c["key"] else "400"
            out.append(f'<text x="{x + 10}" y="{yy}" font-size="11.5" font-weight="{weight}" fill="{col}">{esc(c["col"])}</text>')
            if tag:
                out.append(f'<text x="{x + W_BOX - 8}" y="{yy}" font-size="9.5" font-weight="700" fill="{col}" '
                           f'text-anchor="end">{tag}{" → " + fk[0][3:].split(".")[0] if fk else ""}</text>')
            elif c["desc"].startswith("MESURE"):
                out.append(f'<text x="{x + W_BOX - 8}" y="{yy}" font-size="9.5" fill="#059669" text-anchor="end">mesure</text>')
            yy += ROW
        if rest:
            out.append(f'<text x="{x + 10}" y="{yy}" font-size="10.5" font-style="italic" fill="#64748b">'
                       f'+ {rest} autres colonnes (voir dictionnaire)</text>')
    lx = 40
    ly = height - 34
    legend = [("#b91c1c", "PK = clé primaire"), ("#1d4ed8", "FK → table = clé étrangère vers la dimension"),
              ("#059669", "mesure = valeur additive")]
    for c, txt in legend:
        out.append(f'<text x="{lx}" y="{ly}" font-size="12" font-weight="700" fill="{c}">■</text>')
        out.append(f'<text x="{lx + 16}" y="{ly}" font-size="12" fill="#334155">{esc(txt)}</text>')
        lx += 20 + len(txt) * 6.6
    out.append(f'<text x="{lx}" y="{ly}" font-size="12" fill="#334155">· trait plein = fait → dimension (N–1) · '
               f'pointillé = dimension → dimension (flocon)</text>')
    out.append("</svg>")
    return "\n".join(out), width, height


# --------------------------------------------------------------------------- #
# HTML + SQL
# --------------------------------------------------------------------------- #
def build_html(svg, w, h, counts):
    dims = [t for t in META if META[t]["kind"] == "Dimension"]
    facts = [t for t in META if META[t]["kind"] == "Fait"]
    # matrice
    mat = ['<table class="mat"><tr><th>Fait \\ Dimension</th>' + "".join(f"<th>{d}</th>" for d in dims) + "</tr>"]
    for f in facts + ["dim_document", "dim_client", "dim_fournisseur"]:
        links = {}
        for col, tt, cc in fks(f):
            links.setdefault(tt, []).append(col)
        cells = "".join(f'<td class="{"on" if d in links else ""}">{"<br>".join(links.get(d, []))}</td>' for d in dims)
        mat.append(f"<tr><th>{f}</th>{cells}</tr>")
    mat.append("</table>")
    # liste des relations
    rel = ['<table class="rel"><tr><th>Table (clé étrangère)</th><th>Colonne FK</th><th>→ Table référencée</th>'
           '<th>Clé primaire</th><th>Cardinalité</th></tr>']
    for t in facts + dims:
        for col, tt, cc in fks(t):
            rel.append(f"<tr><td>{t}</td><td><code>{esc(col)}</code></td><td>{tt}</td><td><code>{esc(cc)}</code></td>"
                       f"<td>N – 1</td></tr>")
    rel.append("</table>")
    # dictionnaire
    cards = []
    for t in dims + facts:
        m = META[t]
        pk = ", ".join(pks(t))
        fk = "<br>".join(f"<code>{esc(c)}</code> → {tt}.{cc}" for c, tt, cc in fks(t)) or "—"
        rows = "".join(
            f'<tr><td><code>{esc(c["col"])}</code></td><td>{c["type"]}</td>'
            f'<td class="k">{esc(c["key"].replace("FK:", "FK → ").replace(" FK", " · FK"))}</td><td>{esc(c["desc"])}</td></tr>'
            for c in m["cols"])
        cards.append(f'''<section class="card"><h3><span class="badge {'f' if m['kind'] == 'Fait' else 'd'}">{m['kind']}</span> {t}
<small>{counts[t]:,} lignes · {len(m['cols'])} colonnes</small></h3>
<p class="meta"><b>Granularité :</b> {esc(m['grain'])}<br><b>Clé primaire :</b> <code>{esc(pk)}</code><br><b>Clés étrangères :</b> {fk}</p>
<table class="dict"><tr><th>Colonne</th><th>Type</th><th>Clé</th><th>Contenu</th></tr>{rows}</table></section>''')
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Schéma DWH – Health Retailers</title>
<style>
@page diagram {{ size: A3 landscape; margin: 8mm; }}
@page {{ size: A4; margin: 12mm; }}
body {{ font-family: "Segoe UI", Arial, sans-serif; color: #0f172a; font-size: 10pt; margin: 0; }}
.diagram {{ page: diagram; page-break-after: always; }}
.diagram svg {{ width: 100%; height: auto; max-height: 270mm; }}
h1 {{ font-size: 20pt; margin: 0 0 4px; color: #1e3a8a; }}
h2 {{ font-size: 14pt; color: #1e3a8a; border-bottom: 2px solid #1e3a8a; padding-bottom: 2px; margin: 18px 0 8px; }}
h3 {{ font-size: 12pt; margin: 0 0 4px; }} h3 small {{ font-weight: 400; color: #64748b; font-size: 9pt; margin-left: 6px; }}
.sub {{ color: #475569; margin: 0 0 6px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 8.8pt; }}
th, td {{ border: 1px solid #cbd5e1; padding: 3px 5px; text-align: left; vertical-align: top; }}
th {{ background: #f1f5f9; }}
.mat td {{ text-align: center; font-size: 8pt; }} .mat td.on {{ background: #dbeafe; font-weight: 600; color: #1e40af; }}
.mat th:first-child, .mat tr th {{ white-space: nowrap; }}
code {{ font-family: Consolas, monospace; font-size: 8.6pt; }}
.card {{ border: 1px solid #cbd5e1; border-radius: 5px; padding: 8px 10px; margin: 10px 0; page-break-inside: avoid; }}
.meta {{ margin: 2px 0 6px; font-size: 9pt; }}
.badge {{ font-size: 8pt; padding: 1px 6px; border-radius: 8px; color: #fff; vertical-align: middle; }}
.badge.d {{ background: #334155; }} .badge.f {{ background: #2563eb; }}
td.k {{ white-space: nowrap; color: #1d4ed8; font-weight: 600; }}
tr {{ page-break-inside: avoid; }}
</style></head><body>
<section class="diagram">
<h1>Schéma du Data Warehouse – Health Retailers</h1>
<p class="sub">Modèle en constellation : 6 tables de faits partagent 8 dimensions. Chaque trait relie une clé étrangère (N) à la clé primaire (1) d'une dimension.</p>
{svg}
</section>
<h2>1. Matrice des liens (quelle table est reliée à quelle dimension)</h2>
<p class="sub">Chaque case indique la colonne clé étrangère qui fait le lien. Case vide = pas de lien.</p>
{''.join(mat)}
<h2>2. Liste des relations (clé étrangère → clé primaire)</h2>
{''.join(rel)}
<p class="sub">Membres « inconnu » : <code>-1</code> dans dim_client, dim_fournisseur, dim_document, dim_paiement et dim_geographie, pour que chaque clé étrangère retrouve toujours sa dimension. Dans fait_paiements, une seule des deux clés <code>Client_Id</code> / <code>Fournisseur_Id</code> est remplie.</p>
<h2>3. Dictionnaire des tables</h2>
<p class="sub">Types : INT entier, DEC décimal, TEXTE chaîne, DATE date ISO, BOOL true/false. MESURE = colonne additive à agréger dans les tableaux de bord.</p>
{''.join(cards)}
</body></html>"""


SQLTYPE = {"INT": "INTEGER", "DEC": "NUMERIC(18,4)", "TEXTE": "VARCHAR(255)", "DATE": "DATE", "BOOL": "BOOLEAN"}


def build_sql():
    order = ["dim_temps", "dim_geographie", "dim_paiement", "dim_utilisateur", "dim_produit", "dim_client",
             "dim_fournisseur", "dim_document", "fait_ventes", "fait_achats", "fait_paiements",
             "fait_stock_mouvements", "fait_stock_hebdo", "fait_stock_actuel"]
    L = ["-- Schéma du Data Warehouse Health Retailers (PostgreSQL)",
         "-- Généré par build_schema.py. Charger ensuite chaque CSV de dataset/dwh avec :",
         "--   \\copy <table> FROM 'dataset/dwh/<table>.csv' WITH (FORMAT csv, HEADER true, NULL '')",
         "-- Ordre de chargement : dimensions puis faits (même ordre que ci-dessous).", ""]
    for t in order:
        m = META[t]
        lines = [f'    "{c["col"]}" {SQLTYPE[c["type"]]}{" NOT NULL" if "PK" in c["key"].split() else ""}' for c in m["cols"]]
        lines.append(f'    CONSTRAINT pk_{t} PRIMARY KEY ({", ".join(chr(34) + p + chr(34) for p in pks(t))})')
        for col, tt, cc in fks(t):
            lines.append(f'    CONSTRAINT fk_{t}_{col.lower()} FOREIGN KEY ("{col}") REFERENCES {tt} ("{cc}")')
        L += [f"-- {m['kind']} : {m['grain']}", f"CREATE TABLE {t} (", ",\n".join(lines), ");", ""]
    return "\n".join(L)


def main():
    counts = verify()
    OUT.mkdir(parents=True, exist_ok=True)
    svg, w, h = svg_diagram(counts)
    (OUT / "schema_dwh_diagramme.svg").write_text(svg, encoding="utf-8")
    (OUT / "schema_dwh.html").write_text(build_html(svg, w, h, counts), encoding="utf-8")
    (OUT / "schema_dwh.sql").write_text(build_sql(), encoding="utf-8")
    (OUT / "_diagramme.html").write_text(f'<html><body style="margin:0">{svg}</body></html>', encoding="utf-8")
    print(f"diagramme {w}x{h}px ; fichiers écrits dans {OUT}")


if __name__ == "__main__":
    main()

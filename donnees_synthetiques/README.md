# Données externes synthétiques — suite de l'export (01/05/2025 → 29/09/2026)

> **Ces données sont générées par simulation. Elles ne sont pas réelles.**
> Elles prolongent l'export réel du logiciel (30/09/2024 → 30/04/2025, 7 mois) pour disposer de
> **2 ans d'historique** au total. Elles sont rangées ici, dans `externe/`, et ne sont jamais mélangées
> aux fichiers réels de `fichiers/`. Dans l'entrepôt, la délimitation se fait **par la date** : réel jusqu'au
> 30/04/2025 inclus, synthétique à partir du 01/05/2025 (aucune colonne dédiée).

Produit par `generate_external_data.py` (bibliothèque standard Python), graine `42`, calendrier `FR` :

```bash
python generate_external_data.py                    # régénère exactement les mêmes fichiers
python generate_external_data.py --calendar TN      # variante avec le calendrier tunisien
```

## Fichiers

Même nom, mêmes colonnes et **même format** que le fichier réel correspondant (séparateur, virgule décimale,
formats de date, `VRAI/FAUX`, encodage, guillemets de `DomainEvents.csv`). Le script de nettoyage
`clean_data.py` s'applique donc tel quel.

| Fichier | Lignes | Contenu |
|---|---|---|
| `Documents.csv` | 32,906 | ventes comptoir, bons de livraison, factures client, factures fournisseur |
| `documentItemm.csv` | 82,574 | lignes de ces documents (y compris les lignes vides de mise en page des factures) |
| `Transactions.csv` | 32,906 | une transaction par document |
| `TransactionPayments.csv`, `PaymentsList.csv` | 28,871 | paiements |
| `TresoreriePayments.csv`, `CaisseOperations.csv` | — | affectation des paiements aux caisses / comptes bancaires |
| `StockMovements.csv` | 94,762 | mouvements de stock (ventes, achats, corrections, modifications manuelles) |
| `DomainEvents.csv` | 62,756 | événements de trésorerie : paiements, ouvertures / fermetures de caisse, écarts |
| `ProductStocks.csv` | 6,842 | **état du stock au 29/09/2026** (remplace l'état réel pour la fin de période) |
| `comparaison_mensuelle.csv` | — | indicateurs mensuels réels et générés côte à côte (contrôle de vraisemblance) |
| `parametres_generation.json` | — | tous les paramètres appris ou supposés |

**Non générés** (inchangés, à prendre dans `fichiers/`) : les données de référence (`Produits`, `ProductBrands`,
`Barcodes`, `ProductPrices`, `Clients`, `Fournisseurs`, `CompaniesList`, `users`, `DocumentTypes`, taxes,
paramètres), ainsi que `ItemTaxes`, `DocumentsReports`, `Events`, `RelatedDocuments`, `InventaireItems` et
`Payment.csv` (doublons ou faible valeur analytique, voir le guide des données).

## Continuité avec l'export réel

- **Identifiants** : chaque table repart après le plus grand identifiant réel (documents > 18713,
  lignes > 47484, paiements > 16869, mouvements > 55859, événements > 71384),
  avec la même proportion d'identifiants sautés (documents supprimés) que dans l'export.
- **Numéros** : `VC10418/24`, `BL1070/24`, `FV0315/24`… continuent la série
  (le logiciel n'a pas remis le compteur à zéro en janvier 2025) ; les factures fournisseur continuent la
  numérotation propre à chaque fournisseur.
- **Stock** : chaque produit repart de son solde réel au 30/04/2025 ; le prix d'achat et le CUMP aussi.
- **Soldes clients / fournisseurs** (`Extra.cosld`) et **soldes des caisses** : repris de la fin de l'export.
- **Références** : produits, clients, fournisseurs, caissiers, caisses et comptes bancaires existent tous
  dans l'export réel.

## Ce qui est appris sur l'export réel

Les 24 factures client qui refacturent des bons de livraison (RelatedDocuments) sont exclues de l'apprentissage :
leur chiffre d'affaires est déjà compté sur les bons de livraison et elles sont exclues des ventes du Data Warehouse.

Volume de ventes par jour de semaine et par mois · heures d'activité de chaque type de document · nombre
de lignes, quantités et remises (par produit) · popularité de chaque produit sur chaque canal · clients de
chaque canal · liste de prix · caissier selon le jour et l'heure · taux de brouillons, de documents corrigés,
d'impayés · nombre et délai des paiements · mode de paiement · fournisseur de chaque produit, fréquence de
commande, remises et timbre de chaque fournisseur · écarts de caisse à la fermeture · modifications manuelles
de stock. Les calculs des montants reproduisent ceux du logiciel (remise ligne, remise document dans les
colonnes `Sum…`, TVA, taxe de 1 % sur certaines factures fournisseur, timbre de 1 sur `FinalPrice`).

## Hypothèses ajoutées (à citer comme telles, pas comme des découvertes)

| Hypothèse | Valeur |
|---|---|
| Calendrier | français (dimanches, 1er janv., lundi de Pâques, 1er et 8 mai, Ascension, 14 juil., 15 août, 1er et 11 nov., 25 déc. ; le lundi de Pentecôte reste ouvert) |
| Fuseau horaire | Paris (heure d'été), comme le serveur de l'export : `CreatedDate` en UTC, paiements et mouvements en heure locale |
| Croissance de la fréquentation | +6% par an |
| Mois absents de l'export (mai → sept.) | indices {5: 1.0, 6: 1.04, 7: 1.05, 8: 0.88, 9: 1.0} (août plus calme) |
| Mars | l'export montre une baisse en mars 2025 (Ramadan) : remplacée par la moyenne février / avril |
| Saisonnalité produits | 227 produits solaires et 5 anti-moustiques repérés par mot-clé : pic en juillet |
| Épidémies | 67 produits ORL / immunité : ventes × (1 + 0.35 × écart de l'incidence grippe Sentinelles à sa moyenne)  |
| Cycle de vie | tendance propre à chaque produit ; 150 produits du catalogue lancés, 186 arrêtés en cours de période |
| Prix | hausses le 01/09/2025 (15 % des produits, +2 à 5 %), le 01/01/2026 (60 %, +2 à 7 %), le 01/07/2026 (15 %, +1 à 4 %) |
| Achats | une facture fournisseur est créée quand des produits du fournisseur passent sous 10 jours de demande ; quantité = 25 jours de demande (un stock négatif n'est pas rattrapé) |

⚠️ Les relations météo / épidémies / saison que vos modèles trouveront sur la période générée viennent en partie
de ces hypothèses. Pour évaluer honnêtement un modèle, entraînez-le et testez-le aussi **sur la seule période réelle**.

## Utilisation avec le pipeline

- `python clean_data.py --synthetique` nettoie ces 10 fichiers avec les fichiers de référence réels (produits,
  clients, utilisateurs, noms des caisses issus du `DomainEvents.csv` réel) et écrit `cleaned/synthetique/`, sans
  jamais mélanger réel et synthétique dans un même dossier.
- `build_dataset.py` empile ensuite les deux périodes dans le Data Warehouse ; la délimitation se fait par la date.
- Contrôles passés sur les fichiers générés : clés étrangères (lignes → documents → transactions → paiements →
  trésorerie → caisse ; produits, sociétés et utilisateurs existants), `TotalTtc` = somme des lignes,
  `FinalPrice` = `TotalTtc` + timbre, montant payé = somme des paiements, identifiants et numéros uniques et
  jamais utilisés dans l'export, soldes de stock continus depuis le dernier solde réel jusqu'à `ProductStocks.csv`.

## Limites

- Pas de nouveaux produits, clients ou fournisseurs créés (le catalogue reste celui de l'export).
- Les types de documents rares (avoirs, retours, proformas, commandes) ne sont pas générés : les retours clients
  n'apparaissent que comme lignes négatives des ventes (à la fréquence réelle, surtout des échanges sur un ticket
  de plusieurs lignes), et il n'y a pas d'avoir fournisseur après le 30/04/2025.
- Un ticket ou une facture de total nul ou négatif ne crée pas de paiement, comme dans l'export (aucun paiement
  négatif) : l'argent rendu à un client n'est pas enregistré comme paiement.
- Moyen de paiement : reproduit tel qu'il est saisi dans l'export depuis novembre 2024, c'est-à-dire presque jamais
  (< 1 % des paiements clients) ; seules les premières semaines de l'export (septembre-octobre 2024) le renseignent.
- Pas de dépôts / retraits bancaires ni d'ajustements de solde bancaire (rares dans l'export).
- Les paiements saisis puis supprimés (≈ 1.1%, statut 2 en caisse) sont reproduits ; les mises à jour
  de paiement (`PaymentUpdated`, 11 cas réels) ne le sont pas.
- 308 produits finissent avec un stock négatif (vente sans réception : 132 dans l'export au
  30/04/2025) — c'est un défaut de qualité réel du logiciel, conservé.
- Les mois de mai à septembre n'ont jamais été observés : leur niveau repose sur les indices supposés.

## Comparaison mensuelle (réel puis généré)

| mois | source | nb_ventes_comptoir | ca_ttc_comptoir | panier_moyen_ttc | nb_bons_livraison | nb_factures_client | nb_factures_fournisseur | achats_ttc |
|---|---|---|---|---|---|---|---|---|
| 2024-09 | original | 92 | 6198.21 | 67.37 | 0 | 0 | 5 | 4708.95 |
| 2024-10 | original | 1449 | 104700.79 | 72.26 | 167 | 15 | 153 | 168950.58 |
| 2024-11 | original | 1592 | 122130.64 | 76.72 | 180 | 19 | 130 | 162266.55 |
| 2024-12 | original | 1301 | 87682.05 | 67.4 | 165 | 31 | 146 | 187260.78 |
| 2025-01 | original | 1578 | 101915.14 | 64.59 | 164 | 45 | 109 | 149016.78 |
| 2025-02 | original | 1378 | 93269.61 | 67.68 | 134 | 39 | 115 | 157464.12 |
| 2025-03 | original | 1126 | 80214.69 | 71.24 | 88 | 46 | 111 | 145947.32 |
| 2025-04 | original | 1778 | 118560.42 | 66.68 | 133 | 52 | 111 | 159333.37 |
| 2025-05 | synthetique | 1427 | 103157.62 | 72.29 | 134 | 50 | 120 | 149125.17 |
| 2025-06 | synthetique | 1692 | 121092.73 | 71.57 | 128 | 43 | 125 | 117439.53 |
| 2025-07 | synthetique | 1664 | 129061.2 | 77.56 | 116 | 49 | 146 | 161282.1 |
| 2025-08 | synthetique | 1367 | 101410.08 | 74.18 | 131 | 39 | 139 | 127277.23 |
| 2025-09 | synthetique | 1594 | 112748.9 | 70.73 | 182 | 41 | 139 | 149481.52 |
| 2025-10 | synthetique | 1493 | 109524.81 | 73.36 | 147 | 51 | 139 | 171216.13 |
| 2025-11 | synthetique | 1490 | 100321.53 | 67.33 | 125 | 39 | 117 | 135821.12 |
| 2025-12 | synthetique | 1511 | 107441.22 | 71.11 | 138 | 42 | 151 | 158072.06 |
| 2026-01 | synthetique | 1480 | 103883.12 | 70.19 | 158 | 51 | 123 | 125323.62 |
| 2026-02 | synthetique | 1461 | 104283.89 | 71.38 | 136 | 45 | 127 | 130913.95 |
| 2026-03 | synthetique | 1867 | 134255.27 | 71.91 | 122 | 52 | 131 | 124370.36 |
| 2026-04 | synthetique | 2058 | 141667.42 | 68.84 | 140 | 48 | 131 | 155009.49 |
| 2026-05 | synthetique | 1440 | 108165.88 | 75.12 | 150 | 46 | 115 | 198551.85 |
| 2026-06 | synthetique | 1783 | 130704.43 | 73.31 | 152 | 57 | 139 | 158144.16 |
| 2026-07 | synthetique | 1933 | 152025.98 | 78.65 | 134 | 50 | 155 | 188223.2 |
| 2026-08 | synthetique | 1445 | 110236.22 | 76.29 | 151 | 51 | 132 | 177476.18 |
| 2026-09 | synthetique | 1690 | 123357.6 | 72.99 | 154 | 43 | 126 | 163733.36 |

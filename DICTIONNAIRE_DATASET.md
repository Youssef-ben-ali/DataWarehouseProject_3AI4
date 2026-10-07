# Jeu de données Health Retailers – conforme au cahier de spécification

Construit par `build_dataset.py` à partir des fichiers nettoyés (`cleaned/`). Les fichiers originaux et nettoyés ne sont pas modifiés.

## Organisation

```
dataset/
├── dwh/   modèle en étoile : dimensions (dim_*) et faits (fait_*)
├── ml/    un jeu de données par objectif ML du §11 (X préfixées X_, cible Y_)
├── controles_qualite.csv   contrôles du §7.1
└── README.md
```

## Conventions

- CSV UTF-8, séparateur virgule, décimale `.`, dates ISO `AAAA-MM-JJ`, booléens `true/false`.
- Clé de date `DateKey` = `AAAAMMJJ` (jointure avec `dim_temps`). Clé produit `Product_Id`, clé client / fournisseur `Company_Id`, moyen de paiement `PaymentMode_Id`, document `Document_Id`.
- Les colonnes recopiées d'une source gardent leur **nom d'origine** (`Quantity`, `PrixHt`, `Libellé`…). Les mesures calculées portent le vocabulaire du cahier (`CA_HT`, `Marge_HT`, `PanierMoyen`, `EnRupture`…).
- Dans `ml/` : variables explicatives préfixées `X_`, cibles préfixées `Y_`, colonnes `Regle_*` = règles métier d'interprétation (ni X ni Y). Les identifiants servent seulement à relier les résultats.

## Besoins du cahier → tables

| Décideur | Questions | Mesure / formule | Tables |
|---|---|---|---|
| Direction générale | Quel est le CA ? Évolution ? Période la plus forte ? | CA = Σ CA_HT ; croissance = (CA_N − CA_N-1)/CA_N-1 × 100 ; nb documents = COUNT(DISTINCT Document_Id) | fait_ventes × dim_temps |
| Responsable commercial | Produits / marques les plus vendus, panier moyen, évolution | Σ QuantiteVendue, Σ CA_HT par Product_Id / Marque ; panier moyen = Σ CA_HT / nb documents | fait_ventes × dim_produit × dim_temps |
| Responsable relation client | CA par client, fréquence, panier client, clients actifs | Σ CA_HT par Company_Id ; COUNT(DISTINCT Document_Id) ; CA client / nb documents client | fait_ventes × dim_client ; ml_11_4_segmentation_clients |
| Responsable approvisionnement / stock | Stock faible, ruptures, faible rotation, demande à prévoir | Quantity, EnRupture, StockFaible, Rotation ; taux de rupture = Σ EnRupture / nb produits × 100 | fait_stock_actuel, fait_stock_hebdo, fait_stock_mouvements ; ml_11_1 |
| Responsable financier / caisse | Montants encaissés, répartition par moyen, évolution | Σ Amount (IsPurchase = false) par PaymentMode_Id et par DateKey ; nb transactions = COUNT(Id) | fait_paiements × dim_paiement × dim_temps ; ml_11_3 |

Filtres minimum du §10 (période, produit, marque) : `dim_temps`, `dim_produit.Product_Id`, `dim_produit.Marque`.

## Schéma en étoile

```
dim_temps ─┐        ┌─ dim_produit ── (Famille, Marque)
dim_client ┼─ fait_ventes ─┼─ dim_document ── dim_paiement
dim_geographie ─ dim_client / dim_fournisseur   dim_utilisateur (CreatedBy)
fait_achats      : dim_temps, dim_produit, dim_fournisseur, dim_document
fait_stock_*     : dim_temps, dim_produit
fait_paiements   : dim_temps, dim_client, dim_paiement, dim_document
```

## Tables

### `dwh/dim_temps.csv`

Dimension Temps : jour, semaine, mois, trimestre, année, saison, jours fériés et vacances scolaires.

- **Granularité :** 1 ligne = 1 jour (01/09/2024 → 31/12/2025, pour couvrir aussi l'horizon de prévision)
- **Lignes :** 487
- **Sources :** Calculé (calendrier français : jours fériés par calcul de Pâques, vacances scolaires officielles 2024-2025 zones A/B/C) ; météo journalière Open-Meteo (Paris) ; incidences hebdomadaires du réseau Sentinelles (France)
- **Cahier :** §8 Données externes – Calendrier français, Météo ; §11.1 indicateurs épidémiques ; §9 Dimension Temps
- **Colonnes :** `DateKey`, `Date`, `Annee`, `Trimestre`, `Mois`, `NomMois`, `AnneeMois`, `SemaineISO`, `AnneeSemaine`, `DebutSemaine`, `Jour`, `JourSemaine`, `NomJour`, `EstWeekend`, `EstFerie`, `NomFerie`, `VacancesZoneA`, `VacancesZoneB`, `VacancesZoneC`, `EstVacances`, `Saison`, `DansPeriodeDonnees`, `Meteo_TempMoy`, `Meteo_TempMin`, `Meteo_TempMax`, `Meteo_Pluie_mm`, `Meteo_Ensoleillement_h`, `Meteo_Rayonnement_MJm2`, `Senti_Grippe_Inc100`, `Senti_IRA_Inc100`, `Senti_Gastro_Inc100`, `Senti_Varicelle_Inc100`
- `DansPeriodeDonnees` = true entre le 30/09/2024 et le 30/04/2025 (période des transactions).
- Zone C = Paris / Toulouse, zone B = Marseille / Lille / Nantes / Strasbourg…, zone A = Lyon / Bordeaux / Grenoble.
- Météo (`Meteo_*`, valeur du jour, Paris, source archive-api.open-meteo.com) : température moyenne / min / max (°C), pluie (mm), ensoleillement (heures), rayonnement solaire (MJ/m²). Jointure : DateKey.
- Épidémies (`Senti_*_Inc100`, taux d'incidence pour 100 000 habitants, France entière, réseau Sentinelles – Inserm / Sorbonne Université, sentiweb.fr) : Grippe = syndromes grippaux (indicateur 3), IRA = infections respiratoires aiguës (25), Gastro = diarrhée aiguë (6), Varicelle (7). Valeur HEBDOMADAIRE répétée sur les 7 jours de la semaine ISO : jointure par semaine (AnneeSemaine), ne pas sommer sur les jours.
- Fichiers bruts téléchargés conservés dans `externe/`.

### `dwh/dim_geographie.csv`

Dimension Géographie : ville, département, région (clients et fournisseurs).

- **Granularité :** 1 ligne = 1 ville
- **Lignes :** 12
- **Sources :** Clients, Fournisseurs (Ville)
- **Cahier :** §9 Dimension Géographie
- **Colonnes :** `Geo_Id`, `Ville`, `Departement`, `Region`, `Pays`
- Département et région déduits de la ville ; le code postal n'est pas fiable (10 codes incohérents).
- Les ventes comptoir (client anonyme) n'ont pas de géographie : le magasin est unique.

### `dwh/dim_produit.csv`

Dimension Produit : identifiant, libellé, marque, famille (catégorie), prix, code-barres, seuil d'alerte.

- **Granularité :** 1 ligne = 1 produit du référentiel interne (ProductStocks), clé Product_Id
- **Lignes :** 6,842
- **Sources :** ProductStocks, Produits, Events (libellés), ProductPrices (liste 1), Barcodes, ProductBrands, StockMovements (CUMP)
- **Cahier :** §9 Dimension Produit ; §6.2 Analyse des ventes
- **Colonnes :** `Product_Id`, `ProductStock_Id`, `Libellé`, `Code`, `CodeBarre`, `Famille`, `FamilyGroup`, `Marque`, `MarqueSource`, `Prix d'achat HT`, `Prix de vente HT`, `Tva`, `Prix de vente TTC`, `CoutMoyenPondere`, `Quantité d'Alerte`, `AlerteSource`, `IsDeletedInSoftware`, `ProductIdSource`
- Libellé : {'Events': 159, 'absent': 2182, 'documentItemm': 35, 'Produits': 4466}.
- Marque : {'absent': 3054, 'deduite_du_libelle': 1119, 'Produits': 2669} – quand la marque manque, elle est déduite si le libellé commence par un nom de ProductBrands (colonne `MarqueSource`).
- Famille = catégorie ; `NON RENSEIGNE` quand le produit n'a pas pu être rapproché de l'export Produits.
- Seuil d'alerte manquant → paramètre logiciel `ProductsDefaultAlertQuantity = 5` (colonne `AlerteSource`).

### `dwh/dim_client.csv`

Dimension Client : identifiant, nom, type (particulier / B2B / comptoir anonyme), ville, solde (créance).

- **Granularité :** 1 ligne = 1 client (clé Company_Id, celle des transactions)
- **Lignes :** 82
- **Sources :** CompaniesList, Clients, Transactions
- **Cahier :** §6.3 Analyse des clients ; §9 Dimension Client
- **Colonnes :** `Company_Id`, `Code`, `Nom`, `TypeClient`, `Ville`, `Geo_Id`, `Solde`, `EstClientIdentifie`, `CompanyType`
- Company_Id 2 = client comptoir anonyme (la majorité des ventes comptoir).
- Le nom vient du fichier Clients quand le code y existe (les noms de CompaniesList ont été anonymisés différemment).
- 46 clients du fichier Clients n'existent pas dans CompaniesList : ils n'ont aucune vente reliable et ne sont pas dans la dimension.

### `dwh/dim_fournisseur.csv`

Dimension Fournisseur : identifiant, nom, ville, solde (dette).

- **Granularité :** 1 ligne = 1 fournisseur (clé Company_Id)
- **Lignes :** 116
- **Sources :** CompaniesList, Fournisseurs
- **Cahier :** §9 Dimension Fournisseur ; §7 Fournisseurs (approvisionnement)
- **Colonnes :** `Company_Id`, `Code`, `Nom`, `Ville`, `Geo_Id`, `Solde`
- 33 fournisseurs du fichier Fournisseurs n'ont pas de Company_Id : aucun achat reliable, non repris.

### `dwh/dim_paiement.csv`

Dimension Paiement : moyen / type de paiement.

- **Granularité :** 1 ligne = 1 moyen de paiement
- **Lignes :** 7
- **Sources :** PaymentsList (PaymentMode_Id / PaymentMethodName)
- **Cahier :** §6.5 Paiements ; §9 Dimension Paiement
- **Colonnes :** `PaymentMode_Id`, `PaymentModeName`, `EstEspeces`, `EstDiffere`
- -1 = document sans moyen de paiement renseigné (ex. bons de livraison, factures non réglées).

### `dwh/dim_document.csv`

Dimension Document : numéro, type, statut (validé / brouillon), canal (comptoir / facturé / achat).

- **Granularité :** 1 ligne = 1 document
- **Lignes :** 12,543
- **Sources :** Documents, DocumentTypes, RelatedDocuments
- **Cahier :** §9 Dimension Document (type / statut)
- **Colonnes :** `Document_Id`, `DocumentNumber`, `DateKey`, `DocumentType_Id`, `TypeDocument`, `Flow`, `Canal`, `State`, `IsValidated`, `EstFactureDeBL`, `PaymentMode_Id`, `CreatedBy`, `Heure`, `TotalNetHt`, `TotalTtc`
- `EstFactureDeBL` = facture client qui regroupe des bons de livraison déjà comptés (exclue des ventes).
- `Heure` = heure de création du document (DocumentDate n'a pas d'heure).

### `dwh/dim_utilisateur.csv`

Dimension Utilisateur (vendeur / caissier).

- **Granularité :** 1 ligne = 1 utilisateur
- **Lignes :** 7
- **Sources :** users_csv (sans mots de passe)
- **Cahier :** §11.2 et §11.3 (variable explicative « utilisateur »)
- **Colonnes :** `User_Id`, `FullName`, `IsStaff`
- Les données d'authentification sont exclues (§4.2 du cahier).

### `dwh/fait_ventes.csv`

Fait Ventes : ligne de produit vendue (ou retournée) dans un document validé à une date donnée.

- **Granularité :** 1 ligne = 1 produit × 1 document de vente × 1 date (granularité candidate du §9.1, confirmée)
- **Lignes :** 25,743
- **Sources :** documentItemm, Documents, Transactions, StockMovements (CUMP), Produits
- **Cahier :** §6.1, §6.2, §6.3 ; §9 Mesures ventes (quantité, CA, nb documents, panier moyen)
- **Colonnes :** `Id`, `Document_Id`, `DocumentNumber`, `DateKey`, `Date`, `Heure`, `Product_Id`, `Company_Id`, `PaymentMode_Id`, `DocumentType_Id`, `Canal`, `CreatedBy`, `Signe`, `Quantity`, `PrixHt`, `DiscountPourcentage`, `Tva`, `PrixTotalHt`, `TotalTva`, `PrixTotalTtc`, `QuantiteVendue`, `Remise_HT`, `CA_HT`, `TVA_Montant`, `CA_TTC`, `CoutUnitaire`, `SourceCout`, `Cout_HT`, `Marge_HT`, `VenteSousCout`
- Ventes = vente comptoir (6), bon de livraison (5), facture client (1) ; retours = avoir (4) et bon de retour (7) avec `Signe = -1` : les mesures `QuantiteVendue`, `CA_HT`, `CA_TTC`, `Remise_HT`, `Cout_HT`, `Marge_HT` sont signées.
- Les colonnes d'origine (`Quantity`, `PrixHt`, `PrixTotalHt`…) sont recopiées telles quelles (non signées).
- CA du cahier = Σ(Quantité × Prix) = Σ `CA_HT` (net de remise). Nb documents = COUNT(DISTINCT Document_Id). Panier moyen = Σ CA_HT / Nb documents.
- Exclusions : ligne de commentaire sans produit ni montant : 1,024 lignes; facture client regroupant des BL déjà comptés : 4,003 lignes; document brouillon (State = 0) : 776 lignes.
- Coût unitaire : {'CUMP_MOUVEMENT': 25683, 'PRIX_ACHAT_PRODUIT': 58, 'ABSENT': 2} – CUMP = coût moyen pondéré au moment de la vente (StockMovements.Extra_cump), sinon prix d'achat HT du produit.

### `dwh/fait_achats.csv`

Fait Achats : ligne de produit achetée sur une facture fournisseur validée (avoirs fournisseur en négatif).

- **Granularité :** 1 ligne = 1 produit × 1 document d'achat
- **Lignes :** 6,980
- **Sources :** documentItemm, Documents, Transactions
- **Cahier :** §7 Fournisseurs – approvisionnement ; §9 Dimension Fournisseur
- **Colonnes :** `Id`, `Document_Id`, `DocumentNumber`, `DateKey`, `Date`, `Product_Id`, `Company_Id`, `DocumentType_Id`, `Signe`, `Quantity`, `PrixHt`, `DiscountPourcentage`, `PrixTotalHt`, `QuantiteAchetee`, `MontantAchat_HT`, `MontantAchat_TTC`, `EstUniteGratuite`
- Permet de relier les fournisseurs aux produits et au stock (approvisionnement).
- `EstUniteGratuite` = ligne avec remise 100 % : unités offertes par le fournisseur (≈ 700 lignes). C'est là que se trouvent presque toutes les « remises > 50 % » citées au §11.2 du cahier.
- Lignes de commentaire (sans produit ni montant) exclues.

### `dwh/fait_stock_mouvements.csv`

Fait Mouvements de stock : chaque entrée / sortie de stock avec le solde après mouvement.

- **Granularité :** 1 ligne = 1 mouvement de stock d'un produit
- **Lignes :** 49,609
- **Sources :** StockMovements
- **Cahier :** §6.4 Gestion des stocks ; §9 Mesures stock (mouvements)
- **Colonnes :** `Id`, `DateKey`, `Date`, `Heure`, `Product_Id`, `ProductStock_Id`, `DocumentId`, `Document_Id`, `Action`, `SourceKind`, `Direction`, `Quantity`, `CurrentBalance`, `Extra_cump`, `ValeurMouvement_HT`, `User_Id`
- `DocumentId` = valeur d'origine ; `Document_Id` = clé étrangère vers dim_document (-1 = stock initial, ajustement manuel ou document absent de Documents).
- `SourceKind` = origine (COUNTER_SALE, DELIVERY_NOTE, SUPPLIER_INVOICE, INITIAL_STOCK, MANUAL_ADJUSTMENT…).
- `CurrentBalance` = stock du produit après le mouvement → permet de reconstituer l'historique (fait_stock_hebdo).

### `dwh/fait_stock_hebdo.csv`

Fait Stock hebdomadaire : stock de fin de semaine, entrées, sorties, quantités vendues, rupture.

- **Granularité :** 1 ligne = 1 produit × 1 semaine (lundi), à partir de son premier mouvement
- **Lignes :** 190,626
- **Sources :** StockMovements (CurrentBalance), fait_ventes
- **Cahier :** §6.4 (rupture, faible rotation, demande) ; §9.1 granularité stock « par produit et par date »
- **Colonnes :** `Product_Id`, `SemaineDebut`, `DateKey`, `AnneeSemaine`, `StockFinSemaine`, `QteEntree`, `QteSortie`, `QteVendue`, `CA_HT`, `EnRupture`, `SemaineComplete`
- L'historique par produit et par date existe (solde après chaque mouvement) : la granularité hebdomadaire a été retenue (≈ 31 semaines).
- La dernière semaine (28/04 → 30/04/2025) est incomplète : `SemaineComplete = false`.

### `dwh/fait_stock_actuel.csv`

Fait Stock actuel : stock disponible, rupture, stock faible, rotation, couverture, classe ABC à la date de fin.

- **Granularité :** 1 ligne = 1 produit (photo au 30/04/2025)
- **Lignes :** 6,842
- **Sources :** ProductStocks, fait_ventes, fait_stock_hebdo, Produits
- **Cahier :** §6.4 (stock faible, rupture, faible rotation) ; §12 Taux de rupture
- **Colonnes :** `Product_Id`, `DateKey`, `Quantity`, `Quantité d'Alerte`, `EnRupture`, `StockNegatif`, `StockFaible`, `QteVendue_Periode`, `CA_HT_Periode`, `StockMoyenHebdo`, `Rotation`, `CouvertureJours`, `DateDerniereVente`, `JoursDepuisDerniereVente`, `ValeurStock_HT`, `ClasseABC`, `EstProduitActif`
- Taux de rupture (§12) = COUNT(EnRupture) / COUNT(produits suivis) × 100. `EstProduitActif` = vendu au moins une fois sur la période : à utiliser comme « produit suivi », sinon les produits jamais vendus (souvent à stock 0) gonflent le taux.
- Rotation = quantité vendue sur la période / stock moyen hebdomadaire (formule « à définir » du cahier : proposition à valider). Aucun seuil de faible rotation n'est imposé : utiliser `Rotation` et `JoursDepuisDerniereVente`.
- `StockFaible` utilise le seuil d'alerte du logiciel (Quantité d'Alerte), pas un seuil inventé.
- Classe ABC = Pareto sur le CA (A = 80 % du CA, B = 15 %, C = 5 %).
- Inventaire : InventaireItems ne contient aucune quantité comptée (FinalRealQuantity vide) → pas de mesure d'écart d'inventaire possible.

### `dwh/fait_paiements.csv`

Fait Paiements : montant encaissé (ou payé aux fournisseurs), moyen, date, caisse.

- **Granularité :** 1 ligne = 1 paiement
- **Lignes :** 10,899
- **Sources :** PaymentsList + Payment (fusionnés), TresoreriePayments
- **Cahier :** §6.5 Paiements ; §9 Mesures paiements (montant payé, nb transactions)
- **Colonnes :** `Id`, `DateKey`, `Date`, `Heure`, `Company_Id`, `Client_Id`, `Fournisseur_Id`, `PaymentMode_Id`, `Amount`, `UsedAmount`, `IsPurchase`, `EstPaiementFournisseur`, `DocumentNumber`, `Document_Id`, `CaisseId`, `CaisseName`, `BankAccountId`, `Extra_gA`, `Extra_rA`
- Montant encaissé = Σ Amount où EstPaiementFournisseur = false ; répartition par PaymentMode_Id ; évolution par DateKey.
- `Company_Id` (origine) désigne un client OU un fournisseur : il est réparti en deux clés étrangères, `Client_Id` (→ dim_client) et `Fournisseur_Id` (→ dim_fournisseur), selon le type de la société dans CompaniesList (à défaut, selon `IsPurchase`). Une seule des deux est remplie.
- `Document_Id` retrouvé grâce au numéro de pièce cité dans la description du paiement ; -1 si introuvable.

### `ml/ml_11_1_prevision_demande_famille_hebdo.csv`

ML 11.1 – Prévision de la demande : quantité vendue par famille et par semaine.

- **Granularité :** 1 ligne = 1 FamilyGroup × 1 semaine (toutes les semaines, 0 si aucune vente)
- **Lignes :** 217
- **Sources :** fait_ventes, dim_produit, dim_temps
- **Cahier :** §11.1 Prévision de la demande (régression / séries temporelles)
- **Colonnes :** `FamilyGroup`, `SemaineDebut`, `AnneeSemaine`, `Y_Quantite`, `Y_QuantiteSemaineSuivante`, `X_Qte_Lag1`, `X_Qte_Lag2`, `X_Qte_Lag4`, `X_Qte_MoyenneMobile4`, `X_CA_HT`, `X_PrixMoyen_HT`, `X_TauxRemisePct`, `X_PartComptoirPct`, `X_NbDocuments`, `X_NbJoursFeries`, `X_NbJoursVacancesZoneC`, `X_NbJoursVacancesToutesZones`, `X_NbJoursOuvres`, `X_Mois`, `X_SemaineISO`, `X_Saison`, `X_Meteo_TempMoyenne`, `X_Meteo_TempMin`, `X_Meteo_TempMax`, `X_Meteo_Pluie_mm`, `X_Meteo_NbJoursPluie`, `X_Meteo_Ensoleillement_h`, `X_Meteo_Rayonnement_MJm2`, `X_Grippe_Inc100`, `X_IRA_Inc100`, `X_Gastro_Inc100`, `X_Varicelle_Inc100`, `SemaineComplete`
- Cible Y : `Y_Quantite` (semaine courante) ou `Y_QuantiteSemaineSuivante` (prévision t+1). Les variables explicatives sont préfixées `X_` (§13 : séparer clairement X et Y).
- X : historique (lags 1/2/4, moyenne mobile 4 semaines, toujours calculés sur le passé), prix moyen, remise, canal comptoir / facturé, jours fériés, vacances scolaires, jours ouvrés, mois, saison.
- Externes intégrés : météo de la semaine (Paris, Open-Meteo) – `X_Meteo_TempMoyenne`, `X_Meteo_TempMin`, `X_Meteo_TempMax`, `X_Meteo_Pluie_mm` (cumul), `X_Meteo_NbJoursPluie` (≥ 1 mm), `X_Meteo_Ensoleillement_h` (cumul), `X_Meteo_Rayonnement_MJm2` (cumul) ; épidémies de la semaine (réseau Sentinelles, France, pour 100 000 hab.) – `X_Grippe_Inc100`, `X_IRA_Inc100`, `X_Gastro_Inc100`, `X_Varicelle_Inc100`. Jointure par semaine ISO.
- Pour prévoir `Y_QuantiteSemaineSuivante`, les X de la semaine courante sont connus au moment de la prévision (Sentinelles publie avec ~1 semaine de délai : en production, décaler les épidémies d'une semaine).
- Externes non intégrés : Google Trends, taux EUR/TND.
- Ne pas utiliser la dernière semaine (`SemaineComplete = false`) pour l'entraînement ; ~30 semaines d'historique : valider sur les dernières semaines (baseline = X_Qte_Lag1, métriques MAE / RMSE du §12).

### `ml/ml_11_1_prevision_demande_marque_hebdo.csv`

ML 11.1 – Prévision de la demande : quantité vendue par marque et par semaine.

- **Granularité :** 1 ligne = 1 Marque × 1 semaine (toutes les semaines, 0 si aucune vente)
- **Lignes :** 806
- **Sources :** fait_ventes, dim_produit, dim_temps
- **Cahier :** §11.1 Prévision de la demande (régression / séries temporelles)
- **Colonnes :** `Marque`, `SemaineDebut`, `AnneeSemaine`, `Y_Quantite`, `Y_QuantiteSemaineSuivante`, `X_Qte_Lag1`, `X_Qte_Lag2`, `X_Qte_Lag4`, `X_Qte_MoyenneMobile4`, `X_CA_HT`, `X_PrixMoyen_HT`, `X_TauxRemisePct`, `X_PartComptoirPct`, `X_NbDocuments`, `X_NbJoursFeries`, `X_NbJoursVacancesZoneC`, `X_NbJoursVacancesToutesZones`, `X_NbJoursOuvres`, `X_Mois`, `X_SemaineISO`, `X_Saison`, `X_Meteo_TempMoyenne`, `X_Meteo_TempMin`, `X_Meteo_TempMax`, `X_Meteo_Pluie_mm`, `X_Meteo_NbJoursPluie`, `X_Meteo_Ensoleillement_h`, `X_Meteo_Rayonnement_MJm2`, `X_Grippe_Inc100`, `X_IRA_Inc100`, `X_Gastro_Inc100`, `X_Varicelle_Inc100`, `SemaineComplete`
- Cible Y : `Y_Quantite` (semaine courante) ou `Y_QuantiteSemaineSuivante` (prévision t+1). Les variables explicatives sont préfixées `X_` (§13 : séparer clairement X et Y).
- X : historique (lags 1/2/4, moyenne mobile 4 semaines, toujours calculés sur le passé), prix moyen, remise, canal comptoir / facturé, jours fériés, vacances scolaires, jours ouvrés, mois, saison.
- Externes intégrés : météo de la semaine (Paris, Open-Meteo) – `X_Meteo_TempMoyenne`, `X_Meteo_TempMin`, `X_Meteo_TempMax`, `X_Meteo_Pluie_mm` (cumul), `X_Meteo_NbJoursPluie` (≥ 1 mm), `X_Meteo_Ensoleillement_h` (cumul), `X_Meteo_Rayonnement_MJm2` (cumul) ; épidémies de la semaine (réseau Sentinelles, France, pour 100 000 hab.) – `X_Grippe_Inc100`, `X_IRA_Inc100`, `X_Gastro_Inc100`, `X_Varicelle_Inc100`. Jointure par semaine ISO.
- Pour prévoir `Y_QuantiteSemaineSuivante`, les X de la semaine courante sont connus au moment de la prévision (Sentinelles publie avec ~1 semaine de délai : en production, décaler les épidémies d'une semaine).
- Externes non intégrés : Google Trends, taux EUR/TND.
- Ne pas utiliser la dernière semaine (`SemaineComplete = false`) pour l'entraînement ; ~30 semaines d'historique : valider sur les dernières semaines (baseline = X_Qte_Lag1, métriques MAE / RMSE du §12).
- Les 26 marques les plus vendues sont gardées, les autres regroupées en `AUTRES MARQUES`.

### `ml/ml_11_2_anomalies_ventes.csv`

ML 11.2 – Détection d'anomalies sur les lignes de vente (remise, prix vs coût moyen pondéré, quantité, utilisateur, heure).

- **Granularité :** 1 ligne = 1 ligne de vente (retours exclus)
- **Lignes :** 25,700
- **Sources :** fait_ventes, dim_produit
- **Cahier :** §11.2 Détection d'anomalies (non supervisé)
- **Colonnes :** `Id`, `Document_Id`, `DateKey`, `Product_Id`, `FamilyGroup`, `X_CreatedBy`, `X_Heure`, `X_JourSemaine`, `X_Canal`, `X_Quantity`, `X_Quantity_ZScoreProduit`, `X_PrixHt`, `X_PrixHt_Reference`, `X_EcartPrixReferencePct`, `X_DiscountPourcentage`, `X_PrixTotalHt`, `X_CoutMoyenPondere_HT`, `X_SourceCout`, `X_EcartPrixTotalHtCoutPct`, `X_NbLignesDocument`, `X_RemiseMoyenneUtilisateur`, `Regle_RemiseSup50`, `Regle_VenteSousCout`, `Regle_QuantiteAtypique`, `ScoreRegles`
- Pas de cible Y étiquetée dans les données : apprentissage non supervisé (Isolation Forest, LOF…) sur les colonnes `X_`.
- Les colonnes `Regle_*` sont des règles métier simples, utiles pour interpréter / évaluer les anomalies, pas une vérité terrain. Ne pas les utiliser comme X.
- Vérification des chiffres du cahier : 47 lignes de VENTE avec remise > 50 %. Le chiffre de 789 du cahier se retrouve exactement en comptant toutes les lignes de documents, mais 703 d'entre elles sont des unités gratuites sur factures fournisseurs (remise 100 %, voir fait_achats.EstUniteGratuite) et 37 sont sur des factures qui refacturent des BL : ce ne sont pas des ventes anormales.
- 588 lignes vendues sous le coût moyen pondéré = 2.3 % des lignes ayant un coût. Le chiffre de 22 % du cahier n'a pas pu être reproduit (prix HT médian = 1,45 × CUMP ; même le prix unitaire avant remise n'est sous le coût que pour 0,6 % des lignes) : à revoir dans le cahier.

### `ml/ml_11_3_operations_caisse.csv`

ML 11.3 – Opérations de caisse : montant, utilisateur, heure, fréquence d'annulation par utilisateur.

- **Granularité :** 1 ligne = 1 opération de caisse
- **Lignes :** 9,707
- **Sources :** CaisseOperations (+ noms des caisses issus de DomainEvents)
- **Cahier :** §11.3 Détection des écarts de caisse et annulations anormales
- **Colonnes :** `Id`, `CaisseId`, `CaisseName`, `DateKey`, `AddedAtUtc`, `X_AddedByUserId`, `X_HeureUtc`, `X_JourSemaine`, `X_Amount`, `X_EstMontantNegatif`, `X_Amount_ZScoreUtilisateur`, `X_Status`, `X_TauxAnnulationUtilisateur`, `X_NbOperationsJourUtilisateur`, `X_NbAnnulationsJourUtilisateur`, `Y_IsCancelled`, `DelaiAnnulationMinutes`
- `Y_IsCancelled` = annulation enregistrée (102 cas, cahier : 102) : cible possible pour un modèle supervisé, sinon détection d'anomalies sur les `X_`.
- `X_NbAnnulationsJourUtilisateur` exclut l'opération elle-même (pas de fuite de la cible).
- `DelaiAnnulationMinutes` n'est connu qu'après annulation : à ne pas utiliser comme X.
- Heures en UTC (horodatage d'origine).

### `ml/ml_11_3_ecarts_caisse.csv`

ML 11.3 – Écarts de caisse détectés à l'ouverture / la fermeture (attendu vs trouvé).

- **Granularité :** 1 ligne = 1 écart de caisse
- **Lignes :** 437
- **Sources :** DomainEvents (CaisseDiscrepancyIdentified)
- **Cahier :** §11.3
- **Colonnes :** `Id`, `DateKey`, `UtcTimestamp`, `AggregateId`, `CaisseName`, `X_UserId`, `X_HeureUtc`, `X_JourSemaine`, `X_DetectedAt`, `X_Data_expectedBalance`, `X_Data_foundBalance`, `X_Data_amount`, `X_EcartAbsolu`, `X_EcartRelatifPct`, `X_NbEcartsUtilisateur`, `X_NbEcartsCaisse`, `EstFondDeCaisseRetire`
- 437 écarts (cahier : 437).
- `EstFondDeCaisseRetire` = écart à l'ouverture avec caisse trouvée à 0 : probablement le fond de caisse retiré la veille, pas une perte – à traiter à part avant de parler de comportement à risque.

### `ml/ml_11_4_segmentation_clients.csv`

ML 11.4 – Segmentation client : CA total, fréquence, panier moyen, ancienneté, récence, type de client.

- **Granularité :** 1 ligne = 1 client identifié ayant au moins une vente (client comptoir anonyme exclu)
- **Lignes :** 79
- **Sources :** fait_ventes, dim_client (CompaniesList, Clients)
- **Cahier :** §11.4 Segmentation client (clustering) ; §6.3 clients actifs
- **Colonnes :** `Company_Id`, `Code`, `Nom`, `TypeClient`, `Ville`, `Geo_Id`, `X_CA_HT_Total`, `X_NbDocuments`, `X_FrequenceAchatMensuelle`, `X_PanierMoyen_HT`, `X_AncienneteJours`, `X_RecenceJours`, `X_NbMoisActifs`, `X_QuantiteTotale`, `X_NbProduitsDistincts`, `X_NbLignes`, `X_TauxRemisePct`, `X_PartComptoirPct`, `X_TauxMargePct`, `X_EstB2B`, `Solde`, `CA_TTC_Total`, `PremierAchat`, `DernierAchat`
- 79 clients identifiés ; ils représentent 49.0 % du CA HT (cahier : ~60 %). L'écart vient du double comptage évité : les factures qui refacturent des BL (clients identifiés) ne sont plus comptées deux fois.
- Type de client connu (B2B / particulier) pour 46 clients seulement (les autres n'existent pas dans le fichier Clients) : `X_EstB2B` vide = inconnu.
- Clients actifs (§6.3) = clients ayant au moins une transaction sur la période → tous les clients de ce fichier ; filtrer sur `X_RecenceJours` pour une période plus courte.
- Standardiser les X avant K-Means (montants très asymétriques : passer CA et quantités en log).

## Contrôles qualité (§7.1)

| Contrôle | Table | Concernés | Total | % | Statut |
|---|---|---|---|---|---|
| Ligne de document sans document | documentItemm | 0 | 38,705 | 0.00 | OK |
| Ligne de document sans produit | documentItemm | 1,038 | 38,705 | 2.68 | ATTENTION |
| Identifiant de document en double | Documents | 0 | 12,542 | 0.00 | OK |
| Quantité ≤ 0 sur une ligne | documentItemm | 1,165 | 38,705 | 3.01 | ATTENTION |
| Prix unitaire HT ≤ 0 | documentItemm | 1,085 | 38,705 | 2.80 | ATTENTION |
| Remise > 100 % | documentItemm | 1 | 38,705 | 0.00 | ATTENTION |
| Document hors période 30/09/2024 – 30/04/2025 | Documents | 0 | 12,542 | 0.00 | OK |
| Document brouillon (non validé) | Documents | 56 | 12,542 | 0.45 | ATTENTION |
| Facture client regroupant des BL (double comptage évité) | Documents | 24 | 249 | 9.64 | ATTENTION |
| Code postal incohérent avec la ville | Clients/Fournisseurs | 10 | 211 | 4.74 | ATTENTION |
| Produit du référentiel interne absent de l'export Produits | dim_produit | 2,376 | 6,842 | 34.73 | ATTENTION |
| Company_Id client (ventes / paiements) absent de CompaniesList | fait_ventes, fait_paiements | 19 | 80 | 23.75 | ATTENTION |
| Client du fichier Clients sans Company_Id (non reliable aux ventes) | Clients | 46 | 93 | 49.46 | ATTENTION |
| Company_Id fournisseur (achats / paiements) absent des fournisseurs de CompaniesList | fait_achats, fait_paiements | 21 | 115 | 18.26 | ATTENTION |
| Ligne de vente sans coût (marge non calculable) | fait_ventes | 2 | 25,743 | 0.01 | ATTENTION |
| Ligne de vente sous le coût | fait_ventes | 589 | 25,743 | 2.29 | ATTENTION |
| Paiement sans document retrouvé | fait_paiements | 456 | 10,899 | 4.18 | ATTENTION |
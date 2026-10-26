# Dictionnaire du jeu de données – Health Retailers (version B)

Construit par `build_dataset.py` (branche `main`) à partir de `cleaned/` (réel) et `cleaned/synthetique/` (données générées). Les fichiers sources ne sont jamais modifiés.

**Période :** Données réelles du 30/09/2024 au 30/04/2025 (7 mois), prolongées par des données synthétiques jusqu'au 29/09/2026. Délimitation par la date : réel jusqu'au 30/04/2025 inclus, synthétique ensuite (aucune colonne dédiée).

## Règles

- Modèle du §9 du cahier : 5 dimensions (`dim_temps`, `dim_produit`, `dim_client`, `dim_fournisseur`, `dim_paiement`) et 5 faits (`fait_ventes`, `fait_encaissements`, `fait_achats`, `fait_decaissements`, `fait_stock_actuel`).
- Une colonne n'est stockée que si le cahier l'exige **et** qu'elle ne peut pas être recalculée. Les mesures (marge, rupture, stock faible, montant encaissé…) sont calculées dans Power BI.
- CSV UTF-8, séparateur virgule, décimale `.`, dates ISO, booléens `true/false`. `DateKey` = `AAAAMMJJ`.
- Membres `-1` « NON RENSEIGNE » dans `dim_client`, `dim_fournisseur` et `dim_paiement` : toutes les clés étrangères retrouvent leur dimension.
- Jeux ML : variables explicatives `X_…`, cibles `Y_…`, règles d'interprétation `Regle_…` (ni X ni Y). Ils sont construits depuis la zone ETL (données nettoyées), pas depuis le Data Warehouse.

## Besoins du cahier → tables

| Décideur | Questions | Mesures | Tables |
|---|---|---|---|
| Direction générale | CA, nombre de ventes, panier moyen, croissance | SUM(CA_HT) ; COUNT(DISTINCT Document_Id) ; CA / ventes ; (CA_N − CA_N-1) / CA_N-1 × 100 | fait_ventes × dim_temps |
| Responsable commercial | Produits, familles, marques les plus vendus et les plus rentables, panier moyen | SUM(CA_HT) ; SUM(QuantiteVendue) ; Marge HT = SUM(CA_HT) − SUM(Cout_HT) | fait_ventes × dim_produit × dim_temps |
| Responsable relation client | Clients actifs, valeur, fréquence, panier | DISTINCTCOUNT(Company_Id) avec EstClientIdentifie = true ; SUM(CA_HT) ; COUNT(DISTINCT Document_Id) | fait_ventes × dim_client × dim_temps ; ml_11_4 |
| Responsable approvisionnement / stock | Stock disponible, ruptures, stock faible, demande à anticiper | SUM(Quantity) ; COUNT où Quantity = 0 ; COUNT où 0 < Quantity ≤ QuantiteAlerte | fait_stock_actuel × dim_produit ; ml_11_1 |
| Responsable financier / caisse | Montant encaissé, montant payé par chaque client, montant payé à chaque fournisseur, nombre de paiements, répartition par moyen, quelle vente ou facture chaque paiement règle | SUM(fait_encaissements.Amount) ; SUM(fait_decaissements.Amount) ; par client, fournisseur ou Document_Id ; DISTINCTCOUNT(Payment_Id) | fait_encaissements × dim_client, fait_decaissements × dim_fournisseur ; dim_paiement × dim_temps ; ml_11_3 |
| Responsable achats | Achats par fournisseur et par produit, quel produit vient de quel fournisseur | SUM(MontantAchat_HT) ; SUM(QuantiteAchetee) ; COUNT(DISTINCT Document_Id) | fait_achats × dim_fournisseur × dim_produit × dim_temps |

## Tables du Data Warehouse

### `dwh/dim_temps.csv`

Dimension Temps : date, année, trimestre, mois, semaine ISO, jour férié.

- **Granularité :** 1 ligne = 1 date (30/09/2024 → 29/09/2026)
- **Lignes :** 730
- **Sources :** Calculée : calendrier français (fêtes fixes et fêtes mobiles calculées à partir de Pâques)
- **Cahier :** §7 et §9 du cahier : « Date, semaine, mois, trimestre, année, EstFerie »
- **Colonnes :** `DateKey`, `Date`, `Annee`, `Trimestre`, `Mois`, `SemaineISO`, `EstFerie`
- Le calendrier français est calculé : ce n'est pas une source externe.
- Pas de vacances scolaires, de météo ni d'indicateur épidémique dans cette dimension : la météo et les épidémies sont réservées au jeu ML de prévision (§4.2, §8).
- Délimitation réel / synthétique par la date : réel jusqu'au 30/04/2025 inclus.

### `dwh/dim_produit.csv`

Dimension Produit : libellé, famille, marque.

- **Granularité :** 1 ligne = 1 produit du référentiel interne (ProductStocks), clé Product_Id
- **Lignes :** 6 842
- **Sources :** ProductStocks, Produits, Events (libellés), ProductBrands, users_settings (seuil par défaut)
- **Cahier :** §7 et §9 du cahier : « Libellé, Famille, Marque » ; §6.2, §6.4, §6.6
- **Colonnes :** `Product_Id`, `Libellé`, `Famille`, `Marque`
- Libellé : {'Events': 159, 'absent': 2182, 'documentItemm': 35, 'Produits': 4466}.
- Marque manquante : déduite si le libellé commence par un nom de ProductBrands, sinon `NON RENSEIGNE`.
- Le seuil d'alerte de stock (QuantiteAlerte) est stocké dans `fait_stock_actuel`, à côté de la quantité.
- Les prix d'achat / de vente et le coût moyen pondéré restent en zone ETL : ils servent à calculer `CA_HT` et `Cout_HT`, aucun KPI n'utilise le prix catalogue.

### `dwh/dim_client.csv`

Dimension Client : nom, type de client, client identifié ou non.

- **Granularité :** 1 ligne = 1 client, y compris le client comptoir anonyme (clé Company_Id, celle des transactions)
- **Lignes :** 82
- **Sources :** CompaniesList, Clients, Transactions
- **Cahier :** §6.3 Analyse des clients ; §9 Dimension Client
- **Colonnes :** `Company_Id`, `Nom`, `TypeClient`, `EstClientIdentifie`
- TypeClient : {'COMPTOIR_ANONYME': 1, 'PARTICULIER': 29, 'NON RENSEIGNE': 34, 'B2B': 18}. Company_Id 2 = client comptoir anonyme (la majorité des ventes comptoir).
- `EstClientIdentifie` = false pour le client comptoir et la ligne -1 : filtre de tous les KPI clients (§6.3 : les transactions anonymes ne sont pas utilisées pour les KPI clients).
- Le nom vient du fichier Clients quand le code y existe (les noms de CompaniesList ont été anonymisés différemment) ; le code client sert seulement à cette jointure dans l'ETL.

### `dwh/dim_fournisseur.csv`

Dimension Fournisseur : nom du fournisseur.

- **Granularité :** 1 ligne = 1 fournisseur (clé Fournisseur_Id = identifiant de la société dans le logiciel)
- **Lignes :** 116
- **Sources :** CompaniesList (sociétés de type fournisseur), Fournisseurs (noms), Transactions
- **Cahier :** §6.6 Achats ; §6.5 Paiements ; §9 Dimension Fournisseur
- **Colonnes :** `Fournisseur_Id`, `Nom`
- Le nom vient du fichier Fournisseurs quand le code y existe (les noms de CompaniesList ont été anonymisés différemment) ; le code fournisseur sert seulement à cette jointure dans l'ETL.
- 21 fournisseurs cités par des factures ou des paiements sont absents de CompaniesList : conservés comme 'FOURNISSEUR INCONNU <id>'. -1 = fournisseur non renseigné (et valeur des lignes qui ne concernent pas un fournisseur).

### `dwh/dim_paiement.csv`

Dimension Paiement : moyen de paiement.

- **Granularité :** 1 ligne = 1 moyen de paiement
- **Lignes :** 6
- **Sources :** PaymentsList (PaymentMode_Id / PaymentMethodName)
- **Cahier :** §6.5 Paiements ; §9 « Libellé / type de moyen »
- **Colonnes :** `PaymentMode_Id`, `PaymentModeName`
- -1 = paiement sans moyen renseigné dans la source (encaissements de caisse).
- Le mode « Inconnu (4) » du logiciel n'est utilisé par aucun paiement : il n'est pas repris.

### `dwh/fait_ventes.csv`

Fait Ventes : ligne de produit vendue (ou retournée) dans un document validé à une date donnée.

- **Granularité :** 1 ligne = 1 produit vendu dans 1 document à 1 date
- **Lignes :** 91 015
- **Sources :** documentItemm, Documents, Transactions, StockMovements (coût) — réel + synthétique
- **Cahier :** §6.1, §6.2, §6.3 ; §9 fait_ventes (Document_Id, QuantiteVendue, CA_HT, Remise_HT, Cout_HT)
- **Colonnes :** `Id`, `Document_Id`, `DateKey`, `Product_Id`, `Company_Id`, `QuantiteVendue`, `Remise_HT`, `CA_HT`, `Cout_HT`
- 25 743 lignes de la période réelle et 65 272 lignes de la période synthétique (délimitation par la date : réel jusqu'au 30/04/2025).
- Ventes = vente comptoir (6), bon de livraison (5), facture client (1) ; retours = avoir (4) et bon de retour (7) en négatif : `QuantiteVendue`, `CA_HT`, `Remise_HT`, `Cout_HT` sont signés.
- `Document_Id` est une dimension dégénérée : Nombre de ventes = COUNT(DISTINCT Document_Id), panier moyen = SUM(CA_HT) / Nombre de ventes.
- Exclusions : ligne de commentaire sans produit ni montant : 1 326 lignes; facture client regroupant des BL déjà comptés : 4 003 lignes; document brouillon (State = 0) : 873 lignes.
- Coût : {'CUMP_MOUVEMENT': 90955, 'PRIX_ACHAT_PRODUIT': 58, 'ABSENT': 2} — CUMP = coût moyen pondéré au moment de la vente (StockMovements), sinon prix d'achat HT du produit. Marge HT = SUM(CA_HT) − SUM(Cout_HT) est une mesure Power BI, pas une colonne.
- Retirés de la version précédente : CA_TTC (recalculable), Marge_HT (mesure), coût unitaire, signe, taux de remise, colonnes brutes et colonnes document / utilisateur / moyen de paiement.

### `dwh/fait_achats.csv`

Fait Achats : ligne de produit achetée (ou retournée) à un fournisseur dans une facture validée.

- **Granularité :** 1 ligne = 1 produit acheté dans 1 facture fournisseur à 1 date
- **Lignes :** 23 738
- **Sources :** documentItemm, Documents (factures et avoirs fournisseurs), Transactions — réel + synthétique
- **Cahier :** §6.6 Achats ; §9 fait_achats (Document_Id, QuantiteAchetee, MontantAchat_HT)
- **Colonnes :** `Id`, `Document_Id`, `DateKey`, `Product_Id`, `Fournisseur_Id`, `QuantiteAchetee`, `MontantAchat_HT`
- 6 980 lignes de la période réelle et 16 758 lignes de la période synthétique.
- Achats = facture fournisseur (20) ; retours = avoir fournisseur (23) en négatif : `QuantiteAchetee` et `MontantAchat_HT` sont signés. Aucune facture fournisseur ne regroupe d'autres documents : pas de double comptage.
- `Document_Id` est une dimension dégénérée : Nombre de factures fournisseurs = COUNT(DISTINCT Document_Id).
- `MontantAchat_HT` = montant HT de la ligne après remise. Le prix d'achat unitaire n'est pas stocké : SUM(MontantAchat_HT) / SUM(QuantiteAchetee).
- Exclusions : ligne de commentaire sans produit ni montant : 51 lignes; document brouillon (State = 0) : 157 lignes.

### `dwh/fait_stock_actuel.csv`

Fait Stock actuel : quantité en stock et seuil d'alerte de chaque produit à la date du snapshot.

- **Granularité :** 1 ligne = 1 produit à la date de snapshot (29/09/2026, fin de la période chargée)
- **Lignes :** 6 842
- **Sources :** ProductStocks (données synthétiques, état au 29/09/2026), Produits (seuil d'alerte)
- **Cahier :** §6.4 Gestion du stock ; §9 « Quantity, QuantiteAlerte. Rupture et stock faible sont calculés »
- **Colonnes :** `Product_Id`, `DateKey`, `Quantity`, `QuantiteAlerte`
- Au snapshot : 1 834 produits à 0 (rupture), 2 472 en stock faible (0 < Quantity ≤ QuantiteAlerte), 308 à stock négatif.
- Rupture et stock faible ne sont pas stockés : mesures Power BI à partir de `Quantity` et de `QuantiteAlerte`, dans la même table.
- QuantiteAlerte : {'paramètre par défaut (5)': 2376, 'export Produits': 4466}. Seuil choisi par le magasin pour chaque produit (pas une valeur calculable). Une ligne par produit : le seuil n'est stocké qu'une fois.
- Pas d'historique de stock dans le BI (rotation non retenue, §6.4) : les mouvements restent en zone ETL.

### `dwh/fait_encaissements.csv`

Fait Encaissements : argent reçu d'un client, imputé à la vente qu'il règle.

- **Granularité :** 1 ligne = 1 encaissement imputé à 1 vente réglée
- **Lignes :** 38 738
- **Sources :** PaymentsList + Payment (fusionnés), TransactionPayments (imputation), Documents, RelatedDocuments, CompaniesList — réel + synthétique
- **Cahier :** §6.5 Paiements ; §9 fait_encaissements (Amount ; client ; vente réglée)
- **Colonnes :** `Id`, `Payment_Id`, `Document_Id`, `DateKey`, `PaymentMode_Id`, `Company_Id`, `Amount`
- 38 142 encaissements (10 398 de la période réelle, 36 041 au comptoir) sur 38 738 lignes ; montant encaissé = SUM(Amount) = 3 007 313.
- `Company_Id` = client qui paie (2 = client comptoir anonyme). `Document_Id` = vente réglée, même clé que dans `fait_ventes` : répond à « quelle vente ce paiement règle-t-il ? » ; -1 si aucune imputation.
- Moyen de paiement : saisi par le logiciel seulement pendant les premières semaines (sept.-oct. 2024), presque jamais ensuite ; la répartition par moyen n'est représentative que sur cette période.
- Imputation : celle de TransactionPayments (paiement → transaction → montant). Quand une transaction règle plusieurs documents chargés — facture client regroupant des bons de livraison (seuls les bons sont dans fait_ventes), document et avoir — le montant est réparti au prorata du total TTC des documents de total positif.
- `Payment_Id` = numéro du paiement (dimension dégénérée) : Nombre de paiements = DISTINCTCOUNT(Payment_Id). `Id` = clé technique de la ligne d'imputation ; la somme des lignes d'un paiement est exactement son montant.
- `Amount` est TTC et n'est pas le CA : impayés, paiements fractionnés ou différés. Aucun paiement n'est négatif : l'argent rendu lors d'un retour n'est pas enregistré comme paiement dans la source (les retours apparaissent en négatif dans fait_ventes et fait_achats).
- Remplace, avec fait_decaissements, l'ancienne table fait_paiements : la table donne le sens du paiement, sans indicateur ni clé « sans objet ».

### `dwh/fait_decaissements.csv`

Fait Décaissements : argent versé à un fournisseur, imputé à la facture fournisseur qu'il règle.

- **Granularité :** 1 ligne = 1 décaissement imputé à 1 facture fournisseur réglée
- **Lignes :** 1 629
- **Sources :** PaymentsList + Payment (fusionnés), TransactionPayments (imputation), Documents, CompaniesList — réel + synthétique
- **Cahier :** §6.5 Paiements ; §6.6 Achats ; §9 fait_decaissements (Amount ; fournisseur ; facture réglée)
- **Colonnes :** `Id`, `Payment_Id`, `Document_Id`, `DateKey`, `PaymentMode_Id`, `Fournisseur_Id`, `Amount`
- 1 628 décaissements (501 de la période réelle) sur 1 629 lignes ; montant payé aux fournisseurs = SUM(Amount) = 1 976 938.
- `Fournisseur_Id` = fournisseur payé. `Document_Id` = facture fournisseur réglée, même clé que dans `fait_achats` : répond à « quelle facture ce paiement règle-t-il ? ».
- Imputation : celle de TransactionPayments (paiement → transaction → montant). Quand une transaction règle plusieurs documents chargés — facture client regroupant des bons de livraison (seuls les bons sont dans fait_ventes), document et avoir — le montant est réparti au prorata du total TTC des documents de total positif.
- `Payment_Id` = numéro du paiement (dimension dégénérée) : Nombre de paiements = DISTINCTCOUNT(Payment_Id). `Id` = clé technique de la ligne d'imputation ; la somme des lignes d'un paiement est exactement son montant.
- `Amount` est TTC et n'est pas le CA : impayés, paiements fractionnés ou différés. Aucun paiement n'est négatif : l'argent rendu lors d'un retour n'est pas enregistré comme paiement dans la source (les retours apparaissent en négatif dans fait_ventes et fait_achats).
- Les achats (fait_achats) sont HT, les décaissements TTC : ne pas comparer les deux montants directement.


## Jeux de données Machine Learning

### `ml/ml_11_1_prevision_demande_famille_hebdo.csv`

ML 11.1 – Prévision de la demande : quantité vendue par famille et par semaine.

- **Granularité :** 1 ligne = 1 semaine × 1 famille (toutes les semaines, 0 si aucune vente)
- **Lignes :** 735
- **Sources :** fait_ventes, dim_produit, calendrier ; externes : Open-Meteo, Réseau Sentinelles
- **Cahier :** §11.1 Prévision de la demande (régression / séries temporelles), horizon N+1 semaine
- **Colonnes :** `FamilyGroup`, `SemaineDebut`, `AnneeSemaine`, `Y_Quantite`, `Y_QuantiteSemaineSuivante`, `X_Qte_Lag1`, `X_Qte_Lag2`, `X_Qte_Lag4`, `X_Qte_MoyenneMobile4`, `X_CA_HT`, `X_PrixMoyen_HT`, `X_TauxRemisePct`, `X_PartComptoirPct`, `X_NbDocuments`, `X_NbJoursFeries`, `X_NbJoursOuvres`, `X_Mois`, `X_SemaineISO`, `X_Meteo_TempMoyenne`, `X_Meteo_TempMin`, `X_Meteo_TempMax`, `X_Meteo_Pluie_mm`, `X_Meteo_NbJoursPluie`, `X_Meteo_Ensoleillement_h`, `X_Meteo_Rayonnement_MJm2`, `X_Grippe_Inc100`, `X_IRA_Inc100`, `X_Gastro_Inc100`, `X_Varicelle_Inc100`, `SemaineComplete`
- Cible Y : `Y_QuantiteSemaineSuivante` (prévision N+1) ; `Y_Quantite` = semaine courante. Variables explicatives préfixées `X_` (§15 : séparer X, Y, granularité et métrique).
- X internes : lags 1/2/4, moyenne mobile 4 semaines (toujours sur le passé), CA, prix moyen, taux de remise, part comptoir, nombre de documents. X temporelles : semaine ISO, mois, jours fériés, jours ouvrés.
- X externes candidates (§8) : météo de la semaine (Paris, Open-Meteo) `X_Meteo_*` et épidémies (Réseau Sentinelles, France, /100 000 hab.) `X_Grippe_Inc100`, `X_IRA_Inc100`, `X_Gastro_Inc100`, `X_Varicelle_Inc100`. Pas de vacances scolaires.
- Période réelle = semaines commençant jusqu'au 21/04/2025 inclus ; la semaine suivante mélange réel et synthétique, les autres sont synthétiques. Règle du §8 : l'apport de la météo et des épidémies se mesure sur la période réelle uniquement (ces effets ont servi d'hypothèses à la génération) — comparer le modèle avec et sans ces variables (MAE / RMSE, baseline = X_Qte_Lag1).
- Ne pas entraîner sur les semaines `SemaineComplete = false` (bords de période). Sentinelles publie avec ~1 semaine de délai : en production, décaler les épidémies d'une semaine.

### `ml/ml_11_1_prevision_demande_marque_hebdo.csv`

ML 11.1 – Prévision de la demande : quantité vendue par marque et par semaine.

- **Granularité :** 1 ligne = 1 semaine × 1 marque (toutes les semaines, 0 si aucune vente)
- **Lignes :** 2 730
- **Sources :** fait_ventes, dim_produit, calendrier ; externes : Open-Meteo, Réseau Sentinelles
- **Cahier :** §11.1 Prévision de la demande (régression / séries temporelles), horizon N+1 semaine
- **Colonnes :** `Marque`, `SemaineDebut`, `AnneeSemaine`, `Y_Quantite`, `Y_QuantiteSemaineSuivante`, `X_Qte_Lag1`, `X_Qte_Lag2`, `X_Qte_Lag4`, `X_Qte_MoyenneMobile4`, `X_CA_HT`, `X_PrixMoyen_HT`, `X_TauxRemisePct`, `X_PartComptoirPct`, `X_NbDocuments`, `X_NbJoursFeries`, `X_NbJoursOuvres`, `X_Mois`, `X_SemaineISO`, `X_Meteo_TempMoyenne`, `X_Meteo_TempMin`, `X_Meteo_TempMax`, `X_Meteo_Pluie_mm`, `X_Meteo_NbJoursPluie`, `X_Meteo_Ensoleillement_h`, `X_Meteo_Rayonnement_MJm2`, `X_Grippe_Inc100`, `X_IRA_Inc100`, `X_Gastro_Inc100`, `X_Varicelle_Inc100`, `SemaineComplete`
- Cible Y : `Y_QuantiteSemaineSuivante` (prévision N+1) ; `Y_Quantite` = semaine courante. Variables explicatives préfixées `X_` (§15 : séparer X, Y, granularité et métrique).
- X internes : lags 1/2/4, moyenne mobile 4 semaines (toujours sur le passé), CA, prix moyen, taux de remise, part comptoir, nombre de documents. X temporelles : semaine ISO, mois, jours fériés, jours ouvrés.
- X externes candidates (§8) : météo de la semaine (Paris, Open-Meteo) `X_Meteo_*` et épidémies (Réseau Sentinelles, France, /100 000 hab.) `X_Grippe_Inc100`, `X_IRA_Inc100`, `X_Gastro_Inc100`, `X_Varicelle_Inc100`. Pas de vacances scolaires.
- Période réelle = semaines commençant jusqu'au 21/04/2025 inclus ; la semaine suivante mélange réel et synthétique, les autres sont synthétiques. Règle du §8 : l'apport de la météo et des épidémies se mesure sur la période réelle uniquement (ces effets ont servi d'hypothèses à la génération) — comparer le modèle avec et sans ces variables (MAE / RMSE, baseline = X_Qte_Lag1).
- Ne pas entraîner sur les semaines `SemaineComplete = false` (bords de période). Sentinelles publie avec ~1 semaine de délai : en production, décaler les épidémies d'une semaine.
- Les 26 marques les plus vendues sont gardées, les autres regroupées en `AUTRES MARQUES`.

### `ml/ml_11_2_anomalies_ventes.csv`

ML 11.2 – Détection d'anomalies sur les lignes de vente (remise, prix vs coût, quantité, utilisateur, heure).

- **Granularité :** 1 ligne = 1 ligne de vente (retours exclus)
- **Lignes :** 90 972
- **Sources :** fait_ventes + colonnes de la zone ETL (heure, vendeur, prix, remise)
- **Cahier :** §11.2 Détection d'anomalies (non supervisé : Isolation Forest, LOF…)
- **Colonnes :** `Id`, `Document_Id`, `DateKey`, `Product_Id`, `FamilyGroup`, `X_CreatedBy`, `X_Heure`, `X_JourSemaine`, `X_Canal`, `X_Quantity`, `X_Quantity_ZScoreProduit`, `X_PrixHt`, `X_PrixHt_Reference`, `X_EcartPrixReferencePct`, `X_DiscountPourcentage`, `X_PrixTotalHt`, `X_Cout_HT`, `X_SourceCout`, `X_EcartPrixTotalHtCoutPct`, `X_NbLignesDocument`, `X_RemiseMoyenneUtilisateur`, `Regle_RemiseSup50`, `Regle_VenteSousCout`, `Regle_QuantiteAtypique`, `ScoreRegles`
- Pas de cible Y étiquetée : apprentissage non supervisé sur les colonnes `X_`.
- Les colonnes `Regle_*` sont des règles métier pour contrôler les résultats, pas une vérité terrain : ne pas les utiliser comme X.
- 174 lignes avec remise > 50 % ; 2 857 lignes vendues sous le coût (3.1 % des lignes ayant un coût).
- Le jeu couvre les deux périodes ; les anomalies de la période synthétique sont simulées : à interpréter en priorité sur la période réelle.

### `ml/ml_11_3_operations_caisse.csv`

ML 11.3 – Opérations de caisse : montant, utilisateur, heure, fréquence d'annulation par utilisateur.

- **Granularité :** 1 ligne = 1 opération de caisse
- **Lignes :** 37 767
- **Sources :** CaisseOperations (+ noms des caisses issus de DomainEvents) — réel + synthétique
- **Cahier :** §11.3 Détection d'anomalies de caisse ; Y possible = IsCancelled
- **Colonnes :** `Id`, `CaisseId`, `CaisseName`, `DateKey`, `AddedAtUtc`, `X_AddedByUserId`, `X_HeureUtc`, `X_JourSemaine`, `X_Amount`, `X_EstMontantNegatif`, `X_Amount_ZScoreUtilisateur`, `X_Status`, `X_TauxAnnulationUtilisateur`, `X_NbOperationsJourUtilisateur`, `X_NbAnnulationsJourUtilisateur`, `Y_IsCancelled`, `DelaiAnnulationMinutes`
- `Y_IsCancelled` = annulation enregistrée (404 cas) : cible d'une classification d'annulation, sinon détection d'anomalies sur les `X_`.
- `X_NbAnnulationsJourUtilisateur` exclut l'opération elle-même (pas de fuite de la cible). `DelaiAnnulationMinutes` n'est connu qu'après annulation : à ne pas utiliser comme X.
- Heures en UTC. Une opération annulée n'est pas automatiquement frauduleuse : validation humaine (§11.3).

### `ml/ml_11_3_ecarts_caisse.csv`

ML 11.3 – Écarts de caisse détectés à l'ouverture / la fermeture (attendu vs trouvé).

- **Granularité :** 1 ligne = 1 écart de caisse
- **Lignes :** 2 189
- **Sources :** DomainEvents (CaisseDiscrepancyIdentified) — réel + synthétique
- **Cahier :** §11.3
- **Colonnes :** `Id`, `DateKey`, `UtcTimestamp`, `AggregateId`, `CaisseName`, `X_UserId`, `X_HeureUtc`, `X_JourSemaine`, `X_DetectedAt`, `X_Data_expectedBalance`, `X_Data_foundBalance`, `X_Data_amount`, `X_EcartAbsolu`, `X_EcartRelatifPct`, `X_NbEcartsUtilisateur`, `X_NbEcartsCaisse`, `EstFondDeCaisseRetire`
- 2 189 écarts.
- `EstFondDeCaisseRetire` = écart à l'ouverture avec caisse trouvée à 0 : fond de caisse retiré la veille, pas une perte — à traiter à part avant de parler de comportement à risque.

### `ml/ml_11_4_segmentation_clients.csv`

ML 11.4 – Segmentation client : CA, fréquence, panier moyen, récence, ancienneté, produits distincts, type.

- **Granularité :** 1 ligne = 1 client identifié ayant au moins une vente (client comptoir anonyme exclu)
- **Lignes :** 79
- **Sources :** fait_ventes, dim_client
- **Cahier :** §11.4 Segmentation client (clustering, aucune cible Y)
- **Colonnes :** `Company_Id`, `Nom`, `TypeClient`, `X_CA_HT_Total`, `X_NbDocuments`, `X_FrequenceAchatMensuelle`, `X_PanierMoyen_HT`, `X_AncienneteJours`, `X_RecenceJours`, `X_NbMoisActifs`, `X_QuantiteTotale`, `X_NbProduitsDistincts`, `X_NbLignes`, `X_TauxRemisePct`, `X_PartComptoirPct`, `X_TauxMargePct`, `X_EstB2B`, `PremierAchat`, `DernierAchat`
- 79 clients identifiés, 42.0 % du CA HT sur les deux périodes.
- Type de client connu (B2B / particulier) pour 46 clients : `X_EstB2B` vide = inconnu.
- Récence et ancienneté calculées à la fin de la période chargée (29/09/2026) ; standardiser les X avant K-Means (passer CA et quantités en log).

## Contrôles qualité (§7.1)

| Contrôle | Table | Concernés | Total | % | Statut |
|---|---|---|---|---|---|
| Ligne de document sans document | documentItemm | 0 | 121 279 | 0.00 | OK |
| Ligne de document sans produit | documentItemm | 1 377 | 121 279 | 1.14 | ATTENTION |
| Identifiant de document en double | Documents | 0 | 45 448 | 0.00 | OK |
| Quantité ≤ 0 sur une ligne | documentItemm | 1 824 | 121 279 | 1.50 | ATTENTION |
| Prix unitaire HT ≤ 0 | documentItemm | 1 424 | 121 279 | 1.17 | ATTENTION |
| Remise > 100 % | documentItemm | 1 | 121 279 | 0.00 | ATTENTION |
| Document hors période 30/09/2024 – 29/09/2026 | Documents | 0 | 45 448 | 0.00 | OK |
| Document brouillon (non validé) | Documents | 117 | 45 448 | 0.26 | ATTENTION |
| Facture client regroupant des BL (double comptage évité) | Documents | 24 | 1 052 | 2.28 | ATTENTION |
| Produit du référentiel interne absent de l'export Produits | dim_produit | 2 376 | 6 842 | 34.73 | ATTENTION |
| Company_Id client absent de CompaniesList | fait_ventes / fait_encaissements | 19 | 80 | 23.75 | ATTENTION |
| Fournisseur d'un achat ou d'un paiement absent de CompaniesList | fait_achats / fait_decaissements | 21 | 115 | 18.26 | ATTENTION |
| Ligne de vente sans coût (marge non calculable) | fait_ventes | 2 | 91 015 | 0.00 | ATTENTION |
| Ligne d'achat sans fournisseur identifié | fait_achats | 13 | 23 738 | 0.05 | ATTENTION |
| Produit à stock négatif (vente enregistrée sans réception) | fait_stock_actuel | 308 | 6 842 | 4.50 | ATTENTION |
| Encaissement sans moyen de paiement renseigné | fait_encaissements | 37 264 | 38 142 | 97.70 | ATTENTION |
| Encaissement sans client identifié | fait_encaissements | 0 | 38 142 | 0.00 | OK |
| Décaissement sans fournisseur identifié | fait_decaissements | 0 | 1 628 | 0.00 | OK |
| Paiement non rattaché à un document chargé | fait_encaissements | 6 | 38 142 | 0.02 | ATTENTION |
| Paiement non rattaché à un document chargé | fait_decaissements | 0 | 1 628 | 0.00 | OK |
| Paiement rattaché à un document de l'autre sens (vente ↔ achat) | fait_encaissements / fait_decaissements | 0 | 40 367 | 0.00 | OK |
| Écart entre les paiements source et encaissements + décaissements (centimes) | fait_encaissements / fait_decaissements | 0 | 498 425 121 | 0.00 | OK |
| Clé Product_Id de fait_ventes absente de la dimension | fait_ventes | 0 | 91 015 | 0.00 | OK |
| Clé Company_Id de fait_ventes absente de la dimension | fait_ventes | 0 | 91 015 | 0.00 | OK |
| Clé DateKey de fait_ventes absente de la dimension | fait_ventes | 0 | 91 015 | 0.00 | OK |
| Clé Product_Id de fait_achats absente de la dimension | fait_achats | 0 | 23 738 | 0.00 | OK |
| Clé Fournisseur_Id de fait_achats absente de la dimension | fait_achats | 0 | 23 738 | 0.00 | OK |
| Clé DateKey de fait_achats absente de la dimension | fait_achats | 0 | 23 738 | 0.00 | OK |
| Clé Company_Id de fait_encaissements absente de la dimension | fait_encaissements | 0 | 38 738 | 0.00 | OK |
| Clé PaymentMode_Id de fait_encaissements absente de la dimension | fait_encaissements | 0 | 38 738 | 0.00 | OK |
| Clé DateKey de fait_encaissements absente de la dimension | fait_encaissements | 0 | 38 738 | 0.00 | OK |
| Clé Fournisseur_Id de fait_decaissements absente de la dimension | fait_decaissements | 0 | 1 629 | 0.00 | OK |
| Clé PaymentMode_Id de fait_decaissements absente de la dimension | fait_decaissements | 0 | 1 629 | 0.00 | OK |
| Clé DateKey de fait_decaissements absente de la dimension | fait_decaissements | 0 | 1 629 | 0.00 | OK |
| Ligne de vente sous le coût | fait_ventes | 2 857 | 90 972 | 3.14 | ATTENTION |

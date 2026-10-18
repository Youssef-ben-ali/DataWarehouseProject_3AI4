# Jeux de données Machine Learning – version B

Un fichier par objectif ML du cahier de spécification (§11), produit par `build_dataset.py` (branche `main`) à partir de la zone ETL (données nettoyées réelles et synthétiques).

**Période :** Données réelles du 30/09/2024 au 30/04/2025 (7 mois), prolongées par des données synthétiques jusqu'au 29/09/2026. Délimitation par la date : réel jusqu'au 30/04/2025 inclus, synthétique ensuite (aucune colonne dédiée).

| Fichier | Objectif | Lignes |
|---|---|---|
| `ml_11_1_prevision_demande_famille_hebdo.csv` | §11.1 Prévision de la demande | 735 |
| `ml_11_1_prevision_demande_marque_hebdo.csv` | §11.1 Prévision de la demande | 2 730 |
| `ml_11_2_anomalies_ventes.csv` | §11.2 Détection d'anomalies | 91 952 |
| `ml_11_3_operations_caisse.csv` | §11.3 Détection d'anomalies de caisse ; Y possible = IsCancelled | 38 153 |
| `ml_11_3_ecarts_caisse.csv` | §11.3 | 2 107 |
| `ml_11_4_segmentation_clients.csv` | §11.4 Segmentation client | 79 |

Conventions (§15 du cahier : séparer X, Y, granularité et métrique) :
- `X_…` = variables explicatives, `Y_…` = cible ; `Regle_…` = règles métier d'interprétation (ni X ni Y) ;
- les identifiants (`Id`, `Product_Id`, `Company_Id`…) servent à relier les résultats au Data Warehouse ;
- prévision (11.1) : météo et épidémies sont des variables **candidates**, conservées seulement si elles améliorent le modèle — mesure à faire sur la **période réelle** uniquement (§8).

La description détaillée de chaque fichier est dans `DICTIONNAIRE_DATASET.md` de la branche [`dataset-dwh`](../../tree/dataset-dwh).

Retour à la vue d'ensemble : branche [`main`](../../tree/main).

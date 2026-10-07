# Jeux de données Machine Learning

Un fichier par objectif ML du cahier de spécification (§11), produit par `build_dataset.py` (branche `main`).

| Fichier | Objectif | Lignes |
|---|---|---|
| `ml_11_1_prevision_demande_famille_hebdo.csv` | §11.1 Prévision de la demande par famille et par semaine | 217 |
| `ml_11_1_prevision_demande_marque_hebdo.csv` | §11.1 Prévision de la demande par marque et par semaine | 806 |
| `ml_11_2_anomalies_ventes.csv` | §11.2 Détection d'anomalies sur les lignes de vente | 25 700 |
| `ml_11_3_ecarts_caisse.csv` | §11.3 Écarts de caisse | 437 |
| `ml_11_3_operations_caisse.csv` | §11.3 Opérations de caisse (annulations) | 9 707 |
| `ml_11_4_segmentation_clients.csv` | §11.4 Segmentation des clients identifiés | 79 |

Conventions (§13 du cahier : séparer clairement X et Y) :
- `X_…` = variables explicatives, `Y_…` = cible ;
- `Regle_…` = règles métier pour interpréter les anomalies (ni X ni Y) ;
- les identifiants (`Id`, `Product_Id`…) servent à relier les résultats au Data Warehouse.

La description détaillée de chaque fichier (variables, précautions, fuites de cible à éviter) est dans
`DICTIONNAIRE_DATASET.md` de la branche [`dataset-dwh`](../../tree/dataset-dwh).

Retour à la vue d'ensemble : branche [`main`](../../tree/main).

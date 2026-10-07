# Data Warehouse (modèle en constellation)

Tables du Data Warehouse produites par `build_dataset.py` (branche `main`) à partir de
[`data-cleaned`](../../tree/data-cleaned) et [`data-external`](../../tree/data-external).
Le schéma (diagramme, clés primaires / étrangères, script SQL) est dans la branche [`dwh-schema`](../../tree/dwh-schema).

| Table | Type | Lignes |
|---|---|---|
| `dim_client.csv` | Dimension | 82 |
| `dim_document.csv` | Dimension | 12 543 |
| `dim_fournisseur.csv` | Dimension | 116 |
| `dim_geographie.csv` | Dimension | 12 |
| `dim_paiement.csv` | Dimension | 7 |
| `dim_produit.csv` | Dimension | 6 842 |
| `dim_temps.csv` | Dimension | 487 |
| `dim_utilisateur.csv` | Dimension | 7 |
| `fait_achats.csv` | Fait | 6 980 |
| `fait_paiements.csv` | Fait | 10 899 |
| `fait_stock_actuel.csv` | Fait | 6 842 |
| `fait_stock_hebdo.csv` | Fait | 190 626 |
| `fait_stock_mouvements.csv` | Fait | 49 609 |
| `fait_ventes.csv` | Fait | 25 743 |

- **Grain de `fait_ventes`** : 1 produit vendu dans 1 document validé à 1 date ; mesures signées (retours en négatif).
- Les 24 factures qui refacturent des bons de livraison sont exclues (pas de double comptage du CA).
- Membres `-1` « non renseigné » : 100 % des clés étrangères retrouvent leur dimension.
- [`DICTIONNAIRE_DATASET.md`](DICTIONNAIRE_DATASET.md) : description de chaque table, lien besoin du cahier → table, règles appliquées
  (couvre aussi les jeux ML). [`controles_qualite.csv`](controles_qualite.csv) : contrôles du §7.1 du cahier.

Chargement PostgreSQL : voir `schema_dwh.sql` dans la branche `dwh-schema`.

Retour à la vue d'ensemble : branche [`main`](../../tree/main).

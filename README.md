# Schéma du Data Warehouse

Produit par `build_schema.py` (branche `main`), qui vérifie aussi que le dictionnaire correspond exactement aux
colonnes des tables de [`dataset-dwh`](../../tree/dataset-dwh).

![Schéma du DWH](schema_dwh_diagramme.png)

| Fichier | Contenu |
|---|---|
| `schema_dwh.pdf` | Diagramme (A3), matrice des liens faits × dimensions, liste des relations, dictionnaire de chaque table |
| `schema_dwh.html` | Même document en page web |
| `schema_dwh_diagramme.png` / `.svg` | Diagramme seul |
| `schema_dwh.sql` | `CREATE TABLE` PostgreSQL avec clés primaires et étrangères + commande de chargement des CSV |

Modèle : 6 tables de faits (ventes, achats, paiements, mouvements de stock, stock hebdomadaire, stock actuel)
partagent 8 dimensions (temps, produit, client, fournisseur, document, paiement, utilisateur, géographie).

Retour à la vue d'ensemble : branche [`main`](../../tree/main).

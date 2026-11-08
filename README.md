# Schéma du Data Warehouse – version B

Produit par `build_schema.py` (branche `main`), qui vérifie que la description correspond exactement aux colonnes des tables de [`dataset-dwh`](../../tree/dataset-dwh).

![Schéma du DWH](schema_dwh_diagramme.png)

| Fichier | Contenu |
|---|---|
| `schema_dwh.pdf` / `schema_dwh.html` | Descriptif détaillé : modèle, tables, relations, dictionnaire de chaque colonne, mesures Power BI, différences avec la version A, règles de chargement |
| `schema_dwh_diagramme.png` / `.svg` | Diagramme seul |
| `schema_dwh.sql` | `CREATE TABLE` PostgreSQL avec clés primaires, clés étrangères et clés métier |

Modèle : 5 tables de faits (ventes, encaissements, achats, décaissements, stock actuel) partagent 5 dimensions (temps, produit, client, fournisseur, paiement), reliées par des clés de substitution (SK). Le schéma est le modèle cible : les CSV de dataset-dwh portent encore les identifiants du logiciel, les SK seront attribuées au chargement. Période : 2024-09-30 → 2026-09-29 (réel jusqu'au 2025-04-30, synthétique ensuite).

Retour à la vue d'ensemble : branche [`main`](../../tree/main).

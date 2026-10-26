# Data Warehouse – version B (5 dimensions, 5 faits)

Tables produites par `build_dataset.py` (branche `main`) à partir de [`data-cleaned`](../../tree/data-cleaned) et [`data-external`](../../tree/data-external). Le schéma (diagramme, descriptif, script SQL) est dans la branche [`dwh-schema`](../../tree/dwh-schema).

**Période :** Données réelles du 30/09/2024 au 30/04/2025 (7 mois), prolongées par des données synthétiques jusqu'au 29/09/2026. Délimitation par la date : réel jusqu'au 30/04/2025 inclus, synthétique ensuite (aucune colonne dédiée).

| Table | Type | Lignes | Colonnes |
|---|---|---|---|
| `dim_temps.csv` | Dimension | 730 | DateKey, Date, Annee, Trimestre, Mois, SemaineISO, EstFerie |
| `dim_produit.csv` | Dimension | 6 842 | Product_Id, Libellé, Famille, Marque |
| `dim_client.csv` | Dimension | 82 | Company_Id, Nom, TypeClient, EstClientIdentifie |
| `dim_fournisseur.csv` | Dimension | 116 | Fournisseur_Id, Nom |
| `dim_paiement.csv` | Dimension | 6 | PaymentMode_Id, PaymentModeName |
| `fait_ventes.csv` | Fait | 91 015 | Id, Document_Id, DateKey, Product_Id, Company_Id, QuantiteVendue, Remise_HT, CA_HT, Cout_HT |
| `fait_achats.csv` | Fait | 23 738 | Id, Document_Id, DateKey, Product_Id, Fournisseur_Id, QuantiteAchetee, MontantAchat_HT |
| `fait_stock_actuel.csv` | Fait | 6 842 | Product_Id, DateKey, Quantity, QuantiteAlerte |
| `fait_encaissements.csv` | Fait | 38 738 | Id, Payment_Id, Document_Id, DateKey, PaymentMode_Id, Company_Id, Amount |
| `fait_decaissements.csv` | Fait | 1 629 | Id, Payment_Id, Document_Id, DateKey, PaymentMode_Id, Fournisseur_Id, Amount |

- Mesures Power BI : CA HT, quantité vendue, nombre de ventes, panier moyen, croissance, marge HT, clients actifs, stock disponible, ruptures, stock faible, montant encaissé, nombre de paiements, montant payé par client et par fournisseur, montant réglé par document, achats HT, quantité achetée, nombre de factures fournisseurs.
- [`DICTIONNAIRE_DATASET.md`](DICTIONNAIRE_DATASET.md) : description de chaque table et de chaque jeu ML, règles appliquées. [`controles_qualite.csv`](controles_qualite.csv) : contrôles du §7.1.
- Chargement PostgreSQL : `schema_dwh.sql` dans la branche `dwh-schema`.

Retour à la vue d'ensemble : branche [`main`](../../tree/main).

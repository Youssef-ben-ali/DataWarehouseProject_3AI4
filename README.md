# Scripts de nettoyage — un script par fichier source

Le nettoyage de [`clean_data.py`](../../tree/main) (branche `main`), découpé en **un script par fichier brut** :
`script_cleaning_<nom du fichier>.py`. Le code est le même, et les résultats sont identiques octet pour octet aux
fichiers de la branche [`data-cleaned`](../../tree/data-cleaned) (vérifié sur les 30 fichiers réels et les 11 fichiers
synthétiques).

## Contenu

| Script | Fichier(s) brut(s) | Fichier(s) nettoyé(s) |
|---|---|---|
| `script_cleaning_Produits.py` | `Produits - 24112025081625 (2).csv` | `products.csv` |
| `script_cleaning_ProductBrands.py` | `ProductBrands.csv` | `brands.csv` |
| `script_cleaning_ProductPrices.py` | `ProductPrices.csv` | `product_prices.csv` |
| `script_cleaning_Barcodes.py` | `Barcodes.csv` | `barcodes.csv` |
| `script_cleaning_ProductStocks.py` | `ProductStocks.csv` | `product_stocks.csv` |
| `script_cleaning_StockMovements.py` | `StockMovements.csv` | `stock_movements.csv` |
| `script_cleaning_InventaireItems.py` | `InventaireItems.csv` | `inventory_items.csv` |
| `script_cleaning_DocumentTypes.py` | `DocumentTypes.csv` | `document_types.csv` |
| `script_cleaning_Documents.py` | `Documents.csv` | `documents.csv` |
| `script_cleaning_documentItemm.py` | `documentItemm.csv` | `document_items.csv` |
| `script_cleaning_RelatedDocuments.py` | `RelatedDocuments.csv` | `related_documents.csv` |
| `script_cleaning_DocumentsReports.py` | `DocumentsReports.csv` | `document_reports.csv` |
| `script_cleaning_ItemTaxes.py` | `ItemTaxes.csv` | `item_taxes.csv` |
| `script_cleaning_CompaniesList.py` | `CompaniesList.csv` | `companies.csv` |
| `script_cleaning_Clients.py` | `Clients - 24112025081756 (3).csv` | `customers.csv` |
| `script_cleaning_Fournisseurs.py` | `Fournisseurs - 24112025081816 (2).csv` | `suppliers.csv` |
| `script_cleaning_Transactions.py` | `Transactions.csv` | `transactions.csv` |
| `script_cleaning_TransactionPayments.py` | `TransactionPayments.csv` | `transaction_payments.csv` |
| `script_cleaning_PaymentsList_Payment.py` | `PaymentsList.csv` + `Payment.csv` (fusionnés) | `payments.csv` |
| `script_cleaning_TresoreriePayments.py` | `TresoreriePayments.csv` | `treasury_payments.csv` |
| `script_cleaning_CaisseOperations.py` | `CaisseOperations.csv` | `cash_operations.csv` |
| `script_cleaning_DomainEvents.py` | `DomainEvents.csv` | `treasury_events.csv`, `cash_register_events.csv`, `registers_and_bank_accounts.csv` |
| `script_cleaning_Events.py` | `Events.csv` | `audit_events.csv` |
| `script_cleaning_users_csv.py` | `users_csv.csv` | `users.csv` |
| `script_cleaning_users_settings_csv.py` | `users_settings_csv.csv` | `app_settings.csv` |
| `script_cleaning_Permissions.py` | `Permissions.csv` | `permissions.csv` |
| `script_cleaning_taxRates.py` | `taxRates.csv` | `tax_rates.csv` |
| `script_cleaning_ApplicableTaxes.py` | `ApplicableTaxes.csv` | `applicable_taxes.csv` |

28 scripts pour les 29 fichiers bruts : `PaymentsList.csv` et `Payment.csv` se recouvrent (10 168 paiements communs)
et sont fusionnés par un seul script.

Deux fichiers complètent les scripts :

- `cleaning_commun.py` contient les règles appliquées à tous les fichiers : détection de l'encodage et du séparateur,
  virgule décimale → point, dates au format ISO, booléens `true / false`, colonnes vides ou constantes supprimées,
  écriture en UTF-8. Il contient aussi les tables de correspondance partagées (produit, caisses, comptes bancaires).
- `run_all_cleaning.py` lance tous les scripts dans l'ordre et écrit `cleaned/CLEANING_REPORT.md`, comme
  `python clean_data.py`.

`Clients`, `Fournisseurs` et `Documents` ont besoin d'une table d'un autre fichier (codes des sociétés, types de
document) : leur script rejoue d'abord `script_cleaning_CompaniesList.py` ou `script_cleaning_DocumentTypes.py`.

## Lancer un script

Les scripts attendent les dossiers `fichiers/` (branche `data-original`) et `cleaned/` à côté d'eux, ou dans le
dossier parent quand cette branche est montée comme sous-dossier du dépôt :

```bash
git worktree add scripts_cleaning script-cleaning
python scripts_cleaning/script_cleaning_documentItemm.py
python scripts_cleaning/script_cleaning_Documents.py --synthetique   # données générées -> cleaned/synthetique/
python scripts_cleaning/run_all_cleaning.py                          # tous les fichiers + rapport
```

Chaque script affiche le détail de ses étapes, repris dans `cleaned/CLEANING_REPORT.md`. L'option `--synthetique`
ne concerne que les 11 fichiers générés par `generate_external_data.py`.

Seule la bibliothèque standard Python est utilisée.

Retour à la vue d'ensemble : branche [`main`](../../tree/main).

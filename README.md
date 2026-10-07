# Données nettoyées

Copies nettoyées des fichiers de [`data-original`](../../tree/data-original), produites par `clean_data.py`
(branche `main`). **Chaque action appliquée à chaque fichier est détaillée dans [`CLEANING_REPORT.md`](CLEANING_REPORT.md).**

Règles communes :
- UTF-8, séparateur virgule, décimale `.`, dates ISO `AAAA-MM-JJ [HH:MM]`, booléens `true` / `false` ;
- **noms de colonnes d'origine conservés** ; les colonnes ajoutées suivent le style du logiciel
  (`Product_Id`, `IsValidated`…) et les valeurs extraites d'un JSON sont nommées `<Colonne>_<clé>` (ex. `Extra_cump`) ;
- colonnes 100 % vides ou toujours à 0 supprimées, doublons exacts retirés ;
- valeurs douteuses **signalées** par une colonne, jamais modifiées en silence ;
- mots de passe, e-mails et téléphones retirés.

| Fichier | Lignes | Taille |
|---|---|---|
| `app_settings.csv` | 86 | 4 Ko |
| `applicable_taxes.csv` | 6 428 | 218 Ko |
| `audit_events.csv` | 82 585 | 23.0 Mo |
| `barcodes.csv` | 6 443 | 243 Ko |
| `brands.csv` | 203 | 3 Ko |
| `cash_operations.csv` | 9 707 | 1.6 Mo |
| `cash_register_events.csv` | 973 | 121 Ko |
| `companies.csv` | 156 | 9 Ko |
| `customers.csv` | 93 | 8 Ko |
| `document_items.csv` | 38 705 | 3.9 Mo |
| `document_reports.csv` | 28 185 | 591 Ko |
| `document_types.csv` | 15 | 1 Ko |
| `documents.csv` | 12 542 | 2.2 Mo |
| `inventory_items.csv` | 6 777 | 103 Ko |
| `item_taxes.csv` | 37 707 | 1.3 Mo |
| `payments.csv` | 10 899 | 1.4 Mo |
| `permissions.csv` | 104 | 12 Ko |
| `product_prices.csv` | 14 756 | 482 Ko |
| `product_stocks.csv` | 6 842 | 161 Ko |
| `products.csv` | 7 792 | 1.2 Mo |
| `registers_and_bank_accounts.csv` | 10 | 1 Ko |
| `related_documents.csv` | 864 | 14 Ko |
| `stock_movements.csv` | 49 609 | 6.7 Mo |
| `suppliers.csv` | 118 | 9 Ko |
| `tax_rates.csv` | 28 | 1 Ko |
| `transaction_payments.csv` | 10 962 | 267 Ko |
| `transactions.csv` | 12 523 | 614 Ko |
| `treasury_events.csv` | 21 743 | 8.2 Mo |
| `treasury_payments.csv` | 10 168 | 1.3 Mo |
| `users.csv` | 7 | 0 Ko |

Retour à la vue d'ensemble : branche [`main`](../../tree/main).

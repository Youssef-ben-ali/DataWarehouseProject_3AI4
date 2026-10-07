# Données originales (brutes)

Les **29 fichiers CSV** exportés de la base du logiciel de gestion du drugstore, **à l'identique** de l'export reçu
(aucune modification, fins de ligne et encodages d'origine conservés).

- Période couverte : 30/09/2024 → 30/04/2025.
- Formats hétérogènes : séparateurs `;` ou `,`, encodages UTF-8 / Windows-1252 / DOS 850, dates US et FR.
- Le guide détaillé de chaque fichier et de leurs liens est dans `docs/Dataset_Guide_Health_Retailers.pdf` (branche `main`).
- La version nettoyée est dans la branche [`data-cleaned`](../../tree/data-cleaned).

| Fichier | Lignes | Taille | Contenu |
|---|---|---|---|
| `ApplicableTaxes.csv` | 6 428 | 229 Ko | Configuration : taxe applicable par produit / document |
| `Barcodes.csv` | 6 444 | 171 Ko | Code-barres (EAN) de chaque produit |
| `CaisseOperations.csv` | 9 707 | 1.7 Mo | Mouvements dans les caisses enregistreuses |
| `Clients - 24112025081756 (3).csv` | 93 | 13 Ko | Clients nommés (particuliers et laboratoires) |
| `CompaniesList.csv` | 156 | 19 Ko | Table technique clients + fournisseurs (Company_Id) |
| `documentItemm.csv` | 38 705 | 11.6 Mo | Lignes de documents (produit, quantité, prix, remise) |
| `Documents.csv` | 12 542 | 2.3 Mo | En-tête de chaque document de vente / d'achat |
| `DocumentsReports.csv` | 11 975 | 9.9 Mo | Cache technique de rapports (JSON) |
| `DocumentTypes.csv` | 15 | 2 Ko | Signification des types de documents (vente, achat, retour…) |
| `DomainEvents.csv` | 21 743 | 9.8 Mo | Journal d'événements de la trésorerie (caisses, paiements, écarts) |
| `Events.csv` | 82 585 | 20.4 Mo | Journal d'audit des produits, stocks et prix |
| `Fournisseurs - 24112025081816 (2).csv` | 118 | 15 Ko | Fournisseurs |
| `InventaireItems.csv` | 6 777 | 151 Ko | Lignes d'inventaire physique |
| `ItemTaxes.csv` | 37 707 | 2.2 Mo | Détail de TVA par ligne de document |
| `Payment.csv` | 10 899 | 1.1 Mo | Paiements (doublon partiel de PaymentsList) |
| `PaymentsList.csv` | 10 280 | 1.1 Mo | Paiements avec moyen de paiement |
| `Permissions.csv` | 104 | 12 Ko | Droits d'accès des utilisateurs (configuration) |
| `ProductBrands.csv` | 212 | 3 Ko | Marques |
| `ProductPrices.csv` | 14 756 | 473 Ko | Listes de prix par produit |
| `ProductStocks.csv` | 6 842 | 115 Ko | Stock actuel par produit |
| `Produits - 24112025081625 (2).csv` | 7 800 | 1.2 Mo | Catalogue produits (famille, marque, prix) |
| `RelatedDocuments.csv` | 864 | 15 Ko | Liens entre documents (factures ↔ bons de livraison) |
| `StockMovements.csv` | 49 609 | 5.9 Mo | Chaque mouvement de stock |
| `taxRates.csv` | 28 | 1 Ko | Taux de taxe (configuration) |
| `TransactionPayments.csv` | 10 962 | 267 Ko | Pont transactions ↔ paiements |
| `Transactions.csv` | 12 523 | 559 Ko | Transaction commerciale par document (client, payé ou non) |
| `TresoreriePayments.csv` | 10 280 | 1.2 Mo | Affectation des paiements aux caisses / comptes bancaires |
| `users_csv.csv` | 7 | 2 Ko | Utilisateurs du logiciel (contient les hachages de mots de passe d'origine) |
| `users_settings_csv.csv` | 95 | 36 Ko | Paramètres du logiciel (configuration) |

Retour à la vue d'ensemble : branche [`main`](../../tree/main).

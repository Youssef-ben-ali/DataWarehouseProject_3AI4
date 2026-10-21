"""
Lance tous les scripts script_cleaning_*.py dans l'ordre et écrit cleaned/CLEANING_REPORT.md.
Même résultat que `python clean_data.py` (branche main).

    python run_all_cleaning.py
    python run_all_cleaning.py --synthetique
"""
import cleaning_commun as C
from cleaning_commun import *  # noqa: F401,F403
from script_cleaning_DocumentTypes import clean_document_types
from script_cleaning_CompaniesList import companies_table
from script_cleaning_Produits import clean_products
from script_cleaning_ProductBrands import clean_brands
from script_cleaning_Barcodes import clean_barcodes
from script_cleaning_ProductPrices import clean_prices
from script_cleaning_ProductStocks import clean_product_stocks
from script_cleaning_Clients import clean_customers
from script_cleaning_Fournisseurs import clean_suppliers
from script_cleaning_users_csv import clean_users
from script_cleaning_Documents import clean_documents
from script_cleaning_documentItemm import clean_document_items
from script_cleaning_ItemTaxes import clean_item_taxes
from script_cleaning_DocumentsReports import clean_document_reports
from script_cleaning_RelatedDocuments import clean_related_documents
from script_cleaning_Transactions import clean_transactions
from script_cleaning_TransactionPayments import clean_transaction_payments
from script_cleaning_PaymentsList_Payment import clean_payments
from script_cleaning_TresoreriePayments import clean_treasury_payments
from script_cleaning_CaisseOperations import clean_cash_operations
from script_cleaning_DomainEvents import clean_domain_events
from script_cleaning_StockMovements import clean_stock_movements
from script_cleaning_InventaireItems import clean_inventory
from script_cleaning_Events import clean_events
from script_cleaning_taxRates import clean_tax_rates
from script_cleaning_ApplicableTaxes import clean_applicabletaxes
from script_cleaning_Permissions import clean_permissions
from script_cleaning_users_settings_csv import clean_settings


def main():
    tmp = prepare_synthetic() if SYNTH else None
    build_lookups()
    clean_document_types()
    companies_table()
    clean_products()
    clean_brands()
    clean_barcodes()
    clean_prices()
    clean_product_stocks()
    clean_customers()
    clean_suppliers()
    clean_users()
    clean_documents()
    clean_document_items()
    clean_item_taxes()
    clean_document_reports()
    clean_related_documents()
    clean_transactions()
    clean_transaction_payments()
    clean_payments()
    clean_treasury_payments()
    clean_cash_operations()
    clean_domain_events()
    clean_stock_movements()
    clean_inventory()
    clean_events()
    clean_tax_rates()
    clean_applicabletaxes()
    clean_permissions()
    clean_settings()
    if SYNTH:
        finish_synthetic(tmp)
    write_report()
    for name, lg in REPORT.items():
        print(f"{name:38s} {lg.rows_in:>7,} -> {lg.rows_out:>7,} rows   {lg.cols_in:>3} -> {lg.cols_out:>3} cols")
    print(f"\nCleaned files and CLEANING_REPORT.md written to {C.OUT}")


if __name__ == "__main__":
    main()

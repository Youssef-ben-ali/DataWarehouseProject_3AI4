"""
Nettoyage de `ItemTaxes.csv` -> `cleaned/item_taxes.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_ItemTaxes.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_item_taxes():
    log = Log("item_taxes.csv", ["ItemTaxes.csv"], "VAT detail per document line (optional – VAT already on each line).")
    cols, recs, _ = read("ItemTaxes.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    log("Column `TotalHt` actually contains the TAX amount (e.g. base 27.40 × 19 % = 5.21), not a total excl. VAT "
        "– the original name is kept, be careful when using it.")
    cols, recs = select(recs, [("Id", "item_tax_id"), ("DocumentItem_Id", "item_id"), ("Tax_Id", "tax_id"),
                               ("TaxRate_Id", "tax_rate_id"), ("Rate", "rate_pct"),
                               ("CalculationMethod", "calculation_method"), ("Base", "base_ht"),
                               ("TotalHt", "tax_amount"), ("Type", "type")], log,
                        "the `Sum…` columns duplicate base and amount with more decimals")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_item_taxes)

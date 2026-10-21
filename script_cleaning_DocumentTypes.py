"""
Nettoyage de `DocumentTypes.csv` -> `cleaned/document_types.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_DocumentTypes.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_document_types():
    log = Log("document_types.csv", ["DocumentTypes.csv"], "Meaning of every document type (dimension Dim_DocType).")
    cols, recs, _ = read("DocumentTypes.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        r["label_en"], r["flow"] = DOC_TYPE_EN.get(r["Id"], ("", ""))
    log("Added `label_en` (English name) and `flow` (SALE / SALE_RETURN / PURCHASE / PURCHASE_RETURN / QUOTE / ORDER / "
        "STOCK_IN / STOCK_OUT) so sales and purchases can be separated with one filter.")
    LK["doc_types"] = {r["Id"]: r for r in recs}
    cols, recs = select(recs, [("Id", "document_type_id"), ("Name", "name"), ("label_en", "label_en"),
                               ("flow", "flow"), ("StockFactor", "stock_factor"), ("IsSellType", "is_sell_type"),
                               ("IsPayable", "is_payable"), ("IsRefund", "is_refund"),
                               ("IsDeliverable", "is_deliverable"), ("IsEnabled", "is_enabled")], log,
                        "UI icon path, translation key, invoice footer text, internal priorities")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_document_types)

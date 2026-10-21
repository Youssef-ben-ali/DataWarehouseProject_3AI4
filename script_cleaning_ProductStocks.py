"""
Nettoyage de `ProductStocks.csv` -> `cleaned/product_stocks.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_ProductStocks.py
    python script_cleaning_ProductStocks.py --synthetique   # données générées -> cleaned/synthetique/
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_product_stocks():
    log = Log("product_stocks.csv", ["ProductStocks.csv"], "Current stock level per product (snapshot at export date).")
    cols, recs, _ = read("ProductStocks.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    same = all(r["Quantity"] == r["TotalQuantity"] for r in recs)
    stores = Counter(r["Stock_Id"] for r in recs)
    if same:
        log("`TotalQuantity` is identical to `Quantity` on every row (single store) → dropped.")
    log(f"`Stock_Id` values: {dict(stores)} → only one store/warehouse, column dropped.")
    neg = 0
    for r in recs:
        q = fnum(r["Quantity"], 0)
        r["Quantity"] = fmt(q, 3)
        r["stock_status"] = "NEGATIVE" if q < 0 else "OUT_OF_STOCK" if q == 0 else "IN_STOCK"
        neg += q < 0
    log(f"Added `stock_status` (IN_STOCK / OUT_OF_STOCK / NEGATIVE). {neg} products have a negative stock "
        "(sold before the purchase was recorded) – flagged, not changed.")
    cols, recs = select(recs, [("Id", "product_stock_id"), ("Product_Id", "product_id"),
                               ("Quantity", "quantity"), ("stock_status", "stock_status")], log)
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_product_stocks)

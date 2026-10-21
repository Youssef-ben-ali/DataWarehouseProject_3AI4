"""
Nettoyage de `documentItemm.csv` -> `cleaned/document_items.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_documentItemm.py
    python script_cleaning_documentItemm.py --synthetique   # données générées -> cleaned/synthetique/
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_document_items():
    log = Log("document_items.csv", ["documentItemm.csv"],
              "One row per product line of every document – the grain of Fact_Sales / Fact_Purchases.")
    cols, recs, _ = read("documentItemm.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        r["Description"] = strip_html(r["Description"])
        r["product_id"] = LK["stock_to_product"].get(r["ProductStock_Id"], "")
    log("Removed the HTML formatting in `Description` (`<p style=…><span …>NAME</span></p>`) → plain `product_name`.")
    log("Added `product_id` through ProductStocks (product_stock_id → product_id).")
    log("`PrixHt` is the unit price BEFORE discount but `PrixTtc` is the unit price AFTER discount "
        "(34.25 × 1.19 × 0.80 = 32.61) – be careful when using them together.")
    bad = 0
    for r in recs:
        q, p, d, tot = (fnum(r["Quantity"], 0), fnum(r["PrixHt"], 0),
                        fnum(r.get("DiscountPourcentage"), 0) or 0, fnum(r["PrixTotalHt"], 0))
        if abs(q * p * (1 - d / 100) - tot) > 0.05:
            bad += 1
        for c in ("Quantity", "PrixHt", "Tva", "DiscountPourcentage", "PrixTotalHt", "TotalTva",
                  "PrixTotalTtc", "PrixTtc", "SumDiscountTotal"):
            if r.get(c):
                r[c] = fmt(fnum(r[c]), 4)
    log(f"Checked total_ht = quantity × unit_price_ht × (1 − discount %): {bad:,} lines differ by more than 0.05 "
        "(rounding / manual price) – kept as is.")
    cols, recs = select(recs, [
        ("Id", "item_id"), ("Document_Id", "document_id"), ("DisplayOrder", "line_number"),
        ("ProductStock_Id", "product_stock_id"), ("product_id", "product_id"), ("Description", "product_name"),
        ("Quantity", "quantity"), ("PrixHt", "unit_price_ht"), ("PrixTtc", "unit_price_ttc"),
        ("Tva", "vat_rate_pct"), ("DiscountPourcentage", "discount_pct"), ("SumDiscountTotal", "discount_amount_ht"),
        ("PrixTotalHt", "total_ht"), ("TotalTva", "total_vat"), ("PrixTotalTtc", "total_ttc"),
    ], log, "the `Sum…` columns repeat the line totals with more decimals (SumPrixTotalHt, SumTotalTva, SumPrixTotalTtc, "
            "SumPrixNetHt, SumPrixNetTtc, SumQuantityUnit…); `Extra` is always `{}`")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_document_items)

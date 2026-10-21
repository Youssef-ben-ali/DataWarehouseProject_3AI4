"""
Nettoyage de `ProductPrices.csv` -> `cleaned/product_prices.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_ProductPrices.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_prices():
    log = Log("product_prices.csv", ["ProductPrices.csv"], "Price lists per product.")
    cols, recs, _ = read("ProductPrices.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    lists = Counter(r["PriceName_Id"] for r in recs)
    log(f"Price lists present (`price_list_id` → rows): {dict(lists)}. Price list 1 is the retail price used at the till.")
    recomputed = 0
    for r in recs:
        if not r.get("ProfitMargin"):
            r["ProfitMargin"] = ""
        r["vat_rate_pct"] = ""
        ht, ttc = fnum(r["PriceHt"]), fnum(r["PriceTtc"])
        if ht and ttc and ht > 0:
            r["vat_rate_pct"] = fmt(round(100 * (ttc / ht - 1), 1), 1)
            recomputed += 1
    log(f"Added `vat_rate_pct` deduced from TTC/HT ({recomputed:,} rows).")
    cols, recs = select(recs, [("Id", "price_id"), ("Product_Id", "product_id"), ("PriceName_Id", "price_list_id"),
                               ("PriceHt", "price_ht"), ("PriceTtc", "price_ttc"), ("vat_rate_pct", "vat_rate_pct"),
                               ("UseTva", "use_vat"), ("ProfitMargin", "profit_margin_pct")], log)
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_prices)

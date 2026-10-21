"""
Nettoyage de `ProductBrands.csv` -> `cleaned/brands.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_ProductBrands.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_brands():
    log = Log("brands.csv", ["ProductBrands.csv"], "Brand list (dimension Dim_Brand).")
    cols, recs, _ = read("ProductBrands.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        r["BrandName"] = norm_name(r["BrandName"])
    log("Brand names upper-cased, accents removed and inner spaces collapsed (same rule as products.brand, so they join).")
    seen, out = {}, []
    for r in recs:
        if r["BrandName"] in seen:
            continue
        seen[r["BrandName"]] = r["Id"]
        out.append(r)
    if len(out) < len(recs):
        log(f"Removed {len(recs) - len(out)} duplicate brand name(s) (kept the lowest id).")
    cols, recs = select(out, [("Id", "brand_id"), ("BrandName", "brand_name")], log)
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_brands)

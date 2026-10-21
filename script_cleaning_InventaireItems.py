"""
Nettoyage de `InventaireItems.csv` -> `cleaned/inventory_items.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_InventaireItems.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_inventory():
    log = Log("inventory_items.csv", ["InventaireItems.csv"], "Physical inventory count lines.")
    cols, recs, _ = read("InventaireItems.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    log("`FinalRealQuantity` (counted quantity) is 100 % empty: the physical count was never entered, so no "
        "counted-vs-theoretical difference can be computed. The file is only a snapshot of the theoretical stock.")
    cols, recs = select(recs, [("Id", "inventory_item_id"), ("Inventaire_Id", "inventory_id"),
                               ("Product_Id", "product_id"), ("TheoricalQuantity", "theoretical_quantity"),
                               ("FinalRealQuantity", "counted_quantity"),                                ("Movements", "movements")], log, "`Stock_Id` single store")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_inventory)

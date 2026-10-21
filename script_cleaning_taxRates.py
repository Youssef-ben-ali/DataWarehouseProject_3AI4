"""
Nettoyage de `taxRates.csv` -> `cleaned/tax_rates.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_taxRates.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_tax_rates():
    log = Log("tax_rates.csv", ["taxRates.csv"], "Tax rate definitions (reference).")
    cols, recs, _ = read("taxRates.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        r["is_active"] = "true" if not r.get("EndDate") else "false"
    log("Added `is_active` (no end date). Only the VAT rates 7 %, 13 %, 19 % (Tax_Id 3) appear on sales lines.")
    cols, recs = select(recs, [("Id", "tax_rate_id"), ("Name", "name"), ("Tax_Id", "tax_id"), ("Rate", "rate"),
                               ("Country", "country_code"), ("CalculationMethod", "calculation_method"),
                               ("StartDate", "start_date"), ("EndDate", "end_date"), ("is_active", "is_active")], log)
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_tax_rates)

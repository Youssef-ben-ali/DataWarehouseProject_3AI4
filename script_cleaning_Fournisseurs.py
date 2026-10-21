"""
Nettoyage de `Fournisseurs - 24112025081816 (2).csv` -> `cleaned/suppliers.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_Fournisseurs.py

Prérequis : script_cleaning_CompaniesList.py (companies_table) est rejoué en mémoire, car ce fichier a besoin de sa table de correspondance.
"""
from cleaning_commun import *  # noqa: F401,F403
from script_cleaning_CompaniesList import companies_table


def clean_suppliers():
    log = Log("suppliers.csv", ["Fournisseurs - 24112025081816 (2).csv"], "Suppliers (dimension Dim_Supplier).")
    cols, recs, _ = read("Fournisseurs - 24112025081816 (2).csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        _, r["Nom"] = split_partner_name(r["Nom"])
        r["company_id"] = LK["company_by_code"].get(r["Code"], "")
        for c in ("Solde", "Solde initial"):
            if c in r:
                r[c] = fmt(fnum(r[c], 0), 3)
        r["Ville"] = collapse(r["Ville"]).upper()
        r["Pays"] = collapse(r["Pays"]).upper()
    log("Removed the `1.` numbering in front of every supplier name; city and country upper-cased.")
    matched = sum(bool(r["company_id"]) for r in recs)
    log(f"Added `company_id` by matching the supplier code with companies.csv ({matched}/{len(recs)} matched). "
        "The others have no entry in CompaniesList.csv, so they cannot be linked to any transaction.")
    cols, recs = select(recs, [("company_id", "company_id"), ("Code", "supplier_code"), ("Nom", "supplier_name"),
                               ("Adresse", "address"), ("Code postal", "postal_code"), ("Ville", "city"),
                               ("Pays", "country"), ("Solde", "balance"), ("Solde initial", "initial_balance")], log,
                        "e-mail removed (contact data); website empty")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_suppliers, prerequisites=[companies_table])

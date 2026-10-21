"""
Nettoyage de `CompaniesList.csv` -> `cleaned/companies.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_CompaniesList.py
"""
from cleaning_commun import *  # noqa: F401,F403


def companies_table():
    log = Log("companies.csv", ["CompaniesList.csv"],
              "Every customer and supplier with the numeric `company_id` used by transactions and payments.")
    cols, recs, _ = read("CompaniesList.csv", log)
    name_col = [c for c in cols if "Name" in c][0]
    for r in recs:
        r[name_col] = r[name_col].strip().strip("|").strip()
        if set(r[name_col]) <= set("-"):
            r[name_col] = ""
    log("Removed the Markdown table pipes `|` and padding that surrounded every name (and in the header `| Name |`).")
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        if r["Id"] == "2":
            r[name_col] = "CLIENT COMPTOIR (ANONYME)"
            r["Code"] = "WALKIN"
        r[name_col] = collapse(r[name_col])
        r["company_type"] = {"1": "CUSTOMER", "2": "SUPPLIER"}.get(r["CompanyType_Id"], r["CompanyType_Id"])
    log("Company 2 had a lost name (`|-----|`) and code `__part__`: it is the generic walk-in customer used by most "
        "counter sales → renamed `CLIENT COMPTOIR (ANONYME)`, code `WALKIN`.")
    log("Added `company_type` (1 → CUSTOMER, 2 → SUPPLIER).")
    log("WARNING: the names in this file do NOT match the names in the Clients / Fournisseurs files for the same code "
        "(e.g. CL0001 = `Santélys Pharma` here but `Julien Moreau` in Clients; 0/47 customer names and 1/85 supplier names "
        "agree). Each file was anonymised separately. Join on `code`, never on name; for reporting, prefer the names in "
        "customers.csv / suppliers.csv.")
    cols, recs = select(recs, [("Id", "company_id"), ("Code", "code"), (name_col, "name"),
                               ("company_type", "company_type"), ("CompanyType_Id", "company_type_id"),
                               ("IsGuest", "is_guest"), ("IsRemoved", "is_removed")], log,
                        "technical columns Id3–Id7 and empty trailing columns; phone/e-mail removed as personal "
                        "contact data (GDPR) – they remain in the original file")
    LK["company_by_code"] = {r["Code"]: r["Id"] for r in recs}
    write(cols, recs, log)


if __name__ == "__main__":
    run(companies_table)

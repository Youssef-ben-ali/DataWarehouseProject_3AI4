"""
Nettoyage de `Clients - 24112025081756 (3).csv` -> `cleaned/customers.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_Clients.py

Prérequis : script_cleaning_CompaniesList.py (companies_table) est rejoué en mémoire, car ce fichier a besoin de sa table de correspondance.
"""
from cleaning_commun import *  # noqa: F401,F403
from script_cleaning_CompaniesList import companies_table


def clean_customers():
    log = Log("customers.csv", ["Clients - 24112025081756 (3).csv"], "Named customers (dimension Dim_Customer).")
    cols, recs, _ = read("Clients - 24112025081756 (3).csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    types = Counter()
    for r in recs:
        t, n = split_partner_name(r["Nom"])
        r["customer_type"] = {"Client particulier": "INDIVIDUAL", "Laboratoire": "LABORATORY"}.get(t, t.upper() or "UNKNOWN")
        types[r["customer_type"]] += 1
        r["Nom"] = n
        r["company_id"] = LK["company_by_code"].get(r["Code"], "")
        for c in ("Solde", "Solde initial"):
            if c in r:
                r[c] = fmt(fnum(r[c], 0), 3)
        r["Ville"] = collapse(r["Ville"]).upper()
        r["Pays"] = collapse(r["Pays"]).upper()
    log("Split `Nom` (`1. Client particulier — Julien Moreau`) into `customer_type` and `customer_name`; "
        f"removed the `1.` numbering. Types: {dict(types)}.")
    log("City and country upper-cased; postal code kept as text.")
    matched = sum(bool(r["company_id"]) for r in recs)
    log(f"Added `company_id` by matching the customer code with companies.csv ({matched}/{len(recs)} matched). "
        "The others have no entry in CompaniesList.csv, so they cannot be linked to any transaction.")
    cols, recs = select(recs, [("company_id", "company_id"), ("Code", "customer_code"), ("Nom", "customer_name"),
                               ("customer_type", "customer_type"), ("Adresse", "address"),
                               ("Code postal", "postal_code"), ("Ville", "city"), ("Pays", "country"),
                               ("Solde", "balance"), ("Solde initial", "initial_balance")], log,
                        "e-mail removed as personal data (GDPR); website / trade register empty")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_customers, prerequisites=[companies_table])

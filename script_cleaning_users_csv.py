"""
Nettoyage de `users_csv.csv` -> `cleaned/users.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_users_csv.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_users():
    log = Log("users.csv", ["users_csv.csv"], "Employees / cashiers (dimension Dim_Employee).")
    cols, recs, _ = read("users_csv.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        try:
            r["default_register_id"] = json.loads(r.get("Tresorerie") or "{}").get("defaultCaisseId", "").upper()
        except ValueError:
            r["default_register_id"] = ""
        r["is_staff"] = "false" if r["Id"] in ("1", "2") else "true"
    log("SECURITY: removed `Password` and `PasswordSalt` (password hashes must never reach the warehouse).")
    log("Parsed the `Tresorerie` JSON into `default_register_id`. Added `is_staff` (false for Administrateur and Système accounts).")
    cols, recs = select(recs, [("Id", "user_id"), ("FullName", "full_name"), ("UserName", "user_name"),
                               ("is_staff", "is_staff"), ("default_register_id", "default_register_id")], log,
                        "password hashes and raw JSON")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_users)

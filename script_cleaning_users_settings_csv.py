"""
Nettoyage de `users_settings_csv.csv` -> `cleaned/app_settings.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_users_settings_csv.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_settings():
    log = Log("app_settings.csv", ["users_settings_csv.csv"], "Software settings (configuration).")
    cols, recs, _ = read("users_settings_csv.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    big = [r["SettingName"] for r in recs if len(r["Value"]) > 300]
    recs = [r for r in recs if len(r["Value"]) <= 300]
    log(f"Removed {len(big)} setting(s) whose value is a large report/print template or base64 logo image "
        f"(> 300 characters): {', '.join(big)}.")
    log("Kept settings worth quoting in the report: `Country = 3`, `InvoiceCurrencySymb = DT` (Tunisian dinar) – evidence "
        "of the Tunisian origin of the software. Not needed for the warehouse.")
    cols, recs = select(recs, [("Id", "setting_id"), ("SettingName", "name"), ("Value", "value")], log)
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_settings)

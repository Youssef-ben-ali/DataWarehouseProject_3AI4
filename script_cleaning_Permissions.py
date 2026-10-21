"""
Nettoyage de `Permissions.csv` -> `cleaned/permissions.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_Permissions.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_permissions():
    clean_generic("Permissions.csv", "permissions.csv", "User access rights (software configuration).",
                  "Configuration only (GUID codes of screens and operations) – not needed for analysis.")


if __name__ == "__main__":
    run(clean_permissions)

"""
Nettoyage de `ApplicableTaxes.csv` -> `cleaned/applicable_taxes.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_ApplicableTaxes.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_applicabletaxes():
    clean_generic("ApplicableTaxes.csv", "applicable_taxes.csv", "Which tax applies to which product / document (software configuration).",
                  "Configuration only – kept for completeness, not needed for the warehouse.")


if __name__ == "__main__":
    run(clean_applicabletaxes)

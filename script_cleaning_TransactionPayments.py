"""
Nettoyage de `TransactionPayments.csv` -> `cleaned/transaction_payments.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_TransactionPayments.py
    python script_cleaning_TransactionPayments.py --synthetique   # données générées -> cleaned/synthetique/
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_transaction_payments():
    log = Log("transaction_payments.csv", ["TransactionPayments.csv"],
              "Bridge table transaction ↔ payment (a sale can be paid with several payments).")
    cols, recs, _ = read("TransactionPayments.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    cols, recs = select(recs, [("Id", "transaction_payment_id"), ("Transaction_Id", "transaction_id"),
                               ("Payment_Id", "payment_id"), ("Amount", "amount")], log)
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_transaction_payments)

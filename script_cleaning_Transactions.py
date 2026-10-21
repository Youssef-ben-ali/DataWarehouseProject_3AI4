"""
Nettoyage de `Transactions.csv` -> `cleaned/transactions.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_Transactions.py
    python script_cleaning_Transactions.py --synthetique   # données générées -> cleaned/synthetique/
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_transactions():
    log = Log("transactions.csv", ["Transactions.csv"],
              "One business transaction per sale/purchase: who (company) and paid or not.")
    cols, recs, _ = read("Transactions.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    walk = 0
    for r in recs:
        r["is_walk_in_customer"] = "true" if r["Company_Id"] == "2" else "false"
        walk += r["Company_Id"] == "2"
    unpaid = sum(r["IsPayed"] == "false" for r in recs)
    log(f"Added `is_walk_in_customer` (company 2 = anonymous counter customer): {walk:,} of {len(recs):,} transactions.")
    log(f"{unpaid:,} transactions are not (fully) paid (`is_paid = false`) – useful for the commercial-risk analysis.")
    cols, recs = select(recs, [("Id", "transaction_id"), ("Company_Id", "company_id"),
                               ("is_walk_in_customer", "is_walk_in_customer"), ("IsPayed", "is_paid"),
                               ("PayedAmount", "paid_amount"), ("IsDestocked", "is_destocked"),
                               ("IsRestocked", "is_restocked"), ("PaymentDocument_Id", "payment_document_id"),
                               ("DestockDocument_Id", "destock_document_id"),
                               ("RefundDocument_Id", "refund_document_id"),
                               ("RestockDocument_Id", "restock_document_id")], log)
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_transactions)

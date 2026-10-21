"""
Nettoyage de `TresoreriePayments.csv` -> `cleaned/treasury_payments.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_TresoreriePayments.py
    python script_cleaning_TresoreriePayments.py --synthetique   # données générées -> cleaned/synthetique/
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_treasury_payments():
    log = Log("treasury_payments.csv", ["TresoreriePayments.csv"],
              "Which cash register or bank account received each payment.")
    cols, recs, _ = read("TresoreriePayments.csv", log)
    cols, recs = standardize(cols, recs, log, "MDY")
    before = len(recs)
    recs = [r for r in recs if r["Removed"] != "true"]
    log(f"Removed {before - len(recs)} row(s) with `Removed = TRUE`.")
    for r in recs:
        r["CaisseId"] = r["CaisseId"].upper()
        r["register_name"] = register_name(r["CaisseId"])
        r["BankAccountId"] = r.get("BankAccountId", "").upper()
        b = LK["banks"].get(r["BankAccountId"])
        r["bank_account_name"] = f"{b[1]} {b[0]}" if b else ""
    log("Added `register_name` (the 6 cash registers are named after cashiers in the treasury events: "
        f"{', '.join(sorted(set(LK['registers'].values())))}) and `bank_account_name`.")
    cols, recs = select(recs, [("Id", "treasury_payment_id"), ("SalePaymentId", "payment_id"),
                               ("SaleRefundId", "refund_id"), ("Amount", "amount"), ("IsPurchase", "is_purchase"),
                               ("CaisseId", "register_id"), ("register_name", "register_name"),
                               ("BankAccountId", "bank_account_id"), ("bank_account_name", "bank_account_name"),
                               ("CreatedAtUtc", "created_at_utc"), ("CreatedBy", "created_by")], log,
                        "`Removed` (removed rows filtered)")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_treasury_payments)

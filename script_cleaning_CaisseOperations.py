"""
Nettoyage de `CaisseOperations.csv` -> `cleaned/cash_operations.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_CaisseOperations.py
    python script_cleaning_CaisseOperations.py --synthetique   # données générées -> cleaned/synthetique/
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_cash_operations():
    log = Log("cash_operations.csv", ["CaisseOperations.csv"], "Every movement in a cash register.")
    cols, recs, _ = read("CaisseOperations.csv", log)
    cols, recs = standardize(cols, recs, log, "MDY")
    same = all(r["TransactionId"] == r["PaymentId"] for r in recs)
    for r in recs:
        r["CaisseId"] = r["CaisseId"].upper()
        r["register_name"] = register_name(r["CaisseId"])
        r["is_cancelled"] = "true" if r.get("CancelledAtUtc") else "false"
    canc = sum(r["is_cancelled"] == "true" for r in recs)
    st = Counter(r["Status"] for r in recs)
    log(f"`PaymentId` is identical to `TransactionId` on every row ({same}) → kept once as `operation_ref`. Note: this "
        "GUID does not match any id in the other files; join on register + user + time instead.")
    log(f"Added `register_name` and `is_cancelled` ({canc} cancelled operations). Status values: {dict(st)}.")
    cols, recs = select(recs, [("Id", "operation_id"), ("CaisseId", "register_id"), ("register_name", "register_name"),
                               ("TransactionId", "operation_ref"), ("AddedAtUtc", "added_at_utc"),
                               ("AddedByUserId", "user_id"), ("Amount", "amount"), ("Status", "status"),
                               ("is_cancelled", "is_cancelled"), ("CancelledAtUtc", "cancelled_at_utc"),
                               ("CancelledByUserId", "cancelled_by"), ("DepositId", "deposit_id"),
                               ("WithdrawalId", "withdrawal_id")], log, "`PaymentId` duplicate of TransactionId")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_cash_operations)

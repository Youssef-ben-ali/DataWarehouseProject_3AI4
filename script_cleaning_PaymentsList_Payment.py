"""
Nettoyage de `PaymentsList.csv` + `Payment.csv` -> `cleaned/payments.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_PaymentsList_Payment.py
    python script_cleaning_PaymentsList_Payment.py --synthetique   # données générées -> cleaned/synthetique/
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_payments():
    log = Log("payments.csv", ["PaymentsList.csv", "Payment.csv"],
              "Every customer/supplier payment (fact table Fact_Payment). Merges the two overlapping payment files.")
    c1, pl, _ = read("PaymentsList.csv", log)
    c1, pl = standardize(c1, pl, log, "DMY")
    c2, py, _ = read("Payment.csv", log)
    c2, py = standardize(c2, py, log, "DMY")
    if SYNTH:                       # données synthétiques : PaymentsList seul, aucun paiement réel ajouté
        py = []
    by_id_py = {r["Id"]: r for r in py}
    ids_pl = {r["Id"] for r in pl}
    common = ids_pl & set(by_id_py)
    diff = sum(1 for r in pl if r["Id"] in by_id_py and fnum(r["Amount"]) != fnum(by_id_py[r["Id"]]["Amount"]))
    log(f"The two files overlap: {len(common):,} ids in common (amounts differ on {diff}). PaymentsList.csv is used as "
        f"the main source (it has `IsRemoved` and the method name); {len(set(by_id_py) - ids_pl):,} payments that exist only "
        f"in Payment.csv (mostly the first days, ids 1–1761) were appended. `used_amount` is taken from Payment.csv when available.")
    rows = []
    for r in pl:
        rows.append({**r, "source_file": "PaymentsList.csv", "UsedAmount": by_id_py.get(r["Id"], {}).get("UsedAmount", "")})
    for i, r in by_id_py.items():
        if i not in ids_pl:
            rows.append({**r, "IsRemoved": "false", "source_file": "Payment.csv"})
    removed = [r for r in rows if r.get("IsRemoved") == "true"]
    rows = [r for r in rows if r.get("IsRemoved") != "true"]
    log(f"Removed {len(removed)} payment(s) flagged `IsRemoved = VRAI` (cancelled in the software).")
    cash = 0
    for r in rows:
        r["PaymentMethodName"] = PAYMENT_MODES.get(r["PaymentMode_Id"], "")
        m = RE_DOCNUM.search(r.get("Description", ""))
        r["document_number"] = m.group(1) if m else ""
        r["is_purchase"] = "true" if "fournisseur" in r.get("Description", "").lower() else "false"
        try:
            e = json.loads(r.get("Extra") or "{}")
        except ValueError:
            e = {}
        r["cash_given"] = fmt(fnum(e.get("gA")), 3) if "gA" in e else ""
        r["change_returned"] = fmt(fnum(e.get("rA")), 3) if "rA" in e else ""
        cash += "gA" in e
    rows.sort(key=lambda r: int(r["Id"]))
    log("Rebuilt `PaymentMethodName` for every row from `PaymentMode_Id` (the original name column was filled for only ~6 % "
        "of rows); renamed `Cash.Tunisia` → `Cash`.")
    log("Extracted `document_number` (e.g. `VC0733/24`) from the free-text description "
        "`Paiement de la pièce : Vente Comptoir N° VC0733/24` → payments can be linked to documents.csv by number.")
    log(f"Parsed the `Extra` JSON into `cash_given` (gA) and `change_returned` (rA) for {cash:,} cash payments.")
    cols = [("Id", "payment_id"), ("PaymentDate", "payment_date"), ("Amount", "amount"), ("UsedAmount", "used_amount"),
            ("Company_Id", "company_id"), ("PaymentMode_Id", "payment_mode_id"), ("PaymentMethodName", "payment_method"),
            ("document_number", "document_number"), ("is_purchase", "is_purchase"), ("cash_given", "cash_given"),
            ("change_returned", "change_returned"), ("Description", "description"), ("source_file", "source_file")]
    cols, rows = select(rows, cols, log, "`IsRemoved` (removed rows filtered), raw `Extra` JSON (parsed)")
    write(cols, rows, log)


if __name__ == "__main__":
    run(clean_payments)

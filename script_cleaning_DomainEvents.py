"""
Nettoyage de `DomainEvents.csv` -> `cleaned/treasury_events.csv`, `cleaned/cash_register_events.csv`, `cleaned/registers_and_bank_accounts.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_DomainEvents.py
    python script_cleaning_DomainEvents.py --synthetique   # données générées -> cleaned/synthetique/
"""
import cleaning_commun as C
from cleaning_commun import *  # noqa: F401,F403


def clean_domain_events():
    log = Log("treasury_events.csv", ["DomainEvents.csv"], "Full event log of the treasury module.")
    text, _ = decode(C.SRC / "DomainEvents.csv")
    recs = read_domain_events()
    log.rows_in, log.cols_in = len(recs), 8
    log.orig_cols.update(recs[0].keys())
    log(f"Read `DomainEvents.csv`: {len(recs):,} rows. The file is MALFORMED: every whole line is wrapped in quotes "
        "and inner quotes are doubled, so a normal CSV reader sees a single column. Removed the outer quotes and "
        "un-doubled the inner ones before parsing into 8 columns. Re-encoded to UTF-8.")
    cols = list(recs[0].keys())
    cols, recs = standardize(cols, recs, log, "MDY")
    for r in recs:
        r["AggregateName"] = r["AggregateName"].replace("Tresorerie.", "")
        r["EventName"] = r["EventName"].replace("Tresorerie.", "")
        r["AggregateId"] = r["AggregateId"].upper()
        try:
            r["Data"] = json.dumps(json.loads(r["Data"]), ensure_ascii=False, separators=(",", ":"))
        except ValueError:
            pass
    log("Removed the `Tresorerie.` prefix from aggregate and event names; `data` JSON re-serialised compactly (valid JSON).")
    log("Event counts: " + ", ".join(f"{k} {v:,}" for k, v in Counter(r["EventName"] for r in recs).most_common()) + ".")
    ev_cols, ev = select(recs, [("Id", "event_id"), ("UtcTimestamp", "timestamp_utc"), ("AggregateName", "aggregate"),
                                ("AggregateId", "aggregate_id"), ("Version", "version"), ("EventName", "event_name"),
                                ("UserId", "user_id"), ("Data", "data")], log)
    write(ev_cols, ev, log)

    # derived: register open / close / discrepancy
    log2 = Log("cash_register_events.csv", ["DomainEvents.csv"],
               "Derived from treasury events: register openings, closings and cash discrepancies (for cash-control KPIs).")
    log2.rows_in, log2.cols_in = len(recs), 8
    out = []
    kinds = {"CaisseOpened": "OPEN", "CaisseClosed": "CLOSE", "CaisseDiscrepancyIdentified": "DISCREPANCY",
             "CaisseDiscrepancyApproved": "DISCREPANCY_APPROVED"}
    for r in recs:
        k = kinds.get(r["EventName"])
        if not k:
            continue
        d = json.loads(r["Data"])
        src = d.get("source") or {}
        out.append({
            "Id": r["Id"], "UtcTimestamp": r["UtcTimestamp"], "AggregateId": r["AggregateId"],
            "CaisseName": register_name(r["AggregateId"]), "UserId": r["UserId"], "EventName": r["EventName"],
            "EventType": k,
            "Data_balance": fmt(fnum(d.get("balance")), 3) if "balance" in d else "",
            "Data_expectedBalance": fmt(fnum(d.get("expectedBalance")), 3) if "expectedBalance" in d else "",
            "Data_foundBalance": fmt(fnum(d.get("foundBalance")), 3) if "foundBalance" in d else "",
            "Data_amount": fmt(fnum(d.get("amount")), 3) if k.startswith("DISCREPANCY") and "amount" in d else "",
            "DetectedAt": "OPENING" if "openCaisseOperationId" in src else "CLOSING" if "closeCaisseOperationId" in src else "",
        })
    log2(f"Kept only register events (OPEN, CLOSE, DISCREPANCY, DISCREPANCY_APPROVED) and flattened their JSON into "
         f"columns named <JsonColumn>_<jsonKey>: Data_balance, Data_expectedBalance, Data_foundBalance, Data_amount; "
         f"plus `EventType` (short code) and `DetectedAt` (OPENING / CLOSING) → {len(out):,} rows. Original columns "
         f"(Id, UtcTimestamp, AggregateId, UserId, EventName) keep their names.")
    log2("Added `CaisseName`. A discrepancy detected at OPENING with found_balance 0 usually means the cash was "
         "removed overnight (not a loss) – keep this in mind before reporting 'missing cash'.")
    write(list(out[0].keys()), out, log2)

    # derived: bank accounts & registers reference
    log3 = Log("registers_and_bank_accounts.csv", ["DomainEvents.csv"],
               "Reference list of the 6 cash registers and 4 bank accounts (names were only inside event JSON).")
    log3.rows_in, log3.cols_in = len(recs), 8
    ref = [{"AggregateId": k, "AggregateName": "Caisses.Caisse", "Data_name": v, "Data_bank": "",
            "Data_initialBalance": ""} for k, v in LK["registers"].items()]
    ref += [{"AggregateId": k, "AggregateName": "BankAccount", "Data_name": v[0], "Data_bank": v[1],
             "Data_initialBalance": fmt(fnum(v[2]), 3)} for k, v in LK["banks"].items()]
    log3("Extracted `CaisseAdded` and `BankAccountAdded` events into a small reference table so register / bank GUIDs "
         "in other files can be shown with a readable name.")
    write(["AggregateId", "AggregateName", "Data_name", "Data_bank", "Data_initialBalance"], ref, log3)


if __name__ == "__main__":
    run(clean_domain_events)

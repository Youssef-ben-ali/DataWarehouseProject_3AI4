"""
Nettoyage de `Documents.csv` -> `cleaned/documents.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_Documents.py
    python script_cleaning_Documents.py --synthetique   # données générées -> cleaned/synthetique/

Prérequis : script_cleaning_DocumentTypes.py (clean_document_types) est rejoué en mémoire, car ce fichier a besoin de sa table de correspondance.
"""
from cleaning_commun import *  # noqa: F401,F403
from script_cleaning_DocumentTypes import clean_document_types


def clean_documents():
    log = Log("documents.csv", ["Documents.csv"], "Header of every sale / purchase document (fact table header).")
    cols, recs, _ = read("Documents.csv", log)
    cols, recs = standardize(cols, recs, log, "MDY")
    bal = 0
    for r in recs:
        try:
            v = json.loads(r.get("Extra") or "{}").get("cosld")
        except ValueError:
            v = None
        r["customer_balance_before"] = fmt(fnum(v), 3) if v is not None else ""
        bal += v is not None
        t = LK["doc_types"].get(r["DocumentType_Id"], {})
        r["document_type"] = t.get("Name", "")
        r["flow"] = DOC_TYPE_EN.get(r["DocumentType_Id"], ("", ""))[1]
        r["is_validated"] = "true" if r["State"] == "1" else "false"
        r["payment_mode"] = PAYMENT_MODES.get(r.get("PaymentMode_Id", ""), "")
        r["DocumentNumber"] = r["DocumentNumber"].strip()
    log(f"Parsed the `Extra` JSON: key `cosld` = customer balance before the document → `customer_balance_before` ({bal:,} rows).")
    log("Added `document_type` (name) and `flow` (SALE / PURCHASE / …) from document_types.csv.")
    drafts = sum(r["is_validated"] == "false" for r in recs)
    log(f"Added `is_validated` from `State` (1 = validated, 0 = draft). {drafts} draft documents are kept but "
        "should be excluded from revenue.")
    log("Added `payment_mode` name from `PaymentMode_Id` (1 Cheque, 5 Bank card, 7 Credit, 11 Cash, 21 Tokens).")
    log("`document_date` has no time (always 00:00) – use `created_at` for the hour of the sale.")
    cols, recs = select(recs, [
        ("Id", "document_id"), ("DocumentNumber", "document_number"), ("DocumentDate", "document_date"),
        ("DocumentType_Id", "document_type_id"), ("document_type", "document_type"), ("flow", "flow"),
        ("State", "state"), ("is_validated", "is_validated"), ("Transaction_Id", "transaction_id"),
        ("PaymentMode_Id", "payment_mode_id"), ("payment_mode", "payment_mode"),
        ("ProductPriceName_Id", "price_list_id"), ("TotalHt", "total_ht_before_discount"),
        ("TotalDiscount", "total_discount"), ("TotalNetHt", "total_ht"), ("TotalTva", "total_vat"),
        ("TotalTtc", "total_ttc"), ("Timbre", "stamp_duty"), ("FinalPrice", "final_price"),
        ("IsDelivered", "is_delivered"), ("customer_balance_before", "customer_balance_before"),
        ("CreatedDate", "created_at"), ("CreatedBy", "created_by"), ("ModifiedDate", "modified_at"),
        ("ModifiedBy", "modified_by"), ("ValidatedDate", "validated_at"), ("ValidatedBy", "validated_by"),
    ], log, "raw `Extra` JSON parsed into `Extra_cosld`, `DefaultStock_Id` single store")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_documents, prerequisites=[clean_document_types])

"""
Nettoyage de `StockMovements.csv` -> `cleaned/stock_movements.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_StockMovements.py
    python script_cleaning_StockMovements.py --synthetique   # données générées -> cleaned/synthetique/
"""
from cleaning_commun import *  # noqa: F401,F403


MOVE_KIND = [
    ("Vente Comptoir", "COUNTER_SALE"), ("Bon de livraison", "DELIVERY_NOTE"), ("Facture fournisseur", "SUPPLIER_INVOICE"),
    ("Facture client", "CUSTOMER_INVOICE"), ("Avoir", "CREDIT_NOTE"), ("Bon de retour", "RETURN_NOTE"),
    ("Bon de r", "GOODS_RECEIPT"), ("Stock Initial", "INITIAL_STOCK"), ("Modification manuelle", "MANUAL_ADJUSTMENT"),
]


def movement_kind(desc):
    action = ("VALIDATION" if desc.startswith("Validation") else "CORRECTION" if desc.startswith("Correction")
              else "MANUAL" if desc.startswith("Modification") else "INITIAL" if "Stock Initial" in desc else "OTHER")
    kind = next((k for s, k in MOVE_KIND if s.lower() in desc.lower()), "OTHER")
    ref = desc.split(" - ", 1)[1].strip() if " - " in desc else ""
    return action, kind, ref


def clean_stock_movements():
    log = Log("stock_movements.csv", ["StockMovements.csv"], "Every stock movement (fact table Fact_StockMovement).")
    cols, recs, _ = read("StockMovements.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    parsed = 0
    for r in recs:
        r["action"], r["source_kind"], r["reference"] = movement_kind(r["Description"])
        try:
            e = json.loads(r.get("Extra") or "{}")
        except ValueError:
            e = {}
        r["purchase_price"] = fmt(fnum(e.get("prc")), 4) if "prc" in e else ""
        r["avg_unit_cost"] = fmt(fnum(e.get("cump")), 4) if "cump" in e else ""
        parsed += bool(e)
        r["product_id"] = LK["stock_to_product"].get(r["ProductStock_Id"], "")
        if r["DocumentId"] == "0":
            r["DocumentId"] = ""
        r["direction"] = "IN" if fnum(r["Quantity"], 0) > 0 else "OUT" if fnum(r["Quantity"], 0) < 0 else "NONE"
    log("Split `Description` into `action` (VALIDATION / CORRECTION / MANUAL / INITIAL), `source_kind` "
        "(COUNTER_SALE, DELIVERY_NOTE, SUPPLIER_INVOICE, CUSTOMER_INVOICE, CREDIT_NOTE, INITIAL_STOCK, MANUAL_ADJUSTMENT…) "
        "and `reference` (document number, e.g. VC0001/24 or the supplier's invoice number).")
    log(f"Parsed the `Extra` JSON into `purchase_price` (prc) and `avg_unit_cost` (cump = weighted average cost, "
        f"the best cost for margin calculation) on {parsed:,} rows.")
    log("Added `product_id` (via ProductStocks) and `direction` (IN / OUT / NONE). `document_id` = 0 (initial stock, "
        "manual change) replaced by empty.")
    kinds = Counter(r["source_kind"] for r in recs)
    log("Movements by source: " + ", ".join(f"{k} {v:,}" for k, v in kinds.most_common()) + ".")
    cols, recs = select(recs, [
        ("Id", "movement_id"), ("MovementDate", "movement_date"), ("ProductStock_Id", "product_stock_id"),
        ("product_id", "product_id"), ("DocumentId", "document_id"), ("action", "action"),
        ("source_kind", "source_kind"), ("reference", "reference"), ("direction", "direction"),
        ("Quantity", "quantity"), ("CurrentBalance", "balance_after"), ("purchase_price", "purchase_price"),
        ("avg_unit_cost", "avg_unit_cost"), ("User_Id", "user_id"), ("Description", "description"),
    ], log, "raw `Extra` JSON (parsed)")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_stock_movements)

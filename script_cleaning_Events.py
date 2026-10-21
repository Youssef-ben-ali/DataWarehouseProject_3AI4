"""
Nettoyage de `Events.csv` -> `cleaned/audit_events.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_Events.py
"""
from cleaning_commun import *  # noqa: F401,F403


ENTITY = {"1": "PRODUCT", "3": "BARCODE", "4": "PRODUCT_STOCK", "6": "APPLICABLE_TAX", "7": "PRODUCT_PRICE"}


EVTYPE = {"1": "CREATED", "2": "UPDATED", "3": "DELETED"}


def clean_events():
    log = Log("audit_events.csv", ["Events.csv"], "Audit log of product / stock / price changes (who changed what, when).")
    cols, recs, _ = read("Events.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        r["entity"] = ENTITY.get(r["EntityType"], r["EntityType"])
        r["event"] = EVTYPE.get(r["EventType"], r["EventType"])
        try:
            d = json.loads(r["Data"])
        except ValueError:
            d = {}
        r["product_id"] = str(d.get("pId", r["EntityId"] if r["entity"] == "PRODUCT" else ""))
        r["quantity_change"] = fmt(fnum(d.get("qte")), 3) if "qte" in d else ""
        r["stock_after"] = fmt(fnum(d.get("tQte")), 3) if "tQte" in d else ""
        r["price_ht"] = fmt(fnum(d.get("ht", d.get("ppHt"))), 3) if ("ht" in d or "ppHt" in d) else ""
        r["price_ttc"] = fmt(fnum(d.get("ttc")), 3) if "ttc" in d else ""
        r["margin_pct"] = fmt(fnum(d.get("mrg")), 2) if "mrg" in d else ""
        r["product_label"] = collapse(d.get("lbl", "")) if isinstance(d.get("lbl"), str) else ""
        m = RE_DOCNUM.search(r.get("Reason", ""))
        r["document_number"] = m.group(1) if m else ""
    log(f"Decoded the numeric codes: `EntityType` → `entity` {dict(Counter(r['entity'] for r in recs))}; "
        "`EventType` → `event` (1 CREATED, 2 UPDATED, 3 DELETED). Codes deduced from the JSON content of each event.")
    log("Flattened the useful keys of the `Data` JSON into columns: product_id, quantity_change, stock_after, price_ht, "
        "price_ttc, margin_pct, product_label. The full JSON is kept in `data` for other keys.")
    log("Extracted `document_number` from `Reason` (e.g. `Validation de Vente Comptoir - VC0001/24`).")
    log("266 cells still contain `�` inside the original JSON / labels (accent lost in the source export); left as is "
        "because these columns are informational only.")
    log("Note: stock events here duplicate StockMovements.csv; this file is mainly useful for the history of price "
        "changes and for 'who did what' (user activity).")
    cols, recs = select(recs, [
        ("Id", "event_id"), ("Timestamp", "timestamp"), ("UserId", "user_id"), ("entity", "entity"),
        ("EntityId", "entity_id"), ("event", "event"), ("product_id", "product_id"),
        ("product_label", "product_label"), ("quantity_change", "quantity_change"), ("stock_after", "stock_after"),
        ("price_ht", "price_ht"), ("price_ttc", "price_ttc"), ("margin_pct", "margin_pct"),
        ("document_number", "document_number"), ("Reason", "reason"), ("Data", "data"),
    ], log, "dependent-entity id/type columns (redundant with product_id), numeric type codes (decoded)")
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_events)

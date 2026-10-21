"""
Nettoyage de `Produits - 24112025081625 (2).csv` -> `cleaned/products.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_Produits.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_products():
    log = Log("products.csv", ["Produits - 24112025081625 (2).csv"],
              "Product catalogue (dimension Dim_Product).")
    cols, recs, d = read("Produits - 24112025081625 (2).csv", log)
    cols = [c.replace("�", "é") for c in cols]
    recs = [{k.replace("�", "é"): v for k, v in r.items()} for r in recs]
    log.orig_cols.update(cols)
    log("Repaired the column names whose accents were already destroyed in the export (`Libell�` → `Libellé`).")

    # accent repair inside text values (the export replaced every accented letter by U+FFFD)
    known = set(LK["item_name_to_pid"]) | set(LK["label_to_pid"])
    repaired = 0
    for r in recs:
        for c in ("Libellé", "Désignation", "Libellé ticket de caisse", "Famille", "Marque"):
            v = r.get(c, "")
            if "�" not in v:
                continue
            repaired += 1
            cand = None
            for letter in ("E", "A", "I", "O", "U", "C", ""):
                t = collapse(v.replace("�", letter))
                if norm_name(t) in known:
                    cand = t
                    break
            if cand is None:
                cand = re.sub(r"\bN�", "N°", v).replace("�", "E")
            r[c] = cand
    log(f"Repaired {repaired} text cells containing the replacement character `�` (lost accent): "
        "chose the spelling that exists on sales lines / product events when possible, otherwise `�`→`E` "
        "(e.g. `SERR�E`→`SERREE`, `N�`→`N°`) – the rest of the data set is written in unaccented capitals.")

    cols, recs = standardize(cols, recs, log, "DMY")

    # product code: GUID, EAN, or EAN destroyed by Excel (scientific notation)
    kinds = Counter()
    for r in recs:
        code = r["Code"]
        if re.fullmatch(r"[0-9a-fA-F-]{36}", code):
            k = "GUID"
        elif re.fullmatch(r"\d{8,14}", code):
            k = "EAN"
        elif re.fullmatch(r"ART\d+", code):
            k = "ART_CODE"
        elif re.fullmatch(r"\d+,\d+E\+\d+", code, re.I):
            k = "CORRUPTED"
        elif code == "":
            k = "MISSING"
        else:
            k = "OTHER"
        r["code_type"] = k
        kinds[k] += 1
    log(f"Classified product codes: {dict(kinds)}. The {kinds['CORRUPTED']} `CORRUPTED` codes are barcodes that "
        "Excel converted to scientific notation (`3,66143E+12`): digits are lost and several products share the "
        "same value – this is why the raw file shows 67 'duplicate' codes. They are kept but marked "
        "`code_type = CORRUPTED`, and must not be used as a key.")

    # product_id (the software id used everywhere else)
    how = Counter()
    for r in recs:
        pid, src = "", ""
        if r["code_type"] == "GUID":
            pid = LK["code_to_pid"].get(r["Code"].lower(), "")
            src = "code" if pid else ""
        if not pid and r["code_type"] == "EAN":
            pid = LK["ean_to_pid"].get(r["Code"], "")
            src = "barcode" if pid else ""
        if not pid:
            n = norm_name(r["Libellé"])
            pid = LK["label_to_pid"].get(n) or LK["item_name_to_pid"].get(n, "")
            src = "name" if pid else ""
        r["product_id"], r["product_id_source"] = pid, src or "not found"
        how[src or "not found"] += 1
    log("Added `product_id` (the numeric id used by ProductStocks, Barcodes, ProductPrices, StockMovements…), "
        f"which the raw file does not contain. Matched by GUID code via product events in Events.csv: {how['code']:,}; "
        f"by barcode via Barcodes.csv: {how['barcode']:,}; by exact product name: {how['name']:,}; "
        f"not found: {how['not found']:,}. Column `product_id_source` tells how each match was made.")
    log("Products without `product_id` are mostly items created after the database export (the product list was exported "
        "on 24/11/2025, the transactions stop in April 2025) – they have no sales in this data set anyway.")
    log("`ART####` codes look like `ART` + product id, but for 119 of them that id belongs to a different product, so they "
        "were NOT used as a key (only the exact-name match was trusted).")

    # family & brand
    fam_empty = 0
    for r in recs:
        if not r["Famille"]:
            r["Famille"] = "NON CLASSE"
            fam_empty += 1
        r["Famille"] = norm_name(r["Famille"])
    big = {"TOILETTE", "COMPLEMENTS ALIMENTAIRES", "ACCESSOIRE", "COMPRIME", "ANIMALERIE", "NON CLASSE"}
    for r in recs:
        r["family_group"] = r["Famille"] if r["Famille"] in big else "AUTRES"
    small = sorted({r["Famille"] for r in recs if r["Famille"] not in big})
    log(f"Filled {fam_empty} empty family values with `NON CLASSE`. Added `family_group` that merges the "
        f"tiny families ({', '.join(small)}) into `AUTRES`; the original family is kept in `family`.")
    _, brands, _ = read("ProductBrands.csv", Log("_tmp", [], ""))
    REPORT.pop("_tmp", None)
    brand_id = {norm_name(b["BrandName"]): b["Id"].strip() for b in brands}
    b_empty, b_match = 0, 0
    for r in recs:
        r["Marque"] = norm_name(r["Marque"])
        if not r["Marque"]:
            b_empty += 1
        r["brand_id"] = brand_id.get(r["Marque"], "")
        b_match += bool(r["brand_id"])
    log(f"Brand names upper-cased and trimmed; {b_empty:,} products have no brand (left empty). "
        f"Added `brand_id` by matching the brand name with ProductBrands.csv ({b_match:,} matched).")

    # prices, margin, checks
    neg, missing_cost, ttc_bad = 0, 0, 0
    for r in recs:
        pa, pv, tva, ttc = (fnum(r["Prix d'achat HT"]), fnum(r["Prix de vente HT"]),
                            fnum(r["Tva"]), fnum(r["Prix de vente TTC"]))
        if pa is None or pa <= 0:
            missing_cost += 1
            r["margin_ht"] = r["margin_rate_pct"] = ""
        elif pv is not None and pv > 0:
            m = pv - pa
            r["margin_ht"], r["margin_rate_pct"] = fmt(m, 3), fmt(100 * m / pv, 2)
            neg += m < 0
        else:
            r["margin_ht"] = r["margin_rate_pct"] = ""
        r["price_check"] = "OK"
        if pv is not None and tva is not None and ttc is not None and abs(pv * (1 + tva / 100) - ttc) > 0.05:
            r["price_check"] = "TTC_NOT_EQUAL_HT_PLUS_VAT"
            ttc_bad += 1
        if pa is not None and pv is not None and pa > pv > 0:
            r["price_check"] = "SOLD_BELOW_COST"
        if pv is not None and pv <= 0:
            r["price_check"] = "NO_SALE_PRICE"
        for c in ("Prix d'achat HT", "Prix de vente HT", "Tva", "Prix de vente TTC", "Quantité", "Quantité d'Alerte"):
            r[c] = fmt(fnum(r[c]), 3) if r[c] else ""
    log(f"Added `margin_ht` (sale HT − purchase HT) and `margin_rate_pct` (margin / sale HT). "
        f"{missing_cost:,} products have no purchase price (margin left empty); {neg:,} have a negative margin.")
    log(f"Added `price_check` flag: SOLD_BELOW_COST, NO_SALE_PRICE, or TTC_NOT_EQUAL_HT_PLUS_VAT "
        f"({ttc_bad:,} rows where TTC ≠ HT × (1+VAT)). Rows are kept, only flagged.")
    for r in recs:
        r["is_deleted_in_software"] = "true" if r["product_id"] in LK["deleted_pids"] else "false"

    # designation identical to name?
    same = sum(1 for r in recs if norm_name(r.get("Désignation", "")) == norm_name(r["Libellé"]))
    note = f"`Désignation` is identical to `Libellé` in {same:,}/{len(recs):,} rows; `Unité` contains only 0/empty"
    # true duplicates (same name + same prices)
    seen, out, dups = set(), [], 0
    for r in recs:
        key = (norm_name(r["Libellé"]), r["Prix d'achat HT"], r["Prix de vente HT"], r["product_id"])
        if key in seen:
            dups += 1
            continue
        seen.add(key)
        out.append(r)
    recs = out
    log(f"Removed {dups} true duplicate product(s) (same name, same prices, same product_id).")
    for i, r in enumerate(recs, 1):
        r["product_key"] = str(i)
        r["Libellé"] = collapse(r["Libellé"])
    log("Added `product_key`, a unique surrogate key (1…N), because the original `Code` is not unique.")

    cols, recs = select(recs, [
        ("product_key", "product_key"), ("product_id", "product_id"), ("product_id_source", "product_id_source"),
        ("Code", "product_code"), ("code_type", "code_type"), ("Libellé", "product_name"),
        ("Famille", "family"), ("family_group", "family_group"), ("Marque", "brand"), ("brand_id", "brand_id"),
        ("Prix d'achat HT", "purchase_price_ht"), ("Prix de vente HT", "sale_price_ht"), ("Tva", "vat_rate_pct"),
        ("Prix de vente TTC", "sale_price_ttc"), ("margin_ht", "margin_ht"), ("margin_rate_pct", "margin_rate_pct"),
        ("price_check", "price_check"), ("Quantité", "stock_quantity"), ("Quantité d'Alerte", "alert_quantity"),
        ("is_deleted_in_software", "is_deleted_in_software"),
    ], log, note)
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_products)

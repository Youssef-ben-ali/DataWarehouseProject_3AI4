"""
Nettoyage de `Barcodes.csv` -> `cleaned/barcodes.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_Barcodes.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_barcodes():
    log = Log("barcodes.csv", ["Barcodes.csv"], "Barcode (EAN) of each product.")
    cols, recs, _ = read("Barcodes.csv", log)
    raw_codes = {r["Id"]: r["Code"].strip() for r in recs}
    cols, recs = standardize(cols, recs, log, "DMY")
    before = len(recs)
    recs = [r for r in recs if r["Code"] not in ("", "0")]
    log(f"Removed {before - len(recs)} row(s) with code `0` / empty (placeholder, not a barcode).")
    kinds = Counter()
    for r in recs:
        r["Code"] = raw_codes.get(r["Id"], r["Code"])
        c = r["Code"]
        if c.isdigit():
            k = {13: "EAN13", 8: "EAN8", 12: "UPC12"}.get(len(c), "OTHER_NUMERIC")
        else:
            k = "INTERNAL_TEXT"
        r["code_kind"] = k
        kinds[k] += 1
        if k == "EAN13":
            s = sum(int(x) * (3 if i % 2 else 1) for i, x in enumerate(c[:12]))
            r["is_valid_ean"] = "true" if (10 - s % 10) % 10 == int(c[12]) else "false"
        else:
            r["is_valid_ean"] = ""
    bad = sum(r["is_valid_ean"] == "false" for r in recs)
    log("Kept `Code` as text (never as a number, to keep leading zeros and all 13 digits).")
    log(f"Added `code_kind`: {dict(kinds)}. `INTERNAL_TEXT` are shop abbreviations (e.g. `BASILIC SECH`), not real barcodes.")
    log(f"Added `is_valid_ean` (EAN-13 check-digit test): {bad} EAN-13 codes fail the check.")
    cols, recs = select(recs, [("Id", "barcode_id"), ("Product_Id", "product_id"), ("Code", "code"),
                               ("code_kind", "code_kind"), ("is_valid_ean", "is_valid_ean"), ("Type", "type")], log)
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_barcodes)

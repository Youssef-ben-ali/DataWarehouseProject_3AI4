#!/usr/bin/env python3
"""
Health Retailers – data cleaning script.

Reads the raw CSV export in  ./fichiers/   (never modified)
Writes cleaned copies to     ./cleaned/
plus CLEANING_REPORT.md describing every action taken on every file.

Standard library only (no pandas needed). Re-run any time:
    python clean_data.py

Output conventions (all files):
  - UTF-8 (no BOM), comma delimiter, header in snake_case English
  - decimal point (42.38, never 42,38)
  - dates ISO 8601: YYYY-MM-DD or YYYY-MM-DD HH:MM
  - booleans: true / false
  - empty cell = missing value
"""
import csv
import html
import io
import json
import re
import unicodedata
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

csv.field_size_limit(2**31 - 1)

HERE = Path(__file__).resolve().parent
SRC = HERE / "fichiers"
OUT = HERE / "cleaned"

REPORT = OrderedDict()  # output file name -> info dict


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
class Log:
    def __init__(self, out_name, sources, purpose):
        self.out_name = out_name
        self.sources = sources
        self.purpose = purpose
        self.steps = []
        self.rows_in = 0
        self.cols_in = 0
        self.orig_cols = set()
        self.renames = {}
        REPORT[out_name] = self

    def __call__(self, msg):
        self.steps.append(msg)


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def decode(path):
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig"), "UTF-8"
    except UnicodeDecodeError:
        pass
    # legacy file: Windows-1252 or old DOS code page 850 – keep the one that yields real French letters
    best = None
    for cp, label in (("cp1252", "Windows-1252"), ("cp850", "DOS code page 850")):
        t = raw.decode(cp, errors="replace")
        score = sum(t.count(ch) for ch in "éèàçêù°É") - 3 * sum(t.count(ch) for ch in "ŠŠ‚ø")
        if best is None or score > best[0]:
            best = (score, t, label)
    return best[1], best[2]


def unique_header(header):
    seen, out = Counter(), []
    for h in header:
        h = h.strip() or "unnamed"
        seen[h] += 1
        out.append(h if seen[h] == 1 else f"{h}_{seen[h]}")
    return out


def read(fname, log, text=None):
    """Return (columns, records) for a raw source file."""
    text, enc = decode(SRC / fname)
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") > first.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    header = unique_header(rows[0])
    body = [r for r in rows[1:] if any(c.strip() for c in r)]
    blank = len(rows) - 1 - len(body)
    recs = []
    for r in body:
        r = r + [""] * (len(header) - len(r))
        recs.append(dict(zip(header, r)))
    log.rows_in += len(recs)
    log.cols_in = max(log.cols_in, len(header))
    log.orig_cols.update(header)
    log(f"Read `{fname}`: {len(recs):,} rows × {len(header)} columns, "
        f"encoding {enc}, delimiter `{delim}`.")
    if enc != "UTF-8":
        log(f"Re-encoded from {enc} to UTF-8 (fixes broken accents such as `pi�ce` → `pièce`).")
    if blank:
        log(f"Removed {blank} completely blank line(s).")
    return header, recs, delim


# --------------------------------------------------------------------------- #
# Generic standardisation
# --------------------------------------------------------------------------- #
BOOL_MAP = {"VRAI": "true", "FAUX": "false", "TRUE": "true", "FALSE": "false"}
RE_DEC_COMMA = re.compile(r"^-?\d+(,\d+)?$")
RE_NUM = re.compile(r"^-?\d+(\.\d+)?$")
RE_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?: (\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


def is_num(v):
    return bool(RE_NUM.match(v))


def standardize(cols, recs, log, date_hint):
    """Trim, booleans, decimal commas, dates, empty/zero columns, duplicate rows."""
    # 1. trim whitespace
    trimmed = 0
    for r in recs:
        for c in cols:
            v = r[c]
            s = v.strip()
            if s != v:
                trimmed += 1
                r[c] = s
    if trimmed:
        log(f"Trimmed leading/trailing spaces in {trimmed:,} cells.")

    bool_cols, dec_cols, date_cols = [], [], []
    for c in cols:
        vals = [r[c] for r in recs if r[c] != ""]
        if not vals:
            continue
        # 2. booleans
        if all(v.upper() in BOOL_MAP for v in vals):
            for r in recs:
                if r[c]:
                    r[c] = BOOL_MAP[r[c].upper()]
            bool_cols.append(c)
            continue
        # 3. decimal comma
        if all(RE_DEC_COMMA.match(v) for v in vals) and any("," in v for v in vals):
            for r in recs:
                r[c] = r[c].replace(",", ".")
            dec_cols.append(c)
            continue
        # 4. dates
        parsed = [RE_DATE.match(v) for v in vals]
        if all(parsed):
            a_big = any(int(m.group(1)) > 12 for m in parsed)
            b_big = any(int(m.group(2)) > 12 for m in parsed)
            order = "DMY" if a_big else "MDY" if b_big else date_hint
            all_midnight = all((m.group(4) in (None, "0", "00")) and (m.group(5) in (None, "00"))
                               for m in parsed)
            for r in recs:
                m = RE_DATE.match(r[c]) if r[c] else None
                if not m:
                    continue
                a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
                d, mo = (a, b) if order == "DMY" else (b, a)
                out = f"{y}-{mo:02d}-{d:02d}"
                if not all_midnight:
                    out += f" {int(m.group(4) or 0):02d}:{m.group(5) or '00'}"
                    if m.group(6):
                        out += f":{m.group(6)}"
                r[c] = out
            date_cols.append(f"{c} ({'DD/MM/YYYY' if order == 'DMY' else 'MM/DD/YYYY'})")
    if bool_cols:
        log(f"Booleans VRAI/FAUX/TRUE/FALSE → true/false in: {', '.join(bool_cols)}.")
    if dec_cols:
        log(f"Decimal comma → decimal point in: {', '.join(dec_cols)}.")
    if date_cols:
        log(f"Dates converted to ISO format (YYYY-MM-DD[ HH:MM]) from: {', '.join(date_cols)}.")

    # 5. empty and always-zero columns
    empty = [c for c in cols if all(r[c] == "" for r in recs)]
    zero = [c for c in cols if c not in empty
            and all(r[c] == "" or (is_num(r[c]) and float(r[c]) == 0) for r in recs)
            and not c.lower().endswith("id")]
    drop = empty + zero
    if empty:
        log(f"Dropped {len(empty)} column(s) that are 100 % empty: {', '.join(empty)}.")
    if zero:
        log(f"Dropped {len(zero)} column(s) that are always 0 (no information): {', '.join(zero)}.")
    cols = [c for c in cols if c not in drop]
    for r in recs:
        for c in drop:
            r.pop(c, None)

    # 6. exact duplicate rows
    seen, out = set(), []
    for r in recs:
        key = tuple(r[c] for c in cols)
        if key not in seen:
            seen.add(key)
            out.append(r)
    if len(out) != len(recs):
        log(f"Removed {len(recs) - len(out):,} exact duplicate row(s).")
    return cols, out


# Names given to the columns ADDED by the cleaning (original columns always keep their original name).
# Values extracted from a JSON column are named <JsonColumn>_<jsonKey>, e.g. Extra_cump.
ADDED_NAMES = {
    "customer_balance_before": "Extra_cosld", "purchase_price": "Extra_prc", "avg_unit_cost": "Extra_cump",
    "cash_given": "Extra_gA", "change_returned": "Extra_rA", "default_register_id": "Tresorerie_defaultCaisseId",
    "quantity_change": "Data_qte", "stock_after": "Data_tQte", "price_ht": "Data_ht", "price_ttc": "Data_ttc",
    "margin_pct": "Data_mrg", "product_label": "Data_lbl", "document_number": "DocumentNumber",
    "register_name": "CaisseName", "bank_account_name": "BankAccountName", "document_type": "DocumentTypeName",
    "payment_mode": "PaymentModeName", "product_id_source": "ProductIdSource", "is_valid_ean": "IsValidEan",
}


def added_name(n):
    if n in ADDED_NAMES:
        return ADDED_NAMES[n]
    if n.endswith("_id"):
        return "".join(w.capitalize() for w in n[:-3].split("_")) + "_Id"
    return "".join(w.capitalize() for w in n.split("_"))


def select(recs, mapping, log, note=None):
    """Keep the columns listed in mapping [(old, new), ...]. Original columns keep their ORIGINAL name;
    columns added by the cleaning get a name in the software's style. The rest is logged as dropped."""
    available = set(recs[0].keys()) if recs else set()
    keep = [(o, n) for o, n in mapping if o in available]
    dropped = sorted(available - {o for o, _ in mapping})
    final = []
    for o, n in keep:
        f = (o.strip().strip("|").strip() or o) if o in log.orig_cols else added_name(n)
        final.append((o, f))
        log.renames[n] = f
    out = [{f: r.get(o, "") for o, f in final} for r in recs]
    added = [f for o, f in final if o not in log.orig_cols]
    log("Original column names kept unchanged."
        + (f" Columns added by the cleaning: {', '.join('`' + a + '`' for a in added)}." if added else ""))
    if dropped:
        log(f"Dropped column(s) not useful for analysis: {', '.join(dropped)}"
            + (f" ({note})." if note else "."))
    return [f for _, f in final], out


def snake(name):
    name = "".join(ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch))
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()


def write(cols, recs, log):
    OUT.mkdir(exist_ok=True)
    path = OUT / log.out_name
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in recs:
            w.writerow([r.get(c, "") for c in cols])
    log.rows_out, log.cols_out = len(recs), len(cols)
    log.columns = cols


def fnum(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fmt(x, nd=4):
    if x is None:
        return ""
    s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def collapse(s):
    return re.sub(r"\s+", " ", s).strip()


def strip_html(s):
    return collapse(html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " "))


def norm_name(s):
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return collapse(s.upper())


RE_DOCNUM = re.compile(r"\b([A-Z]{1,4}\d{3,}/\d{2})\b")

PAYMENT_MODES = {"1": "Cheque", "4": "Unknown (4)", "5": "Bank card",
                 "7": "Credit (pay later)", "11": "Cash", "21": "Tokens"}


# =========================================================================== #
# Shared look-ups built from several files
# =========================================================================== #
LK = {}


def build_lookups():
    # product stock id -> product id
    _, ps, _ = read("ProductStocks.csv", Log("_tmp", [], ""))
    LK["stock_to_product"] = {r["Id"].strip(): r["Product_Id"].strip() for r in ps}
    # product events in the audit log: id, GUID code, label
    lg = Log("_tmp", [], "")
    _, ev, _ = read("Events.csv", lg)
    code_to_id, label_to_id, deleted = {}, {}, set()
    for r in ev:
        if r["EntityType"].strip() != "1":
            continue
        pid = r["EntityId"].strip()
        if r["EventType"].strip() == "3":
            deleted.add(pid)
        try:
            d = json.loads(r["Data"])
        except ValueError:
            continue
        if d.get("cde"):
            code_to_id[str(d["cde"]).strip().lower()] = pid
        if d.get("lbl"):
            label_to_id[norm_name(d["lbl"])] = pid
    LK["code_to_pid"], LK["label_to_pid"], LK["deleted_pids"] = code_to_id, label_to_id, deleted
    # barcode -> product id
    _, bc, _ = read("Barcodes.csv", Log("_tmp", [], ""))
    LK["ean_to_pid"] = {r["Code"].strip(): r["Product_Id"].strip() for r in bc if r["Code"].strip() not in ("", "0")}
    # names used on sales lines
    _, di, _ = read("documentItemm.csv", Log("_tmp", [], ""))
    name_to_pid = defaultdict(Counter)
    for r in di:
        pid = LK["stock_to_product"].get(r["ProductStock_Id"].strip())
        if pid:
            name_to_pid[norm_name(strip_html(r["Description"]))][pid] += 1
    LK["item_name_to_pid"] = {k: v.most_common(1)[0][0] for k, v in name_to_pid.items()}
    # register (caisse) and bank account names from treasury events
    LK["registers"], LK["banks"] = {}, {}
    for r in read_domain_events():
        try:
            d = json.loads(r["Data"])
        except ValueError:
            continue
        if r["EventName"].endswith("CaisseAdded"):
            LK["registers"][d["caisseId"].upper()] = d.get("name", "")
        elif r["EventName"].endswith("BankAccountAdded"):
            LK["banks"][d["bankAccountId"].upper()] = (d.get("name", ""), d.get("bank", ""), d.get("initialBalance", ""))
    # companies: id -> code, code -> id
    LK["company_code"] = {}
    for k in ("_tmp",):
        REPORT.pop(k, None)


def read_domain_events():
    """DomainEvents.csv wraps every line in quotes; unwrap before parsing."""
    text, _ = decode(SRC / "DomainEvents.csv")
    lines = text.splitlines()
    fixed = [lines[0]]
    for ln in lines[1:]:
        if ln.startswith('"') and ln.endswith('"'):
            ln = ln[1:-1].replace('""', '"')
        fixed.append(ln)
    return list(csv.DictReader(io.StringIO("\n".join(fixed))))


# =========================================================================== #
# PRODUCTS
# =========================================================================== #
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


def clean_brands():
    log = Log("brands.csv", ["ProductBrands.csv"], "Brand list (dimension Dim_Brand).")
    cols, recs, _ = read("ProductBrands.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        r["BrandName"] = norm_name(r["BrandName"])
    log("Brand names upper-cased, accents removed and inner spaces collapsed (same rule as products.brand, so they join).")
    seen, out = {}, []
    for r in recs:
        if r["BrandName"] in seen:
            continue
        seen[r["BrandName"]] = r["Id"]
        out.append(r)
    if len(out) < len(recs):
        log(f"Removed {len(recs) - len(out)} duplicate brand name(s) (kept the lowest id).")
    cols, recs = select(out, [("Id", "brand_id"), ("BrandName", "brand_name")], log)
    write(cols, recs, log)


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


def clean_prices():
    log = Log("product_prices.csv", ["ProductPrices.csv"], "Price lists per product.")
    cols, recs, _ = read("ProductPrices.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    lists = Counter(r["PriceName_Id"] for r in recs)
    log(f"Price lists present (`price_list_id` → rows): {dict(lists)}. Price list 1 is the retail price used at the till.")
    recomputed = 0
    for r in recs:
        if not r.get("ProfitMargin"):
            r["ProfitMargin"] = ""
        r["vat_rate_pct"] = ""
        ht, ttc = fnum(r["PriceHt"]), fnum(r["PriceTtc"])
        if ht and ttc and ht > 0:
            r["vat_rate_pct"] = fmt(round(100 * (ttc / ht - 1), 1), 1)
            recomputed += 1
    log(f"Added `vat_rate_pct` deduced from TTC/HT ({recomputed:,} rows).")
    cols, recs = select(recs, [("Id", "price_id"), ("Product_Id", "product_id"), ("PriceName_Id", "price_list_id"),
                               ("PriceHt", "price_ht"), ("PriceTtc", "price_ttc"), ("vat_rate_pct", "vat_rate_pct"),
                               ("UseTva", "use_vat"), ("ProfitMargin", "profit_margin_pct")], log)
    write(cols, recs, log)


def clean_product_stocks():
    log = Log("product_stocks.csv", ["ProductStocks.csv"], "Current stock level per product (snapshot at export date).")
    cols, recs, _ = read("ProductStocks.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    same = all(r["Quantity"] == r["TotalQuantity"] for r in recs)
    stores = Counter(r["Stock_Id"] for r in recs)
    if same:
        log("`TotalQuantity` is identical to `Quantity` on every row (single store) → dropped.")
    log(f"`Stock_Id` values: {dict(stores)} → only one store/warehouse, column dropped.")
    neg = 0
    for r in recs:
        q = fnum(r["Quantity"], 0)
        r["Quantity"] = fmt(q, 3)
        r["stock_status"] = "NEGATIVE" if q < 0 else "OUT_OF_STOCK" if q == 0 else "IN_STOCK"
        neg += q < 0
    log(f"Added `stock_status` (IN_STOCK / OUT_OF_STOCK / NEGATIVE). {neg} products have a negative stock "
        "(sold before the purchase was recorded) – flagged, not changed.")
    cols, recs = select(recs, [("Id", "product_stock_id"), ("Product_Id", "product_id"),
                               ("Quantity", "quantity"), ("stock_status", "stock_status")], log)
    write(cols, recs, log)


# =========================================================================== #
# PARTNERS & USERS
# =========================================================================== #
def companies_table():
    log = Log("companies.csv", ["CompaniesList.csv"],
              "Every customer and supplier with the numeric `company_id` used by transactions and payments.")
    cols, recs, _ = read("CompaniesList.csv", log)
    name_col = [c for c in cols if "Name" in c][0]
    for r in recs:
        r[name_col] = r[name_col].strip().strip("|").strip()
        if set(r[name_col]) <= set("-"):
            r[name_col] = ""
    log("Removed the Markdown table pipes `|` and padding that surrounded every name (and in the header `| Name |`).")
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        if r["Id"] == "2":
            r[name_col] = "CLIENT COMPTOIR (ANONYME)"
            r["Code"] = "WALKIN"
        r[name_col] = collapse(r[name_col])
        r["company_type"] = {"1": "CUSTOMER", "2": "SUPPLIER"}.get(r["CompanyType_Id"], r["CompanyType_Id"])
    log("Company 2 had a lost name (`|-----|`) and code `__part__`: it is the generic walk-in customer used by most "
        "counter sales → renamed `CLIENT COMPTOIR (ANONYME)`, code `WALKIN`.")
    log("Added `company_type` (1 → CUSTOMER, 2 → SUPPLIER).")
    log("WARNING: the names in this file do NOT match the names in the Clients / Fournisseurs files for the same code "
        "(e.g. CL0001 = `Santélys Pharma` here but `Julien Moreau` in Clients; 0/47 customer names and 1/85 supplier names "
        "agree). Each file was anonymised separately. Join on `code`, never on name; for reporting, prefer the names in "
        "customers.csv / suppliers.csv.")
    cols, recs = select(recs, [("Id", "company_id"), ("Code", "code"), (name_col, "name"),
                               ("company_type", "company_type"), ("CompanyType_Id", "company_type_id"),
                               ("IsGuest", "is_guest"), ("IsRemoved", "is_removed")], log,
                        "technical columns Id3–Id7 and empty trailing columns; phone/e-mail removed as personal "
                        "contact data (GDPR) – they remain in the original file")
    LK["company_by_code"] = {r["Code"]: r["Id"] for r in recs}
    write(cols, recs, log)


def split_partner_name(raw):
    s = re.sub(r"^\s*\d+\.\s*", "", raw)
    if "—" in s:
        t, n = [collapse(x) for x in s.split("—", 1)]
    else:
        t, n = "", collapse(s)
    return t, n


def clean_customers():
    log = Log("customers.csv", ["Clients - 24112025081756 (3).csv"], "Named customers (dimension Dim_Customer).")
    cols, recs, _ = read("Clients - 24112025081756 (3).csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    types = Counter()
    for r in recs:
        t, n = split_partner_name(r["Nom"])
        r["customer_type"] = {"Client particulier": "INDIVIDUAL", "Laboratoire": "LABORATORY"}.get(t, t.upper() or "UNKNOWN")
        types[r["customer_type"]] += 1
        r["Nom"] = n
        r["company_id"] = LK["company_by_code"].get(r["Code"], "")
        for c in ("Solde", "Solde initial"):
            if c in r:
                r[c] = fmt(fnum(r[c], 0), 3)
        r["Ville"] = collapse(r["Ville"]).upper()
        r["Pays"] = collapse(r["Pays"]).upper()
    log("Split `Nom` (`1. Client particulier — Julien Moreau`) into `customer_type` and `customer_name`; "
        f"removed the `1.` numbering. Types: {dict(types)}.")
    log("City and country upper-cased; postal code kept as text.")
    matched = sum(bool(r["company_id"]) for r in recs)
    log(f"Added `company_id` by matching the customer code with companies.csv ({matched}/{len(recs)} matched). "
        "The others have no entry in CompaniesList.csv, so they cannot be linked to any transaction.")
    cols, recs = select(recs, [("company_id", "company_id"), ("Code", "customer_code"), ("Nom", "customer_name"),
                               ("customer_type", "customer_type"), ("Adresse", "address"),
                               ("Code postal", "postal_code"), ("Ville", "city"), ("Pays", "country"),
                               ("Solde", "balance"), ("Solde initial", "initial_balance")], log,
                        "e-mail removed as personal data (GDPR); website / trade register empty")
    write(cols, recs, log)


def clean_suppliers():
    log = Log("suppliers.csv", ["Fournisseurs - 24112025081816 (2).csv"], "Suppliers (dimension Dim_Supplier).")
    cols, recs, _ = read("Fournisseurs - 24112025081816 (2).csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        _, r["Nom"] = split_partner_name(r["Nom"])
        r["company_id"] = LK["company_by_code"].get(r["Code"], "")
        for c in ("Solde", "Solde initial"):
            if c in r:
                r[c] = fmt(fnum(r[c], 0), 3)
        r["Ville"] = collapse(r["Ville"]).upper()
        r["Pays"] = collapse(r["Pays"]).upper()
    log("Removed the `1.` numbering in front of every supplier name; city and country upper-cased.")
    matched = sum(bool(r["company_id"]) for r in recs)
    log(f"Added `company_id` by matching the supplier code with companies.csv ({matched}/{len(recs)} matched). "
        "The others have no entry in CompaniesList.csv, so they cannot be linked to any transaction.")
    cols, recs = select(recs, [("company_id", "company_id"), ("Code", "supplier_code"), ("Nom", "supplier_name"),
                               ("Adresse", "address"), ("Code postal", "postal_code"), ("Ville", "city"),
                               ("Pays", "country"), ("Solde", "balance"), ("Solde initial", "initial_balance")], log,
                        "e-mail removed (contact data); website empty")
    write(cols, recs, log)


def clean_users():
    log = Log("users.csv", ["users_csv.csv"], "Employees / cashiers (dimension Dim_Employee).")
    cols, recs, _ = read("users_csv.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        try:
            r["default_register_id"] = json.loads(r.get("Tresorerie") or "{}").get("defaultCaisseId", "").upper()
        except ValueError:
            r["default_register_id"] = ""
        r["is_staff"] = "false" if r["Id"] in ("1", "2") else "true"
    log("SECURITY: removed `Password` and `PasswordSalt` (password hashes must never reach the warehouse).")
    log("Parsed the `Tresorerie` JSON into `default_register_id`. Added `is_staff` (false for Administrateur and Système accounts).")
    cols, recs = select(recs, [("Id", "user_id"), ("FullName", "full_name"), ("UserName", "user_name"),
                               ("is_staff", "is_staff"), ("default_register_id", "default_register_id")], log,
                        "password hashes and raw JSON")
    write(cols, recs, log)


# =========================================================================== #
# DOCUMENTS
# =========================================================================== #
DOC_TYPE_EN = {
    "1": ("Customer invoice", "SALE"), "2": ("Quote (pro forma)", "QUOTE"), "3": ("Customer order", "ORDER"),
    "4": ("Customer credit note", "SALE_RETURN"), "5": ("Delivery note", "SALE"), "6": ("Counter sale", "SALE"),
    "7": ("Customer return note", "SALE_RETURN"), "8": ("Route invoice", "SALE"),
    "20": ("Supplier invoice", "PURCHASE"), "21": ("Supplier order", "ORDER"), "22": ("Goods receipt", "PURCHASE"),
    "23": ("Supplier credit note", "PURCHASE_RETURN"), "24": ("Return to supplier", "PURCHASE_RETURN"),
    "40": ("Stock exit note", "STOCK_OUT"), "41": ("Stock entry note", "STOCK_IN"),
}


def clean_document_types():
    log = Log("document_types.csv", ["DocumentTypes.csv"], "Meaning of every document type (dimension Dim_DocType).")
    cols, recs, _ = read("DocumentTypes.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        r["label_en"], r["flow"] = DOC_TYPE_EN.get(r["Id"], ("", ""))
    log("Added `label_en` (English name) and `flow` (SALE / SALE_RETURN / PURCHASE / PURCHASE_RETURN / QUOTE / ORDER / "
        "STOCK_IN / STOCK_OUT) so sales and purchases can be separated with one filter.")
    LK["doc_types"] = {r["Id"]: r for r in recs}
    cols, recs = select(recs, [("Id", "document_type_id"), ("Name", "name"), ("label_en", "label_en"),
                               ("flow", "flow"), ("StockFactor", "stock_factor"), ("IsSellType", "is_sell_type"),
                               ("IsPayable", "is_payable"), ("IsRefund", "is_refund"),
                               ("IsDeliverable", "is_deliverable"), ("IsEnabled", "is_enabled")], log,
                        "UI icon path, translation key, invoice footer text, internal priorities")
    write(cols, recs, log)


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


def clean_document_items():
    log = Log("document_items.csv", ["documentItemm.csv"],
              "One row per product line of every document – the grain of Fact_Sales / Fact_Purchases.")
    cols, recs, _ = read("documentItemm.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        r["Description"] = strip_html(r["Description"])
        r["product_id"] = LK["stock_to_product"].get(r["ProductStock_Id"], "")
    log("Removed the HTML formatting in `Description` (`<p style=…><span …>NAME</span></p>`) → plain `product_name`.")
    log("Added `product_id` through ProductStocks (product_stock_id → product_id).")
    log("`PrixHt` is the unit price BEFORE discount but `PrixTtc` is the unit price AFTER discount "
        "(34.25 × 1.19 × 0.80 = 32.61) – be careful when using them together.")
    bad = 0
    for r in recs:
        q, p, d, tot = (fnum(r["Quantity"], 0), fnum(r["PrixHt"], 0),
                        fnum(r.get("DiscountPourcentage"), 0) or 0, fnum(r["PrixTotalHt"], 0))
        if abs(q * p * (1 - d / 100) - tot) > 0.05:
            bad += 1
        for c in ("Quantity", "PrixHt", "Tva", "DiscountPourcentage", "PrixTotalHt", "TotalTva",
                  "PrixTotalTtc", "PrixTtc", "SumDiscountTotal"):
            if r.get(c):
                r[c] = fmt(fnum(r[c]), 4)
    log(f"Checked total_ht = quantity × unit_price_ht × (1 − discount %): {bad:,} lines differ by more than 0.05 "
        "(rounding / manual price) – kept as is.")
    cols, recs = select(recs, [
        ("Id", "item_id"), ("Document_Id", "document_id"), ("DisplayOrder", "line_number"),
        ("ProductStock_Id", "product_stock_id"), ("product_id", "product_id"), ("Description", "product_name"),
        ("Quantity", "quantity"), ("PrixHt", "unit_price_ht"), ("PrixTtc", "unit_price_ttc"),
        ("Tva", "vat_rate_pct"), ("DiscountPourcentage", "discount_pct"), ("SumDiscountTotal", "discount_amount_ht"),
        ("PrixTotalHt", "total_ht"), ("TotalTva", "total_vat"), ("PrixTotalTtc", "total_ttc"),
    ], log, "the `Sum…` columns repeat the line totals with more decimals (SumPrixTotalHt, SumTotalTva, SumPrixTotalTtc, "
            "SumPrixNetHt, SumPrixNetTtc, SumQuantityUnit…); `Extra` is always `{}`")
    write(cols, recs, log)


def clean_item_taxes():
    log = Log("item_taxes.csv", ["ItemTaxes.csv"], "VAT detail per document line (optional – VAT already on each line).")
    cols, recs, _ = read("ItemTaxes.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    log("Column `TotalHt` actually contains the TAX amount (e.g. base 27.40 × 19 % = 5.21), not a total excl. VAT "
        "– the original name is kept, be careful when using it.")
    cols, recs = select(recs, [("Id", "item_tax_id"), ("DocumentItem_Id", "item_id"), ("Tax_Id", "tax_id"),
                               ("TaxRate_Id", "tax_rate_id"), ("Rate", "rate_pct"),
                               ("CalculationMethod", "calculation_method"), ("Base", "base_ht"),
                               ("TotalHt", "tax_amount"), ("Type", "type")], log,
                        "the `Sum…` columns duplicate base and amount with more decimals")
    write(cols, recs, log)


def clean_document_reports():
    log = Log("document_reports.csv", ["DocumentsReports.csv"],
              "Technical per-line flags from the software report cache (low analytical value).")
    cols, recs, _ = read("DocumentsReports.csv", log)
    out, bad = [], 0
    for r in recs:
        try:
            d = json.loads(r["Benef"])
        except ValueError:
            bad += 1
            continue
        for it in d.get("di", []):
            out.append({"Id": r["Id"].strip(), "Benef_diid": str(it.get("diid", "")),
                        "Benef_pid": str(it.get("pid", "")),
                        "Benef_bcdde": str(it.get("bcdde", "")), "Benef_bcdve": str(it.get("bcdve", ""))})
    log(f"Unpacked the `Benef` JSON (one JSON list per document) into one row per document line: "
        f"{len(recs):,} documents → {len(out):,} rows. {bad} unreadable JSON value(s) skipped.")
    log("Despite its name, `Benef` holds no profit amount – only two unexplained 0/1 flags (`bcdde`, `bcdve`), kept "
        "as `Benef_bcdde`, `Benef_bcdve`. `Id` = document id, `Benef_diid` = document line id, `Benef_pid` = product "
        "stock id (new columns named <JsonColumn>_<jsonKey>). Recommendation: not needed for the warehouse.")
    write(["Id", "Benef_diid", "Benef_pid", "Benef_bcdde", "Benef_bcdve"], out, log)


def clean_related_documents():
    log = Log("related_documents.csv", ["RelatedDocuments.csv"],
              "Links between documents (e.g. delivery notes grouped into one invoice).")
    cols, recs, _ = read("RelatedDocuments.csv", log)
    rel = Counter(r["Relation"].strip() for r in recs)
    cols, recs = standardize(cols, recs, log, "DMY")
    log(f"`Relation` always has the same value {dict(rel)} → dropped.")
    cols, recs = select(recs, [("Id", "relation_id"), ("Document1_Id", "document_id"),
                               ("Document2_Id", "related_document_id")], log)
    write(cols, recs, log)


# =========================================================================== #
# TRANSACTIONS & PAYMENTS
# =========================================================================== #
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


def clean_transaction_payments():
    log = Log("transaction_payments.csv", ["TransactionPayments.csv"],
              "Bridge table transaction ↔ payment (a sale can be paid with several payments).")
    cols, recs, _ = read("TransactionPayments.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    cols, recs = select(recs, [("Id", "transaction_payment_id"), ("Transaction_Id", "transaction_id"),
                               ("Payment_Id", "payment_id"), ("Amount", "amount")], log)
    write(cols, recs, log)


def clean_payments():
    log = Log("payments.csv", ["PaymentsList.csv", "Payment.csv"],
              "Every customer/supplier payment (fact table Fact_Payment). Merges the two overlapping payment files.")
    c1, pl, _ = read("PaymentsList.csv", log)
    c1, pl = standardize(c1, pl, log, "DMY")
    c2, py, _ = read("Payment.csv", log)
    c2, py = standardize(c2, py, log, "DMY")
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


# =========================================================================== #
# TREASURY
# =========================================================================== #
def register_name(gid):
    n = LK["registers"].get((gid or "").upper(), "")
    return f"Caisse {n}" if n else ""


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


def clean_domain_events():
    log = Log("treasury_events.csv", ["DomainEvents.csv"], "Full event log of the treasury module.")
    text, _ = decode(SRC / "DomainEvents.csv")
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


# =========================================================================== #
# STOCK & AUDIT
# =========================================================================== #
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


def clean_inventory():
    log = Log("inventory_items.csv", ["InventaireItems.csv"], "Physical inventory count lines.")
    cols, recs, _ = read("InventaireItems.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    log("`FinalRealQuantity` (counted quantity) is 100 % empty: the physical count was never entered, so no "
        "counted-vs-theoretical difference can be computed. The file is only a snapshot of the theoretical stock.")
    cols, recs = select(recs, [("Id", "inventory_item_id"), ("Inventaire_Id", "inventory_id"),
                               ("Product_Id", "product_id"), ("TheoricalQuantity", "theoretical_quantity"),
                               ("FinalRealQuantity", "counted_quantity"),                                ("Movements", "movements")], log, "`Stock_Id` single store")
    write(cols, recs, log)


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


# =========================================================================== #
# CONFIGURATION
# =========================================================================== #
def clean_tax_rates():
    log = Log("tax_rates.csv", ["taxRates.csv"], "Tax rate definitions (reference).")
    cols, recs, _ = read("taxRates.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    for r in recs:
        r["is_active"] = "true" if not r.get("EndDate") else "false"
    log("Added `is_active` (no end date). Only the VAT rates 7 %, 13 %, 19 % (Tax_Id 3) appear on sales lines.")
    cols, recs = select(recs, [("Id", "tax_rate_id"), ("Name", "name"), ("Tax_Id", "tax_id"), ("Rate", "rate"),
                               ("Country", "country_code"), ("CalculationMethod", "calculation_method"),
                               ("StartDate", "start_date"), ("EndDate", "end_date"), ("is_active", "is_active")], log)
    write(cols, recs, log)


def clean_generic(src, out, purpose, verdict):
    log = Log(out, [src], purpose)
    cols, recs, _ = read(src, log)
    cols, recs = standardize(cols, recs, log, "DMY")
    mapping = [(c, snake(c)) for c in cols]
    cols, recs = select(recs, mapping, log)
    log(verdict)
    write(cols, recs, log)


def clean_settings():
    log = Log("app_settings.csv", ["users_settings_csv.csv"], "Software settings (configuration).")
    cols, recs, _ = read("users_settings_csv.csv", log)
    cols, recs = standardize(cols, recs, log, "DMY")
    big = [r["SettingName"] for r in recs if len(r["Value"]) > 300]
    recs = [r for r in recs if len(r["Value"]) <= 300]
    log(f"Removed {len(big)} setting(s) whose value is a large report/print template or base64 logo image "
        f"(> 300 characters): {', '.join(big)}.")
    log("Kept settings worth quoting in the report: `Country = 3`, `InvoiceCurrencySymb = DT` (Tunisian dinar) – evidence "
        "of the Tunisian origin of the software. Not needed for the warehouse.")
    cols, recs = select(recs, [("Id", "setting_id"), ("SettingName", "name"), ("Value", "value")], log)
    write(cols, recs, log)


# =========================================================================== #
# REPORT
# =========================================================================== #
VERDICT = {
    "document_items.csv": "CORE", "documents.csv": "CORE", "stock_movements.csv": "CORE", "products.csv": "CORE",
    "transactions.csv": "CORE", "payments.csv": "CORE", "product_stocks.csv": "USEFUL", "document_types.csv": "USEFUL",
    "brands.csv": "USEFUL", "customers.csv": "USEFUL", "suppliers.csv": "USEFUL", "companies.csv": "USEFUL",
    "transaction_payments.csv": "USEFUL", "product_prices.csv": "USEFUL", "inventory_items.csv": "USEFUL",
    "treasury_events.csv": "USEFUL", "cash_register_events.csv": "USEFUL", "registers_and_bank_accounts.csv": "USEFUL",
    "cash_operations.csv": "USEFUL", "treasury_payments.csv": "USEFUL", "users.csv": "USEFUL",
    "barcodes.csv": "LOW", "item_taxes.csv": "LOW", "document_reports.csv": "LOW", "related_documents.csv": "LOW",
    "audit_events.csv": "LOW", "tax_rates.csv": "LOW", "applicable_taxes.csv": "CONFIG", "permissions.csv": "CONFIG",
    "app_settings.csv": "CONFIG",
}


def write_report():
    L = ["# Cleaning report – Health Retailers data set", "",
         "Generated by `clean_data.py`. Originals in `fichiers/` were **not modified**; every cleaned file is in `cleaned/`.",
         "", "## Rules applied to every file", "",
         "- Read with the right encoding (UTF-8 or Windows-1252) and delimiter (`;` or `,`), written back as **UTF-8, comma-separated**.",
         "- **Original column names are kept unchanged** (only the broken accents of the Produits header were restored: "
         "`Libell�` → `Libellé`, and the pipes removed from CompaniesList: `| Name |` → `Name`).",
         "- Columns ADDED by the cleaning are named in the software's style (`Product_Id`, `IsValidated`, `CaisseName`…); "
         "values extracted from a JSON column are named `<JsonColumn>_<jsonKey>` (e.g. `Extra_cump`, `Data_qte`).",
         "- Leading / trailing spaces trimmed in every cell.",
         "- **Decimal comma → decimal point** (`42,38` → `42.38`).",
         "- **Dates → ISO 8601** (`9/30/2024 8:28` and `30/09/2024 08:28` both → `2024-09-30 08:28`). The day/month order is "
         "detected per column (a value > 12 tells which part is the day).",
         "- **Booleans → true / false** (`VRAI/FAUX`, `TRUE/FALSE`).",
         "- Columns that are 100 % empty or always 0 dropped; exact duplicate rows removed.",
         "- Rows are never silently corrected: doubtful values are **flagged** in an extra column, not changed.",
         "- Personal / secret data removed: password hashes, e-mails and phone numbers.", "",
         "## Summary", "", "| Cleaned file | From | Verdict | Rows in → out | Columns in → out |", "|---|---|---|---|---|"]
    for name, lg in REPORT.items():
        L.append(f"| `{name}` | {', '.join('`'+s+'`' for s in lg.sources)} | {VERDICT.get(name, '')} | "
                 f"{lg.rows_in:,} → {lg.rows_out:,} | {lg.cols_in} → {lg.cols_out} |")
    L += ["", "Verdict: CORE = main fact / dimension data · USEFUL = dimension or enrichment · LOW = optional · "
          "CONFIG = software configuration, not needed for analysis.", "", "## What was done to each file", ""]
    for name, lg in REPORT.items():
        L += [f"### `{name}`  ←  {', '.join(lg.sources)}", "", f"*{lg.purpose}*", ""]
        steps = []
        for st in lg.steps:
            for n, f in sorted(lg.renames.items(), key=lambda x: -len(x[0])):
                if n != f:
                    st = st.replace(f"`{n}`", f"`{f}`")
            steps.append(st)
        L += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
        L += ["", f"**Output columns:** {', '.join('`'+c+'`' for c in lg.columns)}", ""]
    (OUT / "CLEANING_REPORT.md").write_text("\n".join(L), encoding="utf-8")


def main():
    build_lookups()
    clean_document_types()
    companies_table()
    clean_products()
    clean_brands()
    clean_barcodes()
    clean_prices()
    clean_product_stocks()
    clean_customers()
    clean_suppliers()
    clean_users()
    clean_documents()
    clean_document_items()
    clean_item_taxes()
    clean_document_reports()
    clean_related_documents()
    clean_transactions()
    clean_transaction_payments()
    clean_payments()
    clean_treasury_payments()
    clean_cash_operations()
    clean_domain_events()
    clean_stock_movements()
    clean_inventory()
    clean_events()
    clean_tax_rates()
    clean_generic("ApplicableTaxes.csv", "applicable_taxes.csv", "Which tax applies to which product / document (software configuration).",
                  "Configuration only – kept for completeness, not needed for the warehouse.")
    clean_generic("Permissions.csv", "permissions.csv", "User access rights (software configuration).",
                  "Configuration only (GUID codes of screens and operations) – not needed for analysis.")
    clean_settings()
    write_report()
    for name, lg in REPORT.items():
        print(f"{name:38s} {lg.rows_in:>7,} -> {lg.rows_out:>7,} rows   {lg.cols_in:>3} -> {lg.cols_out:>3} cols")
    print(f"\nCleaned files and CLEANING_REPORT.md written to {OUT}")


if __name__ == "__main__":
    main()

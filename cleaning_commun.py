"""
Health Retailers – code commun aux scripts de nettoyage `script_cleaning_*.py`.

Lecture (encodage, séparateur), standardisation (décimales, dates ISO, booléens), sélection des colonnes,
écriture dans cleaned/, look-ups partagés entre fichiers et rapport de nettoyage.
Repris tel quel de clean_data.py (branche main) : mêmes règles, mêmes résultats.
"""
import csv
import html
import io
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

csv.field_size_limit(2**31 - 1)

HERE = Path(__file__).resolve().parent
if not (HERE / "fichiers").exists() and (HERE.parent / "fichiers").exists():
    HERE = HERE.parent  # branche montée comme sous-dossier du dépôt principal


REAL_SRC = HERE / "fichiers"


SRC = REAL_SRC


OUT = HERE / "cleaned"


SYNTH = "--synthetique" in sys.argv[1:]


SYNTH_SRC = HERE / "externe" / "donnees_synthetiques"


SYNTH_FILES = ["Documents.csv", "documentItemm.csv", "Transactions.csv", "TransactionPayments.csv", "PaymentsList.csv",
               "TresoreriePayments.csv", "CaisseOperations.csv", "StockMovements.csv", "DomainEvents.csv",
               "ProductStocks.csv"]


SYNTH_KEEP = {"documents.csv", "document_items.csv", "transactions.csv", "transaction_payments.csv", "payments.csv",
              "treasury_payments.csv", "cash_operations.csv", "treasury_events.csv", "cash_register_events.csv",
              "stock_movements.csv", "product_stocks.csv"}


REPORT = OrderedDict()  # output file name -> info dict


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
    for r in read_domain_events(REAL_SRC / "DomainEvents.csv"):   # créations de caisses : export réel uniquement
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


def read_domain_events(path=None):
    """DomainEvents.csv wraps every line in quotes; unwrap before parsing."""
    text, _ = decode(path or SRC / "DomainEvents.csv")
    lines = text.splitlines()
    fixed = [lines[0]]
    for ln in lines[1:]:
        if ln.startswith('"') and ln.endswith('"'):
            ln = ln[1:-1].replace('""', '"')
        fixed.append(ln)
    return list(csv.DictReader(io.StringIO("\n".join(fixed))))


def split_partner_name(raw):
    s = re.sub(r"^\s*\d+\.\s*", "", raw)
    if "—" in s:
        t, n = [collapse(x) for x in s.split("—", 1)]
    else:
        t, n = "", collapse(s)
    return t, n


DOC_TYPE_EN = {
    "1": ("Customer invoice", "SALE"), "2": ("Quote (pro forma)", "QUOTE"), "3": ("Customer order", "ORDER"),
    "4": ("Customer credit note", "SALE_RETURN"), "5": ("Delivery note", "SALE"), "6": ("Counter sale", "SALE"),
    "7": ("Customer return note", "SALE_RETURN"), "8": ("Route invoice", "SALE"),
    "20": ("Supplier invoice", "PURCHASE"), "21": ("Supplier order", "ORDER"), "22": ("Goods receipt", "PURCHASE"),
    "23": ("Supplier credit note", "PURCHASE_RETURN"), "24": ("Return to supplier", "PURCHASE_RETURN"),
    "40": ("Stock exit note", "STOCK_OUT"), "41": ("Stock entry note", "STOCK_IN"),
}


def register_name(gid):
    n = LK["registers"].get((gid or "").upper(), "")
    return f"Caisse {n}" if n else ""


def clean_generic(src, out, purpose, verdict):
    log = Log(out, [src], purpose)
    cols, recs, _ = read(src, log)
    cols, recs = standardize(cols, recs, log, "DMY")
    mapping = [(c, snake(c)) for c in cols]
    cols, recs = select(recs, mapping, log)
    log(verdict)
    write(cols, recs, log)


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
         ("Generated by `clean_data.py --synthetique` from the SYNTHETIC data in `externe/donnees_synthetiques/` "
          "(01/05/2025 → 29/09/2026), with the real reference files of `fichiers/`. Only the files built from generated "
          "data are kept here; the real cleaned files are in `cleaned/`." if SYNTH else
          "Generated by `clean_data.py`. Originals in `fichiers/` were **not modified**; every cleaned file is in `cleaned/`."),
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


def prepare_synthetic():
    """Dossier source temporaire : export réel + 10 fichiers générés à la place des fichiers réels."""
    global SRC, OUT
    OUT = HERE / "cleaned" / "synthetique"
    tmp = OUT / "_source"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    for p in REAL_SRC.glob("*.csv"):
        shutil.copy2(p, tmp / p.name)
    for name in SYNTH_FILES:
        shutil.copy2(SYNTH_SRC / name, tmp / name)
    SRC = tmp
    return tmp


def finish_synthetic(tmp):
    shutil.rmtree(tmp)
    for p in OUT.glob("*.csv"):
        if p.name not in SYNTH_KEEP:
            p.unlink()
    for name in list(REPORT):
        if name not in SYNTH_KEEP:
            REPORT.pop(name)


def run(cleaner, prerequisites=()):
    """Nettoie un fichier : look-ups partagés, tables préalables éventuelles, puis le fichier lui-même."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # flèches et accents dans la console Windows
    tmp = prepare_synthetic() if SYNTH else None
    build_lookups()
    for step in prerequisites:
        step()
    before = set(REPORT)
    cleaner()
    mine = [n for n in REPORT if n not in before]
    if SYNTH:
        finish_synthetic(tmp)
    for name in mine:
        lg = REPORT.get(name)
        if lg is None:
            print(f"{name}: not kept in synthetic mode (built from real reference data only)")
            continue
        print(f"{name}: {lg.rows_in:,} -> {lg.rows_out:,} rows, {lg.cols_in} -> {lg.cols_out} cols")
        for i, st in enumerate(lg.steps, 1):
            for n, f in sorted(lg.renames.items(), key=lambda x: -len(x[0])):
                if n != f:
                    st = st.replace(f"`{n}`", f"`{f}`")
            print(f"  {i}. {st}")
    print(f"\nWritten to {OUT}")
